"""Explora o Corp (Infocap)."""
import asyncio
import os
from playwright.async_api import async_playwright

SCREENSHOTS = "/root/sierra/screenshots"
os.makedirs(SCREENSHOTS, exist_ok=True)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        
        # Corp login page 1
        await page.goto("https://corpnuvem-14.ddns.net/")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        await page.screenshot(path=f"{SCREENSHOTS}/corp_01_login1.png")
        print(f"Corp login1 URL: {page.url}")
        
        # List inputs
        inputs = await page.query_selector_all("input")
        for inp in inputs:
            itype = await inp.get_attribute("type")
            iname = await inp.get_attribute("name")
            iid = await inp.get_attribute("id")
            iph = await inp.get_attribute("placeholder")
            print(f"  input: type={itype} name={iname} id={iid} placeholder={iph}")
        
        # List buttons
        buttons = await page.query_selector_all("button, input[type='submit'], input[type='button'], a.btn")
        for btn in buttons:
            tag = await btn.evaluate("el => el.tagName")
            text = (await btn.inner_text()).strip() if tag != "INPUT" else await btn.get_attribute("value")
            print(f"  button: {tag} text='{text}'")
        
        # Try filling first login (sierra / #2025Sierra10#)
        try:
            user_inputs = [inp for inp in inputs if await inp.get_attribute("type") in ["text", "email", None]]
            pass_inputs = [inp for inp in inputs if await inp.get_attribute("type") == "password"]
            
            if user_inputs and pass_inputs:
                await user_inputs[0].fill("sierra")
                await pass_inputs[0].fill("#2025Sierra10#")
                await page.screenshot(path=f"{SCREENSHOTS}/corp_02_filled.png")
                
                # Try submitting
                submit = await page.query_selector("input[type='submit'], button[type='submit'], button:has-text('Entrar'), button:has-text('Login'), button:has-text('Acessar')")
                if submit:
                    await submit.click()
                else:
                    await pass_inputs[0].press("Enter")
                
                await asyncio.sleep(5)
                await page.screenshot(path=f"{SCREENSHOTS}/corp_03_after_login1.png")
                print(f"After login1 URL: {page.url}")
                
                # Check for second login page
                inputs2 = await page.query_selector_all("input")
                for inp in inputs2:
                    itype = await inp.get_attribute("type")
                    iname = await inp.get_attribute("name")
                    print(f"  input2: type={itype} name={iname}")
                
                user_inputs2 = [inp for inp in inputs2 if await inp.get_attribute("type") in ["text", "email", None]]
                pass_inputs2 = [inp for inp in inputs2 if await inp.get_attribute("type") == "password"]
                
                if user_inputs2 and pass_inputs2:
                    await user_inputs2[0].fill("AMANDA")
                    await pass_inputs2[0].fill("amanda001")
                    await page.screenshot(path=f"{SCREENSHOTS}/corp_04_login2_filled.png")
                    
                    submit2 = await page.query_selector("input[type='submit'], button[type='submit'], button:has-text('Entrar'), button:has-text('OK')")
                    if submit2:
                        await submit2.click()
                    else:
                        await pass_inputs2[0].press("Enter")
                    
                    await asyncio.sleep(5)
                    await page.screenshot(path=f"{SCREENSHOTS}/corp_05_inside.png")
                    print(f"Inside Corp URL: {page.url}")
        except Exception as e:
            print(f"Login error: {e}")
        
        await browser.close()
        print("\nCorp exploration done!")

asyncio.run(main())
