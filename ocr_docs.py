"""
OCR de documentos (CNH e CRVL) via IA.
Recebe imagem, extrai dados estruturados.
"""

import os
import base64
import json
import httpx


OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
VISION_MODEL = "google/gemini-2.0-flash-001"  # Barato pra visão

CNH_PROMPT = """Analise esta imagem de uma CNH (Carteira Nacional de Habilitação) brasileira.
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
Extraia os seguintes dados em formato JSON:

{
  "tipo": "CRVL",
  "proprietario": "Nome do proprietário",
  "cpf_cnpj": "000.000.000-00",
  "placa": "ABC-1D23",
  "renavam": "00000000000",
  "chassi": "Número do chassi",
  "marca_modelo": "Ex: VW/GOL 1.0",
  "ano_fabricacao": "2023",
  "ano_modelo": "2024",
  "cor": "Branca",
  "combustivel": "Flex / Gasolina / etc",
  "categoria": "Particular",
  "municipio": "Cidade/UF",
  "exercicio": "2024",
  "data_licenciamento": "DD/MM/AAAA"
}

Se não conseguir ler algum campo, use "N/D".
Responda APENAS com o JSON, sem markdown."""

GENERIC_PROMPT = """Analise esta imagem de um documento.
Se for uma CNH (Carteira Nacional de Habilitação), extraia dados pessoais.
Se for um CRVL (Certificado de Registro e Licenciamento de Veículo), extraia dados do veículo.
Se for outro documento de seguro, extraia as informações relevantes.

Primeiro identifique o tipo do documento, depois extraia os dados em JSON:

{
  "tipo": "CNH / CRVL / Outro",
  ... campos relevantes ...
}

Responda APENAS com o JSON, sem markdown."""


def extract_document_data(image_path: str) -> dict | None:
    """Extrai dados de uma imagem de documento usando IA com visão."""
    if not OPENROUTER_KEY:
        return None

    try:
        # Lê e codifica a imagem
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        # Detecta tipo de imagem
        ext = os.path.splitext(image_path)[1].lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
        mime_type = mime_map.get(ext, "image/jpeg")

        # Primeira passada: identifica o documento
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
                            "text": GENERIC_PROMPT
                        }
                    ]
                }],
                "max_tokens": 2048
            },
            timeout=60.0
        )

        data = response.json()
        content = data["choices"][0]["message"]["content"]

        # Parse JSON
        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()

        result = json.loads(text)

        # Se identificou como CNH ou CRVL, faz segunda passada com prompt específico
        doc_type = result.get("tipo", "").upper()
        if "CNH" in doc_type:
            specific_result = _extract_specific(image_data, mime_type, CNH_PROMPT)
            if specific_result:
                return specific_result
        elif "CRVL" in doc_type or "CRV" in doc_type:
            specific_result = _extract_specific(image_data, mime_type, CRVL_PROMPT)
            if specific_result:
                return specific_result

        return result

    except Exception as e:
        print(f"OCR error: {e}")
        return None


def _extract_specific(image_data: str, mime_type: str, prompt: str) -> dict | None:
    """Extrai com prompt específico pra CNH ou CRVL."""
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

        data = response.json()
        content = data["choices"][0]["message"]["content"]

        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()

        return json.loads(text)

    except Exception as e:
        print(f"Specific OCR error: {e}")
        return None


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
            f"🗓️ *1ª Habilitação:* `{data.get('primeiro_habilitacao', 'N/D')}`\n"
            f"👨 *Pai:* `{data.get('filiacao_pai', 'N/D')}`\n"
            f"👩 *Mãe:* `{data.get('filiacao_mae', 'N/D')}`\n"
            f"📌 *Obs:* `{data.get('observacoes', 'N/D')}`"
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
        # Formato genérico
        lines = [f"📄 *Documento Identificado* ({data.get('tipo', '?')})\n"]
        for key, val in data.items():
            if key != "tipo" and val and val != "N/D":
                lines.append(f"• *{key}:* `{val}`")
        return "\n".join(lines)
