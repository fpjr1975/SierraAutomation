"""
Sierra Automação - Bot Telegram
Recebe PDFs de seguradoras e gera orçamentos no layout Sierra.
Com edição inline de campos e fluxo de nova cotação (/nova).
"""

import os
import sys
import asyncio
import logging
import tempfile
import time
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import re
import json
import httpx

# Garante que o working directory é o diretório do bot
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ConversationHandler,
    filters, ContextTypes
)

from extractors import ExtractorFactory
from extractors.ai_extractor import AIExtractor
from generator_sierra_v7_alt import SierraPDFGeneratorV7 as SierraPDFGenerator
from ocr_docs import extract_document_data, format_document_response
from agilizador import calcular_cotacao, baixar_pdf_cotacao, fechar_sessao

# --- Config ---
BOT_TOKEN = os.environ.get("SIERRA_BOT_TOKEN", "")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "orcamentos")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ID do Fafá — recebe notificações de uso
ADMIN_ID = 6553672222

# Armazena dados extraídos por chat_id pra permitir edição
# {chat_id: {"data": {...}, "output_path": "...", "out_name": "...", "ai_used": bool}}
active_jobs = {}

# Sessões de nova cotação (/nova) — persistidas em disco
# {chat_id: {"cnh": {...}, "crvl": {...}, "cep": "...", "endereco": {...}}}
NOVA_SESSIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".nova_sessions.json")

# Controle de media_group para evitar processar o mesmo álbum duas vezes
# {media_group_id: timestamp}
_media_groups_seen: dict[str, float] = {}


def _try_parse_json_file(path: str) -> dict:
    """Tenta parsear um arquivo JSON. Retorna dict ou None em caso de erro."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return None
        data = json.loads(raw)
        if not isinstance(data, dict):
            logger.warning(f"Arquivo {path} não contém um dict JSON válido")
            return None
        return data
    except json.JSONDecodeError as e:
        logger.error(f"JSON inválido em {path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Erro ao ler {path}: {e}")
        return None


def _load_nova_sessions() -> dict:
    """
    Carrega sessões do arquivo JSON com múltiplos níveis de fallback.
    Fontes tentadas em ordem: arquivo principal → .bak → .tmp
    Nunca lança exceção: retorna dict vazio em último caso.
    """
    sources = [
        NOVA_SESSIONS_FILE,
        NOVA_SESSIONS_FILE + ".bak",
        NOVA_SESSIONS_FILE + ".tmp",
    ]

    for source in sources:
        if not os.path.exists(source):
            continue
        data = _try_parse_json_file(source)
        if data is not None:
            if source != NOVA_SESSIONS_FILE:
                logger.warning(f"Sessões restauradas de: {source}")
            try:
                sessions = {}
                for k, v in data.items():
                    if isinstance(v, dict):  # valida que cada sessão é um dict
                        sessions[int(k)] = v
                    else:
                        print(f"⚠️ Sessão ignorada (valor inválido) para chat_id={k}")
                print(f"📂 Sessões carregadas: {len(sessions)} chat(s) ativos")
                return sessions
            except Exception as e:
                print(f"❌ Erro ao processar sessões de {source}: {e}")
                continue

    print("⚠️ Nenhum arquivo de sessões válido encontrado — iniciando limpo")
    return {}


def _save_nova_sessions():
    """
    Salva sessões em arquivo JSON usando escrita atômica.
    Mantém backup da versão anterior (.bak).
    Nunca lança exceção.
    """
    try:
        # Serializa com try para garantir que o JSON é válido antes de escrever
        payload = json.dumps(
            {str(k): v for k, v in nova_sessions.items()},
            indent=2,
            ensure_ascii=False,
        )
        # Valida que o payload é JSON válido antes de prosseguir
        json.loads(payload)  # double-check

        tmp_file = NOVA_SESSIONS_FILE + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())

        # Backup do arquivo atual antes de sobrescrever
        if os.path.exists(NOVA_SESSIONS_FILE):
            os.replace(NOVA_SESSIONS_FILE, NOVA_SESSIONS_FILE + ".bak")

        # Rename atômico: garante que o arquivo nunca fica em estado inválido
        os.replace(tmp_file, NOVA_SESSIONS_FILE)

    except Exception as e:
        logger.error(f"Erro crítico ao salvar sessões: {e}", exc_info=True)


nova_sessions = _load_nova_sessions()

# Campos editáveis e seus labels
EDITABLE_FIELDS = {
    "segurado": "👤 Segurado",
    "condutor": "🧑 Condutor",
    "veiculo": "🚗 Veículo",
    "placa": "🔢 Placa",
    "vigencia": "📅 Vigência",
    "premio_total": "💰 Prêmio Total",
    "cep_pernoite": "📍 CEP",
    "uso": "🏷️ Uso",
}

EDITABLE_COBERTURAS = {
    "cob_danos_mat": "💥 Danos Materiais",
    "cob_danos_corp": "🏥 Danos Corporais",
    "cob_danos_mor": "⚖️ Danos Morais",
    "cob_casco": "🛡️ Casco/Compreensiva",
    "cob_guincho": "🚛 Guincho",
    "cob_reserva": "🚙 Carro Reserva",
}

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
WAITING_EDIT_VALUE = 1


async def notify_admin(context, user, filename, insurer, success, error_msg=None):
    """Envia notificação de uso pro admin (Fafá)."""
    user_name = user.full_name or "Desconhecido"
    user_username = f"@{user.username}" if user.username else f"ID:{user.id}"
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    if success:
        msg = (
            f"📊 *Uso do Sierra Bot*\n\n"
            f"👤 {user_name} ({user_username})\n"
            f"📄 `{filename}`\n"
            f"🏢 {insurer}\n"
            f"✅ Gerado com sucesso\n"
            f"🕐 {now}"
        )
    else:
        msg = (
            f"📊 *Uso do Sierra Bot*\n\n"
            f"👤 {user_name} ({user_username})\n"
            f"📄 `{filename}`\n"
            f"❌ Falhou: {error_msg}\n"
            f"🕐 {now}"
        )

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=msg,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Erro ao notificar admin: {e}")


async def _deactivate_gestor(chat_id: int):
    """Desativa sessão do Gastón quando outro comando é usado."""
    if chat_id in nova_sessions and nova_sessions[chat_id].get("gestor_active"):
        nova_sessions[chat_id].pop("gestor_active", None)
        _save_nova_sessions()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _deactivate_gestor(update.message.chat_id)
    await update.message.reply_text(
        "👋 Olá! Sou o assistente da *Sierra Seguros*.\n\n"
        "Veja o que posso fazer:\n\n"
        "🚗 */nova* — Iniciar cotação completa\n"
        "_(manda CNH + CRVL + CEP e calculo nas seguradoras)_\n\n"
        "📄 */converter* — Converter PDF de seguradora\n"
        "_(manda o PDF e gero no layout Sierra)_\n\n"
        "Digite `/` para ver todos os comandos disponíveis.",
        parse_mode="Markdown"
    )


async def converter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📄 *Conversor Sierra*\n\n"
        "Me envie o *PDF* gerado por qualquer seguradora e eu converto "
        "automaticamente para o layout padrão Sierra.\n\n"
        "✏️ Depois de gerar, você pode editar qualquer campo!\n\n"
        "_Seguradoras suportadas: Alfa, Aliro, Allianz, Azul, Bradesco, Darwin, "
        "Ezze, HDI, Itaú, Mapfre, Mitsui, Porto, Suhai, Suíça, Tokio, Yelum, Zurich "
        "+ qualquer outra via IA_ 🤖",
        parse_mode="Markdown"
    )


def build_edit_keyboard():
    """Monta teclado inline com campos editáveis."""
    buttons = []
    row = []
    for key, label in EDITABLE_FIELDS.items():
        row.append(InlineKeyboardButton(label, callback_data=f"edit_{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    # Coberturas em outra seção
    buttons.append([InlineKeyboardButton("── Coberturas ──", callback_data="noop")])
    row = []
    for key, label in EDITABLE_COBERTURAS.items():
        row.append(InlineKeyboardButton(label, callback_data=f"edit_{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton("❌ Fechar", callback_data="edit_close")])
    return InlineKeyboardMarkup(buttons)


def generate_pdf(data, output_path):
    """Gera o PDF Sierra a partir dos dados."""
    generator = SierraPDFGenerator(data, output_path)
    generator.generate()


def build_output_name(data):
    """Monta o nome do arquivo de saída."""
    segurado_raw = str(data.get("segurado") or "Cliente").upper()
    pj_suffixes = [r'\bLTDA\b', r'\bS/A\b', r'\bS\.A\.\b', r'\bME\b', r'\bEPP\b', r'\bSA\b']
    for suffix in pj_suffixes:
        segurado_raw = re.sub(suffix, '', segurado_raw)
    segurado_raw = segurado_raw.strip()

    parts = segurado_raw.split()
    if len(parts) >= 2:
        name_str = f"{parts[0]}.{parts[-1]}"
    elif parts:
        name_str = parts[0]
    else:
        name_str = "Cliente"

    insurer_code = str(data.get("insurer", "UNK"))[:3].upper()
    now_str = datetime.now().strftime("%d.%m.%y_%H.%M.%S")
    out_name = f"Orcamento.{name_str}.{insurer_code}.{now_str}.pdf"
    out_name = re.sub(r'[<>:"/\\|?*]', '', out_name)
    return out_name


async def send_pdf_with_edit(msg, context, data, output_path, out_name, ai_used, chat_id):
    """Envia o PDF e o botão de edição."""
    insurer_name = data.get("insurer", "Seguradora")
    segurado_display = data.get("segurado", "Cliente")
    veiculo = data.get("veiculo", "")
    ai_tag = " 🤖" if ai_used else ""

    caption = (
        f"✅ *Orçamento gerado!*{ai_tag}\n\n"
        f"👤 {segurado_display}\n"
        f"🚗 {veiculo}\n"
        f"🏢 {insurer_name}"
    )

    with open(output_path, "rb") as f:
        await msg.reply_document(
            document=f,
            filename=out_name,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ Editar", callback_data="edit_menu")]
            ])
        )


async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = msg.from_user
    doc = msg.document
    chat_id = msg.chat_id

    if not doc or not doc.file_name.lower().endswith(".pdf"):
        await msg.reply_text("⚠️ Por favor, envie um arquivo PDF.")
        return

    filename = doc.file_name
    status = await msg.reply_text("⏳ Recebendo PDF...")

    tmp_path = None
    try:
        file = await context.bot.get_file(doc.file_id)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name

        await file.download_to_drive(tmp_path)
        await status.edit_text("🔍 Identificando seguradora...")

        extractor = ExtractorFactory.get_extractor(tmp_path)
        ai_used = False
        if not extractor:
            await status.edit_text("🤖 Seguradora não reconhecida. Usando IA para extrair dados...")
            extractor = AIExtractor(tmp_path)
            ai_used = True

        await status.edit_text("⚙️ Extraindo dados e gerando orçamento...")

        data = extractor.extract()
        insurer_name = data.get("insurer", "Seguradora")

        out_name = build_output_name(data)
        output_path = os.path.join(OUTPUT_DIR, out_name)

        generate_pdf(data, output_path)

        # Guarda dados pra edição
        active_jobs[chat_id] = {
            "data": data,
            "output_path": output_path,
            "out_name": out_name,
            "ai_used": ai_used,
            "filename": filename
        }

        await send_pdf_with_edit(msg, context, data, output_path, out_name, ai_used, chat_id)
        await status.delete()
        await notify_admin(context, user, filename, insurer_name, True)

    except Exception as e:
        logger.error(f"Erro ao processar PDF: {e}", exc_info=True)
        await status.edit_text(
            f"❌ Erro ao processar o PDF:\n`{str(e)}`\n\n"
            "Tente novamente ou contate o suporte.",
            parse_mode="Markdown"
        )
        await notify_admin(context, user, filename, "?", False, str(e)[:100])
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except:
                pass


async def handle_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback dos botões de edição."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    callback = query.data

    if callback == "noop":
        return

    if callback == "edit_close":
        await query.edit_message_reply_markup(reply_markup=None)
        return

    if callback == "edit_menu":
        await query.edit_message_reply_markup(reply_markup=build_edit_keyboard())
        return

    if callback.startswith("edit_"):
        field = callback[5:]  # Remove "edit_"
        
        job = active_jobs.get(chat_id)
        if not job:
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("⚠️ Nenhum orçamento ativo para editar. Envie um novo PDF.")
            return

        # Mostra valor atual e pede novo
        if field.startswith("cob_"):
            current = get_cobertura_value(job["data"], field)
            label = EDITABLE_COBERTURAS.get(field, field)
        else:
            current = job["data"].get(field, "N/D")
            label = EDITABLE_FIELDS.get(field, field)

        context.user_data["editing_field"] = field
        context.user_data["editing_chat_id"] = chat_id

        await query.message.reply_text(
            f"✏️ *Editando: {label}*\n"
            f"Valor atual: `{current}`\n\n"
            f"Digite o novo valor:",
            parse_mode="Markdown"
        )
        return WAITING_EDIT_VALUE


def get_cobertura_value(data, field_key):
    """Busca valor de uma cobertura pelo campo."""
    coberturas = data.get("coberturas", [])
    search_map = {
        "cob_danos_mat": ["materiais", "material"],
        "cob_danos_corp": ["corporais", "corporal"],
        "cob_danos_mor": ["morais", "moral"],
        "cob_casco": ["casco", "compreensiva", "colisão"],
        "cob_guincho": ["guincho", "assistência"],
        "cob_reserva": ["reserva", "carro reserva"],
    }
    keywords = search_map.get(field_key, [])
    for name, val in coberturas:
        for kw in keywords:
            if kw in name.lower():
                return val
    return "N/D"


def set_cobertura_value(data, field_key, new_value):
    """Atualiza valor de uma cobertura pelo campo."""
    coberturas = data.get("coberturas", [])
    search_map = {
        "cob_danos_mat": ["materiais", "material"],
        "cob_danos_corp": ["corporais", "corporal"],
        "cob_danos_mor": ["morais", "moral"],
        "cob_casco": ["casco", "compreensiva", "colisão"],
        "cob_guincho": ["guincho", "assistência"],
        "cob_reserva": ["reserva", "carro reserva"],
    }
    keywords = search_map.get(field_key, [])
    for i, (name, val) in enumerate(coberturas):
        for kw in keywords:
            if kw in name.lower():
                coberturas[i] = (name, new_value)
                return True
    return False


async def handle_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o novo valor digitado pelo usuário."""
    msg = update.message
    chat_id = msg.chat_id
    new_value = msg.text.strip()

    field = context.user_data.get("editing_field")
    if not field:
        return ConversationHandler.END

    job = active_jobs.get(chat_id)
    if not job:
        await msg.reply_text("⚠️ Nenhum orçamento ativo. Envie um novo PDF.")
        return ConversationHandler.END

    data = job["data"]

    # Atualiza o campo
    if field.startswith("cob_"):
        success = set_cobertura_value(data, field, new_value)
        if not success:
            await msg.reply_text("⚠️ Cobertura não encontrada no orçamento.")
            return ConversationHandler.END
        label = EDITABLE_COBERTURAS.get(field, field)
    else:
        data[field] = new_value
        label = EDITABLE_FIELDS.get(field, field)

    # Regenera PDF
    status = await msg.reply_text("⚙️ Regenerando orçamento...")

    try:
        out_name = build_output_name(data)
        output_path = os.path.join(OUTPUT_DIR, out_name)
        generate_pdf(data, output_path)

        # Atualiza job
        job["output_path"] = output_path
        job["out_name"] = out_name

        await send_pdf_with_edit(msg, context, data, output_path, out_name, job["ai_used"], chat_id)
        await status.delete()

        await msg.reply_text(f"✅ {label} atualizado para: `{new_value}`", parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Erro ao regenerar: {e}", exc_info=True)
        await status.edit_text(f"❌ Erro ao regenerar: `{str(e)}`", parse_mode="Markdown")

    # Limpa estado de edição
    context.user_data.pop("editing_field", None)
    return ConversationHandler.END


async def _route_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Roteia foto: se em sessão /nova, processa como CNH/CRVL; senão, OCR genérico."""
    chat_id = update.message.chat_id
    
    # Verifica se sessão expirou (>2h)
    if chat_id in nova_sessions:
        session = nova_sessions[chat_id]
        created = session.get("created_at", 0)
        if created and (time.time() - created) > 7200:  # 2 horas
            nova_sessions.pop(chat_id, None)
            _save_nova_sessions()
            logger.info(f"Sessão /nova expirada para chat_id={chat_id}")
    
    if chat_id in nova_sessions:
        return await handle_nova_photo(update, context)
    return await handle_photo(update, context)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """OCR genérico de foto (fora do fluxo /nova)."""
    msg = update.message
    photo = msg.photo[-1]

    status = await msg.reply_text("📸 Analisando documento...")

    tmp_path = None
    try:
        file = await context.bot.get_file(photo.file_id)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
        await file.download_to_drive(tmp_path)

        await status.edit_text("🤖 Extraindo dados com IA...")

        data = extract_document_data(tmp_path)
        if not data:
            await status.edit_text(
                "❌ Não consegui ler o documento.\n"
                "Tente tirar uma foto mais nítida, com boa iluminação."
            )
            return

        response_text = format_document_response(data)
        await status.edit_text(response_text, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Erro OCR: {e}", exc_info=True)
        await status.edit_text(f"❌ Erro ao processar: `{str(e)}`", parse_mode="Markdown")
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except:
                pass


async def handle_other(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mensagens que não são PDF nem edição."""
    chat_id = update.message.chat_id
    text = update.message.text or ""
    logger.info(f"[handle_other] chat_id={chat_id} | nova_session={'SIM' if chat_id in nova_sessions else 'NÃO'} | texto='{text[:40]}'")

    # Checa se está em modo de edição
    field = context.user_data.get("editing_field")
    if field:
        return await handle_edit_value(update, context)

    # Checa se está em sessão /gestor (Gastón)
    session = nova_sessions.get(chat_id, {})
    if session.get("gestor_active"):
        return await handle_gestor_message(update, context)

    # Checa se está em sessão /nova — pode ser CEP em texto
    if chat_id in nova_sessions:
        return await handle_nova_text(update, context)

    await update.message.reply_text(
        "📄 Envie um *PDF* de orçamento ou use */nova* para iniciar uma cotação.\n"
        "Use /start para mais informações.",
        parse_mode="Markdown"
    )


# ────────────────────────────────────────────────────────────
#  FLUXO /nova — coleta CNH, CRVL e CEP em qualquer ordem
# ────────────────────────────────────────────────────────────

async def renova(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Renovação de seguro — em desenvolvimento."""
    first_name = update.message.from_user.first_name or "amigo"
    await update.message.reply_text(
        f"🔄 Oi, {first_name}! A função de *renovação de seguros* "
        f"está sendo desenvolvida e em breve estará disponível.\n\n"
        f"⏳ _Estamos trabalhando nisso!_",
        parse_mode="Markdown"
    )


async def gestor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia sessão com o Gastón — Conselheiro de Gestão IA."""
    import gaston_engine
    
    user = update.message.from_user
    user_id = user.id
    first_name = user.first_name or "amigo"
    
    # Verifica whitelist
    if not gaston_engine.is_allowed(user_id):
        await update.message.reply_text(
            f"🔒 Desculpe, {first_name}. O acesso ao Conselheiro de Gestão "
            f"é restrito aos sócios da corretora.",
            parse_mode="Markdown"
        )
        return
    
    # Marca sessão gestor ativa
    chat_id = update.message.chat_id
    if chat_id not in nova_sessions:
        nova_sessions[chat_id] = {}
    nova_sessions[chat_id]["gestor_active"] = True
    _save_nova_sessions()
    
    keyboard = [
        [InlineKeyboardButton("🗑️ Limpar histórico", callback_data="gestor_clear")]
    ]
    
    await update.message.reply_text(
        f"🧠 *Gastón Mattarelli — Conselheiro de Gestão*\n\n"
        f"Oi, {first_name}! Sou o Gastón, seu consultor estratégico.\n\n"
        f"Pode falar comigo sobre:\n"
        f"📊 Análise de desempenho e métricas\n"
        f"📋 Planos de ação e estratégia\n"
        f"💼 Gestão de equipe e processos\n"
        f"🎯 Marketing e geração de leads\n"
        f"🤝 Roleplay de vendas e objeções\n"
        f"💡 Tendências e inovação em seguros\n\n"
        f"_Mande sua mensagem que eu respondo. "
        f"Use qualquer outro comando pra sair._\n\n"
        f"_Nosso histórico fica salvo entre sessões._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ────────────────────────────────────────────────────────────

async def nova(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia sessão de nova cotação — mostra botões de ramo."""
    chat_id = update.message.chat_id
    primeiro_nome = update.message.from_user.first_name or "pessoal"

    await update.message.reply_text(
        f"😊 Oi, {primeiro_nome}! Que tipo de seguro vamos cotar?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚗 Auto", callback_data="ramo_auto"),
             InlineKeyboardButton("🏠 Residencial", callback_data="ramo_resi")],
            [InlineKeyboardButton("🏢 Empresarial", callback_data="ramo_empr"),
             InlineKeyboardButton("➕ Outros", callback_data="ramo_outros")],
        ])
    )


async def handle_ramo_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback: escolha do ramo de seguro."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    
    ramo = query.data.replace("ramo_", "")  # auto, resi, empr, outros
    RAMO_LABELS = {"auto": "🚗 Auto", "resi": "🏠 Residencial", "empr": "🏢 Empresarial", "outros": "➕ Outros"}
    
    nova_sessions[chat_id] = {
        "ramo": ramo, "cnh": None, "cnh_condutor": None, 
        "crvl": None, "cep": None, "endereco": None, "created_at": time.time()
    }
    _save_nova_sessions()
    logger.info(f"[/nova] Sessão iniciada para chat_id={chat_id}, ramo={ramo}")
    
    if ramo == "auto":
        await query.edit_message_text(
            f"*{RAMO_LABELS[ramo]}* — Beleza!\n\n"
            "Me manda os documentos — pode ser na ordem que quiser:\n\n"
            "📸 *CNH* do proprietário\n"
            "📸 *CNH* do condutor (se for diferente)\n"
            "📸 *CRVL* do veículo\n"
            "📍 *CEP* de pernoite — só os números\n\n"
            "Foto de lado, de cabeça pra baixo, PDF... eu me viro! 😄",
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(
            f"*{RAMO_LABELS[ramo]}* — Anotado! 📝\n\n"
            "Esse ramo ainda está em desenvolvimento no bot.\n"
            "Por enquanto, use o Agilizador direto pra essa cotação.\n\n"
            "_Em breve vou suportar todos os ramos!_ 🚀",
            parse_mode="Markdown"
        )


def _calcular_idade(data_nasc_str: str) -> str:
    """Calcula idade a partir de string DD/MM/AAAA."""
    try:
        partes = data_nasc_str.strip().split("/")
        if len(partes) == 3:
            d, m, a = int(partes[0]), int(partes[1]), int(partes[2])
            nascimento = date(a, m, d)
            hoje = date.today()
            idade = relativedelta(hoje, nascimento).years
            return f"{idade} anos"
    except:
        pass
    return ""


def _buscar_cep(cep: str) -> dict | None:
    """Busca endereço pelo CEP via ViaCEP."""
    cep_limpo = re.sub(r"\D", "", cep)
    if len(cep_limpo) != 8:
        return None
    try:
        r = httpx.get(f"https://viacep.com.br/ws/{cep_limpo}/json/", timeout=10)
        data = r.json()
        if "erro" in data:
            return None
        return data
    except:
        return None


def _nova_status(session: dict) -> str:
    """Retorna status atual da sessão."""
    cnh_ok = "✅" if session.get("cnh") else "⏳"
    condutor_ok = "✅" if session.get("cnh_condutor") else "➖"
    crvl_ok = "✅" if session.get("crvl") else "⏳"
    cep_ok = "✅" if session.get("cep") else "⏳"
    status = f"{cnh_ok} CNH Proprietário   {crvl_ok} CRVL   {cep_ok} CEP"
    if session.get("cnh_condutor"):
        status += f"\n{condutor_ok} CNH Condutor"
    return status


def _o_que_falta(session: dict) -> str:
    """Mensagem orientando o que ainda falta enviar."""
    falta = []
    if not session.get("cnh"):
        falta.append("📸 foto ou PDF da *CNH do proprietário*")
    if not session.get("crvl"):
        falta.append("📸 foto ou PDF do *CRVL*")
    if not session.get("cep"):
        falta.append("📍 *CEP* de pernoite — só digita os números aqui no chat")
    if not falta:
        return ""
    extra = "\n\n_💡 Se o condutor for diferente do proprietário, manda a CNH dele também!_"
    return "Ainda preciso:\n" + "\n".join(f"• {f}" for f in falta) + extra


def _nova_completa(session: dict) -> bool:
    return bool(session.get("cnh") and session.get("crvl") and session.get("cep"))


def _montar_resumo(session: dict) -> str:
    """Monta o resumo formatado da cotação."""
    cnh = session.get("cnh", {})
    crvl = session.get("crvl", {})
    end = session.get("endereco", {})
    cep_raw = session.get("cep", "")

    # Veículo
    placa = crvl.get("placa", "N/D")
    modelo = crvl.get("marca_modelo", "N/D")
    cor = crvl.get("cor", "N/D")
    combustivel = crvl.get("combustivel", "N/D")
    chassi = crvl.get("chassi", "N/D")
    ano_fab = crvl.get("ano_fabricacao", "")
    ano_mod = crvl.get("ano_modelo", "")
    ano_str = f" · {ano_fab}/{ano_mod}" if ano_fab and ano_fab != "N/D" else ""

    # Segurado
    nome = cnh.get("nome", crvl.get("proprietario", "N/D"))
    cpf = cnh.get("cpf", crvl.get("cpf_cnpj", "N/D"))
    nasc = cnh.get("data_nascimento", "N/D")
    idade = _calcular_idade(nasc) if nasc != "N/D" else ""
    nasc_str = nasc
    if idade:
        nasc_str += f" · {idade}"

    # Endereço
    if end:
        logradouro = end.get("logradouro", "")
        bairro = end.get("bairro", "")
        cidade = end.get("localidade", "")
        uf = end.get("uf", "")
        cep_fmt = f"{cep_raw[:5]}-{cep_raw[5:]}" if len(re.sub(r'\D','',cep_raw)) == 8 else cep_raw
        end_str = f"{cep_fmt}"
        if logradouro:
            end_str += f" · {logradouro}"
        if bairro:
            end_str += f", {bairro}"
        if cidade:
            end_str += f" · {cidade}/{uf}"
    else:
        end_str = cep_raw

    resumo = (
        f"🚗 *Veículo:* {placa} · {modelo}{ano_str}\n"
        f"    ↳ {cor} · {combustivel}\n"
        f"🔢 *Chassi:* `{chassi}`\n"
        f"\n"
        f"👤 *Segurado:* {nome}\n"
        f"📄 *CPF:* `{cpf}`\n"
        f"🎂 *Nasc.:* {nasc_str}\n"
        f"🌙 *Pernoite:* {end_str}\n"
        f"🔧 *Uso:* Particular\n"
    )
    
    # Condutor (se diferente do proprietário)
    cnh_cond = session.get("cnh_condutor")
    if cnh_cond:
        cond_nome = cnh_cond.get("nome", "N/D")
        cond_cpf = cnh_cond.get("cpf", "N/D")
        cond_nasc = cnh_cond.get("data_nascimento", "N/D")
        cond_idade = _calcular_idade(cond_nasc) if cond_nasc != "N/D" else ""
        cond_nasc_str = cond_nasc
        if cond_idade:
            cond_nasc_str += f" · {cond_idade}"
        resumo += (
            f"\n🚘 *Condutor:* {cond_nome}\n"
            f"📄 *CPF:* `{cond_cpf}`\n"
            f"🎂 *Nasc.:* {cond_nasc_str}\n"
        )
    
    return resumo


async def _processar_doc_nova(file_path: str, chat_id: int, msg, context) -> bool:
    """
    Extrai doc (CNH ou CRVL), salva na sessão.
    Retorna True se processou com sucesso.
    """
    status = await msg.reply_text("🤖 Lendo documento...")
    try:
        data = extract_document_data(file_path)
        if not data:
            await status.edit_text(
                "😅 Não consegui ler esse documento. Tente mandar uma foto mais nítida ou o PDF original."
            )
            return False

        doc_type = data.get("tipo", "").upper()
        session = nova_sessions[chat_id]

        if "CNH" in doc_type:
            nome = data.get("nome", "?")
            cpf = data.get("cpf", "?")
            
            # Se está aguardando CNH do condutor (já confirmou que é diferente)
            if session.get("aguardando_condutor"):
                session["cnh_condutor"] = data
                session.pop("aguardando_condutor", None)
                session["confirmou_condutor"] = True
                _save_nova_sessions()
                await status.edit_text(
                    f"✅ *CNH do motorista lida!*\n🚘 {nome} · {cpf}\n\n"
                    f"{_nova_status(session)}",
                    parse_mode="Markdown"
                )
                # Agora sim monta o resumo
                if _nova_completa(session):
                    await _mostrar_resumo(msg, chat_id)
                return True
            
            # Se já tem uma CNH, é a segunda — perguntar quem é quem
            if session.get("cnh") and session["cnh"].get("nome"):
                nome_anterior = session["cnh"].get("nome", "?")
                # Salva a segunda CNH temporariamente
                session["cnh_2"] = data
                _save_nova_sessions()
                
                keyboard = [
                    [InlineKeyboardButton(f"🚘 {nome_anterior}", callback_data="segurado_1")],
                    [InlineKeyboardButton(f"🚘 {nome}", callback_data="segurado_2")],
                ]
                await status.edit_text(
                    f"📋 Recebi *duas CNHs*!\n\n"
                    f"1️⃣ {nome_anterior}\n"
                    f"2️⃣ {nome}\n\n"
                    f"Quem é o *motorista principal*?\n"
                    f"_(o outro será o proprietário/segurado)_",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return True
            else:
                session["cnh"] = data
                _save_nova_sessions()
                faltam = _o_que_falta(session)
                await status.edit_text(
                    f"✅ *CNH lida!*\n👤 {nome} · {cpf}\n\n"
                    f"{_nova_status(session)}\n\n{faltam}",
                    parse_mode="Markdown"
                )
        elif "CRVL" in doc_type or "CRV" in doc_type:
            session["crvl"] = data
            _save_nova_sessions()
            placa = data.get("placa", "?")
            modelo = data.get("marca_modelo", "?")
            faltam = _o_que_falta(session)
            await status.edit_text(
                f"✅ *CRVL lido!*\n🚗 {placa} · {modelo}\n\n"
                f"{_nova_status(session)}\n\n{faltam}",
                parse_mode="Markdown"
            )
        else:
            await status.edit_text(
                f"🤔 Recebi um documento, mas não identifiquei como CNH ou CRVL.\n"
                f"Tipo detectado: _{data.get('tipo', '?')}_\n\n"
                f"Pode tentar de novo com foto melhor?",
                parse_mode="Markdown"
            )
            return False

        # Se só falta o CEP, pede explicitamente em mensagem separada
        if session.get("cnh") and session.get("crvl") and not session.get("cep"):
            await msg.reply_text(
                "🌙 Ótimo! Agora só falta o *CEP de pernoite* — "
                "onde o carro fica guardado à noite.\n"
                "Digita os 8 números aqui: _(ex: 95084270)_",
                parse_mode="Markdown"
            )

        return True

    except Exception as e:
        logger.error(f"Erro ao processar doc /nova: {e}", exc_info=True)
        try:
            await status.edit_text("❌ Erro ao processar o documento. Tente novamente.")
        except:
            await msg.reply_text("❌ Erro ao processar o documento. Tente novamente.")
        return False


async def handle_nova_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foto recebida durante sessão /nova. Suporta álbuns (media_group)."""
    import time
    msg = update.message
    chat_id = msg.chat_id

    # Checar legenda da foto — pode conter CEP
    caption = msg.caption or ""
    if caption:
        apenas_digitos = re.sub(r"\D", "", caption)
        cep_caption = None
        if len(apenas_digitos) == 8:
            cep_caption = apenas_digitos
        else:
            match = re.search(r"\b(\d{5})[-.\s]?(\d{3})\b", caption)
            if match:
                cep_caption = match.group(1) + match.group(2)

        if cep_caption and not nova_sessions[chat_id].get("cep"):
            # Extrai CEP da legenda automaticamente
            endereco = _buscar_cep(cep_caption)
            nova_sessions[chat_id]["cep"] = cep_caption
            nova_sessions[chat_id]["endereco"] = endereco or {}
            _save_nova_sessions()
            logger.info(f"[nova_photo] CEP extraído da legenda: {cep_caption}")

    # Controle de media_group — aguarda um pouco para processar o álbum todo
    media_group_id = msg.media_group_id
    if media_group_id:
        now = time.time()
        # Se já vimos esse grupo há menos de 3s, aguarda (o outro update já está processando)
        last_seen = _media_groups_seen.get(media_group_id, 0)
        _media_groups_seen[media_group_id] = now
        if now - last_seen < 3.0 and last_seen > 0:
            # Não é o primeiro do grupo — processa normalmente mas sem delay
            pass
        elif last_seen == 0:
            # Primeira foto do álbum — pequena espera pra receber as demais
            await asyncio.sleep(1.5)

    photo = msg.photo[-1]
    tmp_path = None
    try:
        file = await context.bot.get_file(photo.file_id)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
        await file.download_to_drive(tmp_path)

        ok = await _processar_doc_nova(tmp_path, chat_id, msg, context)
        if ok and _nova_completa(nova_sessions[chat_id]):
            await _finalizar_nova(msg, chat_id)

    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except:
                pass


async def handle_nova_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """PDF recebido durante sessão /nova."""
    msg = update.message
    chat_id = msg.chat_id
    doc = msg.document

    # Se é PDF de orçamento (fora de sessão nova), deixa o handler normal processar
    if chat_id not in nova_sessions:
        return await handle_pdf(update, context)

    # Checar legenda do PDF — pode conter CEP
    caption = msg.caption or ""
    if caption and not nova_sessions[chat_id].get("cep"):
        apenas_digitos = re.sub(r"\D", "", caption)
        cep_caption = None
        if len(apenas_digitos) == 8:
            cep_caption = apenas_digitos
        else:
            match = re.search(r"\b(\d{5})[-.\s]?(\d{3})\b", caption)
            if match:
                cep_caption = match.group(1) + match.group(2)
        if cep_caption:
            endereco = _buscar_cep(cep_caption)
            nova_sessions[chat_id]["cep"] = cep_caption
            nova_sessions[chat_id]["endereco"] = endereco or {}
            _save_nova_sessions()

    tmp_path = None
    try:
        file = await context.bot.get_file(doc.file_id)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name
        await file.download_to_drive(tmp_path)

        ok = await _processar_doc_nova(tmp_path, chat_id, msg, context)
        if ok and _nova_completa(nova_sessions[chat_id]):
            await _finalizar_nova(msg, chat_id)

    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except:
                pass


async def handle_nova_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Texto recebido durante sessão /nova — esperamos CEP."""
    msg = update.message
    chat_id = msg.chat_id
    text = msg.text.strip()

    # Extrai CEP: tenta qualquer sequência de 8 dígitos no texto
    # Aceita: 95084270 / 95084-270 / 95.084-270 / "cep 95084270" / etc.
    apenas_digitos = re.sub(r"\D", "", text)
    cep = None

    # Caso 1: o texto inteiro (sem não-dígitos) tem exatamente 8 dígitos
    if len(apenas_digitos) == 8:
        cep = apenas_digitos

    # Caso 2: algum trecho do texto tem padrão de CEP
    if not cep:
        match = re.search(r"\b(\d{5})[-.\s]?(\d{3})\b", text)
        if match:
            cep = match.group(1) + match.group(2)

    if not cep:
        await msg.reply_text(
            "🌙 Manda o *CEP de pernoite* — onde o carro fica guardado à noite.\n"
            "Pode mandar só os 8 números: _(ex: 95084270)_",
            parse_mode="Markdown"
        )
        return
    status = await msg.reply_text("🔍 Buscando endereço...")

    endereco = _buscar_cep(cep)
    session = nova_sessions[chat_id]
    session["cep"] = cep
    session["endereco"] = endereco or {}
    _save_nova_sessions()
    logger.info(f"[nova_text] CEP={cep} salvo para chat_id={chat_id}")

    faltam = _o_que_falta(session)
    if endereco:
        cidade = endereco.get("localidade", "?")
        uf = endereco.get("uf", "?")
        logradouro = endereco.get("logradouro", "")
        end_display = f"{logradouro}, {cidade}/{uf}" if logradouro else f"{cidade}/{uf}"
        await status.edit_text(
            f"✅ *CEP localizado!*\n📍 {end_display}\n\n{_nova_status(session)}"
            + (f"\n\n{faltam}" if faltam else ""),
            parse_mode="Markdown"
        )
    else:
        await status.edit_text(
            f"✅ *CEP registrado:* {cep[:5]}-{cep[5:]}\n_(endereço não encontrado)_\n\n{_nova_status(session)}"
            + (f"\n\n{faltam}" if faltam else ""),
            parse_mode="Markdown"
        )

    if _nova_completa(session):
        await _finalizar_nova(msg, chat_id)


async def _finalizar_nova(msg, chat_id: int):
    """Docs obrigatórios completos — mostra botão Pronto pra usuário decidir."""
    session = nova_sessions[chat_id]
    
    # Se já confirmou condutor, vai direto pro resumo
    if session.get("confirmou_condutor"):
        await _mostrar_resumo(msg, chat_id)
        return
    
    # Se tá esperando escolha de motorista (2 CNHs), não interrompe
    if session.get("cnh_2"):
        return
    
    # Se já mostrou o "Pronto?", não repete
    if session.get("perguntou_pronto"):
        return
    
    session["perguntou_pronto"] = True
    _save_nova_sessions()
    
    await msg.reply_text(
        f"✅ *CNH + CRVL + CEP recebidos!*\n\n"
        f"{_nova_status(session)}\n\n"
        f"Vai mandar mais algum documento?\n"
        f"_(ex: CNH do motorista, se for diferente do proprietário)_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Pronto, pode montar!", callback_data="nova_pronto")],
            [InlineKeyboardButton("📸 Vou mandar mais docs", callback_data="nova_mais_docs")],
        ])
    )


async def handle_nova_pronto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback: usuário disse que terminou de mandar docs."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    
    session = nova_sessions.get(chat_id)
    if not session:
        await query.message.reply_text("⚠️ Sessão expirada. Use /nova para começar de novo.")
        return
    
    if query.data == "nova_pronto":
        session["confirmou_condutor"] = True
        _save_nova_sessions()
        await query.edit_message_text("✅ Montando resumo...")
        await _mostrar_resumo(query.message, chat_id)
    else:
        # nova_mais_docs — limpa flag e aguarda
        session.pop("perguntou_pronto", None)
        _save_nova_sessions()
        await query.edit_message_text(
            "👍 Sem pressa! Manda o que falta que eu vou recebendo.\n\n"
            f"{_nova_status(session)}",
            parse_mode="Markdown"
        )


async def _mostrar_resumo(msg, chat_id: int):
    """Monta e envia o resumo com botão de cotação."""
    session = nova_sessions[chat_id]
    resumo = _montar_resumo(session)

    await msg.reply_text(
        f"🎉 *Dados completos! Aqui está o resumo:*\n\n{resumo}\n"
        f"_Confere aí. Se algo estiver errado, me manda o documento correto._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🚀 Calcular no Agilizador", callback_data="nova_calcular")
        ]])
    )


async def handle_gestor_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa mensagem de texto na sessão do Gastón."""
    import gaston_engine
    
    user = update.message.from_user
    user_id = user.id
    user_name = user.full_name or "Usuário"
    text = update.message.text or ""
    
    if not text.strip():
        return
    
    # Mostra "digitando..."
    await update.message.chat.send_action("typing")
    
    try:
        resposta = await gaston_engine.chat(user_id, user_name, text)
        
        # Telegram tem limite de 4096 chars por mensagem
        if len(resposta) > 4000:
            # Divide em partes
            partes = []
            while resposta:
                if len(resposta) <= 4000:
                    partes.append(resposta)
                    break
                # Corta no último \n antes de 4000
                corte = resposta[:4000].rfind("\n")
                if corte < 100:
                    corte = 4000
                partes.append(resposta[:corte])
                resposta = resposta[corte:]
            
            for parte in partes:
                try:
                    await update.message.reply_text(parte, parse_mode="Markdown")
                except Exception:
                    await update.message.reply_text(parte)
        else:
            try:
                await update.message.reply_text(resposta, parse_mode="Markdown")
            except Exception:
                await update.message.reply_text(resposta)
                
    except Exception as e:
        logger.error(f"Erro Gastón: {e}", exc_info=True)
        await update.message.reply_text(
            "⚠️ Tive um problema ao processar. Tenta de novo em instantes."
        )


async def handle_gestor_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Limpa histórico do Gastón."""
    import gaston_engine
    
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    gaston_engine.clear_history(user_id)
    await query.message.reply_text("🗑️ Histórico limpo! Pode começar uma conversa nova.")


async def handle_segurado_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback quando o usuário escolhe quem é o segurado (com duas CNHs)."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    session = nova_sessions.get(chat_id)
    if not session or not session.get("cnh_2"):
        await query.message.reply_text("⚠️ Sessão expirada. Use /nova para começar de novo.")
        return

    choice = query.data  # "segurado_1" ou "segurado_2"
    cnh_1 = session.get("cnh", {})
    cnh_2 = session.get("cnh_2", {})

    if choice == "segurado_1":
        # CNH 1 é o motorista/condutor, CNH 2 é o proprietário/segurado
        session["cnh"] = cnh_2  # proprietário
        session["cnh_condutor"] = cnh_1  # motorista
        segurado_nome = cnh_2.get("nome", "?")
        condutor_nome = cnh_1.get("nome", "?")
    else:
        # CNH 2 é o motorista/condutor, CNH 1 é o proprietário/segurado
        session["cnh"] = cnh_1  # proprietário
        session["cnh_condutor"] = cnh_2  # motorista
        segurado_nome = cnh_1.get("nome", "?")
        condutor_nome = cnh_2.get("nome", "?")

    # Remove a CNH temporária e marca condutor como confirmado
    session.pop("cnh_2", None)
    session["confirmou_condutor"] = True
    _save_nova_sessions()

    faltam = _o_que_falta(session)
    await query.edit_message_text(
        f"✅ Definido!\n\n"
        f"👤 *Segurado:* {segurado_nome}\n"
        f"🚘 *Condutor:* {condutor_nome}\n\n"
        f"{_nova_status(session)}\n\n{faltam}",
        parse_mode="Markdown"
    )
    
    # Se já tem tudo, vai direto pro resumo
    if _nova_completa(session):
        await _mostrar_resumo(query.message, chat_id)


async def handle_escolher_seguradora(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback: Eduardo escolheu uma seguradora → baixa PDF e converte."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    
    # Extrai nome da seguradora do callback
    seguradora = query.data.replace("escolher_", "").replace("_", " ")
    
    status_msg = await query.message.reply_text(
        f"📄 Baixando PDF da *{seguradora}*...",
        parse_mode="Markdown"
    )
    
    async def on_progress(msg):
        try:
            await status_msg.edit_text(msg, parse_mode="Markdown")
        except:
            pass
    
    # Busca prêmio esperado pra selecionar o plano correto
    from agilizador import _browser_sessions
    bs = _browser_sessions.get(chat_id, {})
    premio_map = bs.get('_premio_map', {})
    premio_esperado = premio_map.get(seguradora.lower())
    
    # Busca dados da tela pra sobrescrever no PDF
    resultado_tela = None
    for r in bs.get('resultados', []):
        if r.get('seguradora', '').lower() == seguradora.lower():
            resultado_tela = r
            break
    
    resultado = await baixar_pdf_cotacao(chat_id, seguradora, on_progress=on_progress, premio_esperado=premio_esperado, resultado_tela=resultado_tela)
    
    if resultado.get("sucesso") and resultado.get("pdf_path"):
        pdf_path = resultado["pdf_path"]
        out_name = resultado.get("out_name", f"Sierra_{seguradora}.pdf")
        
        # Salva PDF permanente + registra no banco
        try:
            import shutil
            session = nova_sessions.get(chat_id, {})
            cotacao_id = session.get("cotacao_id")
            if cotacao_id:
                perm_dir = f"/root/sierra/cotacao_pdfs/{cotacao_id}"
                os.makedirs(perm_dir, exist_ok=True)
                perm_path = f"{perm_dir}/{out_name}"
                shutil.copy2(pdf_path, perm_path)
                pool = await database.get_pool()
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE cotacao_resultados SET pdf_path=$1 WHERE cotacao_id=$2 AND LOWER(seguradora)=LOWER($3)",
                        perm_path, cotacao_id, seguradora)
                logger.info(f"PDF salvo permanente: {perm_path}")
        except Exception as e:
            logger.error(f"Erro salvando PDF permanente: {e}")
        data = resultado.get("data", {})
        ai_used = resultado.get("ai_used", False)
        ai_tag = " 🤖" if ai_used else ""
        
        segurado_display = data.get("segurado", "Cliente")
        veiculo = data.get("veiculo", "")
        insurer_name = data.get("insurer", seguradora)
        
        caption = (
            f"✅ *Orçamento gerado!*{ai_tag}\n\n"
            f"👤 {segurado_display}\n"
            f"🚗 {veiculo}\n"
            f"🏢 {insurer_name}"
        )
        
        await status_msg.edit_text(f"✅ PDF da *{seguradora}* convertido pro layout Sierra!")
        
        with open(pdf_path, "rb") as f:
            await query.message.reply_document(
                document=f,
                filename=out_name,
                caption=caption,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✏️ Editar", callback_data="edit_menu")]
                ])
            )
        
        # Notifica Fafá
        try:
            user = query.from_user
            user_name = user.full_name or "Desconhecido"
            notify_text = (
                f"📄 *PDF gerado via Agilizador*\n"
                f"👤 {user_name}\n"
                f"🏢 {insurer_name}\n"
                f"🚗 {veiculo}\n"
                f"💰 {data.get('premio_total', '?')}"
            )
            await context.bot.send_message(chat_id=6553672222, text=notify_text, parse_mode="Markdown")
        except:
            pass
    else:
        await status_msg.edit_text(resultado.get("msg", "❌ Erro desconhecido"))


async def handle_iniciar_nova(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback do botão 'Nova Cotação' — mostra botões de ramo."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🚗 Que tipo de seguro vamos cotar?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚗 Auto", callback_data="ramo_auto"),
             InlineKeyboardButton("🏠 Residencial", callback_data="ramo_resi")],
            [InlineKeyboardButton("🏢 Empresarial", callback_data="ramo_empr"),
             InlineKeyboardButton("➕ Outros", callback_data="ramo_outros")],
        ])
    )


async def handle_nova_calcular(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dispara a cotação no Agilizador com os dados da sessão /nova."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    session = nova_sessions.get(chat_id)
    if not session:
        await query.message.reply_text("⚠️ Sessão expirada. Use /nova para começar de novo.")
        return

    # Remove botão enquanto processa
    await query.edit_message_reply_markup(reply_markup=None)

    status_msg = await query.message.reply_text("⏳ Iniciando cotação no Agilizador...")

    async def on_progress(text: str):
        try:
            await status_msg.edit_text(text)
        except:
            pass

    resultado = await calcular_cotacao(session, on_progress=on_progress, chat_id=chat_id)

    # Dados pra notificação
    user = query.from_user
    user_name = user.full_name or "Desconhecido"
    user_username = f"@{user.username}" if user.username else f"ID:{user.id}"
    crvl = session.get("crvl", {})
    veiculo = crvl.get("marca_modelo", "N/D")
    placa = crvl.get("placa", "N/D")
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    if resultado["sucesso"]:
        # Envia a mensagem formatada com os resultados
        msg_text = resultado.get("msg", "✅ Cotação calculada!")
        await query.message.reply_text(msg_text, parse_mode="Markdown")
        
        # Envia screenshot
        screenshot = resultado.get("screenshot")
        if screenshot:
            import io
            await query.message.reply_photo(
                photo=io.BytesIO(screenshot),
                caption="_Screenshot da tela no Agilizador_",
                parse_mode="Markdown"
            )
        await status_msg.delete()
        
        # Botões "Escolher" para cada seguradora com valor
        resultados_list = resultado.get("resultados", [])
        com_valor = [r for r in resultados_list if r.get("premio")]
        if com_valor:
            # Monta botões (2 por linha)
            botoes = []
            linha = []
            # Salva mapa de prêmios pra usar na hora de baixar o PDF correto
            _premio_map = {}
            for r in com_valor:
                seg = r.get("seguradora", "?")
                premio = r.get("premio", "")
                # Salva prêmio float
                try:
                    pf = float(premio.replace("R$", "").replace(".", "").replace(",", ".").strip())
                    _premio_map[seg.lower()] = pf
                except:
                    pass
                # Limita nome pra caber no botão
                seg_short = seg[:15] if len(seg) > 15 else seg
                premio_short = premio.replace("R$ ", "").strip()
                callback = f"escolher_{seg.replace(' ', '_')[:30]}"
                linha.append(InlineKeyboardButton(
                    f"📄 {seg_short} ({premio_short})", 
                    callback_data=callback
                ))
                if len(linha) == 2:
                    botoes.append(linha)
                    linha = []
            if linha:
                botoes.append(linha)
            
            # Salva mapa de prêmios na sessão pra baixar PDF correto
            from agilizador import _browser_sessions
            bs = _browser_sessions.get(chat_id, {})
            if bs:
                bs['_premio_map'] = _premio_map
            
            await query.message.reply_text(
                "👆 *Escolha a seguradora* pra gerar o PDF no layout Sierra:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(botoes)
            )

        # Salva no banco PostgreSQL
        try:
            import database
            cnh = session.get("cnh", {})
            
            # Upsert cliente
            nasc_date = None
            nasc_str = cnh.get("nascimento", "")
            if nasc_str:
                try:
                    parts = nasc_str.split("/")
                    if len(parts) == 3:
                        from datetime import date as dt_date
                        nasc_date = dt_date(int(parts[2]), int(parts[1]), int(parts[0]))
                except:
                    pass
            
            cliente_id = await database.upsert_cliente(
                1, cnh.get("nome", ""), cnh.get("cpf", ""),
                nascimento=nasc_date
            )
            
            # Upsert veículo
            veiculo_id = await database.upsert_veiculo(
                cliente_id, crvl.get("placa", ""),
                chassi=crvl.get("chassi"),
                marca_modelo=crvl.get("modelo") or crvl.get("marca_modelo"),
                ano_fabricacao=crvl.get("ano_fabricacao"),
                ano_modelo=crvl.get("ano_modelo"),
                cor=crvl.get("cor"),
                combustivel=crvl.get("combustivel"),
                cep_pernoite=session.get("cep_pernoite"),
            )
            
            # Busca usuario_id pelo telegram
            db_user = await database.get_usuario_by_telegram(user.id)
            usuario_id = db_user["id"] if db_user else 1
            
            # Insere cotação
            cotacao_id = await database.inserir_cotacao(
                1, usuario_id, cliente_id, veiculo_id,
                "nova", cnh, crvl, session.get("cep_pernoite", ""),
                condutor_data=session.get("cnh_condutor")
            )
            
            # Insere resultados
            resultados_list = resultado.get("resultados", [])
            if resultados_list:
                await database.inserir_resultados(cotacao_id, resultados_list)
            
            logger.info(f"💾 Cotação #{cotacao_id} salva no banco ({len(resultados_list)} resultados)")
        except Exception as db_err:
            logger.error(f"Erro ao salvar cotação no banco: {db_err}")

        # Notifica admin
        qtd_resultados = len(resultado.get("resultados", []))
        com_valor = len([r for r in resultado.get("resultados", []) if r.get("premio")])
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"🚗 *Nova Cotação — /nova*\n\n"
                    f"👤 {user_name} ({user_username})\n"
                    f"🚘 {veiculo}\n"
                    f"🔢 Placa: `{placa}`\n"
                    f"✅ {com_valor} cotações com valor (de {qtd_resultados} total)\n"
                    f"🕐 {now}"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Erro ao notificar admin /nova: {e}")
        
        # NÃO limpa sessão aqui — usuário ainda pode clicar nos botões pra gerar PDFs
        # Sessão será limpa quando iniciar nova cotação (/nova ou botão)
        pass
    else:
        screenshot = resultado.get("screenshot")
        if screenshot:
            import io
            await query.message.reply_photo(
                photo=io.BytesIO(screenshot),
                caption=f"⚠️ {resultado['msg']}\n\nCaptura da tela no momento do erro.",
                parse_mode="Markdown"
            )
        else:
            await status_msg.edit_text(resultado["msg"])

        # Notifica admin do erro
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"🚗 *Nova Cotação — /nova*\n\n"
                    f"👤 {user_name} ({user_username})\n"
                    f"🚘 {veiculo}\n"
                    f"🔢 Placa: `{placa}`\n"
                    f"❌ {resultado['msg'][:100]}\n"
                    f"🕐 {now}"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Erro ao notificar admin /nova: {e}")


def main():
    if not BOT_TOKEN:
        print("❌ SIERRA_BOT_TOKEN não configurado!")
        sys.exit(1)

    print("🚀 Sierra Bot iniciando...")
    from telegram.request import HTTPXRequest
    request = HTTPXRequest(connect_timeout=20, read_timeout=30, write_timeout=30)

    # Registra menu de comandos visível ao digitar "/"
    async def post_init(application):
        await application.bot.set_my_commands([
            BotCommand("nova",      "🚗 Nova cotação — CNH + CRVL + CEP → Agilizador"),
            BotCommand("renova",    "🔄 Renovação de seguro"),
            BotCommand("gestor",    "🧠 Conselheiro de Gestão IA"),
            BotCommand("converter", "📄 Converter PDF de seguradora → layout Sierra"),
            BotCommand("agente",   "🤖 Atendimento inteligente (Sofia)"),
            BotCommand("start",     "ℹ️ Apresentação e ajuda"),
        ])

    app = Application.builder().token(BOT_TOKEN).request(request).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("nova", nova))
    app.add_handler(CommandHandler("renova", renova))
    app.add_handler(CommandHandler("gestor", gestor))
    app.add_handler(CommandHandler("converter", converter))

    # PDFs: em sessão /nova processa como doc de identidade; fora, como orçamento
    app.add_handler(MessageHandler(filters.Document.PDF, handle_nova_pdf))

    # Fotos: em sessão /nova extrai CNH/CRVL; fora, OCR genérico
    app.add_handler(MessageHandler(filters.PHOTO, _route_photo))

    app.add_handler(CallbackQueryHandler(handle_escolher_seguradora, pattern="^escolher_"))
    app.add_handler(CallbackQueryHandler(handle_ramo_choice, pattern="^ramo_(auto|resi|empr|outros)$"))
    app.add_handler(CallbackQueryHandler(handle_nova_calcular, pattern="^nova_calcular$"))
    app.add_handler(CallbackQueryHandler(handle_iniciar_nova, pattern="^iniciar_nova$"))
    app.add_handler(CallbackQueryHandler(handle_segurado_choice, pattern="^segurado_[12]$"))
    app.add_handler(CallbackQueryHandler(handle_nova_pronto, pattern="^nova_(pronto|mais_docs)$"))
    app.add_handler(CallbackQueryHandler(handle_gestor_clear, pattern="^gestor_clear$"))

    # 🤖 Agente Sofia — callback dos botões (ANTES do catch-all handle_edit_callback)
    try:
        from agent.bot_integration import sofia_callback
        app.add_handler(CallbackQueryHandler(sofia_callback, pattern="^sofia_"))
    except Exception as e:
        print(f"⚠️ Sofia callbacks não registrados: {e}")

    app.add_handler(CallbackQueryHandler(handle_edit_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_other))

    # 🤖 Agente Sofia — handlers em grupo 5 (intercepta quando /agente ativo)
    try:
        from agent.bot_integration import register_agent_handlers
        register_agent_handlers(app)
        print("🤖 Agente Sofia registrado!")
    except Exception as e:
        print(f"⚠️ Agente Sofia não carregado: {e}")

    print("✅ Bot online! Aguardando mensagens...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
