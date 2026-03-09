"""
agent_engine.py — Motor do Agente Conversacional Sofia (Sierra Seguros)

Responsável por:
  - Gerenciar sessões de conversa por chat_id (PostgreSQL)
  - Classificar intenções via Claude Sonnet 4 com tool_use
  - Orquestrar as ferramentas (OCR, cotação, PDF, DB)
  - Persistir histórico de mensagens
  - Fazer handoff pro corretor quando necessário
  - Compliance SUSEP: disclaimers automáticos

Modelo: claude-sonnet-4-20250514 (Claude Sonnet 4)
Persona: Sofia — atendente virtual da Sierra Seguros
"""

import os
import sys
import json
import logging
import asyncio
from datetime import datetime
from typing import Optional, Callable

import anthropic
import psycopg2
import psycopg2.extras

# Adiciona o diretório pai (/root/sierra/) ao path
_SIERRA_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SIERRA_ROOT not in sys.path:
    sys.path.insert(0, _SIERRA_ROOT)

from agent.agent_tools import TOOLS_DEFINITIONS, executar_ferramenta

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  CONFIGURAÇÕES
# ─────────────────────────────────────────────────────────────

# Anthropic API key — carregada dos perfis do OpenClaw ou do ambiente
def _get_anthropic_key() -> str:
    # Tenta variável de ambiente primeiro
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    # Tenta do arquivo de perfis do OpenClaw
    try:
        profiles_path = "/root/.openclaw/agents/main/agent/auth-profiles.json"
        with open(profiles_path) as f:
            data = json.load(f)
        token = (
            data.get("profiles", {})
                .get("anthropic:default", {})
                .get("token", "")
        )
        if token:
            return token
    except Exception:
        pass
    logger.warning("⚠️ ANTHROPIC_API_KEY não encontrada!")
    return ""


ANTHROPIC_KEY = _get_anthropic_key()
MODEL = "claude-sonnet-4-20250514"
DB_URL = "postgresql://sierra:SierraDB2026!!@localhost/sierra_db"

# Confiança mínima para continuar sem handoff
CONFIANCA_MINIMA = 0.95

# Máximo de tokens do histórico antes de truncar
MAX_HISTORICO_TOKENS = 4000

# ─────────────────────────────────────────────────────────────
#  SYSTEM PROMPT — Persona Sofia
# ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Você é a Sofia, atendente virtual da Sierra Seguros, corretora de seguros.

## Sua Personalidade
- Educada, objetiva e calorosa — tom informal-profissional em português brasileiro
- Eficiente: vai direto ao ponto sem rodeios desnecessários
- Empática: especialmente em situações difíceis (sinistros, urgências)
- Usa emojis com moderação (1-2 por mensagem, nunca exagera)

## Regras SUSEP (OBRIGATÓRIAS)
- NUNCA recomende uma seguradora específica — apresente sempre como "opções" ou "alternativas"
- Sempre use disclaimers sutis: "valores baseados na cotação atual, podem variar na emissão"
- NUNCA faça promessas de valores exatos antes de calcular
- Em caso de sinistro: oriente mas não interprete coberturas — passe pro Eduardo
- NUNCA forneça CPF, dados sensíveis de terceiros via chat

## Fluxo de Cotação
1. Identifique o que o cliente precisa (use classificar_intencao)
2. Colete dados necessários (CNH, CRLV, CEP) um a um, com confirmação
3. Mostre o resumo dos dados antes de calcular: "Confere essas informações?"
4. Calcule (use calcular_cotacao) e apresente as opções
5. Quando escolher seguradora, gere o PDF (use gerar_pdf_sierra)
6. Notifique o Eduardo com resumo completo (use notificar_corretor)

## Handoff para o Corretor Eduardo
Faça handoff (notificar_corretor com tipo="handoff") quando:
- Confiança na intenção < 0.95
- Cliente pede explicitamente falar com humano
- Sinistro, reclamação, ou situação complexa
- Valor de prêmio acima de R$ 5.000/ano
- Após concluir qualquer cotação completa

Mensagem de handoff ao cliente: "Vou passar pro Eduardo que ele confirma os detalhes! 😊"

## Cenários que você atende
1. **cotacao_nova** — Coletar CNH + CRLV + CEP → calcular → apresentar opções
2. **transferencia** — Transferência de propriedade, novo seguro no nome do comprador
3. **renovacao** — Renovar apólice: buscar cliente, verificar vencimento, recalcular
4. **endosso** — Alterar apólice vigente → handoff imediato pro Eduardo
5. **sinistro** — Orientar, coletar informações básicas → handoff imediato pro Eduardo
6. **documentos** — Enviar apólice, boleto, documentos digitais
7. **duvidas** — Responder dúvidas gerais sobre seguros
8. **assistencia** — Guincho, socorro → informar número 0800 e fazer handoff
9. **status** — Verificar status de cotação ou proposta
10. **indicacao** — Agradecer e pedir indicar amigos/familiares

## Formato de Resposta
- Mensagens curtas e diretas (máximo 3-4 parágrafos)
- Use markdown do Telegram (*negrito*, _itálico_, `código`)
- Para listas de seguradoras, use tabela ou bullets com os valores
- Sempre confirme o próximo passo: "O que prefere fazer agora?"
"""

# ─────────────────────────────────────────────────────────────
#  DATABASE — Sessões e Histórico
# ─────────────────────────────────────────────────────────────

def _get_db_conn():
    """Cria conexão com o PostgreSQL."""
    return psycopg2.connect(DB_URL)


def criar_sessao(chat_id: int, intent: str = None) -> int:
    """
    Cria ou recupera sessão ativa para o chat_id.
    Retorna o session_id.
    """
    conn = _get_db_conn()
    cur = conn.cursor()
    try:
        # Verifica se há sessão ativa (menos de 24h)
        cur.execute("""
            SELECT id FROM agent_sessions
            WHERE chat_id = %s 
              AND updated_at > NOW() - INTERVAL '24 hours'
            ORDER BY updated_at DESC
            LIMIT 1
        """, (chat_id,))
        row = cur.fetchone()
        if row:
            session_id = row[0]
            # Atualiza timestamp e intent se fornecido
            if intent:
                cur.execute("""
                    UPDATE agent_sessions 
                    SET updated_at = NOW(), estado = 'ativo', intent = %s
                    WHERE id = %s
                """, (intent, session_id))
            else:
                cur.execute("""
                    UPDATE agent_sessions SET updated_at = NOW()
                    WHERE id = %s
                """, (session_id,))
            conn.commit()
            return session_id
        else:
            # Nova sessão
            cur.execute("""
                INSERT INTO agent_sessions (chat_id, estado, contexto, intent)
                VALUES (%s, 'ativo', '{}'::jsonb, %s)
                RETURNING id
            """, (chat_id, intent or 'novo'))
            session_id = cur.fetchone()[0]
            conn.commit()
            return session_id
    finally:
        cur.close()
        conn.close()


def salvar_mensagem(session_id: int, role: str, content: str,
                     tool_calls: dict = None):
    """Persiste uma mensagem no histórico da sessão."""
    conn = _get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO agent_messages (session_id, role, content, tool_calls)
            VALUES (%s, %s, %s, %s)
        """, (
            session_id,
            role,
            content,
            json.dumps(tool_calls) if tool_calls else None
        ))
        conn.commit()
    except Exception as e:
        logger.error(f"Erro ao salvar mensagem: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


def carregar_historico(session_id: int, limit: int = 20) -> list:
    """
    Carrega as últimas N mensagens do histórico da sessão.
    Retorna lista no formato esperado pelo Claude.
    """
    conn = _get_db_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT role, content, tool_calls
            FROM agent_messages
            WHERE session_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (session_id, limit))
        rows = cur.fetchall()
        # Retorna em ordem cronológica (do mais antigo pro mais recente)
        rows = list(reversed(rows))

        mensagens = []
        for r in rows:
            role = r["role"]
            content = r["content"]
            tool_calls = r["tool_calls"]

            if role == "tool_result" and tool_calls:
                # Mensagem de resultado de ferramenta
                tc = json.loads(tool_calls) if isinstance(tool_calls, str) else tool_calls
                mensagens.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tc.get("tool_use_id", ""),
                        "content": content
                    }]
                })
            elif role == "tool_use" and tool_calls:
                # Mensagem de chamada de ferramenta (assistant)
                tc = json.loads(tool_calls) if isinstance(tool_calls, str) else tool_calls
                mensagens.append({
                    "role": "assistant",
                    "content": [{
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": tc.get("name", ""),
                        "input": tc.get("input", {})
                    }]
                })
            else:
                mensagens.append({"role": role, "content": content})

        # Validação: remove tool_result órfãos (sem tool_use correspondente)
        tool_use_ids = set()
        for m in mensagens:
            if m.get("role") == "assistant" and isinstance(m.get("content"), list):
                for block in m["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_use_ids.add(block.get("id", ""))
        
        validated = []
        for m in mensagens:
            if m.get("role") == "user" and isinstance(m.get("content"), list):
                blocks = m["content"]
                if any(b.get("type") == "tool_result" and b.get("tool_use_id") not in tool_use_ids for b in blocks if isinstance(b, dict)):
                    logger.warning(f"[Sofia] Removendo tool_result órfão do histórico (session={session_id})")
                    continue
            validated.append(m)
        
        return validated
    finally:
        cur.close()
        conn.close()


def atualizar_contexto(session_id: int, contexto: dict):
    """Atualiza o contexto JSON da sessão (dados coletados até agora)."""
    conn = _get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE agent_sessions
            SET contexto = %s::jsonb, updated_at = NOW()
            WHERE id = %s
        """, (json.dumps(contexto), session_id))
        conn.commit()
    finally:
        cur.close()
        conn.close()


def carregar_contexto(session_id: int) -> dict:
    """Carrega o contexto atual da sessão."""
    conn = _get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT contexto FROM agent_sessions WHERE id = %s", (session_id,))
        row = cur.fetchone()
        if row and row[0]:
            return row[0] if isinstance(row[0], dict) else json.loads(row[0])
        return {}
    finally:
        cur.close()
        conn.close()


def encerrar_sessao(chat_id: int):
    """Marca sessão como encerrada."""
    conn = _get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE agent_sessions SET estado = 'encerrado', updated_at = NOW()
            WHERE chat_id = %s AND estado = 'ativo'
        """, (chat_id,))
        conn.commit()
    finally:
        cur.close()
        conn.close()


# ─────────────────────────────────────────────────────────────
#  MOTOR DO AGENTE
# ─────────────────────────────────────────────────────────────

class SofiaAgent:
    """
    Motor conversacional da Sofia.
    
    Uso:
        agent = SofiaAgent(chat_id=123456789, bot=telegram_bot)
        resposta = await agent.processar_mensagem("quero cotar um seguro")
    """

    def __init__(self, chat_id: int, bot=None):
        self.chat_id = chat_id
        self.bot = bot  # objeto bot do python-telegram-bot
        self.cliente_nome: str = None  # Nome do cliente (preenchido ao longo da conversa)

        # Inicializa cliente Anthropic
        if not ANTHROPIC_KEY:
            raise ValueError("ANTHROPIC_API_KEY não configurada")
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

        # Sessão persistente no banco
        self.session_id = criar_sessao(chat_id)
        self.contexto = carregar_contexto(self.session_id)

        logger.info(f"[Sofia] Sessão {self.session_id} para chat_id={chat_id}")

    async def processar_mensagem(
        self,
        mensagem_usuario: str,
        foto_path: str = None,
        on_progress: Callable = None
    ) -> str:
        """
        Ponto de entrada principal. Processa mensagem do usuário e retorna resposta.
        
        Args:
            mensagem_usuario: Texto enviado pelo cliente
            foto_path: Caminho de imagem (se cliente enviou foto)
            on_progress: Callback opcional para atualizações de progresso (async)
        
        Returns:
            Texto da resposta da Sofia
        """
        # Carrega histórico recente (últimas 20 mensagens)
        historico = carregar_historico(self.session_id, limit=20)

        # Monta a mensagem atual
        if foto_path:
            # Se é uma foto, inclui contexto
            conteudo_usuario = (
                f"{mensagem_usuario}\n"
                f"[Arquivo recebido: {os.path.basename(foto_path)}]"
            ) if mensagem_usuario else f"[Foto enviada: {os.path.basename(foto_path)}]"
            # Inclui o path no contexto para uso pelas ferramentas
            self.contexto["ultimo_foto_path"] = foto_path
            atualizar_contexto(self.session_id, self.contexto)
        else:
            conteudo_usuario = mensagem_usuario

        # Salva mensagem do usuário no histórico
        salvar_mensagem(self.session_id, "user", conteudo_usuario)

        # Adiciona à lista de mensagens pro Claude
        historico.append({"role": "user", "content": conteudo_usuario})

        # Loop agentico: envia pro Claude, processa tool calls até ter resposta final
        resposta_final = await self._loop_agente(historico, on_progress)

        # Salva resposta da Sofia
        salvar_mensagem(self.session_id, "assistant", resposta_final)

        return resposta_final

    async def _loop_agente(
        self,
        mensagens: list,
        on_progress: Callable = None
    ) -> str:
        """
        Loop agentico principal:
        1. Envia mensagens pro Claude
        2. Se retorna tool_use: executa a ferramenta e continua
        3. Se retorna text: retorna como resposta final
        
        Max 5 iterações para evitar loops infinitos.
        """
        max_iteracoes = 5
        iteracao = 0

        while iteracao < max_iteracoes:
            iteracao += 1
            logger.info(f"[Sofia] Loop #{iteracao} | {len(mensagens)} mensagens")

            try:
                # Chama o Claude
                response = self.client.messages.create(
                    model=MODEL,
                    max_tokens=2048,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS_DEFINITIONS,
                    messages=mensagens
                )
            except anthropic.APIError as e:
                logger.error(f"Erro Anthropic API: {e}")
                return (
                    "😕 Tive um problema técnico aqui. "
                    "Vou chamar o Eduardo pra te ajudar! Pode aguardar um momento?"
                )

            # Analisa o motivo de parada
            stop_reason = response.stop_reason

            if stop_reason == "end_turn":
                # Resposta final em texto
                texto = self._extrair_texto(response)
                return texto

            elif stop_reason == "tool_use":
                # O Claude quer usar uma ferramenta
                tool_uses = [b for b in response.content if b.type == "tool_use"]
                texto_junto = self._extrair_texto(response)

                # Adiciona a resposta do assistant (com tool_use) no histórico
                mensagens.append({
                    "role": "assistant",
                    "content": response.content
                })

                # Processa cada ferramenta e monta os resultados
                tool_results = []
                for tool_use in tool_uses:
                    nome = tool_use.name
                    params = tool_use.input
                    tool_id = tool_use.id

                    logger.info(f"[Sofia] Tool call: {nome} | id={tool_id}")

                    # Progresso pro usuário (se tiver callback)
                    if on_progress:
                        msgs_progresso = {
                            "calcular_cotacao": "⏳ Calculando cotação no Agilizador...",
                            "gerar_pdf_sierra": "⏳ Gerando PDF da cotação...",
                            "processar_cnh": "🔍 Lendo CNH...",
                            "processar_crlv": "🔍 Lendo CRVL...",
                            "buscar_cep": "📍 Buscando CEP...",
                            "buscar_cliente": "🔍 Buscando cliente...",
                            "consultar_apolices": "📋 Buscando apólices...",
                            "notificar_corretor": "📲 Notificando corretor...",
                        }
                        msg_prog = msgs_progresso.get(nome)
                        if msg_prog:
                            try:
                                await on_progress(msg_prog)
                            except Exception:
                                pass

                    # Enriquece parâmetros com contexto da sessão quando necessário
                    params = self._enriquecer_params(nome, params)

                    # Executa a ferramenta
                    resultado = await executar_ferramenta(
                        nome=nome,
                        parametros=params,
                        bot=self.bot,
                        on_progress=on_progress,
                        cliente_nome=self.cliente_nome
                    )

                    # Pós-processamento: atualiza contexto com dados coletados
                    self._atualizar_contexto_pos_tool(nome, params, resultado)

                    # Persiste no histórico
                    salvar_mensagem(
                        self.session_id, "tool_result",
                        json.dumps(resultado, ensure_ascii=False, default=str),
                        tool_calls={"tool_use_id": tool_id}
                    )

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": json.dumps(resultado, ensure_ascii=False, default=str)
                    })

                # Adiciona resultados das ferramentas no histórico
                mensagens.append({
                    "role": "user",
                    "content": tool_results
                })

                # Continua o loop para o Claude processar os resultados

            else:
                # Outro motivo de parada (max_tokens, etc.)
                logger.warning(f"[Sofia] Stop reason inesperado: {stop_reason}")
                texto = self._extrair_texto(response)
                return texto if texto else (
                    "Desculpe, tive um problema para completar a resposta. "
                    "Pode repetir sua pergunta?"
                )

        # Se chegou aqui, ultrapassou o limite de iterações
        logger.warning(f"[Sofia] Máximo de iterações atingido para chat_id={self.chat_id}")
        return (
            "Esse atendimento ficou um pouco complexo! 😅 "
            "Vou passar pro Eduardo que ele te ajuda melhor. "
            "Um momento..."
        )

    def _extrair_texto(self, response) -> str:
        """Extrai blocos de texto da resposta do Claude."""
        textos = [b.text for b in response.content if hasattr(b, "text") and b.text]
        return "\n".join(textos).strip()

    def _enriquecer_params(self, nome_ferramenta: str, params: dict) -> dict:
        """
        Injeta dados do contexto da sessão nos parâmetros da ferramenta,
        quando o Claude não os forneceu explicitamente.
        """
        params = dict(params)  # cópia

        if nome_ferramenta == "calcular_cotacao":
            if "chat_id" not in params:
                params["chat_id"] = self.chat_id
            if "session_data" not in params:
                # Monta session_data a partir do contexto
                params["session_data"] = {
                    "cnh": self.contexto.get("cnh"),
                    "crvl": self.contexto.get("crvl"),
                    "cep": self.contexto.get("cep"),
                    "endereco": self.contexto.get("endereco"),
                    "cnh_condutor": self.contexto.get("cnh_condutor"),
                }

        elif nome_ferramenta == "gerar_pdf_sierra":
            if "chat_id" not in params:
                params["chat_id"] = self.chat_id

        elif nome_ferramenta in ("processar_cnh", "processar_crlv"):
            if "foto_path" not in params or not params.get("foto_path"):
                params["foto_path"] = self.contexto.get("ultimo_foto_path", "")

        return params

    def _atualizar_contexto_pos_tool(self, nome: str, params: dict, resultado: dict):
        """
        Atualiza o contexto da sessão com dados coletados pelas ferramentas.
        """
        atualizou = False

        if nome == "processar_cnh" and resultado.get("sucesso"):
            dados = resultado.get("dados", {})
            if self.contexto.get("cnh"):
                # Segunda CNH = condutor
                self.contexto["cnh_condutor"] = dados
            else:
                self.contexto["cnh"] = dados
                # Extrai nome do cliente
                nome_cliente = dados.get("nome", "")
                if nome_cliente and nome_cliente != "N/D":
                    self.cliente_nome = nome_cliente
                    self.contexto["cliente_nome"] = nome_cliente
            atualizou = True

        elif nome == "processar_crlv" and resultado.get("sucesso"):
            self.contexto["crvl"] = resultado.get("dados", {})
            atualizou = True

        elif nome == "buscar_cep" and resultado.get("sucesso"):
            self.contexto["cep"] = resultado.get("cep", "")
            self.contexto["endereco"] = resultado.get("dados_completos", {})
            atualizou = True

        elif nome == "classificar_intencao":
            intent = resultado.get("intencao", "")
            confianca = resultado.get("confianca", 1.0)
            self.contexto["intent_atual"] = intent
            self.contexto["confianca_atual"] = confianca
            atualizou = True

        elif nome == "buscar_cliente" and resultado.get("encontrado"):
            clientes = resultado.get("clientes", [])
            if clientes:
                self.contexto["cliente_db"] = clientes[0]
                nome_db = clientes[0].get("nome", "")
                if nome_db:
                    self.cliente_nome = nome_db
            atualizou = True

        elif nome == "calcular_cotacao":
            self.contexto["ultimo_calculo"] = resultado
            atualizou = True

        if atualizou:
            atualizar_contexto(self.session_id, self.contexto)

    def encerrar(self):
        """Encerra a sessão do agente."""
        encerrar_sessao(self.chat_id)
        logger.info(f"[Sofia] Sessão encerrada para chat_id={self.chat_id}")


# ─────────────────────────────────────────────────────────────
#  CACHE DE INSTÂNCIAS (uma por chat_id ativo)
# ─────────────────────────────────────────────────────────────

_agentes_ativos: dict[int, SofiaAgent] = {}


def get_or_create_agente(chat_id: int, bot=None) -> SofiaAgent:
    """
    Retorna agente existente ou cria novo para o chat_id.
    Mantém instância em memória durante a sessão.
    """
    if chat_id not in _agentes_ativos:
        _agentes_ativos[chat_id] = SofiaAgent(chat_id=chat_id, bot=bot)
    else:
        # Atualiza referência do bot se necessário
        if bot and not _agentes_ativos[chat_id].bot:
            _agentes_ativos[chat_id].bot = bot
    return _agentes_ativos[chat_id]


def remover_agente(chat_id: int):
    """Remove agente da memória e encerra sessão."""
    if chat_id in _agentes_ativos:
        try:
            _agentes_ativos[chat_id].encerrar()
        except Exception:
            pass
        del _agentes_ativos[chat_id]
        logger.info(f"[Sofia] Agente removido do cache: chat_id={chat_id}")
