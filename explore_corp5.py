"""Corp - senha sierr@seg0418 (sem o a)."""
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
        
        await page.fill('#Editbox1', 'sierra')
        await page.fill('#Editbox2', 'sierr@seg0418')
        await page.click('#buttonLogOn')
        await asyncio.sleep(5)
        
        await page.screenshot(path=f"{SCREENSHOTS}/corp5_01.png")
        print(f"URL: {page.url}")
        
        # Check if login failed
        content = await page.content()
        if "Login Inválido" in content or "Invalid" in content.lower():
            print("Login failed at step 1")
            await browser.close()
            return
        
        # Try to click to access
        try:
            await page.click('text=Clique para acessar', timeout=5000)
            await asyncio.sleep(8)
        except:
            pass
        
        await page.screenshot(path=f"{SCREENSHOTS}/corp5_02.png")
        print(f"URL after click: {page.url}")
        
        content = await page.content()
        if "Invalid" in content:
            print("Still Invalid Credentials after click")
        else:
            print("SUCCESS - No Invalid message!")
        
        pages = browser.contexts[0].pages
        print(f"Pages open: {len(pages)}")
        for i, pg in enumerate(pages):
            print(f"  Page {i}: {pg.url}")
            
        # Check elements
        els = await page.query_selector_all("*")
        for el in els[:30]:
            text = ""
            try:
                text = (await el.inner_text()).strip()
            except:
                pass
            if text and len(text) < 80 and text not in ["", "\n"]:
                tag = await el.evaluate("el => el.tagName")
                print(f"  {tag}: '{text}'")
        
        await browser.close()

asyncio.run(main())
