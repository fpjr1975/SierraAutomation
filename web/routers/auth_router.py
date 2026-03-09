"""
Rotas de autenticação — login, registro, perfil.
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional

import sys
sys.path.insert(0, "/root/sierra")
sys.path.insert(0, "/root/sierra/web")

import database
from auth import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    senha: str


class RegisterRequest(BaseModel):
    nome: str
    email: str
    senha: str
    corretora_id: int = 1


class ChangePasswordRequest(BaseModel):
    senha_atual: str
    nova_senha: str


@router.post("/login")
async def login(req: LoginRequest, request: Request = None):
    """Login com email + senha → JWT."""
    from routers.seguranca_router import check_brute_force, record_attempt, log_action
    
    ip = request.client.host if request else "unknown"
    
    # Brute force check
    await check_brute_force(req.email, ip)
    
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT * FROM usuarios WHERE email=$1 AND active=TRUE",
            req.email
        )
    
    if not user or not user["senha_hash"]:
        await record_attempt(req.email, ip, False)
        raise HTTPException(status_code=401, detail="Email ou senha incorretos")
    
    if not verify_password(req.senha, user["senha_hash"]):
        await record_attempt(req.email, ip, False)
        raise HTTPException(status_code=401, detail="Email ou senha incorretos")
    
    # Login OK
    await record_attempt(req.email, ip, True)
    
    # Atualiza last_login
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE usuarios SET last_login=NOW() WHERE id=$1", user["id"])
    
    await log_action(user["id"], user["nome"], "login", f"Login via {ip}", ip)
    
    token = create_access_token({
        "sub": str(user["id"]),
        "corretora_id": user["corretora_id"],
        "role": user["role"],
        "nome": user["nome"],
    })
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "nome": user["nome"],
            "email": user["email"],
            "role": user["role"],
            "corretora_id": user["corretora_id"],
        }
    }


@router.post("/register")
async def register(req: RegisterRequest):
    """Registra novo usuário (role padrão: corretor)."""
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        # Verifica se email já existe
        existing = await conn.fetchrow(
            "SELECT id FROM usuarios WHERE email=$1", req.email
        )
        if existing:
            raise HTTPException(status_code=400, detail="Email já cadastrado")
        
        # Cria usuário
        user_id = await conn.fetchval(
            """INSERT INTO usuarios (corretora_id, nome, email, senha_hash, role)
               VALUES ($1, $2, $3, $4, 'corretor') RETURNING id""",
            req.corretora_id, req.nome, req.email, hash_password(req.senha)
        )
    
    return {"id": user_id, "message": "Usuário criado com sucesso"}


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Retorna dados do usuário logado."""
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT u.*, c.nome as corretora_nome
               FROM usuarios u
               LEFT JOIN corretoras c ON u.corretora_id = c.id
               WHERE u.id=$1""",
            user["id"]
        )
    
    if not row:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    return {
        "id": row["id"],
        "nome": row["nome"],
        "email": row["email"],
        "role": row["role"],
        "corretora_id": row["corretora_id"],
        "corretora_nome": row["corretora_nome"],
        "telegram_id": row["telegram_id"],
        "last_login": row["last_login"],
    }


@router.post("/setup-password")
async def setup_password(req: LoginRequest):
    """Define senha pra usuário existente (primeiro acesso)."""
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id FROM usuarios WHERE email=$1 AND active=TRUE AND senha_hash IS NULL",
            req.email
        )
        if not user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado ou já tem senha")
        
        await conn.execute(
            "UPDATE usuarios SET senha_hash=$1, email=$2 WHERE id=$3",
            hash_password(req.senha), req.email, user["id"]
        )
    
    return {"message": "Senha definida com sucesso. Faça login."}
