"""
Dashboard de Comissões — MVP sem bordereaux
Calcula comissões esperadas com base em apólices vigentes.
"""
import sys
sys.path.insert(0, "/root/sierra")
sys.path.insert(0, "/root/sierra/web")

from fastapi import APIRouter, Depends, Query, HTTPException
from datetime import date, timedelta
import database
from auth import get_current_user

router = APIRouter(prefix="/api/comissoes", tags=["comissoes"])


@router.get("/resumo")
async def resumo(user: dict = Depends(get_current_user)):
    """Resumo de comissões: mês atual, acumulado ano, projeção trimestral."""
    pool = await database.get_pool()
    cid = user["corretora_id"]
    hoje = date.today()

    async with pool.acquire() as conn:
        # Esperado mês atual (apólices vigentes com vigência no mês atual)
        mes_atual = await conn.fetchval("""
            SELECT COALESCE(SUM(premio * comissao_percentual / 100), 0)
            FROM apolices
            WHERE corretora_id = $1
              AND status = 'vigente'
              AND comissao_percentual IS NOT NULL
              AND EXTRACT(YEAR FROM vigencia_inicio) = $2
              AND EXTRACT(MONTH FROM vigencia_inicio) = $3
        """, cid, hoje.year, hoje.month)

        # Acumulado ano (todas apólices vigentes criadas no ano)
        acumulado_ano = await conn.fetchval("""
            SELECT COALESCE(SUM(premio * comissao_percentual / 100), 0)
            FROM apolices
            WHERE corretora_id = $1
              AND comissao_percentual IS NOT NULL
              AND EXTRACT(YEAR FROM vigencia_inicio) = $2
        """, cid, hoje.year)

        # Projeção trimestral (próximos 3 meses)
        projecao = await conn.fetchval("""
            SELECT COALESCE(SUM(premio * comissao_percentual / 100), 0)
            FROM apolices
            WHERE corretora_id = $1
              AND status = 'vigente'
              AND comissao_percentual IS NOT NULL
              AND vigencia_fim >= $2
              AND vigencia_inicio <= $3
        """, cid, hoje, hoje + timedelta(days=90))

        # Total carteira ativa
        total_premio_carteira = await conn.fetchval("""
            SELECT COALESCE(SUM(premio), 0)
            FROM apolices
            WHERE corretora_id = $1 AND status = 'vigente'
        """, cid)

    return {
        "mes_atual": float(mes_atual),
        "acumulado_ano": float(acumulado_ano),
        "projecao_trimestral": float(projecao),
        "total_premio_carteira": float(total_premio_carteira),
        "mes_referencia": hoje.strftime("%B/%Y"),
    }


@router.get("/por-mes")
async def por_mes(user: dict = Depends(get_current_user)):
    """Comissões esperadas por mês (últimos 12 meses + próximos 3)."""
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                EXTRACT(YEAR FROM vigencia_inicio)::int as ano,
                EXTRACT(MONTH FROM vigencia_inicio)::int as mes,
                COALESCE(SUM(premio * comissao_percentual / 100), 0) as comissao_total,
                COUNT(*) as total_apolices
            FROM apolices
            WHERE corretora_id = $1
              AND comissao_percentual IS NOT NULL
              AND vigencia_inicio >= (CURRENT_DATE - INTERVAL '12 months')
              AND vigencia_inicio <= (CURRENT_DATE + INTERVAL '3 months')
            GROUP BY ano, mes
            ORDER BY ano, mes
        """, cid)
    meses_pt = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
    return [
        {
            "ano": r["ano"],
            "mes": r["mes"],
            "mes_label": f"{meses_pt[r['mes']-1]}/{str(r['ano'])[2:]}",
            "comissao_total": float(r["comissao_total"]),
            "total_apolices": r["total_apolices"],
        }
        for r in rows
    ]


@router.get("/por-seguradora")
async def por_seguradora(user: dict = Depends(get_current_user)):
    """Comissões agrupadas por seguradora."""
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                seguradora,
                COUNT(*) as total_apolices,
                COALESCE(SUM(premio), 0) as premio_total,
                COALESCE(AVG(comissao_percentual), 0) as comissao_media_pct,
                COALESCE(SUM(premio * comissao_percentual / 100), 0) as comissao_total
            FROM apolices
            WHERE corretora_id = $1
              AND status = 'vigente'
              AND comissao_percentual IS NOT NULL
            GROUP BY seguradora
            ORDER BY comissao_total DESC
        """, cid)
    total_comissao = sum(float(r["comissao_total"]) for r in rows)
    return [
        {
            "seguradora": r["seguradora"],
            "total_apolices": r["total_apolices"],
            "premio_total": float(r["premio_total"]),
            "comissao_media_pct": round(float(r["comissao_media_pct"]), 2),
            "comissao_total": float(r["comissao_total"]),
            "participacao_pct": round(float(r["comissao_total"]) / total_comissao * 100, 1) if total_comissao > 0 else 0,
        }
        for r in rows
    ]


@router.get("/por-produtor")
async def por_produtor(user: dict = Depends(get_current_user)):
    """Comissões agrupadas por produtor."""
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                COALESCE(produtor, 'Sem produtor') as produtor,
                COUNT(*) as total_apolices,
                COALESCE(SUM(premio), 0) as premio_total,
                COALESCE(SUM(premio * comissao_percentual / 100), 0) as comissao_total
            FROM apolices
            WHERE corretora_id = $1
              AND status = 'vigente'
              AND comissao_percentual IS NOT NULL
            GROUP BY produtor
            ORDER BY comissao_total DESC
        """, cid)
    total_comissao = sum(float(r["comissao_total"]) for r in rows)
    return [
        {
            "produtor": r["produtor"],
            "total_apolices": r["total_apolices"],
            "premio_total": float(r["premio_total"]),
            "comissao_total": float(r["comissao_total"]),
            "participacao_pct": round(float(r["comissao_total"]) / total_comissao * 100, 1) if total_comissao > 0 else 0,
        }
        for r in rows
    ]


@router.get("/projecao")
async def projecao(user: dict = Depends(get_current_user)):
    """Projeção de comissões para os próximos 3 meses com base em vigências ativas."""
    pool = await database.get_pool()
    cid = user["corretora_id"]
    hoje = date.today()
    meses_pt = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                EXTRACT(YEAR FROM vigencia_fim)::int as ano,
                EXTRACT(MONTH FROM vigencia_fim)::int as mes,
                COUNT(*) as renovacoes_previstas,
                COALESCE(SUM(premio), 0) as premio_em_risco,
                COALESCE(SUM(premio * comissao_percentual / 100), 0) as comissao_projetada
            FROM apolices
            WHERE corretora_id = $1
              AND status = 'vigente'
              AND comissao_percentual IS NOT NULL
              AND vigencia_fim >= $2
              AND vigencia_fim <= $3
            GROUP BY ano, mes
            ORDER BY ano, mes
        """, cid, hoje, hoje + timedelta(days=90))

    return [
        {
            "ano": r["ano"],
            "mes": r["mes"],
            "mes_label": f"{meses_pt[r['mes']-1]}/{str(r['ano'])[2:]}",
            "renovacoes_previstas": r["renovacoes_previstas"],
            "premio_em_risco": float(r["premio_em_risco"]),
            "comissao_projetada": float(r["comissao_projetada"]),
        }
        for r in rows
    ]


# ── STRESS TEST ──────────────────────────────────────────────────────────────

@router.get("/stress-test")
async def stress_test(
    seguradora: str = Query(..., description="Nome da seguradora a simular remoção"),
    user: dict = Depends(get_current_user)
):
    """
    Simula: 'e se a seguradora X sair da carteira?'
    Retorna apólices afetadas, prêmio em risco, % da carteira, clientes afetados.
    """
    pool = await database.get_pool()
    cid = user["corretora_id"]

    async with pool.acquire() as conn:
        # Totais da carteira
        total_apolices = await conn.fetchval(
            "SELECT COUNT(*) FROM apolices WHERE corretora_id=$1 AND status='vigente'", cid)
        total_premio = await conn.fetchval(
            "SELECT COALESCE(SUM(premio),0) FROM apolices WHERE corretora_id=$1 AND status='vigente'", cid)
        total_clientes = await conn.fetchval(
            "SELECT COUNT(DISTINCT cliente_id) FROM apolices WHERE corretora_id=$1 AND status='vigente'", cid)

        # Apólices da seguradora
        afetadas = await conn.fetchval(
            "SELECT COUNT(*) FROM apolices WHERE corretora_id=$1 AND status='vigente' AND LOWER(seguradora) ILIKE $2",
            cid, f"%{seguradora.lower()}%")
        premio_risco = await conn.fetchval(
            "SELECT COALESCE(SUM(premio),0) FROM apolices WHERE corretora_id=$1 AND status='vigente' AND LOWER(seguradora) ILIKE $2",
            cid, f"%{seguradora.lower()}%")
        comissao_risco = await conn.fetchval(
            "SELECT COALESCE(SUM(premio * comissao_percentual / 100),0) FROM apolices WHERE corretora_id=$1 AND status='vigente' AND comissao_percentual IS NOT NULL AND LOWER(seguradora) ILIKE $2",
            cid, f"%{seguradora.lower()}%")
        clientes_afetados = await conn.fetchval(
            "SELECT COUNT(DISTINCT cliente_id) FROM apolices WHERE corretora_id=$1 AND status='vigente' AND LOWER(seguradora) ILIKE $2",
            cid, f"%{seguradora.lower()}%")

        # Seguradoras alternativas (top 5 por volume)
        alternativas = await conn.fetch("""
            SELECT seguradora, COUNT(*) as total, COALESCE(SUM(premio),0) as premio_total
            FROM apolices
            WHERE corretora_id=$1 AND status='vigente'
              AND LOWER(seguradora) NOT ILIKE $2
            GROUP BY seguradora
            ORDER BY total DESC
            LIMIT 5
        """, cid, f"%{seguradora.lower()}%")

    pct_apolices = round(float(afetadas) / float(total_apolices) * 100, 1) if total_apolices > 0 else 0
    pct_premio = round(float(premio_risco) / float(total_premio) * 100, 1) if total_premio > 0 else 0
    pct_clientes = round(float(clientes_afetados) / float(total_clientes) * 100, 1) if total_clientes > 0 else 0

    nivel_risco = "ALTO" if pct_premio > 30 else "MÉDIO" if pct_premio > 15 else "BAIXO"

    return {
        "seguradora_simulada": seguradora,
        "impacto": {
            "apolices_afetadas": int(afetadas),
            "pct_apolices": pct_apolices,
            "premio_total_risco": float(premio_risco),
            "pct_premio": pct_premio,
            "comissao_risco": float(comissao_risco),
            "clientes_afetados": int(clientes_afetados),
            "pct_clientes": pct_clientes,
        },
        "carteira": {
            "total_apolices": int(total_apolices),
            "total_premio": float(total_premio),
            "total_clientes": int(total_clientes),
        },
        "nivel_risco": nivel_risco,
        "alternativas": [
            {
                "seguradora": r["seguradora"],
                "total_apolices": r["total"],
                "premio_total": float(r["premio_total"])
            }
            for r in alternativas
        ]
    }
