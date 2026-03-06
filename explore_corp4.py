"""Corp - tentativa com sierra@seg0418 no primeiro login."""
import asyncio
import os
from playwright.async_api import async_playwright

SCREENSHOTS = "/root/sierra/screenshots"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        
        await page.goto("https://corpnuvem-14.ddns.net/")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        
        # Tentar com sierra@seg0418 como senha
        await page.fill('#Editbox1', 'sierra')
        await page.fill('#Editbox2', 'sierra@seg0418')
        await page.click('#buttonLogOn')
        await asyncio.sleep(5)
        
        await page.screenshot(path=f"{SCREENSHOTS}/corp4_01.png")
        print(f"URL: {page.url}")
        
        # Tentar clicar para acessar
        try:
            await page.click('text=Clique para acessar', timeout=5000)
            await asyncio.sleep(8)
        except:
            pass
        
        await page.screenshot(path=f"{SCREENSHOTS}/corp4_02.png")
        print(f"URL after click: {page.url}")
        
        # Check content
        content = await page.content()
        if "Invalid" in content:
            print("Still Invalid Credentials")
        else:
            print("No Invalid message - might have worked!")
            
        # Check for iframes or new windows
        pages = browser.contexts[0].pages
        print(f"Pages open: {len(pages)}")
        for i, pg in enumerate(pages):
            print(f"  Page {i}: {pg.url}")
        
        # List visible elements
        els = await page.query_selector_all("div.applications, img, a")
        for el in els[:15]:
            text = ""
            try:
                text = (await el.inner_text()).strip()[:60]
            except:
                pass
            src = await el.get_attribute("src") or ""
            print(f"  el: text='{text}' src='{src[:50]}'")
        
        await browser.close()

asyncio.run(main())
