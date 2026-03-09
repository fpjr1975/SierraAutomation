"""
Rotas do Dashboard — visão geral da corretora.
"""

from fastapi import APIRouter, Depends

import sys
sys.path.insert(0, "/root/sierra")
sys.path.insert(0, "/root/sierra/web")

import database
from auth import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_stats(user: dict = Depends(get_current_user)):
    """Estatísticas gerais da corretora."""
    stats = await database.dashboard_stats(user["corretora_id"])
    return stats


@router.get("/cotacoes-recentes")
async def get_cotacoes_recentes(user: dict = Depends(get_current_user)):
    """Últimas cotações do mês."""
    cotacoes = await database.get_cotacoes_mes(user["corretora_id"])
    # Serializa pra JSON
    result = []
    # Busca PDFs disponíveis pra cada cotação
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        for c in cotacoes[:20]:
            pdfs = await conn.fetch(
                "SELECT id, seguradora, pdf_path FROM cotacao_resultados WHERE cotacao_id = $1 AND pdf_path IS NOT NULL",
                c["id"]
            )
            pdf_links = [{"id": p["id"], "seguradora": p["seguradora"]} for p in pdfs]
            result.append({
                "id": c["id"],
                "cliente": c.get("cliente_nome", "N/D"),
                "placa": c.get("placa", "N/D"),
                "veiculo": c.get("marca_modelo", "N/D"),
                "tipo": c["tipo"],
                "status": c["status"],
                "data": c["created_at"].isoformat() if c.get("created_at") else None,
                "pdfs": pdf_links,
            })
    return result


@router.get("/renovacoes")
async def get_renovacoes(dias: int = 60, user: dict = Depends(get_current_user)):
    """Apólices que vencem nos próximos X dias."""
    renovacoes = await database.get_renovacoes_proximas(user["corretora_id"], dias)
    result = []
    for r in renovacoes:
        result.append({
            "id": r["id"],
            "cliente": r.get("cliente_nome", "N/D"),
            "telefone": r.get("telefone", ""),
            "placa": r.get("placa", "N/D"),
            "veiculo": r.get("marca_modelo", "N/D"),
            "seguradora": r.get("seguradora", "N/D"),
            "vigencia_fim": r["vigencia_fim"].isoformat() if r.get("vigencia_fim") else None,
            "premio": float(r["premio"]) if r.get("premio") else None,
        })
    return result
