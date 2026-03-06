"""Explora portais de seguradoras."""
import asyncio
import os
from playwright.async_api import async_playwright

SCREENSHOTS = "/root/sierra/screenshots"
os.makedirs(SCREENSHOTS, exist_ok=True)

PORTAIS = {
    "porto": {
        "url": "https://www.portoseguro.com.br/corretor",
        "user": "00057031070",
        "pass": "Logica2525@@"
    },
    "hdi": {
        "url": "https://www.hdi.com.br/corretor",
        "user": "00057031070",
        "pass": "Logica@2525"
    },
    "tokio": {
        "url": "https://www.tokiomarine.com.br/corretor",
        "user": "00057031070",
        "pass": "Sierra@25."
    }
}

async def explore_portal(p, name, config):
    print(f"\n{'='*50}")
    print(f"Explorando: {name.upper()}")
    print(f"{'='*50}")
    
    try:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        
        await page.goto(config["url"], timeout=30000)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        
        await page.screenshot(path=f"{SCREENSHOTS}/portal_{name}_01.png")
        print(f"URL: {page.url}")
        
        # List all visible inputs
        inputs = await page.query_selector_all("input:visible")
        for inp in inputs:
            itype = await inp.get_attribute("type") or "text"
            iname = await inp.get_attribute("name") or ""
            iid = await inp.get_attribute("id") or ""
            iph = await inp.get_attribute("placeholder") or ""
            print(f"  input: type={itype} name={iname} id={iid} ph={iph}")
        
        # List buttons
        buttons = await page.query_selector_all("button:visible, input[type='submit']:visible")
        for btn in buttons:
            text = ""
            try:
                text = (await btn.inner_text()).strip()
            except:
                text = await btn.get_attribute("value") or ""
            print(f"  button: '{text[:50]}'")
        
        # List main links
        links = await page.query_selector_all("a:visible")
        for link in links[:15]:
            text = (await link.inner_text()).strip()
            href = await link.get_attribute("href") or ""
            if text and len(text) < 50:
                print(f"  link: '{text}' -> {href[:80]}")
        
        await browser.close()
        
    except Exception as e:
        print(f"Error: {e}")
        try:
            await browser.close()
        except:
            pass

async def main():
    async with async_playwright() as p:
        for name, config in PORTAIS.items():
            await explore_portal(p, name, config)
    
    print("\n\nPortais exploration done!")

asyncio.run(main())
