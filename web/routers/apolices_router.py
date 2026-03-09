"""
Rotas de Apólices — listagem, filtros, stats.
"""

from fastapi import APIRouter, Depends, Query
from typing import Optional

import sys
sys.path.insert(0, "/root/sierra")
sys.path.insert(0, "/root/sierra/web")

import database
from auth import get_current_user

router = APIRouter(prefix="/api/apolices", tags=["apolices"])

SEGURADORA_NOMES = {
    "AF": "Alfa Seguros", "AFN": "Alfa Nacional", "AKAD": "AKAD Seguros",
    "ALLI": "Allianz Seguros", "ARG": "Argentavis", "AXA": "AXA Seguros",
    "AZUL": "Azul Seguros", "BRAD": "Bradesco Seguros", "CHUB": "Chubb Seguros",
    "DS": "Darwin Seguros", "ESS": "Essor Seguros", "EZZ": "Ezze Seguros",
    "FFB": "Fairfax Brasil", "GENE": "Generali Seguros", "HDI": "HDI Seguros",
    "ITAU": "Itaú Seguros", "ITU": "Itaú Seguros", "JT": "JT Seguros",
    "LIBE": "Liberty Seguros", "MAPF": "Mapfre Seguros", "MET": "MetLife",
    "MITS": "Mitsui Sumitomo", "PORT": "Porto Seguro", "SANC": "Santander Auto",
    "SOM": "Sompo Seguros", "SUH": "Suhai Seguros", "SUI": "Suíça Seguros",
    "SULA": "SulAmérica", "SURA": "Sura Seguros", "TOKI": "Tokio Marine",
    "UNI": "Unimed Seguros", "ZURI": "Zurich Seguros",
}

RAMO_NOMES = {
    "AUTO": "Automóvel", "RESI": "Residencial", "EMPR": "Empresarial",
    "RCP": "RC Profissional", "COND": "Condomínio", "VIND": "Vida Individual",
    "VGRP": "Vida em Grupo", "EQUI": "Equipamentos", "VIA": "Viagem",
    "CV": "Carta Verde", "MOT": "Motocicleta", "BIK": "Bicicleta",
    "SG": "Seguro Garantia", "FIAN": "Fiança Locatícia", "RCO": "RC Ônibus",
    "RCE": "RC Empregador", "RCG": "RC Geral", "API": "Acidentes Pessoais",
    "GR": "Grandes Riscos", "IMOB": "Imobiliário", "PREV": "Previdência",
}

def _nome_seguradora(sigla):
    if not sigla:
        return "—"
    return SEGURADORA_NOMES.get(sigla.upper(), sigla)

def _nome_ramo(sigla):
    if not sigla:
        return "—"
    return RAMO_NOMES.get(sigla.upper(), sigla)


@router.get("/")
async def listar_apolices(
    q: str = Query("", description="Busca por nome do cliente ou nº apólice"),
    seguradora: str = Query("", description="Filtro por seguradora (sigla)"),
    ramo: str = Query("", description="Filtro por ramo (sigla)"),
    status: str = Query("", description="Filtro por status"),
    vigencia: str = Query("", description="Filtro de vigência: vencidas|30d|60d|90d|vigentes"),
    order: str = Query("vigencia_fim", description="Coluna para ordenar"),
    dir: str = Query("asc", description="Direção: asc|desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=10, le=200),
    user: dict = Depends(get_current_user)
):
    """Lista apólices com filtros, busca e paginação."""
    pool = await database.get_pool()
    cid = user["corretora_id"]

    conditions = ["a.corretora_id=$1"]
    params = [cid]
    idx = 2

    if q:
        conditions.append(f"(c.nome ILIKE ${idx} OR a.numero_apolice ILIKE ${idx})")
        params.append(f"%{q}%")
        idx += 1

    if seguradora:
        conditions.append(f"a.seguradora = ${idx}")
        params.append(seguradora)
        idx += 1

    if ramo:
        conditions.append(f"a.ramo = ${idx}")
        params.append(ramo)
        idx += 1

    if status:
        conditions.append(f"a.status = ${idx}")
        params.append(status)
        idx += 1

    if vigencia == "vencidas":
        conditions.append("a.vigencia_fim < CURRENT_DATE")
    elif vigencia == "30d":
        conditions.append(f"a.vigencia_fim BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '30 days'")
    elif vigencia == "60d":
        conditions.append(f"a.vigencia_fim BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '60 days'")
    elif vigencia == "90d":
        conditions.append(f"a.vigencia_fim BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '90 days'")
    elif vigencia == "vigentes":
        conditions.append("a.status = 'vigente' AND a.vigencia_fim >= CURRENT_DATE")

    where = " AND ".join(conditions)

    # Ordenação segura
    valid_orders = {"vigencia_fim", "vigencia_inicio", "premio", "seguradora", "ramo", "numero_apolice", "cliente"}
    if order not in valid_orders:
        order = "vigencia_fim"
    dir_sql = "DESC" if dir.lower() == "desc" else "ASC"
    order_sql = f"c.nome {dir_sql}" if order == "cliente" else f"a.{order} {dir_sql} NULLS LAST"

    async with pool.acquire() as conn:
        total = await conn.fetchval(f"""
            SELECT COUNT(*) FROM apolices a
            LEFT JOIN clientes c ON c.id = a.cliente_id
            WHERE {where}
        """, *params)

        offset = (page - 1) * limit
        rows = await conn.fetch(f"""
            SELECT a.id, a.seguradora, a.numero_apolice, a.proposta,
                   a.vigencia_inicio, a.vigencia_fim, a.premio,
                   a.ramo, a.status, a.cliente_id, a.veiculo_id,
                   a.emissao, a.created_at,
                   c.nome as cliente_nome, c.cpf_cnpj
            FROM apolices a
            LEFT JOIN clientes c ON c.id = a.cliente_id
            WHERE {where}
            ORDER BY {order_sql}
            LIMIT {limit} OFFSET {offset}
        """, *params)

    from datetime import date as dt_date
    hoje = dt_date.today()

    result = []
    for r in rows:
        vf = r["vigencia_fim"]
        dias_para_vencer = (vf - hoje).days if vf else None
        highlight = None
        if vf:
            if vf < hoje:
                highlight = "vencida"
            elif dias_para_vencer <= 30:
                highlight = "30d"

        result.append({
            "id": r["id"],
            "seguradora": r["seguradora"],
            "seguradora_nome": _nome_seguradora(r["seguradora"]),
            "numero_apolice": r["numero_apolice"],
            "proposta": r["proposta"],
            "vigencia_inicio": r["vigencia_inicio"].isoformat() if r["vigencia_inicio"] else None,
            "vigencia_fim": r["vigencia_fim"].isoformat() if r["vigencia_fim"] else None,
            "premio": float(r["premio"]) if r["premio"] else None,
            "ramo": r["ramo"],
            "ramo_nome": _nome_ramo(r["ramo"]),
            "status": r["status"],
            "cliente_id": r["cliente_id"],
            "cliente_nome": r.get("cliente_nome") or "—",
            "cpf_cnpj": r.get("cpf_cnpj"),
            "dias_para_vencer": dias_para_vencer,
            "highlight": highlight,
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        })

    return {
        "total": total,
        "page": page,
        "pages": max(1, (total + limit - 1) // limit),
        "apolices": result,
    }


@router.get("/stats")
async def apolices_stats(user: dict = Depends(get_current_user)):
    """Stats para o dashboard: a vencer 30/60/90d, últimas 10 importadas, prêmio total."""
    pool = await database.get_pool()
    cid = user["corretora_id"]

    async with pool.acquire() as conn:
        # Totais gerais
        total = await conn.fetchval("SELECT COUNT(*) FROM apolices WHERE corretora_id=$1", cid)
        vigentes = await conn.fetchval(
            "SELECT COUNT(*) FROM apolices WHERE corretora_id=$1 AND status='vigente'", cid)
        premio_total = await conn.fetchval(
            "SELECT COALESCE(SUM(premio),0) FROM apolices WHERE corretora_id=$1 AND status='vigente'", cid)

        # A vencer
        a_vencer_30 = await conn.fetchval("""
            SELECT COUNT(*) FROM apolices
            WHERE corretora_id=$1 AND status='vigente'
            AND vigencia_fim BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '30 days'
        """, cid)
        a_vencer_60 = await conn.fetchval("""
            SELECT COUNT(*) FROM apolices
            WHERE corretora_id=$1 AND status='vigente'
            AND vigencia_fim BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '60 days'
        """, cid)
        a_vencer_90 = await conn.fetchval("""
            SELECT COUNT(*) FROM apolices
            WHERE corretora_id=$1 AND status='vigente'
            AND vigencia_fim BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '90 days'
        """, cid)

        # Últimas 10 apólices importadas
        ultimas = await conn.fetch("""
            SELECT a.id, a.seguradora, a.numero_apolice, a.vigencia_fim, a.premio,
                   a.ramo, a.status, a.created_at,
                   c.nome as cliente_nome
            FROM apolices a
            LEFT JOIN clientes c ON c.id = a.cliente_id
            WHERE a.corretora_id=$1
            ORDER BY a.created_at DESC NULLS LAST
            LIMIT 10
        """, cid)

        # Por seguradora
        por_seg = await conn.fetch("""
            SELECT seguradora, COUNT(*) as qty, COALESCE(SUM(premio),0) as premio
            FROM apolices WHERE corretora_id=$1 AND seguradora IS NOT NULL
            GROUP BY seguradora ORDER BY qty DESC LIMIT 10
        """, cid)

        # Total clientes
        total_clientes = await conn.fetchval(
            "SELECT COUNT(*) FROM clientes WHERE corretora_id=$1", cid)

    return {
        "total": total,
        "vigentes": vigentes,
        "premio_total": float(premio_total),
        "a_vencer_30": a_vencer_30,
        "a_vencer_60": a_vencer_60,
        "a_vencer_90": a_vencer_90,
        "total_clientes": total_clientes,
        "ultimas": [
            {
                "id": r["id"],
                "seguradora": r["seguradora"],
                "seguradora_nome": _nome_seguradora(r["seguradora"]),
                "numero_apolice": r["numero_apolice"],
                "vigencia_fim": r["vigencia_fim"].isoformat() if r["vigencia_fim"] else None,
                "premio": float(r["premio"]) if r["premio"] else None,
                "ramo": _nome_ramo(r["ramo"]),
                "status": r["status"],
                "cliente_nome": r.get("cliente_nome") or "—",
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            }
            for r in ultimas
        ],
        "por_seguradora": [
            {
                "sigla": r["seguradora"],
                "nome": _nome_seguradora(r["seguradora"]),
                "qty": r["qty"],
                "premio": float(r["premio"]),
            }
            for r in por_seg
        ],
    }


@router.get("/filtros")
async def filtros_disponiveis(user: dict = Depends(get_current_user)):
    """Listas de seguradoras e ramos disponíveis para os filtros."""
    pool = await database.get_pool()
    cid = user["corretora_id"]

    async with pool.acquire() as conn:
        segs = await conn.fetch("""
            SELECT DISTINCT seguradora FROM apolices
            WHERE corretora_id=$1 AND seguradora IS NOT NULL
            ORDER BY seguradora
        """, cid)
        ramos = await conn.fetch("""
            SELECT DISTINCT ramo FROM apolices
            WHERE corretora_id=$1 AND ramo IS NOT NULL
            ORDER BY ramo
        """, cid)
        statuses = await conn.fetch("""
            SELECT DISTINCT status FROM apolices
            WHERE corretora_id=$1 AND status IS NOT NULL
            ORDER BY status
        """, cid)

    return {
        "seguradoras": [{"sigla": r["seguradora"], "nome": _nome_seguradora(r["seguradora"])} for r in segs],
        "ramos": [{"sigla": r["ramo"], "nome": _nome_ramo(r["ramo"])} for r in ramos],
        "statuses": [r["status"] for r in statuses],
    }
