"""
Corp — Exporta CSV de Clientes e Documentos.
1. Login (pixel detection)
2. Ferramentas > Exportação de Dados (6 ArrowDown)
3. Abre Clientes e Documentos
4. Seleciona .CSV
5. Clica buscar pra carregar registros
6. Seleciona todos
7. Exporta
"""

from playwright.sync_api import sync_playwright
import time
import os

DIR = "/root/sierra/corp_do_export"
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
        
        # ========================================
        # Abre Ferramentas > Exportação > Clientes e Documentos
        # 6 ArrowDown = Exportação de Dados (confirmado!)
        # ========================================
        print("\n=== Abrindo Exportação de Clientes e Documentos ===")
        rdp.keyboard.press('Alt+f')
        time.sleep(2)
        for i in range(6):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('ArrowRight')
        time.sleep(2)
        # Segundo item = Clientes e Documentos
        rdp.keyboard.press('ArrowDown')
        time.sleep(0.5)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "01_tela_aberta")
        
        # ========================================
        # Seleciona .CSV (radio button)
        # Baseado no screenshot: .vCard está em ~(540, 142), .CSV em ~(540, 167)
        # ========================================
        print("\n=== Selecionando .CSV ===")
        rdp.mouse.click(540, 167)
        time.sleep(1)
        ss(rdp, "02_csv_selecionado")
        
        # ========================================
        # Limpa filtro de data (Vigentes na Data)
        # Pra pegar TODOS os clientes, preciso limpar o campo de data
        # ou colocar uma data bem antiga
        # Campo data está em ~x=330, y=99
        # Vou limpar o campo
        # ========================================
        print("\n=== Limpando filtro de data ===")
        rdp.mouse.click(330, 99, click_count=3)
        time.sleep(0.5)
        rdp.keyboard.press('Delete')
        time.sleep(0.5)
        ss(rdp, "03_data_limpa")
        
        # ========================================
        # Clica no botão de busca (lupa azul na toolbar)
        # A lupa/botão de busca está na barra de ferramentas ~x=295, y=45
        # Ou pode ser que precise clicar em algum botão na tela
        # Na verdade, baseado no screenshot do Fafá, parece que precisa 
        # clicar no botão de "filtrar" ou "buscar" pra carregar registros
        # Vou tentar o botão da lupa na toolbar principal
        # ========================================
        print("\n=== Buscando registros ===")
        # A lupa na toolbar principal está ~x=295, y=45
        rdp.mouse.click(295, 45)
        time.sleep(5)
        ss(rdp, "04_buscando")
        time.sleep(5)
        ss(rdp, "05_resultados")
        
        # Se não carregou, tenta Enter ou F5
        rdp.keyboard.press('F5')
        time.sleep(5)
        ss(rdp, "06_pos_f5")
        
        # ========================================
        # Verifica quantos registros foram encontrados
        # Status bar deve mostrar "Filtrados: X"
        # ========================================
        time.sleep(3)
        ss(rdp, "07_status")
        
        # ========================================
        # Seleciona TODOS os registros
        # Pode ter um botão "Selecionar Todos" ou Ctrl+A
        # No screenshot do Fafá, há ícones no canto inferior esquerdo
        # com checkmarks (selecionar/deselecionar todos)
        # Ícone de selecionar todos: ~x=20, y=880
        # ========================================
        print("\n=== Selecionando todos ===")
        # Tenta Ctrl+A primeiro
        rdp.keyboard.press('Control+a')
        time.sleep(2)
        ss(rdp, "08_selecionados")
        
        # Se não funcionou, tenta clicar no ícone de selecionar todos
        # Os ícones estão no canto inferior esquerdo: ✓= ~x=22, y=875
        rdp.mouse.click(22, 875)
        time.sleep(2)
        ss(rdp, "09_sel_icone")
        
        # ========================================
        # Clica no botão EXPORTAR
        # O botão verde de exportar está ~x=710, y=145
        # (ícone com seta verde pra baixo)
        # ========================================
        print("\n=== Exportando CSV ===")
        rdp.mouse.click(710, 145)
        time.sleep(5)
        ss(rdp, "10_exportando")
        time.sleep(5)
        ss(rdp, "11_exportando2")
        
        # Pode aparecer dialog "Salvar como" ou mensagem de sucesso
        time.sleep(5)
        ss(rdp, "12_resultado_export")
        
        # Se aparecer dialog de salvar, pressiona Enter pra confirmar
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "13_pos_enter")
        
        # ========================================
        # Agora tenta Exportação de Itens
        # ========================================
        print("\n=== Exportação de Itens ===")
        rdp.keyboard.press('Escape')
        time.sleep(1)
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        rdp.keyboard.press('Alt+f')
        time.sleep(2)
        for i in range(6):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('ArrowRight')
        time.sleep(2)
        # Primeiro item = Exportação de Itens
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "20_itens_tela")
        
        # Na tela de itens, também selecionar CSV se houver opção
        # e buscar/exportar
        time.sleep(3)
        ss(rdp, "21_itens_tela2")
        
        # Tenta buscar
        rdp.keyboard.press('F5')
        time.sleep(5)
        ss(rdp, "22_itens_busca")
        
        # Seleciona todos
        rdp.keyboard.press('Control+a')
        time.sleep(2)
        
        # Tenta clicar no botão exportar (posição similar)
        # Botão exportar na tela de itens deve estar no canto inferior direito
        rdp.mouse.click(1130, 875)
        time.sleep(5)
        ss(rdp, "23_itens_export")
        
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "24_itens_resultado")
        
        print("\n✅ Exportação concluída!")
        browser.close()

if __name__ == "__main__":
    main()
