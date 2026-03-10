#!/usr/bin/env python3
"""
Deep Import OneDrive → PostgreSQL
Reprocessa PDFs dos meses Out/Nov/Dez que falharam por erro 401 na API.
Também pode processar outros meses para capturar PDFs perdidos.
"""

import asyncio
import base64
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import fitz  # PyMuPDF

# ─── CONFIG ────────────────────────────────────────────────────────────────
CORRETORA_ID = 1
DEBUG_DIR = Path("/root/sierra/debug")
DEBUG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = DEBUG_DIR / "onedrive_deep_import.log"
PROGRESS_FILE = DEBUG_DIR / "deep_import_progress.json"
IMPORT_DIR = Path("/root/sierra/onedrive_imports")

# Rate limit: 10 req/min → 6s between requests
RATE_LIMIT_INTERVAL = 6.0
REPORT_EVERY = 50

# Palavras-chave no nome do arquivo para classificação
KW_APOLICE = ['apolice', 'apólice', 'ap0lice', 'apolíce', 'apolce']
KW_PROPOSTA = ['proposta']
KW_ENDOSSO = ['endosso']
KW_BOLETO = ['boleto', 'parcela', 'fatura']
KW_IGNORAR = ['boleto', 'parcela', 'fatura', 'carta verde', 'cartao', 'cartão',
               'declaracao', 'declaração', 'recibo', 'comprovante', 'aviso']

# ─── LOGGING ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
    ]
)
log = logging.getLogger('deep_import')

# ─── API KEY ────────────────────────────────────────────────────────────────
def get_api_key():
    with open('/root/.openclaw/agents/main/agent/auth-profiles.json') as f:
        d = json.load(f)
        p = d.get('profiles', {})
        if isinstance(p, str):
            p = json.loads(p)
        for k, v in p.items():
            if 'anthropic' in k:
                return v.get('token', '')
    return None

API_KEY = get_api_key()
log.info(f"API key: {'OK (' + API_KEY[:20] + '...)' if API_KEY else 'MISSING'}")

# ─── PROGRESS ────────────────────────────────────────────────────────────────
def load_progress():
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {
        "processed_pdfs": [],
        "failed_pdfs": [],
        "total_processed": 0,
        "total_extracted": 0,
        "total_ignored": 0,
        "started": datetime.now().isoformat(),
    }

def save_progress(prog):
    PROGRESS_FILE.write_text(json.dumps(prog, indent=2, ensure_ascii=False))

# ─── CLASSIFICAÇÃO ────────────────────────────────────────────────────────────
def classify_pdf_name(name: str) -> str:
    """Classifica PDF por nome do arquivo."""
    n = name.lower()
    
    # Boletos e docs ignoráveis
    for kw in KW_IGNORAR:
        if kw in n:
            return 'ignorar'
    
    # Apólice
    for kw in KW_APOLICE:
        if kw in n:
            return 'apolice'
    
    # Endosso
    for kw in KW_ENDOSSO:
        if kw in n:
            return 'endosso'
    
    # Proposta
    for kw in KW_PROPOSTA:
        if kw in n:
            return 'proposta'
    
    # Não identificado — processar mesmo assim para não perder
    return 'outros'

# ─── EXTRAÇÃO COM AI ────────────────────────────────────────────────────────
_last_api_call = 0.0

MAX_PDF_PAGES = 50  # Limitar a 50 páginas para evitar erro 400

def truncate_pdf_bytes(pdf_path: Path, max_pages: int = MAX_PDF_PAGES) -> bytes:
    """Trunca PDF para max_pages e retorna os bytes do PDF truncado."""
    try:
        doc = fitz.open(str(pdf_path))
        num_pages = len(doc)
        if num_pages <= max_pages:
            doc.close()
            return pdf_path.read_bytes()
        
        log.info(f"  ✂️ PDF grande ({num_pages} páginas) — truncando para {max_pages}")
        # Criar novo PDF com apenas as primeiras max_pages páginas
        new_doc = fitz.open()
        new_doc.insert_pdf(doc, from_page=0, to_page=max_pages - 1)
        data = new_doc.tobytes()
        new_doc.close()
        doc.close()
        return data
    except Exception as e:
        log.warning(f"  Falha ao truncar PDF: {e}, usando original")
        return pdf_path.read_bytes()

async def extract_with_ai(pdf_path: Path) -> dict | None:
    """Extrai dados de apólice via Anthropic API com rate limiting."""
    global _last_api_call
    
    # Rate limiting: 6s entre chamadas
    elapsed = time.time() - _last_api_call
    if elapsed < RATE_LIMIT_INTERVAL:
        await asyncio.sleep(RATE_LIMIT_INTERVAL - elapsed)
    
    try:
        data = truncate_pdf_bytes(pdf_path)
        if len(data) < 200:
            log.warning(f"PDF muito pequeno: {pdf_path.name} ({len(data)} bytes)")
            return None
        
        pdf_b64 = base64.b64encode(data).decode()
        
        prompt = """Analise este documento de seguro brasileiro.

Classifique o tipo e extraia os dados. Retorne APENAS JSON válido (sem markdown):
{
  "tipo_documento": "apolice|proposta|endosso|boleto|correspondencia|outro",
  "seguradora": "nome da seguradora",
  "numero_apolice": "número da apólice ou vazio",
  "numero_proposta": "número da proposta ou vazio",
  "segurado": {
    "nome": "nome completo do segurado",
    "cpf": "CPF/CNPJ sem formatação ou vazio"
  },
  "veiculo": {
    "placa": "placa sem traço ou vazio",
    "modelo": "marca e modelo ou vazio",
    "ano_modelo": "ano ou vazio",
    "chassi": "chassi ou vazio"
  },
  "vigencia": {
    "inicio": "DD/MM/YYYY ou vazio",
    "fim": "DD/MM/YYYY ou vazio"
  },
  "premio_total": 0.0,
  "ramo": "auto|residencial|vida|empresarial|fianca|rural|transporte|outro",
  "franquia_casco": 0.0,
  "comissao_percentual": 0.0,
  "obs": "informação relevante de endosso ou vazio"
}

Se não for apólice/proposta/endosso, retorne tipo_documento correto com campos vazios."""

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=90) as client:
                    _last_api_call = time.time()
                    resp = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key": API_KEY,
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json",
                        },
                        json={
                            "model": "claude-sonnet-4-20250514",
                            "max_tokens": 1024,
                            "messages": [{
                                "role": "user",
                                "content": [
                                    {
                                        "type": "document",
                                        "source": {
                                            "type": "base64",
                                            "media_type": "application/pdf",
                                            "data": pdf_b64,
                                        }
                                    },
                                    {"type": "text", "text": prompt}
                                ]
                            }]
                        }
                    )
                    
                    if resp.status_code == 200:
                        text = resp.json()['content'][0]['text'].strip()
                        # Remove markdown se necessário
                        if text.startswith('```'):
                            text = re.sub(r'^```\w*\n?', '', text)
                            text = re.sub(r'\n?```$', '', text)
                        result = json.loads(text.strip())
                        return result
                    
                    elif resp.status_code == 429:
                        log.warning(f"Rate limit hit, aguardando 60s... (tentativa {attempt+1})")
                        await asyncio.sleep(60)
                        continue
                    
                    else:
                        log.error(f"API erro {resp.status_code}: {resp.text[:200]}")
                        if attempt < 2:
                            await asyncio.sleep(5)
                        continue
                        
            except json.JSONDecodeError as e:
                log.error(f"JSON parse error: {e} — texto: {text[:200]}")
                return None
            except Exception as e:
                log.error(f"Erro na extração (tentativa {attempt+1}): {e}")
                if attempt < 2:
                    await asyncio.sleep(5)
        
        return None
    
    except Exception as e:
        log.error(f"Erro crítico ao processar {pdf_path}: {e}")
        return None

# ─── NORMALIZAÇÃO ────────────────────────────────────────────────────────────
def normalize_seguradora(nome: str) -> str:
    mapa = {
        'tokio': 'Tokio Marine', 'porto': 'Porto Seguro',
        'bradesco': 'Bradesco Seguros', 'mapfre': 'Mapfre',
        'hdi': 'HDI Seguros', 'allianz': 'Allianz',
        'azul': 'Azul Seguros', 'itau': 'Itaú Seguros',
        'itaú': 'Itaú Seguros', 'zurich': 'Zurich',
        'liberty': 'Liberty / Yelum', 'yelum': 'Liberty / Yelum',
        'suhai': 'Suhai', 'alfa': 'Alfa Seguros',
        'aliro': 'Aliro', 'darwin': 'Darwin',
        'ezze': 'Ezze Seguros', 'mitsui': 'Mitsui',
        'suíça': 'Suíça Seguros', 'suica': 'Suíça Seguros',
        'sura': 'Sura', 'essor': 'Essor',
        'sompo': 'Sompo', 'icatu': 'Icatu Seguros',
        'sulamerica': 'SulAmérica', 'sul america': 'SulAmérica',
        'berkley': 'Berkley', 'berkshire': 'Berkshire',
        'fairfax': 'Fairfax', 'liberty seguros': 'Liberty Seguros',
    }
    n = nome.lower().strip()
    for k, v in mapa.items():
        if k in n:
            return v
    return nome.strip()[:100] if nome else ''

def parse_date(s: str):
    if not s:
        return None
    for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']:
        try:
            return datetime.strptime(str(s).strip(), fmt).date()
        except:
            continue
    return None

def parse_money(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if v > 0 else None
    try:
        s = str(v).replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.').strip()
        f = float(s)
        return f if f > 0 else None
    except:
        return None

# ─── SALVAR NO DB ────────────────────────────────────────────────────────────
sys.path.insert(0, '/root/sierra')
import database

async def save_apolice_to_db(client_name: str, doc: dict, pdf_path: Path) -> bool:
    """Salva apólice/proposta/endosso no banco."""
    try:
        tipo = doc.get('tipo_documento', '')
        if tipo not in ('apolice', 'proposta', 'endosso'):
            return False
        
        seg = doc.get('segurado', {}) or {}
        veic = doc.get('veiculo', {}) or {}
        vig = doc.get('vigencia', {}) or {}
        
        nome = (seg.get('nome', '') or client_name or '').strip()
        cpf = (seg.get('cpf', '') or '').strip()
        seguradora = normalize_seguradora(doc.get('seguradora', '') or '')
        num_apolice = (doc.get('numero_apolice', '') or '').strip()[:50]
        num_proposta = (doc.get('numero_proposta', '') or '').strip()[:50]
        ramo = (doc.get('ramo', 'auto') or 'auto').strip()[:20]
        
        # Validação mínima
        if not nome:
            log.warning(f"  ⚠️ Sem nome para {pdf_path.name}")
            return False
        
        # Upsert cliente
        cliente_id = await database.upsert_cliente(CORRETORA_ID, nome, cpf)
        
        # Upsert veículo se tiver placa
        veiculo_id = None
        placa = (veic.get('placa', '') or '').strip().upper()
        placa = re.sub(r'[^A-Z0-9]', '', placa)
        if len(placa) >= 7:
            veiculo_id = await database.upsert_veiculo(
                cliente_id, placa,
                marca_modelo=veic.get('modelo', ''),
                ano_modelo=veic.get('ano_modelo', '')
            )
        
        # Valores monetários
        premio = parse_money(doc.get('premio_total'))
        franquia = parse_money(doc.get('franquia_casco'))
        comissao_pct = parse_money(doc.get('comissao_percentual'))
        
        # Datas
        vig_ini = parse_date(vig.get('inicio', ''))
        vig_fim = parse_date(vig.get('fim', ''))
        
        # Status baseado no tipo
        status_map = {'endosso': 'endosso', 'proposta': 'importada', 'apolice': 'importada'}
        status = status_map.get(tipo, 'importada')
        
        # Observação para endossos
        obs = doc.get('obs', '') or ''
        
        pool = await database.get_pool()
        async with pool.acquire() as conn:
            # Verificar se já existe para evitar dup
            existing = await conn.fetchval(
                """SELECT id FROM apolices 
                   WHERE corretora_id=$1 AND cliente_id=$2 
                   AND seguradora=$3 AND numero_apolice=$4
                   AND numero_apolice != ''""",
                CORRETORA_ID, cliente_id, seguradora, num_apolice
            ) if num_apolice else None
            
            if existing:
                log.info(f"  ⏭️ Já existe: {nome[:30]} | {seguradora} | {num_apolice}")
                return False
            
            await conn.execute(
                """INSERT INTO apolices 
                   (corretora_id, cliente_id, veiculo_id, seguradora, 
                    numero_apolice, proposta, vigencia_inicio, vigencia_fim,
                    premio, franquia, comissao_percentual, ramo, status, renovacao_obs)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                   ON CONFLICT DO NOTHING""",
                CORRETORA_ID, cliente_id, veiculo_id, seguradora,
                num_apolice, num_proposta, vig_ini, vig_fim,
                premio, franquia, comissao_pct, ramo, status,
                obs[:500] if obs else None
            )
        
        log.info(f"  ✅ {tipo.upper()}: {nome[:35]} | {seguradora[:25]} | {num_apolice} | R${premio}")
        return True
    
    except Exception as e:
        log.error(f"  ❌ DB error: {e}")
        return False

# ─── MAIN ────────────────────────────────────────────────────────────────────
async def main():
    log.info("=" * 70)
    log.info("🚀 DEEP IMPORT ONEDRIVE — INÍCIO")
    log.info(f"Timestamp: {datetime.now().isoformat()}")
    log.info("=" * 70)
    
    progress = load_progress()
    processed_set = set(progress.get('processed_pdfs', []))
    
    # Coletar todos os PDFs dos meses com falha (e opcionalmente todos)
    months_to_process = ['10_OUTUBRO', '11_NOVEMBRO', '12_DEZEMBRO']
    
    # Verificar se foi passado argumento para processar todos os meses
    if '--all-months' in sys.argv:
        months_to_process = [d.name for d in IMPORT_DIR.iterdir() if d.is_dir()]
        months_to_process.sort()
        log.info(f"Modo: TODOS OS MESES — {months_to_process}")
    else:
        log.info(f"Modo: MESES COM FALHA — {months_to_process}")
    
    # Coletar PDFs para processar
    all_pdfs = []
    for month in months_to_process:
        month_dir = IMPORT_DIR / month
        if not month_dir.exists():
            log.warning(f"Pasta não encontrada: {month_dir}")
            continue
        
        for pdf_path in sorted(month_dir.rglob("*.pdf")):
            pdf_key = str(pdf_path)
            if pdf_key in processed_set:
                continue
            
            # Verificar se já tem JSON sidecar (já processado)
            json_file = pdf_path.with_suffix('.json')
            if json_file.exists():
                processed_set.add(pdf_key)
                continue
            
            all_pdfs.append(pdf_path)
    
    log.info(f"📊 PDFs a processar: {len(all_pdfs)}")
    log.info(f"📊 Já processados: {len(processed_set)}")
    
    if not all_pdfs:
        log.info("✅ Nada a processar!")
        return progress
    
    total_processed = 0
    total_extracted = 0
    total_ignored = 0
    total_failed = 0
    
    for i, pdf_path in enumerate(all_pdfs):
        # Extrair nome do cliente da pasta pai
        client_name = pdf_path.parent.name
        pdf_name = pdf_path.name
        
        # Classificação por nome
        tipo_nome = classify_pdf_name(pdf_name.lower())
        
        log.info(f"\n[{i+1}/{len(all_pdfs)}] {client_name[:40]} / {pdf_name[:40]}")
        log.info(f"  Classificação por nome: {tipo_nome}")
        
        # Ignorar boletos e documentos irrelevantes
        if tipo_nome == 'ignorar':
            log.info(f"  ⏭️ Ignorado (boleto/docs irrel.)")
            total_ignored += 1
            processed_set.add(str(pdf_path))
            progress['processed_pdfs'].append(str(pdf_path))
            progress['total_ignored'] = progress.get('total_ignored', 0) + 1
            save_progress(progress)
            continue
        
        # Para "outros" (sem palavra-chave), processar mas sem prioridade
        # Processar apólices, propostas, endossos e outros
        doc = await extract_with_ai(pdf_path)
        total_processed += 1
        
        if doc:
            tipo_doc = doc.get('tipo_documento', 'outro')
            log.info(f"  📋 Tipo detectado: {tipo_doc}")
            
            # Salvar JSON sidecar
            pdf_path.with_suffix('.json').write_text(
                json.dumps(doc, indent=2, ensure_ascii=False)
            )
            
            if tipo_doc in ('apolice', 'proposta', 'endosso'):
                saved = await save_apolice_to_db(client_name, doc, pdf_path)
                if saved:
                    total_extracted += 1
                    progress['total_extracted'] = progress.get('total_extracted', 0) + 1
            else:
                log.info(f"  ℹ️ Tipo '{tipo_doc}' — não importado")
        else:
            log.warning(f"  ⚠️ Falha na extração")
            total_failed += 1
            progress['failed_pdfs'].append(str(pdf_path))
        
        processed_set.add(str(pdf_path))
        progress['processed_pdfs'].append(str(pdf_path))
        progress['total_processed'] = progress.get('total_processed', 0) + 1
        
        # Salvar progresso periodicamente
        if (i + 1) % 10 == 0:
            save_progress(progress)
        
        # Relatório a cada 50 documentos
        if (i + 1) % REPORT_EVERY == 0:
            log.info("\n" + "=" * 60)
            log.info(f"📊 PROGRESSO: {i+1}/{len(all_pdfs)} PDFs")
            log.info(f"   Processados: {total_processed}")
            log.info(f"   Extraídos/Salvos: {total_extracted}")
            log.info(f"   Ignorados: {total_ignored}")
            log.info(f"   Falhas: {total_failed}")
            log.info("=" * 60 + "\n")
    
    # Salvar progresso final
    progress['finished'] = datetime.now().isoformat()
    progress['summary'] = {
        'total_pdfs': len(all_pdfs),
        'total_processed': total_processed,
        'total_extracted': total_extracted,
        'total_ignored': total_ignored,
        'total_failed': total_failed,
    }
    save_progress(progress)
    
    log.info("\n" + "=" * 70)
    log.info("✅ DEEP IMPORT CONCLUÍDO")
    log.info(f"   Total PDFs: {len(all_pdfs)}")
    log.info(f"   Processados: {total_processed}")
    log.info(f"   Apólices/Propostas salvas: {total_extracted}")
    log.info(f"   Ignorados: {total_ignored}")
    log.info(f"   Falhas: {total_failed}")
    log.info("=" * 70)
    
    return progress, total_processed, total_extracted

if __name__ == '__main__':
    result = asyncio.run(main())
    if isinstance(result, tuple):
        _, total_processed, total_extracted = result
        # Notificar via openclaw
        os.system(f'openclaw system event --text "OneDrive deep import: {total_processed} documentos processados, {total_extracted} apólices extraídas" --mode now 2>/dev/null || true')
