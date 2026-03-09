"""
Configuração global dos testes Sierra SaaS.
"""

import sys
import pytest
import asyncio

sys.path.insert(0, "/root/sierra")
sys.path.insert(0, "/root/sierra/web")


@pytest.fixture(autouse=True)
async def reset_db_pool():
    """
    Reseta o pool de conexões ANTES de cada teste.
    Evita conflito de event loops com asyncpg.
    """
    import database
    # Fecha pool existente antes do teste
    if database._pool is not None:
        try:
            await database._pool.close()
        except Exception:
            pass
        database._pool = None
    yield
    # Fecha pool após o teste também
    if database._pool is not None:
        try:
            await database._pool.close()
        except Exception:
            pass
        database._pool = None


@pytest.fixture
async def client():
    """Cliente HTTP assíncrono contra a app FastAPI (function-scoped)."""
    from httpx import AsyncClient, ASGITransport
    from web.app import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
