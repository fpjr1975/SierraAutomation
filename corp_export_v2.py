"""
Corp — Exporta CSV v2.
Usa coordenadas calibradas do screenshot real.
Janela "Exportação de Clientes" flutua — ajusta baseado na posição real.
"""

from playwright.sync_api import sync_playwright
import time
import os

DIR = "/root/sierra/corp_export_v2"
os.makedirs(DIR, exist_ok=True)

def ss(page, name):
    path = f"{DIR}/{name}.jpg"
    page.screenshot(path=path, quality=90, type="jpeg")
    print(f"📸 {name}")

def find_white_fields(rdp):
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

def find_window_top(rdp):
    """Encontra o topo da janela flutuante (barra de título cinza)."""
    return rdp.evaluate("""() => {
        const canvas = document.querySelector('#JWTS_myCanvas') || document.querySelector('canvas');
        if (!canvas) return null;
        const ctx = canvas.getContext('2d');
        if (!ctx) return null;
        
        // Procura a borda superior da janela (mudança de cor escura pra cinza claro)
        // A janela tem uma barra de título cinza e um corpo branco/cinza claro
        // Varre coluna x=400 de cima pra baixo
        for (let y = 50; y < 500; y++) {
            const pixel = ctx.getImageData(400, y, 1, 1).data;
            const r = pixel[0], g = pixel[1], b = pixel[2];
            // A barra de título é cinza claro (~RGB 240,240,240)
            // O background do Corp é escuro (~RGB 40,40,50)
            if (r > 200 && g > 200 && b > 200) {
                return y;
            }
        }
        return null;
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
    print(f"Campos login: {fields}")
    
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
        
        # Abre Exportação de Clientes
        print("\n=== Abrindo Exportação ===")
        rdp.keyboard.press('Alt+f')
        time.sleep(2)
        for i in range(6):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('ArrowRight')
        time.sleep(2)
        rdp.keyboard.press('ArrowDown')
        time.sleep(0.5)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "01_tela")
        
        # Encontra posição da janela
        win_top = find_window_top(rdp)
        print(f"Janela top: y={win_top}")
        
        # Baseado no screenshot real, as posições RELATIVAS ao topo da janela são:
        # Título "Exportação de Clientes": +0
        # Filial/Agente row: +25
        # Seguradora/Produtor row: +50
        # Ramo/Cliente row: +75
        # Checkbox "Apresentar...": +95
        # Colunas tabela: +110
        # .vCard radio: +68 relativo ao grupo "Tipo de Exportação" que está à +55 do topo
        # .CSV radio: +90 relativo ao grupo
        
        # Coordenadas absolutas baseadas no screenshot anterior:
        # Janela topo estava em ~y=200
        # .vCard: y=288 (offset +88)
        # .CSV: y=312 (offset +112)  
        # Botão exportar (ícone azul): y=280, x=795 (offset +80)
        # Lupa buscar: deve estar em algum lugar...
        
        if win_top:
            csv_y = win_top + 112
            csv_x = 635
            export_btn_y = win_top + 80
            export_btn_x = 795
            date_y = win_top + 44
            date_x = 430
        else:
            # Fallback: baseado no screenshot
            csv_y = 312
            csv_x = 635
            export_btn_y = 280
            export_btn_x = 795
            date_y = 244
            date_x = 430
        
        # 1. Seleciona .CSV
        print(f"\n=== Selecionando .CSV em ({csv_x}, {csv_y}) ===")
        rdp.mouse.click(csv_x, csv_y)
        time.sleep(1)
        ss(rdp, "02_csv")
        
        # 2. Limpa filtro de data pra pegar TUDO
        print(f"\n=== Limpando data em ({date_x}, {date_y}) ===")
        rdp.mouse.click(date_x, date_y, click_count=3)
        time.sleep(0.5)
        rdp.keyboard.press('Delete')
        time.sleep(0.5)
        # Preenche com data antiga pra pegar histórico completo
        rdp.keyboard.type('01/01/2020', delay=50)
        time.sleep(1)
        ss(rdp, "03_data")
        
        # 3. Busca registros — tenta botão lupa na toolbar da janela
        # A lupa na toolbar principal está em ~x=295, y=45 
        # Mas a janela pode ter seu próprio botão de busca
        # Tenta Enter ou F5 primeiro
        print("\n=== Buscando registros ===")
        
        # Tenta clicar na lupa da toolbar principal
        rdp.mouse.click(295, 45)
        time.sleep(8)
        ss(rdp, "04_busca1")
        
        # Se não carregou, tenta o ícone de "selecionar todos" no canto inferior esquerdo
        # que pode também funcionar como "filtrar"
        # Ícones bottom-left: x=110, y=870 e x=155, y=870
        rdp.mouse.click(110, 870)
        time.sleep(5)
        ss(rdp, "05_busca2")
        
        # Verifica filtrados
        time.sleep(3)
        ss(rdp, "06_status")
        
        # 4. Se tem registros, seleciona todos
        print("\n=== Selecionando todos ===")
        rdp.mouse.click(110, 870)
        time.sleep(2)
        ss(rdp, "07_selecionados")
        
        # 5. Clica no botão EXPORTAR (ícone azul com seta)
        print(f"\n=== Exportando em ({export_btn_x}, {export_btn_y}) ===")
        rdp.mouse.click(export_btn_x, export_btn_y)
        time.sleep(5)
        ss(rdp, "08_export_click")
        time.sleep(5)
        ss(rdp, "09_export_result")
        
        # Se aparecer dialog, confirma
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "10_pos_enter")
        
        # Tenta mais uma vez caso tenha dialog de pasta
        rdp.keyboard.press('Enter')
        time.sleep(3)
        ss(rdp, "11_final")
        
        print("\n✅ Concluído!")
        browser.close()

if __name__ == "__main__":
    main()
