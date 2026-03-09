"""
Corp — Login calibrado com screenshot do Fafá.
Campos mais acima do que eu achava: Usuário ~y=370, Senha ~y=390.
Tenta múltiplas posições Y pra garantir.
"""

from playwright.sync_api import sync_playwright
import time
import os

DIR = "/root/sierra/corp_calibrado"
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
        
        # Mede o canvas pra saber offset
        canvas_info = rdp.evaluate("""() => {
            const c = document.querySelector('#JWTS_myCanvas') || document.querySelector('canvas');
            if (!c) return null;
            const r = c.getBoundingClientRect();
            return {x: r.x, y: r.y, w: r.width, h: r.height};
        }""")
        print(f"Canvas info: {canvas_info}")
        
        # Baseado no screenshot do Fafá, o diálogo parece centrado
        # Vou tentar: clicar no campo usuario, digitar, depois clicar 
        # DIRETAMENTE no campo senha com coordenadas calibradas
        
        # O dialog center está em ~x=600, campos em x=680
        # Vou tentar com o campo de usuario primeiro
        FIELD_X = 690
        
        # Tentativa: click no campo Usuário, limpar, digitar
        rdp.mouse.click(FIELD_X, 370)
        time.sleep(0.5)
        rdp.mouse.click(FIELD_X, 370, click_count=3)
        time.sleep(0.5)
        rdp.keyboard.press('Delete')
        time.sleep(0.3)
        
        for ch in 'AMANDA':
            rdp.keyboard.press(ch)
            time.sleep(0.2)
        time.sleep(1)
        ss(rdp, "01_usuario_digitado")
        
        # Agora clica no campo SENHA - baseado no screenshot, ~20px abaixo
        rdp.mouse.click(FIELD_X, 393)
        time.sleep(0.8)
        rdp.mouse.click(FIELD_X, 393, click_count=3)
        time.sleep(0.3)
        rdp.keyboard.press('Delete')
        time.sleep(0.3)
        
        for ch in 'amanda001':
            rdp.keyboard.press(ch)
            time.sleep(0.2)
        time.sleep(1)
        ss(rdp, "02_senha_digitada")
        
        # Clica em Entrar (~y=413)
        rdp.mouse.click(FIELD_X, 413)
        time.sleep(3)
        rdp.keyboard.press('Enter')
        print("✅ Login enviado")
        time.sleep(22)
        ss(rdp, "03_resultado")
        
        # Se falhou, tenta com Y mais baixo (dialog pode estar mais embaixo no headless)
        # Verifica se ainda tá na tela de login
        rdp.mouse.click(600, 457)  # possível botão OK do erro
        time.sleep(2)
        
        # Tenta com coordenadas mais baixas
        print("\n=== Tentativa 2: Y mais baixo ===")
        FIELD_X2 = 690
        
        rdp.mouse.click(FIELD_X2, 430)
        time.sleep(0.5)
        rdp.mouse.click(FIELD_X2, 430, click_count=3)
        time.sleep(0.5)
        rdp.keyboard.press('Delete')
        time.sleep(0.3)
        for ch in 'AMANDA':
            rdp.keyboard.press(ch)
            time.sleep(0.2)
        time.sleep(1)
        ss(rdp, "04_t2_usuario")
        
        # Senha: 25px abaixo
        rdp.mouse.click(FIELD_X2, 455)
        time.sleep(0.8)
        rdp.mouse.click(FIELD_X2, 455, click_count=3)
        time.sleep(0.3)
        rdp.keyboard.press('Delete')
        time.sleep(0.3)
        for ch in 'amanda001':
            rdp.keyboard.press(ch)
            time.sleep(0.2)
        time.sleep(1)
        ss(rdp, "05_t2_senha")
        
        # Entrar
        rdp.mouse.click(FIELD_X2, 480)
        time.sleep(2)
        rdp.keyboard.press('Enter')
        time.sleep(22)
        ss(rdp, "06_t2_resultado")
        
        # Se falhou de novo, tenta Y ainda mais baixo
        rdp.mouse.click(600, 457)
        time.sleep(2)
        
        print("\n=== Tentativa 3: Y 450/475 ===")
        rdp.mouse.click(FIELD_X2, 450)
        time.sleep(0.5)
        rdp.mouse.click(FIELD_X2, 450, click_count=3)
        time.sleep(0.5)
        rdp.keyboard.press('Delete')
        time.sleep(0.3)
        for ch in 'AMANDA':
            rdp.keyboard.press(ch)
            time.sleep(0.2)
        time.sleep(1)
        
        rdp.mouse.click(FIELD_X2, 475)
        time.sleep(0.8)
        rdp.mouse.click(FIELD_X2, 475, click_count=3)
        time.sleep(0.3)
        rdp.keyboard.press('Delete')
        time.sleep(0.3)
        for ch in 'amanda001':
            rdp.keyboard.press(ch)
            time.sleep(0.2)
        time.sleep(1)
        ss(rdp, "07_t3_preenchido")
        
        rdp.mouse.click(FIELD_X2, 500)
        time.sleep(2)
        rdp.keyboard.press('Enter')
        time.sleep(22)
        ss(rdp, "08_t3_resultado")
        
        # Testa se logou
        rdp.keyboard.press('Alt+f')
        time.sleep(2)
        ss(rdp, "09_teste_menu")
        rdp.keyboard.press('Escape')
        time.sleep(1)

        # Se qualquer tentativa funcionou, vai pros menus
        print("\n=== Explorando Ferramentas > Exportação ===")
        rdp.keyboard.press('Alt+f')
        time.sleep(2)
        ss(rdp, "10_ferramentas")
        
        for i in range(8):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('ArrowRight')
        time.sleep(2)
        ss(rdp, "11_exportacao_sub")
        
        # Screenshot cada item
        for i in range(6):
            ss(rdp, f"12_item_{i}")
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.5)
        
        # Volta e abre primeiro
        for i in range(6):
            rdp.keyboard.press('ArrowUp')
            time.sleep(0.2)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "13_export1")
        
        # Fecha e segundo
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
        ss(rdp, "14_export2")
        
        # Terceiro
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
        ss(rdp, "15_export3")
        
        # === Gerenciador de Relatórios ===
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
