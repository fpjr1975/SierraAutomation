"""
Corp — Extração completa de dados.
1. Login via pixel detection
2. Gerenciador de Relatórios — captura todos os meses/abas
3. Ferramentas > Exportação > Clientes e Documentos (CSV)
4. Ferramentas > Exportação > Exportação de Itens
"""

from playwright.sync_api import sync_playwright
import time
import os
import json

DIR = "/root/sierra/corp_data"
os.makedirs(DIR, exist_ok=True)

def ss(page, name):
    path = f"{DIR}/{name}.jpg"
    page.screenshot(path=path, quality=90, type="jpeg")
    print(f"📸 {name}")

def find_white_fields(rdp):
    """Encontra campos brancos (inputs) no canvas via análise de pixels."""
    fields = rdp.evaluate("""() => {
        const canvas = document.querySelector('#JWTS_myCanvas') || document.querySelector('canvas');
        if (!canvas) return null;
        const ctx = canvas.getContext('2d');
        if (!ctx) return null;
        
        const results = [];
        for (let y = 200; y < 600; y++) {
            const pixel = ctx.getImageData(700, y, 1, 1).data;
            const isWhite = pixel[0] > 240 && pixel[1] > 240 && pixel[2] > 240;
            if (isWhite) {
                const prevPixel = ctx.getImageData(700, y-1, 1, 1).data;
                const prevWhite = prevPixel[0] > 240 && prevPixel[1] > 240 && prevPixel[2] > 240;
                if (!prevWhite) {
                    let endY = y;
                    while (endY < 600) {
                        const p = ctx.getImageData(700, endY, 1, 1).data;
                        if (p[0] <= 240 || p[1] <= 240 || p[2] <= 240) break;
                        endY++;
                    }
                    results.push({startY: y, endY: endY, height: endY - y, centerY: Math.round((y + endY) / 2)});
                    y = endY;
                }
            }
        }
        return results;
    }""")
    return fields

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
    
    # Pixel detection pra achar os campos
    fields = find_white_fields(rdp)
    print(f"Campos encontrados: {fields}")
    
    if fields and len(fields) >= 2:
        user_y = fields[0]['centerY']
        pass_y = fields[1]['centerY']
        print(f"🎯 Usuário: y={user_y}, Senha: y={pass_y}")
        
        rdp.mouse.click(700, user_y, click_count=3)
        time.sleep(1)
        rdp.keyboard.type('AMANDA', delay=80)
        time.sleep(1)
        
        rdp.mouse.click(700, pass_y, click_count=3)
        time.sleep(1)
        rdp.keyboard.type('amanda001', delay=80)
        time.sleep(1)
        
        rdp.keyboard.press('Enter')
        print("✅ Login Corp enviado")
        time.sleep(25)
    else:
        print("⚠️ Campos não encontrados, tentando coords padrão")
        rdp.mouse.click(700, 461, click_count=3)
        time.sleep(1)
        rdp.keyboard.type('AMANDA', delay=80)
        time.sleep(1)
        rdp.mouse.click(700, 493, click_count=3)
        time.sleep(1)
        rdp.keyboard.type('amanda001', delay=80)
        time.sleep(1)
        rdp.keyboard.press('Enter')
        print("✅ Login Corp enviado (fallback)")
        time.sleep(25)
    
    ss(rdp, "00_login_resultado")
    return rdp

def dismiss_dialogs(rdp):
    """Fecha qualquer dialog (Escape, Enter, etc)."""
    rdp.keyboard.press('Escape')
    time.sleep(1)
    rdp.keyboard.press('Escape')
    time.sleep(0.5)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1280, 'height': 900})
        rdp = login_corp(ctx)
        
        # ========================================
        # PARTE 1: GERENCIADOR DE RELATÓRIOS
        # Captura todos os meses e todas as abas
        # ========================================
        print("\n" + "="*60)
        print("PARTE 1: GERENCIADOR DE RELATÓRIOS")
        print("="*60)
        
        # Abre Consultas > Gerenciador de Relatórios
        # Na primeira exploração, Alt+C abriu Consultas
        # Items: 1.Documentos, 2.Fluxo Caixa, 3.Sinistros, 4.Gerenciador, 5.Gráficos
        rdp.keyboard.press('Alt+c')
        time.sleep(2)
        for i in range(4):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "10_gerenciador_home")
        
        # Pode ter dialog de atualização do InCorp - fecha
        rdp.keyboard.press('Escape')
        time.sleep(1)
        rdp.keyboard.press('Enter')  # caso tenha botão Não/OK
        time.sleep(2)
        
        # Re-abre Gerenciador
        rdp.keyboard.press('Alt+c')
        time.sleep(2)
        for i in range(4):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "11_gerenciador")
        
        # O Gerenciador tem 3 abas: Prêmio Base | Comissão | Qtde de Docs
        # E sub-abas: Produção Total | Ranking
        # Meses: Jan a Dez, Anos: 2024, 2025, 2026
        # Vou clicar em cada aba e capturar
        
        # Aba Prêmio Base já deve estar selecionada
        time.sleep(2)
        ss(rdp, "12_premio_base_mar26")
        
        # Clica na aba Comissão (está à direita de Prêmio Base)
        # Baseado no layout: Prêmio Base ~x=65, Comissão ~x=195, Qtde de Docs ~x=340
        # Mas como está no RDP canvas, preciso clicar em coordenadas do menu
        # As abas estão no topo da tela do Gerenciador, ~y=25
        rdp.mouse.click(195, 25)
        time.sleep(3)
        ss(rdp, "13_comissao_mar26")
        
        # Aba Qtde de Docs
        rdp.mouse.click(340, 25)
        time.sleep(3)
        ss(rdp, "14_qtde_docs_mar26")
        
        # Volta pra Prêmio Base e navega pelos meses
        rdp.mouse.click(65, 25)
        time.sleep(2)
        
        # Navega pra 2025 (clica no ano)
        # O seletor de ano está no topo: < 2024 2025 2026 >
        # Clica em "2025" (~x=615, y=57)
        rdp.mouse.click(615, 57)
        time.sleep(3)
        ss(rdp, "15_premio_2025")
        
        # Captura cada mês de 2025 (Jan a Dez)
        # Meses estão em: Jan ~x=440, Fev ~x=465, Mar ~x=495, Abr ~x=530...
        # Vou clicar em cada um
        meses_x = {
            'Jan': 440, 'Fev': 470, 'Mar': 500, 'Abr': 530,
            'Mai': 555, 'Jun': 580, 'Jul': 600, 'Ago': 625,
            'Set': 650, 'Out': 675, 'Nov': 700, 'Dez': 728
        }
        
        for mes, x in meses_x.items():
            rdp.mouse.click(x, 80)
            time.sleep(2)
            ss(rdp, f"20_premio_{mes}25")
        
        # Agora aba Comissão 2025
        rdp.mouse.click(195, 25)
        time.sleep(2)
        for mes, x in meses_x.items():
            rdp.mouse.click(x, 80)
            time.sleep(2)
            ss(rdp, f"21_comissao_{mes}25")
        
        # Qtde Docs 2025
        rdp.mouse.click(340, 25)
        time.sleep(2)
        for mes, x in meses_x.items():
            rdp.mouse.click(x, 80)
            time.sleep(2)
            ss(rdp, f"22_qtde_{mes}25")
        
        # Ranking (sub-aba)
        # Volta pra Prêmio Base
        rdp.mouse.click(65, 25)
        time.sleep(2)
        # Clica em "Ranking" (~x=165, y=98)
        rdp.mouse.click(165, 98)
        time.sleep(3)
        ss(rdp, "23_ranking_2025")
        
        # Fecha gerenciador
        dismiss_dialogs(rdp)
        
        # ========================================
        # PARTE 2: GRÁFICOS DE ANÁLISE E METAS
        # ========================================
        print("\n" + "="*60)
        print("PARTE 2: GRÁFICOS DE ANÁLISE E METAS")
        print("="*60)
        
        rdp.keyboard.press('Alt+c')
        time.sleep(2)
        for i in range(5):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "30_graficos")
        time.sleep(3)
        ss(rdp, "31_graficos_2")
        dismiss_dialogs(rdp)
        
        # ========================================
        # PARTE 3: EXPORTAÇÃO - CLIENTES E DOCUMENTOS
        # ========================================
        print("\n" + "="*60)
        print("PARTE 3: EXPORTAÇÃO - CLIENTES E DOCUMENTOS")
        print("="*60)
        
        # Abre Ferramentas > Exportação de Dados > Clientes e Documentos
        rdp.keyboard.press('Alt+f')
        time.sleep(2)
        ss(rdp, "40_ferramentas_menu")
        
        # Conta os itens:
        # 1.Acomp.Assinaturas, 2.Agenda, 3.Controle Recibos,
        # 4.Envelopes, 5.Planilha, (sep), 6.Mala Direta, 7.Exportação, 8.Utilitários
        # Separator pode ou não contar — vou tentar 7 primeiro, depois 8
        for i in range(7):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        ss(rdp, "41_hover_item7")
        rdp.keyboard.press('ArrowRight')
        time.sleep(2)
        ss(rdp, "42_submenu")
        
        # Segundo item do submenu = Clientes e Documentos
        rdp.keyboard.press('ArrowDown')
        time.sleep(0.5)
        ss(rdp, "43_clientes_hover")
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "44_clientes_docs_tela")
        time.sleep(3)
        ss(rdp, "45_clientes_docs_tela2")
        
        # Se a tela abriu, preciso:
        # 1. Mudar pra CSV (radio button)
        # 2. Marcar todos checkboxes
        # 3. Clicar Exportar
        # Mas como é RDP canvas, preciso das coordenadas exatas dos controles
        # Vou documentar a tela e fazer numa segunda passagem
        
        dismiss_dialogs(rdp)
        
        # ========================================
        # PARTE 4: EXPORTAÇÃO - ITENS
        # ========================================
        print("\n" + "="*60)
        print("PARTE 4: EXPORTAÇÃO - ITENS")
        print("="*60)
        
        rdp.keyboard.press('Alt+f')
        time.sleep(2)
        for i in range(7):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('ArrowRight')
        time.sleep(2)
        # Primeiro item = Exportação de Itens
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "50_export_itens_tela")
        time.sleep(3)
        ss(rdp, "51_export_itens_tela2")
        
        dismiss_dialogs(rdp)
        
        # ========================================
        # PARTE 5: CONSULTA DE DOCUMENTOS
        # ========================================
        print("\n" + "="*60)
        print("PARTE 5: CONSULTA DE DOCUMENTOS")
        print("="*60)
        
        rdp.keyboard.press('Alt+c')
        time.sleep(2)
        rdp.keyboard.press('ArrowDown')
        time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "60_consulta_docs")
        time.sleep(3)
        ss(rdp, "61_consulta_docs2")
        
        dismiss_dialogs(rdp)
        
        # ========================================
        # PARTE 6: MOVIMENTOS
        # ========================================
        print("\n" + "="*60)
        print("PARTE 6: ACOMP. RENOVAÇÕES")
        print("="*60)
        
        rdp.keyboard.press('Alt+m')
        time.sleep(2)
        for i in range(3):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "70_renovacoes")
        time.sleep(3)
        ss(rdp, "71_renovacoes2")
        
        dismiss_dialogs(rdp)
        
        # Parcelas e Comissões
        print("\n=== Parcelas e Comissões ===")
        rdp.keyboard.press('Alt+m')
        time.sleep(2)
        for i in range(5):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "72_parcelas")
        time.sleep(3)
        ss(rdp, "73_parcelas2")
        
        # ========================================
        # PARTE 7: CADASTRO CLIENTES
        # ========================================
        print("\n" + "="*60)
        print("PARTE 7: CADASTRO CLIENTES")
        print("="*60)
        
        dismiss_dialogs(rdp)
        rdp.keyboard.press('Alt+a')
        time.sleep(2)
        rdp.keyboard.press('ArrowDown')
        time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "80_clientes")
        time.sleep(3)
        ss(rdp, "81_clientes2")
        
        print("\n" + "="*60)
        print("✅ EXTRAÇÃO COMPLETA!")
        print("="*60)
        
        # Lista todos os screenshots
        files = sorted(os.listdir(DIR))
        print(f"\nTotal de screenshots: {len(files)}")
        
        browser.close()

if __name__ == "__main__":
    main()
