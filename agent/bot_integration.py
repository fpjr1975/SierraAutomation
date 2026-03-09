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

# Adiciona path
_SIERRA_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SIERRA_ROOT not in sys.path:
    sys.path.insert(0, _SIERRA_ROOT)

from agent.agent_engine import get_or_create_agente, remover_agente

logger = logging.getLogger(__name__)

# Chat IDs com agente ativo
_agente_ativo = set()

# Eduardo chat ID para notificações
EDUARDO_CHAT_ID = 2104676074


async def cmd_agente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ativa o modo agente Sofia para o chat."""
    chat_id = update.effective_chat.id
    _agente_ativo.add(chat_id)
    
    agente = get_or_create_agente(chat_id, bot=context.bot)
    
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
    
    # Ativa agente se não estiver ativo
    if chat_id not in _agente_ativo:
        _agente_ativo.add(chat_id)
    
    mensagens = {
        "sofia_cotar": "Quero cotar seguro",
        "sofia_renovar": "Quero renovar meu seguro",
        "sofia_docs": "Preciso de um documento",
    }
    
    texto = mensagens.get(data, "Olá")
    
    # Processa como mensagem de texto
    agente = get_or_create_agente(chat_id, bot=context.bot)
    
    await query.message.reply_text("⏳ Processando...")
    
    try:
        resposta = await agente.processar_mensagem(texto)
        if resposta:
            # Divide em chunks se muito longo (Telegram limite 4096)
            for i in range(0, len(resposta), 4000):
                chunk = resposta[i:i+4000]
                await query.message.reply_text(chunk, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Erro Sofia callback: {e}")
        await query.message.reply_text("⚠️ Desculpa, tive um probleminha. Tenta de novo?")


async def sofia_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa mensagens de texto quando agente está ativo."""
    chat_id = update.effective_chat.id
    
    if chat_id not in _agente_ativo:
        # Verifica se tem sessão ativa no DB (caso bot reiniciou e perdeu o set em memória)
        try:
            from agent.agent_engine import _get_db_conn
            conn = _get_db_conn()
            cur = conn.cursor()
            cur.execute("SELECT id FROM agent_sessions WHERE chat_id=%s AND estado='ativo' ORDER BY id DESC LIMIT 1", (chat_id,))
            row = cur.fetchone()
            conn.close()
            if row:
                _agente_ativo.add(chat_id)
                logger.info(f"[Sofia] Restaurou sessão ativa do DB para chat_id={chat_id}")
            else:
                return  # Sem sessão ativa — passa pro próximo handler
        except Exception as e:
            logger.warning(f"[Sofia] Erro ao checar DB: {e}")
            return
    
    texto = update.message.text
    if not texto:
        return
    
    # Ignora comandos
    if texto.startswith('/'):
        return
    
    agente = get_or_create_agente(chat_id, bot=context.bot)
    
    # Indicador de digitação
    await context.bot.send_chat_action(chat_id, "typing")
    
    try:
        resposta = await agente.processar_mensagem(texto)
        if resposta:
            for i in range(0, len(resposta), 4000):
                chunk = resposta[i:i+4000]
                try:
                    await update.message.reply_text(chunk, parse_mode="Markdown")
                except Exception:
                    # Fallback sem Markdown se falhar
                    await update.message.reply_text(chunk)
    except Exception as e:
        logger.error(f"Erro Sofia mensagem: {e}", exc_info=True)
        await update.message.reply_text(
            "⚠️ Desculpa, tive um probleminha técnico. "
            "Vou avisar o Eduardo pra te ajudar!"
        )
        # Notifica Eduardo
        try:
            user = update.effective_user
            await context.bot.send_message(
                EDUARDO_CHAT_ID,
                f"⚠️ *Erro no atendimento automático*\n"
                f"Cliente: {user.full_name}\n"
                f"Chat: {chat_id}\n"
                f"Erro: {str(e)[:200]}",
                parse_mode="Markdown"
            )
        except:
            pass
    
    # Impede que handle_other processe a mesma mensagem
    raise ApplicationHandlerStop


async def sofia_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa fotos enviadas quando agente está ativo."""
    chat_id = update.effective_chat.id
    
    if chat_id not in _agente_ativo:
        return
    
    await context.bot.send_chat_action(chat_id, "typing")
    
    # Baixa a foto
    photo = update.message.photo[-1]  # Maior resolução
    file = await photo.get_file()
    
    os.makedirs("/root/sierra/agent_uploads", exist_ok=True)
    local_path = f"/root/sierra/agent_uploads/{chat_id}_{photo.file_unique_id}.jpg"
    await file.download_to_drive(local_path)
    
    agente = get_or_create_agente(chat_id, bot=context.bot)
    
    try:
        # Envia como mensagem com referência à foto
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
                except:
                    await update.message.reply_text(chunk)
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
                except:
                    await update.message.reply_text(resposta[i:i+4000])
    except Exception as e:
        logger.error(f"Erro Sofia PDF: {e}")
        await update.message.reply_text("⚠️ Não consegui processar o documento. Tenta de novo?")


def register_agent_handlers(app):
    """Registra os handlers do agente no bot existente.
    
    IMPORTANTE: Chamar ANTES dos handlers genéricos do bot,
    pra que o agente intercepte mensagens quando ativo.
    """
    # Comandos
    app.add_handler(CommandHandler("agente", cmd_agente))
    app.add_handler(CommandHandler("sofia", cmd_agente))  # alias
    app.add_handler(CommandHandler("sair", cmd_sair))
    
    # Callbacks dos botões Sofia
    app.add_handler(CallbackQueryHandler(sofia_callback, pattern="^sofia_"))
    
    # Mensagens — grupo -1 (prioridade MAIOR que handlers do bot em grupo 0)
    # Sofia intercepta quando agente ativo, senão passa adiante
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
