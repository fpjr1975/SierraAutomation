"""
sync_agilizador.py — Importa histórico de cotações do Agilizador (multicalculo.net)
para o banco de dados PostgreSQL do Projeto Vértice/Sierra.

Uso:
    /root/sierra/venv/bin/python sync_agilizador.py [--limit N] [--debug]
"""

import asyncio
import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, date
from typing import Optional, List, Dict, Any

import psycopg2
import psycopg2.extras
from playwright.async_api import async_playwright, Page, Response

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/root/sierra/debug/sync_agilizador.log"),
    ],
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
AGG_URL   = "https://aggilizador.com.br"
AGG_EMAIL = "contato@sierraseguros.com.br"
AGG_SENHA = "Tronca2660&&"

DB_DSN = "postgresql://sierra:SierraDB2026!!@localhost/sierra_db"
CORRETORA_ID = 1
DEBUG_DIR = "/root/sierra/debug"

# ── Helpers ───────────────────────────────────────────────────────────────────

def clean_placa(placa: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (placa or "").upper())


def parse_premio(valor) -> Optional[float]:
    """Converte string de prêmio (ex: 'R$ 1.234,56' ou 1234.56) para float."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    s = str(valor).replace("R$", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(s)
    except:
        return None


def parse_date(s) -> Optional[date]:
    """Converte string de data para date. Aceita dd/mm/yyyy, yyyy-mm-dd, etc."""
    if not s:
        return None
    if isinstance(s, date):
        return s
    s = str(s).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(s[:len(fmt)], fmt).date()
        except:
            continue
    return None


# ── DB ────────────────────────────────────────────────────────────────────────

def get_db():
    return psycopg2.connect(DB_DSN)


def upsert_cliente(cur, nome: str, cpf_cnpj: str = None, nascimento=None, telefone: str = None) -> int:
    """Insere ou retorna cliente existente. Retorna cliente_id."""
    nome = (nome or "").strip()
    cpf_cnpj = re.sub(r"\D", "", cpf_cnpj or "") or None

    # Tenta encontrar por CPF primeiro
    if cpf_cnpj:
        cur.execute(
            "SELECT id FROM clientes WHERE corretora_id = %s AND cpf_cnpj = %s",
            (CORRETORA_ID, cpf_cnpj)
        )
        row = cur.fetchone()
        if row:
            return row[0]

    # Tenta por nome exato (fallback)
    if not cpf_cnpj:
        cur.execute(
            "SELECT id FROM clientes WHERE corretora_id = %s AND LOWER(nome) = LOWER(%s) LIMIT 1",
            (CORRETORA_ID, nome)
        )
        row = cur.fetchone()
        if row:
            return row[0]

    # Insere novo
    nasc = parse_date(nascimento)
    cur.execute(
        """
        INSERT INTO clientes (corretora_id, nome, cpf_cnpj, nascimento, telefone, created_at, updated_at, status)
        VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), 'ativo')
        ON CONFLICT (corretora_id, cpf_cnpj) DO UPDATE SET nome = EXCLUDED.nome, updated_at = NOW()
        RETURNING id
        """,
        (CORRETORA_ID, nome, cpf_cnpj, nasc, telefone)
    )
    return cur.fetchone()[0]


def upsert_veiculo(cur, cliente_id: int, placa: str, marca_modelo: str = None,
                   ano_fabricacao: str = None, ano_modelo: str = None,
                   chassi: str = None, combustivel: str = None) -> int:
    """Insere ou retorna veículo. Retorna veiculo_id."""
    placa = clean_placa(placa)

    if placa:
        cur.execute(
            "SELECT id FROM veiculos WHERE corretora_id = %s AND placa = %s LIMIT 1",
            (CORRETORA_ID, placa)
        )
        row = cur.fetchone()
        if row:
            return row[0]

    cur.execute(
        """
        INSERT INTO veiculos (corretora_id, cliente_id, placa, marca_modelo,
                              ano_fabricacao, ano_modelo, chassi, combustivel, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        RETURNING id
        """,
        (CORRETORA_ID, cliente_id, placa or None, marca_modelo,
         str(ano_fabricacao) if ano_fabricacao else None,
         str(ano_modelo) if ano_modelo else None,
         chassi, combustivel)
    )
    return cur.fetchone()[0]


def cotacao_exists(cur, agilizador_uuid: str = None, veiculo_id: int = None,
                   created_at_date=None) -> Optional[int]:
    """Verifica se cotação já existe. Retorna id ou None."""
    # 1) Por UUID do Agilizador na URL
    if agilizador_uuid:
        cur.execute(
            "SELECT id FROM cotacoes WHERE agilizador_url LIKE %s LIMIT 1",
            (f"%{agilizador_uuid}%",)
        )
        row = cur.fetchone()
        if row:
            return row[0]

    # 2) Por veiculo + data (mesmo dia)
    if veiculo_id and created_at_date:
        cur.execute(
            """
            SELECT id FROM cotacoes
            WHERE veiculo_id = %s AND DATE(created_at) = %s AND corretora_id = %s
            LIMIT 1
            """,
            (veiculo_id, created_at_date, CORRETORA_ID)
        )
        row = cur.fetchone()
        if row:
            return row[0]

    return None


def insert_cotacao(cur, cliente_id: int, veiculo_id: int, agilizador_url: str,
                   crvl_data: dict, created_at: datetime, status: str = "calculada") -> int:
    """Insere cotação e retorna id."""
    cur.execute(
        """
        INSERT INTO cotacoes (corretora_id, cliente_id, veiculo_id, tipo, status,
                               agilizador_url, crvl_data, created_at)
        VALUES (%s, %s, %s, 'historico', %s, %s, %s, %s)
        RETURNING id
        """,
        (CORRETORA_ID, cliente_id, veiculo_id, status,
         agilizador_url,
         json.dumps(crvl_data) if crvl_data else None,
         created_at)
    )
    return cur.fetchone()[0]


def insert_resultado(cur, cotacao_id: int, seguradora: str, premio: float,
                     franquia: float = None, plano: str = None,
                     numero_cotacao: str = None, coberturas: str = None,
                     parcelas: str = None, mensagem: str = None):
    """Insere resultado de seguradora. ON CONFLICT DO NOTHING."""
    cur.execute(
        """
        INSERT INTO cotacao_resultados
            (cotacao_id, corretora_id, seguradora, premio, franquia, plano,
             numero_cotacao, mensagem, parcelas, status, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'ok', NOW())
        ON CONFLICT DO NOTHING
        """,
        (cotacao_id, CORRETORA_ID, seguradora, premio, franquia, plano,
         numero_cotacao, coberturas or mensagem, parcelas, )
    )


# ── Playwright helpers ────────────────────────────────────────────────────────

async def fechar_modais(page: Page):
    """Fecha modais/overlays."""
    try:
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.3)
    except:
        pass
    try:
        for texto in ["Fechar", "OK", "Entendido", "Continuar", "Prosseguir", "close", "Não"]:
            btn = page.locator(f'button:has-text("{texto}")')
            if await btn.count() > 0:
                await btn.first.click(force=True)
                await asyncio.sleep(0.3)
    except:
        pass
    try:
        await page.evaluate("""
            document.querySelectorAll('.cdk-overlay-backdrop').forEach(e => e.remove());
            document.querySelectorAll('.cdk-global-overlay-wrapper').forEach(e => e.remove());
            const oc = document.querySelector('.cdk-overlay-container');
            if (oc) oc.innerHTML = '';
            document.body.classList.remove('cdk-global-scrollblock');
        """)
        await asyncio.sleep(0.2)
    except:
        pass


async def login(page: Page):
    """Faz login no Agilizador."""
    logger.info(f"Navegando para login: {AGG_URL}/login")
    await page.goto(f"{AGG_URL}/login", timeout=60000)
    await page.wait_for_load_state("networkidle")

    await page.fill('input[formcontrolname="email"]', AGG_EMAIL)
    await asyncio.sleep(0.5)
    await page.fill('input[formcontrolname="senha"]', AGG_SENHA)
    await asyncio.sleep(0.5)
    await page.click('button:has-text("Entrar")')

    # Aguarda redirecionamento (até 20s)
    try:
        await page.wait_for_url(lambda url: "/login" not in url, timeout=20000)
    except:
        # Pode ter aparecido popup de termos — tenta continuar
        pass

    await asyncio.sleep(3)

    # Fecha popup "Prosseguir" se aparecer
    try:
        btn = page.locator('button:has-text("Prosseguir")')
        if await btn.count() > 0:
            await btn.click()
            await asyncio.sleep(2)
    except:
        pass

    # Aceita termos se aparecer
    try:
        terms_btn = page.locator('button:has-text("Aceitar"), button:has-text("Concordo"), mat-checkbox')
        if await terms_btn.count() > 0:
            await terms_btn.first.click()
            await asyncio.sleep(1)
            proceed = page.locator('button:has-text("Prosseguir"), button:has-text("Continuar")')
            if await proceed.count() > 0:
                await proceed.first.click()
                await asyncio.sleep(2)
    except:
        pass

    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(2)
    await fechar_modais(page)

    # Captura token JWT
    token = await page.evaluate("""
        () => {
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                const val = localStorage.getItem(key);
                if (val && val.startsWith('eyJ')) return val;
                try {
                    const obj = JSON.parse(val);
                    if (obj && obj.token) return obj.token;
                    if (obj && obj.access_token) return obj.access_token;
                } catch {}
            }
            for (let i = 0; i < sessionStorage.length; i++) {
                const key = sessionStorage.key(i);
                const val = sessionStorage.getItem(key);
                if (val && val.startsWith('eyJ')) return val;
            }
            return null;
        }
    """)
    if token:
        logger.info(f"Token JWT capturado: {token[:40]}...")
    else:
        logger.warning("Token JWT não encontrado no storage")

    logger.info(f"Login OK. URL atual: {page.url}")
    return token


# ── Interceptação de API ──────────────────────────────────────────────────────

class ApiInterceptor:
    """Intercepta respostas da API do Agilizador."""

    def __init__(self):
        self.captured: Dict[str, Any] = {}  # url → parsed_data
        self.list_endpoints: List[tuple] = []  # (url, data) das listagens
        self.detail_endpoints: Dict[str, Any] = {}  # uuid → data

    async def handle_response(self, response: Response):
        url = response.url
        try:
            if "api.multicalculo.net" not in url and "aggilizador.com.br" not in url:
                return
            if response.status != 200:
                return

            # Só processa JSON
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return

            text = await response.text()
            if not text or len(text) < 10:
                return

            data = json.loads(text)
            self.captured[url] = data

            # Salva para debug
            if len(self.captured) <= 50:
                fname = re.sub(r"[^a-z0-9]", "_", url.lower())[-60:]
                debug_path = os.path.join(DEBUG_DIR, f"api_{fname}.json")
                try:
                    with open(debug_path, "w") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                except:
                    pass

            # Classifica a resposta
            self._classify(url, data)

        except Exception as e:
            logger.debug(f"Interceptor err {url[:80]}: {e}")

    def _classify(self, url: str, data: Any):
        """Tenta identificar o tipo de endpoint."""
        # Só interessa endpoints de cotação/negócio
        url_lower = url.lower()
        is_cotacao_url = any(kw in url_lower for kw in [
            "negocio", "cotacao", "busca", "calculo/historico"
        ])
        # Endpoints de detalhes (versoes de cotação específica)
        is_versoes_url = "versoes" in url_lower or "orcamentos" in url_lower

        # Listagem de cotações — deve ser do endpoint certo
        if isinstance(data, dict):
            # Padrão: {data: [...]} com chave negocios ou seguradoNome
            if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
                first = data["data"][0] if isinstance(data["data"][0], dict) else {}
                has_cotacao_keys = any(k in first for k in [
                    "seguradoNome", "seguradoCpfCnpj", "negocios",
                    "placa", "veiculo", "idIntegracao"
                ])
                if has_cotacao_keys:
                    logger.info(f"📋 Listagem (data) encontrada: {url[:80]} ({len(data['data'])} items)")
                    self.list_endpoints.append((url, data))

        elif isinstance(data, list) and len(data) > 0:
            first = data[0] if isinstance(data[0], dict) else {}

            # Versões de uma cotação específica
            if is_versoes_url and ("calculos" in first or "versaoAtual" in first or "configuracoes" in first):
                uuid_match = re.search(r"([a-f0-9-]{36})", url)
                if uuid_match:
                    self.detail_endpoints[uuid_match.group(1)] = data[-1]  # última versão
                    logger.debug(f"Versões: {url[:80]}")

            # Array de cotações direto (formato alternativo)
            elif is_cotacao_url:
                has_cotacao_keys = any(k in first for k in [
                    "seguradoNome", "seguradoCpfCnpj", "negocios",
                    "placa", "idIntegracao", "negocioId"
                ])
                if has_cotacao_keys:
                    logger.info(f"📋 Lista (array) encontrada: {url[:80]} ({len(data)} items)")
                    self.list_endpoints.append((url, data))


# ── Extração de cotações ──────────────────────────────────────────────────────

def extract_cotacoes_from_list(data: Any) -> List[Dict]:
    """Extrai lista normalizada de cotações de diferentes formatos de API.
    
    Para o endpoint busca/v2 com modo=2:
    - data.data[] = array de grupos por segurado
    - Cada item tem: seguradoCpfCnpj, seguradoNome, negocios[]
    - Cada negocio tem: id, idIntegracao, ramo, vigenciaIni, createdAt, etc.
    
    Expande os negocios em cotações individuais.
    """
    items = []

    # Estrutura: {data: [grupos_por_segurado]}
    if isinstance(data, dict):
        if "data" in data and isinstance(data["data"], list) and data["data"]:
            # Cada elemento é um grupo por segurado com array negocios[]
            for group in data["data"]:
                if isinstance(group, dict):
                    # Dados do segurado
                    segurado_cpf = group.get("seguradoCpfCnpj", "")
                    segurado_nome = group.get("seguradoNome", "")
                    
                    # Array negocios[] - cada um é uma cotação
                    for negocio in group.get("negocios", []):
                        if isinstance(negocio, dict):
                            negocio["seguradoCpfCnpj"] = segurado_cpf
                            negocio["seguradoNome"] = segurado_nome
                            if "nomeSegurado" in negocio:
                                del negocio["nomeSegurado"]  # evitar duplicata
                            items.append(negocio)
        elif "content" in data and isinstance(data["content"], list):
            items = data["content"]
        elif "cotacoes" in data and isinstance(data["cotacoes"], list):
            items = data["cotacoes"]
        elif any(k in data for k in ["seguradoNome", "seguradoCpfCnpj", "idIntegracao"]):
            items = [data]
    elif isinstance(data, list) and data:
        items = data

    return items


def parse_cotacao_item(item: Dict) -> Dict:
    """
    Normaliza um item da lista de cotações para formato interno.
    Tenta vários campos/nomes comuns da API.
    """
    def get(*keys):
        for k in keys:
            v = item.get(k)
            if v is not None:
                return v
            # nested: "veiculo.placa" → item.get("veiculo", {}).get("placa")
            if "." in k:
                parts = k.split(".", 1)
                sub = item.get(parts[0])
                if isinstance(sub, dict):
                    v = sub.get(parts[1])
                    if v is not None:
                        return v
        return None

    # UUID/ID da cotação
    uuid = get("uuid", "id", "cotacaoUuid", "cotacaoId")
    created_at_raw = get("dataCalculo", "createdAt", "created_at", "dataCotacao",
                         "dataVigenciaIni", "data")

    # Segurado/Cliente
    segurado_nome = get("nomeSegurado", "segurado", "cliente", "nome",
                        "segurado.nome", "cliente.nome")
    segurado_cpf = get("cpfSegurado", "cpf", "cpfCnpj", "segurado.cpf",
                       "cliente.cpf", "segurado.cpfCnpj")

    # Veículo
    placa = get("placa", "veiculo.placa", "veiculoPlaca")
    marca_modelo = get("marcaModelo", "descricaoVeiculo", "veiculo.marcaModelo",
                       "veiculo.descricao", "modeloVeiculo", "veiculo")
    if isinstance(marca_modelo, dict):
        marca_modelo = marca_modelo.get("descricao") or marca_modelo.get("marcaModelo") or str(marca_modelo)
    ano_fab = get("anoFabricacao", "anoFab", "veiculo.anoFabricacao", "ano")
    ano_mod = get("anoModelo", "anoMod", "veiculo.anoModelo")
    chassi = get("chassi", "veiculo.chassi")

    # Nascimento
    nascimento = get("dataNascimento", "dataNasc", "segurado.dataNascimento")

    # URL do Agilizador para esta cotação
    if uuid:
        agilizador_url = f"{AGG_URL}/cotacao/auto/resultados/{uuid}"
    else:
        agilizador_url = None

    return {
        "uuid": str(uuid) if uuid else None,
        "agilizador_url": agilizador_url,
        "created_at_raw": created_at_raw,
        "segurado_nome": segurado_nome,
        "segurado_cpf": segurado_cpf,
        "nascimento": nascimento,
        "placa": clean_placa(str(placa)) if placa else None,
        "marca_modelo": str(marca_modelo) if marca_modelo else None,
        "ano_fabricacao": str(ano_fab) if ano_fab else None,
        "ano_modelo": str(ano_mod) if ano_mod else None,
        "chassi": str(chassi) if chassi else None,
        "_raw": item,
    }


def parse_resultados_from_versoes(versoes_data: Any) -> List[Dict]:
    """
    Extrai resultados (seguradoras/prêmios) dos dados de versões de uma cotação.
    Formato esperado: lista de versões, cada uma com calculos[].resultados[]
    """
    results = []
    versoes = versoes_data if isinstance(versoes_data, list) else [versoes_data]

    # Pega a última versão (mais recente)
    if not versoes:
        return []

    latest = versoes[-1] if isinstance(versoes[-1], dict) else versoes[0]
    calculos = latest.get("calculos", [])

    seen = set()  # evita duplicatas por seguradora
    for calc in calculos:
        seg_nome = (calc.get("nomeSeguradora") or calc.get("seguradoraTxt") or "").strip()
        if not seg_nome:
            continue

        res_list = calc.get("resultados", [])
        if not res_list:
            # Seguradora sem resultado
            key = seg_nome.lower()
            if key not in seen:
                seen.add(key)
                results.append({
                    "seguradora": seg_nome,
                    "premio": None,
                    "franquia": None,
                    "plano": None,
                    "numero": None,
                    "coberturas": None,
                    "mensagem": calc.get("mensagemErro") or "Sem resultado",
                })
            continue

        for res in res_list:
            premio = parse_premio(res.get("premio"))
            # Filtra apenas resultados com prêmio (coberturas compreensivas)
            if premio is None:
                continue

            plano = (res.get("identificacao") or res.get("cobertura") or
                     res.get("nomePacote") or "").strip()
            key = f"{seg_nome.lower()}|{plano.lower()}"
            if key in seen:
                continue
            seen.add(key)

            results.append({
                "seguradora": seg_nome,
                "premio": premio,
                "franquia": parse_premio(res.get("franquia")),
                "plano": plano,
                "numero": str(res.get("numeroCotacao") or res.get("identificacao") or ""),
                "coberturas": res.get("coberturas") or res.get("cobertura"),
                "mensagem": res.get("mensagemErro"),
            })

    return results


# ── Sync principal ────────────────────────────────────────────────────────────

async def fetch_versoes_for_cotacao(page: Page, uuid: str) -> Optional[Any]:
    """Busca os detalhes (versões/resultados) de uma cotação pelo UUID."""
    api_url = f"https://api.multicalculo.net/calculo/cotacao/versoes/{uuid}"
    try:
        # Tenta via fetch no contexto do browser (com cookies)
        resp_text = await page.evaluate(f"""
            async () => {{
                try {{
                    const r = await fetch('{api_url}', {{credentials: 'include'}});
                    if (r.status !== 200) return null;
                    return await r.text();
                }} catch(e) {{ return null; }}
            }}
        """)
        if resp_text:
            return json.loads(resp_text)
    except Exception as e:
        logger.debug(f"fetch versoes {uuid}: {e}")

    # Tenta via Playwright request
    try:
        api_resp = await page.context.request.get(api_url)
        if api_resp.ok:
            return json.loads(await api_resp.text())
    except Exception as e:
        logger.debug(f"playwright request versoes {uuid}: {e}")

    return None


async def navigate_to_cotacoes_list(page: Page, interceptor: ApiInterceptor):
    """Navega para a lista de cotações e aguarda carregamento."""
    logger.info("Navegando para lista de cotações...")

    # Tenta a página principal
    await page.goto(f"{AGG_URL}/cotacao/auto", timeout=30000)
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(3)
    await fechar_modais(page)

    # Procura link/botão para histórico de cotações
    hist_selectors = [
        'a:has-text("Histórico")',
        'a:has-text("Meus Cálculos")',
        'a:has-text("Cotações")',
        'button:has-text("Histórico")',
        '[routerlink*="historico"]',
        '[routerlink*="cotacoes"]',
        'a[href*="historico"]',
        'a[href*="cotacoes"]',
        'mat-nav-list a',
    ]

    for sel in hist_selectors:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                href = await el.get_attribute("href") or ""
                text = await el.inner_text()
                logger.info(f"Encontrou link: '{text.strip()}' → {href}")
                if any(kw in (href + text).lower() for kw in ["histor", "calc", "cotac", "lista"]):
                    await el.click(force=True)
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(3)
                    logger.info(f"Navegou para: {page.url}")
                    break
        except:
            pass

    # Screenshot de debug
    try:
        await page.screenshot(path=f"{DEBUG_DIR}/lista_cotacoes.png", full_page=False)
    except:
        pass


async def fetch_list_via_api(page: Page, interceptor: ApiInterceptor,
                              limit: int = 200) -> List[Dict]:
    """
    Tenta descobrir e consumir o endpoint de listagem de cotações.
    Retorna lista de itens de cotação normalizados.
    """
    all_items = []
    found_list = False

    # Primeiro aguarda interceptações ao navegar
    await navigate_to_cotacoes_list(page, interceptor)
    await asyncio.sleep(2)

    # Verifica se já capturamos listagens via interceptação
    if interceptor.list_endpoints:
        for url, data in interceptor.list_endpoints:
            items = extract_cotacoes_from_list(data)
            if items:
                logger.info(f"Listagem interceptada: {len(items)} cotações em {url[:80]}")
                all_items.extend(items)
                found_list = True

    # Se não interceptou, tenta endpoints comuns diretamente
    if not found_list:
        logger.info("Nenhuma listagem interceptada, tentando endpoints diretos...")

        candidate_endpoints = [
            # Padrões mais comuns de APIs Spring/Angular
            "https://api.multicalculo.net/calculo/cotacao?size=100&page=0&sort=createdAt,desc",
            "https://api.multicalculo.net/calculo/cotacao/list?limit=100",
            "https://api.multicalculo.net/calculo/cotacao/historico?size=100",
            "https://api.multicalculo.net/calculo/historico?size=100&page=0",
            "https://api.multicalculo.net/cotacao?size=100&page=0",
            "https://api.multicalculo.net/calculo?size=100&page=0",
            "https://api.multicalculo.net/calculo/cotacao/auto?size=100",
        ]

        for ep in candidate_endpoints:
            try:
                resp_text = await page.evaluate(f"""
                    async () => {{
                        try {{
                            const r = await fetch('{ep}', {{credentials: 'include', headers: {{'Accept': 'application/json'}}}});
                            if (r.status !== 200) return null;
                            const ct = r.headers.get('content-type') || '';
                            if (!ct.includes('json')) return null;
                            return await r.text();
                        }} catch(e) {{ return null; }}
                    }}
                """)
                if resp_text:
                    try:
                        data = json.loads(resp_text)
                        items = extract_cotacoes_from_list(data)
                        if items:
                            logger.info(f"✅ Endpoint funcionou: {ep} → {len(items)} itens")
                            all_items.extend(items)
                            found_list = True
                            # Tenta paginar
                            if isinstance(data, dict) and "totalPages" in data:
                                total_pages = data.get("totalPages", 1)
                                logger.info(f"Total de páginas: {total_pages}")
                                for pg in range(1, min(total_pages, 20)):  # max 20 pages
                                    if len(all_items) >= limit:
                                        break
                                    page_ep = re.sub(r"page=\d+", f"page={pg}", ep)
                                    page_ep = re.sub(r"&size=\d+", f"&size=100", page_ep)
                                    resp2 = await page.evaluate(f"""
                                        async () => {{
                                            try {{
                                                const r = await fetch('{page_ep}', {{credentials: 'include'}});
                                                if (r.status !== 200) return null;
                                                return await r.text();
                                            }} catch(e) {{ return null; }}
                                        }}
                                    """)
                                    if resp2:
                                        d2 = json.loads(resp2)
                                        items2 = extract_cotacoes_from_list(d2)
                                        if items2:
                                            all_items.extend(items2)
                                            logger.info(f"Página {pg}: +{len(items2)} itens")
                                        else:
                                            break
                                    await asyncio.sleep(1)
                            break
                    except:
                        pass
            except:
                pass
            await asyncio.sleep(0.5)

    # Se ainda não achou, tenta pegar UUIDs da página via DOM
    if not found_list:
        logger.info("Tentando extrair UUIDs via DOM da página...")
        try:
            page_html = await page.content()
            # Salva para análise
            with open(f"{DEBUG_DIR}/pagina_cotacoes.html", "w") as f:
                f.write(page_html)

            # Extrai UUIDs do HTML (cotação URLs)
            uuid_pattern = r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'
            uuids = list(set(re.findall(uuid_pattern, page_html)))
            if uuids:
                logger.info(f"UUIDs encontrados no DOM: {len(uuids)}")
                for uuid in uuids[:limit]:
                    all_items.append({"uuid": uuid})
        except Exception as e:
            logger.warning(f"Erro ao extrair UUIDs: {e}")

    # Verifica também as captured APIs (pode ter dados de cotação individual carregada)
    if not all_items:
        for url, data in interceptor.captured.items():
            if isinstance(data, list) and len(data) > 0:
                first = data[0] if isinstance(data[0], dict) else {}
                if any(k in first for k in ["uuid", "placa", "segurado", "dataCalculo"]):
                    items = extract_cotacoes_from_list(data)
                    if items:
                        logger.info(f"Dados de cotação em: {url[:80]} ({len(items)} items)")
                        all_items.extend(items)

    return all_items[:limit]


async def scroll_and_collect_cotacoes(page: Page, interceptor: ApiInterceptor, limit: int = 200) -> List[Dict]:
    """
    Abordagem alternativa: navega pela lista visível na UI e coleta dados via DOM.
    """
    logger.info("Tentando coleta via scroll na UI...")
    cotacoes_ui = []

    try:
        # Aguarda carregamento de cards
        await page.wait_for_selector(
            '.cotacao-item, .card-cotacao, mat-card, .historico-item, tr.ng-star-inserted',
            timeout=10000
        )
    except:
        logger.warning("Nenhum card/row de cotação detectado via seletor padrão")

    try:
        # Scroll down para carregar mais
        for _ in range(10):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.5)
            if len(cotacoes_ui) >= limit:
                break

        # Extrai dados visíveis
        cotacoes_ui = await page.evaluate("""
            () => {
                const results = [];
                // Procura linhas de tabela ou cards
                const rows = document.querySelectorAll('tr[class*="ng-star"], .cotacao-item, mat-row, .historico-item');
                rows.forEach(row => {
                    const text = row.innerText || '';
                    const links = row.querySelectorAll('a[href*="resultados"], a[href*="cotacao"]');
                    const href = links.length > 0 ? links[0].href : '';
                    
                    // UUID da cotação
                    const uuidMatch = href.match(/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/);
                    if (!uuidMatch) return;
                    
                    results.push({
                        uuid: uuidMatch[1],
                        href: href,
                        text: text.trim().substring(0, 200)
                    });
                });
                return results;
            }
        """)

        if cotacoes_ui:
            logger.info(f"Coletados {len(cotacoes_ui)} itens via DOM scroll")
    except Exception as e:
        logger.warning(f"Erro na coleta DOM: {e}")

    return cotacoes_ui


# ── Main sync ─────────────────────────────────────────────────────────────────

async def sync_cotacoes(limit: int = 200, debug: bool = False):
    """Função principal de sincronização."""
    os.makedirs(DEBUG_DIR, exist_ok=True)

    stats = {
        "cotacoes_total": 0,
        "cotacoes_novas": 0,
        "cotacoes_skip": 0,
        "clientes_novos": 0,
        "resultados_inseridos": 0,
        "erros": 0,
    }

    interceptor = ApiInterceptor()

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"]
    )
    context = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
    page = await context.new_page()

    # Registra interceptador
    page.on("response", interceptor.handle_response)

    try:
        # Login
        logger.info("=" * 60)
        logger.info("🔐 Fazendo login no Agilizador...")
        jwt_token = await login(page)

        await asyncio.sleep(1)

        # Coleta lista de cotações
        logger.info("=" * 60)
        logger.info(f"📋 Coletando lista de cotações (limit={limit})...")
        raw_list = await fetch_list_via_api(page, interceptor, limit=limit)

        if not raw_list:
            # Tenta abordagem alternativa via scroll
            raw_list = await scroll_and_collect_cotacoes(page, interceptor, limit=limit)

        if not raw_list:
            logger.error("❌ Não conseguiu obter lista de cotações. Verifique debug/pagina_cotacoes.html")
            # Dump de todos os endpoints capturados para análise
            logger.info(f"Endpoints capturados ({len(interceptor.captured)}):")
            for url in list(interceptor.captured.keys())[:30]:
                data = interceptor.captured[url]
                dtype = type(data).__name__
                dlen = len(data) if isinstance(data, (list, dict)) else "?"
                logger.info(f"  {dtype}[{dlen}] {url[:100]}")
            return stats

        logger.info(f"✅ {len(raw_list)} cotações encontradas na lista")

        # Processa cada cotação
        db = get_db()
        cur = db.cursor()

        for i, raw_item in enumerate(raw_list[:limit]):
            if i >= limit:
                break

            cotacao = parse_cotacao_item(raw_item)
            uuid = cotacao.get("uuid")
            stats["cotacoes_total"] += 1

            if i > 0 and i % 10 == 0:
                logger.info(f"📊 Progresso: {i}/{min(len(raw_list), limit)} | "
                            f"novas={stats['cotacoes_novas']} skip={stats['cotacoes_skip']} "
                            f"erros={stats['erros']}")

            # Busca detalhes (versões/resultados) se não temos ainda
            versoes_data = None
            if uuid:
                versoes_data = interceptor.detail_endpoints.get(uuid)
                if not versoes_data:
                    await asyncio.sleep(1)  # rate limit
                    versoes_data = await fetch_versoes_for_cotacao(page, uuid)
                    if versoes_data:
                        interceptor.detail_endpoints[uuid] = versoes_data

            # Enriquece dados com info das versões
            if versoes_data:
                versao = versoes_data if isinstance(versoes_data, dict) else (
                    versoes_data[-1] if isinstance(versoes_data, list) and versoes_data else {}
                )
                # Preenche campos faltantes do item com dados das versões
                if not cotacao.get("segurado_nome"):
                    cot_data = versao.get("cotacao") or versao
                    cotacao["segurado_nome"] = (
                        cot_data.get("nomeSegurado") or
                        cot_data.get("segurado") or
                        cotacao.get("segurado_nome")
                    )
                if not cotacao.get("segurado_cpf"):
                    cot_data = versao.get("cotacao") or versao
                    cotacao["segurado_cpf"] = (
                        cot_data.get("cpfSegurado") or
                        cot_data.get("cpf") or
                        cotacao.get("segurado_cpf")
                    )
                if not cotacao.get("placa"):
                    cot_data = versao.get("cotacao") or versao
                    placa_raw = (
                        cot_data.get("placa") or
                        (cot_data.get("veiculo") or {}).get("placa") if isinstance(cot_data.get("veiculo"), dict) else None
                    )
                    cotacao["placa"] = clean_placa(str(placa_raw)) if placa_raw else None

            # Valida dados mínimos
            nome = (cotacao.get("segurado_nome") or "").strip()
            placa = cotacao.get("placa") or ""
            if not nome and not placa and not uuid:
                logger.debug(f"Item {i}: sem dados suficientes, skip")
                stats["cotacoes_skip"] += 1
                continue

            if not nome:
                nome = f"Cliente_{placa or uuid or i}"

            # Parse data
            created_at = None
            if cotacao.get("created_at_raw"):
                dt = parse_date(cotacao["created_at_raw"])
                if dt:
                    created_at = datetime.combine(dt, datetime.min.time())
            if not created_at:
                created_at = datetime.now()

            try:
                # Clientes
                cliente_existia = False
                cpf = cotacao.get("segurado_cpf") or ""
                cpf_clean = re.sub(r"\D", "", cpf)
                if cpf_clean:
                    cur.execute("SELECT id FROM clientes WHERE corretora_id=%s AND cpf_cnpj=%s",
                                (CORRETORA_ID, cpf_clean))
                    row = cur.fetchone()
                    cliente_existia = row is not None

                cliente_id = upsert_cliente(
                    cur,
                    nome=nome,
                    cpf_cnpj=cpf_clean or None,
                    nascimento=cotacao.get("nascimento"),
                )
                if not cliente_existia and cpf_clean:
                    stats["clientes_novos"] += 1
                db.commit()

                # Veículos
                veiculo_id = upsert_veiculo(
                    cur,
                    cliente_id=cliente_id,
                    placa=placa,
                    marca_modelo=cotacao.get("marca_modelo"),
                    ano_fabricacao=cotacao.get("ano_fabricacao"),
                    ano_modelo=cotacao.get("ano_modelo"),
                    chassi=cotacao.get("chassi"),
                )
                db.commit()

                # Verifica se cotação já existe
                existing_id = cotacao_exists(
                    cur,
                    agilizador_uuid=uuid,
                    veiculo_id=veiculo_id,
                    created_at_date=created_at.date() if created_at else None,
                )
                if existing_id:
                    logger.debug(f"Cotação já existe: {uuid or placa} → id={existing_id}")
                    stats["cotacoes_skip"] += 1
                    continue

                # Insere cotação
                agilizador_url = cotacao.get("agilizador_url") or (
                    f"{AGG_URL}/cotacao/auto/resultados/{uuid}" if uuid else None
                )
                crvl_data = {
                    "placa": placa,
                    "marca_modelo": cotacao.get("marca_modelo"),
                    "ano_fabricacao": cotacao.get("ano_fabricacao"),
                    "ano_modelo": cotacao.get("ano_modelo"),
                    "chassi": cotacao.get("chassi"),
                }
                cotacao_id = insert_cotacao(
                    cur,
                    cliente_id=cliente_id,
                    veiculo_id=veiculo_id,
                    agilizador_url=agilizador_url,
                    crvl_data=crvl_data,
                    created_at=created_at,
                )
                db.commit()
                stats["cotacoes_novas"] += 1

                # Insere resultados
                if versoes_data:
                    resultados = parse_resultados_from_versoes(versoes_data)
                    for res in resultados:
                        insert_resultado(
                            cur,
                            cotacao_id=cotacao_id,
                            seguradora=res["seguradora"],
                            premio=res["premio"],
                            franquia=res.get("franquia"),
                            plano=res.get("plano"),
                            numero_cotacao=res.get("numero"),
                            coberturas=res.get("coberturas"),
                            mensagem=res.get("mensagem"),
                        )
                        stats["resultados_inseridos"] += 1
                    db.commit()
                    logger.debug(f"Cotação {uuid or placa}: {len(resultados)} resultados inseridos")

            except Exception as e:
                db.rollback()
                logger.error(f"Erro ao processar cotação {uuid or placa}: {e}")
                stats["erros"] += 1
                continue

            await asyncio.sleep(0.5)  # Gentil para não sobrecarregar a API

        cur.close()
        db.close()

    finally:
        await browser.close()
        await pw.stop()

    return stats


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sync histórico de cotações do Agilizador")
    parser.add_argument("--limit", type=int, default=200, help="Máximo de cotações a importar")
    parser.add_argument("--debug", action="store_true", help="Modo debug verboso")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 60)
    logger.info("🚀 Sync Agilizador — Importar histórico de cotações")
    logger.info(f"   Limit: {args.limit}")
    logger.info("=" * 60)

    start = time.time()
    stats = asyncio.run(sync_cotacoes(limit=args.limit, debug=args.debug))
    elapsed = time.time() - start

    logger.info("=" * 60)
    logger.info("✅ SYNC CONCLUÍDO")
    logger.info(f"   Total processadas: {stats['cotacoes_total']}")
    logger.info(f"   Cotações novas:    {stats['cotacoes_novas']}")
    logger.info(f"   Cotações skip:     {stats['cotacoes_skip']}")
    logger.info(f"   Clientes novos:    {stats['clientes_novos']}")
    logger.info(f"   Resultados:        {stats['resultados_inseridos']}")
    logger.info(f"   Erros:             {stats['erros']}")
    logger.info(f"   Tempo:             {elapsed:.1f}s")
    logger.info("=" * 60)

    return stats


if __name__ == "__main__":
    main()
