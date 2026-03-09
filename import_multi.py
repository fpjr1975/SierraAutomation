#!/usr/bin/env python3
"""
OneDrive Importer v2 — Navega por URL (sem click)
Resolve o problema de itens fora do viewport.
"""

import asyncio, logging, httpx, re, os, json, sys, time, base64
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/root/sierra/import_multi.log')
    ]
)
logger = logging.getLogger('import_v2')

DOWNLOAD_DIR = Path("/root/sierra/onedrive_imports/MULTI_MESES")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
PROGRESS_FILE = Path("/root/sierra/import_multi_progress.json")

# OneDrive base params
REDEEM = 'aHR0cHM6Ly8xZHJ2Lm1zL2YvYy9mOGRhMjBmMjQ3OWQ4MTAwL0lnQUFnWjFIOGlEYUlJRDRQSWtDQUFBQUFRRmQyMC13ZUl4WjU3aWVvdjBGSEtJP2U9NTpjeVVwWlkmYXQ9OQ'
CID = 'F8DA20F2479D8100'
JAN_ID = 'F8DA20F2479D8100%21170696'  # ID da pasta 1 JANEIRO


def load_progress():
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {"done": [], "failed": [], "total_pdfs": 0, "total_extracted": 0, 
            "started": datetime.now().isoformat(), "errors": {}}

def save_progress(prog):
    PROGRESS_FILE.write_text(json.dumps(prog, indent=2, ensure_ascii=False))


def make_url(item_id: str) -> str:
    """Monta URL do OneDrive pra um item específico."""
    return f"https://onedrive.live.com/?redeem={REDEEM}&id={item_id}&cid={CID}"


async def get_api_key():
    auth_file = '/root/.openclaw/agents/main/agent/auth-profiles.json'
    with open(auth_file) as f:
        auth = json.load(f)
        for k, v in auth.get('profiles', {}).items():
            if 'anthropic' in k:
                return v.get('token', '')
    return None


async def extract_with_ai(pdf_path: str, api_key: str) -> dict:
    """Extrai dados do PDF via Anthropic Sonnet."""
    try:
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
        
        if len(pdf_bytes) < 500:
            return None
        
        pdf_b64 = base64.b64encode(pdf_bytes).decode()
        
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 4096,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
                            {"type": "text", "text": """Analise este documento de seguro. Retorne JSON com:
{"tipo_documento":"apolice|proposta|boleto|endosso|parcela|outro","seguradora":"","numero_apolice":"","numero_proposta":"","segurado":{"nome":"","cpf":""},"veiculo":{"placa":"","modelo":"","ano_modelo":"","chassi":""},"vigencia":{"inicio":"DD/MM/YYYY","fim":"DD/MM/YYYY"},"premio_total":0.0,"ramo":"auto|residencial|vida|empresarial|fianca|outro","franquia_casco":0.0}
APENAS o JSON, sem markdown."""}
                        ]
                    }]
                }
            )
            
            if resp.status_code == 200:
                text = resp.json()['content'][0]['text'].strip()
                if text.startswith('```'):
                    text = re.sub(r'^```\w*\n?', '', text)
                    text = re.sub(r'\n?```$', '', text)
                return json.loads(text.strip())
            elif resp.status_code == 429:
                logger.warning("Rate limit — aguardando 30s...")
                await asyncio.sleep(30)
                return None
            else:
                logger.error(f"API {resp.status_code}: {resp.text[:200]}")
                return None
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error: {e}")
        return None
    except Exception as e:
        logger.error(f"Erro extração: {e}")
        return None


async def save_to_db(client_name: str, doc_data: dict, pdf_path: str):
    """Salva no PostgreSQL."""
    try:
        sys.path.insert(0, '/root/sierra')
        import database
        
        if not doc_data:
            return False
        
        tipo = doc_data.get('tipo_documento', 'outro')
        if tipo not in ('apolice', 'proposta', 'endosso'):
            return True  # Salvo em disco, não importa
        
        seg = doc_data.get('segurado', {})
        veic = doc_data.get('veiculo', {})
        vig = doc_data.get('vigencia', {})
        
        nome = seg.get('nome', '') or client_name
        cpf = seg.get('cpf', '')
        
        # Normaliza seguradora
        seguradora = _normalize_seguradora(doc_data.get('seguradora', ''))
        
        cliente_id = await database.upsert_cliente(1, nome, cpf)
        
        veiculo_id = None
        placa = veic.get('placa', '')
        if placa and len(placa) >= 7:
            veiculo_id = await database.upsert_veiculo(
                cliente_id, placa,
                marca_modelo=veic.get('modelo', ''),
                ano_modelo=veic.get('ano_modelo', ''),
            )
        
        premio = doc_data.get('premio_total')
        if isinstance(premio, str):
            try:
                premio = float(premio.replace('R$', '').replace('.', '').replace(',', '.').strip())
            except:
                premio = None
        
        pool = await database.get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO apolices (corretora_id, cliente_id, veiculo_id, seguradora, 
                                      numero_apolice, proposta, vigencia_inicio, vigencia_fim, 
                                      premio, ramo, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT DO NOTHING
            """, 1, cliente_id, veiculo_id, seguradora,
                doc_data.get('numero_apolice', ''), doc_data.get('numero_proposta', ''),
                _parse_date(vig.get('inicio', '')), _parse_date(vig.get('fim', '')),
                float(premio) if premio else None,
                doc_data.get('ramo', 'auto'), 'importada')
        
        logger.info(f"  ✅ DB: {nome[:40]} | {seguradora[:20]} | R${premio}")
        return True
        
    except Exception as e:
        logger.error(f"  ❌ DB: {e}")
        return False


def _normalize_seguradora(nome: str) -> str:
    """Normaliza nome da seguradora."""
    mapa = {
        'tokio': 'Tokio Marine',
        'porto': 'Porto Seguro',
        'bradesco': 'Bradesco Seguros',
        'mapfre': 'Mapfre',
        'hdi': 'HDI Seguros',
        'allianz': 'Allianz',
        'azul': 'Azul Seguros',
        'itau': 'Itaú Seguros',
        'itaú': 'Itaú Seguros',
        'zurich': 'Zurich',
        'liberty': 'Liberty / Yelum',
        'yelum': 'Liberty / Yelum',
        'suhai': 'Suhai',
        'alfa': 'Alfa Seguros',
        'aliro': 'Aliro',
        'darwin': 'Darwin',
        'ezze': 'Ezze Seguros',
        'mitsui': 'Mitsui',
        'suíça': 'Suíça',
        'suica': 'Suíça',
        'sura': 'Sura',
        'essor': 'Essor',
        'sompo': 'Sompo',
    }
    nome_lower = nome.lower()
    for key, val in mapa.items():
        if key in nome_lower:
            return val
    return nome.strip()[:50]


def _parse_date(date_str):
    if not date_str:
        return None
    try:
        for fmt in ['%d/%m/%Y', '%Y-%m-%d']:
            try:
                return datetime.strptime(str(date_str), fmt).date()
            except:
                continue
    except:
        pass
    return None


async def run():
    from playwright.async_api import async_playwright
    
    progress = load_progress()
    done_set = set(progress.get('done', []))
    api_key = await get_api_key()
    
    if not api_key:
        logger.error("Sem API key!")
        return
    
    logger.info("🚀 IMPORTAÇÃO JANEIRO v2 — INÍCIO")
    logger.info(f"Já processados: {len(done_set)}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        
        # FASE 1: Coleta TODOS os IDs das pastas de clientes
        logger.info("📂 Fase 1: Coletando IDs de todas as pastas...")
        
        all_folders = {}
        
        async def on_resp(response):
            if response.status == 200:
                ct = response.headers.get('content-type', '')
                if 'json' in ct:
                    try:
                        body = await response.json()
                        if isinstance(body, dict):
                            for item in body.get('value', body.get('items', [])):
                                if isinstance(item, dict) and item.get('folder') and item.get('name'):
                                    name = item['name']
                                    item_id = item.get('id', '')
                                    if item_id and not re.match(r'^\d+\s+(JANEIRO|FEVEREIRO|MARÇO|ABRIL|MAIO|JUNHO|JULHO|AGOSTO|SETEMBRO|OUTUBRO|NOVEMBRO|DEZEMBRO)$', name):
                                        if name not in ['CARTA VERDE']:
                                            all_folders[name] = {
                                                'id': item_id,
                                                'size': item.get('size', 0),
                                                'child_count': item.get('folder', {}).get('childCount', 0),
                                            }
                    except:
                        pass
        
        page.on('response', on_resp)
        
        await page.goto(make_url(JAN_ID), wait_until='networkidle', timeout=30000)
        await asyncio.sleep(4)
        
        # Scroll extensivo pra forçar carregamento de TODOS os items
        prev_count = 0
        for scroll_round in range(20):
            await page.mouse.wheel(0, 3000)
            await asyncio.sleep(1)
            if len(all_folders) > prev_count:
                prev_count = len(all_folders)
            elif scroll_round > 5:
                break  # Parou de carregar novos
        
        logger.info(f"📁 Total pastas encontradas: {len(all_folders)}")
        
        # FASE 2: Pra cada pasta, navega por URL direta
        to_process = {name: info for name, info in all_folders.items() if name not in done_set}
        logger.info(f"📋 A processar: {len(to_process)}")
        
        total_pdfs = progress.get('total_pdfs', 0)
        total_extracted = progress.get('total_extracted', 0)
        
        for i, (name, info) in enumerate(to_process.items()):
            logger.info(f"\n[{i+1}/{len(to_process)}] === {name} ===")
            
            try:
                # Limpa interceptações anteriores
                client_pdfs = []
                
                async def on_client_resp(response):
                    if response.status == 200:
                        ct = response.headers.get('content-type', '')
                        if 'json' in ct:
                            try:
                                body = await response.json()
                                if isinstance(body, dict):
                                    for item in body.get('value', body.get('items', [])):
                                        if isinstance(item, dict) and item.get('name', '').lower().endswith('.pdf'):
                                            dl = (item.get('@microsoft.graph.downloadUrl') or 
                                                 item.get('@content.downloadUrl') or '')
                                            if dl:
                                                client_pdfs.append({
                                                    'name': item['name'],
                                                    'size': item.get('size', 0),
                                                    'url': dl,
                                                })
                            except:
                                pass
                
                # Remove listener anterior e adiciona novo
                page.remove_listener('response', on_resp)
                page.on('response', on_client_resp)
                
                # Navega diretamente pela URL com o item ID
                folder_url = make_url(info['id'])
                await page.goto(folder_url, wait_until='networkidle', timeout=20000)
                await asyncio.sleep(3)
                
                if client_pdfs:
                    logger.info(f"  📄 {len(client_pdfs)} PDFs")
                    
                    safe_name = re.sub(r'[<>:"/\\|?*]', '_', name)[:80]
                    client_dir = DOWNLOAD_DIR / safe_name
                    client_dir.mkdir(parents=True, exist_ok=True)
                    
                    for pdf in client_pdfs:
                        pdf_path = client_dir / pdf['name']
                        
                        # Baixa
                        if not pdf_path.exists():
                            try:
                                async with httpx.AsyncClient(timeout=60) as dl:
                                    resp = await dl.get(pdf['url'], follow_redirects=True)
                                    if resp.status_code == 200 and len(resp.content) > 500:
                                        pdf_path.write_bytes(resp.content)
                                        total_pdfs += 1
                                    else:
                                        continue
                            except Exception as de:
                                logger.error(f"  Download erro: {de}")
                                continue
                        
                        # Extrai só apólices/propostas
                        fname_lower = pdf['name'].lower()
                        if any(kw in fname_lower for kw in ['apolice', 'apólice', 'proposta', 'endosso', 'ap0olice']):
                            logger.info(f"  🔍 Extraindo: {pdf['name']}")
                            doc_data = await extract_with_ai(str(pdf_path), api_key)
                            if doc_data:
                                # Salva JSON
                                json_path = pdf_path.with_suffix('.json')
                                json_path.write_text(json.dumps(doc_data, indent=2, ensure_ascii=False))
                                
                                ok = await save_to_db(name, doc_data, str(pdf_path))
                                if ok:
                                    total_extracted += 1
                        else:
                            logger.info(f"  💾 {pdf['name']}")
                else:
                    logger.info(f"  📭 Sem PDFs (pode ter subpastas ou outros formatos)")
                
                # Remove listener do cliente
                page.remove_listener('response', on_client_resp)
                page.on('response', on_resp)
                
                # Marca feito
                done_set.add(name)
                progress['done'] = list(done_set)
                progress['total_pdfs'] = total_pdfs
                progress['total_extracted'] = total_extracted
                save_progress(progress)
                
            except Exception as e:
                logger.error(f"  ❌ Erro: {e}")
                progress.setdefault('errors', {})[name] = str(e)
                progress['failed'] = list(set(progress.get('failed', [])) | {name})
                save_progress(progress)
                # Re-attach listener
                try:
                    page.remove_listener('response', on_client_resp)
                except:
                    pass
                page.on('response', on_resp)
        
        await browser.close()
    
    progress['finished'] = datetime.now().isoformat()
    save_progress(progress)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"🏁 IMPORTAÇÃO JANEIRO v2 — CONCLUÍDA")
    logger.info(f"   Clientes processados: {len(done_set)}")
    logger.info(f"   PDFs baixados: {total_pdfs}")
    logger.info(f"   Apólices importadas: {total_extracted}")
    logger.info(f"   Falhas: {len(progress.get('failed', []))}")
    logger.info(f"{'='*60}")


if __name__ == '__main__':
    asyncio.run(run())
