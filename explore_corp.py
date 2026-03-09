"""
Explorador do Corp — mapeia menus e funcionalidades.
"""

from playwright.sync_api import sync_playwright
import time
import os

SCREENSHOTS_DIR = "/root/sierra/corp_screenshots"
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

def screenshot(page, name):
    path = f"{SCREENSHOTS_DIR}/{name}.jpg"
    page.screenshot(path=path, quality=90, type="jpeg")
    print(f"📸 {name}")
    return path

def login_corp(ctx):
    """Login no portal e abre o Corp."""
    page = ctx.new_page()
    page.goto('https://corpnuvem-14.ddns.net/software/html5.html', timeout=30000, wait_until='networkidle')
    
    page.fill('#Editbox1', 'sierra')
    page.fill('#Editbox2', 'sierr@seg0418')
    page.click('#buttonLogOn')
    print("✅ Login portal OK")
    time.sleep(8)
    
    with ctx.expect_page(timeout=20000) as new_page_info:
        page.click('text=Sierra')
    
    rdp = new_page_info.value
    print("✅ Aba RDP aberta")
    time.sleep(20)
    
    # Login Corp interno
    rdp.mouse.click(700, 400)
    time.sleep(0.5)
    rdp.keyboard.press('Control+a')
    rdp.keyboard.type('AMANDA', delay=50)
    rdp.keyboard.press('Tab')
    time.sleep(0.3)
    rdp.keyboard.type('amanda001', delay=50)
    rdp.keyboard.press('Enter')
    print("✅ Login Corp OK")
    time.sleep(15)
    
    return rdp

def explore_menu(rdp, menu_name, menu_x, menu_y):
    """Clica num menu e tira screenshot."""
    rdp.mouse.click(menu_x, menu_y)
    time.sleep(2)
    screenshot(rdp, f"menu_{menu_name}")
    return True

def close_menu(rdp):
    """Fecha menu com Escape."""
    rdp.keyboard.press('Escape')
    time.sleep(0.5)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1280, 'height': 900})
        
        rdp = login_corp(ctx)
        screenshot(rdp, "00_home")
        
        # Menu positions (estimativas - preciso ajustar)
        # Baseado no screenshot: Arquivos, Movimentos, Consultas, Ferramentas, Aplicativos, Sistema, Ajuda
        # Estão na barra de menu superior, espaçados horizontalmente
        
        menus = [
            ("01_arquivos", 35, 30),
            ("02_movimentos", 115, 30),
            ("03_consultas", 205, 30),
            ("04_ferramentas", 300, 30),
            ("05_aplicativos", 395, 30),
            ("06_sistema", 475, 30),
            ("07_ajuda", 530, 30),
        ]
        
        for name, x, y in menus:
            explore_menu(rdp, name, x, y)
            time.sleep(1)
            close_menu(rdp)
            time.sleep(0.5)
        
        # Agora explora submenus importantes
        # Primeiro: Consultas (onde devem estar clientes/apólices)
        print("\n--- Explorando CONSULTAS ---")
        rdp.mouse.click(205, 30)
        time.sleep(2)
        screenshot(rdp, "10_consultas_aberto")
        
        # Clica nos itens do submenu um por um
        # Primeiro preciso ver os itens do menu
        # Vou clicar em posições incrementais pra mapear cada item
        
        # Fecha consultas
        close_menu(rdp)
        
        # Explora Arquivos (cadastros)
        print("\n--- Explorando ARQUIVOS ---")
        rdp.mouse.click(35, 30)
        time.sleep(2)
        screenshot(rdp, "11_arquivos_aberto")
        close_menu(rdp)
        
        # Explora Movimentos
        print("\n--- Explorando MOVIMENTOS ---")  
        rdp.mouse.click(115, 30)
        time.sleep(2)
        screenshot(rdp, "12_movimentos_aberto")
        close_menu(rdp)
        
        # Explora Ferramentas
        print("\n--- Explorando FERRAMENTAS ---")
        rdp.mouse.click(300, 30)
        time.sleep(2)
        screenshot(rdp, "13_ferramentas_aberto")
        close_menu(rdp)
        
        # Explora Aplicativos
        print("\n--- Explorando APLICATIVOS ---")
        rdp.mouse.click(395, 30)
        time.sleep(2)
        screenshot(rdp, "14_aplicativos_aberto")
        close_menu(rdp)
        
        # Explora Sistema
        print("\n--- Explorando SISTEMA ---")
        rdp.mouse.click(475, 30)
        time.sleep(2)
        screenshot(rdp, "15_sistema_aberto")
        close_menu(rdp)
        
        # Agora tenta abrir a busca (ícone lupa na barra de ferramentas)
        print("\n--- Barra de Busca ---")
        # O ícone de busca fica na toolbar, aprox x=500, y=60
        rdp.mouse.click(500, 60)
        time.sleep(2)
        screenshot(rdp, "20_busca")
        close_menu(rdp)
        
        # Tenta o ícone de pessoas (cadastro de clientes?)
        print("\n--- Ícone Pessoas ---")
        rdp.mouse.click(50, 60)
        time.sleep(3)
        screenshot(rdp, "21_pessoas")
        
        time.sleep(2)
        screenshot(rdp, "22_pessoas_2")
        close_menu(rdp)
        
        print("\n✅ Exploração concluída!")
        print(f"Screenshots em: {SCREENSHOTS_DIR}/")
        
        browser.close()

if __name__ == "__main__":
    main()
