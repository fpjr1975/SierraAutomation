"""
Router do Gastón — Conselheiro de Gestão IA (admin only)
"""
import sys
sys.path.insert(0, "/root/sierra")

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routers.auth_router import get_current_user
import gaston_engine

router = APIRouter(prefix="/api/gestor", tags=["gestor"])


class GestorMessage(BaseModel):
    message: str


class GestorResponse(BaseModel):
    response: str
    user_name: str


def _require_admin(user: dict = Depends(get_current_user)):
    """Só admin pode usar o Gastón."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")
    return user


@router.post("/chat", response_model=GestorResponse)
async def gestor_chat(msg: GestorMessage, user: dict = Depends(_require_admin)):
    """Envia mensagem pro Gastón e retorna resposta."""
    user_id = user["id"]
    user_name = user.get("nome", "Usuário")
    
    response = await gaston_engine.chat(user_id, user_name, msg.message)
    
    return GestorResponse(response=response, user_name=user_name)


@router.post("/clear")
async def gestor_clear(user: dict = Depends(_require_admin)):
    """Limpa histórico de conversa."""
    gaston_engine.clear_history(user["id"])
    return {"ok": True, "message": "Histórico limpo"}


@router.get("/history")
async def gestor_history(user: dict = Depends(_require_admin)):
    """Retorna histórico de mensagens."""
    memory = gaston_engine._load_user_memory(user["id"])
    messages = []
    for msg in memory.get("messages", [])[-50:]:
        messages.append({
            "role": msg["role"],
            "content": msg["content"],
            "timestamp": msg.get("timestamp", "")
        })
    return {"messages": messages}
