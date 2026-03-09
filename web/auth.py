"""
Autenticação JWT para Sierra Web.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import bcrypt
from pydantic import BaseModel

import sys
sys.path.insert(0, "/root/sierra")
import database

# Config
SECRET_KEY = "sierra-saas-2026-super-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: Optional[int] = None
    corretora_id: Optional[int] = None
    role: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    nome: str
    email: Optional[str]
    role: str
    corretora_id: int


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Extrai usuário do token JWT."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido ou expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        return {
            "id": int(user_id),
            "corretora_id": payload.get("corretora_id"),
            "role": payload.get("role"),
            "nome": payload.get("nome"),
        }
    except JWTError:
        raise credentials_exception


def require_role(*roles):
    """Decorator pra exigir role específico."""
    async def role_checker(user: dict = Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acesso restrito. Roles permitidos: {', '.join(roles)}"
            )
        return user
    return role_checker


async def get_current_user_from_token(token: str) -> dict:
    """Extract user from raw token string (for query param auth)."""
    from fastapi import HTTPException, status
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido ou expirado",
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    pool = await database.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, nome, email, corretora_id, role FROM usuarios WHERE id=$1",
            int(user_id)
        )
    if row is None:
        raise credentials_exception
    return dict(row)
