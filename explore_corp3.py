"""Explora o Corp - 3 etapas de login."""
import asyncio
import os
from playwright.async_api import async_playwright

SCREENSHOTS = "/root/sierra/screenshots"
os.makedirs(SCREENSHOTS, exist_ok=True)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        
        # Etapa 1 - Login Citrix
        print("=== ETAPA 1: Login Citrix ===")
        await page.goto("https://corpnuvem-14.ddns.net/")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        
        await page.fill('#Editbox1', 'sierra')
        await page.fill('#Editbox2', '#2025Sierra10#')
        await page.click('#buttonLogOn')
        await asyncio.sleep(5)
        
        await page.screenshot(path=f"{SCREENSHOTS}/corp3_01.png")
        print(f"URL: {page.url}")
        
        # Etapa 2 - Clique para acessar (vai abrir segunda tela de login)
        print("\n=== ETAPA 2: Clique para acessar ===")
        try:
            await page.click('text=Clique para acessar', timeout=5000)
            await asyncio.sleep(5)
        except:
            # Try any clickable element
            pass
        
        await page.screenshot(path=f"{SCREENSHOTS}/corp3_02.png")
        print(f"URL: {page.url}")
        
        # Check all frames (might be iframe)
        frames = page.frames
        print(f"Frames: {len(frames)}")
        for i, frame in enumerate(frames):
            print(f"  Frame {i}: {frame.url}")
            inputs = await frame.query_selector_all("input")
            if inputs:
                print(f"    Has {len(inputs)} inputs")
                for inp in inputs:
                    itype = await inp.get_attribute("type")
                    iid = await inp.get_attribute("id")
                    iname = await inp.get_attribute("name")
                    print(f"    input: type={itype} id={iid} name={iname}")
        
        # Try filling login on any frame that has inputs
        for frame in frames:
            inputs = await frame.query_selector_all("input")
            user_inputs = []
            pass_inputs = []
            for inp in inputs:
                itype = await inp.get_attribute("type")
                if itype == "password":
                    pass_inputs.append(inp)
                elif itype in ["text", None]:
                    try:
                        vis = await inp.is_visible()
                        if vis:
                            user_inputs.append(inp)
                    except:
                        pass
            
            if user_inputs and pass_inputs:
                print(f"\n=== ETAPA 2b: Login Corp (sierra/sierra@seg0418) ===")
                await user_inputs[0].fill("sierra")
                await pass_inputs[0].fill("sierra@seg0418")
                
                submit = await frame.query_selector("button, input[type='submit']")
                if submit:
                    await submit.click()
                else:
                    await pass_inputs[0].press("Enter")
                
                await asyncio.sleep(8)
                await page.screenshot(path=f"{SCREENSHOTS}/corp3_03.png")
                print(f"URL: {page.url}")
                
                # Check for another login (AMANDA)
                for frame2 in page.frames:
                    inputs2 = await frame2.query_selector_all("input")
                    user2 = []
                    pass2 = []
                    for inp in inputs2:
                        itype = await inp.get_attribute("type")
                        if itype == "password":
                            pass2.append(inp)
                        elif itype in ["text", None]:
                            try:
                                vis = await inp.is_visible()
                                if vis:
                                    user2.append(inp)
                            except:
                                pass
                    
                    if user2 and pass2:
                        print(f"\n=== ETAPA 3: Login Amanda ===")
                        await user2[0].fill("AMANDA")
                        await pass2[0].fill("amanda001")
                        
                        submit2 = await frame2.query_selector("button, input[type='submit']")
                        if submit2:
                            await submit2.click()
                        else:
                            await pass2[0].press("Enter")
                        
                        await asyncio.sleep(8)
                        await page.screenshot(path=f"{SCREENSHOTS}/corp3_04_inside.png")
                        print(f"Inside URL: {page.url}")
                        break
                break
        
        # Final state
        await page.screenshot(path=f"{SCREENSHOTS}/corp3_final.png")
        
        # Check for any app icons or content
        all_elements = await page.query_selector_all("img, [class*='app'], [class*='icon'], a")
        for el in all_elements[:20]:
            tag = await el.evaluate("el => el.tagName")
            text = ""
            try:
                text = (await el.inner_text()).strip()
            except:
                pass
            src = await el.get_attribute("src") or await el.get_attribute("href") or ""
            alt = await el.get_attribute("alt") or ""
            cls = await el.get_attribute("class") or ""
            if text or alt or src:
                print(f"  {tag}: text='{text[:40]}' alt='{alt[:40]}' src='{src[:60]}' class='{cls[:40]}'")
        
        await browser.close()
        print("\nDone!")

asyncio.run(main())
