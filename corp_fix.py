"""
Corp — Login com Shift+Tab pra navegar pros campos corretos.
Descoberta: y=430 = Senha, y=463 = Usuário (invertido do visual).
Nova estratégia: Shift+Tab pra ir pro primeiro campo, depois Tab.
"""

from playwright.sync_api import sync_playwright
import time
import os

DIR = "/root/sierra/corp_fix"
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
        
        # ========================================
        # ABORDAGEM: Click no dialog + Shift+Tab pra voltar ao primeiro campo
        # ========================================
        
        # Click no meio do dialog pra dar foco
        rdp.mouse.click(640, 430)
        time.sleep(1)
        
        # Shift+Tab várias vezes pra garantir que estou no PRIMEIRO campo (Usuário)
        for _ in range(5):
            rdp.keyboard.press('Shift+Tab')
            time.sleep(0.5)
        
        # Agora deve estar no campo Usuário
        rdp.keyboard.press('Control+a')
        time.sleep(0.3)
        rdp.keyboard.type('AMANDA', delay=80)
        time.sleep(1)
        ss(rdp, "01_usuario")
        
        # Tab pro campo Senha
        rdp.keyboard.press('Tab')
        time.sleep(1)
        
        rdp.keyboard.type('amanda001', delay=80)
        time.sleep(1)
        ss(rdp, "02_senha")
        
        # Enter pra logar
        rdp.keyboard.press('Enter')
        print("✅ Login tentativa 1 (Shift+Tab)")
        time.sleep(25)
        ss(rdp, "03_resultado")
        
        # ========================================
        # Se falhou, tenta invertendo: y=463 = Usuário, y=430 = Senha
        # ========================================
        rdp.mouse.click(600, 457)  # OK do erro
        time.sleep(2)
        
        print("\n=== Tentativa 2: Coords invertidas ===")
        # Baseado na descoberta: y=463 é Usuário
        rdp.mouse.click(725, 463, click_count=3)
        time.sleep(1)
        rdp.keyboard.type('AMANDA', delay=80)
        time.sleep(1)
        ss(rdp, "04_t2_usuario")
        
        # y=430 é Senha
        rdp.mouse.click(725, 430, click_count=3)
        time.sleep(1)
        rdp.keyboard.type('amanda001', delay=80)
        time.sleep(1)
        ss(rdp, "05_t2_senha")
        
        rdp.keyboard.press('Enter')
        print("✅ Login tentativa 2 (invertido)")
        time.sleep(25)
        ss(rdp, "06_t2_resultado")
        
        # ========================================
        # Se ainda falhou, tenta Home pra ir ao primeiro campo
        # ========================================
        rdp.mouse.click(600, 457)
        time.sleep(2)
        
        print("\n=== Tentativa 3: Home key ===")
        # Click no dialog
        rdp.mouse.click(640, 430)
        time.sleep(1)
        # Home pra ir ao início
        rdp.keyboard.press('Home')
        time.sleep(0.5)
        # Ctrl+Home
        rdp.keyboard.press('Control+Home')
        time.sleep(0.5)
        # Shift+Tab muitas vezes
        for _ in range(10):
            rdp.keyboard.press('Shift+Tab')
            time.sleep(0.3)
        
        rdp.keyboard.type('AMANDA', delay=80)
        time.sleep(1)
        rdp.keyboard.press('Tab')
        time.sleep(1)
        rdp.keyboard.type('amanda001', delay=80)
        time.sleep(1)
        ss(rdp, "07_t3_preenchido")
        
        rdp.keyboard.press('Enter')
        print("✅ Login tentativa 3")
        time.sleep(25)
        ss(rdp, "08_t3_resultado")
        
        # Verifica se logou
        rdp.keyboard.press('Alt+a')
        time.sleep(2)
        ss(rdp, "09_teste_menu")
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        # === MENUS ===
        print("\n=== Ferramentas > Exportação ===")
        rdp.keyboard.press('Alt+f')
        time.sleep(2)
        ss(rdp, "10_ferramentas")
        for i in range(8):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('ArrowRight')
        time.sleep(2)
        ss(rdp, "11_exportacao_sub")
        
        for i in range(5):
            ss(rdp, f"12_sub_{i}")
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.5)
        
        # Primeiro item
        for i in range(5):
            rdp.keyboard.press('ArrowUp')
            time.sleep(0.2)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "13_export1")
        
        # Segundo item
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
        ss(rdp, "14_export2")
        
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
        ss(rdp, "15_export3")
        
        # Gerenciador relatórios
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
        
        print("\n✅ Concluído!")
        browser.close()

if __name__ == "__main__":
    main()
