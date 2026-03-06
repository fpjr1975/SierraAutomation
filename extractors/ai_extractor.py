"""
AI-powered extractor — fallback para seguradoras não mapeadas.
Usa Claude/OpenRouter para ler o PDF e extrair dados estruturados.
"""

import os
import json
import pdfplumber
from .base import BaseExtractor

# Try anthropic first, fall back to httpx for OpenRouter
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

TEXT_MODEL = "minimax/minimax-m2.5"  # Barato pra texto


EXTRACTION_PROMPT = """Você é um especialista em seguros de automóvel no Brasil.

Analise o texto abaixo extraído de um PDF de orçamento/cotação de seguro auto e extraia os dados em formato JSON.

REGRAS:
- Extraia TODOS os campos possíveis
- Para coberturas, use tuplas [nome, valor] 
- Para pagamento, extraia todas as opções disponíveis
- Valores monetários no formato "R$ 1.234,56"
- Se não encontrar um campo, use "N/D"
- Identifique a seguradora pelo conteúdo do PDF

JSON esperado:
{
  "insurer": "Nome da Seguradora",
  "segurado": "Nome do segurado",
  "condutor": "Nome do condutor principal",
  "veiculo": "Descrição do veículo",
  "placa": "ABC-1234",
  "vigencia": "DD/MM/AAAA a DD/MM/AAAA",
  "uso": "Particular / Comercial",
  "cep_pernoite": "00000-000",
  "coberturas": [
    ["Nome da Cobertura", "Valor ou Limite"],
    ["Danos Materiais", "R$ 100.000,00"],
    ["Danos Corporais", "R$ 100.000,00"]
  ],
  "franquias_lista": [
    "Casco: R$ 3.500,00",
    "Vidros: Consulte tabela"
  ],
  "assistencias": [
    "Guincho 400 KM",
    "Carro Reserva 15 dias"
  ],
  "pagamento_opcoes": [
    {"tipo": "À Vista", "parcelas": "1x", "valor": "R$ 2.500,00"},
    {"tipo": "Cartão de Crédito", "parcelas": "10x", "valor": "R$ 250,00"}
  ],
  "premio_total": "R$ 2.500,00",
  "condutor_jovem": "Sim / Não / N/D"
}

TEXTO DO PDF:
---
{text}
---

Responda APENAS com o JSON, sem markdown, sem explicações."""


class AIExtractor(BaseExtractor):
    """Extractor que usa IA para interpretar PDFs de qualquer seguradora."""

    def __init__(self, pdf_path):
        super().__init__(pdf_path)
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")

    def extract(self):
        """Extrai dados usando IA."""
        # Limita texto para não estourar contexto (primeiras 8000 chars)
        text = self.full_text[:8000]

        if not text.strip():
            return self.data

        # Tenta Anthropic primeiro, depois OpenRouter
        ai_data = None
        if self.api_key and HAS_ANTHROPIC:
            ai_data = self._extract_anthropic(text)
        elif self.openrouter_key and HAS_HTTPX:
            ai_data = self._extract_openrouter(text)

        if ai_data:
            self._merge_ai_data(ai_data)

        self._apply_casing()
        return self.data

    def _extract_anthropic(self, text):
        """Extrai via API Anthropic direta."""
        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                messages=[{
                    "role": "user",
                    "content": EXTRACTION_PROMPT.format(text=text)
                }]
            )
            return self._parse_response(message.content[0].text)
        except Exception as e:
            print(f"Anthropic extraction error: {e}")
            return None

    def _extract_openrouter(self, text):
        """Extrai via OpenRouter (modelo barato)."""
        try:
            response = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openrouter_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": TEXT_MODEL,
                    "messages": [{
                        "role": "user",
                        "content": EXTRACTION_PROMPT.format(text=text)
                    }],
                    "max_tokens": 4096
                },
                timeout=60.0
            )
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return self._parse_response(content)
        except Exception as e:
            print(f"OpenRouter extraction error: {e}")
            return None

    def _parse_response(self, text):
        """Parseia resposta JSON da IA."""
        try:
            # Remove markdown code blocks se presentes
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            if text.startswith("json"):
                text = text[4:].strip()

            return json.loads(text)
        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}")
            return None

    def _merge_ai_data(self, ai_data):
        """Merge dados da IA no formato do BaseExtractor."""
        simple_fields = [
            "insurer", "segurado", "condutor", "veiculo", "placa",
            "vigencia", "uso", "cep_pernoite", "premio_total",
            "condutor_jovem"
        ]

        for field in simple_fields:
            val = ai_data.get(field)
            if val and val != "N/D":
                self.data[field] = val

        # Coberturas: IA retorna lista de listas, converter pra lista de tuplas
        coberturas = ai_data.get("coberturas", [])
        if coberturas:
            self.data["coberturas"] = [(c[0], c[1]) for c in coberturas if len(c) >= 2]

        # Franquias
        franquias = ai_data.get("franquias_lista", [])
        if franquias:
            self.data["franquias_lista"] = franquias

        # Assistências
        assistencias = ai_data.get("assistencias", [])
        if assistencias:
            self.data["assistencias"] = assistencias

        # Pagamento
        pagamento = ai_data.get("pagamento_opcoes", [])
        if pagamento:
            self.data["pagamento_opcoes"] = pagamento
