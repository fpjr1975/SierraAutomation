#!/usr/bin/env python3
"""
OneDrive Importer — Genérico por mês
Uso: python3 import_mes.py "2 FEVEREIRO" "F8DA20F2479D8100!170700"
"""

import asyncio, logging, httpx, re, os, json, sys, base64
from pathlib import Path
from datetime import datetime

MES_NOME = sys.argv[1] if len(sys.argv) > 1 else "2 FEVEREIRO"
MES_ID = sys.argv[2] if len(sys.argv) > 2 else "F8DA20F2479D8100!170700"
MES_SAFE = re.sub(r'[<>:"/\\|?*\s]', '_', MES_NOME)

DOWNLOAD_DIR = Path(f"/root/sierra/onedrive_imports/{MES_SAFE}")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = f'/root/sierra/import_{MES_SAFE}.log'
PROGRESS_FILE = Path(f'/root/sierra/import_{MES_SAFE}_progress.json')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE)])
logger = logging.getLogger('import')

REDEEM = 'aHR0cHM6Ly8xZHJ2Lm1zL2YvYy9mOGRhMjBmMjQ3OWQ4MTAwL0lnQUFnWjFIOGlEYUlJRDRQSWtDQUFBQUFRRmQyMC13ZUl4WjU3aWVvdjBGSEtJP2U9NTpjeVVwWlkmYXQ9OQ'
CID = 'F8DA20F2479D8100'

def load_progress():
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {"done": [], "failed": [], "total_pdfs": 0, "total_extracted": 0, "started": datetime.now().isoformat()}

def save_progress(prog):
    PROGRESS_FILE.write_text(json.dumps(prog, indent=2, ensure_ascii=False))

def make_url(item_id):
    return f"https://onedrive.live.com/?redeem={REDEEM}&id={item_id}&cid={CID}"

async def get_api_key():
    with open('/root/.openclaw/agents/main/agent/auth-profiles.json') as f:
        auth = json.load(f)
        for k, v in auth.get('profiles', {}).items():
            if 'anthropic' in k:
                return v.get('token', '')
    return None

async def extract_with_ai(pdf_path, api_key):
    try:
        with open(pdf_path, 'rb') as f:
            pdf_b64 = base64.b64encode(f.read()).decode()
        if len(pdf_b64) < 100:
            return None
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post("https://api.anthropic.com/v1/messages",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": "claude-sonnet-4-20250514", "max_tokens": 4096, "messages": [{"role": "user", "content": [
                    {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
                    {"type": "text", "text": 'Analise este documento de seguro. Retorne JSON com: {"tipo_documento":"apolice|proposta|boleto|endosso|parcela|outro","seguradora":"","numero_apolice":"","numero_proposta":"","segurado":{"nome":"","cpf":""},"veiculo":{"placa":"","modelo":"","ano_modelo":"","chassi":""},"vigencia":{"inicio":"DD/MM/YYYY","fim":"DD/MM/YYYY"},"premio_total":0.0,"ramo":"auto|residencial|vida|empresarial|fianca|outro","franquia_casco":0.0} APENAS JSON, sem markdown.'}
                ]}]})
            if resp.status_code == 200:
                text = resp.json()['content'][0]['text'].strip()
                if text.startswith('```'): text = re.sub(r'^```\w*\n?', '', text); text = re.sub(r'\n?```$', '', text)
                return json.loads(text.strip())
            elif resp.status_code == 429:
                logger.warning("Rate limit — 30s..."); await asyncio.sleep(30)
            else:
                logger.error(f"API {resp.status_code}")
    except json.JSONDecodeError: pass
    except Exception as e: logger.error(f"Extração: {e}")
    return None

def _normalize_seg(nome):
    mapa = {'tokio':'Tokio Marine','porto':'Porto Seguro','bradesco':'Bradesco Seguros','mapfre':'Mapfre',
        'hdi':'HDI Seguros','allianz':'Allianz','azul':'Azul Seguros','itau':'Itaú Seguros','itaú':'Itaú Seguros',
        'zurich':'Zurich','liberty':'Liberty / Yelum','yelum':'Liberty / Yelum','suhai':'Suhai','alfa':'Alfa Seguros',
        'aliro':'Aliro','darwin':'Darwin','ezze':'Ezze Seguros','mitsui':'Mitsui','suíça':'Suíça','suica':'Suíça',
        'sura':'Sura','essor':'Essor','sompo':'Sompo'}
    for k,v in mapa.items():
        if k in nome.lower(): return v
    return nome.strip()[:50]

def _parse_date(s):
    if not s: return None
    for fmt in ['%d/%m/%Y','%Y-%m-%d']:
        try: return datetime.strptime(str(s), fmt).date()
        except: continue
    return None

async def save_to_db(client_name, doc_data, pdf_path):
    try:
        sys.path.insert(0, '/root/sierra')
        import database
        if not doc_data or doc_data.get('tipo_documento','') not in ('apolice','proposta','endosso'):
            return True
        seg = doc_data.get('segurado',{}); veic = doc_data.get('veiculo',{}); vig = doc_data.get('vigencia',{})
        nome = seg.get('nome','') or client_name
        seguradora = _normalize_seg(doc_data.get('seguradora',''))
        cliente_id = await database.upsert_cliente(1, nome, seg.get('cpf',''))
        veiculo_id = None
        placa = veic.get('placa','')
        if placa and len(placa) >= 7:
            veiculo_id = await database.upsert_veiculo(cliente_id, placa, marca_modelo=veic.get('modelo',''), ano_modelo=veic.get('ano_modelo',''))
        premio = doc_data.get('premio_total')
        if isinstance(premio, str):
            try: premio = float(premio.replace('R$','').replace('.','').replace(',','.').strip())
            except: premio = None
        pool = await database.get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""INSERT INTO apolices (corretora_id, cliente_id, veiculo_id, seguradora, numero_apolice, proposta, vigencia_inicio, vigencia_fim, premio, ramo, status)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) ON CONFLICT DO NOTHING""",
                1, cliente_id, veiculo_id, seguradora, doc_data.get('numero_apolice',''), doc_data.get('numero_proposta',''),
                _parse_date(vig.get('inicio','')), _parse_date(vig.get('fim','')),
                float(premio) if premio else None, doc_data.get('ramo','auto'), 'importada')
        logger.info(f"  ✅ DB: {nome[:35]} | {seguradora[:20]} | R${premio}")
        return True
    except Exception as e:
        logger.error(f"  ❌ DB: {e}"); return False

async def run():
    from playwright.async_api import async_playwright
    progress = load_progress()
    done_set = set(progress.get('done', []))
    api_key = await get_api_key()
    
    logger.info(f"🚀 IMPORTAÇÃO {MES_NOME} — INÍCIO (já feitos: {len(done_set)})")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        
        all_folders = {}
        async def on_resp(response):
            if response.status == 200 and 'json' in response.headers.get('content-type', ''):
                try:
                    body = await response.json()
                    if isinstance(body, dict):
                        for item in body.get('value', body.get('items', [])):
                            if isinstance(item, dict) and item.get('folder') and item.get('name') and item.get('id'):
                                all_folders[item['name']] = {'id': item['id'], 'size': item.get('size', 0)}
                except: pass
        
        page.on('response', on_resp)
        await page.goto(make_url(MES_ID), wait_until='networkidle', timeout=30000)
        await asyncio.sleep(4)
        
        prev = 0
        for i in range(20):
            await page.mouse.wheel(0, 3000); await asyncio.sleep(1)
            if len(all_folders) > prev: prev = len(all_folders)
            elif i > 5: break
        
        logger.info(f"📁 {len(all_folders)} pastas encontradas")
        to_process = {n: info for n, info in all_folders.items() if n not in done_set}
        logger.info(f"📋 A processar: {len(to_process)}")
        
        total_pdfs = progress.get('total_pdfs', 0)
        total_extracted = progress.get('total_extracted', 0)
        
        for i, (name, info) in enumerate(to_process.items()):
            logger.info(f"\n[{i+1}/{len(to_process)}] === {name} ===")
            try:
                client_pdfs = []
                async def on_client(response):
                    if response.status == 200 and 'json' in response.headers.get('content-type', ''):
                        try:
                            body = await response.json()
                            if isinstance(body, dict):
                                for item in body.get('value', body.get('items', [])):
                                    if isinstance(item, dict) and item.get('name', '').lower().endswith('.pdf'):
                                        dl = item.get('@microsoft.graph.downloadUrl') or item.get('@content.downloadUrl', '')
                                        if dl: client_pdfs.append({'name': item['name'], 'size': item.get('size', 0), 'url': dl})
                        except: pass
                
                page.remove_listener('response', on_resp)
                page.on('response', on_client)
                await page.goto(make_url(info['id']), wait_until='networkidle', timeout=20000)
                await asyncio.sleep(3)
                
                if client_pdfs:
                    logger.info(f"  📄 {len(client_pdfs)} PDFs")
                    safe = re.sub(r'[<>:"/\\|?*]', '_', name)[:80]
                    cdir = DOWNLOAD_DIR / safe; cdir.mkdir(parents=True, exist_ok=True)
                    
                    for pdf in client_pdfs:
                        pp = cdir / pdf['name']
                        if not pp.exists():
                            try:
                                async with httpx.AsyncClient(timeout=60) as dl:
                                    r = await dl.get(pdf['url'], follow_redirects=True)
                                    if r.status_code == 200 and len(r.content) > 500:
                                        pp.write_bytes(r.content); total_pdfs += 1
                            except: continue
                        
                        fl = pdf['name'].lower()
                        if any(kw in fl for kw in ['apolice','apólice','proposta','endosso','ap0olice']):
                            logger.info(f"  🔍 {pdf['name']}")
                            d = await extract_with_ai(str(pp), api_key)
                            if d:
                                pp.with_suffix('.json').write_text(json.dumps(d, indent=2, ensure_ascii=False))
                                if await save_to_db(name, d, str(pp)): total_extracted += 1
                        else:
                            logger.info(f"  💾 {pdf['name']}")
                else:
                    logger.info(f"  📭 Sem PDFs")
                
                page.remove_listener('response', on_client)
                page.on('response', on_resp)
                done_set.add(name)
                progress['done'] = list(done_set); progress['total_pdfs'] = total_pdfs; progress['total_extracted'] = total_extracted
                save_progress(progress)
            except Exception as e:
                logger.error(f"  ❌ {e}")
                progress['failed'] = list(set(progress.get('failed',[])) | {name}); save_progress(progress)
                try: page.remove_listener('response', on_client)
                except: pass
                page.on('response', on_resp)
        
        await browser.close()
    
    progress['finished'] = datetime.now().isoformat(); save_progress(progress)
    logger.info(f"\n{'='*60}")
    logger.info(f"🏁 {MES_NOME} CONCLUÍDO — {len(done_set)} clientes | {total_pdfs} PDFs | {total_extracted} extraídos | {len(progress.get('failed',[]))} falhas")
    logger.info(f"{'='*60}")

if __name__ == '__main__':
    asyncio.run(run())
