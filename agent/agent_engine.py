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

def _get_anthropic_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
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

CONFIANCA_MINIMA = 0.95
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

## ✅ PODE FAZER (Permitido pela SUSEP)
- Informar preços e coberturas das seguradoras disponíveis
- Comparar opções entre seguradoras (mostrar ranking de preços)
- Coletar dados do cliente (CPF, placa, CNH, CRLV)
- Explicar franquias, condições e coberturas de forma geral
- Mostrar estimativas de prêmio com as opções disponíveis
- Orientar sobre documentação necessária

## ❌ NÃO PODE FAZER (Proibido pela SUSEP)
- Recomendar seguradora específica ("a melhor é X", "sugiro a Y")
- Garantir cobertura de sinistro ("seu caso será coberto", "vai ser pago")
- Fechar contrato ou emitir apólice diretamente
- Prometer preço fixo antes da emissão ("vai custar exatamente R$X")
- Dar conselho jurídico ou médico de qualquer natureza
- Inventar ou estimar dados que não existem no sistema
- Divulgar CPF, dados pessoais ou financeiros de terceiros

## ⚠️ SEMPRE (Obrigatório)
- Disclaimer automático ao apresentar valores: *"Os valores são estimativas. A apólice final pode variar conforme análise da seguradora."*
- Se não souber a resposta, dizer: "Vou verificar com o Eduardo e retorno em breve!"
- Ao coletar dados sensíveis: confirmar antes de prosseguir ("Confere essas informações?")
- Usar linguagem simples, sem jargão técnico excessivo

## 🤝 Handoff para o Corretor Eduardo
Faça handoff (use a ferramenta notificar_corretor com tipo="handoff") OBRIGATORIAMENTE quando:
- Confiança na intenção < 0.95
- Cliente pede explicitamente falar com humano
- Sinistro — acidente, furto, roubo, perda total
- Reclamação ou insatisfação com qualquer serviço
- Endosso (alteração de apólice vigente)
- Cancelamento de apólice
- Situação jurídica ou conflito com seguradora
- Valor de prêmio acima de R$ 5.000/ano
- Após concluir qualquer cotação completa
- Qualquer dúvida que você não tenha certeza

Mensagem padrão ao cliente no handoff: "Vou passar para o Eduardo, nosso especialista. Ele já vai receber todo o contexto da nossa conversa! 😊"

## Regras SUSEP (RESUMO)
- NUNCA recomende uma seguradora específica — apresente sempre como "opções" ou "alternativas"
- Sempre use disclaimers: "valores baseados na cotação atual, podem variar na emissão"
- NUNCA faça promessas de valores exatos antes do cálculo
- Em caso de sinistro: oriente mas não interprete coberturas — passe pro Eduardo IMEDIATAMENTE

## Fluxo de Cotação
1. Identifique o que o cliente precisa (use classificar_intencao)
2. Colete dados necessários (CNH, CRLV, CEP) um a um, com confirmação
3. Mostre o resumo dos dados antes de calcular: "Confere essas informações?"
4. Calcule (use calcular_cotacao) e apresente as opções com disclaimer
5. Quando escolher seguradora, gere o PDF (use gerar_pdf_sierra)
6. Notifique o Eduardo com resumo completo (use notificar_corretor)

## Cenários que você atende
1. **cotacao_nova** — Coletar CNH + CRLV + CEP → calcular → apresentar opções
2. **transferencia** — Transferência de propriedade → handoff imediato pro Eduardo
3. **renovacao** — Renovar apólice: buscar cliente → consultar_renovacoes_pendentes → recalcular
4. **endosso** — Alterar apólice vigente → handoff imediato pro Eduardo
5. **sinistro** — Orientar, coletar informações básicas → handoff IMEDIATO pro Eduardo
6. **documentos** — Enviar apólice, boleto, documentos digitais
7. **duvidas** — Responder dúvidas gerais sobre seguros (sem garantias)
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
    Retorna lista no formato 100% compatível com a API Anthropic messages.

    Algoritmo robusto:
    - Carrega mensagens em ordem cronológica
    - Agrupa tool_use (assistant) + tool_result (user) como pares válidos
    - Se tool_result não tem tool_use correspondente → IGNORA
    - Se tool_use não tem tool_result correspondente → IGNORA
    - Garante alternância correta: user → assistant → user → assistant
    - Se primeira mensagem não é user → prefixar com mensagem user vazia
    - Mescla mensagens consecutivas do mesmo role (evita erro 400)
    """
    conn = _get_db_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # Busca as últimas `limit` mensagens, em ordem cronológica
        cur.execute("""
            SELECT id, role, content, tool_calls
            FROM agent_messages
            WHERE session_id = %s
            ORDER BY created_at ASC, id ASC
            LIMIT %s
        """, (session_id, limit))
        rows = cur.fetchall()

        if not rows:
            return []

        # ── PASSO 1: mapear tool_use_ids e tool_result_ids ──
        # tool_use salvo no DB: role='tool_use', tool_calls={"id": "tu_xxx", "name": "...", "input": {...}}
        # tool_result salvo no DB: role='tool_result', tool_calls={"tool_use_id": "tu_xxx"}
        tool_use_map: dict = {}     # tool_id → row dict
        tool_result_map: dict = {}  # tool_use_id → row dict

        for r in rows:
            tc = r["tool_calls"]
            if isinstance(tc, str):
                try:
                    tc = json.loads(tc)
                except Exception:
                    tc = None

            if r["role"] == "tool_use" and tc:
                tool_id = tc.get("id", "")
                if tool_id:
                    tool_use_map[tool_id] = (r, tc)

            elif r["role"] == "tool_result" and tc:
                tool_use_id = tc.get("tool_use_id", "")
                if tool_use_id:
                    tool_result_map[tool_use_id] = (r, tc)

        # Pares válidos = IDs que aparecem nos DOIS lados
        valid_pair_ids = set(tool_use_map.keys()) & set(tool_result_map.keys())

        if len(tool_result_map) > len(valid_pair_ids):
            orphans = set(tool_result_map.keys()) - valid_pair_ids
            logger.warning(
                f"[Sofia] Ignorando {len(orphans)} tool_result(s) órfão(s) "
                f"(session={session_id}): {orphans}"
            )
        if len(tool_use_map) > len(valid_pair_ids):
            unpaired = set(tool_use_map.keys()) - valid_pair_ids
            logger.warning(
                f"[Sofia] Ignorando {len(unpaired)} tool_use(s) sem tool_result "
                f"(session={session_id}): {unpaired}"
            )

        # ── PASSO 2: construir a lista de mensagens filtrada ──
        mensagens: list = []

        for r in rows:
            role = r["role"]
            content = r["content"] or ""
            tc = r["tool_calls"]
            if isinstance(tc, str):
                try:
                    tc = json.loads(tc)
                except Exception:
                    tc = None

            if role == "tool_use":
                if tc and tc.get("id", "") in valid_pair_ids:
                    mensagens.append({
                        "role": "assistant",
                        "content": [{
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc.get("name", ""),
                            "input": tc.get("input", {})
                        }]
                    })
                # else: ignora (sem par ou sem tc)

            elif role == "tool_result":
                if tc and tc.get("tool_use_id", "") in valid_pair_ids:
                    mensagens.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": tc["tool_use_id"],
                            "content": content
                        }]
                    })
                # else: ignora órfão

            elif role in ("user", "assistant"):
                if content.strip():  # ignora mensagens vazias
                    mensagens.append({"role": role, "content": content})
                # else: ignora

            # Qualquer outro role desconhecido → ignora silenciosamente

        # ── PASSO 3: garantir alternância user ↔ assistant ──
        # Mescla mensagens consecutivas do mesmo role
        merged: list = []
        for m in mensagens:
            if merged and merged[-1]["role"] == m["role"]:
                # Mescla com a última mensagem
                prev = merged[-1]
                pc = prev["content"]
                mc = m["content"]

                if isinstance(pc, str) and isinstance(mc, str):
                    prev["content"] = pc + "\n" + mc
                elif isinstance(pc, list) and isinstance(mc, list):
                    prev["content"] = pc + mc
                elif isinstance(pc, str) and isinstance(mc, list):
                    prev["content"] = [{"type": "text", "text": pc}] + mc
                elif isinstance(pc, list) and isinstance(mc, str):
                    prev["content"] = pc + [{"type": "text", "text": mc}]
            else:
                merged.append(dict(m))

        # ── PASSO 4: primeira mensagem deve ser "user" ──
        if merged and merged[0]["role"] != "user":
            logger.warning(
                f"[Sofia] Histórico não começa com user — prefixando "
                f"mensagem vazia (session={session_id})"
            )
            merged.insert(0, {"role": "user", "content": "..."})

        # ── PASSO 5: validação final — garante alternância estrita ──
        validado: list = []
        for m in merged:
            if validado and validado[-1]["role"] == m["role"]:
                # Isso não deveria acontecer após o merge, mas como failsafe:
                logger.error(
                    f"[Sofia] Alternância inválida detectada após merge "
                    f"(role={m['role']}) — descartando duplicata"
                )
                continue
            validado.append(m)

        logger.debug(
            f"[Sofia] Histórico carregado: {len(rows)} rows → {len(validado)} msgs "
            f"(session={session_id})"
        )
        return validado

    finally:
        cur.close()
        conn.close()


def carregar_historico_texto(session_id: int, limit: int = 10) -> str:
    """
    Retorna um resumo textual do histórico para handoffs.
    Formato legível por humanos.
    """
    conn = _get_db_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT role, content, created_at
            FROM agent_messages
            WHERE session_id = %s AND role IN ('user', 'assistant')
            ORDER BY created_at DESC
            LIMIT %s
        """, (session_id, limit))
        rows = list(reversed(cur.fetchall()))

        if not rows:
            return "(sem histórico disponível)"

        linhas = []
        for r in rows:
            role = r["role"]
            content = (r["content"] or "").strip()
            if not content:
                continue
            if role == "user":
                linhas.append(f"👤 Cliente: {content[:200]}")
            else:
                linhas.append(f"🤖 Sofia: {content[:200]}")

        return "\n".join(linhas) if linhas else "(sem histórico)"
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
        self.bot = bot
        self.cliente_nome: str = None

        if not ANTHROPIC_KEY:
            raise ValueError("ANTHROPIC_API_KEY não configurada")
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

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
        """
        historico = carregar_historico(self.session_id, limit=20)

        if foto_path:
            conteudo_usuario = (
                f"{mensagem_usuario}\n"
                f"[Arquivo recebido: {os.path.basename(foto_path)}]"
            ) if mensagem_usuario else f"[Foto enviada: {os.path.basename(foto_path)}]"
            self.contexto["ultimo_foto_path"] = foto_path
            atualizar_contexto(self.session_id, self.contexto)
        else:
            conteudo_usuario = mensagem_usuario

        salvar_mensagem(self.session_id, "user", conteudo_usuario)
        historico.append({"role": "user", "content": conteudo_usuario})

        resposta_final = await self._loop_agente(historico, on_progress)

        salvar_mensagem(self.session_id, "assistant", resposta_final)

        return resposta_final

    async def _loop_agente(
        self,
        mensagens: list,
        on_progress: Callable = None
    ) -> str:
        """
        Loop agentico principal.
        Max 5 iterações para evitar loops infinitos.
        """
        max_iteracoes = 5
        iteracao = 0

        while iteracao < max_iteracoes:
            iteracao += 1
            logger.info(f"[Sofia] Loop #{iteracao} | {len(mensagens)} mensagens")

            try:
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

            stop_reason = response.stop_reason

            if stop_reason == "end_turn":
                texto = self._extrair_texto(response)
                return texto

            elif stop_reason == "tool_use":
                tool_uses = [b for b in response.content if b.type == "tool_use"]

                # Adiciona resposta do assistant (com tool_use) no histórico em memória
                mensagens.append({
                    "role": "assistant",
                    "content": response.content
                })

                # Salva tool_use blocks no DB (para parear com tool_results no futuro)
                for tu in tool_uses:
                    salvar_mensagem(
                        self.session_id, "tool_use",
                        f"[tool_use: {tu.name}]",
                        tool_calls={"id": tu.id, "name": tu.name, "input": dict(tu.input)}
                    )

                tool_results = []
                for tool_use in tool_uses:
                    nome = tool_use.name
                    params = tool_use.input
                    tool_id = tool_use.id

                    logger.info(f"[Sofia] Tool call: {nome} | id={tool_id}")

                    if on_progress:
                        msgs_progresso = {
                            "calcular_cotacao": "⏳ Calculando cotação no Agilizador...",
                            "gerar_pdf_sierra": "⏳ Gerando PDF da cotação...",
                            "processar_cnh": "🔍 Lendo CNH...",
                            "processar_crlv": "🔍 Lendo CRLV...",
                            "buscar_cep": "📍 Buscando CEP...",
                            "buscar_cliente": "🔍 Buscando cliente...",
                            "consultar_apolices": "📋 Buscando apólices...",
                            "consultar_renovacoes_pendentes": "🔄 Verificando renovações...",
                            "iniciar_renovacao": "🚀 Iniciando renovação...",
                            "notificar_corretor": "📲 Notificando corretor...",
                        }
                        msg_prog = msgs_progresso.get(nome)
                        if msg_prog:
                            try:
                                await on_progress(msg_prog)
                            except Exception:
                                pass

                    params = self._enriquecer_params(nome, params)

                    resultado = await executar_ferramenta(
                        nome=nome,
                        parametros=params,
                        bot=self.bot,
                        on_progress=on_progress,
                        cliente_nome=self.cliente_nome
                    )

                    self._atualizar_contexto_pos_tool(nome, params, resultado)

                    resultado_str = json.dumps(resultado, ensure_ascii=False, default=str)

                    # Salva tool_result no DB (pareado com o tool_use salvo acima)
                    salvar_mensagem(
                        self.session_id, "tool_result",
                        resultado_str,
                        tool_calls={"tool_use_id": tool_id}
                    )

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": resultado_str
                    })

                mensagens.append({
                    "role": "user",
                    "content": tool_results
                })

            else:
                logger.warning(f"[Sofia] Stop reason inesperado: {stop_reason}")
                texto = self._extrair_texto(response)
                return texto if texto else (
                    "Desculpe, tive um problema para completar a resposta. "
                    "Pode repetir sua pergunta?"
                )

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
        params = dict(params)

        if nome_ferramenta == "calcular_cotacao":
            if "chat_id" not in params:
                params["chat_id"] = self.chat_id
            if "session_data" not in params:
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

        elif nome_ferramenta == "notificar_corretor":
            # Injeta contexto do cliente e histórico resumido para handoffs ricos
            if "chat_id" not in params:
                params["chat_id"] = self.chat_id
            if "cliente_nome" not in params and self.cliente_nome:
                params["cliente_nome"] = self.cliente_nome
            # Inclui resumo da conversa para handoffs
            if params.get("tipo") == "handoff" and "historico_resumo" not in params:
                params["historico_resumo"] = carregar_historico_texto(
                    self.session_id, limit=10
                )

        elif nome_ferramenta in ("consultar_renovacoes_pendentes", "iniciar_renovacao"):
            # Injeta cliente_id do contexto se disponível
            if "cliente_id" not in params:
                cliente_db = self.contexto.get("cliente_db", {})
                if cliente_db.get("id"):
                    params["cliente_id"] = cliente_db["id"]

        return params

    def _atualizar_contexto_pos_tool(self, nome: str, params: dict, resultado: dict):
        """Atualiza o contexto da sessão com dados coletados pelas ferramentas."""
        atualizou = False

        if nome == "processar_cnh" and resultado.get("sucesso"):
            dados = resultado.get("dados", {})
            if self.contexto.get("cnh"):
                self.contexto["cnh_condutor"] = dados
            else:
                self.contexto["cnh"] = dados
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
    """Retorna agente existente ou cria novo para o chat_id."""
    if chat_id not in _agentes_ativos:
        _agentes_ativos[chat_id] = SofiaAgent(chat_id=chat_id, bot=bot)
    else:
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
