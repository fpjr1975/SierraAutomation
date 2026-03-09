#!/usr/bin/env python3
"""
OneDrive → Vértice DB — Sync diário
Verifica todas as pastas de meses, processa apenas clientes novos.
Roda via cron às 01:00 BRT (04:00 UTC).
"""

import asyncio, logging, httpx, re, os, json, sys, base64, subprocess
from pathlib import Path
from datetime import datetime

LOG_FILE = '/root/sierra/onedrive_sync.log'
SYNC_STATE = Path('/root/sierra/onedrive_sync_state.json')
BASE_DIR = Path('/root/sierra/onedrive_imports')
BASE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE)])
logger = logging.getLogger('sync')

REDEEM = 'aHR0cHM6Ly8xZHJ2Lm1zL2YvYy9mOGRhMjBmMjQ3OWQ4MTAwL0lnQUFnWjFIOGlEYUlJRDRQSWtDQUFBQUFRRmQyMC13ZUl4WjU3aWVvdjBGSEtJP2U9NTpjeVVwWlkmYXQ9OQ'
CID = 'F8DA20F2479D8100'
APOLICES_ID = 'F8DA20F2479D8100%21166206'

# Mapeamento de meses conhecidos (atualizado dinamicamente)
MESES_FIXOS = {
    '1 JANEIRO': 'F8DA20F2479D8100!170696',
    '2 FEVEREIRO': 'F8DA20F2479D8100!170700',
    '3 MARÇO': 'F8DA20F2479D8100!166207',
    '4 ABRIL': 'F8DA20F2479D8100!170701',
    '5 MAIO': 'F8DA20F2479D8100!170702',
    '6 JUNHO': 'F8DA20F2479D8100!170703',
    '7 JULHO': 'F8DA20F2479D8100!170704',
    '8 AGOSTO': 'F8DA20F2479D8100!170705',
    '9 SETEMBRO': 'F8DA20F2479D8100!170706',
    '10 OUTUBRO': 'F8DA20F2479D8100!170697',
    '11 NOVEMBRO': 'F8DA20F2479D8100!170698',
    '12 DEZEMBRO': 'F8DA20F2479D8100!170699',
}

def make_url(item_id):
    return f"https://onedrive.live.com/?redeem={REDEEM}&id={item_id}&cid={CID}"

def load_state():
    if SYNC_STATE.exists():
        return json.loads(SYNC_STATE.read_text())
    return {"last_sync": None, "months_done": {}, "total_synced": 0}

def save_state(state):
    SYNC_STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


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
                    {"type": "text", "text": 'Analise este documento de seguro. Retorne JSON: {"tipo_documento":"apolice|proposta|boleto|endosso|parcela|outro","seguradora":"","numero_apolice":"","numero_proposta":"","segurado":{"nome":"","cpf":""},"veiculo":{"placa":"","modelo":"","ano_modelo":"","chassi":""},"vigencia":{"inicio":"DD/MM/YYYY","fim":"DD/MM/YYYY"},"premio_total":0.0,"ramo":"auto|residencial|vida|empresarial|fianca|outro","franquia_casco":0.0} APENAS JSON.'}
                ]}]})
            if resp.status_code == 200:
                text = resp.json()['content'][0]['text'].strip()
                if text.startswith('```'): text = re.sub(r'^```\w*\n?', '', text); text = re.sub(r'\n?```$', '', text)
                return json.loads(text.strip())
            elif resp.status_code == 429:
                logger.warning("Rate limit — 60s..."); await asyncio.sleep(60); return None
            else:
                logger.error(f"API {resp.status_code}"); return None
    except: return None


def _normalize_seg(nome):
    mapa = {'tokio':'Tokio Marine','porto':'Porto Seguro','bradesco':'Bradesco Seguros','mapfre':'Mapfre',
        'hdi':'HDI Seguros','allianz':'Allianz','azul':'Azul Seguros','itau':'Itaú Seguros','itaú':'Itaú Seguros',
        'zurich':'Zurich','liberty':'Liberty / Yelum','yelum':'Liberty / Yelum','suhai':'Suhai','alfa':'Alfa Seguros',
        'aliro':'Aliro','darwin':'Darwin','ezze':'Ezze Seguros','mitsui':'Mitsui','suíça':'Suíça',
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
        return True
    except Exception as e:
        logger.error(f"  DB: {e}"); return False


async def sync_month(page, mes_nome, mes_id, state, api_key):
    """Sincroniza um mês — processa apenas pastas novas."""
    
    mes_safe = re.sub(r'[<>:"/\\|?*\s]', '_', mes_nome)
    month_dir = BASE_DIR / mes_safe
    month_dir.mkdir(parents=True, exist_ok=True)
    
    # Pastas já processadas neste mês
    done_key = f"done_{mes_safe}"
    done_set = set(state.get(done_key, []))
    
    # Coleta pastas do mês
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
    await page.goto(make_url(mes_id), wait_until='networkidle', timeout=30000)
    await asyncio.sleep(4)
    
    prev = 0
    for i in range(15):
        await page.mouse.wheel(0, 3000); await asyncio.sleep(1)
        if len(all_folders) > prev: prev = len(all_folders)
        elif i > 4: break
    
    page.remove_listener('response', on_resp)
    
    # Filtra novos
    new_folders = {n: info for n, info in all_folders.items() if n not in done_set}
    
    if not new_folders:
        logger.info(f"  {mes_nome}: nada novo ({len(done_set)} já processados)")
        return 0
    
    logger.info(f"  {mes_nome}: {len(new_folders)} novas pastas (de {len(all_folders)} total)")
    
    extracted = 0
    for name, info in new_folders.items():
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
            
            page.on('response', on_client)
            await page.goto(make_url(info['id']), wait_until='networkidle', timeout=20000)
            await asyncio.sleep(3)
            page.remove_listener('response', on_client)
            
            if client_pdfs:
                safe = re.sub(r'[<>:"/\\|?*]', '_', name)[:80]
                cdir = month_dir / safe; cdir.mkdir(parents=True, exist_ok=True)
                
                for pdf in client_pdfs:
                    pp = cdir / pdf['name']
                    if not pp.exists():
                        try:
                            async with httpx.AsyncClient(timeout=60) as dl:
                                r = await dl.get(pdf['url'], follow_redirects=True)
                                if r.status_code == 200 and len(r.content) > 500:
                                    pp.write_bytes(r.content)
                        except: continue
                    
                    fl = pdf['name'].lower()
                    if any(kw in fl for kw in ['apolice','apólice','proposta','endosso','ap0olice']):
                        d = await extract_with_ai(str(pp), api_key)
                        if d:
                            pp.with_suffix('.json').write_text(json.dumps(d, indent=2, ensure_ascii=False))
                            if await save_to_db(name, d, str(pp)):
                                extracted += 1
            
            done_set.add(name)
            state[done_key] = list(done_set)
            
        except Exception as e:
            logger.error(f"    ❌ {name}: {e}")
    
    return extracted


async def run_sync():
    """Sync completo — varre todos os meses."""
    
    state = load_state()
    api_key = await get_api_key()
    
    if not api_key:
        logger.error("Sem API key!"); return
    
    logger.info(f"{'='*60}")
    logger.info(f"🔄 SYNC ONEDRIVE → VÉRTICE — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    logger.info(f"{'='*60}")
    
    from playwright.async_api import async_playwright
    
    total_new = 0
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        
        # Processa cada mês (mais recente primeiro)
        meses_ordem = ['3 MARÇO', '2 FEVEREIRO', '1 JANEIRO', '12 DEZEMBRO', '11 NOVEMBRO', 
                       '10 OUTUBRO', '9 SETEMBRO', '8 AGOSTO', '7 JULHO', '6 JUNHO', 
                       '5 MAIO', '4 ABRIL']
        
        for mes in meses_ordem:
            mes_id = MESES_FIXOS.get(mes)
            if not mes_id:
                continue
            
            try:
                n = await sync_month(page, mes, mes_id, state, api_key)
                total_new += n
                save_state(state)
            except Exception as e:
                logger.error(f"  ❌ Erro mês {mes}: {e}")
        
        await browser.close()
    
    state['last_sync'] = datetime.now().isoformat()
    state['total_synced'] = state.get('total_synced', 0) + total_new
    save_state(state)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"✅ SYNC CONCLUÍDO — {total_new} novos registros importados")
    logger.info(f"   Total histórico sincronizado: {state['total_synced']}")
    logger.info(f"{'='*60}")


if __name__ == '__main__':
    asyncio.run(run_sync())
