#!/usr/bin/env python3
"""
OneDrive → Vértice DB Importer
Importa apólices do OneDrive da Sierra para o banco PostgreSQL.
"""

import asyncio
import base64
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, date
from pathlib import Path

import httpx

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('onedrive_importer')

# === OneDrive Config ===
SHARE_URL = "https://1drv.ms/f/c/f8da20f2479d8100/IgAAgZ1H8iDaIID4PIkCAAAAAQFd20-weIxZ57ieov0FHKI?e=5:cyUpZY&at=9"
DOWNLOAD_DIR = Path("/root/sierra/onedrive_imports")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# === Graph API helpers ===

def encode_sharing_url(url: str) -> str:
    """Converte URL de compartilhamento em token pra Graph API."""
    encoded = base64.urlsafe_b64encode(url.encode()).decode()
    # Remove padding
    encoded = encoded.rstrip('=')
    return f"u!{encoded}"


async def graph_get(client: httpx.AsyncClient, path: str, params: dict = None) -> dict:
    """Faz GET na Graph API via sharing token."""
    url = f"https://graph.microsoft.com/v1.0{path}"
    resp = await client.get(url, params=params, timeout=30)
    if resp.status_code == 200:
        return resp.json()
    else:
        logger.error(f"Graph API {resp.status_code}: {resp.text[:300]}")
        return None


async def list_shared_folder(client: httpx.AsyncClient, share_token: str) -> dict:
    """Lista o conteúdo da pasta compartilhada."""
    return await graph_get(client, f"/shares/{share_token}/driveItem/children")


async def list_folder_by_id(client: httpx.AsyncClient, share_token: str, item_id: str) -> dict:
    """Lista conteúdo de uma subpasta por ID."""
    return await graph_get(client, f"/shares/{share_token}/driveItem:/{item_id}:/children")


async def get_drive_item(client: httpx.AsyncClient, share_token: str) -> dict:
    """Pega info do item raiz compartilhado."""
    return await graph_get(client, f"/shares/{share_token}/driveItem")


# === Playwright-based approach (fallback) ===

async def enumerate_onedrive_playwright(base_url: str, folder_name: str = None) -> list:
    """Usa Playwright pra navegar pelo OneDrive e listar arquivos."""
    from playwright.async_api import async_playwright
    
    files = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        
        # Intercepta chamadas de API do OneDrive pra capturar listing
        api_responses = []
        
        async def handle_response(response):
            url = response.url
            if 'api.onedrive.com' in url or 'graph.microsoft.com' in url or '/_api/' in url:
                try:
                    body = await response.json()
                    api_responses.append({'url': url, 'data': body})
                except:
                    pass
        
        page.on('response', handle_response)
        
        await page.goto(base_url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(4)
        
        if folder_name:
            try:
                await page.click(f'text={folder_name}', timeout=8000)
                await asyncio.sleep(4)
            except Exception as e:
                logger.error(f"Não achei pasta '{folder_name}': {e}")
                await browser.close()
                return files
        
        # Extrai dados das respostas interceptadas
        for resp in api_responses:
            data = resp['data']
            if isinstance(data, dict) and 'value' in data:
                for item in data['value']:
                    if item.get('file'):
                        files.append({
                            'name': item.get('name', ''),
                            'size': item.get('size', 0),
                            'id': item.get('id', ''),
                            'download_url': item.get('@microsoft.graph.downloadUrl') or item.get('@content.downloadUrl', ''),
                            'mime': item.get('file', {}).get('mimeType', ''),
                            'modified': item.get('lastModifiedDateTime', ''),
                            'parent_path': item.get('parentReference', {}).get('path', ''),
                        })
                    elif item.get('folder'):
                        files.append({
                            'name': item.get('name', ''),
                            'type': 'folder',
                            'id': item.get('id', ''),
                            'child_count': item.get('folder', {}).get('childCount', 0),
                            'size': item.get('size', 0),
                        })
        
        # Fallback: scrape da página se API não retornou dados
        if not files:
            logger.info("API interception vazia, tentando scrape da página...")
            items = await page.query_selector_all('[role="row"], [data-automationid="DetailsRow"]')
            for item in items:
                text = await item.inner_text()
                files.append({'name': text.strip()[:100], 'type': 'unknown'})
        
        await browser.close()
    
    return files


async def navigate_and_list_subfolders(base_url: str, target_folder: str) -> list:
    """Navega até uma pasta e lista as subpastas (nomes de clientes)."""
    from playwright.async_api import async_playwright
    
    subfolders = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        
        api_items = []
        
        async def handle_response(response):
            url = response.url
            if ('onedrive' in url or 'sharepoint' in url or 'graph' in url or 'live.com' in url) and response.status == 200:
                try:
                    ct = response.headers.get('content-type', '')
                    if 'json' in ct:
                        body = await response.json()
                        api_items.append(body)
                except:
                    pass
        
        page.on('response', handle_response)
        
        # Carrega página raiz
        await page.goto(base_url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(3)
        
        # Navega pra Apólices
        try:
            await page.click(f'text={target_folder}', timeout=8000)
            await asyncio.sleep(3)
        except:
            logger.error(f"Pasta '{target_folder}' não encontrada")
            await browser.close()
            return []
        
        # Agora navega pro mês desejado
        page_url = page.url
        
        await browser.close()
    
    return subfolders, page_url


async def download_folder_pdfs(folder_url: str, month_folder: str, max_clients: int = None) -> list:
    """
    Navega dentro de uma pasta de mês, entra em cada subpasta de cliente,
    e baixa os PDFs encontrados.
    """
    from playwright.async_api import async_playwright
    
    downloaded = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        
        # Intercepta download URLs
        download_urls = {}
        
        async def handle_response(response):
            url = response.url
            ct = response.headers.get('content-type', '')
            if 'json' in ct and response.status == 200:
                try:
                    body = await response.json()
                    # Busca items com downloadUrl
                    if isinstance(body, dict):
                        items = body.get('value', body.get('items', []))
                        if isinstance(items, list):
                            for item in items:
                                if isinstance(item, dict):
                                    dl = item.get('@microsoft.graph.downloadUrl') or item.get('@content.downloadUrl', '')
                                    name = item.get('name', '')
                                    if dl and name.lower().endswith('.pdf'):
                                        download_urls[name] = {
                                            'url': dl,
                                            'size': item.get('size', 0),
                                            'id': item.get('id', ''),
                                        }
                except:
                    pass
        
        page.on('response', handle_response)
        
        # Vai pra URL da pasta do mês
        await page.goto(folder_url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(3)
        
        # Lista subpastas (nomes de clientes)
        # Pega todos os links/itens da lista
        rows = await page.query_selector_all('[data-automationid="DetailsRow"], [role="row"]')
        client_names = []
        for row in rows:
            try:
                name_el = await row.query_selector('[data-automationid="DetailsRowCell"] button, [data-automationid="name-column"]')
                if name_el:
                    name = await name_el.inner_text()
                    name = name.strip()
                    if name and name not in ['Nome', 'Name']:
                        client_names.append(name)
            except:
                pass
        
        if not client_names:
            # Fallback: pega texto de cada linha
            for row in rows:
                text = (await row.inner_text()).strip()
                first_col = text.split('\t')[0].split('\n')[0].strip()
                if first_col and first_col not in ['Nome', 'Name', 'Modificado', 'Modified', 'Tamanho', 'Size']:
                    client_names.append(first_col)
        
        logger.info(f"Encontrados {len(client_names)} clientes em {month_folder}")
        
        if max_clients:
            client_names = client_names[:max_clients]
        
        # Para cada cliente, entra na pasta e baixa PDFs
        for i, client_name in enumerate(client_names):
            logger.info(f"[{i+1}/{len(client_names)}] Processando: {client_name}")
            
            try:
                download_urls.clear()
                
                # Clica na pasta do cliente
                await page.click(f'text="{client_name}"', timeout=5000)
                await asyncio.sleep(3)
                
                # Verifica se interceptou PDFs
                if download_urls:
                    for pdf_name, pdf_info in download_urls.items():
                        # Baixa o PDF
                        client_dir = DOWNLOAD_DIR / month_folder / _sanitize(client_name)
                        client_dir.mkdir(parents=True, exist_ok=True)
                        pdf_path = client_dir / pdf_name
                        
                        if not pdf_path.exists():
                            logger.info(f"  📥 Baixando {pdf_name} ({pdf_info['size']//1024}KB)...")
                            async with httpx.AsyncClient() as dl_client:
                                resp = await dl_client.get(pdf_info['url'], timeout=60)
                                if resp.status_code == 200:
                                    pdf_path.write_bytes(resp.content)
                                    downloaded.append({
                                        'client': client_name,
                                        'file': pdf_name,
                                        'path': str(pdf_path),
                                        'size': len(resp.content),
                                    })
                                    logger.info(f"  ✅ Salvo: {pdf_path}")
                        else:
                            logger.info(f"  ⏩ Já existe: {pdf_name}")
                            downloaded.append({
                                'client': client_name,
                                'file': pdf_name,
                                'path': str(pdf_path),
                                'size': pdf_path.stat().st_size,
                            })
                else:
                    logger.warning(f"  ⚠️ Nenhum PDF interceptado para {client_name}")
                
                # Volta pra pasta do mês
                await page.go_back(wait_until='networkidle', timeout=15000)
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"  ❌ Erro com {client_name}: {e}")
                # Tenta voltar
                try:
                    await page.go_back(wait_until='networkidle', timeout=10000)
                    await asyncio.sleep(2)
                except:
                    # Se não consegue voltar, recarrega a URL do mês
                    await page.goto(folder_url, wait_until='networkidle', timeout=30000)
                    await asyncio.sleep(3)
        
        await browser.close()
    
    return downloaded


def _sanitize(name: str) -> str:
    """Sanitiza nome pra usar como diretório."""
    return re.sub(r'[<>:"/\\|?*]', '_', name)[:100]


# === PDF Processing ===

async def extract_apolice_data(pdf_path: str) -> dict:
    """Extrai dados de uma apólice PDF usando extractors ou IA."""
    try:
        # Tenta com extractors existentes
        sys.path.insert(0, '/root/sierra')
        from extractors import ExtractorFactory
        
        extractor = ExtractorFactory.get_extractor(pdf_path)
        if extractor:
            data = extractor.extract()
            if data:
                return {'source': 'extractor', 'data': data}
        
        # Fallback: AI extractor
        from ai_extractor import AIExtractor
        ai = AIExtractor(pdf_path)
        data = ai.extract()
        if data:
            return {'source': 'ai', 'data': data}
        
    except Exception as e:
        logger.error(f"Erro extraindo {pdf_path}: {e}")
    
    return None


async def import_to_db(client_name: str, pdf_data: dict, pdf_path: str, corretora_id: int = 1):
    """Importa dados extraídos do PDF pro banco."""
    sys.path.insert(0, '/root/sierra')
    import database
    
    data = pdf_data.get('data', {})
    
    # Extrai campos
    nome = data.get('segurado', {}).get('nome', '') or client_name
    cpf = data.get('segurado', {}).get('cpf', '')
    seguradora = data.get('seguradora', '')
    num_apolice = data.get('proposta', '') or data.get('apolice', '')
    
    # Vigência
    vig_inicio = data.get('vigencia', {}).get('inicio', '')
    vig_fim = data.get('vigencia', {}).get('fim', '')
    
    # Veículo
    placa = data.get('veiculo', {}).get('placa', '')
    modelo = data.get('veiculo', {}).get('modelo', '')
    ano_fab = data.get('veiculo', {}).get('ano_fabricacao', '')
    ano_mod = data.get('veiculo', {}).get('ano_modelo', '')
    
    # Prêmio
    premio = data.get('premio_total', '') or data.get('premio', {}).get('total', '')
    
    logger.info(f"  DB: {nome} | {seguradora} | {num_apolice} | {placa} | {premio}")
    
    try:
        # Upsert cliente
        nascimento = _parse_date(data.get('segurado', {}).get('nascimento', ''))
        cliente_id = await database.upsert_cliente(
            corretora_id, nome, cpf, nascimento=nascimento
        )
        
        # Upsert veículo (se tem placa)
        veiculo_id = None
        if placa:
            veiculo_id = await database.upsert_veiculo(
                cliente_id, placa,
                marca_modelo=modelo,
                ano_fabricacao=ano_fab,
                ano_modelo=ano_mod,
            )
        
        # Insere apólice
        await database.execute("""
            INSERT INTO apolices (corretora_id, cliente_id, veiculo_id, seguradora, 
                                  numero_apolice, vigencia_inicio, vigencia_fim, 
                                  premio_total, ramo, status, pdf_path)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT DO NOTHING
        """, corretora_id, cliente_id, veiculo_id, seguradora,
            num_apolice, _parse_date(vig_inicio), _parse_date(vig_fim),
            _parse_float(premio), 'auto', 'importada', pdf_path)
        
        return True
    except Exception as e:
        logger.error(f"  Erro DB: {e}")
        return False


def _parse_date(date_str: str):
    if not date_str:
        return None
    try:
        for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d.%m.%Y']:
            try:
                return datetime.strptime(date_str, fmt).date()
            except:
                continue
    except:
        pass
    return None


def _parse_float(val) -> float:
    if not val:
        return None
    try:
        if isinstance(val, (int, float)):
            return float(val)
        return float(str(val).replace('R$', '').replace('.', '').replace(',', '.').strip())
    except:
        return None


# === Main ===

async def run_pilot(month: str = "1 JANEIRO", max_clients: int = 5):
    """Roda importação piloto de um mês."""
    logger.info(f"🚀 Importação piloto: {month} (max {max_clients} clientes)")
    
    # Step 1: Tentar Graph API primeiro
    share_token = encode_sharing_url(SHARE_URL)
    logger.info(f"Share token: {share_token[:50]}...")
    
    async with httpx.AsyncClient() as client:
        # Testa acesso via Graph API
        root = await get_drive_item(client, share_token)
        if root:
            logger.info(f"✅ Graph API OK: {root.get('name', '?')}")
            # Lista filhos
            children = await list_shared_folder(client, share_token)
            if children and 'value' in children:
                for item in children['value']:
                    logger.info(f"  📁 {item.get('name', '?')} ({item.get('size', 0)//1024//1024}MB)")
            return  # TODO: implementar download via Graph
        else:
            logger.warning("Graph API não disponível, usando Playwright...")
    
    # Step 2: Fallback Playwright
    apolices_url = 'https://onedrive.live.com/?redeem=aHR0cHM6Ly8xZHJ2Lm1zL2YvYy9mOGRhMjBmMjQ3OWQ4MTAwL0lnQUFnWjFIOGlEYUlJRDRQSWtDQUFBQUFRRmQyMC13ZUl4WjU3aWVvdjBGSEtJP2U9NTpjeVVwWlkmYXQ9OQ&id=F8DA20F2479D8100%21166206&cid=F8DA20F2479D8100&sb=name&sd=1'
    
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        
        # Intercepta respostas JSON
        all_items = {}
        
        async def handle_response(response):
            if response.status == 200:
                ct = response.headers.get('content-type', '')
                if 'json' in ct:
                    try:
                        body = await response.json()
                        _extract_items(body, all_items)
                    except:
                        pass
        
        page.on('response', handle_response)
        
        # Vai pra Apólices
        logger.info("Navegando pra pasta Apólices...")
        await page.goto(apolices_url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(4)
        
        # Clica no mês
        logger.info(f"Clicando em '{month}'...")
        await page.click(f'text={month}', timeout=8000)
        await asyncio.sleep(4)
        
        month_url = page.url
        logger.info(f"URL do mês: {month_url}")
        
        # Scroll pra carregar todas as pastas
        for _ in range(5):
            await page.mouse.wheel(0, 1000)
            await asyncio.sleep(1)
        
        # Coleta nomes de clientes via interception
        client_folders = []
        for item_id, item in all_items.items():
            if item.get('type') == 'folder':
                client_folders.append(item)
        
        if not client_folders:
            # Fallback: scrape da página
            logger.info("Scraping nomes de clientes da página...")
            rows = await page.query_selector_all('[data-automationid="DetailsRow"]')
            for row in rows:
                text = (await row.inner_text()).strip().split('\n')[0].split('\t')[0]
                if text:
                    client_folders.append({'name': text})
        
        logger.info(f"📁 {len(client_folders)} pastas de clientes encontradas")
        
        if max_clients:
            client_folders = client_folders[:max_clients]
        
        # Entra em cada pasta e baixa PDFs
        total_downloaded = 0
        total_imported = 0
        
        for i, folder in enumerate(client_folders):
            client_name = folder.get('name', f'Cliente_{i}')
            logger.info(f"\n[{i+1}/{len(client_folders)}] === {client_name} ===")
            
            try:
                all_items.clear()
                
                # Clica na pasta
                await page.click(f'text="{client_name}"', timeout=5000)
                await asyncio.sleep(3)
                
                # Scroll pra carregar conteúdo
                await page.mouse.wheel(0, 500)
                await asyncio.sleep(1)
                
                # Busca PDFs nos items interceptados
                pdfs_found = {k: v for k, v in all_items.items() 
                             if v.get('name', '').lower().endswith('.pdf') and v.get('download_url')}
                
                if pdfs_found:
                    for pdf_name, pdf_info in pdfs_found.items():
                        client_dir = DOWNLOAD_DIR / _sanitize(month) / _sanitize(client_name)
                        client_dir.mkdir(parents=True, exist_ok=True)
                        pdf_path = client_dir / pdf_info['name']
                        
                        if not pdf_path.exists():
                            logger.info(f"  📥 Baixando: {pdf_info['name']} ({pdf_info.get('size',0)//1024}KB)")
                            async with httpx.AsyncClient() as dl:
                                resp = await dl.get(pdf_info['download_url'], timeout=60, follow_redirects=True)
                                if resp.status_code == 200 and len(resp.content) > 100:
                                    pdf_path.write_bytes(resp.content)
                                    total_downloaded += 1
                                    
                                    # Extrai dados
                                    extracted = await extract_apolice_data(str(pdf_path))
                                    if extracted:
                                        ok = await import_to_db(client_name, extracted, str(pdf_path))
                                        if ok:
                                            total_imported += 1
                                else:
                                    logger.warning(f"  ⚠️ Download falhou: {resp.status_code}")
                        else:
                            logger.info(f"  ⏩ Já existe: {pdf_info['name']}")
                else:
                    logger.warning(f"  ⚠️ Nenhum PDF encontrado")
                
                # Volta
                await page.go_back(wait_until='networkidle', timeout=15000)
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"  ❌ Erro: {e}")
                try:
                    await page.goto(month_url, wait_until='networkidle', timeout=30000)
                    await asyncio.sleep(3)
                except:
                    pass
        
        await browser.close()
    
    logger.info(f"\n{'='*50}")
    logger.info(f"📊 Resumo piloto {month}:")
    logger.info(f"   Clientes processados: {len(client_folders)}")
    logger.info(f"   PDFs baixados: {total_downloaded}")
    logger.info(f"   Registros importados: {total_imported}")
    logger.info(f"{'='*50}")


def _extract_items(body, items_dict: dict):
    """Extrai items de resposta JSON do OneDrive."""
    if isinstance(body, dict):
        # Formato OneDrive: {value: [{...}]}
        for item in body.get('value', body.get('items', [])):
            if isinstance(item, dict):
                name = item.get('name', '')
                item_id = item.get('id', name)
                dl_url = (item.get('@microsoft.graph.downloadUrl') or 
                         item.get('@content.downloadUrl') or
                         item.get('downloadUrl', ''))
                
                entry = {
                    'name': name,
                    'id': item_id,
                    'size': item.get('size', 0),
                    'download_url': dl_url,
                    'modified': item.get('lastModifiedDateTime', ''),
                }
                
                if item.get('folder'):
                    entry['type'] = 'folder'
                    entry['child_count'] = item.get('folder', {}).get('childCount', 0)
                elif item.get('file'):
                    entry['type'] = 'file'
                    entry['mime'] = item.get('file', {}).get('mimeType', '')
                
                items_dict[item_id] = entry


if __name__ == '__main__':
    month = sys.argv[1] if len(sys.argv) > 1 else "1 JANEIRO"
    max_c = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    asyncio.run(run_pilot(month, max_c))
