"""
Analytics API — dados para o dashboard gerencial + ficha cliente
"""
from fastapi import APIRouter, Depends, Query, Request
from datetime import date
import sys
sys.path.insert(0, "/root/sierra")
sys.path.insert(0, "/root/sierra/web")
import database
from auth import get_current_user

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/overview")
async def overview(user: dict = Depends(get_current_user)):
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        total_apolices = await conn.fetchval(
            "SELECT COUNT(*) FROM apolices WHERE corretora_id=$1", cid)
        ativas = await conn.fetchval(
            "SELECT COUNT(*) FROM apolices WHERE corretora_id=$1 AND status='vigente'", cid)
        total_clientes = await conn.fetchval(
            "SELECT COUNT(*) FROM clientes WHERE corretora_id=$1", cid)
        premio_total = await conn.fetchval(
            "SELECT COALESCE(SUM(premio),0) FROM apolices WHERE corretora_id=$1", cid)
        a_receber = await conn.fetchval("""
            SELECT COALESCE(SUM(p.valor),0) FROM parcelas p
            JOIN apolices a ON p.apolice_id=a.id
            WHERE a.corretora_id=$1 AND p.vencimento >= CURRENT_DATE AND p.valor > 0
        """, cid)
    return {
        "total_apolices": total_apolices,
        "apolices_ativas": ativas,
        "total_clientes": total_clientes,
        "premio_total": float(premio_total),
        "a_receber": float(a_receber),
    }


@router.get("/faturamento-anual")
async def faturamento_anual(user: dict = Depends(get_current_user)):
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT EXTRACT(YEAR FROM p.vencimento)::int as ano,
                   COUNT(*) as parcelas,
                   SUM(p.valor) as total
            FROM parcelas p JOIN apolices a ON p.apolice_id=a.id
            WHERE a.corretora_id=$1 AND p.valor > 0
              AND EXTRACT(YEAR FROM p.vencimento) BETWEEN 2018 AND 2026
            GROUP BY ano ORDER BY ano
        """, cid)
    return [{"ano": r["ano"], "parcelas": r["parcelas"], "total": float(r["total"])} for r in rows]


@router.get("/faturamento-detalhe/{ano}")
async def faturamento_detalhe(ano: int, user: dict = Depends(get_current_user)):
    """Drill-down do faturamento por ano: mês a mês, por seguradora, por ramo, por produtor."""
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        # Mês a mês
        mensal = await conn.fetch("""
            SELECT EXTRACT(MONTH FROM p.vencimento)::int as mes,
                   COUNT(*) as parcelas,
                   SUM(p.valor) as total
            FROM parcelas p JOIN apolices a ON p.apolice_id=a.id
            WHERE a.corretora_id=$1 AND p.valor > 0
              AND EXTRACT(YEAR FROM p.vencimento) = $2
            GROUP BY mes ORDER BY mes
        """, cid, ano)

        # Por seguradora
        por_seg = await conn.fetch("""
            SELECT a.seguradora, COUNT(DISTINCT a.id) as apolices,
                   SUM(p.valor) as total
            FROM parcelas p JOIN apolices a ON p.apolice_id=a.id
            WHERE a.corretora_id=$1 AND p.valor > 0
              AND EXTRACT(YEAR FROM p.vencimento) = $2
              AND a.seguradora IS NOT NULL
            GROUP BY a.seguradora ORDER BY total DESC LIMIT 10
        """, cid, ano)

        # Por ramo
        por_ramo = await conn.fetch("""
            SELECT a.ramo, COUNT(DISTINCT a.id) as apolices,
                   SUM(p.valor) as total
            FROM parcelas p JOIN apolices a ON p.apolice_id=a.id
            WHERE a.corretora_id=$1 AND p.valor > 0
              AND EXTRACT(YEAR FROM p.vencimento) = $2
              AND a.ramo IS NOT NULL
            GROUP BY a.ramo ORDER BY total DESC LIMIT 10
        """, cid, ano)

        # Por produtor
        por_prod = await conn.fetch("""
            SELECT a.produtor as nome, COUNT(DISTINCT a.id) as apolices,
                   SUM(p.valor) as total
            FROM parcelas p JOIN apolices a ON p.apolice_id=a.id
            WHERE a.corretora_id=$1 AND p.valor > 0
              AND EXTRACT(YEAR FROM p.vencimento) = $2
              AND a.produtor IS NOT NULL
            GROUP BY a.produtor ORDER BY total DESC LIMIT 10
        """, cid, ano)

        # Totais
        totais = await conn.fetchrow("""
            SELECT COUNT(*) as parcelas, SUM(p.valor) as total,
                   COUNT(DISTINCT a.id) as apolices,
                   COUNT(DISTINCT a.cliente_id) as clientes
            FROM parcelas p JOIN apolices a ON p.apolice_id=a.id
            WHERE a.corretora_id=$1 AND p.valor > 0
              AND EXTRACT(YEAR FROM p.vencimento) = $2
        """, cid, ano)

    MESES = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']
    return {
        "ano": ano,
        "totais": {
            "parcelas": totais["parcelas"],
            "total": float(totais["total"] or 0),
            "apolices": totais["apolices"],
            "clientes": totais["clientes"],
        },
        "mensal": [{"mes": r["mes"], "nome": MESES[r["mes"]-1], "parcelas": r["parcelas"], "total": float(r["total"])} for r in mensal],
        "seguradoras": [{"nome": _nome_seguradora(r["seguradora"]), "apolices": r["apolices"], "total": float(r["total"])} for r in por_seg],
        "ramos": [{"nome": _nome_ramo(r["ramo"]), "apolices": r["apolices"], "total": float(r["total"])} for r in por_ramo],
        "produtores": [{"nome": r["nome"], "apolices": r["apolices"], "total": float(r["total"])} for r in por_prod],
    }


@router.get("/faturamento-drill")
async def faturamento_drill(
    ano: int = None, mes: int = None,
    seguradora: str = None, ramo: str = None, produtor: str = None,
    user: dict = Depends(get_current_user)
):
    """Drill-down cruzado do faturamento — filtra por qualquer combinação."""
    pool = await database.get_pool()
    cid = user["corretora_id"]

    where = ["a.corretora_id=$1", "p.valor > 0"]
    params = [cid]
    idx = 2

    if ano:
        where.append(f"EXTRACT(YEAR FROM p.vencimento) = ${idx}")
        params.append(ano); idx += 1
    if mes:
        where.append(f"EXTRACT(MONTH FROM p.vencimento) = ${idx}")
        params.append(mes); idx += 1
    if seguradora:
        where.append(f"a.seguradora = ${idx}")
        params.append(seguradora); idx += 1
    if ramo:
        where.append(f"a.ramo = ${idx}")
        params.append(ramo); idx += 1
    if produtor:
        where.append(f"a.produtor = ${idx}")
        params.append(produtor); idx += 1

    w = " AND ".join(where)

    async with pool.acquire() as conn:
        # Totais
        totais = await conn.fetchrow(f"""
            SELECT COUNT(*) as parcelas, COALESCE(SUM(p.valor),0) as total,
                   COUNT(DISTINCT a.id) as apolices,
                   COUNT(DISTINCT a.cliente_id) as clientes
            FROM parcelas p JOIN apolices a ON p.apolice_id=a.id
            WHERE {w}
        """, *params)

        # Agrupamentos disponíveis
        por_mes = await conn.fetch(f"""
            SELECT EXTRACT(MONTH FROM p.vencimento)::int as mes,
                   SUM(p.valor) as total, COUNT(*) as parcelas
            FROM parcelas p JOIN apolices a ON p.apolice_id=a.id
            WHERE {w} GROUP BY mes ORDER BY mes
        """, *params) if ano and not mes else []

        por_seg = await conn.fetch(f"""
            SELECT a.seguradora as nome, SUM(p.valor) as total,
                   COUNT(DISTINCT a.id) as apolices
            FROM parcelas p JOIN apolices a ON p.apolice_id=a.id
            WHERE {w} AND a.seguradora IS NOT NULL
            GROUP BY a.seguradora ORDER BY total DESC LIMIT 15
        """, *params)

        por_ramo = await conn.fetch(f"""
            SELECT a.ramo as nome, SUM(p.valor) as total,
                   COUNT(DISTINCT a.id) as apolices
            FROM parcelas p JOIN apolices a ON p.apolice_id=a.id
            WHERE {w} AND a.ramo IS NOT NULL
            GROUP BY a.ramo ORDER BY total DESC LIMIT 15
        """, *params)

        por_prod = await conn.fetch(f"""
            SELECT a.produtor as nome, SUM(p.valor) as total,
                   COUNT(DISTINCT a.id) as apolices
            FROM parcelas p JOIN apolices a ON p.apolice_id=a.id
            WHERE {w} AND a.produtor IS NOT NULL
            GROUP BY a.produtor ORDER BY total DESC LIMIT 15
        """, *params)

        # Lista de apólices (quando filtrado o suficiente)
        apolices_list = []
        if (ano and mes) or seguradora or ramo:
            rows = await conn.fetch(f"""
                SELECT DISTINCT a.id, a.numero, a.seguradora, a.ramo, a.produtor,
                       a.premio, a.vig_inicio, a.vig_fim, a.status,
                       c.nome as cliente, c.id as cliente_id
                FROM parcelas p JOIN apolices a ON p.apolice_id=a.id
                JOIN clientes c ON a.cliente_id=c.id
                WHERE {w}
                ORDER BY a.premio DESC NULLS LAST
                LIMIT 50
            """, *params)
            apolices_list = [dict(r) for r in rows]
            for ap in apolices_list:
                ap["premio"] = float(ap["premio"] or 0)
                ap["seguradora"] = _nome_seguradora(ap.get("seguradora"))
                ap["ramo"] = _nome_ramo(ap.get("ramo"))
                ap["vig_inicio"] = str(ap["vig_inicio"]) if ap["vig_inicio"] else None
                ap["vig_fim"] = str(ap["vig_fim"]) if ap["vig_fim"] else None

    MESES = ['','Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']
    return {
        "filtros": {"ano": ano, "mes": mes, "seguradora": seguradora, "ramo": ramo, "produtor": produtor},
        "totais": {
            "parcelas": totais["parcelas"],
            "total": float(totais["total"]),
            "apolices": totais["apolices"],
            "clientes": totais["clientes"],
        },
        "mensal": [{"mes": r["mes"], "nome": MESES[r["mes"]], "total": float(r["total"]), "parcelas": r["parcelas"]} for r in por_mes],
        "seguradoras": [{"nome": _nome_seguradora(r["nome"]), "total": float(r["total"]), "apolices": r["apolices"]} for r in por_seg],
        "ramos": [{"nome": _nome_ramo(r["nome"]), "total": float(r["total"]), "apolices": r["apolices"]} for r in por_ramo],
        "produtores": [{"nome": r["nome"], "total": float(r["total"]), "apolices": r["apolices"]} for r in por_prod],
        "apolices": apolices_list,
    }


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

def _nome_ramo(sigla):
    """Converte sigla de ramo pra nome completo."""
    if not sigla:
        return "—"
    return RAMO_NOMES.get(sigla.upper(), sigla)

def _nome_seguradora(sigla):
    """Converte sigla pra nome completo."""
    if not sigla:
        return "—"
    return SEGURADORA_NOMES.get(sigla.upper(), sigla)


@router.get("/seguradoras")
async def seguradoras(user: dict = Depends(get_current_user)):
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT seguradora, COUNT(*) as quantidade,
                   COALESCE(SUM(premio),0) as premio_total
            FROM apolices WHERE corretora_id=$1 AND seguradora IS NOT NULL
            GROUP BY seguradora ORDER BY quantidade DESC LIMIT 15
        """, cid)
    return [{"seguradora": _nome_seguradora(r["seguradora"]), "quantidade": r["quantidade"],
             "premio": float(r["premio_total"])} for r in rows]


@router.get("/ramos")
async def ramos(user: dict = Depends(get_current_user)):
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT COALESCE(ramo, 'N/I') as ramo, COUNT(*) as quantidade,
                   COALESCE(SUM(premio),0) as premio_total
            FROM apolices WHERE corretora_id=$1
            GROUP BY ramo ORDER BY quantidade DESC
        """, cid)
    return [{"ramo": _nome_ramo(r["ramo"]), "quantidade": r["quantidade"],
             "premio": float(r["premio_total"])} for r in rows]


@router.get("/produtores")
async def produtores(user: dict = Depends(get_current_user)):
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT REPLACE(produtor, 'SIER - ', '') as nome,
                   COUNT(*) as quantidade,
                   COALESCE(SUM(premio),0) as premio_total
            FROM apolices WHERE corretora_id=$1 AND produtor IS NOT NULL
            GROUP BY produtor ORDER BY premio_total DESC LIMIT 10
        """, cid)
    return [{"nome": r["nome"], "quantidade": r["quantidade"],
             "premio": float(r["premio_total"])} for r in rows]


@router.get("/parcelas-futuras")
async def parcelas_futuras(user: dict = Depends(get_current_user)):
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT TO_CHAR(p.vencimento, 'YYYY-MM') as mes,
                   COUNT(*) as quantidade,
                   SUM(p.valor) as total
            FROM parcelas p JOIN apolices a ON p.apolice_id=a.id
            WHERE a.corretora_id=$1 AND p.vencimento >= CURRENT_DATE AND p.valor > 0
            GROUP BY mes ORDER BY mes LIMIT 12
        """, cid)
    return [{"mes": r["mes"], "quantidade": r["quantidade"],
             "total": float(r["total"])} for r in rows]


@router.get("/renovacoes-pipeline")
async def renovacoes_pipeline(user: dict = Depends(get_current_user)):
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT TO_CHAR(vigencia_fim, 'YYYY-MM') as mes,
                   COUNT(*) as quantidade,
                   COALESCE(SUM(premio),0) as premio_total
            FROM apolices
            WHERE corretora_id=$1 AND vigencia_fim >= CURRENT_DATE AND status='vigente'
            GROUP BY mes ORDER BY mes LIMIT 12
        """, cid)
    return [{"mes": r["mes"], "quantidade": r["quantidade"],
             "premio": float(r["premio_total"])} for r in rows]


@router.get("/renovacoes-detalhe")
async def renovacoes_detalhe(dias: int = Query(60), status: str = Query("todos"), user: dict = Depends(get_current_user)):
    """Apólices a renovar nos próximos N dias — com nome do cliente e status de renovação"""
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        conditions = ["a.corretora_id=$1", "a.status='vigente'"]
        params = [cid]
        idx = 2

        if dias > 0:
            conditions.append(f"a.vigencia_fim BETWEEN CURRENT_DATE AND CURRENT_DATE + ${idx} * INTERVAL '1 day'")
            params.append(dias)
            idx += 1

        if status != "todos":
            conditions.append(f"a.renovacao_status=${idx}")
            params.append(status)
            idx += 1

        where = " AND ".join(conditions)
        rows = await conn.fetch(f"""
            SELECT a.id as apolice_id, c.id as cliente_id, c.nome, c.cpf_cnpj,
                   c.telefone, c.email,
                   a.seguradora, a.numero_apolice, a.ramo,
                   a.vigencia_fim, a.premio, a.produtor,
                   a.renovacao_status, a.renovacao_obs, a.renovacao_updated_at
            FROM apolices a
            JOIN clientes c ON c.id = a.cliente_id
            WHERE {where}
            ORDER BY a.vigencia_fim ASC
            LIMIT 200
        """, *params)
    return [{
        "apolice_id": r["apolice_id"],
        "cliente_id": r["cliente_id"],
        "cliente": r["nome"],
        "cpf": r["cpf_cnpj"],
        "telefone": r["telefone"],
        "email": r["email"],
        "seguradora": _nome_seguradora(r["seguradora"]),
        "numero": r["numero_apolice"],
        "ramo": _nome_ramo(r["ramo"]),
        "vencimento": r["vigencia_fim"].isoformat() if r["vigencia_fim"] else None,
        "premio": float(r["premio"]) if r["premio"] else 0,
        "produtor": r["produtor"],
        "renovacao_status": r["renovacao_status"] or "pendente",
        "renovacao_obs": r["renovacao_obs"],
        "renovacao_updated_at": r["renovacao_updated_at"].isoformat() if r["renovacao_updated_at"] else None,
    } for r in rows]


@router.get("/renovacoes-stats")
async def renovacoes_stats(dias: int = Query(90), user: dict = Depends(get_current_user)):
    """Stats de renovação por status"""
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT COALESCE(renovacao_status, 'pendente') as status,
                   COUNT(*) as count,
                   COALESCE(SUM(premio), 0) as premio_total
            FROM apolices
            WHERE corretora_id=$1 AND status='vigente'
              AND vigencia_fim BETWEEN CURRENT_DATE AND CURRENT_DATE + $2 * INTERVAL '1 day'
            GROUP BY renovacao_status
        """, cid, dias)
    return {r["status"]: {"count": r["count"], "premio": float(r["premio_total"])} for r in rows}


@router.post("/renovacao-update")
async def renovacao_update(request: Request, user: dict = Depends(get_current_user)):
    """Atualizar status de renovação de uma apólice"""
    body = await request.json()
    apolice_id = body.get("apolice_id")
    new_status = body.get("status")
    obs = body.get("obs", "")

    valid = ["pendente", "contatado", "cotando", "renovado", "perdido", "cancelado"]
    if new_status not in valid:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": f"Status inválido. Use: {valid}"}, status_code=400)

    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE apolices SET renovacao_status=$1, renovacao_obs=$2, renovacao_updated_at=NOW()
            WHERE id=$3 AND corretora_id=$4
        """, new_status, obs, apolice_id, cid)
    return {"ok": True, "updated": result.split()[-1]}


@router.get("/renovacoes-pdf")
async def renovacoes_pdf(dias: int = Query(60), token: str = Query(None)):
    """Gera PDF das renovações para impressão/encaminhamento"""
    from fastapi.responses import Response
    from routers.renovacoes_pdf import generate_renovacoes_pdf
    from auth import get_current_user_from_token
    
    if not token:
        from fastapi import HTTPException
        raise HTTPException(401, "Token required")
    
    user = await get_current_user_from_token(token)
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT a.id as apolice_id, c.id as cliente_id, c.nome, c.cpf_cnpj,
                   a.seguradora, a.numero_apolice, a.ramo,
                   a.vigencia_fim, a.premio, a.produtor, a.renovacao_status
            FROM apolices a
            JOIN clientes c ON c.id = a.cliente_id
            WHERE a.corretora_id=$1 AND a.status='vigente'
              AND a.vigencia_fim BETWEEN CURRENT_DATE AND CURRENT_DATE + $2 * INTERVAL '1 day'
            ORDER BY a.vigencia_fim ASC
        """, cid, dias)
    
    data = [{
        "vencimento": r["vigencia_fim"].isoformat() if r["vigencia_fim"] else None,
        "cliente": r["nome"],
        "cpf": r["cpf_cnpj"],
        "seguradora": _nome_seguradora(r["seguradora"]),
        "ramo": _nome_ramo(r["ramo"]),
        "numero": r["numero_apolice"],
        "produtor": r["produtor"],
        "premio": float(r["premio"]) if r["premio"] else 0,
        "renovacao_status": r["renovacao_status"] or "pendente",
    } for r in rows]
    
    pdf_bytes = generate_renovacoes_pdf(data, dias)
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=renovacoes_sierra_{dias}d.pdf"}
    )


@router.get("/top-clientes")
async def top_clientes(user: dict = Depends(get_current_user)):
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT c.id, c.nome, c.cpf_cnpj, COUNT(a.id) as apolices,
                   COALESCE(SUM(a.premio),0) as premio_total
            FROM clientes c JOIN apolices a ON a.cliente_id=c.id
            WHERE a.corretora_id=$1
            GROUP BY c.id, c.nome, c.cpf_cnpj
            ORDER BY premio_total DESC LIMIT 15
        """, cid)
    return [{"id": r["id"], "nome": r["nome"], "cpf": r["cpf_cnpj"],
             "apolices": r["apolices"], "premio": float(r["premio_total"])} for r in rows]


@router.get("/cliente/{cliente_id}")
async def ficha_cliente(cliente_id: int, user: dict = Depends(get_current_user)):
    """Ficha completa do cliente — dados + apólices + parcelas"""
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        # Client info
        cli = await conn.fetchrow("""
            SELECT id, nome, cpf_cnpj, cidade, uf, cep, telefone, email, nascimento, status, drive_pasta
            FROM clientes WHERE id=$1 AND corretora_id=$2
        """, cliente_id, cid)
        if not cli:
            return {"error": "Cliente não encontrado"}
        
        # Apolices
        apos = await conn.fetch("""
            SELECT id, seguradora, numero_apolice, ramo, vigencia_inicio, vigencia_fim,
                   premio, status, produtor, emissao
            FROM apolices WHERE cliente_id=$1 AND corretora_id=$2
            ORDER BY vigencia_fim DESC NULLS LAST
        """, cliente_id, cid)
        
        apolices_list = []
        for a in apos:
            # Get parcelas for this apolice
            parcs = await conn.fetch("""
                SELECT numero_parcela, vencimento, valor, endosso
                FROM parcelas WHERE apolice_id=$1
                ORDER BY vencimento
            """, a["id"])
            
            apolices_list.append({
                "id": a["id"],
                "seguradora": a["seguradora"],
                "numero": a["numero_apolice"],
                "ramo": a["ramo"],
                "vig_inicio": a["vigencia_inicio"].isoformat() if a["vigencia_inicio"] else None,
                "vig_fim": a["vigencia_fim"].isoformat() if a["vigencia_fim"] else None,
                "premio": float(a["premio"]) if a["premio"] else None,
                "status": a["status"],
                "produtor": a["produtor"],
                "emissao": a["emissao"].isoformat() if a["emissao"] else None,
                "parcelas": [{
                    "num": p["numero_parcela"],
                    "vencimento": p["vencimento"].isoformat() if p["vencimento"] else None,
                    "valor": float(p["valor"]) if p["valor"] else 0,
                    "endosso": p["endosso"],
                } for p in parcs]
            })
        
        return {
            "id": cli["id"],
            "nome": cli["nome"],
            "cpf_cnpj": cli["cpf_cnpj"],
            "cidade": cli["cidade"],
            "uf": cli["uf"],
            "cep": cli["cep"],
            "telefone": cli["telefone"],
            "email": cli["email"],
            "nascimento": cli["nascimento"].isoformat() if cli["nascimento"] else None,
            "status": cli["status"] or "ativo",
            "apolices": apolices_list,
            "total_apolices": len(apolices_list),
            "total_premio": sum(a["premio"] or 0 for a in apolices_list),
            "drive_pasta": cli["drive_pasta"],
        }


@router.get("/busca-clientes")
async def busca_clientes(
    q: str = Query("", min_length=0),
    status: str = Query("todos"),
    ano: int = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=10, le=200),
    order: str = Query("apolices"),
    user: dict = Depends(get_current_user)
):
    """Busca clientes por nome ou CPF, filtro por status/ano, paginado"""
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        conditions = ["c.corretora_id=$1"]
        params = [cid]
        idx = 2
        
        if q and len(q) >= 2:
            conditions.append(f"(c.nome ILIKE ${idx} OR c.cpf_cnpj ILIKE ${idx})")
            params.append(f"%{q}%")
            idx += 1
        
        if status in ("ativo", "inativo"):
            conditions.append(f"c.status=${idx}")
            params.append(status)
            idx += 1

        # Filtro por ano (última vigência)
        ano_join = ""
        ano_having = ""
        if ano:
            if ano == 0:
                # Sem apólice (sem data)
                ano_having = " HAVING MAX(a.vigencia_fim) IS NULL"
            else:
                ano_having = f" HAVING EXTRACT(YEAR FROM MAX(a.vigencia_fim)) = ${idx}"
                params.append(ano)
                idx += 1
        
        where = " AND ".join(conditions)

        # Contagem total (com filtro de ano)
        total_row = await conn.fetchrow(f"""
            SELECT COUNT(*) as total FROM (
                SELECT c.id FROM clientes c
                LEFT JOIN apolices a ON a.cliente_id=c.id
                WHERE {where}
                GROUP BY c.id {ano_having}
            ) sub
        """, *params)
        total = total_row["total"]

        order_clause = "c.nome ASC" if order == "nome" else "COUNT(a.id) DESC"
        offset = (page - 1) * limit

        rows = await conn.fetch(f"""
            SELECT c.id, c.nome, c.cpf_cnpj, c.cidade, c.uf, c.status,
                   c.drive_pasta,
                   COUNT(a.id) as apolices,
                   EXTRACT(YEAR FROM MAX(a.vigencia_fim))::int as ultimo_ano
            FROM clientes c
            LEFT JOIN apolices a ON a.cliente_id=c.id
            WHERE {where}
            GROUP BY c.id
            {ano_having}
            ORDER BY {order_clause}
            LIMIT {limit} OFFSET {offset}
        """, *params)

    return {
        "total": total,
        "page": page,
        "pages": max(1, (total + limit - 1) // limit),
        "items": [{"id": r["id"], "nome": r["nome"], "cpf": r["cpf_cnpj"],
                 "cidade": r["cidade"], "uf": r["uf"], "status": r["status"],
                 "apolices": r["apolices"], "tem_docs": r["drive_pasta"] is not None,
                 "ultimo_ano": r["ultimo_ano"]} for r in rows]
    }


@router.get("/clientes-anos")
async def clientes_anos(status: str = Query("inativo"), user: dict = Depends(get_current_user)):
    """Lista anos disponíveis para filtro de clientes (baseado em última vigência)."""
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        cond = "c.corretora_id=$1"
        params = [cid]
        if status in ("ativo", "inativo"):
            cond += " AND c.status=$2"
            params.append(status)

        rows = await conn.fetch(f"""
            SELECT ultimo_ano, COUNT(*) as total FROM (
                SELECT c.id, EXTRACT(YEAR FROM MAX(a.vigencia_fim))::int as ultimo_ano
                FROM clientes c LEFT JOIN apolices a ON a.cliente_id=c.id
                WHERE {cond}
                GROUP BY c.id
            ) sub
            GROUP BY ultimo_ano ORDER BY ultimo_ano NULLS FIRST
        """, *params)
    return [{"ano": r["ultimo_ano"], "label": str(r["ultimo_ano"]) if r["ultimo_ano"] else "Sem data", "total": r["total"]} for r in rows]


@router.get("/clientes-stats")
async def clientes_stats(user: dict = Depends(get_current_user)):
    """Contagem de clientes por status"""
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT COALESCE(status, 'ativo') as status, COUNT(*) as count
            FROM clientes WHERE corretora_id=$1
            GROUP BY status
        """, cid)
    return {r["status"]: r["count"] for r in rows}
