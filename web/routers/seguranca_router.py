"""
Rotas de segurança — gestão de usuários, audit log, brute force protection.
"""

from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta

import sys
sys.path.insert(0, "/root/sierra")
sys.path.insert(0, "/root/sierra/web")

import database
from auth import hash_password, verify_password, get_current_user, require_role

router = APIRouter(prefix="/api/seguranca", tags=["seguranca"])

# ═══ MODELS ═══

class UserCreate(BaseModel):
    nome: str
    email: str
    senha: str
    role: str = "corretor"
    telefone: Optional[str] = None
    telegram_id: Optional[int] = None

class UserUpdate(BaseModel):
    nome: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    telefone: Optional[str] = None
    telegram_id: Optional[int] = None
    active: Optional[bool] = None

class PasswordChange(BaseModel):
    senha_atual: str
    nova_senha: str

class PasswordReset(BaseModel):
    user_id: int
    nova_senha: str


# ═══ AUDIT HELPER ═══

async def log_action(user_id: int, user_nome: str, action: str, detail: str, ip: str = None):
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO audit_log (user_id, user_nome, action, detail, ip) VALUES ($1,$2,$3,$4,$5)",
            user_id, user_nome, action, detail, ip
        )


# ═══ BRUTE FORCE ═══

MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

async def check_brute_force(email: str, ip: str):
    """Verifica se email ou IP estão bloqueados."""
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        cutoff = datetime.utcnow() - timedelta(minutes=LOCKOUT_MINUTES)
        
        # Por email
        email_attempts = await conn.fetchval(
            "SELECT COUNT(*) FROM login_attempts WHERE email=$1 AND success=FALSE AND created_at>$2",
            email, cutoff
        )
        
        # Por IP
        ip_attempts = await conn.fetchval(
            "SELECT COUNT(*) FROM login_attempts WHERE ip=$1 AND success=FALSE AND created_at>$2",
            ip, cutoff
        )
        
        if email_attempts >= MAX_ATTEMPTS:
            raise HTTPException(status_code=429, detail=f"Muitas tentativas. Tente novamente em {LOCKOUT_MINUTES} minutos.")
        if ip_attempts >= (MAX_ATTEMPTS * 3):
            raise HTTPException(status_code=429, detail="IP temporariamente bloqueado por muitas tentativas.")


async def record_attempt(email: str, ip: str, success: bool):
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO login_attempts (email, ip, success) VALUES ($1,$2,$3)",
            email, ip, success
        )
        # Limpar tentativas antigas (>24h)
        await conn.execute(
            "DELETE FROM login_attempts WHERE created_at < NOW() - INTERVAL '24 hours'"
        )


# ═══ GESTÃO DE USUÁRIOS ═══

@router.get("/usuarios")
async def listar_usuarios(user: dict = Depends(require_role("admin"))):
    """Lista todos os usuários da corretora."""
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, nome, email, role, telefone, telegram_id, active, 
                   created_at, last_login
            FROM usuarios WHERE corretora_id=$1
            ORDER BY active DESC, nome ASC
        """, cid)
    return [dict(r) for r in rows]


@router.post("/usuarios")
async def criar_usuario(req: UserCreate, request: Request, user: dict = Depends(require_role("admin"))):
    """Cria novo usuário (admin only)."""
    valid_roles = ["admin", "gestor", "corretor", "operacional"]
    if req.role not in valid_roles:
        raise HTTPException(400, f"Role inválido. Opções: {', '.join(valid_roles)}")
    
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM usuarios WHERE email=$1", req.email)
        if existing:
            raise HTTPException(400, "Email já cadastrado")
        
        user_id = await conn.fetchval("""
            INSERT INTO usuarios (corretora_id, nome, email, senha_hash, role, telefone, telegram_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id
        """, cid, req.nome, req.email, hash_password(req.senha), req.role, req.telefone, req.telegram_id)
    
    await log_action(user["id"], user["nome"], "user_create", 
                     f"Criou usuário {req.nome} ({req.email}) role={req.role}", 
                     request.client.host)
    return {"id": user_id, "message": f"Usuário {req.nome} criado com sucesso"}


@router.put("/usuarios/{user_id}")
async def atualizar_usuario(user_id: int, req: UserUpdate, request: Request, user: dict = Depends(require_role("admin"))):
    """Atualiza dados de um usuário (admin only)."""
    valid_roles = ["admin", "gestor", "corretor", "operacional"]
    if req.role and req.role not in valid_roles:
        raise HTTPException(400, f"Role inválido. Opções: {', '.join(valid_roles)}")
    
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        target = await conn.fetchrow("SELECT * FROM usuarios WHERE id=$1 AND corretora_id=$2", user_id, user["corretora_id"])
        if not target:
            raise HTTPException(404, "Usuário não encontrado")
        
        updates = []
        params = []
        idx = 1
        
        for field in ["nome", "email", "role", "telefone", "telegram_id", "active"]:
            val = getattr(req, field, None)
            if val is not None:
                updates.append(f"{field}=${idx}")
                params.append(val)
                idx += 1
        
        if not updates:
            raise HTTPException(400, "Nenhum campo para atualizar")
        
        params.append(user_id)
        await conn.execute(f"UPDATE usuarios SET {','.join(updates)} WHERE id=${idx}", *params)
    
    changes = {k: v for k, v in req.dict().items() if v is not None}
    await log_action(user["id"], user["nome"], "user_update",
                     f"Atualizou usuário #{user_id}: {changes}",
                     request.client.host)
    return {"message": "Usuário atualizado"}


@router.post("/usuarios/{user_id}/reset-senha")
async def reset_senha(user_id: int, req: PasswordReset, request: Request, user: dict = Depends(require_role("admin"))):
    """Reset de senha pelo admin."""
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        target = await conn.fetchrow("SELECT nome FROM usuarios WHERE id=$1 AND corretora_id=$2", user_id, user["corretora_id"])
        if not target:
            raise HTTPException(404, "Usuário não encontrado")
        
        await conn.execute("UPDATE usuarios SET senha_hash=$1 WHERE id=$2", hash_password(req.nova_senha), user_id)
    
    await log_action(user["id"], user["nome"], "password_reset",
                     f"Resetou senha do usuário #{user_id} ({target['nome']})",
                     request.client.host)
    return {"message": "Senha resetada com sucesso"}


@router.post("/trocar-senha")
async def trocar_senha(req: PasswordChange, request: Request, user: dict = Depends(get_current_user)):
    """Troca própria senha (qualquer usuário logado)."""
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT senha_hash FROM usuarios WHERE id=$1", user["id"])
        if not row or not verify_password(req.senha_atual, row["senha_hash"]):
            raise HTTPException(400, "Senha atual incorreta")
        
        if len(req.nova_senha) < 6:
            raise HTTPException(400, "Nova senha deve ter pelo menos 6 caracteres")
        
        await conn.execute("UPDATE usuarios SET senha_hash=$1 WHERE id=$2", hash_password(req.nova_senha), user["id"])
    
    await log_action(user["id"], user["nome"], "password_change", "Trocou própria senha", request.client.host)
    return {"message": "Senha alterada com sucesso"}


# ═══ AUDIT LOG ═══

@router.get("/audit")
async def audit_log(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=10, le=200),
    action: str = Query(None),
    user_id_filter: int = Query(None),
    user: dict = Depends(require_role("admin"))
):
    """Consulta audit log (admin only)."""
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        conditions = ["1=1"]
        params = []
        idx = 1
        
        if action:
            conditions.append(f"action=${idx}")
            params.append(action)
            idx += 1
        
        if user_id_filter:
            conditions.append(f"user_id=${idx}")
            params.append(user_id_filter)
            idx += 1
        
        where = " AND ".join(conditions)
        
        total = await conn.fetchval(f"SELECT COUNT(*) FROM audit_log WHERE {where}", *params)
        
        offset = (page - 1) * limit
        rows = await conn.fetch(f"""
            SELECT id, user_id, user_nome, action, detail, ip, created_at
            FROM audit_log WHERE {where}
            ORDER BY created_at DESC
            LIMIT {limit} OFFSET {offset}
        """, *params)
    
    return {
        "total": total,
        "page": page,
        "pages": max(1, (total + limit - 1) // limit),
        "items": [dict(r) for r in rows]
    }


@router.get("/audit/actions")
async def audit_actions(user: dict = Depends(require_role("admin"))):
    """Lista tipos de ação do audit log."""
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT DISTINCT action, COUNT(*) as total FROM audit_log GROUP BY action ORDER BY total DESC")
    return [dict(r) for r in rows]


# ═══ LOGIN ATTEMPTS ═══

@router.get("/tentativas")
async def login_attempts(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=10, le=100),
    user: dict = Depends(require_role("admin"))
):
    """Lista tentativas de login recentes (admin only)."""
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM login_attempts WHERE created_at > NOW() - INTERVAL '7 days'")
        offset = (page - 1) * limit
        rows = await conn.fetch(f"""
            SELECT id, email, ip, success, created_at
            FROM login_attempts
            WHERE created_at > NOW() - INTERVAL '7 days'
            ORDER BY created_at DESC
            LIMIT {limit} OFFSET {offset}
        """)
    
    return {
        "total": total,
        "page": page,
        "pages": max(1, (total + limit - 1) // limit),
        "items": [dict(r) for r in rows]
    }


# ═══ STATS ═══

@router.get("/stats")
async def security_stats(user: dict = Depends(require_role("admin"))):
    """Resumo de segurança."""
    pool = await database.get_pool()
    cid = user["corretora_id"]
    async with pool.acquire() as conn:
        users_total = await conn.fetchval("SELECT COUNT(*) FROM usuarios WHERE corretora_id=$1", cid)
        users_active = await conn.fetchval("SELECT COUNT(*) FROM usuarios WHERE corretora_id=$1 AND active=TRUE", cid)
        
        login_24h = await conn.fetchval("SELECT COUNT(*) FROM login_attempts WHERE created_at > NOW() - INTERVAL '24 hours'")
        login_fail_24h = await conn.fetchval("SELECT COUNT(*) FROM login_attempts WHERE success=FALSE AND created_at > NOW() - INTERVAL '24 hours'")
        
        audit_24h = await conn.fetchval("SELECT COUNT(*) FROM audit_log WHERE created_at > NOW() - INTERVAL '24 hours'")
        
        last_login = await conn.fetch("""
            SELECT nome, last_login FROM usuarios 
            WHERE corretora_id=$1 AND last_login IS NOT NULL 
            ORDER BY last_login DESC LIMIT 5
        """, cid)
    
    return {
        "usuarios": {"total": users_total, "ativos": users_active},
        "login_24h": {"total": login_24h, "falhas": login_fail_24h},
        "audit_24h": audit_24h,
        "ultimos_logins": [{"nome": r["nome"], "last_login": r["last_login"]} for r in last_login]
    }
