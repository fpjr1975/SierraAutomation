"""
Conversor PDF — endpoint web para converter PDFs de seguradoras em layout Sierra.
Reusa o mesmo engine do bot Telegram.
"""
import os
import re
import sys
import tempfile
from datetime import datetime
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

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


@router.get("/download/{filename}")
async def converter_download(filename: str, token: str = None, user: dict = Depends(get_current_user)):
    """Download do PDF convertido."""
    filename = os.path.basename(filename)
    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(404, "Arquivo não encontrado")
    return FileResponse(filepath, media_type="application/pdf", filename=filename)
