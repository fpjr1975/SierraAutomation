"""
bot_integration.py — Integra o agente Sofia ao bot Telegram existente.

Uso: import agent.bot_integration no bot.py e chame register_agent_handlers(app)
"""

import os
import sys
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ApplicationHandlerStop
)

_SIERRA_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SIERRA_ROOT not in sys.path:
    sys.path.insert(0, _SIERRA_ROOT)

from agent.agent_engine import (
    get_or_create_agente, remover_agente,
    carregar_historico_texto, _get_db_conn
)

logger = logging.getLogger(__name__)

_agente_ativo = set()

EDUARDO_CHAT_ID = 2104676074


async def _notificar_eduardo_handoff(bot, chat_id: int, cliente_nome: str,
                                      motivo: str, historico: str):
    """
    Envia notificação de handoff ao Eduardo com contexto completo.
    Chamado quando Sofia identifica que precisa de atendimento humano.
    """
    nome_fmt = cliente_nome or f"chat {chat_id}"
    hist_trunc = historico[:1500] if len(historico) > 1500 else historico

    msg = (
        f"🤝 *Sofia — Handoff para você!*\n"
        f"👤 *Cliente:* {nome_fmt}\n"
        f"💬 *Chat ID:* `{chat_id}`\n"
        f"📌 *Motivo:* {motivo}\n\n"
        f"*📋 Contexto da conversa:*\n"
        f"```\n{hist_trunc}\n```\n\n"
        f"_O cliente está aguardando seu contato!_"
    )

    try:
        await bot.send_message(
            chat_id=EDUARDO_CHAT_ID,
            text=msg,
            parse_mode="Markdown"
        )
        logger.info(f"[Sofia] Handoff enviado ao Eduardo para chat_id={chat_id}")
    except Exception as e:
        logger.error(f"[Sofia] Erro ao notificar Eduardo no handoff: {e}")
        # Fallback sem Markdown
        try:
            await bot.send_message(
                chat_id=EDUARDO_CHAT_ID,
                text=msg.replace("*", "").replace("_", "").replace("`", "")
            )
        except Exception:
            pass


async def cmd_agente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ativa o modo agente Sofia para o chat."""
    chat_id = update.effective_chat.id
    _agente_ativo.add(chat_id)

    get_or_create_agente(chat_id, bot=context.bot)

    await update.message.reply_text(
        "👋 Oi! Eu sou a *Sofia*, atendente virtual da Sierra Seguros!\n\n"
        "Posso te ajudar com:\n"
        "🚗 Cotação de seguro\n"
        "🔄 Renovação\n"
        "📋 Segunda via de apólice/boleto\n"
        "❓ Dúvidas sobre coberturas\n"
        "🆘 Sinistro\n\n"
        "Me conta como posso te ajudar! 😊\n\n"
        "_Para sair do modo agente, digite /sair_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚗 Cotar seguro", callback_data="sofia_cotar")],
            [InlineKeyboardButton("🔄 Renovar", callback_data="sofia_renovar")],
            [InlineKeyboardButton("📋 Documentos", callback_data="sofia_docs")],
        ])
    )


async def cmd_sair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Desativa o modo agente."""
    chat_id = update.effective_chat.id
    if chat_id in _agente_ativo:
        _agente_ativo.discard(chat_id)
        remover_agente(chat_id)
        await update.message.reply_text(
            "👋 Valeu! Se precisar, é só digitar /agente novamente.\n"
            "Voltando ao modo normal do bot."
        )
    else:
        await update.message.reply_text("Você não está no modo agente. Use /agente pra ativar.")


async def sofia_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lida com callbacks dos botões da Sofia."""
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    data = query.data

    if chat_id not in _agente_ativo:
        _agente_ativo.add(chat_id)

    mensagens = {
        "sofia_cotar": "Quero cotar seguro",
        "sofia_renovar": "Quero renovar meu seguro",
        "sofia_docs": "Preciso de um documento",
    }

    texto = mensagens.get(data, "Olá")
    agente = get_or_create_agente(chat_id, bot=context.bot)

    await query.message.reply_text("⏳ Processando...")

    try:
        resposta = await agente.processar_mensagem(texto)
        if resposta:
            for i in range(0, len(resposta), 4000):
                chunk = resposta[i:i+4000]
                await query.message.reply_text(chunk, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Erro Sofia callback: {e}")
        await query.message.reply_text("⚠️ Desculpa, tive um probleminha. Tenta de novo?")


def _detectar_handoff_na_resposta(resposta: str) -> bool:
    """
    Detecta se a resposta da Sofia indica que fez um handoff.
    Verifica palavras-chave típicas de transição para humano.
    """
    keywords = [
        "vou passar pro eduardo",
        "vou chamar o eduardo",
        "passando pro eduardo",
        "eduardo vai te atender",
        "nosso especialista",
        "vou transferir",
        "corretor vai entrar em contato",
    ]
    resposta_lower = resposta.lower()
    return any(kw in resposta_lower for kw in keywords)


async def _executar_handoff_bot(
    bot, chat_id: int, agente, motivo: str = "Handoff solicitado"
):
    """
    Executa o processo de handoff a partir do bot:
    1. Busca histórico e contexto
    2. Notifica Eduardo com contexto completo
    """
    try:
        # Busca histórico em texto para o Eduardo
        historico = carregar_historico_texto(agente.session_id, limit=10)
        cliente_nome = agente.cliente_nome

        # Busca mais contexto do DB se disponível
        contexto_extra = ""
        if agente.contexto:
            ctx = agente.contexto
            partes = []
            if ctx.get("cnh"):
                partes.append(f"CNH: {ctx['cnh'].get('nome', '')} / CPF: {ctx['cnh'].get('cpf', '')}")
            if ctx.get("crvl"):
                partes.append(f"Veículo: {ctx['crvl'].get('marca_modelo', '')} {ctx['crvl'].get('placa', '')}")
            if ctx.get("cep"):
                partes.append(f"CEP: {ctx['cep']}")
            if ctx.get("intent_atual"):
                partes.append(f"Intenção: {ctx['intent_atual']}")
            if partes:
                contexto_extra = "\n📊 *Dados coletados:* " + " | ".join(partes)

        msg = (
            f"🤝 *Sofia — Handoff para você!*\n"
            f"👤 *Cliente:* {cliente_nome or f'chat {chat_id}'}\n"
            f"💬 *Chat ID:* `{chat_id}`\n"
            f"📌 *Motivo:* {motivo}"
            f"{contexto_extra}\n\n"
            f"*📋 Contexto da conversa:*\n"
            f"```\n{historico[:1200]}\n```\n\n"
            f"_O cliente aguarda seu contato!_"
        )

        await bot.send_message(
            chat_id=EDUARDO_CHAT_ID,
            text=msg,
            parse_mode="Markdown"
        )
        logger.info(f"[Sofia] Handoff executado: chat_id={chat_id}, motivo={motivo}")
    except Exception as e:
        logger.error(f"[Sofia] Erro no handoff para Eduardo: {e}")
        try:
            await bot.send_message(
                chat_id=EDUARDO_CHAT_ID,
                text=f"⚠️ Sofia solicitou handoff\nChat: {chat_id}\nMotivo: {motivo}\nErro no contexto: {e}"
            )
        except Exception:
            pass


async def sofia_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa mensagens de texto quando agente está ativo."""
    chat_id = update.effective_chat.id

    if chat_id not in _agente_ativo:
        try:
            conn = _get_db_conn()
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM agent_sessions WHERE chat_id=%s AND estado='ativo' ORDER BY id DESC LIMIT 1",
                (chat_id,)
            )
            row = cur.fetchone()
            conn.close()
            if row:
                _agente_ativo.add(chat_id)
                logger.info(f"[Sofia] Restaurou sessão ativa do DB para chat_id={chat_id}")
            else:
                return
        except Exception as e:
            logger.warning(f"[Sofia] Erro ao checar DB: {e}")
            return

    texto = update.message.text
    if not texto:
        return

    if texto.startswith('/'):
        return

    agente = get_or_create_agente(chat_id, bot=context.bot)

    await context.bot.send_chat_action(chat_id, "typing")

    try:
        resposta = await agente.processar_mensagem(texto)

        if resposta:
            for i in range(0, len(resposta), 4000):
                chunk = resposta[i:i+4000]
                try:
                    await update.message.reply_text(chunk, parse_mode="Markdown")
                except Exception:
                    await update.message.reply_text(chunk)

            # Detecta se Sofia fez um handoff e notifica Eduardo com contexto completo
            if _detectar_handoff_na_resposta(resposta):
                await _executar_handoff_bot(
                    bot=context.bot,
                    chat_id=chat_id,
                    agente=agente,
                    motivo="Sofia detectou necessidade de atendimento humano"
                )

    except Exception as e:
        logger.error(f"Erro Sofia mensagem: {e}", exc_info=True)
        await update.message.reply_text(
            "⚠️ Desculpa, tive um probleminha técnico. "
            "Vou avisar o Eduardo pra te ajudar!"
        )
        # Notifica Eduardo com contexto do erro
        try:
            user = update.effective_user
            historico = carregar_historico_texto(agente.session_id, limit=5)
            await context.bot.send_message(
                EDUARDO_CHAT_ID,
                f"⚠️ *Erro no atendimento automático*\n"
                f"👤 *Cliente:* {user.full_name}\n"
                f"💬 *Chat:* `{chat_id}`\n"
                f"❌ *Erro:* `{str(e)[:200]}`\n\n"
                f"*📋 Últimas mensagens:*\n```\n{historico[:800]}\n```",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    raise ApplicationHandlerStop


async def sofia_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa fotos enviadas quando agente está ativo."""
    chat_id = update.effective_chat.id

    if chat_id not in _agente_ativo:
        return

    await context.bot.send_chat_action(chat_id, "typing")

    photo = update.message.photo[-1]
    file = await photo.get_file()

    os.makedirs("/root/sierra/agent_uploads", exist_ok=True)
    local_path = f"/root/sierra/agent_uploads/{chat_id}_{photo.file_unique_id}.jpg"
    await file.download_to_drive(local_path)

    agente = get_or_create_agente(chat_id, bot=context.bot)

    try:
        caption = update.message.caption or ""
        resposta = await agente.processar_mensagem(
            f"[FOTO RECEBIDA: {local_path}] {caption}",
            foto_path=local_path
        )
        if resposta:
            for i in range(0, len(resposta), 4000):
                chunk = resposta[i:i+4000]
                try:
                    await update.message.reply_text(chunk, parse_mode="Markdown")
                except Exception:
                    await update.message.reply_text(chunk)

            if _detectar_handoff_na_resposta(resposta):
                await _executar_handoff_bot(
                    bot=context.bot,
                    chat_id=chat_id,
                    agente=agente,
                    motivo="Handoff após processamento de foto/documento"
                )
    except Exception as e:
        logger.error(f"Erro Sofia foto: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Não consegui processar a foto. Tenta enviar de novo?")


async def sofia_documento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa documentos (PDF) quando agente está ativo."""
    chat_id = update.effective_chat.id

    if chat_id not in _agente_ativo:
        return

    doc = update.message.document
    if not doc.file_name.lower().endswith('.pdf'):
        return

    await context.bot.send_chat_action(chat_id, "typing")

    file = await doc.get_file()
    os.makedirs("/root/sierra/agent_uploads", exist_ok=True)
    local_path = f"/root/sierra/agent_uploads/{chat_id}_{doc.file_unique_id}.pdf"
    await file.download_to_drive(local_path)

    agente = get_or_create_agente(chat_id, bot=context.bot)

    try:
        caption = update.message.caption or ""
        resposta = await agente.processar_mensagem(
            f"[PDF RECEBIDO: {local_path}] {caption}",
            foto_path=local_path
        )
        if resposta:
            for i in range(0, len(resposta), 4000):
                try:
                    await update.message.reply_text(resposta[i:i+4000], parse_mode="Markdown")
                except Exception:
                    await update.message.reply_text(resposta[i:i+4000])

            if _detectar_handoff_na_resposta(resposta):
                await _executar_handoff_bot(
                    bot=context.bot,
                    chat_id=chat_id,
                    agente=agente,
                    motivo="Handoff após processamento de PDF"
                )
    except Exception as e:
        logger.error(f"Erro Sofia PDF: {e}")
        await update.message.reply_text("⚠️ Não consegui processar o documento. Tenta de novo?")


def register_agent_handlers(app):
    """Registra os handlers do agente no bot existente."""
    app.add_handler(CommandHandler("agente", cmd_agente))
    app.add_handler(CommandHandler("sofia", cmd_agente))
    app.add_handler(CommandHandler("sair", cmd_sair))

    app.add_handler(CallbackQueryHandler(sofia_callback, pattern="^sofia_"))

    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, sofia_mensagem
    ), group=-1)

    app.add_handler(MessageHandler(
        filters.PHOTO, sofia_foto
    ), group=-1)

    app.add_handler(MessageHandler(
        filters.Document.PDF, sofia_documento
    ), group=-1)

    logger.info("🤖 Agente Sofia registrado no bot!")
