"""
Rotas de Clientes — CRUD, busca, ficha completa.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

import sys
sys.path.insert(0, "/root/sierra")
sys.path.insert(0, "/root/sierra/web")

import database
from auth import get_current_user, require_role

router = APIRouter(prefix="/api/clientes", tags=["clientes"])


class ClienteCreate(BaseModel):
    nome: str
    cpf_cnpj: str
    nascimento: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None
    cep: Optional[str] = None
    endereco: Optional[str] = None


class ClienteUpdate(BaseModel):
    nome: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None
    cep: Optional[str] = None
    endereco: Optional[str] = None


@router.get("/")
async def listar_clientes(
    q: str = Query("", description="Busca por nome, CPF ou placa"),
    page: int = 1,
    limit: int = 20,
    user: dict = Depends(get_current_user)
):
    """Lista clientes com busca."""
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        offset = (page - 1) * limit
        
        if q:
            search = f"%{q}%"
            total = await conn.fetchval(
                """SELECT COUNT(DISTINCT c.id) FROM clientes c
                   LEFT JOIN veiculos v ON v.cliente_id = c.id
                   WHERE c.corretora_id=$1 AND (
                       c.nome ILIKE $2 OR c.cpf_cnpj ILIKE $2 OR v.placa ILIKE $2
                   )""",
                user["corretora_id"], search
            )
            rows = await conn.fetch(
                """SELECT DISTINCT c.*, 
                   (SELECT COUNT(*) FROM cotacoes ct WHERE ct.cliente_id = c.id) as total_cotacoes,
                   (SELECT COUNT(*) FROM apolices ap WHERE ap.cliente_id = c.id AND ap.status = 'vigente') as apolices_vigentes
                   FROM clientes c
                   LEFT JOIN veiculos v ON v.cliente_id = c.id
                   WHERE c.corretora_id=$1 AND (
                       c.nome ILIKE $2 OR c.cpf_cnpj ILIKE $2 OR v.placa ILIKE $2
                   )
                   ORDER BY c.nome
                   LIMIT $3 OFFSET $4""",
                user["corretora_id"], search, limit, offset
            )
        else:
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM clientes WHERE corretora_id=$1",
                user["corretora_id"]
            )
            rows = await conn.fetch(
                """SELECT c.*,
                   (SELECT COUNT(*) FROM cotacoes ct WHERE ct.cliente_id = c.id) as total_cotacoes,
                   (SELECT COUNT(*) FROM apolices ap WHERE ap.cliente_id = c.id AND ap.status = 'vigente') as apolices_vigentes
                   FROM clientes c
                   WHERE c.corretora_id=$1
                   ORDER BY c.nome
                   LIMIT $2 OFFSET $3""",
                user["corretora_id"], limit, offset
            )
        
        clientes = []
        for r in rows:
            clientes.append({
                "id": r["id"],
                "nome": r["nome"],
                "cpf_cnpj": r.get("cpf_cnpj"),
                "telefone": r.get("telefone"),
                "email": r.get("email"),
                "cep": r.get("cep"),
                "total_cotacoes": r.get("total_cotacoes", 0),
                "apolices_vigentes": r.get("apolices_vigentes", 0),
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            })
        
        return {"total": total, "page": page, "clientes": clientes}


@router.get("/{cliente_id}")
async def get_cliente(cliente_id: int, user: dict = Depends(get_current_user)):
    """Ficha completa do cliente."""
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        # Cliente
        cliente = await conn.fetchrow(
            "SELECT * FROM clientes WHERE id=$1 AND corretora_id=$2",
            cliente_id, user["corretora_id"]
        )
        if not cliente:
            raise HTTPException(404, "Cliente não encontrado")
        
        # Veículos
        veiculos = await conn.fetch(
            "SELECT * FROM veiculos WHERE cliente_id=$1 ORDER BY created_at DESC",
            cliente_id
        )
        
        # Cotações
        cotacoes = await conn.fetch(
            """SELECT c.*, u.nome as usuario_nome
               FROM cotacoes c
               LEFT JOIN usuarios u ON c.usuario_id = u.id
               WHERE c.cliente_id=$1
               ORDER BY c.created_at DESC LIMIT 20""",
            cliente_id
        )
        
        # Apólices
        apolices = await conn.fetch(
            "SELECT * FROM apolices WHERE cliente_id=$1 ORDER BY vigencia_fim DESC",
            cliente_id
        )
        
        return {
            "cliente": {
                "id": cliente["id"],
                "nome": cliente["nome"],
                "cpf_cnpj": cliente.get("cpf_cnpj"),
                "nascimento": cliente["nascimento"].isoformat() if cliente.get("nascimento") else None,
                "telefone": cliente.get("telefone"),
                "email": cliente.get("email"),
                "cep": cliente.get("cep"),
                "endereco": cliente.get("endereco"),
                "created_at": cliente["created_at"].isoformat() if cliente.get("created_at") else None,
            },
            "veiculos": [
                {
                    "id": v["id"],
                    "placa": v.get("placa"),
                    "marca_modelo": v.get("marca_modelo"),
                    "ano": f"{v.get('ano_fabricacao', '?')}/{v.get('ano_modelo', '?')}",
                    "cor": v.get("cor"),
                    "combustivel": v.get("combustivel"),
                    "chassi": v.get("chassi"),
                }
                for v in veiculos
            ],
            "cotacoes": [
                {
                    "id": c["id"],
                    "tipo": c["tipo"],
                    "status": c["status"],
                    "usuario": c.get("usuario_nome"),
                    "data": c["created_at"].isoformat() if c.get("created_at") else None,
                }
                for c in cotacoes
            ],
            "apolices": [
                {
                    "id": a["id"],
                    "seguradora": a.get("seguradora"),
                    "numero": a.get("numero_apolice"),
                    "vigencia_inicio": a["vigencia_inicio"].isoformat() if a.get("vigencia_inicio") else None,
                    "vigencia_fim": a["vigencia_fim"].isoformat() if a.get("vigencia_fim") else None,
                    "premio": float(a["premio"]) if a.get("premio") else None,
                    "franquia": float(a["franquia"]) if a.get("franquia") else None,
                    "comissao_percentual": float(a["comissao_percentual"]) if a.get("comissao_percentual") else None,
                    "status": a["status"],
                }
                for a in apolices
            ],
        }


@router.post("/")
async def criar_cliente(req: ClienteCreate, user: dict = Depends(get_current_user)):
    """Cria novo cliente."""
    from datetime import date as dt_date
    nascimento = None
    if req.nascimento:
        try:
            parts = req.nascimento.split("/")
            if len(parts) == 3:
                nascimento = dt_date(int(parts[2]), int(parts[1]), int(parts[0]))
        except:
            pass
    
    cliente_id = await database.upsert_cliente(
        user["corretora_id"], req.nome, req.cpf_cnpj,
        nascimento=nascimento, telefone=req.telefone,
        email=req.email, cep=req.cep, endereco=req.endereco
    )
    return {"id": cliente_id, "message": "Cliente salvo"}


@router.put("/{cliente_id}")
async def atualizar_cliente(
    cliente_id: int,
    req: ClienteUpdate,
    user: dict = Depends(get_current_user)
):
    """Atualiza dados do cliente."""
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        cliente = await conn.fetchrow(
            "SELECT id FROM clientes WHERE id=$1 AND corretora_id=$2",
            cliente_id, user["corretora_id"]
        )
        if not cliente:
            raise HTTPException(404, "Cliente não encontrado")
        
        updates = []
        params = []
        i = 1
        for field in ["nome", "telefone", "email", "cep", "endereco"]:
            val = getattr(req, field, None)
            if val is not None:
                updates.append(f"{field}=${i}")
                params.append(val)
                i += 1
        
        if updates:
            params.append(cliente_id)
            await conn.execute(
                f"UPDATE clientes SET {', '.join(updates)}, updated_at=NOW() WHERE id=${i}",
                *params
            )
    
    return {"message": "Cliente atualizado"}
