"""
Documentos API — arquivos do Google Drive vinculados a clientes
"""
import os
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
import sys
sys.path.insert(0, "/root/sierra")
sys.path.insert(0, "/root/sierra/web")
import database
from auth import get_current_user, get_current_user_from_token

router = APIRouter(prefix="/api/documentos", tags=["documentos"])

DRIVE_DIR = "/root/sierra/drive_docs"


@router.get("/cliente/{cliente_id}")
async def listar_documentos(cliente_id: int, user: dict = Depends(get_current_user)):
    """Lista documentos de um cliente (arquivos da pasta do Drive)"""
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT drive_pasta FROM clientes WHERE id=$1 AND corretora_id=$2",
            cliente_id, cid
        )
    
    if not row or not row["drive_pasta"]:
        return {"docs": [], "pasta": None}
    
    pasta = row["drive_pasta"]
    folder_path = os.path.join(DRIVE_DIR, pasta)
    
    if not os.path.isdir(folder_path):
        return {"docs": [], "pasta": pasta}
    
    docs = []
    for fname in sorted(os.listdir(folder_path)):
        fpath = os.path.join(folder_path, fname)
        if os.path.isfile(fpath):
            ext = os.path.splitext(fname)[1].lower()
            size = os.path.getsize(fpath)
            docs.append({
                "nome": fname,
                "ext": ext,
                "tamanho": size,
                "tipo": _tipo_doc(fname, ext),
                "icone": _icone(ext),
            })
    
    return {"docs": docs, "pasta": pasta}


@router.get("/download/{cliente_id}/{filename}")
async def download_documento(cliente_id: int, filename: str, token: str = Query(None)):
    """Download de um documento específico (auth via query param token)"""
    if not token:
        raise HTTPException(401, "Token necessário")
    user = await get_current_user_from_token(token)
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT drive_pasta FROM clientes WHERE id=$1 AND corretora_id=$2",
            cliente_id, cid
        )
    
    if not row or not row["drive_pasta"]:
        raise HTTPException(404, "Cliente sem documentos")
    
    fpath = os.path.join(DRIVE_DIR, row["drive_pasta"], filename)
    
    # Security: prevent path traversal
    real = os.path.realpath(fpath)
    if not real.startswith(os.path.realpath(DRIVE_DIR)):
        raise HTTPException(403, "Acesso negado")
    
    if not os.path.isfile(fpath):
        raise HTTPException(404, "Arquivo não encontrado")
    
    return FileResponse(
        fpath,
        filename=filename,
        media_type="application/octet-stream"
    )


def _tipo_doc(nome: str, ext: str) -> str:
    nome_up = nome.upper()
    if "BOLETO" in nome_up:
        return "Boleto"
    if "APOLICE" in nome_up or "APÓLICE" in nome_up:
        return "Apólice"
    if "CARTA VERDE" in nome_up:
        return "Carta Verde"
    if "PROPOSTA" in nome_up:
        return "Proposta"
    if "ENDOSSO" in nome_up:
        return "Endosso"
    if "CNH" in nome_up:
        return "CNH"
    if "CRVL" in nome_up or "CRV" in nome_up:
        return "CRVL"
    if "SINISTRO" in nome_up:
        return "Sinistro"
    if ext == ".pdf":
        return "PDF"
    if ext in (".jpg", ".jpeg", ".png"):
        return "Imagem"
    return "Arquivo"


def _icone(ext: str) -> str:
    if ext == ".pdf":
        return "📄"
    if ext in (".jpg", ".jpeg", ".png", ".gif"):
        return "🖼️"
    if ext in (".doc", ".docx"):
        return "📝"
    if ext in (".xls", ".xlsx"):
        return "📊"
    return "📎"
