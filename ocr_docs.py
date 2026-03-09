"""
OCR de documentos (CNH e CRVL) via IA.
Recebe imagem ou PDF, extrai dados estruturados.
Usa Gemini 2 Flash via OpenRouter (suporta qualquer orientação).
"""

import os
import base64
import json
import tempfile
import httpx
import fitz  # PyMuPDF


OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
VISION_MODEL = "google/gemini-2.0-flash-001"


CNH_PROMPT = """Analise esta imagem de uma CNH (Carteira Nacional de Habilitação) brasileira.
A imagem pode estar em qualquer orientação (rotacionada, de lado, de cabeça para baixo) — leia mesmo assim.

Extraia os seguintes dados em formato JSON:

{
  "tipo": "CNH",
  "nome": "Nome completo",
  "cpf": "000.000.000-00",
  "data_nascimento": "DD/MM/AAAA",
  "rg": "Número do RG",
  "categoria": "B / AB / etc",
  "validade": "DD/MM/AAAA",
  "numero_registro": "Número do registro",
  "primeiro_habilitacao": "DD/MM/AAAA",
  "filiacao_pai": "Nome do pai",
  "filiacao_mae": "Nome da mãe",
  "observacoes": "EAR / usa lentes / etc"
}

Se não conseguir ler algum campo, use "N/D".
Responda APENAS com o JSON, sem markdown."""

CRVL_PROMPT = """Analise esta imagem de um CRVL (Certificado de Registro e Licenciamento de Veículo) brasileiro.
A imagem pode estar em qualquer orientação (rotacionada, de lado, de cabeça para baixo) — leia mesmo assim.

Extraia os seguintes dados em formato JSON:

{
  "tipo": "CRVL",
  "proprietario": "Nome do proprietário",
  "cpf_cnpj": "000.000.000-00",
  "placa": "ABC1D23",
  "renavam": "00000000000",
  "chassi": "Número do chassi",
  "marca_modelo": "Ex: HONDA/CIVIC 1.5 TURBO",
  "ano_fabricacao": "2023",
  "ano_modelo": "2024",
  "cor": "Branca",
  "combustivel": "Flex",
  "categoria": "Particular",
  "municipio": "Cidade/UF"
}

Se não conseguir ler algum campo, use "N/D".
Responda APENAS com o JSON, sem markdown."""

GENERIC_PROMPT = """Analise esta imagem de um documento.
A imagem pode estar em qualquer orientação (rotacionada, de lado, de cabeça para baixo) — leia mesmo assim.

Se for uma CNH (Carteira Nacional de Habilitação), retorne tipo "CNH".
Se for um CRVL (Certificado de Registro e Licenciamento de Veículo), retorne tipo "CRVL".

Extraia os dados mais importantes em JSON:
{
  "tipo": "CNH ou CRVL ou Outro",
  ... campos relevantes ...
}

Responda APENAS com o JSON, sem markdown."""


def _parse_json_response(content: str) -> dict | None:
    """Limpa e faz parse do JSON retornado pelo modelo."""
    text = content.strip()
    # Remove blocos de markdown
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            try:
                return json.loads(part)
            except:
                pass
    try:
        return json.loads(text)
    except:
        return None


def _image_to_base64(image_path: str) -> tuple[str, str]:
    """Lê imagem e retorna (base64, mime_type)."""
    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp"
    }
    mime_type = mime_map.get(ext, "image/jpeg")
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8"), mime_type


def _pdf_first_page_to_image(pdf_path: str) -> str | None:
    """Converte a primeira página do PDF em imagem JPEG temporária."""
    try:
        doc = fitz.open(pdf_path)
        page = doc[0]
        # Renderiza em alta resolução
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        pix.save(tmp.name)
        doc.close()
        return tmp.name
    except Exception as e:
        print(f"Erro ao converter PDF: {e}")
        return None


def _call_vision(image_data: str, mime_type: str, prompt: str) -> dict | None:
    """Chama Gemini 2 Flash via OpenRouter com imagem e prompt."""
    try:
        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": VISION_MODEL,
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_data}"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }],
                "max_tokens": 2048
            },
            timeout=60.0
        )
        content = response.json()["choices"][0]["message"]["content"]
        return _parse_json_response(content)
    except Exception as e:
        print(f"Vision API error: {e}")
        return None


def extract_document_data(file_path: str) -> dict | None:
    """
    Extrai dados de uma imagem ou PDF de documento (CNH/CRVL).
    Suporta qualquer orientação da imagem.
    """
    if not OPENROUTER_KEY:
        return None

    tmp_img = None
    try:
        # Converte PDF pra imagem se necessário
        if file_path.lower().endswith(".pdf"):
            tmp_img = _pdf_first_page_to_image(file_path)
            if not tmp_img:
                return None
            image_data, mime_type = _image_to_base64(tmp_img)
        else:
            image_data, mime_type = _image_to_base64(file_path)

        # Primeira passada: identifica o tipo de documento
        result = _call_vision(image_data, mime_type, GENERIC_PROMPT)
        if not result:
            return None

        # Segunda passada com prompt específico
        doc_type = result.get("tipo", "").upper()
        if "CNH" in doc_type:
            specific = _call_vision(image_data, mime_type, CNH_PROMPT)
            return specific or result
        elif "CRVL" in doc_type or "CRV" in doc_type:
            specific = _call_vision(image_data, mime_type, CRVL_PROMPT)
            return specific or result

        return result

    except Exception as e:
        print(f"OCR error: {e}")
        return None
    finally:
        if tmp_img:
            try:
                os.unlink(tmp_img)
            except:
                pass


def format_document_response(data: dict) -> str:
    """Formata os dados extraídos pra exibição no Telegram."""
    doc_type = data.get("tipo", "Documento").upper()

    if "CNH" in doc_type:
        return (
            f"🪪 *CNH Identificada*\n\n"
            f"👤 *Nome:* `{data.get('nome', 'N/D')}`\n"
            f"📋 *CPF:* `{data.get('cpf', 'N/D')}`\n"
            f"🎂 *Nascimento:* `{data.get('data_nascimento', 'N/D')}`\n"
            f"🆔 *RG:* `{data.get('rg', 'N/D')}`\n"
            f"🚗 *Categoria:* `{data.get('categoria', 'N/D')}`\n"
            f"📅 *Validade:* `{data.get('validade', 'N/D')}`\n"
            f"📝 *Registro:* `{data.get('numero_registro', 'N/D')}`\n"
            f"🗓️ *1ª Habilitação:* `{data.get('primeiro_habilitacao', 'N/D')}`"
        )

    elif "CRVL" in doc_type or "CRV" in doc_type:
        return (
            f"📄 *CRVL Identificado*\n\n"
            f"👤 *Proprietário:* `{data.get('proprietario', 'N/D')}`\n"
            f"📋 *CPF/CNPJ:* `{data.get('cpf_cnpj', 'N/D')}`\n"
            f"🔢 *Placa:* `{data.get('placa', 'N/D')}`\n"
            f"📝 *Renavam:* `{data.get('renavam', 'N/D')}`\n"
            f"🔑 *Chassi:* `{data.get('chassi', 'N/D')}`\n"
            f"🚗 *Veículo:* `{data.get('marca_modelo', 'N/D')}`\n"
            f"📅 *Fab/Mod:* `{data.get('ano_fabricacao', 'N/D')}/{data.get('ano_modelo', 'N/D')}`\n"
            f"🎨 *Cor:* `{data.get('cor', 'N/D')}`\n"
            f"⛽ *Combustível:* `{data.get('combustivel', 'N/D')}`\n"
            f"📍 *Município:* `{data.get('municipio', 'N/D')}`"
        )

    else:
        lines = [f"📄 *Documento* ({data.get('tipo', '?')})\n"]
        for key, val in data.items():
            if key != "tipo" and val and val != "N/D":
                lines.append(f"• *{key}:* `{val}`")
        return "\n".join(lines)
