"""Corp - acesso via HTML5 (sem plugin Citrix)."""
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
        
        # Select HTML5 access type
        try:
            await page.click('#accesstypeuserchoice_html5')
            print("Selected HTML5 access")
        except:
            print("HTML5 radio not found")
        
        await page.fill('#Editbox1', 'sierra')
        await page.fill('#Editbox2', 'sierr@seg0418')
        await page.click('#buttonLogOn')
        await asyncio.sleep(5)
        
        await page.screenshot(path=f"{SCREENSHOTS}/corp_html5_01.png")
        print(f"URL: {page.url}")
        
        # Click to access
        try:
            # Find and click the app icon/link
            app_link = await page.query_selector('a:has-text("Clique"), div.applications a, img[src*="Corp"]')
            if app_link:
                await app_link.click()
                print("Clicked app link")
            else:
                await page.click('text=Clique para acessar')
                print("Clicked text")
        except Exception as e:
            print(f"Click error: {e}")
        
        await asyncio.sleep(10)
        await page.screenshot(path=f"{SCREENSHOTS}/corp_html5_02.png")
        print(f"URL after: {page.url}")
        
        # Check all pages/popups
        pages = browser.contexts[0].pages
        print(f"Pages: {len(pages)}")
        for i, pg in enumerate(pages):
            print(f"  Page {i}: {pg.url}")
            await pg.screenshot(path=f"{SCREENSHOTS}/corp_html5_page{i}.png")
        
        # Check frames
        for i, frame in enumerate(page.frames):
            print(f"Frame {i}: {frame.url}")
        
        # Check for canvas (HTML5 Citrix uses canvas)
        canvas = await page.query_selector_all("canvas")
        print(f"Canvas elements: {len(canvas)}")
        
        # Check for iframes
        iframes = await page.query_selector_all("iframe")
        print(f"Iframes: {len(iframes)}")
        for iframe in iframes:
            src = await iframe.get_attribute("src") or ""
            print(f"  iframe src: {src[:100]}")
        
        await asyncio.sleep(5)
        await page.screenshot(path=f"{SCREENSHOTS}/corp_html5_03.png")
        
        await browser.close()
        print("\nDone!")

asyncio.run(main())
