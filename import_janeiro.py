#!/usr/bin/env python3
"""
Importa todos os PDFs de Janeiro do OneDrive da Sierra.
Roda em background, salva progresso em JSON.
"""

import asyncio, logging, httpx, re, os, json, sys, time
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/root/sierra/import_janeiro.log')
    ]
)
logger = logging.getLogger('import_jan')

DOWNLOAD_DIR = Path("/root/sierra/onedrive_imports/1_JANEIRO")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
PROGRESS_FILE = Path("/root/sierra/import_janeiro_progress.json")

def load_progress():
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {"done": [], "failed": [], "total_pdfs": 0, "total_extracted": 0, "started": datetime.now().isoformat()}

def save_progress(prog):
    PROGRESS_FILE.write_text(json.dumps(prog, indent=2, ensure_ascii=False))


async def extract_apolice_with_ai(pdf_path: str) -> dict:
    """Extrai dados da apólice usando Anthropic API."""
    import base64
    
    try:
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
        
        if len(pdf_bytes) < 500:
            return None
        
        pdf_b64 = base64.b64encode(pdf_bytes).decode()
        
        # Usa Anthropic direto
        api_key = None
        auth_file = '/root/.openclaw/agents/main/agent/auth-profiles.json'
        if os.path.exists(auth_file):
            with open(auth_file) as f:
                auth = json.load(f)
                for k, v in auth.get('profiles', {}).items():
                    if 'anthropic' in k:
                        api_key = v.get('token', '')
                        break
        
        if not api_key:
            logger.error("Sem API key Anthropic")
            return None
        
        async with httpx.AsyncClient(timeout=60) as client:
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
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": pdf_b64
                                }
                            },
                            {
                                "type": "text",
                                "text": """Analise este documento de seguro. Identifique o TIPO (apolice, proposta, boleto, endosso, parcela, outro) e extraia dados em JSON:
{
  "tipo_documento": "apolice|proposta|boleto|endosso|parcela|outro",
  "seguradora": "",
  "numero_apolice": "",
  "numero_proposta": "",
  "segurado": {"nome": "", "cpf": "", "endereco": "", "cep": "", "cidade": "", "uf": "", "nascimento": ""},
  "veiculo": {"placa": "", "modelo": "", "ano_fabricacao": "", "ano_modelo": "", "chassi": ""},
  "vigencia": {"inicio": "DD/MM/YYYY", "fim": "DD/MM/YYYY"},
  "premio_total": 0.0,
  "ramo": "auto|residencial|vida|empresarial|fianca|outro",
  "coberturas": [{"nome": "", "valor": ""}],
  "franquia_casco": 0.0
}
Retorne APENAS o JSON, sem markdown."""
                            }
                        ]
                    }]
                }
            )
            
            if resp.status_code == 200:
                data = resp.json()
                text = data['content'][0]['text']
                # Parse JSON da resposta
                # Remove possível markdown
                text = text.strip()
                if text.startswith('```'):
                    text = re.sub(r'^```\w*\n?', '', text)
                    text = re.sub(r'\n?```$', '', text)
                return json.loads(text.strip())
            else:
                logger.error(f"Anthropic API {resp.status_code}: {resp.text[:200]}")
                return None
                
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error: {e}")
        return None
    except Exception as e:
        logger.error(f"Erro extração: {e}")
        return None


async def save_to_db(client_name: str, doc_data: dict, pdf_path: str):
    """Salva dados extraídos no banco PostgreSQL."""
    try:
        sys.path.insert(0, '/root/sierra')
        import database
        
        if not doc_data:
            return False
        
        tipo = doc_data.get('tipo_documento', 'outro')
        
        # Só importa apólices e propostas pro banco (boletos/parcelas são auxiliares)
        if tipo not in ('apolice', 'proposta', 'endosso'):
            logger.info(f"  Tipo '{tipo}' — salvo em disco, não importa pro banco")
            return True
        
        seg = doc_data.get('segurado', {})
        veic = doc_data.get('veiculo', {})
        
        nome = seg.get('nome', '') or client_name
        cpf = seg.get('cpf', '')
        
        # Upsert cliente
        nascimento = _parse_date(seg.get('nascimento', ''))
        cliente_id = await database.upsert_cliente(
            1,  # corretora_id Sierra
            nome, cpf, nascimento=nascimento
        )
        
        # Upsert veículo
        veiculo_id = None
        placa = veic.get('placa', '')
        if placa and len(placa) >= 7:
            veiculo_id = await database.upsert_veiculo(
                cliente_id, placa,
                marca_modelo=veic.get('modelo', ''),
                ano_fabricacao=veic.get('ano_fabricacao', ''),
                ano_modelo=veic.get('ano_modelo', ''),
            )
        
        # Insere apólice
        vig = doc_data.get('vigencia', {})
        premio = doc_data.get('premio_total')
        if isinstance(premio, str):
            premio = float(premio.replace('R$', '').replace('.', '').replace(',', '.').strip() or '0')
        
        seguradora = doc_data.get('seguradora', '')
        num_apolice = doc_data.get('numero_apolice', '')
        num_proposta = doc_data.get('numero_proposta', '')
        ramo = doc_data.get('ramo', 'auto')
        
        pool = await database.get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO apolices (corretora_id, cliente_id, veiculo_id, seguradora, 
                                      numero_apolice, proposta, vigencia_inicio, vigencia_fim, 
                                      premio, ramo, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT DO NOTHING
            """, 1, cliente_id, veiculo_id, seguradora,
                num_apolice, num_proposta,
                _parse_date(vig.get('inicio', '')), 
                _parse_date(vig.get('fim', '')),
                float(premio) if premio else None, 
                ramo, 'importada')
        
        logger.info(f"  ✅ DB: {nome} | {seguradora} | {num_apolice} | R${premio}")
        return True
        
    except Exception as e:
        logger.error(f"  ❌ DB erro: {e}")
        return False


def _parse_date(date_str):
    if not date_str:
        return None
    try:
        for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']:
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
    done_clients = set(progress.get('done', []))
    
    logger.info("🚀 IMPORTAÇÃO JANEIRO — INÍCIO")
    logger.info(f"Já processados anteriormente: {len(done_clients)}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        
        # Intercepta items do OneDrive
        captured = []
        
        async def on_resp(response):
            if response.status == 200:
                ct = response.headers.get('content-type', '')
                if 'json' in ct:
                    try:
                        body = await response.json()
                        captured.append(body)
                    except:
                        pass
        
        page.on('response', on_resp)
        
        # Navega direto pra Janeiro
        jan_url = 'https://onedrive.live.com/?redeem=aHR0cHM6Ly8xZHJ2Lm1zL2YvYy9mOGRhMjBmMjQ3OWQ4MTAwL0lnQUFnWjFIOGlEYUlJRDRQSWtDQUFBQUFRRmQyMC13ZUl4WjU3aWVvdjBGSEtJP2U9NTpjeVVwWlkmYXQ9OQ&id=F8DA20F2479D8100%21170696&cid=F8DA20F2479D8100'
        
        await page.goto(jan_url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(5)
        
        # Scroll pra carregar tudo
        for _ in range(10):
            await page.mouse.wheel(0, 2000)
            await asyncio.sleep(0.8)
        await asyncio.sleep(2)
        
        # Extrai pastas de clientes
        client_folders = []
        for body in captured:
            if isinstance(body, dict):
                for item in body.get('value', body.get('items', [])):
                    if isinstance(item, dict) and item.get('folder') and item.get('name'):
                        name = item['name']
                        if not re.match(r'^\d+\s+(JANEIRO|FEVEREIRO|MARÇO|ABRIL|MAIO|JUNHO|JULHO|AGOSTO|SETEMBRO|OUTUBRO|NOVEMBRO|DEZEMBRO)$', name):
                            if name not in ['CARTA VERDE']:
                                client_folders.append({
                                    'name': name,
                                    'id': item.get('id', ''),
                                    'size': item.get('size', 0),
                                })
        
        logger.info(f"📁 {len(client_folders)} pastas de clientes em Janeiro")
        
        # Filtra já processados
        to_process = [cf for cf in client_folders if cf['name'] not in done_clients]
        logger.info(f"📋 A processar: {len(to_process)} (já feitos: {len(done_clients)})")
        
        total_pdfs = progress.get('total_pdfs', 0)
        total_extracted = progress.get('total_extracted', 0)
        
        for i, cf in enumerate(to_process):
            name = cf['name']
            logger.info(f"\n[{i+1}/{len(to_process)}] === {name} ===")
            
            try:
                captured.clear()
                
                # Clica na pasta
                clicked = False
                # Tenta com nome truncado pra evitar problemas com nomes longos
                short_name = name[:35]
                for selector in [
                    f'[data-automationid="DetailsRow"] >> text="{short_name}"',
                    f'button:has-text("{short_name}")',
                    f'span:has-text("{short_name}")',
                ]:
                    try:
                        await page.locator(selector).first.dblclick(timeout=4000)
                        clicked = True
                        break
                    except:
                        continue
                
                if not clicked:
                    logger.warning(f"  ⚠️ Não consegui clicar — pulando")
                    progress['failed'].append(name)
                    save_progress(progress)
                    continue
                
                await asyncio.sleep(3)
                
                # Busca PDFs interceptados
                pdfs = []
                for body in captured:
                    if isinstance(body, dict):
                        for item in body.get('value', body.get('items', [])):
                            if isinstance(item, dict) and item.get('name', '').lower().endswith('.pdf'):
                                dl = (item.get('@microsoft.graph.downloadUrl') or 
                                     item.get('@content.downloadUrl') or '')
                                if dl:
                                    pdfs.append({
                                        'name': item['name'],
                                        'size': item.get('size', 0),
                                        'url': dl,
                                    })
                
                if pdfs:
                    logger.info(f"  📄 {len(pdfs)} PDFs encontrados")
                    
                    safe_name = re.sub(r'[<>:"/\\|?*]', '_', name)[:80]
                    client_dir = DOWNLOAD_DIR / safe_name
                    client_dir.mkdir(parents=True, exist_ok=True)
                    
                    for pdf in pdfs:
                        pdf_path = client_dir / pdf['name']
                        
                        # Baixa se não existe
                        if not pdf_path.exists():
                            try:
                                async with httpx.AsyncClient() as dl:
                                    resp = await dl.get(pdf['url'], timeout=60, follow_redirects=True)
                                    if resp.status_code == 200 and len(resp.content) > 500:
                                        pdf_path.write_bytes(resp.content)
                                        total_pdfs += 1
                                    else:
                                        logger.warning(f"  ⚠️ Download falhou: HTTP {resp.status_code}")
                                        continue
                            except Exception as de:
                                logger.error(f"  ❌ Download erro: {de}")
                                continue
                        
                        # Extrai dados (só pra apólices/propostas — identifica pelo nome do arquivo)
                        fname_lower = pdf['name'].lower()
                        is_worth_extracting = any(kw in fname_lower for kw in 
                            ['apolice', 'apólice', 'proposta', 'endosso', 'ap0olice'])
                        
                        if is_worth_extracting:
                            logger.info(f"  🔍 Extraindo: {pdf['name']}")
                            doc_data = await extract_apolice_with_ai(str(pdf_path))
                            if doc_data:
                                ok = await save_to_db(name, doc_data, str(pdf_path))
                                if ok:
                                    total_extracted += 1
                                    
                                # Salva JSON de extração
                                json_path = pdf_path.with_suffix('.json')
                                json_path.write_text(json.dumps(doc_data, indent=2, ensure_ascii=False))
                        else:
                            logger.info(f"  💾 Salvo: {pdf['name']} (boleto/parcela — não extrai)")
                else:
                    logger.warning(f"  ⚠️ Nenhum PDF encontrado")
                
                # Marca como feito
                done_clients.add(name)
                progress['done'] = list(done_clients)
                progress['total_pdfs'] = total_pdfs
                progress['total_extracted'] = total_extracted
                save_progress(progress)
                
                # Volta
                await page.go_back(wait_until='networkidle', timeout=15000)
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"  ❌ Erro geral: {e}")
                progress['failed'].append(name)
                save_progress(progress)
                # Recarrega
                try:
                    await page.goto(jan_url, wait_until='networkidle', timeout=30000)
                    await asyncio.sleep(4)
                    # Scroll novamente
                    for _ in range(5):
                        await page.mouse.wheel(0, 2000)
                        await asyncio.sleep(0.5)
                except:
                    pass
        
        await browser.close()
    
    # Resumo final
    progress['finished'] = datetime.now().isoformat()
    save_progress(progress)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"🏁 IMPORTAÇÃO JANEIRO — CONCLUÍDA")
    logger.info(f"   Clientes processados: {len(done_clients)}")
    logger.info(f"   PDFs baixados: {total_pdfs}")
    logger.info(f"   Apólices extraídas/importadas: {total_extracted}")
    logger.info(f"   Falhas: {len(progress.get('failed', []))}")
    logger.info(f"{'='*60}")


if __name__ == '__main__':
    asyncio.run(run())
