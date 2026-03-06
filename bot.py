"""
Sierra Automação - Bot Telegram
Recebe PDFs de seguradoras e gera orçamentos no layout Sierra.
Com edição inline de campos.
"""

import os
import sys
import logging
import tempfile
from datetime import datetime
import re
import json

# Garante que o working directory é o diretório do bot
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ConversationHandler,
    filters, ContextTypes
)

from extractors import ExtractorFactory
from extractors.ai_extractor import AIExtractor
from generator_sierra_v7_alt import SierraPDFGeneratorV7 as SierraPDFGenerator
from ocr_docs import extract_document_data

# --- Config ---
BOT_TOKEN = os.environ.get("SIERRA_BOT_TOKEN", "")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "orcamentos")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ID do Fafá — recebe notificações de uso
ADMIN_ID = 6553672222

# Armazena dados extraídos por chat_id pra permitir edição
# {chat_id: {"data": {...}, "output_path": "...", "out_name": "...", "ai_used": bool}}
active_jobs = {}

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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Olá! Sou o assistente da *Sierra Seguros*.\n\n"
        "📄 Me envie o PDF de orçamento de uma seguradora e eu gero automaticamente "
        "o documento no padrão Sierra.\n\n"
        "✏️ Depois de gerar, você pode *editar* qualquer campo!\n\n"
        "_Seguradoras suportadas: Alfa, Aliro, Allianz, Azul, Bradesco, Darwin, "
        "Ezze, HDI, Itaú, Mapfre, Mitsui, Porto, Suhai, Suíça, Tokio, Yelum, Zurich "
        "+ qualquer outra via IA_",
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


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa fotos de documentos (CNH, CRVL)."""
    msg = update.message
    photo = msg.photo[-1]  # Maior resolução

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

        from ocr_docs import format_document_response
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
    # Checa se está em modo de edição
    field = context.user_data.get("editing_field")
    if field:
        return await handle_edit_value(update, context)
    
    await update.message.reply_text(
        "📄 Envie um *PDF* de orçamento ou uma *foto* de CNH/CRVL.\n"
        "Use /start para mais informações.",
        parse_mode="Markdown"
    )


def main():
    if not BOT_TOKEN:
        print("❌ SIERRA_BOT_TOKEN não configurado!")
        sys.exit(1)

    print("🚀 Sierra Bot iniciando...")
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_edit_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_other))

    print("✅ Bot online! Aguardando mensagens...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
