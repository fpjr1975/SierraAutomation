"""
Corp — Exportação CSV de Clientes e Documentos.
Menu Ferramentas: 6 ArrowDown = Exportação de Dados (sem separador!)
"""

from playwright.sync_api import sync_playwright
import time
import os

DIR = "/root/sierra/corp_csv"
os.makedirs(DIR, exist_ok=True)

def ss(page, name):
    path = f"{DIR}/{name}.jpg"
    page.screenshot(path=path, quality=90, type="jpeg")
    print(f"📸 {name}")

def find_white_fields(rdp):
    """Encontra campos brancos no canvas."""
    return rdp.evaluate("""() => {
        const canvas = document.querySelector('#JWTS_myCanvas') || document.querySelector('canvas');
        if (!canvas) return null;
        const ctx = canvas.getContext('2d');
        if (!ctx) return null;
        const results = [];
        for (let y = 200; y < 600; y++) {
            const pixel = ctx.getImageData(700, y, 1, 1).data;
            if (pixel[0] > 240 && pixel[1] > 240 && pixel[2] > 240) {
                const prev = ctx.getImageData(700, y-1, 1, 1).data;
                if (!(prev[0] > 240 && prev[1] > 240 && prev[2] > 240)) {
                    let endY = y;
                    while (endY < 600) {
                        const p = ctx.getImageData(700, endY, 1, 1).data;
                        if (p[0] <= 240 || p[1] <= 240 || p[2] <= 240) break;
                        endY++;
                    }
                    results.push({centerY: Math.round((y + endY) / 2)});
                    y = endY;
                }
            }
        }
        return results;
    }""")

def login_corp(ctx):
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
    
    fields = find_white_fields(rdp)
    print(f"Campos: {fields}")
    
    if fields and len(fields) >= 2:
        rdp.mouse.click(700, fields[0]['centerY'], click_count=3)
        time.sleep(1)
        rdp.keyboard.type('AMANDA', delay=80)
        time.sleep(1)
        rdp.mouse.click(700, fields[1]['centerY'], click_count=3)
        time.sleep(1)
        rdp.keyboard.type('amanda001', delay=80)
        time.sleep(1)
        rdp.keyboard.press('Enter')
        print("✅ Login Corp")
        time.sleep(25)
    
    return rdp

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1280, 'height': 900})
        rdp = login_corp(ctx)
        ss(rdp, "00_home")
        
        # Verifica login
        rdp.keyboard.press('Alt+a')
        time.sleep(2)
        ss(rdp, "01_test_menu")
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        # ========================================
        # FERRAMENTAS > EXPORTAÇÃO DE DADOS
        # Testa com 6 ArrowDown primeiro
        # ========================================
        print("\n=== Ferramentas > Exportação (6 ArrowDown) ===")
        rdp.keyboard.press('Alt+f')
        time.sleep(2)
        ss(rdp, "10_ferramentas_aberto")
        
        for i in range(6):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.4)
        ss(rdp, "11_item6_selecionado")
        
        # Abre submenu
        rdp.keyboard.press('ArrowRight')
        time.sleep(2)
        ss(rdp, "12_submenu")
        
        # Se o submenu não abriu (talvez 7 ArrowDown), tenta de novo
        # Primeiro, verifica o que está na tela
        # Vamos tentar clicar no segundo item do submenu (Clientes e Documentos)
        rdp.keyboard.press('ArrowDown')
        time.sleep(0.5)
        ss(rdp, "13_submenu_item2")
        
        # Entra na tela
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "14_tela_export")
        time.sleep(3)
        ss(rdp, "15_tela_export2")
        
        # Se não abriu a tela certa, fecha e tenta com 7 ArrowDown
        rdp.keyboard.press('Escape')
        time.sleep(1)
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        print("\n=== Tentativa 2: 7 ArrowDown ===")
        rdp.keyboard.press('Alt+f')
        time.sleep(2)
        for i in range(7):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.4)
        ss(rdp, "20_item7_selecionado")
        rdp.keyboard.press('ArrowRight')
        time.sleep(2)
        ss(rdp, "21_submenu7")
        
        # Segundo item = Clientes e Documentos
        rdp.keyboard.press('ArrowDown')
        time.sleep(0.5)
        ss(rdp, "22_clientes_hover")
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "23_tela_clientes")
        time.sleep(3)
        ss(rdp, "24_tela_clientes2")
        
        # Se abriu, fecha e tenta primeiro item (Exportação de Itens)
        rdp.keyboard.press('Escape')
        time.sleep(1)
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        # Testa primeiro item do submenu
        print("\n=== Exportação de Itens (primeiro item) ===")
        rdp.keyboard.press('Alt+f')
        time.sleep(2)
        for i in range(7):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('ArrowRight')
        time.sleep(2)
        # Primeiro item (já selecionado)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "30_export_itens")
        time.sleep(3)
        ss(rdp, "31_export_itens2")
        
        print("\n✅ Concluído!")
        browser.close()

if __name__ == "__main__":
    main()
