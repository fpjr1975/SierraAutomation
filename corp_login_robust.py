"""
Corp — Login robusto com múltiplas tentativas de coordenadas.
Depois explora Ferramentas > Exportação de Dados e demais menus.
"""

from playwright.sync_api import sync_playwright
import time
import os

DIR = "/root/sierra/corp_robust"
os.makedirs(DIR, exist_ok=True)

def ss(page, name):
    path = f"{DIR}/{name}.jpg"
    page.screenshot(path=path, quality=90, type="jpeg")
    print(f"📸 {name}")

def try_login(rdp, user_x, user_y, pass_x, pass_y):
    """Tenta login com coordenadas específicas."""
    # Limpa e digita usuario
    rdp.mouse.click(user_x, user_y)
    time.sleep(0.8)
    rdp.keyboard.press('Control+a')
    time.sleep(0.3)
    rdp.keyboard.type('AMANDA', delay=100)
    time.sleep(0.8)
    
    # Limpa e digita senha (CLIQUE DIRETO)
    rdp.mouse.click(pass_x, pass_y)
    time.sleep(0.8)
    rdp.keyboard.press('Control+a')
    time.sleep(0.3)
    rdp.keyboard.type('amanda001', delay=100)
    time.sleep(0.5)

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
        time.sleep(10)
        
        with ctx.expect_page(timeout=20000) as npi:
            page.click('text=Sierra')
        rdp = npi.value
        print("✅ Aba RDP")
        
        # Espera MAIS tempo pro RDP carregar completamente
        time.sleep(30)
        ss(rdp, "00_rdp_loaded")
        
        # Tenta a abordagem ORIGINAL que funcionou na primeira vez:
        # (700, 400) + Tab
        print("Tentativa 1: coords originais (700,400) + Tab")
        rdp.mouse.click(700, 400)
        time.sleep(1)
        rdp.keyboard.press('Control+a')
        time.sleep(0.3)
        rdp.keyboard.type('AMANDA', delay=100)
        time.sleep(1)
        rdp.keyboard.press('Tab')
        time.sleep(1)
        rdp.keyboard.type('amanda001', delay=100)
        time.sleep(1)
        ss(rdp, "01_preenchido")
        
        rdp.keyboard.press('Enter')
        time.sleep(20)
        ss(rdp, "02_resultado")
        
        # Verifica se tem erro - se sim, fecha o dialog e tenta de novo
        # Se a tela mudou significativamente, login funcionou
        # Vamos tirar mais um screenshot pra comparar
        ss(rdp, "03_estado_final")
        
        # Se tiver dialog de erro, clica OK e tenta coords diferentes
        # OK button do dialog de erro fica ~no centro da tela
        # Vamos clicar no OK se estiver visível
        rdp.mouse.click(600, 457)  # Aprox posição do botão OK
        time.sleep(2)
        ss(rdp, "04_apos_ok")
        
        # Se o login falhou, vamos fechar e tentar novamente com:
        # Wait mais longo + delays maiores entre ações
        print("\nTentativa 2: delays maiores")
        rdp.mouse.click(700, 400)
        time.sleep(2)
        # Triple click pra selecionar tudo no campo
        rdp.mouse.click(700, 400, click_count=3)
        time.sleep(0.5)
        rdp.keyboard.type('AMANDA', delay=150)
        time.sleep(2)
        
        # Tab com delay grande
        rdp.keyboard.press('Tab')
        time.sleep(2)
        
        rdp.keyboard.type('amanda001', delay=150)
        time.sleep(1)
        ss(rdp, "05_tentativa2_preenchido")
        
        rdp.keyboard.press('Enter')
        time.sleep(20)
        ss(rdp, "06_tentativa2_resultado")
        
        # Se ainda falhou, tenta com coordenadas diferentes
        rdp.mouse.click(600, 457)  # OK do erro
        time.sleep(2)
        
        print("\nTentativa 3: click direto no campo senha")
        rdp.mouse.click(700, 400, click_count=3)
        time.sleep(1)
        rdp.keyboard.type('AMANDA', delay=100)
        time.sleep(1)
        
        # Clica DIRETO no campo senha - tenta várias posições Y
        rdp.mouse.click(700, 435)
        time.sleep(1)
        rdp.mouse.click(700, 435, click_count=3)
        time.sleep(0.5)
        rdp.keyboard.type('amanda001', delay=100)
        time.sleep(1)
        ss(rdp, "07_tentativa3_preenchido")
        
        rdp.keyboard.press('Enter')
        time.sleep(20)
        ss(rdp, "08_tentativa3_resultado")
        
        # Se login funcionou em alguma tentativa, explora menus
        # Verifica tentando abrir um menu
        rdp.keyboard.press('Alt+f')
        time.sleep(2)
        ss(rdp, "09_teste_menu")
        rdp.keyboard.press('Escape')
        
        # Se conseguiu abrir o menu, continua a exploração
        print("\n=== Explorando menus (se logado) ===")
        
        # Ferramentas > Exportação de Dados
        rdp.keyboard.press('Alt+f')
        time.sleep(2)
        for i in range(8):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('ArrowRight')
        time.sleep(2)
        ss(rdp, "10_exportacao_submenu")
        
        # Screenshot de cada item do submenu
        for i in range(5):
            ss(rdp, f"11_sub_{i}")
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.5)
        
        # Abre o primeiro item
        for i in range(5):
            rdp.keyboard.press('ArrowUp')
            time.sleep(0.2)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "12_export_tela1")
        
        # Fecha e segundo item
        rdp.keyboard.press('Escape')
        time.sleep(1)
        rdp.keyboard.press('Alt+f')
        time.sleep(1)
        for i in range(8):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.2)
        rdp.keyboard.press('ArrowRight')
        time.sleep(1)
        rdp.keyboard.press('ArrowDown')
        time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "13_export_tela2")
        
        # Terceiro item
        rdp.keyboard.press('Escape')
        time.sleep(1)
        rdp.keyboard.press('Alt+f')
        time.sleep(1)
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
        ss(rdp, "14_export_tela3")
        
        # Consultas > Gerenciador de Relatórios
        rdp.keyboard.press('Escape')
        time.sleep(1)
        rdp.keyboard.press('Alt+c')
        time.sleep(2)
        for i in range(4):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "20_gerenciador_relatorios")
        
        # Consultas > Documentos
        rdp.keyboard.press('Escape')
        time.sleep(1)
        rdp.keyboard.press('Alt+c')
        time.sleep(2)
        rdp.keyboard.press('ArrowDown')
        time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "30_consulta_docs")
        
        # Arquivos > Clientes
        rdp.keyboard.press('Escape')
        time.sleep(1)
        rdp.keyboard.press('Alt+a')
        time.sleep(2)
        rdp.keyboard.press('ArrowDown')
        time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "40_cadastro_clientes")
        
        # Movimentos > Acomp Renovações
        rdp.keyboard.press('Escape')
        time.sleep(1)
        rdp.keyboard.press('Alt+m')
        time.sleep(2)
        for i in range(3):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "50_renovacoes")
        
        print("\n✅ Concluído!")
        browser.close()

if __name__ == "__main__":
    main()
