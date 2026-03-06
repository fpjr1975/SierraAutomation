"""Explora o Corp - segunda tentativa com credenciais corretas."""
import asyncio
import os
from playwright.async_api import async_playwright

SCREENSHOTS = "/root/sierra/screenshots"
os.makedirs(SCREENSHOTS, exist_ok=True)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        
        # Etapa 1
        await page.goto("https://corpnuvem-14.ddns.net/")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        
        await page.fill('#Editbox1', 'sierra')
        await page.fill('#Editbox2', '#2025Sierra10#')
        await page.click('#buttonLogOn')
        await asyncio.sleep(5)
        
        await page.screenshot(path=f"{SCREENSHOTS}/corp2_01_after_login1.png")
        print(f"After login1 URL: {page.url}")
        
        # Etapa 2 - "Clique para acessar"
        try:
            await page.click('text=Clique para acessar', timeout=5000)
            await asyncio.sleep(5)
        except:
            # Try clicking any link/button
            links = await page.query_selector_all("a, button")
            for link in links:
                text = (await link.inner_text()).strip()
                print(f"  found: '{text}'")
                if "acessar" in text.lower() or "clique" in text.lower():
                    await link.click()
                    await asyncio.sleep(5)
                    break
        
        await page.screenshot(path=f"{SCREENSHOTS}/corp2_02_login2.png")
        print(f"Login2 URL: {page.url}")
        
        # List inputs on this page
        inputs = await page.query_selector_all("input")
        for inp in inputs:
            itype = await inp.get_attribute("type")
            iname = await inp.get_attribute("name")
            iid = await inp.get_attribute("id")
            print(f"  input: type={itype} name={iname} id={iid}")
        
        # Fill login2 with new credentials
        user_inputs = []
        pass_inputs = []
        for inp in inputs:
            itype = await inp.get_attribute("type")
            if itype == "password":
                pass_inputs.append(inp)
            elif itype in ["text", "email", None]:
                vis = await inp.is_visible()
                if vis:
                    user_inputs.append(inp)
        
        if user_inputs and pass_inputs:
            await user_inputs[0].fill("sierra")
            await pass_inputs[0].fill("sierra@seg0418")
            await page.screenshot(path=f"{SCREENSHOTS}/corp2_03_filled.png")
            
            # Submit
            submit = await page.query_selector("input[type='submit'], button[type='submit'], button:has-text('Entrar'), button:has-text('OK'), button:has-text('Acessar')")
            if submit:
                await submit.click()
            else:
                await pass_inputs[0].press("Enter")
            
            await asyncio.sleep(8)
            await page.screenshot(path=f"{SCREENSHOTS}/corp2_04_inside.png")
            print(f"Inside URL: {page.url}")
            
            # Explore what's visible
            all_text = await page.query_selector_all("h1, h2, h3, a, button, .menu-item, [class*='menu']")
            for el in all_text[:30]:
                text = (await el.inner_text()).strip()
                if text and len(text) < 80:
                    print(f"  element: '{text}'")
        else:
            print("No login form found on page 2")
            # Maybe it's a remote app launcher
            content = await page.content()
            if "citrix" in content.lower() or "ica" in content.lower() or "remote" in content.lower():
                print("  -> Detected Citrix/Remote app")
        
        await browser.close()
        print("\nCorp exploration done!")

asyncio.run(main())
