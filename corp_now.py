"""
Corp — Replica EXATAMENTE o método que funcionou na 1a vez.
keyboard.type() em vez de keyboard.press() individual.
"""

from playwright.sync_api import sync_playwright
import time
import os

DIR = "/root/sierra/corp_now"
os.makedirs(DIR, exist_ok=True)

def ss(page, name):
    path = f"{DIR}/{name}.jpg"
    page.screenshot(path=path, quality=90, type="jpeg")
    print(f"📸 {name}")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1280, 'height': 900})
        
        page = ctx.new_page()
        page.goto('https://corpnuvem-14.ddns.net/software/html5.html', timeout=30000, wait_until='networkidle')
        page.fill('#Editbox1', 'sierra')
        page.fill('#Editbox2', 'sierr@seg0418')
        page.click('#buttonLogOn')
        print("✅ Login portal")
        time.sleep(12)
        
        with ctx.expect_page(timeout=20000) as npi:
            page.click('text=Sierra')
        rdp = npi.value
        print("✅ Aba RDP")
        time.sleep(35)
        ss(rdp, "00_rdp")
        
        # EXATAMENTE como na primeira vez que funcionou:
        # Click no campo usuario (700, 400)
        rdp.mouse.click(700, 400)
        time.sleep(0.5)
        rdp.keyboard.press('Control+a')
        rdp.keyboard.type('AMANDA', delay=50)
        time.sleep(1)
        
        # Click DIRETO no campo senha em vez de Tab
        # Baseado no screenshot: senha está ~30px abaixo do usuario
        rdp.mouse.click(700, 460)
        time.sleep(0.5)
        rdp.keyboard.press('Control+a')
        rdp.keyboard.type('amanda001', delay=50)
        time.sleep(0.5)
        ss(rdp, "01_preenchido")
        
        rdp.keyboard.press('Enter')
        print("✅ Login enviado (método original + click direto)")
        time.sleep(25)
        ss(rdp, "02_resultado")
        
        # Testa se logou
        rdp.keyboard.press('Alt+a')
        time.sleep(2)
        ss(rdp, "03_teste_menu")
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        # === FERRAMENTAS > EXPORTAÇÃO ===
        print("\n=== Ferramentas > Exportação de Dados ===")
        rdp.keyboard.press('Alt+f')
        time.sleep(2)
        ss(rdp, "10_ferramentas")
        
        for i in range(8):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        ss(rdp, "11_exportacao_hover")
        rdp.keyboard.press('ArrowRight')
        time.sleep(2)
        ss(rdp, "12_exportacao_submenu")
        
        # Cada item do submenu
        for i in range(6):
            ss(rdp, f"13_sub_{i}")
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.5)
        
        # Volta ao topo e abre primeiro item
        for i in range(6):
            rdp.keyboard.press('ArrowUp')
            time.sleep(0.2)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "14_export1")
        time.sleep(3)
        ss(rdp, "15_export1b")
        
        # Fecha e segundo item
        rdp.keyboard.press('Escape')
        time.sleep(1)
        rdp.keyboard.press('Alt+f')
        time.sleep(1.5)
        for i in range(8):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.2)
        rdp.keyboard.press('ArrowRight')
        time.sleep(1)
        rdp.keyboard.press('ArrowDown')
        time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "16_export2")
        
        # Terceiro item
        rdp.keyboard.press('Escape')
        time.sleep(1)
        rdp.keyboard.press('Alt+f')
        time.sleep(1.5)
        for i in range(8):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.2)
        rdp.keyboard.press('ArrowRight')
        time.sleep(1)
        rdp.keyboard.press('ArrowDown')
        time.sleep(0.2)
        rdp.keyboard.press('ArrowDown')
        time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "17_export3")
        
        # === CONSULTAS > GERENCIADOR ===
        print("\n=== Gerenciador de Relatórios ===")
        rdp.keyboard.press('Escape')
        time.sleep(1)
        rdp.keyboard.press('Alt+c')
        time.sleep(2)
        for i in range(4):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "20_gerenciador")
        
        # === CONSULTAS > GRÁFICOS ===
        rdp.keyboard.press('Escape')
        time.sleep(1)
        rdp.keyboard.press('Alt+c')
        time.sleep(2)
        for i in range(5):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "21_graficos")
        
        # === MOVIMENTOS > ACOMP RENOVAÇÕES ===
        print("\n=== Acomp. Renovações ===")
        rdp.keyboard.press('Escape')
        time.sleep(1)
        rdp.keyboard.press('Alt+m')
        time.sleep(2)
        for i in range(3):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "30_renovacoes")
        
        print("\n✅ Concluído!")
        browser.close()

if __name__ == "__main__":
    main()
