"""
Conversor PDF — endpoint web para converter PDFs de seguradoras em layout Sierra.
Reusa o mesmo engine do bot Telegram.
"""
import os
import re
import sys
import json
import tempfile
import logging
import httpx
from datetime import datetime
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

sys.path.insert(0, "/root/sierra")
sys.path.insert(0, "/root/sierra/web")
from auth import get_current_user
from extractors import ExtractorFactory
from extractors.ai_extractor import AIExtractor
from generator_sierra_v7_alt import SierraPDFGeneratorV7 as SierraPDFGenerator

router = APIRouter(prefix="/api/conversor", tags=["conversor"])

OUTPUT_DIR = "/root/sierra/output"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def build_output_name(data):
    segurado_raw = str(data.get("segurado") or "Cliente").upper()
    for suffix in [r'\bLTDA\b', r'\bS/A\b', r'\bS\.A\.\b', r'\bME\b', r'\bEPP\b', r'\bSA\b']:
        segurado_raw = re.sub(suffix, '', segurado_raw)
    segurado_raw = segurado_raw.strip()
    parts = segurado_raw.split()
    if len(parts) >= 2:
        name_str = f"{parts[0]}.{parts[-1]}"
    elif parts:
        name_str = parts[0]
    else:
        name_str = "Cliente"
    insurer_code = str(data.get("insurer", "UNK"))[:3].upper()
    now_str = datetime.now().strftime("%d.%m.%y_%H.%M.%S")
    out_name = f"Orcamento.{name_str}.{insurer_code}.{now_str}.pdf"
    return re.sub(r'[<>:"/\\|?*]', '', out_name)


@router.post("/upload")
async def converter_upload(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Recebe PDF de seguradora, converte para layout Sierra, retorna PDF."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Envie um arquivo PDF")

    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(400, "Arquivo muito grande (máx 10MB)")

    tmp_path = None
    output_path = None
    try:
        # Save uploaded file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name
            content = await file.read()
            tmp.write(content)

        # Identify insurer and extract
        extractor = ExtractorFactory.get_extractor(tmp_path)
        ai_used = False
        if not extractor:
            extractor = AIExtractor(tmp_path)
            ai_used = True

        data = extractor.extract()
        insurer_name = data.get("insurer", "Desconhecida")

        # Generate Sierra PDF
        out_name = build_output_name(data)
        output_path = os.path.join(OUTPUT_DIR, out_name)
        generator = SierraPDFGenerator(data, output_path)
        generator.generate()

        return {
            "success": True,
            "filename": out_name,
            "seguradora": insurer_name,
            "segurado": data.get("segurado", "N/I"),
            "ai_used": ai_used,
            "download_url": f"/api/conversor/download/{out_name}",
            "data": {
                "segurado": data.get("segurado"),
                "cpf": data.get("cpf"),
                "veiculo": data.get("veiculo"),
                "placa": data.get("placa"),
                "vigencia_inicio": data.get("vigencia_inicio"),
                "vigencia_fim": data.get("vigencia_fim"),
                "premio_total": data.get("premio_total") or data.get("premio_liquido"),
                "franquia": data.get("franquia"),
            }
        }
    except Exception as e:
        raise HTTPException(500, f"Erro ao processar PDF: {str(e)}")
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except:
                pass


ISSUE_LOG = "/root/sierra/extraction_issues.log"
BOT_TOKEN = os.environ.get("SIERRA_BOT_TOKEN", "")
ADMIN_CHAT_ID = 6553672222

logger = logging.getLogger("conversor")


class IssueReport(BaseModel):
    seguradora: str
    filename: str
    campo: str = ""
    descricao: str = ""
    dados_extraidos: Optional[dict] = None


@router.post("/report-issue")
async def report_issue(report: IssueReport, user: dict = Depends(get_current_user)):
    """Recebe report de franquia/dado faltando e notifica via Telegram."""
    user_nome = user.get("nome", "Desconhecido")
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M")

    # Log to file
    entry = {
        "timestamp": timestamp,
        "user": user_nome,
        "seguradora": report.seguradora,
        "filename": report.filename,
        "campo": report.campo,
        "descricao": report.descricao,
    }
    try:
        with open(ISSUE_LOG, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Erro ao salvar issue: {e}")

    # Notify via Telegram
    msg = (
        f"⚠️ *Problema na extração reportado*\n\n"
        f"👤 Usuário: {user_nome}\n"
        f"🏢 Seguradora: {report.seguradora}\n"
        f"📄 Arquivo: {report.filename}\n"
    )
    if report.campo:
        msg += f"📌 Campo: {report.campo}\n"
    if report.descricao:
        msg += f"💬 Descrição: {report.descricao}\n"
    msg += f"\n🕐 {timestamp}"

    if BOT_TOKEN:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": ADMIN_CHAT_ID,
                        "text": msg,
                        "parse_mode": "Markdown",
                    },
                    timeout=10,
                )
        except Exception as e:
            logger.error(f"Erro ao enviar notificação Telegram: {e}")

    return {"success": True, "message": "Report enviado com sucesso"}


@router.get("/download/{filename}")
async def converter_download(filename: str, token: str = None):
    """Download do PDF convertido. Aceita token via query string para downloads diretos do browser."""
    from jose import jwt, JWTError
    SECRET_KEY = "sierra-saas-2026-super-secret-key-change-in-production"
    ALGORITHM = "HS256"

    if not token:
        raise HTTPException(401, "Token de autenticação necessário")
    try:
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(401, "Token inválido ou expirado")

    filename = os.path.basename(filename)
    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(404, "Arquivo não encontrado. Pode ter sido removido do servidor.")
    return FileResponse(filepath, media_type="application/pdf", filename=filename)
