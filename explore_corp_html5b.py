"""Corp - forçar HTML5 mode."""
import asyncio
import os
from playwright.async_api import async_playwright

SCREENSHOTS = "/root/sierra/screenshots"

async def main():
    async with async_playwright() as p:
        # Use full chromium instead of headless shell
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu"]
        )
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        
        await page.goto("https://corpnuvem-14.ddns.net/")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        
        # Check all radio buttons
        radios = await page.query_selector_all("input[type='radio']")
        print(f"Found {len(radios)} radio buttons")
        for r in radios:
            rid = await r.get_attribute("id") or ""
            rval = await r.get_attribute("value") or ""
            checked = await r.is_checked()
            print(f"  radio: id={rid} value={rval} checked={checked}")
        
        # Try to check HTML5 via JS
        await page.evaluate("""
            var html5 = document.getElementById('accesstypeuserchoice_html5');
            if (html5) { html5.checked = true; html5.click(); }
        """)
        await asyncio.sleep(1)
        
        # Verify
        radios = await page.query_selector_all("input[type='radio']")
        for r in radios:
            rid = await r.get_attribute("id") or ""
            checked = await r.is_checked()
            print(f"  after: id={rid} checked={checked}")
        
        # Login
        await page.fill('#Editbox1', 'sierra')
        await page.fill('#Editbox2', 'sierr@seg0418')
        await page.click('#buttonLogOn')
        await asyncio.sleep(5)
        
        await page.screenshot(path=f"{SCREENSHOTS}/corp_h5b_01.png")
        print(f"URL: {page.url}")
        
        # Click app
        try:
            await page.click('text=Clique para acessar', timeout=5000)
            await asyncio.sleep(15)
        except Exception as e:
            print(f"Click error: {e}")
        
        await page.screenshot(path=f"{SCREENSHOTS}/corp_h5b_02.png")
        
        # Check for canvas/iframes/new content
        canvas = await page.query_selector_all("canvas")
        iframes = await page.query_selector_all("iframe")
        print(f"Canvas: {len(canvas)}, Iframes: {len(iframes)}")
        
        pages = browser.contexts[0].pages
        print(f"Pages: {len(pages)}")
        for i, pg in enumerate(pages):
            print(f"  Page {i}: {pg.url}")
            if i > 0:
                await pg.screenshot(path=f"{SCREENSHOTS}/corp_h5b_page{i}.png")
        
        # Check frames
        for i, frame in enumerate(page.frames):
            print(f"Frame {i}: {frame.url[:100]}")
            if i > 0:
                canvas_f = await frame.query_selector_all("canvas")
                print(f"  canvas in frame: {len(canvas_f)}")
        
        await browser.close()
        print("\nDone!")

asyncio.run(main())
