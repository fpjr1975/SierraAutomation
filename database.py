"""
Sierra SaaS — Acesso ao banco de dados PostgreSQL.
Usa asyncpg pra operações async dentro do bot/API.
"""

import asyncpg
import logging
from datetime import date, datetime

logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "sierra_db",
    "user": "sierra",
    "password": "SierraDB2026!!",
}

_pool = None


async def get_pool():
    """Retorna pool de conexões (cria se não existir)."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(**DB_CONFIG, min_size=2, max_size=10)
        logger.info("Pool de conexões PostgreSQL criado")
    return _pool


async def close_pool():
    """Fecha pool de conexões."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ── CLIENTES ──────────────────────────────────────

async def upsert_cliente(corretora_id: int, nome: str, cpf: str, **kwargs) -> int:
    """Insere ou atualiza cliente. Retorna ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM clientes WHERE corretora_id=$1 AND cpf_cnpj=$2",
            corretora_id, cpf
        )
        if row:
            await conn.execute(
                """UPDATE clientes SET nome=$1, updated_at=NOW(),
                   nascimento=COALESCE($3, nascimento),
                   telefone=COALESCE($4, telefone),
                   email=COALESCE($5, email),
                   cep=COALESCE($6, cep),
                   endereco=COALESCE($7, endereco)
                   WHERE id=$2""",
                nome, row["id"],
                kwargs.get("nascimento"), kwargs.get("telefone"),
                kwargs.get("email"), kwargs.get("cep"), kwargs.get("endereco")
            )
            return row["id"]
        else:
            return await conn.fetchval(
                """INSERT INTO clientes (corretora_id, nome, cpf_cnpj, nascimento, telefone, email, cep, endereco)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id""",
                corretora_id, nome, cpf,
                kwargs.get("nascimento"), kwargs.get("telefone"),
                kwargs.get("email"), kwargs.get("cep"), kwargs.get("endereco")
            )


# ── VEÍCULOS ──────────────────────────────────────

async def upsert_veiculo(cliente_id: int, placa: str, **kwargs) -> int:
    """Insere ou atualiza veículo. Retorna ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM veiculos WHERE cliente_id=$1 AND placa=$2",
            cliente_id, placa
        )
        if row:
            return row["id"]
        else:
            return await conn.fetchval(
                """INSERT INTO veiculos (cliente_id, placa, chassi, marca_modelo, ano_fabricacao, ano_modelo, cor, combustivel, cep_pernoite)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id""",
                cliente_id, placa,
                kwargs.get("chassi"), kwargs.get("marca_modelo"),
                kwargs.get("ano_fabricacao"), kwargs.get("ano_modelo"),
                kwargs.get("cor"), kwargs.get("combustivel"),
                kwargs.get("cep_pernoite")
            )


# ── COTAÇÕES ──────────────────────────────────────

async def inserir_cotacao(corretora_id: int, usuario_id: int, cliente_id: int,
                          veiculo_id: int, tipo: str, cnh_data: dict,
                          crvl_data: dict, cep: str, **kwargs) -> int:
    """Insere cotação. Retorna ID."""
    import json
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """INSERT INTO cotacoes (corretora_id, usuario_id, cliente_id, veiculo_id,
               tipo, cnh_data, crvl_data, condutor_data, cep_pernoite, status)
               VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8::jsonb, $9, 'calculada')
               RETURNING id""",
            corretora_id, usuario_id, cliente_id, veiculo_id,
            tipo, json.dumps(cnh_data), json.dumps(crvl_data),
            json.dumps(kwargs.get("condutor_data")) if kwargs.get("condutor_data") else None,
            cep
        )


async def inserir_resultados(cotacao_id: int, resultados: list):
    """Insere resultados de cotação."""
    import re
    pool = await get_pool()
    async with pool.acquire() as conn:
        for r in resultados:
            # Extrai valor numérico do prêmio
            premio_str = r.get("premio", "")
            premio = None
            if premio_str:
                nums = re.findall(r"[\d.]+", premio_str.replace(".", "").replace(",", "."))
                if nums:
                    try:
                        premio = float(nums[0])
                    except:
                        pass

            # Franquia
            franquia_str = r.get("franquia", "")
            franquia = None
            if franquia_str:
                nums = re.findall(r"[\d.]+", franquia_str.replace(".", "").replace(",", "."))
                if nums:
                    try:
                        franquia = float(nums[0])
                    except:
                        pass

            status = "ok" if premio else ("erro" if r.get("mensagem") else "sem_resultado")

            await conn.execute(
                """INSERT INTO cotacao_resultados (cotacao_id, seguradora, premio, franquia, parcelas, numero_cotacao, mensagem, status)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                cotacao_id, r.get("seguradora", ""),
                premio, franquia,
                r.get("parcelas", ""), r.get("numero", ""),
                r.get("mensagem", ""), status
            )


# ── QUERIES ──────────────────────────────────────

async def get_usuario_by_telegram(telegram_id: int) -> dict:
    """Busca usuário pelo Telegram ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM usuarios WHERE telegram_id=$1 AND active=TRUE",
            telegram_id
        )
        return dict(row) if row else None


async def get_cotacoes_mes(corretora_id: int, mes: int = None, ano: int = None) -> list:
    """Cotações do mês."""
    if not mes:
        mes = date.today().month
    if not ano:
        ano = date.today().year
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT c.*, cl.nome as cliente_nome, v.placa, v.marca_modelo
               FROM cotacoes c
               LEFT JOIN clientes cl ON c.cliente_id = cl.id
               LEFT JOIN veiculos v ON c.veiculo_id = v.id
               WHERE c.corretora_id=$1
               AND EXTRACT(MONTH FROM c.created_at)=$2
               AND EXTRACT(YEAR FROM c.created_at)=$3
               ORDER BY c.created_at DESC""",
            corretora_id, mes, ano
        )
        return [dict(r) for r in rows]


async def get_renovacoes_proximas(corretora_id: int, dias: int = 60) -> list:
    """Apólices que vencem nos próximos X dias."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT a.*, cl.nome as cliente_nome, cl.telefone, v.placa, v.marca_modelo
               FROM apolices a
               LEFT JOIN clientes cl ON a.cliente_id = cl.id
               LEFT JOIN veiculos v ON a.veiculo_id = v.id
               WHERE a.corretora_id=$1
               AND a.status='vigente'
               AND a.vigencia_fim BETWEEN CURRENT_DATE AND CURRENT_DATE + $2 * INTERVAL '1 day'
               ORDER BY a.vigencia_fim ASC""",
            corretora_id, dias
        )
        return [dict(r) for r in rows]


async def dashboard_stats(corretora_id: int) -> dict:
    """Estatísticas pro dashboard."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        stats = {}
        # Total clientes
        stats["total_clientes"] = await conn.fetchval(
            "SELECT COUNT(*) FROM clientes WHERE corretora_id=$1", corretora_id)
        # Cotações do mês
        stats["cotacoes_mes"] = await conn.fetchval(
            """SELECT COUNT(*) FROM cotacoes WHERE corretora_id=$1
               AND EXTRACT(MONTH FROM created_at)=EXTRACT(MONTH FROM NOW())
               AND EXTRACT(YEAR FROM created_at)=EXTRACT(YEAR FROM NOW())""",
            corretora_id)
        # Apólices vigentes
        stats["apolices_vigentes"] = await conn.fetchval(
            "SELECT COUNT(*) FROM apolices WHERE corretora_id=$1 AND status='vigente'",
            corretora_id)
        # Renovações próximas (30 dias)
        stats["renovacoes_30d"] = await conn.fetchval(
            """SELECT COUNT(*) FROM apolices WHERE corretora_id=$1
               AND status='vigente'
               AND vigencia_fim BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '30 days'""",
            corretora_id)
        return stats
