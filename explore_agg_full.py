"""Explora o Agilizador a fundo — todas as telas."""
import asyncio
import os
from playwright.async_api import async_playwright

SCREENSHOTS = "/root/sierra/screenshots"
os.makedirs(SCREENSHOTS, exist_ok=True)

async def login(page):
    await page.goto("https://aggilizador.com.br/login")
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(2)
    await page.fill('input[formcontrolname="email"]', 'contato@sierraseguros.com.br')
    await page.fill('input[formcontrolname="senha"]', 'Tronca2660&&')
    await page.click('button:has-text("Entrar")')
    await asyncio.sleep(5)
    # Handle session modal
    try:
        await page.click('button:has-text("Prosseguir")', timeout=5000)
        await asyncio.sleep(5)
    except:
        pass
    # Close any popup/modal
    try:
        await page.click('button:has-text("X")', timeout=3000)
        await asyncio.sleep(1)
    except:
        pass
    try:
        close_btns = await page.query_selector_all('.close, .mat-dialog-close, [mat-dialog-close], .cdk-overlay-backdrop')
        for btn in close_btns:
            try:
                await btn.click()
                await asyncio.sleep(1)
            except:
                pass
    except:
        pass

async def screenshot_and_describe(page, name):
    await page.screenshot(path=f"{SCREENSHOTS}/{name}.png")
    title = await page.title()
    url = page.url
    print(f"\n=== {name} === URL: {url}")
    
    # Get visible text elements for context
    try:
        headings = await page.query_selector_all("h1, h2, h3, h4, .mat-card-title, .title, .header-title")
        for h in headings[:10]:
            text = (await h.inner_text()).strip()
            if text:
                print(f"  heading: {text[:80]}")
    except:
        pass

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        
        await login(page)
        await screenshot_and_describe(page, "01_cotacoes")
        
        # Close comunicados modal if present
        try:
            marcar = await page.query_selector('text=Marcar como visto')
            if marcar:
                await marcar.click()
                await asyncio.sleep(1)
            close = await page.query_selector('.mat-dialog-close, button.close, mat-icon:has-text("close")')
            if close:
                await close.click()
                await asyncio.sleep(1)
        except:
            pass
        
        await page.screenshot(path=f"{SCREENSHOTS}/01_cotacoes_clean.png")
        
        # Navigate to Dashboard
        try:
            await page.click('text=Dashboard', timeout=5000)
            await asyncio.sleep(3)
            await screenshot_and_describe(page, "02_dashboard")
        except Exception as e:
            print(f"Dashboard error: {e}")
        
        # Navigate to Tarefas
        try:
            await page.click('text=Tarefas', timeout=5000)
            await asyncio.sleep(3)
            await screenshot_and_describe(page, "03_tarefas")
        except Exception as e:
            print(f"Tarefas error: {e}")
        
        # Navigate to Configurações
        try:
            await page.click('text=Configurações', timeout=5000)
            await asyncio.sleep(2)
            await screenshot_and_describe(page, "04_configuracoes")
        except Exception as e:
            print(f"Config error: {e}")
        
        # Back to Cotações and open one
        try:
            await page.click('text=Cotações', timeout=5000)
            await asyncio.sleep(3)
            # Click on first cotação row
            rows = await page.query_selector_all('tr, mat-row, .row-item, [class*="cotacao"], [class*="item"]')
            print(f"  Found {len(rows)} rows")
            for row in rows[:5]:
                text = (await row.inner_text()).strip()[:100]
                print(f"  row: {text}")
            
            # Try clicking first cotação
            if rows:
                await rows[0].click()
                await asyncio.sleep(3)
                await screenshot_and_describe(page, "05_cotacao_detalhe")
        except Exception as e:
            print(f"Cotacao detail error: {e}")
        
        # Navigate to Nova Cotação
        try:
            await page.goto("https://aggilizador.com.br/cotacoes")
            await asyncio.sleep(3)
            await page.click('button:has-text("Nova Cotação")', timeout=5000)
            await asyncio.sleep(3)
            await screenshot_and_describe(page, "06_nova_cotacao")
        except Exception as e:
            print(f"Nova cotacao error: {e}")
        
        # Minhas Plataformas
        try:
            await page.goto("https://aggilizador.com.br/cotacoes")
            await asyncio.sleep(2)
            await page.click('text=Minhas plataformas', timeout=5000)
            await asyncio.sleep(3)
            await screenshot_and_describe(page, "07_plataformas")
        except Exception as e:
            print(f"Plataformas error: {e}")
        
        await browser.close()
        print("\n\nDone!")

asyncio.run(main())
