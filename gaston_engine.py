"""
Gastón Engine — Conselheiro de Gestão IA para Sierra Seguros.
Usa Claude Opus via Anthropic API para conversas profundas.
Memória persistente por usuário em /root/sierra/gaston/data/
"""

import os
import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path

import httpx
import asyncpg

logger = logging.getLogger(__name__)

GASTON_DIR = Path("/root/sierra/gaston")
DATA_DIR = GASTON_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# API config — usa Anthropic direto (Opus precisa de API key)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# Modelo: Opus pro pensamento estratégico (Eduardo/Maurício trocam ideia com o Gastón)
# Opus direto pela Anthropic
MODEL_PRIMARY = "claude-opus-4-0-20250514"
MODEL_FALLBACK = "claude-sonnet-4-20250514"
USE_OPENROUTER_PRIMARY = False

# Whitelist: só esses IDs podem usar o /gestor
ALLOWED_USERS = {
    6553672222,   # Fafá (admin)
    2104676074,   # Eduardo
    # Maurício: adicionar ID quando soubermos
}

# Carrega os arquivos do Gastón
def _load_file(path: str) -> str:
    """Carrega um arquivo de texto."""
    try:
        with open(path, "r") as f:
            return f.read()
    except Exception:
        return ""


async def _build_system_prompt() -> str:
    """Monta o system prompt completo do Gastón com SKILL + references + contexto + dados ao vivo."""
    skill = _load_file(GASTON_DIR / "SKILL.md")
    
    # References
    refs = []
    ref_dir = GASTON_DIR / "references"
    if ref_dir.exists():
        for f in sorted(ref_dir.glob("*.md")):
            content = _load_file(f)
            if content:
                refs.append(f"## Referência: {f.stem}\n\n{content}")
    
    # Contexto Sierra pré-carregado (estático)
    sierra_ctx = _load_file(GASTON_DIR / "sierra-context.md")
    
    # Dados AO VIVO do banco
    live_data = await _get_live_data()
    
    system = f"""{skill}

---

# Referências Técnicas

{"---".join(refs)}

---

# Dados da Sierra Seguros (Contexto base)

{sierra_ctx}

---

{live_data}

---

# Instruções Operacionais

- Você está operando dentro do bot Telegram da Sierra Seguros (@Sierrasegbot)
- O usuário está conversando via comando /gestor
- VOCÊ TEM ACESSO AOS DADOS REAIS acima — USE-OS para responder com números concretos
- Os dados ao vivo vêm direto do banco do Vértice (sistema da Sierra)
- Se precisar de dados que não estão acima, pergunte diretamente
- Mantenha respostas concisas mas profundas — é Telegram, não relatório
- Formate com Markdown compatível com Telegram (negrito, itálico, listas)
- Quando mencionar valores, use R$ e formato brasileiro (1.234,56)
- Responda SEMPRE em português brasileiro
"""
    return system


def _get_user_memory_path(user_id: int) -> Path:
    """Caminho do arquivo de memória do usuário."""
    return DATA_DIR / f"user_{user_id}.json"


def _load_user_memory(user_id: int) -> dict:
    """Carrega memória persistente do usuário."""
    path = _get_user_memory_path(user_id)
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return {"messages": [], "context": {}}
    return {"messages": [], "context": {}}


def _save_user_memory(user_id: int, memory: dict):
    """Salva memória persistente do usuário."""
    path = _get_user_memory_path(user_id)
    # Mantém apenas as últimas 50 mensagens pra não estourar contexto
    if len(memory.get("messages", [])) > 50:
        memory["messages"] = memory["messages"][-50:]
    with open(path, "w") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


DB_URL = "postgresql://sierra:SierraDB2026!!@localhost/sierra_db"

async def _get_live_data() -> str:
    """Puxa dados reais do banco pra contextualizar o Gastón."""
    try:
        conn = await asyncpg.connect(DB_URL)
        
        lines = ["# 📊 DADOS AO VIVO DO BANCO (atualizados agora)\n"]
        
        # Totais gerais
        total_clientes = await conn.fetchval("SELECT count(*) FROM clientes WHERE corretora_id=1")
        total_apolices = await conn.fetchval("SELECT count(*) FROM apolices WHERE corretora_id=1")
        total_premio = await conn.fetchval("SELECT COALESCE(SUM(premio),0) FROM apolices WHERE corretora_id=1 AND premio > 0")
        total_veiculos = await conn.fetchval("SELECT count(*) FROM veiculos")
        
        lines.append(f"## Carteira Geral")
        lines.append(f"- Clientes: {total_clientes}")
        lines.append(f"- Apólices no sistema: {total_apolices}")
        lines.append(f"- Veículos cadastrados: {total_veiculos}")
        lines.append(f"- Prêmio total: R$ {total_premio:,.2f}")
        lines.append("")
        
        # Por mês 2026
        rows = await conn.fetch("""
            SELECT EXTRACT(MONTH FROM vigencia_inicio)::int as mes,
                count(*) as qtd, count(DISTINCT cliente_id) as clientes,
                COALESCE(ROUND(SUM(premio)::numeric,2),0) as premio,
                COALESCE(ROUND(AVG(premio)::numeric,2),0) as ticket
            FROM apolices WHERE vigencia_inicio >= '2026-01-01' AND vigencia_inicio < '2027-01-01'
            GROUP BY mes ORDER BY mes
        """)
        if rows:
            meses_nome = {1:'Jan',2:'Fev',3:'Mar',4:'Abr',5:'Mai',6:'Jun',7:'Jul',8:'Ago',9:'Set',10:'Out',11:'Nov',12:'Dez'}
            lines.append("## Produção 2026 (por mês de vigência)")
            for r in rows:
                m = meses_nome.get(r['mes'], str(r['mes']))
                lines.append(f"- {m}/2026: {r['qtd']} apólices | {r['clientes']} clientes | R$ {r['premio']:,.2f} | Ticket médio R$ {r['ticket']:,.2f}")
            lines.append("")
        
        # 2025 resumo
        rows25 = await conn.fetch("""
            SELECT EXTRACT(MONTH FROM vigencia_inicio)::int as mes,
                count(*) as qtd, COALESCE(ROUND(SUM(premio)::numeric,2),0) as premio
            FROM apolices WHERE vigencia_inicio >= '2025-01-01' AND vigencia_inicio < '2026-01-01'
            GROUP BY mes ORDER BY mes
        """)
        if rows25:
            lines.append("## Produção 2025 (por mês de vigência)")
            for r in rows25:
                m = meses_nome.get(r['mes'], str(r['mes']))
                lines.append(f"- {m}/2025: {r['qtd']} apólices | R$ {r['premio']:,.2f}")
            lines.append("")
        
        # Top seguradoras
        segs = await conn.fetch("""
            SELECT seguradora, count(*) as qtd, COALESCE(ROUND(SUM(premio)::numeric,2),0) as premio
            FROM apolices WHERE seguradora != '' AND premio > 0
            GROUP BY seguradora ORDER BY premio DESC LIMIT 10
        """)
        if segs:
            lines.append("## Top Seguradoras (por prêmio total)")
            for s in segs:
                lines.append(f"- {s['seguradora']}: {s['qtd']} apólices | R$ {s['premio']:,.2f}")
            lines.append("")
        
        # Vencimentos
        venc30 = await conn.fetchval("SELECT count(*) FROM apolices WHERE vigencia_fim BETWEEN CURRENT_DATE AND CURRENT_DATE + interval '30 days'")
        venc60 = await conn.fetchval("SELECT count(*) FROM apolices WHERE vigencia_fim BETWEEN CURRENT_DATE AND CURRENT_DATE + interval '60 days'")
        venc90 = await conn.fetchval("SELECT count(*) FROM apolices WHERE vigencia_fim BETWEEN CURRENT_DATE AND CURRENT_DATE + interval '90 days'")
        vencidas = await conn.fetchval("SELECT count(*) FROM apolices WHERE vigencia_fim < CURRENT_DATE AND vigencia_fim > CURRENT_DATE - interval '90 days'")
        
        lines.append("## Renovações / Vencimentos")
        lines.append(f"- Vencendo em 30 dias: {venc30}")
        lines.append(f"- Vencendo em 60 dias: {venc60}")
        lines.append(f"- Vencendo em 90 dias: {venc90}")
        lines.append(f"- Vencidas últimos 90 dias: {vencidas}")
        lines.append("")
        
        # Ramos
        ramos = await conn.fetch("""
            SELECT ramo, count(*) as qtd, COALESCE(ROUND(SUM(premio)::numeric,2),0) as premio
            FROM apolices WHERE ramo IS NOT NULL AND ramo != ''
            GROUP BY ramo ORDER BY qtd DESC
        """)
        if ramos:
            lines.append("## Distribuição por Ramo")
            for r in ramos:
                lines.append(f"- {r['ramo']}: {r['qtd']} apólices | R$ {r['premio']:,.2f}")
            lines.append("")
        
        # Cotações feitas pelo sistema
        cotacoes = await conn.fetchval("SELECT count(*) FROM cotacoes")
        lines.append(f"## Sistema Vértice")
        lines.append(f"- Cotações realizadas pelo sistema: {cotacoes}")
        lines.append(f"- Data da consulta: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        
        await conn.close()
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Erro ao buscar dados do banco: {e}")
        return f"# ⚠️ Erro ao acessar banco de dados: {e}"


def is_allowed(user_id: int) -> bool:
    """Verifica se o usuário tem acesso ao /gestor."""
    return user_id in ALLOWED_USERS


async def chat(user_id: int, user_name: str, message: str) -> str:
    """
    Envia mensagem pro Gastón e retorna a resposta.
    Mantém histórico de conversa persistente por usuário.
    """
    memory = _load_user_memory(user_id)
    
    # Adiciona a mensagem do usuário ao histórico
    memory["messages"].append({
        "role": "user",
        "content": message,
        "timestamp": datetime.now().isoformat()
    })
    
    # Monta mensagens pra API (agora com dados ao vivo do banco)
    system_prompt = await _build_system_prompt()
    
    # Adiciona contexto do usuário se existir
    user_ctx = memory.get("context", {})
    if user_ctx:
        system_prompt += f"\n\n# Contexto do Usuário ({user_name})\n"
        for k, v in user_ctx.items():
            system_prompt += f"- {k}: {v}\n"
    
    # Prepara mensagens (sem timestamps, só role + content)
    api_messages = []
    for msg in memory["messages"]:
        api_messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })
    
    response_text = ""
    
    # Anthropic direto (Opus 4)
    if ANTHROPIC_API_KEY:
        try:
            response_text = await _call_anthropic(system_prompt, api_messages)
        except Exception as e:
            logger.error(f"Erro Anthropic: {e}")
    
    # Fallback 2: OpenRouter Kimi
    if not response_text and OPENROUTER_API_KEY:
        try:
            response_text = await _call_openrouter(system_prompt, api_messages)
        except Exception as e:
            logger.error(f"Erro OpenRouter: {e}")
    
    if not response_text:
        response_text = "⚠️ Não consegui processar sua mensagem. Tente novamente em instantes."
    
    # Salva resposta no histórico
    memory["messages"].append({
        "role": "assistant",
        "content": response_text,
        "timestamp": datetime.now().isoformat()
    })
    _save_user_memory(user_id, memory)
    
    return response_text


async def _call_anthropic(system: str, messages: list) -> str:
    """Chama API Anthropic diretamente (Claude Opus)."""
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": MODEL_PRIMARY,
                "max_tokens": 4096,
                "system": system,
                "messages": messages
            }
        )
        data = resp.json()
        if "content" in data and len(data["content"]) > 0:
            return data["content"][0]["text"]
        elif "error" in data:
            logger.error(f"Anthropic error: {data['error']}")
            # Se Opus falhar, tenta Sonnet
            resp2 = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": MODEL_FALLBACK,
                    "max_tokens": 4096,
                    "system": system,
                    "messages": messages
                }
            )
            data2 = resp2.json()
            if "content" in data2 and len(data2["content"]) > 0:
                return data2["content"][0]["text"]
        return ""


async def _call_openrouter(system: str, messages: list, model: str = "moonshotai/kimi-k2.5") -> str:
    """Chama via OpenRouter."""
    api_messages = [{"role": "system", "content": system}] + messages
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": api_messages,
                "max_tokens": 4096
            }
        )
        data = resp.json()
        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0]["message"]["content"]
        return ""


def clear_history(user_id: int):
    """Limpa histórico de conversa do usuário."""
    memory = _load_user_memory(user_id)
    memory["messages"] = []
    _save_user_memory(user_id, memory)
    logger.info(f"Histórico limpo para user {user_id}")
