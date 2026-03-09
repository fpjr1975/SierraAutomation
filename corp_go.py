"""
Corp — Login + Ferramentas > Exportação de Dados
Abordagem: espera mais, delays maiores, triple-click nos campos.
"""

from playwright.sync_api import sync_playwright
import time
import os

DIR = "/root/sierra/corp_go"
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
        
        # Espera BEM mais pro RDP carregar
        time.sleep(35)
        ss(rdp, "00_login_screen")
        
        # Triple-click no campo usuario pra selecionar tudo
        rdp.mouse.click(700, 400, click_count=3)
        time.sleep(1)
        # Deleta qualquer conteúdo
        rdp.keyboard.press('Delete')
        time.sleep(0.5)
        rdp.keyboard.press('Backspace')
        time.sleep(0.5)
        # Digita devagar
        for ch in 'AMANDA':
            rdp.keyboard.press(ch)
            time.sleep(0.15)
        time.sleep(1)
        ss(rdp, "01_usuario")
        
        # Tab com espera grande
        rdp.keyboard.press('Tab')
        time.sleep(2)
        
        # Digita senha devagar
        for ch in 'amanda001':
            rdp.keyboard.press(ch)
            time.sleep(0.15)
        time.sleep(1)
        ss(rdp, "02_preenchido")
        
        # Enter
        rdp.keyboard.press('Enter')
        print("✅ Login enviado")
        time.sleep(25)
        ss(rdp, "03_resultado")
        
        # === Verifica se logou tentando Alt+F ===
        rdp.keyboard.press('Alt+f')
        time.sleep(2)
        ss(rdp, "04_teste_ferramentas")
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        # === FERRAMENTAS > EXPORTAÇÃO DE DADOS ===
        print("\n=== Ferramentas > Exportação de Dados ===")
        rdp.keyboard.press('Alt+f')
        time.sleep(2)
        
        # Navega: Acomp Assinaturas, Agenda, Controle Recibos,
        # Envelopes, Planilha, (sep), Mala Direta, Exportação de Dados
        for i in range(8):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.4)
        time.sleep(1)
        ss(rdp, "05_exportacao_hover")
        
        # Abre submenu
        rdp.keyboard.press('ArrowRight')
        time.sleep(2)
        ss(rdp, "06_exportacao_submenu")
        
        # Mapeia cada item do submenu
        for i in range(8):
            ss(rdp, f"07_sub_{i}")
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.5)
        
        # Volta ao topo
        for i in range(8):
            rdp.keyboard.press('ArrowUp')
            time.sleep(0.2)
        time.sleep(0.5)
        
        # Abre PRIMEIRO item do submenu
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "10_export_item1")
        time.sleep(3)
        ss(rdp, "11_export_item1b")
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        # Abre SEGUNDO item
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
        ss(rdp, "12_export_item2")
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        # Abre TERCEIRO item
        rdp.keyboard.press('Alt+f')
        time.sleep(1.5)
        for i in range(8):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.2)
        rdp.keyboard.press('ArrowRight')
        time.sleep(1)
        for i in range(2):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "13_export_item3")
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        # === CONSULTAS ===
        print("\n=== Consultas ===")
        
        # Gerenciador de Relatórios (4o item)
        rdp.keyboard.press('Alt+c')
        time.sleep(2)
        ss(rdp, "20_consultas_menu")
        for i in range(4):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "21_gerenciador")
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        # Gráficos de Análise (5o item)
        rdp.keyboard.press('Alt+c')
        time.sleep(2)
        for i in range(5):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "22_graficos")
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        # === ARQUIVOS > CLIENTES ===
        print("\n=== Arquivos > Clientes ===")
        rdp.keyboard.press('Alt+a')
        time.sleep(2)
        rdp.keyboard.press('ArrowDown')
        time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "30_clientes")
        time.sleep(3)
        ss(rdp, "31_clientes2")
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        # === MOVIMENTOS ===
        print("\n=== Movimentos ===")
        
        # Acomp Renovações (3o item)
        rdp.keyboard.press('Alt+m')
        time.sleep(2)
        for i in range(3):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "40_renovacoes")
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        # Parcelas e Comissões (5o item)
        rdp.keyboard.press('Alt+m')
        time.sleep(2)
        for i in range(5):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "41_parcelas")
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        print("\n✅ TUDO capturado!")
        browser.close()

if __name__ == "__main__":
    main()
