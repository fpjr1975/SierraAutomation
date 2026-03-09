"""
Explorador Corp v2 — foco em abrir menus dropdown e mapear funcionalidades.
"""

from playwright.sync_api import sync_playwright
import time
import os

DIR = "/root/sierra/corp_screenshots2"
os.makedirs(DIR, exist_ok=True)

def ss(page, name):
    path = f"{DIR}/{name}.jpg"
    page.screenshot(path=path, quality=90, type="jpeg")
    print(f"📸 {name}")

def login_corp(ctx):
    page = ctx.new_page()
    page.goto('https://corpnuvem-14.ddns.net/software/html5.html', timeout=30000, wait_until='networkidle')
    page.fill('#Editbox1', 'sierra')
    page.fill('#Editbox2', 'sierr@seg0418')
    page.click('#buttonLogOn')
    print("✅ Login portal")
    time.sleep(8)
    
    with ctx.expect_page(timeout=20000) as npi:
        page.click('text=Sierra')
    rdp = npi.value
    print("✅ Aba RDP")
    time.sleep(20)
    
    rdp.mouse.click(700, 400)
    time.sleep(0.5)
    rdp.keyboard.press('Control+a')
    rdp.keyboard.type('AMANDA', delay=50)
    rdp.keyboard.press('Tab')
    time.sleep(0.3)
    rdp.keyboard.type('amanda001', delay=50)
    rdp.keyboard.press('Enter')
    print("✅ Login Corp")
    time.sleep(15)
    return rdp

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1280, 'height': 900})
        rdp = login_corp(ctx)
        ss(rdp, "00_home")
        
        # Fechar qualquer janela aberta primeiro
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        # Primeiro, vamos mapear os menus
        # Preciso clicar EXATAMENTE no texto do menu
        # Baseado no screenshot da home, a barra de menu fica no topo
        # Vou tentar diferentes posições Y (a barra pode ser mais alta)
        
        # === MENU ARQUIVOS ===
        print("\n=== ARQUIVOS ===")
        rdp.mouse.click(35, 8)  # Tenta y=8 (topo do menu)
        time.sleep(2)
        ss(rdp, "01_arquivos_y8")
        rdp.keyboard.press('Escape')
        time.sleep(0.5)
        
        rdp.mouse.click(35, 15)
        time.sleep(2)
        ss(rdp, "02_arquivos_y15")
        rdp.keyboard.press('Escape')
        time.sleep(0.5)
        
        # Tenta com Alt+A (atalho de menu)
        rdp.keyboard.press('Alt+a')
        time.sleep(2)
        ss(rdp, "03_arquivos_alt")
        rdp.keyboard.press('Escape')
        time.sleep(0.5)
        
        # === TENTA ABRIR PELO TECLADO ===
        # Talvez F10 ative a barra de menu
        print("\n=== F10 / Alt ===")
        rdp.keyboard.press('F10')
        time.sleep(2)
        ss(rdp, "04_f10")
        rdp.keyboard.press('Escape')
        time.sleep(0.5)
        
        rdp.keyboard.press('Alt')
        time.sleep(1)
        rdp.keyboard.press('ArrowRight')
        time.sleep(1)
        ss(rdp, "05_alt_right")
        rdp.keyboard.press('Escape')
        time.sleep(0.5)
        
        # === ÍCONES DA TOOLBAR ===
        # Vou clicar em cada ícone da toolbar e ver o que abre
        print("\n=== TOOLBAR ÍCONES ===")
        
        # Baseado na análise: ícones ficam na segunda linha
        # Vamos tentar y ~55-65 pra toolbar
        icons = [
            ("icon_01", 18, 55),   # Primeiro ícone (pessoas?)
            ("icon_02", 50, 55),   # Segundo
            ("icon_03", 80, 55),   # Terceiro (calendário 31?)
            ("icon_04", 110, 55),  # Quarto
            ("icon_05", 140, 55),  # Quinto
            ("icon_06", 170, 55),  # Sexto (casa)
            ("icon_07", 200, 55),  # Sétimo
            ("icon_08", 340, 55),  # Busca?
            ("icon_09", 560, 55),  # $$
            ("icon_10", 610, 55),  # Lupa
            ("icon_11", 660, 55),  # Gráfico
        ]
        
        for name, x, y in icons:
            rdp.mouse.click(x, y)
            time.sleep(3)
            ss(rdp, name)
            rdp.keyboard.press('Escape')
            time.sleep(1)
        
        # === BARRA DE BUSCA ===
        # Há uma barra de busca na toolbar
        print("\n=== BARRA BUSCA ===")
        # Tenta clicar na barra de busca e digitar um nome
        rdp.mouse.click(350, 55)  # Campo de busca estimado
        time.sleep(1)
        rdp.keyboard.type('CAPELETTI', delay=50)
        time.sleep(1)
        # Clica no botão de busca ao lado
        rdp.mouse.click(430, 55)
        time.sleep(3)
        ss(rdp, "30_busca_capeletti")
        
        # Enter pra buscar
        rdp.keyboard.press('Enter')
        time.sleep(3)
        ss(rdp, "31_busca_resultado")
        
        # Fechar
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        print("\n✅ Exploração v2 concluída!")
        browser.close()

if __name__ == "__main__":
    main()
