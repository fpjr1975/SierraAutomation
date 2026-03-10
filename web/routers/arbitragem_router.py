"""
Arbitragem de Prêmio — Camada 1 de Inteligência Comercial
Calcula ranking duplo (cliente × corretor) e sweet spot por cotação.
"""
import sys
sys.path.insert(0, "/root/sierra")
sys.path.insert(0, "/root/sierra/web")

from fastapi import APIRouter, Depends, HTTPException
import database
from auth import get_current_user

router = APIRouter(prefix="/api/arbitragem", tags=["arbitragem"])


@router.get("/cotacoes-recentes")
async def cotacoes_recentes(user: dict = Depends(get_current_user)):
    """Retorna as últimas 20 cotações com resultados."""
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT c.id, c.created_at,
                   cl.nome as cliente_nome,
                   v.marca_modelo, v.placa,
                   COUNT(cr.id) as total_resultados
            FROM cotacoes c
            LEFT JOIN clientes cl ON c.cliente_id = cl.id
            LEFT JOIN veiculos v ON c.veiculo_id = v.id
            JOIN cotacao_resultados cr ON cr.cotacao_id = c.id
            WHERE c.corretora_id = $1
              AND cr.premio IS NOT NULL AND cr.premio > 0
            GROUP BY c.id, c.created_at, cl.nome, v.marca_modelo, v.placa
            ORDER BY c.created_at DESC
            LIMIT 20
        """, cid)
    return [
        {
            "id": r["id"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "cliente_nome": r["cliente_nome"] or "—",
            "marca_modelo": r["marca_modelo"] or "—",
            "placa": r["placa"] or "—",
            "total_resultados": r["total_resultados"],
            "label": f"#{r['id']} — {r['cliente_nome'] or '?'} | {r['marca_modelo'] or '?'} ({r['created_at'].strftime('%d/%m/%Y') if r['created_at'] else '?'})"
        }
        for r in rows
    ]


@router.get("/{cotacao_id}")
async def arbitragem(cotacao_id: int, user: dict = Depends(get_current_user)):
    """
    Análise de arbitragem de prêmio para uma cotação.
    Retorna ranking duplo, sweet spot, dispersão e alertas.
    """
    pool = await database.get_pool()
    cid = user["corretora_id"]

    async with pool.acquire() as conn:
        # Verifica que a cotação pertence à corretora
        cotacao = await conn.fetchrow(
            "SELECT id, created_at FROM cotacoes WHERE id=$1 AND corretora_id=$2",
            cotacao_id, cid
        )
        if not cotacao:
            raise HTTPException(status_code=404, detail="Cotação não encontrada")

        rows = await conn.fetch("""
            SELECT seguradora, premio, comissao_percentual, franquia, status, mensagem
            FROM cotacao_resultados
            WHERE cotacao_id = $1 AND premio IS NOT NULL AND premio > 0
            ORDER BY premio ASC
        """, cotacao_id)

    if not rows:
        raise HTTPException(status_code=404, detail="Nenhum resultado com prêmio para esta cotação")

    resultados = []
    for r in rows:
        premio = float(r["premio"])
        comissao_pct = float(r["comissao_percentual"]) if r["comissao_percentual"] else 0.0
        comissao_rs = round(premio * comissao_pct / 100, 2)
        franquia = float(r["franquia"]) if r["franquia"] else None
        resultados.append({
            "seguradora": r["seguradora"],
            "premio": premio,
            "comissao_percentual": comissao_pct,
            "comissao_rs": comissao_rs,
            "franquia": franquia,
        })

    if not resultados:
        raise HTTPException(status_code=404, detail="Sem resultados válidos")

    premios = [r["premio"] for r in resultados]
    comissoes_rs = [r["comissao_rs"] for r in resultados]

    premio_min = min(premios)
    premio_max = max(premios)
    comissao_max_rs = max(comissoes_rs)

    # Dispersão do prêmio
    dispersao = round((premio_max - premio_min) / premio_min * 100, 1) if premio_min > 0 else 0

    # Rankings
    ranking_cliente = sorted(resultados, key=lambda x: x["premio"])
    ranking_corretor = sorted(resultados, key=lambda x: x["comissao_rs"], reverse=True)

    # Identifica tags
    mais_barato = ranking_cliente[0]["seguradora"] if ranking_cliente else None
    melhor_comissao = ranking_corretor[0]["seguradora"] if ranking_corretor else None

    # SWEET SPOT: normaliza prêmio (menor = melhor) e comissão R$ (maior = melhor)
    # Score = 0.5 * (1 - norm_premio) + 0.5 * norm_comissao
    for r in resultados:
        norm_premio = (r["premio"] - premio_min) / (premio_max - premio_min) if (premio_max - premio_min) > 0 else 0
        norm_comissao = (r["comissao_rs"] - min(comissoes_rs)) / (comissao_max_rs - min(comissoes_rs)) \
            if (comissao_max_rs - min(comissoes_rs)) > 0 else 0
        r["_sweet_score"] = round(0.5 * (1 - norm_premio) + 0.5 * norm_comissao, 4)

    sweet_spot = max(resultados, key=lambda x: x["_sweet_score"])
    sweet_spot_seguradora = sweet_spot["seguradora"]

    # Limpa score interno
    for r in resultados:
        del r["_sweet_score"]

    # Adiciona tags
    for r in resultados:
        tags = []
        if r["seguradora"] == mais_barato:
            tags.append("mais_barato")
        if r["seguradora"] == melhor_comissao:
            tags.append("melhor_comissao")
        if r["seguradora"] == sweet_spot_seguradora:
            tags.append("sweet_spot")
        r["tags"] = tags

    # Resumo
    economia_potencial = round(premio_max - premio_min, 2)
    comissao_extra = round(comissao_max_rs - min(comissoes_rs), 2) if len(comissoes_rs) > 1 else 0

    return {
        "cotacao_id": cotacao_id,
        "created_at": cotacao["created_at"].isoformat() if cotacao["created_at"] else None,
        "total_seguradoras": len(resultados),
        "resultados": resultados,
        "ranking_cliente": [r["seguradora"] for r in ranking_cliente],
        "ranking_corretor": [r["seguradora"] for r in ranking_corretor],
        "sweet_spot": sweet_spot_seguradora,
        "dispersao_percentual": dispersao,
        "alerta_dispersao": dispersao > 50,
        "resumo": {
            "premio_min": premio_min,
            "premio_max": premio_max,
            "economia_potencial": economia_potencial,
            "comissao_extra_potencial": comissao_extra,
            "mais_barato": mais_barato,
            "melhor_comissao": melhor_comissao,
            "sweet_spot": sweet_spot_seguradora,
        }
    }
