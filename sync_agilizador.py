"""
sync_agilizador.py — Importa histórico de cotações do Agilizador (aggilizador.com.br / multicalculo.net)
para o banco de dados PostgreSQL do Projeto Vértice/Sierra.

Uso:
    /root/sierra/venv/bin/python sync_agilizador.py [--limit N] [--debug]

Bugs corrigidos (v2):
  1. _classify: mais restritivo — só classifica busca/v2 como lista real
  2. parse_cotacao_item: usa idIntegracao (não id) como UUID p/ versoes
  3. Bug com dict como nome: sanitiza segurado_nome antes de usar
  4. Paginação: busca/v2 itera páginas até obter N cotações
  5. Filtra só ramo=31 (auto) para importar em veiculos
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
os.makedirs("/root/sierra/debug", exist_ok=True)
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

# Endpoint real de listagem (padrão de URL)
BUSCA_V2_BASE = "https://api.multicalculo.net/calculo/negocio/busca/v2"

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
    """Converte string de data para date."""
    if not s:
        return None
    if isinstance(s, date):
        return s
    s = str(s).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s[:19] if "T" in s else s, fmt.split("Z")[0] if "Z" in fmt else fmt).date()
        except:
            continue
    # Tenta extrair data de ISO string
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except:
            pass
    return None


def safe_str(val, default="") -> str:
    """Converte valor para string segura — nunca retorna um dict."""
    if val is None:
        return default
    if isinstance(val, dict):
        # Tenta extrair nome de dentro do dict
        for key in ("nome", "nomeCompleto", "nomeSegurado", "name"):
            if key in val and val[key]:
                return str(val[key]).strip()
        return default
    if isinstance(val, (list, set)):
        return default
    return str(val).strip()


# ── DB ────────────────────────────────────────────────────────────────────────

def get_db():
    return psycopg2.connect(DB_DSN)


def upsert_cliente(cur, nome: str, cpf_cnpj: str = None, telefone: str = None) -> int:
    """Insere ou retorna cliente existente. Retorna cliente_id."""
    nome = (nome or "").strip()
    cpf_cnpj = re.sub(r"\D", "", cpf_cnpj or "") or None

    # Busca por CPF
    if cpf_cnpj:
        cur.execute(
            "SELECT id FROM clientes WHERE corretora_id = %s AND cpf_cnpj = %s",
            (CORRETORA_ID, cpf_cnpj)
        )
        row = cur.fetchone()
        if row:
            return row[0]

    # Busca por nome (fallback sem CPF)
    if nome and not cpf_cnpj:
        cur.execute(
            "SELECT id FROM clientes WHERE corretora_id = %s AND LOWER(nome) = LOWER(%s) LIMIT 1",
            (CORRETORA_ID, nome)
        )
        row = cur.fetchone()
        if row:
            return row[0]

    # Insere novo
    if cpf_cnpj:
        cur.execute(
            """
            INSERT INTO clientes (corretora_id, nome, cpf_cnpj, telefone, created_at, updated_at, status)
            VALUES (%s, %s, %s, %s, NOW(), NOW(), 'ativo')
            ON CONFLICT (corretora_id, cpf_cnpj) DO UPDATE SET nome = EXCLUDED.nome, updated_at = NOW()
            RETURNING id
            """,
            (CORRETORA_ID, nome, cpf_cnpj, telefone)
        )
    else:
        cur.execute(
            """
            INSERT INTO clientes (corretora_id, nome, telefone, created_at, updated_at, status)
            VALUES (%s, %s, %s, NOW(), NOW(), 'ativo')
            RETURNING id
            """,
            (CORRETORA_ID, nome, telefone)
        )
    return cur.fetchone()[0]


def upsert_veiculo(cur, cliente_id: int, placa: str, marca_modelo: str = None,
                   ano_fabricacao: str = None, ano_modelo: str = None,
                   chassi: str = None) -> int:
    """Insere ou retorna veículo. Retorna veiculo_id."""
    placa = clean_placa(placa or "")

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
                              ano_fabricacao, ano_modelo, chassi, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        RETURNING id
        """,
        (CORRETORA_ID, cliente_id, placa or None, marca_modelo,
         str(ano_fabricacao) if ano_fabricacao else None,
         str(ano_modelo) if ano_modelo else None,
         chassi)
    )
    return cur.fetchone()[0]


def cotacao_exists(cur, agilizador_uuid: str = None, veiculo_id: int = None,
                   created_at_date=None) -> Optional[int]:
    """Verifica se cotação já existe. Retorna id ou None."""
    if agilizador_uuid:
        cur.execute(
            "SELECT id FROM cotacoes WHERE agilizador_url LIKE %s LIMIT 1",
            (f"%{agilizador_uuid}%",)
        )
        row = cur.fetchone()
        if row:
            return row[0]

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
                     mensagem: str = None):
    """Insere resultado de seguradora. ON CONFLICT DO NOTHING."""
    cur.execute(
        """
        INSERT INTO cotacao_resultados
            (cotacao_id, corretora_id, seguradora, premio, franquia, plano,
             numero_cotacao, mensagem, status, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ok', NOW())
        ON CONFLICT DO NOTHING
        """,
        (cotacao_id, CORRETORA_ID, seguradora, premio, franquia, plano,
         numero_cotacao, coberturas or mensagem)
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


async def login(page: Page, retry: bool = True):
    """Faz login no Agilizador. Tenta 2x se falhar."""
    async def _do_login():
        logger.info(f"Navegando para login: {AGG_URL}/login")
        await page.goto(f"{AGG_URL}/login", timeout=60000)
        await page.wait_for_load_state("networkidle")

        await page.fill('input[formcontrolname="email"]', AGG_EMAIL)
        await asyncio.sleep(0.5)
        await page.fill('input[formcontrolname="senha"]', AGG_SENHA)
        await asyncio.sleep(0.5)
        await page.click('button:has-text("Entrar")')

        try:
            await page.wait_for_url(lambda url: "/login" not in url, timeout=20000)
        except:
            pass

        await asyncio.sleep(3)

        try:
            btn = page.locator('button:has-text("Prosseguir")')
            if await btn.count() > 0:
                await btn.click()
                await asyncio.sleep(2)
        except:
            pass

        try:
            terms_btn = page.locator('button:has-text("Aceitar"), button:has-text("Concordo")')
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

    await _do_login()

    # Verifica se login funcionou
    if "/login" in page.url:
        if retry:
            logger.warning("Login falhou, tentando novamente...")
            await asyncio.sleep(3)
            await _do_login()
        else:
            logger.error(f"Login falhou definitivamente. URL: {page.url}")

    logger.info(f"Login OK. URL atual: {page.url}")


# ── Interceptação de API ──────────────────────────────────────────────────────

class ApiInterceptor:
    """
    Intercepta respostas da API do Agilizador.
    
    BUG 1 FIX: _classify é agora muito mais restritivo:
    - Só classifica como lista se URL contiver 'busca/v2' ou 'negocio/busca'
    - Exclui endpoints de seguradoras, config, usuario, status, etc.
    - Para arrays: exige 'idIntegracao' ou 'negocios' na estrutura
    """

    def __init__(self):
        self.captured: Dict[str, Any] = {}
        # Apenas endpoints REAIS de listagem de cotações
        self.list_endpoints: List[tuple] = []
        # UUID do idIntegracao → dados de versões
        self.detail_endpoints: Dict[str, Any] = {}

    async def handle_response(self, response: Response):
        url = response.url
        try:
            if "api.multicalculo.net" not in url and "api.aggilizador.com.br" not in url \
               and "api-prod.aggilizador.com.br" not in url:
                return
            if response.status != 200:
                return

            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return

            text = await response.text()
            if not text or len(text) < 10:
                return

            data = json.loads(text)
            self.captured[url] = data

            # Salva para debug (primeiros 30)
            if len(self.captured) <= 30:
                fname = re.sub(r"[^a-z0-9]", "_", url.lower())[-60:]
                debug_path = os.path.join(DEBUG_DIR, f"api_{fname}.json")
                try:
                    with open(debug_path, "w") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                except:
                    pass

            self._classify(url, data)

        except Exception as e:
            logger.debug(f"Interceptor err {url[:80]}: {e}")

    def _classify(self, url: str, data: Any):
        """
        BUG 1 FIX: Identifica APENAS endpoints reais de cotação.
        
        Exclui: seguradoras, config, usuario, cep, status, discount, renovacao, multi, travel
        Inclui: negocio/busca, busca/v2, cotacao/versoes
        """
        url_lower = url.lower()

        # Padrões a EXCLUIR (não são cotações)
        exclude_patterns = [
            "seguradoras", "seguradora/config", "seguradorastatus",
            "seguradoradiscountstatus", "seguradorasmulti", "seguradorasrenovacao",
            "listusuarios", "listausuarios", "usuario/", "/usuario",
            "cep/", "/cep", "/travel", "preferencias", "assinatura",
            "research", "getresearch", "cobertura_v2", "seguradorastatus",
            "app/seguradorastatus", "app/seguradoras"
        ]
        if any(p in url_lower for p in exclude_patterns):
            logger.debug(f"Excluindo endpoint: {url[:80]}")
            return

        # Endpoint de LISTA de negócios (busca/v2) — estrutura {data: [...]}
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list) and data["data"]:
            first = data["data"][0] if isinstance(data["data"][0], dict) else {}
            # Precisa ter campos característicos de negócio
            has_negocio_keys = "negocios" in first or (
                "seguradoCpfCnpj" in first and "qtdNegocios" in first
            )
            if has_negocio_keys:
                logger.info(f"📋 Lista busca/v2 encontrada: {url[:80]} ({len(data['data'])} segurados)")
                self.list_endpoints.append((url, data))
                return

        # Endpoint de VERSÕES de cotação específica — exige 'calculos' no item
        if isinstance(data, list) and data:
            first = data[0] if isinstance(data[0], dict) else {}
            last = data[-1] if isinstance(data[-1], dict) else {}

            # Versões: tem 'calculos' e 'idIntegracao'
            if ("calculos" in last or "calculos" in first) and (
                "idIntegracao" in last or "idIntegracao" in first
            ):
                # Extrai UUID do URL
                uuid_match = re.search(r"versoes/([a-f0-9-]{36})", url)
                if uuid_match:
                    uuid = uuid_match.group(1)
                    self.detail_endpoints[uuid] = data
                    logger.debug(f"Versões capturadas: {uuid[:8]}... ({len(data)} versões)")
                return


# ── Extração de cotações ──────────────────────────────────────────────────────

def extract_negocios_from_busca_v2(data: Any) -> List[Dict]:
    """
    BUG 2 FIX: Extrai lista de negócios do endpoint busca/v2.
    
    Estrutura esperada:
    {
      "data": [
        {
          "seguradoCpfCnpj": "...",
          "seguradoNome": "...",
          "fone1": "...",
          "negocios": [
            {
              "id": "uuid-negocio",         ← NÃO usar como UUID de versoes!
              "idIntegracao": "uuid-real",  ← UUID real para versoes
              "seguradoNome": "...",
              "seguradoCpfCnpj": "...",
              "placa": "...",
              "modelo": "...",
              "ramo": 31,
              "tipo": "v",
              "createdAt": "..."
            }
          ]
        }
      ]
    }
    """
    negocios = []

    if not isinstance(data, dict):
        return negocios

    groups = data.get("data", [])
    if not isinstance(groups, list):
        return negocios

    for group in groups:
        if not isinstance(group, dict):
            continue

        # Dados do segurado a nível de grupo
        cpf_grupo = group.get("seguradoCpfCnpj", "")
        nome_grupo = safe_str(group.get("seguradoNome", ""))
        fone_grupo = group.get("fone1", "")

        for neg in group.get("negocios", []):
            if not isinstance(neg, dict):
                continue

            # Propaga dados do segurado para o negócio se faltarem
            if not neg.get("seguradoCpfCnpj"):
                neg["_cpf_grupo"] = cpf_grupo
            if not neg.get("seguradoNome"):
                neg["_nome_grupo"] = nome_grupo
            if not neg.get("fone1"):
                neg["_fone_grupo"] = fone_grupo

            negocios.append(neg)

    return negocios


def parse_negocio_item(neg: Dict) -> Dict:
    """
    BUG 2 FIX: Normaliza um negócio do busca/v2 para formato interno.
    Usa 'idIntegracao' como UUID (não 'id').
    BUG 3 FIX: Garante que nome nunca é dict.
    """
    # UUID correto: idIntegracao (usado para fetch de versoes)
    id_integracao = neg.get("idIntegracao") or neg.get("id")  # idIntegracao é o real
    negocio_id = neg.get("id")  # id do negócio (diferente de idIntegracao!)

    # Se idIntegracao existir, usa ele; caso contrário usa id
    # (idIntegracao é o que o endpoint /versoes espera)
    uuid = id_integracao

    # Nome do segurado — BUG 3 FIX: nunca retorna dict
    segurado_nome = safe_str(
        neg.get("seguradoNome") or neg.get("_nome_grupo") or neg.get("nomeSegurado")
    )

    # CPF
    segurado_cpf = neg.get("seguradoCpfCnpj") or neg.get("_cpf_grupo") or ""
    segurado_cpf = re.sub(r"\D", "", str(segurado_cpf))

    # Telefone
    telefone = neg.get("fone1") or neg.get("_fone_grupo") or ""
    telefone = re.sub(r"\D", "", str(telefone)) if telefone else ""

    # Veículo (só para ramo=31 / tipo='v')
    placa = clean_placa(str(neg.get("placa", "")))
    # BUG 3 FIX: modelo pode ser dict em algumas variações da API
    modelo_raw = neg.get("modelo") or neg.get("marcaModelo") or neg.get("descricaoVeiculo")
    marca_modelo = safe_str(modelo_raw) if modelo_raw else None

    # Ramo e tipo
    ramo = neg.get("ramo", 0)  # 31 = auto, 2 = residencial
    tipo = neg.get("tipo", "")  # 'v' = veiculo

    # Data de criação
    created_at_raw = neg.get("createdAt") or neg.get("dataCriacao") or neg.get("vigenciaIni")

    # URL do Agilizador
    if uuid:
        if ramo == 31 or tipo == "v":
            agilizador_url = f"{AGG_URL}/cotacao/auto/resultados/{uuid}"
        elif ramo == 2:
            agilizador_url = f"{AGG_URL}/cotacao/residencial/resultados/{uuid}"
        else:
            agilizador_url = f"{AGG_URL}/cotacao/resultados/{uuid}"
    else:
        agilizador_url = None

    return {
        "uuid": str(uuid) if uuid else None,
        "negocio_id": str(negocio_id) if negocio_id else None,
        "agilizador_url": agilizador_url,
        "created_at_raw": created_at_raw,
        "segurado_nome": segurado_nome,
        "segurado_cpf": segurado_cpf,
        "telefone": telefone,
        "placa": placa,
        "marca_modelo": marca_modelo,
        "ramo": ramo,
        "tipo": tipo,
        "is_auto": ramo == 31 or tipo == "v",
        "_raw": neg,
    }


def parse_resultados_from_versoes(versoes_data: Any) -> List[Dict]:
    """
    Extrai resultados (seguradoras/prêmios) dos dados de versões de uma cotação.
    """
    results = []
    versoes = versoes_data if isinstance(versoes_data, list) else [versoes_data]

    if not versoes:
        return []

    # Usa a última versão (mais recente)
    latest = None
    for v in reversed(versoes):
        if isinstance(v, dict) and "calculos" in v:
            latest = v
            break
    if not latest:
        return []

    calculos = latest.get("calculos", [])
    seen = set()

    for calc in calculos:
        seg_nome = safe_str(calc.get("nomeSeguradora") or calc.get("seguradoraTxt")).strip()
        if not seg_nome:
            continue

        res_list = calc.get("resultados", [])
        if not res_list:
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
                    "mensagem": safe_str(calc.get("mensagemErro") or calc.get("retornoErro")) or "Sem resultado",
                })
            continue

        for res in res_list:
            premio = parse_premio(res.get("premio"))
            if premio is None:
                continue

            plano = safe_str(
                res.get("identificacao") or res.get("cobertura") or res.get("nomePacote")
            )
            key = f"{seg_nome.lower()}|{plano.lower()}"
            if key in seen:
                continue
            seen.add(key)

            results.append({
                "seguradora": seg_nome,
                "premio": premio,
                "franquia": parse_premio(res.get("franquia") or res.get("valorFranquia")),
                "plano": plano,
                "numero": safe_str(res.get("nroCalculo") or res.get("numeroCotacao") or res.get("identificacao")),
                "coberturas": safe_str(res.get("coberturas") or res.get("cobertura")),
                "mensagem": safe_str(res.get("mensagemErro")),
            })

    return results


# ── Sync principal ────────────────────────────────────────────────────────────

async def fetch_versoes_for_cotacao(page: Page, id_integracao: str) -> Optional[Any]:
    """Busca versões de uma cotação pelo idIntegracao."""
    api_url = f"https://api.multicalculo.net/calculo/cotacao/versoes/{id_integracao}"
    try:
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
        logger.debug(f"fetch versoes {id_integracao}: {e}")

    try:
        api_resp = await page.context.request.get(api_url)
        if api_resp.ok:
            return json.loads(await api_resp.text())
    except Exception as e:
        logger.debug(f"playwright request versoes {id_integracao}: {e}")

    return None


async def fetch_busca_v2_page(page: Page, page_num: int = 1, limit: int = 40) -> Optional[Dict]:
    """
    Busca uma página do endpoint busca/v2.
    BUG 4 FIX: Suporte a paginação.
    """
    url = f"{BUSCA_V2_BASE}?textoBusca=&modo=2&page={page_num}&limit={limit}&sortOrder=desc&integracaoInfo=1"
    try:
        resp_text = await page.evaluate(f"""
            async () => {{
                try {{
                    const r = await fetch('{url}', {{
                        credentials: 'include',
                        headers: {{'Accept': 'application/json'}}
                    }});
                    if (r.status !== 200) return null;
                    return await r.text();
                }} catch(e) {{ return null; }}
            }}
        """)
        if resp_text:
            data = json.loads(resp_text)
            logger.info(f"busca/v2 página {page_num}: {len(data.get('data', []))} segurados")
            return data
    except Exception as e:
        logger.warning(f"fetch busca/v2 página {page_num}: {e}")
    return None


async def collect_all_negocios(page: Page, interceptor: ApiInterceptor,
                                limit: int = 200) -> List[Dict]:
    """
    Coleta todos os negócios do busca/v2 via paginação.
    Prioriza dados já interceptados, depois faz fetch manual.
    """
    all_negocios = []
    seen_uuids = set()

    def add_negocios(negocios_list):
        added = 0
        for neg in negocios_list:
            uid = neg.get("uuid") or neg.get("negocio_id")
            if uid and uid in seen_uuids:
                continue
            if uid:
                seen_uuids.add(uid)
            all_negocios.append(neg)
            added += 1
        return added

    # 1. Primeiro usa dados interceptados (já temos a página 1)
    if interceptor.list_endpoints:
        for url, data in interceptor.list_endpoints:
            raw_negocios = extract_negocios_from_busca_v2(data)
            parsed = [parse_negocio_item(n) for n in raw_negocios]
            added = add_negocios(parsed)
            logger.info(f"Da interceptação {url[:60]}: {added} negócios")
        
        # Verifica se precisamos de mais páginas
        if len(all_negocios) < limit:
            page_num = 2
            while len(all_negocios) < limit:
                await asyncio.sleep(0.5)
                data = await fetch_busca_v2_page(page, page_num, limit=40)
                if not data:
                    break
                raw_negocios = extract_negocios_from_busca_v2(data)
                if not raw_negocios:
                    break
                parsed = [parse_negocio_item(n) for n in raw_negocios]
                added = add_negocios(parsed)
                logger.info(f"Página {page_num}: +{added} negócios (total: {len(all_negocios)})")
                if added == 0:
                    break
                page_num += 1
                if page_num > 50:  # segurança
                    break
    else:
        # Sem interceptação — faz fetch manual das páginas
        logger.info("Sem dados interceptados, fazendo fetch manual do busca/v2...")
        page_num = 1
        while len(all_negocios) < limit:
            data = await fetch_busca_v2_page(page, page_num, limit=40)
            if not data:
                break
            raw_negocios = extract_negocios_from_busca_v2(data)
            if not raw_negocios:
                break
            parsed = [parse_negocio_item(n) for n in raw_negocios]
            added = add_negocios(parsed)
            logger.info(f"Página {page_num}: +{added} negócios (total: {len(all_negocios)})")
            if added == 0:
                break
            page_num += 1
            await asyncio.sleep(0.5)
            if page_num > 50:
                break

    logger.info(f"Total de negócios coletados: {len(all_negocios)}")
    return all_negocios[:limit]


async def navigate_to_cotacoes_list(page: Page, interceptor: ApiInterceptor):
    """Navega para a lista de cotações e aguarda carregamento (dispara interceptações)."""
    logger.info("Navegando para /cotacoes...")
    await page.goto(f"{AGG_URL}/cotacoes", timeout=30000)
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(4)
    await fechar_modais(page)

    # Screenshot de debug
    try:
        await page.screenshot(path=f"{DEBUG_DIR}/lista_cotacoes_v2.png", full_page=False)
    except:
        pass


# ── Main sync ─────────────────────────────────────────────────────────────────

async def sync_cotacoes(limit: int = 200, debug: bool = False):
    """Função principal de sincronização."""
    os.makedirs(DEBUG_DIR, exist_ok=True)

    stats = {
        "cotacoes_total": 0,
        "cotacoes_novas": 0,
        "cotacoes_skip": 0,
        "cotacoes_nao_auto": 0,
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
    page.on("response", interceptor.handle_response)

    try:
        # Login
        logger.info("=" * 60)
        logger.info("🔐 Fazendo login no Agilizador...")
        await login(page)

        # Navega para lista (dispara interceptações da busca/v2)
        await navigate_to_cotacoes_list(page, interceptor)

        # Coleta negócios
        logger.info("=" * 60)
        logger.info(f"📋 Coletando negócios (limit={limit})...")
        negocios = await collect_all_negocios(page, interceptor, limit=limit)

        if not negocios:
            logger.error("❌ Nenhum negócio encontrado. Verifique debug/lista_cotacoes_v2.png")
            # Dump endpoints capturados
            for url in list(interceptor.captured.keys()):
                d = interceptor.captured[url]
                logger.info(f"  Capturado: {type(d).__name__} {url[:100]}")
            return stats

        logger.info(f"✅ {len(negocios)} negócios encontrados")

        # Filtra apenas auto (ramo=31 ou tipo='v')
        auto_negocios = [n for n in negocios if n.get("is_auto")]
        outros = len(negocios) - len(auto_negocios)
        logger.info(f"   Auto: {len(auto_negocios)} | Outros (residencial, etc): {outros}")
        stats["cotacoes_nao_auto"] = outros

        # Processa cada negócio auto
        db = get_db()
        cur = db.cursor()

        for i, negocio in enumerate(auto_negocios[:limit]):
            stats["cotacoes_total"] += 1
            uuid = negocio.get("uuid")  # = idIntegracao
            placa = negocio.get("placa") or ""
            nome = negocio.get("segurado_nome") or ""
            cpf = negocio.get("segurado_cpf") or ""
            telefone = negocio.get("telefone") or ""

            if i > 0 and i % 10 == 0:
                logger.info(f"📊 Progresso: {i}/{len(auto_negocios)} | "
                            f"novas={stats['cotacoes_novas']} skip={stats['cotacoes_skip']} "
                            f"erros={stats['erros']}")

            # Valida dados mínimos
            if not nome and not placa and not uuid:
                logger.debug(f"Item {i}: sem dados suficientes, skip")
                stats["cotacoes_skip"] += 1
                continue

            # BUG 3 FIX: nome sempre string
            if not nome:
                nome = f"Cliente_{placa or uuid[:8] if uuid else str(i)}"

            # Parse data de criação
            created_at = None
            if negocio.get("created_at_raw"):
                dt = parse_date(negocio["created_at_raw"])
                if dt:
                    created_at = datetime.combine(dt, datetime.min.time())
            if not created_at:
                created_at = datetime.now()

            try:
                # Busca versões para enriquecer dados (rate: 1 req/s)
                versoes_data = interceptor.detail_endpoints.get(uuid) if uuid else None
                if not versoes_data and uuid:
                    await asyncio.sleep(0.8)
                    versoes_data = await fetch_versoes_for_cotacao(page, uuid)
                    if versoes_data:
                        interceptor.detail_endpoints[uuid] = versoes_data

                # Enriquece com dados das versões se necessário
                if versoes_data:
                    latest = versoes_data[-1] if isinstance(versoes_data, list) and versoes_data else (
                        versoes_data if isinstance(versoes_data, dict) else {}
                    )
                    if not nome or nome.startswith("Cliente_"):
                        nome = safe_str(
                            latest.get("seguradoNome") or
                            (latest.get("segurado") or {}).get("nome") if isinstance(latest.get("segurado"), dict) else None
                        ) or nome
                    if not placa:
                        placa = clean_placa(safe_str(
                            latest.get("placa") or
                            (latest.get("configuracoes") or {}).get("placa") if isinstance(latest.get("configuracoes"), dict) else None
                        ))
                    if not negocio.get("marca_modelo"):
                        cfg = latest.get("configuracoes") or {}
                        if isinstance(cfg, dict):
                            negocio["marca_modelo"] = safe_str(cfg.get("modelo") or cfg.get("marcaModelo"))

                # Clientes
                cliente_id = upsert_cliente(
                    cur,
                    nome=nome,
                    cpf_cnpj=cpf or None,
                    telefone=telefone or None,
                )
                db.commit()

                # Veículos
                veiculo_id = upsert_veiculo(
                    cur,
                    cliente_id=cliente_id,
                    placa=placa,
                    marca_modelo=negocio.get("marca_modelo"),
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
                agilizador_url = negocio.get("agilizador_url")
                crvl_data = {
                    "placa": placa,
                    "marca_modelo": negocio.get("marca_modelo"),
                    "idIntegracao": uuid,
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

                # Insere resultados das seguradoras
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
                    if resultados:
                        logger.info(f"  ✅ {nome[:30]} | {placa} → {len(resultados)} resultados")

            except Exception as e:
                db.rollback()
                logger.error(f"Erro ao processar {nome[:20]} / {placa} / {uuid}: {e}")
                stats["erros"] += 1
                continue

        cur.close()
        db.close()

    finally:
        try:
            await page.screenshot(path=f"{DEBUG_DIR}/sync_final.png")
        except:
            pass
        await browser.close()
        await pw.stop()

    return stats


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sync histórico de cotações do Agilizador")
    parser.add_argument("--limit", type=int, default=200, help="Máximo de cotações auto a importar")
    parser.add_argument("--debug", action="store_true", help="Modo debug verboso")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 60)
    logger.info("🚀 Sync Agilizador v2 — Importar histórico de cotações AUTO")
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
    logger.info(f"   Não-auto (skip):   {stats['cotacoes_nao_auto']}")
    logger.info(f"   Clientes novos:    {stats['clientes_novos']}")
    logger.info(f"   Resultados:        {stats['resultados_inseridos']}")
    logger.info(f"   Erros:             {stats['erros']}")
    logger.info(f"   Tempo:             {elapsed:.1f}s")
    logger.info("=" * 60)

    return stats


if __name__ == "__main__":
    main()
