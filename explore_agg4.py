"""Explora o Agilizador - login completo."""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        
        await page.goto("https://aggilizador.com.br/login")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)
        
        # Fill login
        await page.fill('input[formcontrolname="email"]', 'contato@sierraseguros.com.br')
        await page.fill('input[formcontrolname="senha"]', 'Tronca2660&&')
        await asyncio.sleep(1)
        await page.click('button:has-text("Entrar")')
        await asyncio.sleep(5)
        
        # Click "Prosseguir" on session modal
        try:
            await page.click('button:has-text("Prosseguir")', timeout=5000)
            print("Clicked Prosseguir")
            await asyncio.sleep(8)
        except:
            print("No Prosseguir button found")
        
        await page.screenshot(path="/root/sierra/screenshots/agg_dashboard.png")
        print(f"URL: {page.url}")
        
        # Navigate and screenshot
        await asyncio.sleep(3)
        await page.screenshot(path="/root/sierra/screenshots/agg_main.png", full_page=True)
        
        # Find menu items
        links = await page.query_selector_all("a, [routerlink], mat-list-item, .menu-item, .nav-item, .sidebar a")
        for link in links[:40]:
            text = (await link.inner_text()).strip()
            href = await link.get_attribute("href") or await link.get_attribute("routerlink") or ""
            if text and len(text) < 60:
                print(f"  menu: '{text}' -> {href}")
        
        await browser.close()

import os
os.makedirs("/root/sierra/screenshots", exist_ok=True)
asyncio.run(main())
