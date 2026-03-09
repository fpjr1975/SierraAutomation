"""
Rotas de cotação — upload, OCR, cálculo, resultados.
"""

import os
import sys
import json
import uuid
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel

sys.path.insert(0, "/root/sierra")
sys.path.insert(0, "/root/sierra/web")

import database
from auth import get_current_user
from ocr_docs import extract_document_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cotacoes", tags=["cotacoes"])

# Sessões de cotação em andamento (in-memory, por usuário)
_cotacao_sessions = {}

UPLOAD_DIR = "/root/sierra/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


class CotacaoStatus(BaseModel):
    id: str
    status: str  # collecting, ready, calculating, done, error
    cnh: Optional[dict] = None
    crvl: Optional[dict] = None
    cep_pernoite: Optional[str] = None
    endereco_pernoite: Optional[str] = None
    faltam: list = []
    resultados: list = []
    erro: Optional[str] = None


def _session_key(user_id: int) -> str:
    return f"user_{user_id}"


def _o_que_falta(session: dict) -> list:
    faltam = []
    if not session.get("cnh"):
        faltam.append("CNH")
    if not session.get("crvl"):
        faltam.append("CRVL")
    if not session.get("cep_pernoite"):
        faltam.append("CEP de pernoite")
    return faltam


@router.post("/nova")
async def iniciar_cotacao(user: dict = Depends(get_current_user)):
    """Inicia nova sessão de cotação."""
    session_id = str(uuid.uuid4())[:8]
    key = _session_key(user["id"])
    _cotacao_sessions[key] = {
        "id": session_id,
        "user_id": user["id"],
        "corretora_id": user["corretora_id"],
        "status": "collecting",
        "cnh": None,
        "crvl": None,
        "cep_pernoite": None,
        "endereco_pernoite": None,
        "resultados": [],
        "erro": None,
        "created_at": datetime.utcnow().isoformat(),
    }
    return {"id": session_id, "status": "collecting", "faltam": ["CNH", "CRVL", "CEP de pernoite"]}


@router.post("/upload-cnh")
async def upload_cnh(
    file: UploadFile = File(...),
    condutor: Optional[str] = Form(None),
    user: dict = Depends(get_current_user)
):
    """Upload e OCR da CNH (segurado ou condutor)."""
    key = _session_key(user["id"])
    session = _cotacao_sessions.get(key)
    if not session:
        raise HTTPException(400, "Nenhuma cotação em andamento. Use POST /api/cotacoes/nova primeiro.")

    is_condutor = condutor == 'true'
    label = "cnh_condutor" if is_condutor else "cnh"
    
    # Salva arquivo
    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    filepath = os.path.join(UPLOAD_DIR, f"{label}_{session['id']}.{ext}")
    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    # OCR
    try:
        logger.info(f"OCR {label}: processando {filepath} ({os.path.getsize(filepath)} bytes)")
        cnh_data = await asyncio.to_thread(extract_document_data, filepath)
        logger.info(f"OCR {label}: resultado = {list(cnh_data.keys()) if cnh_data else 'None'}")
        if not cnh_data or not cnh_data.get("nome"):
            raise ValueError("Não consegui extrair dados da CNH")
        session[label] = cnh_data
        faltam = _o_que_falta(session)
        if not faltam:
            session["status"] = "ready"
        return {"ok": True, "cnh": cnh_data, "faltam": faltam, "status": session["status"]}
    except Exception as e:
        logger.error(f"Erro OCR CNH: {e}")
        raise HTTPException(422, f"Erro ao processar CNH: {str(e)}")


@router.post("/upload-crvl")
async def upload_crvl(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    """Upload e OCR do CRVL."""
    key = _session_key(user["id"])
    session = _cotacao_sessions.get(key)
    if not session:
        raise HTTPException(400, "Nenhuma cotação em andamento. Use POST /api/cotacoes/nova primeiro.")

    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    filepath = os.path.join(UPLOAD_DIR, f"crvl_{session['id']}.{ext}")
    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    try:
        crvl_data = await asyncio.to_thread(extract_document_data, filepath)
        if not crvl_data or not crvl_data.get("placa"):
            raise ValueError("Não consegui extrair dados do CRVL")
        session["crvl"] = crvl_data
        faltam = _o_que_falta(session)
        if not faltam:
            session["status"] = "ready"
        return {"ok": True, "crvl": crvl_data, "faltam": faltam, "status": session["status"]}
    except Exception as e:
        logger.error(f"Erro OCR CRVL: {e}")
        raise HTTPException(422, f"Erro ao processar CRVL: {str(e)}")


class CepRequest(BaseModel):
    cep: str

@router.post("/cep")
async def set_cep(
    data: CepRequest,
    user: dict = Depends(get_current_user)
):
    """Define CEP de pernoite."""
    import re
    key = _session_key(user["id"])
    session = _cotacao_sessions.get(key)
    if not session:
        raise HTTPException(400, "Nenhuma cotação em andamento.")

    cep_limpo = re.sub(r"[^0-9]", "", data.cep)
    if len(cep_limpo) != 8:
        raise HTTPException(422, "CEP inválido — precisa ter 8 dígitos")

    # Busca endereço via ViaCEP
    endereco = ""
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"https://viacep.com.br/ws/{cep_limpo}/json/", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if not data.get("erro"):
                    endereco = f"{data.get('logradouro', '')}, {data.get('bairro', '')}, {data.get('localidade', '')}/{data.get('uf', '')}"
    except:
        pass

    session["cep_pernoite"] = cep_limpo
    session["endereco_pernoite"] = endereco
    faltam = _o_que_falta(session)
    if not faltam:
        session["status"] = "ready"

    return {"ok": True, "cep": cep_limpo, "endereco": endereco, "faltam": faltam, "status": session["status"]}


@router.get("/status")
async def cotacao_status(user: dict = Depends(get_current_user)):
    """Status da cotação em andamento."""
    key = _session_key(user["id"])
    session = _cotacao_sessions.get(key)
    if not session:
        return {"status": "none", "message": "Nenhuma cotação em andamento"}

    return {
        "id": session["id"],
        "status": session["status"],
        "cnh": session.get("cnh"),
        "crvl": session.get("crvl"),
        "cep_pernoite": session.get("cep_pernoite"),
        "endereco_pernoite": session.get("endereco_pernoite"),
        "faltam": _o_que_falta(session),
        "resultados": session.get("resultados", []),
        "erro": session.get("erro"),
        "message": session.get("message", ""),
    }


@router.post("/calcular")
async def calcular_cotacao_endpoint(
    user: dict = Depends(get_current_user)
):
    """Dispara cálculo no Agilizador (background task)."""
    key = _session_key(user["id"])
    session = _cotacao_sessions.get(key)
    if not session:
        raise HTTPException(400, "Nenhuma cotação em andamento.")
    if session["status"] not in ("ready", "error", "done", "calculating"):
        faltam = _o_que_falta(session)
        raise HTTPException(400, f"Dados incompletos. Faltam: {', '.join(faltam)}")
    if session["status"] == "calculating":
        return {"status": "calculating", "message": session.get("message", "Já calculando...")}
    # Permite recalcular se erro ou done
    if _o_que_falta(session):
        faltam = _o_que_falta(session)
        raise HTTPException(400, f"Dados incompletos. Faltam: {', '.join(faltam)}")

    session["status"] = "calculating"
    session["message"] = "Iniciando cálculo..."
    task = asyncio.create_task(_run_agilizador(key, user))
    task.add_done_callback(lambda t: logger.error(f"Task agilizador falhou: {t.exception()}") if t.exception() else None)

    return {"status": "calculating", "message": "Calculando... isso leva ~30-60 segundos."}


async def _run_agilizador(session_key: str, user: dict):
    """Executa automação do Agilizador em background."""
    session = _cotacao_sessions.get(session_key)
    if not session:
        return

    try:
        from agilizador import calcular_cotacao

        cnh = session["cnh"]
        crvl = session["crvl"]
        cep = session["cep_pernoite"]
        cnh_condutor = session.get("cnh_condutor")

        # Monta dados no formato do calcular_cotacao
        session_data = {
            "cnh": cnh,
            "crvl": crvl,
            "cep": cep,
            "cnh_condutor": cnh_condutor,
        }

        async def update_status(msg, screenshot=None):
            session["message"] = msg
            if screenshot:
                # Salva screenshot pra visualização em tempo real
                ss_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "debug_live.jpg")
                with open(ss_path, "wb") as f:
                    f.write(screenshot)

        resultado = await calcular_cotacao(session_data, on_progress=update_status, chat_id=user["id"])
        resultados = resultado.get("resultados", []) if resultado.get("sucesso") else []

        session["resultados"] = resultados if resultados else []
        session["status"] = "done"
        session["cotacao_uuid"] = resultado.get("cotacao_uuid")
        session["resultados_url"] = resultado.get("url", "")

        # Salva _premio_map na browser_session (igual ao bot Telegram)
        # Necessário pra selecionar o plano correto (Compreensiva) na hora de gerar PDF
        try:
            from agilizador import _browser_sessions
            bs = _browser_sessions.get(user["id"], {})
            if bs and resultados:
                _premio_map = {}
                for r in resultados:
                    seg = r.get("seguradora", "")
                    premio = r.get("premio", "")
                    if seg and premio:
                        try:
                            pf = float(premio.replace("R$", "").replace(".", "").replace(",", ".").strip())
                            _premio_map[seg.lower()] = pf
                        except:
                            pass
                bs['_premio_map'] = _premio_map
                logger.info(f"_premio_map salvo: {_premio_map}")
        except Exception as pm_err:
            logger.warning(f"Erro ao salvar _premio_map: {pm_err}")

        # Salva no banco
        try:
            # Upsert cliente
            cliente_id = await database.upsert_cliente(
                session["corretora_id"],
                cnh.get("nome", ""),
                cnh.get("cpf", ""),
                nascimento=_parse_date(cnh.get("nascimento")),
            )

            # Upsert veículo
            veiculo_id = await database.upsert_veiculo(
                cliente_id,
                crvl.get("placa", ""),
                chassi=crvl.get("chassi"),
                marca_modelo=crvl.get("modelo"),
                ano_fabricacao=crvl.get("ano_fabricacao"),
                ano_modelo=crvl.get("ano_modelo"),
                cor=crvl.get("cor"),
                combustivel=crvl.get("combustivel"),
                cep_pernoite=cep,
            )

            # Busca usuario_id
            db_user = await database.get_usuario_by_telegram(None)  # web user
            usuario_id = session.get("user_id", 1)

            # Insere cotação
            cotacao_id = await database.inserir_cotacao(
                session["corretora_id"],
                usuario_id,
                cliente_id,
                veiculo_id,
                "nova",
                cnh,
                crvl,
                cep,
            )

            # Insere resultados
            if resultados:
                await database.inserir_resultados(cotacao_id, resultados)

            logger.info(f"Cotação {cotacao_id} salva no banco ({len(resultados)} resultados)")
        except Exception as db_err:
            logger.error(f"Erro ao salvar no banco: {db_err}")

    except Exception as e:
        logger.error(f"Erro Agilizador: {e}")
        session["status"] = "error"
        session["erro"] = str(e)


def _parse_date(date_str: str):
    """Converte DD/MM/YYYY pra date."""
    if not date_str:
        return None
    try:
        from datetime import date
        parts = date_str.split("/")
        if len(parts) == 3:
            return date(int(parts[2]), int(parts[1]), int(parts[0]))
    except:
        pass
    return None


@router.get("/historico")
async def listar_cotacoes(
    page: int = 1,
    limit: int = 20,
    user: dict = Depends(get_current_user)
):
    """Lista histórico de cotações da corretora."""
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        offset = (page - 1) * limit
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM cotacoes WHERE corretora_id=$1",
            user["corretora_id"]
        )
        rows = await conn.fetch(
            """SELECT c.id, c.tipo, c.status, c.cep_pernoite, c.created_at,
                      cl.nome as cliente_nome, cl.cpf_cnpj,
                      v.placa, v.marca_modelo
               FROM cotacoes c
               LEFT JOIN clientes cl ON c.cliente_id = cl.id
               LEFT JOIN veiculos v ON c.veiculo_id = v.id
               WHERE c.corretora_id=$1
               ORDER BY c.created_at DESC
               LIMIT $2 OFFSET $3""",
            user["corretora_id"], limit, offset
        )
        cotacoes = []
        for r in rows:
            cotacoes.append({
                "id": r["id"],
                "tipo": r["tipo"],
                "status": r["status"],
                "cliente": r.get("cliente_nome"),
                "cpf": r.get("cpf_cnpj"),
                "placa": r.get("placa"),
                "veiculo": r.get("marca_modelo"),
                "cep": r.get("cep_pernoite"),
                "data": r["created_at"].isoformat() if r.get("created_at") else None,
            })
        return {"total": total, "page": page, "cotacoes": cotacoes}


@router.get("/{cotacao_id}/resultados")
async def get_resultados(cotacao_id: int, user: dict = Depends(get_current_user)):
    """Resultados de uma cotação específica."""
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        # Verifica se cotação pertence à corretora
        cotacao = await conn.fetchrow(
            "SELECT * FROM cotacoes WHERE id=$1 AND corretora_id=$2",
            cotacao_id, user["corretora_id"]
        )
        if not cotacao:
            raise HTTPException(404, "Cotação não encontrada")

        rows = await conn.fetch(
            """SELECT * FROM cotacao_resultados
               WHERE cotacao_id=$1
               ORDER BY CASE WHEN premio IS NOT NULL THEN 0 ELSE 1 END, premio ASC""",
            cotacao_id
        )
        return {
            "cotacao_id": cotacao_id,
            "resultados": [
                {
                    "id": r["id"],
                    "seguradora": r["seguradora"],
                    "premio": float(r["premio"]) if r["premio"] else None,
                    "franquia": float(r["franquia"]) if r["franquia"] else None,
                    "parcelas": r.get("parcelas"),
                    "numero": r.get("numero_cotacao"),
                    "mensagem": r.get("mensagem"),
                    "status": r["status"],
                    "pdf_disponivel": bool(r.get("pdf_path")),
                }
                for r in rows
            ]
        }


async def _save_pdf_to_db(session: dict, seguradora: str, pdf_path: str, filename: str):
    """Copia PDF pra pasta permanente e salva path no cotacao_resultados."""
    import shutil
    try:
        cotacao_id = session.get("cotacao_id")
        if not cotacao_id:
            return
        
        # Pasta permanente por cotação
        perm_dir = f"/root/sierra/cotacao_pdfs/{cotacao_id}"
        os.makedirs(perm_dir, exist_ok=True)
        perm_path = f"{perm_dir}/{filename}"
        
        if pdf_path != perm_path:
            shutil.copy2(pdf_path, perm_path)
        
        # Atualiza no banco
        pool = await database.get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """UPDATE cotacao_resultados SET pdf_path = $1 
                   WHERE cotacao_id = $2 AND LOWER(seguradora) = LOWER($3)""",
                perm_path, cotacao_id, seguradora
            )
        logger.info(f"PDF salvo: {perm_path}")
    except Exception as e:
        logger.error(f"Erro salvando PDF: {e}")


@router.get("/pdf/{resultado_id}")
async def download_pdf(resultado_id: int, user: dict = Depends(get_current_user)):
    """Download direto do PDF Sierra salvo."""
    from fastapi.responses import FileResponse
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT pdf_path, seguradora FROM cotacao_resultados WHERE id = $1", resultado_id
        )
    if not row or not row["pdf_path"]:
        raise HTTPException(404, "PDF não encontrado")
    if not os.path.exists(row["pdf_path"]):
        raise HTTPException(404, "Arquivo não encontrado no servidor")
    return FileResponse(row["pdf_path"], filename=os.path.basename(row["pdf_path"]), media_type="application/pdf")


@router.post("/gerar-pdf")
async def gerar_pdf_seguradora(
    data: dict,
    user: dict = Depends(get_current_user)
):
    """Gera PDF Sierra pra uma seguradora específica."""
    from fastapi.responses import FileResponse
    from agilizador import baixar_pdf_cotacao
    
    seguradora = data.get("seguradora")
    if not seguradora:
        raise HTTPException(400, "Seguradora não informada")
    
    key = _session_key(user["id"])
    session = _cotacao_sessions.get(key)
    if not session:
        raise HTTPException(400, "Sessão expirada. Calcule novamente.")
    
    chat_id = user["id"]
    
    try:
        # Busca prêmio esperado e dados da tela (igual ao bot Telegram)
        from agilizador import _browser_sessions
        bs = _browser_sessions.get(chat_id, {})
        premio_map = bs.get('_premio_map', {})
        premio_esperado = premio_map.get(seguradora.lower())

        resultado_tela = None
        for r in bs.get('resultados', []):
            if r.get('seguradora', '').lower() == seguradora.lower():
                resultado_tela = r
                break

        # Primeiro tenta via agilizador (browser sessions)
        resultado = await baixar_pdf_cotacao(chat_id, seguradora, premio_esperado=premio_esperado, resultado_tela=resultado_tela)
        
        if resultado.get("sucesso") and resultado.get("pdf_path"):
            # Salva PDF permanente e registra no banco
            await _save_pdf_to_db(session, seguradora, resultado["pdf_path"], resultado.get("out_name", f"Sierra_{seguradora}.pdf"))
            return FileResponse(
                resultado["pdf_path"],
                filename=resultado.get("out_name", f"Sierra_{seguradora}.pdf"),
                media_type="application/pdf"
            )
        
        # Se falhou, tenta buscar PDF via API direta com login
        logger.info(f"baixar_pdf_cotacao falhou, tentando API direta pra {seguradora}...")
        cotacao_uuid = session.get("cotacao_uuid")
        if not cotacao_uuid:
            # Tenta extrair do resultados_url salvo na sessão
            from agilizador import _browser_sessions
            bs = _browser_sessions.get(chat_id, {})
            cotacao_uuid = bs.get("cotacao_uuid")
            url = bs.get("resultados_url", "")
            if not cotacao_uuid and url:
                import re
                m = re.search(r'resultados/([a-f0-9-]{36})', url)
                if m:
                    cotacao_uuid = m.group(1)
        
        if cotacao_uuid:
            import httpx
            from agilizador import _agg_token_cache
            cached_token = _agg_token_cache.get('token', '')
            
            if cached_token:
                async with httpx.AsyncClient(timeout=30) as hc:
                    token = cached_token
                    if token:
                        vr = await hc.get(
                            f"https://api.multicalculo.net/calculo/cotacao/versoes/{cotacao_uuid}",
                            headers={"Authorization": f"Bearer {token}"}
                        )
                        if vr.status_code == 200:
                            versoes = vr.json()
                            if isinstance(versoes, list) and versoes:
                                latest = versoes[-1]
                                seg_lower = seguradora.lower()
                                for calc in latest.get('calculos', []):
                                    nome = (calc.get('nomeSeguradora') or '').strip().lower()
                                    if seg_lower in nome or nome in seg_lower:
                                        for res in calc.get('resultados', []):
                                            pdf_url = res.get('pathPdf', '')
                                            if pdf_url:
                                                # Baixa e converte
                                                pdf_resp = await hc.get(pdf_url)
                                                if pdf_resp.status_code == 200 and pdf_resp.content[:5] == b'%PDF-':
                                                    seg_clean = seguradora.replace(' ', '_')
                                                    orig_path = f"/root/sierra/downloads/{seg_clean}_web.pdf"
                                                    os.makedirs("/root/sierra/downloads", exist_ok=True)
                                                    with open(orig_path, "wb") as f:
                                                        f.write(pdf_resp.content)
                                                    
                                                    from extractors import ExtractorFactory
                                                    from generator_sierra_v7_alt import SierraPDFGeneratorV7
                                                    extractor = ExtractorFactory.get_extractor(orig_path)
                                                    if not extractor:
                                                        from ai_extractor import AIExtractor
                                                        extractor = AIExtractor(orig_path)
                                                    data_ext = extractor.extract()
                                                    
                                                    from datetime import datetime as _dt
                                                    out_name = f"Sierra_{seg_clean}_{_dt.now().strftime('%H%M%S')}.pdf"
                                                    out_path = f"/root/sierra/downloads/{out_name}"
                                                    gen = SierraPDFGeneratorV7(data_ext, out_path)
                                                    gen.generate()
                                                    
                                                    await _save_pdf_to_db(session, seguradora, out_path, out_name)
                                                    return FileResponse(out_path, filename=out_name, media_type="application/pdf")
        
        raise HTTPException(400, resultado.get("msg", "Erro ao gerar PDF"))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao gerar PDF {seguradora}: {e}", exc_info=True)
        raise HTTPException(500, f"Erro interno: {str(e)[:200]}")
