"""
Sierra SaaS — API Web (FastAPI)
"""

import sys
sys.path.insert(0, "/root/sierra")
sys.path.insert(0, "/root/sierra/web")

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

import logging
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')

import database
from routers.auth_router import router as auth_router
from routers.dashboard_router import router as dashboard_router
from routers.cotacao_router import router as cotacao_router
from routers.clientes_router import router as clientes_router
from routers.pages_router import router as pages_router
from routers.analytics_router import router as analytics_router
from routers.conversor_router import router as conversor_router
from routers.documentos_router import router as documentos_router
from routers.seguranca_router import router as seguranca_router
from routers.apolices_router import router as apolices_router
from routers.gestor_router import router as gestor_router
from routers.arbitragem_router import router as arbitragem_router
from routers.comissoes_router import router as comissoes_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown."""
    await database.get_pool()
    print("🚀 Sierra Web API iniciada")
    yield
    await database.close_pool()
    print("Sierra Web API encerrada")


app = FastAPI(
    title="Sierra SaaS",
    description="API para gestão de corretoras de seguros",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(cotacao_router)
app.include_router(clientes_router)
app.include_router(pages_router)
app.include_router(analytics_router)
app.include_router(conversor_router)
app.include_router(documentos_router)
app.include_router(seguranca_router)
app.include_router(apolices_router)
app.include_router(gestor_router)
app.include_router(arbitragem_router)
app.include_router(comissoes_router)

# Static files
app.mount("/static", StaticFiles(directory="/root/sierra/web/static"), name="static")


def _serve(filename: str):
    with open(f"/root/sierra/web/static/{filename}", "r") as f:
        return HTMLResponse(f.read())


@app.get("/", response_class=HTMLResponse)
async def root():
    return _serve("login.html")


@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page():
    return _serve("dashboard.html")


@app.get("/clientes", response_class=HTMLResponse)
async def clientes_page():
    return _serve("clientes.html")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page():
    return _serve("operacional.html")


@app.get("/conversor", response_class=HTMLResponse)
async def conversor_page():
    return _serve("conversor.html")


@app.get("/analise", response_class=HTMLResponse)
async def analise_page():
    return _serve("analise.html")

@app.get("/seguranca", response_class=HTMLResponse)
async def seguranca_page():
    return _serve("seguranca.html")

@app.get("/renovacoes", response_class=HTMLResponse)
async def renovacoes_page():
    return _serve("renovacoes.html")


@app.get("/apolices", response_class=HTMLResponse)
async def apolices_page():
    return _serve("apolices.html")


@app.get("/gestor", response_class=HTMLResponse)
async def gestor_page():
    return _serve("gestor.html")


@app.get("/arbitragem", response_class=HTMLResponse)
async def arbitragem_page():
    return _serve("arbitragem.html")


@app.get("/comissoes", response_class=HTMLResponse)
async def comissoes_page():
    return _serve("comissoes.html")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "sierra-web"}
