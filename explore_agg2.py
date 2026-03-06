"""Explora o Agilizador - debug login."""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        
        await page.goto("https://aggilizador.com.br/login")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)
        
        # Debug: list all inputs
        inputs = await page.query_selector_all("input")
        for inp in inputs:
            itype = await inp.get_attribute("type")
            iname = await inp.get_attribute("name")
            iph = await inp.get_attribute("placeholder")
            ifc = await inp.get_attribute("formcontrolname")
            print(f"  input: type={itype} name={iname} placeholder={iph} formcontrol={ifc}")
        
        # Debug: list all buttons
        buttons = await page.query_selector_all("button")
        for btn in buttons:
            text = await btn.inner_text()
            btype = await btn.get_attribute("type")
            print(f"  button: type={btype} text='{text.strip()}'")
        
        # Try filling with more specific selectors
        all_inputs = await page.query_selector_all("input")
        if len(all_inputs) >= 2:
            await all_inputs[0].fill("contato@sierraseguros.com.br")
            await all_inputs[1].fill("Tronca2660&&")
            await asyncio.sleep(1)
            await page.screenshot(path="/root/sierra/screenshots/agg_filled2.png")
            
            # Try clicking button
            btns = await page.query_selector_all("button")
            for btn in btns:
                text = await btn.inner_text()
                if "entrar" in text.lower() or "login" in text.lower() or "acessar" in text.lower():
                    await btn.click()
                    break
            
            await asyncio.sleep(5)
            await page.screenshot(path="/root/sierra/screenshots/agg_after_login.png")
            print(f"After login URL: {page.url}")
            
            # Get page content snippet
            title = await page.title()
            print(f"Title: {title}")
        
        await browser.close()

import os
os.makedirs("/root/sierra/screenshots", exist_ok=True)
asyncio.run(main())
