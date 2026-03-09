"""
Explorador Corp v3 — login corrigido + exploração de menus.
"""

from playwright.sync_api import sync_playwright
import time
import os

DIR = "/root/sierra/corp_screenshots3"
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
    time.sleep(10)
    
    with ctx.expect_page(timeout=20000) as npi:
        page.click('text=Sierra')
    rdp = npi.value
    print("✅ Aba RDP")
    time.sleep(25)
    ss(rdp, "00_rdp_login")
    
    # O login Corp tem campos no centro da tela
    # Da primeira vez funcionou com x=700, y=400 e Tab
    # Dessa vez, preciso mapear melhor os campos
    # Vamos clicar no campo de usuario e digitar
    
    # Campo Usuário - centro-direita da janela de login
    # Na primeira run bem-sucedida, cliquei em (700, 400) e funcionou
    # Vamos primeiro limpar o campo e digitar AMANDA
    rdp.mouse.click(730, 395)
    time.sleep(0.5)
    rdp.keyboard.press('Control+a')
    time.sleep(0.2)
    rdp.keyboard.type('AMANDA', delay=80)
    time.sleep(0.5)
    
    # Agora CLICAR diretamente no campo de senha (abaixo do usuario)
    rdp.mouse.click(730, 435)
    time.sleep(0.5)
    rdp.keyboard.press('Control+a')
    time.sleep(0.2)
    rdp.keyboard.type('amanda001', delay=80)
    time.sleep(0.5)
    
    ss(rdp, "01_login_preenchido")
    
    # Clicar no botão Entrar (abaixo dos campos)
    rdp.mouse.click(700, 480)
    time.sleep(2)
    
    # Se não clicou no botão, tenta Enter
    rdp.keyboard.press('Enter')
    print("✅ Tentando login Corp...")
    time.sleep(15)
    ss(rdp, "02_pos_login")
    
    return rdp

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1280, 'height': 900})
        rdp = login_corp(ctx)
        
        # Verifica se logou
        time.sleep(5)
        ss(rdp, "03_verificacao")
        
        # Tenta abrir menus clicando na barra de menu
        # Na home logada, a barra tem: Arquivos | Movimentos | Consultas | ...
        # Preciso achar a posição Y correta da barra de menus
        
        # Vamos tentar várias posições Y para a barra de menus
        print("\n=== Mapeando barra de menus ===")
        for y in [8, 12, 16, 20, 25]:
            rdp.mouse.click(35, y)
            time.sleep(1.5)
            ss(rdp, f"menu_y{y}")
            rdp.keyboard.press('Escape')
            time.sleep(0.5)
        
        # Tenta navegar pelo menu com Alt+letra ou F10
        print("\n=== ALT + teclas ===")
        
        # Alt+F10 ativa a barra de menus em muitos apps Windows
        rdp.keyboard.press('F10')
        time.sleep(1)
        ss(rdp, "10_f10")
        
        # Seta pra direita pra navegar
        rdp.keyboard.press('ArrowDown')
        time.sleep(1)
        ss(rdp, "11_f10_down")
        rdp.keyboard.press('Escape')
        time.sleep(0.5)
        
        # Tenta Alt sozinho
        rdp.keyboard.press('Alt')
        time.sleep(1)
        ss(rdp, "12_alt")
        rdp.keyboard.press('ArrowDown')
        time.sleep(1)
        ss(rdp, "13_alt_down")
        rdp.keyboard.press('Escape')
        time.sleep(0.5)
        
        # Tenta clicar nos ícones da toolbar (que a gente JÁ SABE que funcionam)
        # No primeiro round, clicar na toolbar abriu Cadastro de Clientes
        print("\n=== Toolbar ícones (posições refinadas) ===")
        
        # Na primeira execução bem-sucedida:
        # - icon pessoas (x=50, y=60) abriu Cadastro de Clientes
        # Vamos clicar na mesma posição
        
        # Primeiro verificamos se estamos na home
        ss(rdp, "20_antes_icones")
        
        # Ícone pessoas/cadastro (primeiro ícone grande da toolbar)
        for y in [48, 52, 56, 60, 65]:
            rdp.mouse.click(25, y)
            time.sleep(2)
            ss(rdp, f"icon_x25_y{y}")
            rdp.keyboard.press('Escape')
            time.sleep(1)
        
        # Tenta x=50
        rdp.mouse.click(50, 55)
        time.sleep(3)
        ss(rdp, "25_icon_x50_y55")
        
        # Se cadastro de clientes abriu, vamos explorar
        # Senão, tenta mais coordenadas
        rdp.mouse.click(90, 55)
        time.sleep(3)
        ss(rdp, "26_icon_x90_y55")
        
        rdp.mouse.click(130, 55)
        time.sleep(3)
        ss(rdp, "27_icon_x130_y55")
        
        rdp.mouse.click(160, 55)
        time.sleep(3)
        ss(rdp, "28_icon_x160_y55")
        
        print("\n✅ Exploração v3 concluída!")
        browser.close()

if __name__ == "__main__":
    main()
