"""Explora o Agilizador - login com seletores corretos."""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        
        await page.goto("https://aggilizador.com.br/login")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)
        
        # Fill using formcontrolname
        await page.fill('input[formcontrolname="email"]', 'contato@sierraseguros.com.br')
        await page.fill('input[formcontrolname="senha"]', 'Tronca2660&&')
        await asyncio.sleep(1)
        
        # Click Entrar
        await page.click('button:has-text("Entrar")')
        await asyncio.sleep(8)
        
        await page.screenshot(path="/root/sierra/screenshots/agg_loggedin.png")
        print(f"URL: {page.url}")
        print(f"Title: {await page.title()}")
        
        # Get main content
        content = await page.content()
        # Save HTML for analysis
        with open("/root/sierra/screenshots/agg_home.html", "w") as f:
            f.write(content)
        print("HTML saved")
        
        # Try to find navigation/menu items
        links = await page.query_selector_all("a, button, mat-list-item, [routerlink]")
        for link in links[:30]:
            text = (await link.inner_text()).strip()
            href = await link.get_attribute("href") or await link.get_attribute("routerlink") or ""
            if text:
                print(f"  link: '{text[:50]}' -> {href}")
        
        await browser.close()

import os
os.makedirs("/root/sierra/screenshots", exist_ok=True)
asyncio.run(main())
