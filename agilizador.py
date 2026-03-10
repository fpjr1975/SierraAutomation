"""
Automação do Agilizador via Playwright.
Preenche formulário de cotação auto com dados extraídos da CNH/CRVL.
Nomes de campos mapeados em 07/03/2026.
"""

import asyncio
import os
import re
import logging
from datetime import date
from playwright.async_api import async_playwright, Page

logger = logging.getLogger(__name__)

# Sessões de browser abertas (chat_id → {browser, page, playwright, resultados})
_browser_sessions = {}
_agg_token_cache = {}  # cache do token JWT do Agilizador
_SESSIONS_FILE = "/root/sierra/downloads/cotacao_sessions.json"


def _save_sessions_to_disk():
    """Salva dados das sessões em disco (só dados serializáveis, não objetos Playwright)."""
    import json as _json
    serializable = {}
    for cid, s in _browser_sessions.items():
        serializable[str(cid)] = {
            "resultados": s.get("resultados", []),
            "resultados_url": s.get("resultados_url", ""),
            "pdf_map": s.get("pdf_map", {}),
            "cotacao_uuid": s.get("cotacao_uuid"),
        }
    try:
        with open(_SESSIONS_FILE, "w") as f:
            _json.dump(serializable, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Erro ao salvar sessões em disco: {e}")


def _load_sessions_from_disk():
    """Carrega sessões salvas do disco."""
    import json as _json
    try:
        with open(_SESSIONS_FILE, "r") as f:
            data = _json.load(f)
        for cid, s in data.items():
            _browser_sessions[int(cid)] = s
        logger.info(f"Sessões carregadas do disco: {len(data)}")
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"Erro ao carregar sessões do disco: {e}")

# Carrega sessões ao importar o módulo
_load_sessions_from_disk()


async def fechar_sessao(chat_id: int):
    """Fecha browser de uma sessão (mantém dados em memória/disco)."""
    session = _browser_sessions.get(chat_id)
    if session:
        # Fecha browser se existir, mas mantém dados
        try:
            if "browser" in session:
                await session["browser"].close()
                del session["browser"]
        except:
            pass
        try:
            if "pw" in session:
                await session["pw"].__aexit__(None, None, None)
                del session["pw"]
        except:
            pass
        logger.info(f"Browser fechado para chat_id={chat_id} (dados mantidos)")


async def get_sessao(chat_id: int):
    """Retorna sessão de browser ativa ou None."""
    return _browser_sessions.get(chat_id)

AGG_EMAIL = "contato@sierraseguros.com.br"
AGG_SENHA = "Tronca2660&&"
AGG_URL   = "https://aggilizador.com.br"

# Timeout curto pra não travar 30s por campo
FIELD_TIMEOUT = 5000  # 5 segundos


async def _fechar_modais(page: Page):
    """Fecha qualquer modal/overlay aberto."""
    try:
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.3)
    except: pass

    try:
        for texto in ["Fechar", "OK", "Entendido", "Continuar", "Prosseguir", "close"]:
            btn = page.locator(f'button:has-text("{texto}")')
            if await btn.count() > 0:
                await btn.first.click(force=True)
                await asyncio.sleep(0.3)
    except: pass

    try:
        await page.evaluate("""
            document.querySelectorAll('.cdk-overlay-backdrop').forEach(e => e.remove());
            document.querySelectorAll('.cdk-global-overlay-wrapper').forEach(e => e.remove());
            const oc = document.querySelector('.cdk-overlay-container');
            if (oc) oc.innerHTML = '';
            document.body.classList.remove('cdk-global-scrollblock');
        """)
        await asyncio.sleep(0.3)
    except: pass


async def _fill(page: Page, selector: str, value: str):
    """Preenche um campo com force e timeout curto."""
    if not value or value == "N/D":
        return
    try:
        el = page.locator(selector).first
        await el.click(force=True, timeout=FIELD_TIMEOUT)
        await el.fill(value, timeout=FIELD_TIMEOUT)
        await asyncio.sleep(0.3)
    except Exception as e:
        logger.warning(f"Campo {selector}: {str(e)[:80]}")


async def _fill_by_name(page: Page, name: str, value: str):
    """Preenche campo pelo atributo name."""
    await _fill(page, f'input[name="{name}"]', value)


async def _fill_by_fc(page: Page, fc: str, value: str):
    """Preenche campo pelo formcontrolname."""
    await _fill(page, f'input[formcontrolname="{fc}"]', value)


async def _select_mat(page: Page, fc: str, option_text: str):
    """Abre mat-select e escolhe opção. Se não tem opções, tenta forçar via Angular."""
    try:
        await _fechar_modais(page)
        sel = page.locator(f'mat-select[formcontrolname="{fc}"]').first
        if await sel.count() == 0:
            logger.warning(f"Select {fc}: elemento não encontrado")
            return
        
        # Scroll até o campo e garante visibilidade
        try:
            await sel.scroll_into_view_if_needed(timeout=3000)
        except:
            await page.evaluate(f"""
                const el = document.querySelector('mat-select[formcontrolname="{fc}"]');
                if (el) el.scrollIntoView({{block: 'center'}});
            """)
        await asyncio.sleep(0.3)
        
        await sel.click(force=True, timeout=FIELD_TIMEOUT)
        await asyncio.sleep(1)
        
        # Tenta achar a opção desejada
        opt = page.locator(f'mat-option:has-text("{option_text}")').first
        if await opt.count() > 0:
            await opt.click(force=True, timeout=FIELD_TIMEOUT)
            await asyncio.sleep(0.3)
            return
        
        # Se não achou a opção exata, pega a primeira disponível
        all_opts = page.locator('mat-option')
        qtd = await all_opts.count()
        if qtd > 0:
            txt = await all_opts.first.inner_text()
            await all_opts.first.click(force=True, timeout=FIELD_TIMEOUT)
            logger.info(f"Select {fc}: '{option_text}' não encontrado, usou '{txt.strip()}' ({qtd} opções)")
            await asyncio.sleep(0.3)
            return
        
        # Sem opções — fecha dropdown e tenta forçar via Angular
        await page.keyboard.press("Escape")
        logger.warning(f"Select {fc}: sem opções no dropdown, tentando via Angular...")
        
        # Force-set via Angular's ngModel
        set_ok = await page.evaluate(f"""
            (() => {{
                const el = document.querySelector('mat-select[formcontrolname="{fc}"]');
                if (!el) return false;
                // Tenta acessar o ngControl do Angular
                const keys = Object.keys(el).filter(k => k.startsWith('__ngContext__') || k.startsWith('_ngcontent'));
                // Dispatch change event pra Angular detectar
                el.click();
                return 'attempted';
            }})()
        """)
        logger.info(f"Select {fc}: Angular force attempt = {set_ok}")
        
    except Exception as e:
        logger.warning(f"Select {fc}={option_text}: {str(e)[:80]}")
        try: await page.keyboard.press("Escape")
        except: pass


async def _type_placa(page: Page, placa: str, modelo_crvl: str):
    """Digita placa, aguarda dropdown e seleciona o veículo correto."""
    try:
        campo = page.locator('input[name="placa"]').first
        await campo.click(force=True, timeout=FIELD_TIMEOUT)
        await campo.fill("")
        await campo.type(placa, delay=80)
        await asyncio.sleep(3)

        dropdown = page.locator('mat-option')
        qtd = await dropdown.count()
        logger.info(f"Placa '{placa}': {qtd} opções no dropdown")
        
        if qtd > 0:
            # Lê todas as opções
            opcoes = []
            for i in range(qtd):
                txt = await dropdown.nth(i).inner_text()
                opcoes.append(txt.strip())
                logger.info(f"  Opção {i}: {txt.strip()}")
            
            # Sempre seleciona a PRIMEIRA opção (é a que o Agilizador considera correta pra placa)
            await dropdown.first.click(force=True)
            logger.info(f"Veículo selecionado: {opcoes[0] if opcoes else '?'}")
        
        await asyncio.sleep(2)
    except Exception as e:
        logger.warning(f"Placa: {str(e)[:80]}")


def _formatar_placa(placa: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (placa or "").upper())


def _vigencia_padrao() -> tuple[str, str]:
    hoje = date.today()
    fim = date(hoje.year + 1, hoje.month, hoje.day)
    return hoje.strftime("%d/%m/%Y"), fim.strftime("%d/%m/%Y")


async def _login(page: Page):
    """Faz login e fecha popups."""
    await page.goto(f"{AGG_URL}/login", timeout=30000)
    await page.wait_for_load_state("networkidle")
    await page.fill('input[formcontrolname="email"]', AGG_EMAIL)
    await page.fill('input[type="password"]', AGG_SENHA)
    await page.click('button:has-text("Entrar")')
    await asyncio.sleep(3)

    try:
        btn = page.locator('button:has-text("Prosseguir")')
        if await btn.count() > 0:
            await btn.click()
            await asyncio.sleep(3)
    except: pass

    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(2)
    await _fechar_modais(page)
    
    # Captura token JWT do localStorage/cookies pra uso posterior via httpx
    try:
        token = await page.evaluate("""
            () => {
                // Tenta localStorage
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
                // Tenta sessionStorage
                for (let i = 0; i < sessionStorage.length; i++) {
                    const key = sessionStorage.key(i);
                    const val = sessionStorage.getItem(key);
                    if (val && val.startsWith('eyJ')) return val;
                }
                return null;
            }
        """)
        if token:
            _agg_token_cache['token'] = token
            logger.info(f"Token JWT capturado: {token[:30]}...")
    except:
        pass


async def _extrair_resultados(page: Page) -> list:
    """Extrai resultados das cotações da página de resultados do Agilizador.
    
    Usa seletores reais mapeados do DOM:
    - .pacote = bloco de cada resultado (desktop + mobile duplicados)
    - .pacote__seg-nome = nome da seguradora
    - .currency-formatted--premio = valor do prêmio
    - .currency-formatted--franquia = valor da franquia
    - .pacote__value--cotacao = número da cotação
    - .expansion-panel__value--error = mensagem de erro
    - .pacote__seg--loading = seguradora ainda calculando
    """
    try:
        # Aguarda mais tempo pros cálculos terminarem
        # Verifica se ainda tem loading a cada 5s, até 90s
        for tentativa in range(18):
            loading_count = await page.locator('.pacote__seg--loading, .pacote__item--loading, [class*="loading"]').count()
            # Filtra só os loadings dentro de pacotes de seguradoras
            loading_real = await page.evaluate("""
                () => document.querySelectorAll('.pacote__seg--loading, .pacote__item.pacote__seg[class*="loading"]').length
            """)
            if loading_real == 0 and tentativa >= 2:
                logger.info(f"Todos os cálculos terminaram (tentativa {tentativa+1})")
                break
            logger.info(f"Ainda calculando... {loading_real} seguradoras pendentes (tentativa {tentativa+1}/18)")
            await asyncio.sleep(5)
        
        await asyncio.sleep(2)
        
        # Salva HTML pra debug
        try:
            html = await page.content()
            with open("/root/sierra/debug_resultados.html", "w") as f:
                f.write(html)
            logger.info(f"HTML de resultados salvo ({len(html)} bytes)")
        except Exception as e:
            logger.warning(f"Erro ao salvar HTML debug: {e}")
        
        # Extração via JavaScript com seletores REAIS do Agilizador
        resultados = await page.evaluate("""
            () => {
                const results = [];
                const seen = new Set();  // Evita duplicatas (mobile + desktop)
                
                // Cada ".pacote" é um bloco de resultado
                // Pega apenas os que NÃO são duplicatas mobile
                const pacotes = document.querySelectorAll('.pacote');
                
                pacotes.forEach(pacote => {
                    // Nome da seguradora
                    const nomeEl = pacote.querySelector('.pacote__seg-nome');
                    if (!nomeEl) return;
                    const nome = nomeEl.textContent.trim();
                    if (!nome) return;
                    
                    // Nome/título do pacote (Auto, Auto Clássico, Assistência Exclusiva, etc.)
                    const tituloEl = pacote.querySelector('.pacote__name, .pacote__title, .expansion-panel__title');
                    let tituloPacote = tituloEl ? tituloEl.textContent.trim() : '';
                    
                    // Tipo de cobertura (Compreensiva, Roubo e Furto, etc.)
                    const coberturaEl = pacote.querySelector('.pacote__cobertura');
                    let cobertura = '';
                    if (coberturaEl) {
                        // Pega os spans/textos que não são "Cobertura" nem "Editar Coberturas"
                        const textos = coberturaEl.textContent.replace(/Cobertura/gi, '').replace(/Editar Coberturas/gi, '').trim();
                        cobertura = textos.split('\\n').map(t => t.trim()).filter(t => t.length > 0)[0] || '';
                    }
                    
                    // Pega o texto do prêmio dentro do pacote
                    const premioEl = pacote.querySelector('.currency-formatted--premio .currency-formatted__value');
                    let premio = premioEl ? premioEl.textContent.trim() : '';
                    
                    // Franquia
                    const franquiaEl = pacote.querySelector('.currency-formatted--franquia .currency-formatted__value');
                    let franquia = franquiaEl ? franquiaEl.textContent.trim() : '';
                    
                    // Número da cotação
                    const cotacaoEl = pacote.querySelector('.pacote__value--cotacao');
                    let cotacao = cotacaoEl ? cotacaoEl.textContent.trim() : '';
                    
                    // Mensagem de erro
                    const erroEl = pacote.querySelector('.expansion-panel__value--error, .expansion-panel__content-error');
                    let erro = erroEl ? erroEl.textContent.trim() : '';
                    
                    // Loading?
                    const isLoading = pacote.querySelector('.pacote__seg--loading') !== null ||
                                     pacote.classList.contains('pacote__seg--loading');
                    
                    // Parcelas (procura texto tipo "10x sem juros")
                    const pacoteText = pacote.textContent || '';
                    const parcelasMatch = pacoteText.match(/(\\d+)\\s*x\\s*(sem\\s*juros|s\\/\\s*juros)?/i);
                    let parcelas = parcelasMatch ? parcelasMatch[0] : '';
                    
                    // Chave de deduplicação: nome + premio (evita mobile/desktop duplicados)
                    const key = nome + '|' + premio + '|' + franquia;
                    if (seen.has(key)) return;
                    seen.add(key);
                    
                    // Formata prêmio como R$ se tiver valor numérico
                    if (premio && !premio.includes('R$')) {
                        premio = 'R$ ' + premio;
                    }
                    if (franquia && !franquia.includes('R$')) {
                        franquia = 'R$ ' + franquia;
                    }
                    
                    results.push({
                        seguradora: nome,
                        pacote: tituloPacote || '',
                        cobertura: cobertura || '',
                        premio: premio || '',
                        franquia: franquia || '',
                        parcelas: parcelas,
                        numero: cotacao,
                        mensagem: erro || (isLoading ? 'Ainda calculando...' : ''),
                        loading: isLoading
                    });
                });
                
                return results;
            }
        """)
        
        logger.info(f"Resultados extraídos: {len(resultados)}")
        for r in resultados:
            status = r.get('mensagem', '') or ('✅' if r['premio'] else '—')
            logger.info(f"  → {r['seguradora']}: {r['premio'] or 'sem valor'} | franquia={r['franquia'] or '-'} | {r['parcelas']} | nº={r['numero']} | {status}")
        
        return resultados
    except Exception as e:
        logger.error(f"Erro ao extrair resultados: {e}")
        return []


async def _abrir_formulario_auto(page: Page):
    """Clica em Nova Cotação > Carro e garante que todas as seguradoras estão marcadas."""
    await _fechar_modais(page)
    btn = page.locator('[data-testid="btn_nova-cotacao"]')
    await btn.click(force=True)
    await asyncio.sleep(2)
    await page.locator('span:has-text("Carro")').first.click()
    await asyncio.sleep(8)
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(3)
    await _fechar_modais(page)
    
    # Garante que TODAS as seguradoras estão selecionadas
    # Scroll até a seção de seguradoras
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await asyncio.sleep(1)
    
    # Clica "Selecionar todas" — se já estiver marcada, desmarca e remarca
    sel_todas = page.locator('mat-checkbox:has-text("Selecionar todas")')
    if await sel_todas.count() > 0:
        # Verifica se está marcada checando a classe
        is_checked = await sel_todas.evaluate('el => el.classList.contains("mat-mdc-checkbox-checked") || el.classList.contains("mat-checkbox-checked")')
        if not is_checked:
            await sel_todas.click(force=True)
            logger.info("✅ 'Selecionar todas' seguradoras marcada")
            await asyncio.sleep(1)
        else:
            logger.info("✅ 'Selecionar todas' já estava marcada")
    else:
        logger.warning("⚠️ Checkbox 'Selecionar todas' não encontrada")
    
    # Volta pro topo do formulário
    await page.evaluate("window.scrollTo(0, 0)")
    await asyncio.sleep(0.5)


async def calcular_cotacao(session_data: dict, on_progress=None, chat_id: int = None) -> dict:
    """
    Preenche o formulário do Agilizador e calcula.
    session_data: dict com 'cnh', 'crvl', 'cep', 'endereco', 'cnh_condutor' (opcional)
    Se chat_id fornecido, mantém browser aberto pra download de PDF depois.
    """
    cnh  = session_data.get("cnh") or {}
    crvl = session_data.get("crvl") or {}
    cnh_condutor = session_data.get("cnh_condutor") or {}
    cep  = re.sub(r"\D", "", session_data.get("cep", ""))

    # Fecha sessão anterior se existir
    if chat_id:
        await fechar_sessao(chat_id)

    _page_ref = [None]  # referência pra screenshot
    
    async def progress(msg: str):
        logger.info(msg)
        if on_progress:
            screenshot = None
            if _page_ref[0]:
                try:
                    screenshot = await _page_ref[0].screenshot(type="jpeg", quality=60)
                except:
                    pass
            try:
                await on_progress(msg, screenshot=screenshot)
            except TypeError:
                # fallback se on_progress não aceita screenshot
                await on_progress(msg)

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    page = await browser.new_page(viewport={"width": 1280, "height": 900})
    _page_ref[0] = page
    
    # Intercepta TODAS as respostas de rede pra capturar PDFs e dados da API
    _captured_api = {}  # URL → response body
    
    async def _on_response(response):
        url = response.url
        try:
            # Captura respostas da API de versões/cálculos
            if 'multicalculo.net/calculo' in url or 'aggilizador.com.br/calculo' in url:
                if response.status == 200:
                    body = await response.text()
                    _captured_api[url] = body
                    logger.info(f"Interceptou API: {url[:80]} ({len(body)} chars)")
                    # Salva pra análise
                    try:
                        import json as _j
                        safe_name = url.split('/')[-1][:20].replace('?','_')
                        with open(f"/root/sierra/downloads/api_debug_{safe_name}.json", "w") as _f:
                            _f.write(body)
                        # Log da estrutura
                        d = _j.loads(body)
                        if isinstance(d, list) and d:
                            f0 = d[0] if isinstance(d[0], dict) else {}
                            logger.info(f"API struct: list[{len(d)}] keys={list(f0.keys())[:8]}")
                            if 'calculos' in f0:
                                for c in f0['calculos'][:20]:
                                    seg = c.get('nomeSeguradora','?')
                                    ress = c.get('resultados',[])
                                    pdfs = sum(1 for r in ress if r.get('pathPdf'))
                                    premios = [r.get('premio') for r in ress if r.get('pathPdf')]
                                    logger.info(f"  versoes→ {seg}: {len(ress)} res, {pdfs} pdfs, premios={premios}")
                            elif 'nomeSeguradora' in f0:
                                for c in d[:20]:
                                    seg = c.get('nomeSeguradora','?')
                                    ress = c.get('resultados',[])
                                    pdfs = sum(1 for r in ress if r.get('pathPdf'))
                                    premios = [r.get('premio') for r in ress if r.get('pathPdf')]
                                    logger.info(f"  calculos→ {seg}: {len(ress)} res, {pdfs} pdfs, premios={premios}")
                        elif isinstance(d, dict):
                            logger.info(f"API struct: dict keys={list(d.keys())[:8]}")
                    except Exception as e:
                        logger.warning(f"Debug save err: {e}")
            # Captura URLs de PDF
            if 'quotation-files' in url or 'pathPdf' in url:
                _captured_api[url] = str(response.status)
                logger.info(f"Interceptou PDF URL: {url[:80]}")
        except:
            pass
    
    page.on("response", _on_response)
    keep_open = False  # só mantém aberto se deu sucesso

    try:
        await progress("🔐 Conectando ao Agilizador...")
        await _login(page)

        await progress("📋 Abrindo formulário de cotação...")
        await _abrir_formulario_auto(page)
        await _fechar_modais(page)

        # ── SEGURADO ─────────────────────────────────────
        await progress("👤 Preenchendo segurado...")
            
        cpf  = re.sub(r"\D", "", cnh.get("cpf") or crvl.get("cpf_cnpj", ""))
        nome = cnh.get("nome") or crvl.get("proprietario", "")
        nasc = cnh.get("data_nascimento", "")

        await _fill_by_fc(page, "cpfCnpj", cpf)
        await asyncio.sleep(1)
        await _fill_by_name(page, "nomeSegurado", nome)
        await _fill_by_name(page, "dataNascimento", nasc)  # fc=dataNasc, name=dataNascimento

        # CEP residencial (mesmo que pernoite por padrão)
        if cep:
            cep_fmt = f"{cep[:5]}-{cep[5:]}" if len(cep) == 8 else cep
            await _fill_by_name(page, "cepImovel", cep_fmt)
            await asyncio.sleep(1)

        # ── CONDUTOR (se diferente do proprietário) ────────
        if cnh_condutor and cnh_condutor.get("nome"):
            await progress("🚘 Preenchendo condutor...")
            try:
                # Tenta marcar "Segurado é condutor = Não"
                # O Agilizador pode ter radio buttons ou mat-select pra isso
                cond_nome = cnh_condutor.get("nome", "")
                cond_cpf = re.sub(r"\D", "", cnh_condutor.get("cpf", ""))
                cond_nasc = cnh_condutor.get("data_nascimento", "")
                    
                # Preenche campos do condutor se existirem
                if cond_nome:
                    await _fill_by_name(page, "nomeCondutor", cond_nome)
                if cond_cpf:
                    await _fill_by_fc(page, "cpfCondutor", cond_cpf)
                if cond_nasc:
                    await _fill_by_name(page, "dataNascCondutor", cond_nasc)
                    
                logger.info(f"Condutor preenchido: {cond_nome}")
            except Exception as e:
                logger.warning(f"Erro ao preencher condutor: {e}")

        # ── VEÍCULO ──────────────────────────────────────
        await progress("🚗 Preenchendo veículo...")
        await _fechar_modais(page)

        placa   = _formatar_placa(crvl.get("placa", ""))
        chassi  = crvl.get("chassi", "")
        ano_fab = crvl.get("ano_fabricacao", "")
        ano_mod = crvl.get("ano_modelo", "")
        modelo  = crvl.get("marca_modelo", "")

        veiculo_preenchido = False

        if placa:
            await _type_placa(page, placa, modelo)
            await asyncio.sleep(3)
                
            # Verifica se a placa preencheu o modelo automaticamente
            modelo_auto = await page.locator('input[name="modelo"]').first.input_value()
            if modelo_auto and modelo_auto.strip():
                veiculo_preenchido = True
                logger.info(f"Placa preencheu modelo: {modelo_auto}")
                
                # Verifica se ano e combustível foram preenchidos também
                ano_auto = ""
                try:
                    ano_auto = await page.locator('input[name="anoFab"]').first.input_value()
                except: pass
                comb_auto = ""
                try:
                    comb_auto = await page.locator('mat-select[formcontrolname="combustivel"] .mat-select-value-text').first.inner_text()
                except: pass
                logger.info(f"  Após placa: anoFab='{ano_auto}', combustivel='{comb_auto}'")
                
                # Se faltou ano fabricação, preenche do CRVL
                if not ano_auto and ano_fab:
                    await _fill_by_name(page, "anoFab", ano_fab)
                    await asyncio.sleep(1)
                    logger.info(f"  Preencheu anoFab do CRVL: {ano_fab}")

        # Se a placa não funcionou, busca pelo modelo/FIPE
        if not veiculo_preenchido and modelo:
            logger.info(f"Placa não retornou veículo. Buscando por modelo: {modelo}")
            await _fechar_modais(page)
                
            # Preenche ano fabricação primeiro (necessário pra FIPE)
            if ano_fab:
                await page.locator('input[name="anoFab"]').first.click(force=True, timeout=FIELD_TIMEOUT)
                await page.locator('input[name="anoFab"]').first.fill(ano_fab)
                await asyncio.sleep(0.5)

            # Seleciona ano modelo
            if ano_mod:
                await _select_mat(page, "anoMod", ano_mod)
                await asyncio.sleep(0.5)

            # Busca modelo pelo nome (campo modelo tem autocomplete)
            # Extrai marca e modelo do CRVL: "FORD/KA SE PLUS 1.0 SD C"
            modelo_upper = modelo.upper()
            marca = ""
            nome_modelo = modelo_upper
            if "/" in modelo_upper:
                partes = modelo_upper.split("/", 1)
                marca = partes[0].strip()
                nome_modelo = partes[1].strip()
                
            # Palavras-chave do modelo completo
            palavras_modelo = [p for p in nome_modelo.split() if len(p) > 1]
                
            # Tenta múltiplas buscas até achar resultado
            buscas = []
            # 1. Nome do modelo principal (ex: "KA SE PLUS")
            if palavras_modelo:
                buscas.append(" ".join(palavras_modelo[:3]))
            # 2. Marca + primeiro nome (ex: "FORD KA")
            if marca and palavras_modelo:
                buscas.append(f"{marca} {palavras_modelo[0]}")
            # 3. Só o primeiro nome do modelo (ex: "KA")
            if palavras_modelo:
                buscas.append(palavras_modelo[0])
                
            campo_modelo = page.locator('input[name="modelo"]').first
            encontrou = False
                
            for busca in buscas:
                if encontrou:
                    break
                    
                await campo_modelo.click(force=True, timeout=FIELD_TIMEOUT)
                await campo_modelo.fill("")
                await campo_modelo.type(busca, delay=80)
                await asyncio.sleep(3)
                    
                dropdown = page.locator('mat-option')
                qtd = await dropdown.count()
                logger.info(f"Busca '{busca}': {qtd} resultados")
                    
                if qtd > 0:
                    # Tenta achar o modelo mais parecido
                    melhor = 0
                    melhor_score = 0
                    for i in range(qtd):
                        txt = (await dropdown.nth(i).inner_text()).upper()
                        score = 0
                        # Marca bate = +5 pontos
                        if marca and marca in txt:
                            score += 5
                        # Cada palavra do modelo que bate = +1
                        for p in palavras_modelo:
                            if p in txt:
                                score += 1
                        if score > melhor_score:
                            melhor_score = score
                            melhor = i
                        
                    txt_sel = await dropdown.nth(melhor).inner_text()
                    txt_upper = txt_sel.upper()
                        
                    # O PRIMEIRO nome do modelo (KA, ONIX, GOL, etc) TEM que estar presente
                    # Sem isso, aceita qualquer lixo
                    primeiro_nome = palavras_modelo[0] if palavras_modelo else ""
                    primeiro_nome_ok = primeiro_nome and (
                        # Match como palavra inteira (não substring)
                        f" {primeiro_nome} " in f" {txt_upper} " or
                        txt_upper.startswith(f"{primeiro_nome} ") or
                        txt_upper.endswith(f" {primeiro_nome}")
                    )
                    marca_ok = marca and marca.upper() in txt_upper
                        
                    # Aceita score >= 2, ou score >= 1 se primeiro nome OK 
                    # (códigos de acabamento como "CL AD" nunca batem no dropdown)
                    score_ok = melhor_score >= 2 or (primeiro_nome_ok and melhor_score >= 1)
                    if primeiro_nome_ok and score_ok:
                        await dropdown.nth(melhor).click(force=True, timeout=FIELD_TIMEOUT)
                        logger.info(f"Modelo selecionado (score={melhor_score}): {txt_sel.strip()}")
                        veiculo_preenchido = True
                        encontrou = True
                        # Espera campos dependentes (combustível, carroceria, etc) carregarem
                        await asyncio.sleep(4)
                    else:
                        logger.warning(f"Nenhum match bom pra '{busca}' (primeiro_nome={primeiro_nome}, ok={primeiro_nome_ok}, marca_ok={marca_ok}, score={melhor_score}), tentando próxima...")
                        await page.keyboard.press("Escape")
                        await asyncio.sleep(0.5)
                else:
                    logger.warning(f"Nenhum resultado pra '{busca}'")
                
            if not encontrou:
                logger.warning(f"Não encontrou modelo: {modelo}")

        # Preenche ano fabricação se ainda não foi
        if ano_fab and not veiculo_preenchido:
            await _fill_by_name(page, "anoFab", ano_fab)
            await asyncio.sleep(1)

        # Ano modelo — é mat-select (fc=anoMod)
        if ano_mod:
            # Verifica se já tem valor selecionado
            try:
                txt_atual = await page.locator('mat-select[formcontrolname="anoMod"] .mat-select-value-text').first.inner_text()
                if not txt_atual or ano_mod not in txt_atual:
                    await _select_mat(page, "anoMod", ano_mod)
            except:
                await _select_mat(page, "anoMod", ano_mod)

        # Combustível — mat-select fc=combustivel (SEMPRE preencher)
        combustivel = crvl.get("combustivel", "")
        comb_option = "Flex"  # default seguro
        if combustivel:
            comb_upper = combustivel.upper()
            if "ALCOOL" in comb_upper and "GASOLINA" in comb_upper:
                comb_option = "Flex"
            elif "FLEX" in comb_upper:
                comb_option = "Flex"
            elif "ALCOOL" in comb_upper or "ETANOL" in comb_upper:
                comb_option = "Álcool"
            elif "DIESEL" in comb_upper:
                comb_option = "Diesel"
            elif "GASOLINA" in comb_upper:
                comb_option = "Gasolina"
            elif "ELETRIC" in comb_upper:
                comb_option = "Elétrico"
            elif "HIBRIDO" in comb_upper or "HÍBRIDO" in comb_upper:
                comb_option = "Híbrido"
        # Espera o dropdown de combustível ter opções (depende de modelo FIPE)
        for retry in range(5):
            opts_count = await page.evaluate("""
                (() => {
                    const el = document.querySelector('mat-select[formcontrolname="combustivel"]');
                    if (!el) return -1;
                    // Angular mat-select stores options internally
                    el.click();
                    return document.querySelectorAll('mat-option').length;
                })()
            """)
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)
            if opts_count and opts_count > 0:
                logger.info(f"Combustível: {opts_count} opções disponíveis (tentativa {retry+1})")
                break
            logger.info(f"Combustível: aguardando opções carregarem... (tentativa {retry+1})")
            await asyncio.sleep(2)
        
        await _select_mat(page, "combustivel", comb_option)
        logger.info(f"Combustível: '{combustivel}' → {comb_option}")

        # Chassi válido: 17 chars alfanuméricos, formato real
        # Chassi: SÓ preenche se tiver chassi COMPLETO (17 chars válidos)
        # Chassi parcial ou gerado falha na validação do Agilizador (dígito verificador VIN)
        # O Agilizador aceita cotação SEM chassi — campo é opcional pra cálculo
        if chassi:
            chassi_clean = re.sub(r'[^A-Za-z0-9]', '', str(chassi)).upper()
            if len(chassi_clean) == 17:
                await _fill_by_name(page, "chassi", chassi_clean)
                logger.info(f"Chassi completo: {chassi_clean}")
            else:
                # Limpa o campo — não preenche chassi parcial
                try:
                    el = page.locator('input[name="chassi"]').first
                    await el.click(force=True, timeout=3000)
                    await el.fill("", timeout=3000)
                    logger.info(f"Chassi parcial '{chassi}' ignorado — campo limpo")
                except:
                    logger.info(f"Chassi parcial '{chassi}' ignorado")

        # ── CEP PERNOITE ─────────────────────────────────
        if cep:
            cep_fmt = f"{cep[:5]}-{cep[5:]}" if len(cep) == 8 else cep
            await _fill_by_name(page, "perfilCepPernoite", cep_fmt)
            await asyncio.sleep(0.5)
        
        # NOTA: Telefone e Email NÃO existem no formulário de cotação do Agilizador
        # (campos input[name="telefone"] e input[name="email"] não estão no DOM)

        # ── PERFIL DE RISCO ───────────────────────────────
        await _fechar_modais(page)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)

        # Tipo de Carroceria — pega primeira opção disponível (geralmente "Passeio" ou similar)
        async def _select_first_option(page, fc, label=""):
            """Abre mat-select e seleciona a primeira opção."""
            try:
                sel = page.locator(f'mat-select[formcontrolname="{fc}"]').first
                if await sel.count() == 0:
                    logger.info(f"Campo {fc} não encontrado (pode não existir pra este veículo)")
                    return False
                # Verifica se já tem valor selecionado
                current = await sel.inner_text()
                if current and current.strip() and current.strip() not in ('', 'Selecione', '--'):
                    logger.info(f"{label or fc}: já preenchido com '{current.strip()}'")
                    return True
                
                # Força visibilidade via JS antes de clicar
                await page.evaluate(f"""
                    const el = document.querySelector('mat-select[formcontrolname="{fc}"]');
                    if (el) {{
                        el.scrollIntoView({{block: 'center'}});
                        // Expande painéis pais se colapsados
                        let parent = el.closest('mat-expansion-panel');
                        if (parent && !parent.classList.contains('mat-expanded')) {{
                            const header = parent.querySelector('mat-expansion-panel-header');
                            if (header) header.click();
                        }}
                        // Força visibilidade
                        el.style.visibility = 'visible';
                        el.style.opacity = '1';
                        let p = el.parentElement;
                        while (p) {{
                            p.style.visibility = 'visible';
                            p.style.display = '';
                            p.style.overflow = 'visible';
                            p.style.height = 'auto';
                            p = p.parentElement;
                        }}
                    }}
                """)
                await asyncio.sleep(0.8)
                
                # Tenta click normal com force
                try:
                    await sel.click(force=True, timeout=FIELD_TIMEOUT)
                except Exception:
                    # Fallback: click via JS
                    await page.evaluate(f"""
                        const el = document.querySelector('mat-select[formcontrolname="{fc}"]');
                        if (el) {{
                            el.click();
                            // Dispara evento Angular
                            el.dispatchEvent(new MouseEvent('click', {{bubbles: true}}));
                        }}
                    """)
                await asyncio.sleep(1)
                opts = page.locator('mat-option')
                qtd = await opts.count()
                if qtd > 0:
                    txt = await opts.first.inner_text()
                    await opts.first.click(force=True, timeout=FIELD_TIMEOUT)
                    logger.info(f"{label or fc}: selecionou '{txt.strip()}' ({qtd} opções)")
                    await asyncio.sleep(0.5)
                    return True
                else:
                    await page.keyboard.press("Escape")
                    logger.warning(f"{label or fc}: sem opções")
                    return False
            except Exception as e:
                logger.warning(f"{label or fc}: {str(e)[:80]}")
                try: await page.keyboard.press("Escape")
                except: pass
                return False

        # Expande TODAS as seções colapsáveis do Angular (mat-expansion-panel, accordion, etc)
        await page.evaluate("""
            () => {
                // Expande mat-expansion-panel
                document.querySelectorAll('mat-expansion-panel:not(.mat-expanded)').forEach(p => {
                    const header = p.querySelector('mat-expansion-panel-header');
                    if (header) header.click();
                });
                // Expande qualquer accordion colapsado
                document.querySelectorAll('.mat-expansion-panel:not(.mat-expanded)').forEach(p => {
                    const header = p.querySelector('.mat-expansion-panel-header');
                    if (header) header.click();
                });
                // Clica em tabs não ativos pra garantir que campos ocultos renderizem
                document.querySelectorAll('.mat-tab-label:not(.mat-tab-label-active)').forEach(t => t.click());
                // Força visibilidade de todos os mat-select
                document.querySelectorAll('mat-select').forEach(el => {
                    el.style.visibility = 'visible';
                    el.style.display = '';
                    const parent = el.closest('.mat-form-field');
                    if (parent) {
                        parent.style.visibility = 'visible';
                        parent.style.display = '';
                    }
                });
            }
        """)
        await asyncio.sleep(2)

        # Scroll pra garantir que todos os campos estejam visíveis e inicializados
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1.5)
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(0.5)

        # Scroll progressivo — desce aos poucos pra renderizar TODAS as seções (incluindo Questionário)
        page_height = await page.evaluate("document.body.scrollHeight")
        for scroll_pos in range(0, page_height + 500, 300):
            await page.evaluate(f"window.scrollTo(0, {scroll_pos})")
            await asyncio.sleep(0.3)
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)
        logger.info(f"Scroll progressivo concluído (page height: {page_height}px)")
        
        # HACK: O Agilizador renderiza FORMULARIO-AUTO-PERFIL-CAMINHAO com display:none
        # mas valida seus campos (tpCarroceria, areaCirculacao, periodoUso).
        # Solução: forçar visibilidade dos ancestrais + preencher via JS trigger click.
        caminhao_exists = await page.evaluate("""
            () => !!document.querySelector('formulario-auto-perfil-caminhao')
        """)
        if caminhao_exists:
            logger.info("📦 Componente PERFIL-CAMINHAO detectado — preenchendo campos ocultos")
            
            # 1. Força visibilidade do componente e TODOS os ancestrais
            await page.evaluate("""
                () => {
                    const caminhao = document.querySelector('formulario-auto-perfil-caminhao');
                    if (!caminhao) return;
                    let el = caminhao;
                    while (el) {
                        el.style.setProperty('display', 'block', 'important');
                        el.style.setProperty('visibility', 'visible', 'important');
                        el.style.setProperty('opacity', '1', 'important');
                        el.style.setProperty('height', 'auto', 'important');
                        el.style.setProperty('overflow', 'visible', 'important');
                        el = el.parentElement;
                    }
                }
            """)
            await asyncio.sleep(1)
            
            # 2. Preenche cada mat-select via JS trigger click + Playwright option select
            for fc in ['tpUso', 'tpCarroceria', 'areaCirculacao', 'periodoUso', 'perguntasAdicionais']:
                try:
                    exists = await page.evaluate(f"""
                        () => {{
                            const el = document.querySelector('formulario-auto-perfil-caminhao mat-select[formcontrolname="{fc}"]');
                            if (!el) return 'none';
                            const val = el.querySelector('.mat-mdc-select-value-text');
                            return val ? val.textContent.trim() : '';
                        }}
                    """)
                    if exists == 'none':
                        continue
                    if exists and exists not in ('', 'Selecione', '--'):
                        logger.info(f"  ✅ {fc}: já tem '{exists}'")
                        continue
                    
                    # Click no trigger pra abrir dropdown
                    await page.evaluate(f"""
                        () => {{
                            const el = document.querySelector('formulario-auto-perfil-caminhao mat-select[formcontrolname="{fc}"]');
                            if (el) {{
                                const trigger = el.querySelector('.mat-mdc-select-trigger');
                                (trigger || el).click();
                            }}
                        }}
                    """)
                    await asyncio.sleep(1)
                    
                    opts = page.locator('mat-option')
                    n = await opts.count()
                    if n > 0:
                        await opts.first.click(force=True)
                        logger.info(f"  ✅ {fc} preenchido ({n} opções)")
                    else:
                        logger.warning(f"  ❌ {fc}: sem opções")
                        await page.keyboard.press("Escape")
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.warning(f"  ❌ {fc}: {str(e)[:50]}")
                    try: await page.keyboard.press("Escape")
                    except: pass
            
            # 3. Preenche inputs de texto do caminhão (se existirem e estiverem vazios)
            for fc in ['equipamento', 'seguroCarga']:
                try:
                    await page.evaluate(f"""
                        () => {{
                            const el = document.querySelector('formulario-auto-perfil-caminhao input[formcontrolname="{fc}"]');
                            if (el && !el.value) {{
                                el.value = 'N/A';
                                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                            }}
                        }}
                    """)
                except: pass
            
            # 4. Esconde de volta (pra não confundir screenshot)
            await page.evaluate("""
                () => {
                    const el = document.querySelector('formulario-auto-perfil-caminhao');
                    if (el) el.style.setProperty('display', 'none', 'important');
                }
            """)
            logger.info("📦 Campos caminhão preenchidos e componente re-ocultado")
            await asyncio.sleep(0.5)

        # Campos obrigatórios de perfil — preenche com primeira opção disponível
        PERFIL_CAMPOS = [
            ("tpCarroceria",    "Tipo Carroceria"),
            ("risco",           "Gerenc. Risco"),
            ("tipoCarga",       "Tipo Carga"),
            ("areaCirculacao",  "Área Circulação"),
            ("periodoUso",      "Período de Uso"),
            ("tempoHabilitacao","Tempo Habilitação"),
            ("garagem",         "Garagem"),
            ("estadoCivil",     "Estado Civil"),
            ("sexo",            "Sexo"),
            ("utilizacao",      "Utilização"),
            ("perfil",          "Perfil"),
        ]
        for fc, label in PERFIL_CAMPOS:
            await _select_first_option(page, fc, label)
            await _fechar_modais(page)

        # ── CAMPOS ADICIONAIS DE PERFIL ──────────────────
        # Preenche campos que podem não ter sido preenchidos ainda
        CAMPOS_EXTRAS = [
            ("tpUso",           "Tipo Uso"),
            ("jovemCondutor",   "Jovem Condutor"),
            ("tipoResidencia",  "Tipo Residência"),
            ("kmMensal",        "KM Mensal"),
            ("isPCD",           "PCD"),
            ("isencaoFiscal",   "Isenção Fiscal"),
            ("tipoCobertura",   "Tipo Cobertura"),
            ("relaSegCond",     "Relação Seg/Condutor"),
        ]
        for fc, label in CAMPOS_EXTRAS:
            await _select_first_option(page, fc, label)
            await _fechar_modais(page)
            
        # Varredura final: qualquer mat-select vazio → preenche com 1ª opção
        vazios_finais = await page.evaluate("""
            () => {
                const fcs = [];
                document.querySelectorAll('mat-select').forEach(el => {
                    const fc = el.getAttribute('formcontrolname') || '';
                    const txt = el.textContent.trim();
                    if (fc && (!txt || txt === 'Selecione' || txt === '--' || txt === '')) {
                        fcs.push(fc);
                    }
                });
                return fcs;
            }
        """)
        if vazios_finais:
            logger.info(f"Varredura final: {len(vazios_finais)} mat-selects vazios: {vazios_finais}")
            for fc in vazios_finais:
                await _select_first_option(page, fc, f"AUTO:{fc}")
                await _fechar_modais(page)

        # ── VIGÊNCIA ─────────────────────────────────────
        await progress("📅 Configurando vigência...")
        await _fechar_modais(page)

        inicio, fim = _vigencia_padrao()
        await _fill_by_name(page, "vigenciaIni", inicio)
        await _fill_by_name(page, "vigenciaFim", fim)

        # ── COMISSÃO 10% ─────────────────────────────────
        await progress("💼 Configurando comissão (10%)...")
        await _fechar_modais(page)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)

        # Preenche TODOS os campos percComissao_XX vazios com 10
        comissao_inputs = await page.evaluate("""
            () => {
                const names = [];
                document.querySelectorAll('input[name^="percComissao_"]').forEach(el => {
                    if (!el.value || el.value.trim() === '' || el.value.trim() === '0') {
                        names.push(el.name);
                    }
                });
                return names;
            }
        """)
        preenchidos = 0
        for name in comissao_inputs:
            try:
                campo = page.locator(f'input[name="{name}"]').first
                await campo.click(force=True, timeout=FIELD_TIMEOUT)
                await campo.fill("")
                await campo.type("10", delay=50)
                await page.keyboard.press("Tab")
                await asyncio.sleep(0.2)
                preenchidos += 1
            except Exception as e:
                logger.warning(f"Comissão {name}: {str(e)[:60]}")
        if preenchidos:
            logger.info(f"Comissão: preencheu {preenchidos}/{len(comissao_inputs)} campos com 10%")

        # ── CALCULAR ─────────────────────────────────────
        await _fechar_modais(page)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)

        await progress("⚙️ Clicando em Calcular...")
        calcular_btn = page.locator('button:has-text("Calcular")')
        if await calcular_btn.count() > 0:
            await calcular_btn.first.scroll_into_view_if_needed()
            await asyncio.sleep(0.5)
            await calcular_btn.first.click(force=True)
            await asyncio.sleep(3)

            # Fecha modais pós-clique (CPF já cotado, etc)
            await _fechar_modais(page)

            # Verifica campos em vermelho (EXCLUI componente caminhão oculto)
            campos_erro = await page.evaluate("""
                () => {
                    const all = document.querySelectorAll('.mat-form-field-invalid, .ng-invalid.ng-touched');
                    let count = 0;
                    all.forEach(el => {
                        // Ignora campos dentro do perfil-caminhao oculto
                        if (!el.closest('formulario-auto-perfil-caminhao')) count++;
                    });
                    return count;
                }
            """)
            if campos_erro > 0:
                await progress(f"⚠️ {campos_erro} campo(s) em vermelho — tentando corrigir automaticamente...")

                # Detecta quais mat-selects estão inválidos e preenche com primeira opção
                fcs_invalidos = await page.evaluate("""
                    () => {
                        const fcs = [];
                        // mat-select inválidos
                        document.querySelectorAll('mat-select.ng-invalid, mat-select.mat-select-invalid').forEach(el => {
                            const fc = el.getAttribute('formcontrolname') || el.getAttribute('ng-reflect-name') || '';
                            if (fc) fcs.push(fc);
                        });
                        // mat-form-field com invalid
                        document.querySelectorAll('.mat-form-field-invalid mat-select').forEach(el => {
                            const fc = el.getAttribute('formcontrolname') || el.getAttribute('ng-reflect-name') || '';
                            if (fc && !fcs.includes(fc)) fcs.push(fc);
                        });
                        return fcs;
                    }
                """)
                logger.info(f"mat-selects inválidos detectados: {fcs_invalidos}")

                # Tenta preencher via Angular FormControl direto (bypass DOM visibility)
                fixed_via_angular = await page.evaluate("""
                    (campos) => {
                        const fixed = [];
                        // Valores padrão pra campos comuns
                        const defaults = {
                            'tpCarroceria': '1',    // Sedan
                            'areaCirculacao': '1',  // Urbana
                            'periodoUso': '1',      // Diurno
                            'tpUso': '1',           // Particular
                            'perguntasAdicionais': '2', // Não
                        };
                        
                        for (const fc of campos) {
                            try {
                                const el = document.querySelector(`mat-select[formcontrolname="${fc}"]`);
                                if (!el) continue;
                                
                                // Tenta acessar o Angular FormControl via __ngContext__
                                const ngRef = el.__ngContext__ || el.closest('[_nghost-ng-c]')?.__ngContext__;
                                
                                // Método 1: Clica nas mat-tab pra renderizar campos ocultos
                                const tabs = document.querySelectorAll('.mat-tab-label, .mat-mdc-tab');
                                for (const tab of tabs) {
                                    if (!tab.classList.contains('mat-tab-label-active') && 
                                        !tab.classList.contains('mdc-tab--active')) {
                                        tab.click();
                                    }
                                }
                                
                                // Método 2: Expande TODOS os painéis
                                document.querySelectorAll('mat-expansion-panel').forEach(p => {
                                    if (!p.classList.contains('mat-expanded')) {
                                        const h = p.querySelector('mat-expansion-panel-header');
                                        if (h) h.click();
                                    }
                                });
                                
                                // Método 3: Remove display:none de ancestrais
                                let parent = el.parentElement;
                                while (parent) {
                                    const style = window.getComputedStyle(parent);
                                    if (style.display === 'none') parent.style.display = 'block';
                                    if (style.visibility === 'hidden') parent.style.visibility = 'visible';
                                    if (style.height === '0px') parent.style.height = 'auto';
                                    if (style.overflow === 'hidden') parent.style.overflow = 'visible';
                                    parent = parent.parentElement;
                                }
                                
                                fixed.push(fc);
                            } catch(e) {}
                        }
                        return fixed;
                    }
                """, fcs_invalidos)
                logger.info(f"Angular fix tentado em: {fixed_via_angular}")
                await asyncio.sleep(2)
                
                # Método nuclear: setar valores via Angular FormControl diretamente
                angular_set = await page.evaluate("""
                    (campos) => {
                        const defaults = {
                            'tpCarroceria': 1, 'areaCirculacao': 1, 'periodoUso': 1,
                            'tpUso': 1, 'perguntasAdicionais': 2
                        };
                        const fixed = [];
                        for (const fc of campos) {
                            try {
                                const el = document.querySelector(`[formcontrolname="${fc}"]`);
                                if (!el) continue;
                                // Acessa o Angular NgControl via __ngContext__ ou _lView
                                const val = defaults[fc] || 1;
                                // Dispara eventos Angular
                                const ev = new Event('change', {bubbles: true});
                                el.value = val;
                                el.dispatchEvent(ev);
                                el.dispatchEvent(new Event('input', {bubbles: true}));
                                el.dispatchEvent(new Event('blur', {bubbles: true}));
                                fixed.push(fc);
                            } catch(e) {}
                        }
                        // Tenta acessar o formulário Angular global
                        try {
                            const appRef = window.ng?.getComponent(document.querySelector('app-root'));
                            if (appRef?.form) {
                                for (const fc of campos) {
                                    const val = defaults[fc] || 1;
                                    if (appRef.form.controls[fc]) {
                                        appRef.form.controls[fc].setValue(val);
                                        appRef.form.controls[fc].markAsDirty();
                                        fixed.push(fc + '_ng');
                                    }
                                }
                            }
                        } catch(e) {}
                        return fixed;
                    }
                """, fcs_invalidos)
                logger.info(f"Angular setValue tentado: {angular_set}")
                await asyncio.sleep(1)
                
                # Agora tenta clicar nos campos que foram liberados
                for fc in fcs_invalidos:
                    await _select_first_option(page, fc, fc)
                    await _fechar_modais(page)

                # Se não detectou via JS, tenta lista completa de candidatos
                if not fcs_invalidos:
                    CANDIDATOS_EXTRA = [
                        ("combustivel",      "Combustível"),
                        ("tempoHabilitacao", "Tempo Habilitação"),
                        ("garagem",          "Garagem"),
                        ("estadoCivil",      "Estado Civil"),
                        ("sexo",             "Sexo"),
                        ("utilizacao",       "Utilização"),
                        ("perfil",           "Perfil"),
                        ("tpCarroceria",     "Tipo Carroceria"),
                        ("risco",            "Gerenc. Risco"),
                        ("tipoCarga",        "Tipo Carga"),
                        ("areaCirculacao",   "Área Circulação"),
                        ("tpUso",            "Tipo Uso"),
                        ("jovemCondutor",    "Jovem Condutor"),
                        ("tipoResidencia",   "Tipo Residência"),
                        ("kmMensal",         "KM Mensal"),
                        ("isPCD",            "PCD"),
                        ("isencaoFiscal",    "Isenção Fiscal"),
                        ("tipoCobertura",    "Tipo Cobertura"),
                        ("relaSegCond",      "Relação Seg/Condutor"),
                    ]
                    for fc, label in CANDIDATOS_EXTRA:
                        await _select_first_option(page, fc, label)
                        await _fechar_modais(page)

                await asyncio.sleep(1)
                await _fechar_modais(page)

                # Tenta calcular de novo
                await progress("🔁 Recalculando após correção...")
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(0.5)
                calcular_btn2 = page.locator('button:has-text("Calcular")')
                if await calcular_btn2.count() > 0:
                    await calcular_btn2.first.scroll_into_view_if_needed()
                    await calcular_btn2.first.click(force=True)
                    await asyncio.sleep(3)
                    await _fechar_modais(page)

                # Verifica de novo
                campos_erro2 = await page.evaluate("""
                    () => {
                        const all = document.querySelectorAll('.mat-form-field-invalid, .ng-invalid.ng-touched');
                        let count = 0;
                        all.forEach(el => {
                            if (!el.closest('formulario-auto-perfil-caminhao')) count++;
                        });
                        return count;
                    }
                """)
                if campos_erro2 > 0:
                    await progress(f"⚠️ Ainda {campos_erro2} campo(s) em vermelho após retry...")
                    await page.evaluate("""
                        const erroEl = document.querySelector('.mat-form-field-invalid, .ng-invalid.ng-touched');
                        if (erroEl) erroEl.scrollIntoView({block: 'center'});
                        else window.scrollTo(0, 0);
                    """)
                    await asyncio.sleep(1)
                    await _fechar_modais(page)
                    screenshot = await page.screenshot(type="jpeg", quality=80)
                    try:
                        with open("/root/sierra/debug_erro.jpg", "wb") as f:
                            f.write(screenshot)
                        # Detecta nomes: verifica inputs, mat-select e labels
                        campos_nomes = await page.evaluate("""
                            () => {
                                const campos = [];
                                document.querySelectorAll('.mat-form-field-invalid').forEach(wrapper => {
                                    const label = wrapper.querySelector('mat-label, label');
                                    const inp = wrapper.querySelector('input, mat-select');
                                    const fc = inp ? (inp.getAttribute('formcontrolname') || inp.getAttribute('name') || '') : '';
                                    const lbl = label ? label.textContent.trim() : fc;
                                    if (lbl) campos.push(lbl + (fc && fc !== lbl ? ' [' + fc + ']' : ''));
                                });
                                return campos;
                            }
                        """)
                        logger.info(f"Campos em vermelho (retry): {campos_nomes}")
                    except Exception as e:
                        logger.warning(f"Debug erro retry: {e}")

                    return {
                        "sucesso": False,
                        "url": page.url,
                        "msg": f"⚠️ {campos_erro2} campo(s) em vermelho. Confere na imagem.",
                        "screenshot": screenshot
                    }
                # Retry funcionou — continua normalmente pra extrair resultados

            # Sem erros — aguarda TODAS as seguradoras calcularem
            await progress("⏳ Calculando... aguardando seguradoras responderem...")
            
            # Espera até 180s (3 min) — todas seguradoras precisam terminar
            loading_zero_count = 0
            for wait_i in range(36):  # 36 × 5s = 180s
                await asyncio.sleep(5)
                tem_resultado = await page.evaluate("""
                    () => {
                        // Cards de resultado (cada seguradora)
                        const cards = document.querySelectorAll('.card-resultado, .resultado-item, [class*="resultado"], .mat-expansion-panel');
                        // Spinners de loading (seguradoras ainda calculando)
                        const loading = document.querySelectorAll('.mat-progress-spinner, .mat-spinner, [class*="loading"]:not(.mat-expansion-panel)');
                        // Texto "Calculando" visível
                        const calcText = document.querySelectorAll('*');
                        let calculando = 0;
                        for (const el of calcText) {
                            if (el.children.length === 0 && el.textContent.includes('Calculando')) calculando++;
                        }
                        return {
                            cards: cards.length,
                            loading: loading.length,
                            calculando: calculando
                        };
                    }
                """)
                
                loading_count = tem_resultado.get('loading', 0) + tem_resultado.get('calculando', 0)
                cards = tem_resultado.get('cards', 0)
                
                await progress(f"⏳ Aguardando seguradoras... ({(wait_i+1)*5}s) — {cards} responderam, {loading_count} calculando")
                
                # Só sai quando NÃO tem nenhum loading E tem pelo menos 1 resultado
                if loading_count == 0 and cards > 0:
                    loading_zero_count += 1
                    # Confirma 2x seguidas (evita falso positivo)
                    if loading_zero_count >= 2:
                        logger.info(f"Todas seguradoras finalizaram: {cards} resultados")
                        break
                else:
                    loading_zero_count = 0
                    
                # Timeout: se depois de 150s ainda tem loading, segue mesmo assim
                if wait_i >= 30 and cards > 0:
                    logger.info(f"Timeout 150s com {cards} resultados e {loading_count} loading — seguindo")
                    break
            
            await asyncio.sleep(3)
            await _fechar_modais(page)

        # Extrai resultados das cotações
        await progress("📊 Extraindo resultados...")
        resultados = await _extrair_resultados(page)

        # Screenshot do resultado
        await _fechar_modais(page)
        await asyncio.sleep(1)
        try:
            screenshot = await page.screenshot(type="jpeg", quality=75, full_page=True)
        except Exception as ss_err:
            logger.warning(f"Erro ao tirar screenshot: {ss_err}")
            screenshot = None

        # Monta mensagem com resultados
        if resultados:
            # Log todos os resultados com tipo de cobertura e nome do pacote
            for r in resultados:
                logger.info(f"  Resultado bruto: {r['seguradora']} | pacote={r.get('pacote','?')} | cobertura={r.get('cobertura','?')} | premio={r.get('premio','')}")
                
            # Pega só o PRIMEIRO pacote de cada seguradora (o principal)
            vistos = set()
            primeiro_pacote = []
            for r in resultados:
                seg = r.get('seguradora', '').strip().lower()
                if seg not in vistos:
                    vistos.add(seg)
                    primeiro_pacote.append(r)
            resultados = primeiro_pacote
                
            # Filtra APENAS Compreensiva (ou sem tipo definido — que geralmente é compreensiva)
            compreensiva = [r for r in resultados if not r.get('cobertura') or 
                           'compreensiv' in r.get('cobertura', '').lower()]
            outros = [r for r in resultados if r.get('cobertura') and 
                     'compreensiv' not in r.get('cobertura', '').lower()]
                
            # Se não tem nenhuma compreensiva, mostra tudo (fallback)
            exibir = compreensiva if compreensiva else resultados
                
            # Separa: com valor vs sem valor
            def _premio_float(r):
                try:
                    return float(r.get('premio','').replace('R$','').replace('.','').replace(',','.').strip() or '999999')
                except:
                    return 999999
                
            com_valor = sorted([r for r in exibir if r.get('premio')], 
                              key=lambda r: _premio_float(r))
            sem_valor = [r for r in exibir if not r.get('premio')]
                
            texto_resultado = "🎯 *Resultados da Cotação — Compreensiva:*\n\n"
                
            # Primeiro mostra os que têm prêmio (ordenado por valor)
            for i, r in enumerate(com_valor):
                medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "🏢"
                texto_resultado += f"{medal} *{r['seguradora']}*\n"
                texto_resultado += f"💰 Prêmio: {r['premio']}\n"
                if r.get('franquia'):
                    texto_resultado += f"💥 Franquia: {r['franquia']}\n"
                if r.get('parcelas'):
                    texto_resultado += f"📅 {r['parcelas']}\n"
                if r.get('numero'):
                    texto_resultado += f"📝 Nº: {r['numero']}\n"
                texto_resultado += "\n"
                
            # Depois mostra os sem valor (com mensagem do que apareceu)
            if sem_valor:
                texto_resultado += "─────────────────\n"
                for r in sem_valor[:10]:
                    mensagem = r.get('mensagem', '')
                    if mensagem:
                        texto_resultado += f"🏢 *{r['seguradora']}* — ⚠️ _{mensagem}_\n"
                    elif r.get('loading'):
                        texto_resultado += f"🏢 *{r['seguradora']}* — ⏳ _Ainda calculando_\n"
                    else:
                        texto_resultado += f"🏢 *{r['seguradora']}* — _Sem resultado_\n"
                    if r.get('numero'):
                        texto_resultado += f"   📝 Nº: {r['numero']}\n"
                
            # Info sobre tipos filtrados
            if outros:
                tipos_filtrados = set(r.get('cobertura','') for r in outros if r.get('cobertura'))
                texto_resultado += f"\n_ℹ️ Filtrado: mostrando apenas Compreensiva ({len(outros)} resultado(s) de {', '.join(tipos_filtrados)} omitido(s))_"
                
        else:
            texto_resultado = "✅ Cotação calculada! _(não consegui extrair detalhes automaticamente — veja o screenshot)_"

        # Captura dados completos via interceptação de rede OU API
        pdf_map = {}  # seguradora_lower → {pathPdf, identificacao, ...}
        
        # Primeiro tenta usar dados capturados pela interceptação de rede
        def _add_to_pdf_map(pdf_map, nome_seg, res):
            """Adiciona resultado ao pdf_map, agrupando por seguradora."""
            path_pdf = res.get('pathPdf', '')
            if not path_pdf or not nome_seg:
                return
            k = nome_seg.lower()
            entry = {
                'pathPdf': path_pdf,
                'identificacao': res.get('identificacao', ''),
                'nomeSeguradora': nome_seg,
                'premio': res.get('premio'),
                'pdfFileName': res.get('pdfFileNameAgger', ''),
                'cobertura': res.get('cobertura', ''),
            }
            if k not in pdf_map:
                pdf_map[k] = entry
                pdf_map[k]['_all_plans'] = [entry]
            else:
                pdf_map[k].setdefault('_all_plans', [pdf_map[k].copy()])
                # Evita duplicatas por pathPdf
                existing_urls = {p.get('pathPdf') for p in pdf_map[k]['_all_plans']}
                if path_pdf not in existing_urls:
                    pdf_map[k]['_all_plans'].append(entry)
        
        for cap_url, cap_body in _captured_api.items():
            if 'versoes' in cap_url or 'cotacao' in cap_url:
                try:
                    import json as _json2
                    api_data = _json2.loads(cap_body)
                    
                    # Estrutura 1: Array de versões (endpoint /versoes)
                    # [{calculos: [{nomeSeguradora, resultados: [{pathPdf, premio, ...}]}]}]
                    if isinstance(api_data, list) and api_data and 'calculos' in (api_data[-1] if isinstance(api_data[-1], dict) else {}):
                        latest = api_data[-1]
                        for calc in latest.get('calculos', []):
                            nome_seg = (calc.get('nomeSeguradora') or calc.get('seguradoraTxt') or '').strip()
                            for res in calc.get('resultados', []):
                                _add_to_pdf_map(pdf_map, nome_seg, res)
                    
                    # Estrutura 2: Array de cálculos (endpoint /calculos)
                    # [{nomeSeguradora, resultados: [{pathPdf, premio, ...}]}]
                    elif isinstance(api_data, list) and api_data and 'resultados' in (api_data[0] if isinstance(api_data[0], dict) else {}):
                        for calc in api_data:
                            nome_seg = (calc.get('nomeSeguradora') or calc.get('seguradoraTxt') or '').strip()
                            for res in calc.get('resultados', []):
                                _add_to_pdf_map(pdf_map, nome_seg, res)
                    
                    # Estrutura 3: Dict com calculos
                    elif isinstance(api_data, dict) and 'calculos' in api_data:
                        for calc in api_data.get('calculos', []):
                            nome_seg = (calc.get('nomeSeguradora') or calc.get('seguradoraTxt') or '').strip()
                            for res in calc.get('resultados', []):
                                _add_to_pdf_map(pdf_map, nome_seg, res)
                    
                except Exception as e:
                    logger.warning(f"Erro parsing interceptação: {e}")
        
        if pdf_map:
            logger.info(f"PDFs via interceptação: {list(pdf_map.keys())} ({len(pdf_map)} total)")
            for seg_k, seg_v in pdf_map.items():
                plans = seg_v.get('_all_plans', [seg_v])
                plans_str = " | ".join(f"{p.get('identificacao','?')}={p.get('premio','?')}" for p in plans)
                logger.info(f"  {seg_k}: {len(plans)} planos → {plans_str}")
        
        try:
            resultados_url = page.url
            # Extrai UUID da URL dos resultados
            uuid_match = re.search(r'resultados/([a-f0-9-]{36})', resultados_url)
            if uuid_match:
                cotacao_uuid = uuid_match.group(1)
                logger.info(f"UUID da cotação: {cotacao_uuid}")
                
                # Busca dados completos via API do multicálculo
                # Primeiro tenta via página (mesmo contexto de cookies do Agilizador)
                api_url = f"https://api.multicalculo.net/calculo/cotacao/versoes/{cotacao_uuid}"
                logger.info(f"Buscando PDFs na API: {api_url}")
                versoes_resp = await page.evaluate(f"""
                    async () => {{
                        try {{
                            const resp = await fetch('{api_url}', {{credentials: 'include', mode: 'cors'}});
                            const status = resp.status;
                            const text = await resp.text();
                            if (status !== 200) return 'HTTP_' + status + ':' + text.substring(0, 100);
                            return text;
                        }} catch(e) {{
                            return 'FETCH_ERROR:' + e.message;
                        }}
                    }}
                """)
                logger.info(f"API response: {str(versoes_resp)[:150] if versoes_resp else 'null'}")
                
                # Se falhou via page, tenta via request do Playwright (usa cookies do contexto)
                if not versoes_resp or versoes_resp.startswith('HTTP_') or versoes_resp.startswith('FETCH_ERROR'):
                    logger.info("Fetch via page falhou, tentando via page.context.request...")
                    try:
                        api_resp = await page.context.request.get(api_url)
                        if api_resp.ok:
                            versoes_resp = await api_resp.text()
                            logger.info(f"API via request OK: {len(versoes_resp)} chars")
                        else:
                            logger.warning(f"API via request falhou: {api_resp.status}")
                            versoes_resp = None
                    except Exception as e:
                        logger.warning(f"API via request erro: {e}")
                        versoes_resp = None
                
                # Se ambos falharam, tenta via httpx com token JWT capturado
                if not versoes_resp:
                    cached_token = _agg_token_cache.get('token')
                    if cached_token:
                        logger.info("Tentando via httpx com token JWT capturado...")
                        try:
                            import httpx as _hx
                            async with _hx.AsyncClient(timeout=30) as hclient:
                                api_resp2 = await hclient.get(
                                    api_url,
                                    headers={"Authorization": f"Bearer {cached_token}"}
                                )
                                if api_resp2.status_code == 200:
                                    versoes_resp = api_resp2.text
                                    logger.info(f"API via httpx+token OK: {len(versoes_resp)} chars")
                                else:
                                    logger.warning(f"API via httpx+token falhou: {api_resp2.status_code}")
                        except Exception as e:
                            logger.warning(f"httpx token API erro: {e}")
                    else:
                        logger.warning("Sem token JWT capturado — não consegue buscar PDFs via API")
                
                if versoes_resp:
                    import json as _json
                    
                    def _parse_pdfs(raw_text):
                        pm = {}
                        versoes = _json.loads(raw_text)
                        if isinstance(versoes, list) and versoes:
                            latest = versoes[-1]
                            for calc in latest.get('calculos', []):
                                nome_seg = (calc.get('nomeSeguradora') or calc.get('seguradoraTxt') or '').strip()
                                for res in calc.get('resultados', []):
                                    path_pdf = res.get('pathPdf', '')
                                    if path_pdf and nome_seg:
                                        key = nome_seg.lower()
                                        if key not in pm:
                                            pm[key] = {
                                                'pathPdf': path_pdf,
                                                'identificacao': res.get('identificacao', ''),
                                                'nomeSeguradora': nome_seg,
                                                'premio': res.get('premio'),
                                                'pdfFileName': res.get('pdfFileNameAgger', ''),
                                            }
                        return pm
                    
                    pdf_map = _parse_pdfs(versoes_resp)
                    logger.info(f"PDFs disponíveis (1ª tentativa): {list(pdf_map.keys())} ({len(pdf_map)} total)")
                    
                    # Se poucos PDFs, espera e tenta de novo (seguradoras podem estar gerando)
                    if len(pdf_map) < 5 and len(resultados) > 5:
                        logger.info("Poucos PDFs prontos, aguardando 15s pra mais seguradoras gerarem...")
                        await asyncio.sleep(15)
                        retry_resp = await page.evaluate(f"""
                            async () => {{
                                try {{
                                    const resp = await fetch('{api_url}', {{credentials: 'include'}});
                                    return await resp.text();
                                }} catch(e) {{ return null; }}
                            }}
                        """)
                        if retry_resp:
                            pdf_map = _parse_pdfs(retry_resp)
                            logger.info(f"PDFs disponíveis (2ª tentativa): {list(pdf_map.keys())} ({len(pdf_map)} total)")
        except Exception as e:
            logger.warning(f"Erro ao capturar dados da API multicálculo: {e}")
        
        # Salva resultados + URL + PDFs pra download depois
        if chat_id and resultados:
            _browser_sessions[chat_id] = {
                "resultados": resultados,
                "resultados_url": page.url,
                "pdf_map": pdf_map,
                "cotacao_uuid": cotacao_uuid if 'cotacao_uuid' in dir() else None,
            }
            logger.info(f"Resultados salvos para chat_id={chat_id} ({len(resultados)} resultados, {len(pdf_map)} PDFs) url={page.url}")
            _save_sessions_to_disk()

        return {
            "sucesso": True,
            "url": page.url,
            "msg": texto_resultado,
            "screenshot": screenshot,
            "resultados": resultados,
            "cotacao_uuid": cotacao_uuid if 'cotacao_uuid' in dir() else None,
        }

    except Exception as e:
        logger.error(f"Erro Agilizador: {e}", exc_info=True)
        screenshot = None
        try:
            await _fechar_modais(page)
            screenshot = await page.screenshot(type="jpeg", quality=70, full_page=True)
        except: pass
        return {
            "sucesso": False,
            "url": page.url,
            "msg": f"❌ Erro: {str(e)[:200]}",
            "screenshot": screenshot
        }
    finally:
        try:
            await browser.close()
        except: pass
        try:
            await pw.stop()
        except: pass



async def baixar_pdf_cotacao(chat_id: int, seguradora: str, on_progress=None, premio_esperado: float = None, resultado_tela: dict = None) -> dict:
    """
    Baixa o PDF original da seguradora via API do Agilizador (quotation-files).
    Depois converte pro layout Sierra usando o extractor pipeline.
    """
    import httpx as _httpx
    
    session = _browser_sessions.get(chat_id)
    if not session:
        return {"sucesso": False, "msg": "❌ Resultados não encontrados. Calcule novamente com /nova."}
    
    pdf_map = session.get("pdf_map", {})
    
    async def progress(msg):
        logger.info(msg)
        if on_progress:
            await on_progress(msg)

    # Busca a seguradora no pdf_map
    pdf_info = None
    seg_lower = seguradora.lower()
    for key, info in pdf_map.items():
        if seg_lower in key or key in seg_lower:
            # Se tem múltiplos planos, filtra por tipo e depois por prêmio
            all_plans = info.get('_all_plans', [info])
            if len(all_plans) > 1:
                # Palavras que indicam plano NÃO-compreensivo (excluir)
                _excl = ['roubo', 'furto', 'terceiro', 'assistência exclusiva', 'assistencia exclusiva']
                # Palavras que indicam plano compreensivo (priorizar)
                _prio = ['compreensiv', 'completo', 'compacto', 'tradicional', 'perfil', 'clássico', 'classico', 'sênior', 'senior', 'conforto']
                
                def _is_compreensivo(plan):
                    ident = (plan.get('identificacao') or plan.get('cobertura') or '').lower()
                    # Se contém exclusão explícita, não é compreensivo
                    for ex in _excl:
                        if ex in ident:
                            return False
                    # Se contém prioridade, é compreensivo
                    for pr in _prio:
                        if pr in ident:
                            return True
                    # Sem identificação clara, assume compreensivo
                    return True
                
                # Filtra planos compreensivos primeiro
                compr_plans = [p for p in all_plans if _is_compreensivo(p)]
                candidatos = compr_plans if compr_plans else all_plans
                
                logger.info(f"Planos {seg_lower}: {len(all_plans)} total, {len(compr_plans)} compreensivos, candidatos: {len(candidatos)}")
                for cp in candidatos:
                    logger.info(f"  Candidato: {cp.get('identificacao','?')} premio={cp.get('premio','?')}")
                
                if premio_esperado and len(candidatos) > 1:
                    # Entre compreensivos, busca prêmio mais próximo
                    melhor = None
                    menor_diff = float('inf')
                    for plan in candidatos:
                        try:
                            p = float(str(plan.get('premio', 0)).replace(',', '.'))
                            diff = abs(p - premio_esperado)
                            if diff < menor_diff:
                                menor_diff = diff
                                melhor = plan
                        except:
                            pass
                    if melhor:
                        pdf_info = melhor
                        logger.info(f"Selecionado plano compreensivo com prêmio {melhor.get('premio')} (esperado: {premio_esperado}, diff: {menor_diff:.2f})")
                    else:
                        pdf_info = candidatos[0]
                else:
                    pdf_info = candidatos[0]
                    logger.info(f"Selecionado plano: {pdf_info.get('identificacao','?')} premio={pdf_info.get('premio','?')}")
            else:
                pdf_info = info
            break
    
    if not pdf_info or not pdf_info.get('pathPdf'):
        # Fallback: abre browser, faz login no Agilizador, navega pra resultados e busca PDFs via API
        cotacao_uuid = session.get("cotacao_uuid")
        resultados_url = session.get("resultados_url", "")
        if not cotacao_uuid:
            uuid_match = re.search(r'resultados/([a-f0-9-]{36})', resultados_url)
            cotacao_uuid = uuid_match.group(1) if uuid_match else None
        
        if cotacao_uuid:
            await progress(f"🔍 Buscando PDFs na API (fallback)...")
            try:
                from playwright.async_api import async_playwright as _apw
                pw = await _apw().start()
                br = await pw.chromium.launch(headless=True)
                pg = await br.new_page()
                await _login(pg)
                
                # Navega pra resultados pra ter contexto de cookies correto
                await pg.goto(resultados_url or f"https://aggilizador.com.br/cotacao/auto/resultados/{cotacao_uuid}", 
                             wait_until="networkidle", timeout=30000)
                await asyncio.sleep(3)
                
                api_url = f"https://api.multicalculo.net/calculo/cotacao/versoes/{cotacao_uuid}"
                versoes_resp = await pg.evaluate(f"""
                    async () => {{
                        try {{
                            const resp = await fetch('{api_url}', {{credentials: 'include'}});
                            if (resp.status !== 200) return null;
                            return await resp.text();
                        }} catch(e) {{ return null; }}
                    }}
                """)
                
                await br.close()
                await pw.stop()
                
                if versoes_resp:
                    import json as _json
                    versoes = _json.loads(versoes_resp)
                    if isinstance(versoes, list) and versoes:
                        latest = versoes[-1]
                        for calc in latest.get('calculos', []):
                            nome_seg = (calc.get('nomeSeguradora') or calc.get('seguradoraTxt') or '').strip()
                            for res in calc.get('resultados', []):
                                path_pdf = res.get('pathPdf', '')
                                if path_pdf and nome_seg:
                                    key = nome_seg.lower()
                                    if key not in pdf_map:
                                        pdf_map[key] = {
                                            'pathPdf': path_pdf,
                                            'identificacao': res.get('identificacao', ''),
                                            'nomeSeguradora': nome_seg,
                                            'premio': res.get('premio'),
                                            'pdfFileName': res.get('pdfFileNameAgger', ''),
                                        }
                        session['pdf_map'] = pdf_map
                        logger.info(f"PDF map atualizado via fallback: {list(pdf_map.keys())}")
                        _save_sessions_to_disk()
                        for key, info in pdf_map.items():
                            if seg_lower in key or key in seg_lower:
                                pdf_info = info
                                break
            except Exception as e:
                logger.warning(f"Fallback browser API falhou: {e}")
        
        if not pdf_info or not pdf_info.get('pathPdf'):
            return {"sucesso": False, "msg": f"❌ PDF da {seguradora} não disponível. Nem todas as seguradoras geram PDF no Agilizador."}
    
    pdf_url = pdf_info['pathPdf']
    await progress(f"📥 Baixando PDF da {seguradora}...")
    
    os.makedirs("/root/sierra/downloads", exist_ok=True)
    
    try:
        async with _httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(pdf_url)
        
        if resp.status_code != 200:
            return {"sucesso": False, "msg": f"❌ Erro ao baixar PDF: HTTP {resp.status_code}"}
        
        pdf_bytes = resp.content
        if not pdf_bytes or pdf_bytes[:5] != b'%PDF-':
            return {"sucesso": False, "msg": f"❌ Arquivo baixado não é um PDF válido."}
        
        # Salva PDF original
        seg_clean = seguradora.replace(' ', '_').replace('/', '_')
        original_path = f"/root/sierra/downloads/{seg_clean}_{chat_id}_original.pdf"
        with open(original_path, "wb") as f:
            f.write(pdf_bytes)
        
        await progress(f"✅ PDF original baixado ({len(pdf_bytes)//1024} KB). Convertendo pro layout Sierra...")
        
        # Converte pro layout Sierra usando o pipeline de extração
        from extractors import ExtractorFactory
        from generator_sierra_v7_alt import SierraPDFGeneratorV7
        
        extractor = ExtractorFactory.get_extractor(original_path)
        ai_used = False
        if not extractor:
            from ai_extractor import AIExtractor
            extractor = AIExtractor(original_path)
            ai_used = True
        
        data = extractor.extract()
        
        # Gera nome de saída
        segurado_raw = str(data.get("segurado") or "Cliente").upper()
        parts = segurado_raw.split()
        name_str = f"{parts[0]}.{parts[-1]}" if len(parts) >= 2 else parts[0] if parts else "Cliente"
        insurer_code = str(data.get("insurer", "UNK"))[:3].upper()
        from datetime import datetime as _dt
        now_str = _dt.now().strftime("%d.%m.%y_%H.%M.%S")
        out_name = f"Orcamento.{name_str}.{insurer_code}.{now_str}.pdf"
        
        sierra_path = f"/root/sierra/downloads/{out_name}"
        gen = SierraPDFGeneratorV7(data, sierra_path)
        gen.generate()
        
        file_size = os.path.getsize(sierra_path)
        await progress(f"✅ PDF Sierra gerado! ({file_size//1024} KB)")
        
        return {
            "sucesso": True,
            "pdf_path": sierra_path,
            "original_path": original_path,
            "out_name": out_name,
            "data": data,
            "ai_used": ai_used,
            "msg": f"✅ PDF da {seguradora} convertido! ({file_size//1024} KB)"
        }

    except Exception as e:
        logger.error(f"Erro ao baixar/converter PDF {seguradora}: {e}", exc_info=True)
        return {"sucesso": False, "msg": f"❌ Erro: {str(e)[:200]}"}
