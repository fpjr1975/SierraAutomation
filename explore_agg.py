"""Explora o Agilizador e tira screenshots."""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        
        # Login Agilizador
        await page.goto("https://aggilizador.com.br/login")
        await page.wait_for_load_state("networkidle")
        await page.screenshot(path="/root/sierra/screenshots/agg_login.png")
        print("Screenshot: agg_login.png")
        
        # Preenche login
        await page.fill('input[type="email"], input[formcontrolname="email"], input[name="email"]', 'contato@sierraseguros.com.br')
        await page.fill('input[type="password"], input[formcontrolname="password"], input[name="password"]', 'Tronca2660&&')
        await page.screenshot(path="/root/sierra/screenshots/agg_login_filled.png")
        print("Screenshot: agg_login_filled.png")
        
        # Clica em entrar
        await page.click('button[type="submit"], button:has-text("Entrar"), button:has-text("Login")')
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        await page.screenshot(path="/root/sierra/screenshots/agg_home.png")
        print(f"Screenshot: agg_home.png - URL: {page.url}")
        
        # Tenta navegar pra area de cotação
        await asyncio.sleep(2)
        await page.screenshot(path="/root/sierra/screenshots/agg_dashboard.png", full_page=True)
        print(f"Screenshot: agg_dashboard.png - URL: {page.url}")
        
        await browser.close()

import os
os.makedirs("/root/sierra/screenshots", exist_ok=True)
asyncio.run(main())
