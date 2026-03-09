"""
Corp — Login (coordenadas invertidas) + abre as 2 telas de Exportação de Dados.
Coordenadas descobertas: Usuário y=463, Senha y=430 (invertidas!)
"""

from playwright.sync_api import sync_playwright
import time
import os

DIR = "/root/sierra/corp_export_final"
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
    time.sleep(12)
    
    with ctx.expect_page(timeout=20000) as npi:
        page.click('text=Sierra')
    rdp = npi.value
    print("✅ Aba RDP")
    time.sleep(35)
    
    # Login Corp — coordenadas INVERTIDAS!
    # Usuário (visualmente acima) = y=463 no canvas
    rdp.mouse.click(725, 463, click_count=3)
    time.sleep(1)
    rdp.keyboard.type('AMANDA', delay=80)
    time.sleep(1)
    
    # Senha (visualmente abaixo) = y=430 no canvas
    rdp.mouse.click(725, 430, click_count=3)
    time.sleep(1)
    rdp.keyboard.type('amanda001', delay=80)
    time.sleep(1)
    
    rdp.keyboard.press('Enter')
    print("✅ Login Corp enviado")
    time.sleep(25)
    
    return rdp

def open_ferramentas_exportacao(rdp, item_index=0):
    """Abre Ferramentas > Exportação de Dados > item (0=primeiro, 1=segundo)"""
    rdp.keyboard.press('Alt+f')
    time.sleep(2)
    
    # Navega até Exportação de Dados (8 ArrowDown)
    # Items: Acomp.Assinaturas, Agenda, Controle Recibos,
    # Envelopes, Planilha, (sep), Mala Direta, Exportação de Dados
    for i in range(8):
        rdp.keyboard.press('ArrowDown')
        time.sleep(0.3)
    
    # Abre submenu
    rdp.keyboard.press('ArrowRight')
    time.sleep(2)
    
    # Navega pro item desejado
    for i in range(item_index):
        rdp.keyboard.press('ArrowDown')
        time.sleep(0.3)
    
    return True

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1280, 'height': 900})
        rdp = login_corp(ctx)
        ss(rdp, "00_home")
        
        # Verifica se logou
        rdp.keyboard.press('Alt+a')
        time.sleep(2)
        ss(rdp, "01_teste_menu")
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        # ========================================
        # EXPORTAÇÃO 1: Exportação de Itens
        # ========================================
        print("\n=== Exportação de Itens ===")
        open_ferramentas_exportacao(rdp, item_index=0)
        ss(rdp, "10_sub_exportacao_itens")
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "11_tela_exportacao_itens")
        time.sleep(3)
        ss(rdp, "12_tela_exportacao_itens_2")
        
        # Explora a tela - tira screenshots de diferentes partes
        # Tenta scroll ou Tab pra ver mais opções
        rdp.keyboard.press('Tab')
        time.sleep(1)
        ss(rdp, "13_export_itens_tab1")
        rdp.keyboard.press('Tab')
        time.sleep(1)
        ss(rdp, "14_export_itens_tab2")
        
        # Fecha a tela
        rdp.keyboard.press('Escape')
        time.sleep(2)
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        # ========================================
        # EXPORTAÇÃO 2: Clientes e Documentos
        # ========================================
        print("\n=== Clientes e Documentos ===")
        open_ferramentas_exportacao(rdp, item_index=1)
        ss(rdp, "20_sub_clientes_docs")
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "21_tela_clientes_docs")
        time.sleep(3)
        ss(rdp, "22_tela_clientes_docs_2")
        
        # Explora
        rdp.keyboard.press('Tab')
        time.sleep(1)
        ss(rdp, "23_clientes_tab1")
        rdp.keyboard.press('Tab')
        time.sleep(1)
        ss(rdp, "24_clientes_tab2")
        rdp.keyboard.press('Tab')
        time.sleep(1)
        ss(rdp, "25_clientes_tab3")
        
        # Fecha
        rdp.keyboard.press('Escape')
        time.sleep(2)
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        # ========================================
        # CONSULTAS > GERENCIADOR DE RELATÓRIOS
        # ========================================
        print("\n=== Gerenciador de Relatórios ===")
        rdp.keyboard.press('Alt+c')
        time.sleep(2)
        ss(rdp, "30_consultas_menu")
        # Items: Documentos, Fluxo Caixa, Sinistros, Gerenciador Relatórios
        for i in range(4):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "31_gerenciador")
        time.sleep(3)
        ss(rdp, "32_gerenciador_2")
        
        # Explora
        rdp.keyboard.press('Tab')
        time.sleep(1)
        ss(rdp, "33_gerenciador_tab1")
        
        # Fecha
        rdp.keyboard.press('Escape')
        time.sleep(2)
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        # ========================================
        # CONSULTAS > GRÁFICOS
        # ========================================
        print("\n=== Gráficos de Análise ===")
        rdp.keyboard.press('Alt+c')
        time.sleep(2)
        for i in range(5):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "40_graficos")
        time.sleep(3)
        ss(rdp, "41_graficos_2")
        
        # Fecha
        rdp.keyboard.press('Escape')
        time.sleep(2)
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        # ========================================
        # CONSULTAS > DOCUMENTOS (Consulta Avançada)
        # ========================================
        print("\n=== Consulta de Documentos ===")
        rdp.keyboard.press('Alt+c')
        time.sleep(2)
        rdp.keyboard.press('ArrowDown')
        time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "50_consulta_docs")
        time.sleep(3)
        ss(rdp, "51_consulta_docs_2")
        
        # Fecha
        rdp.keyboard.press('Escape')
        time.sleep(2)
        
        # ========================================
        # MOVIMENTOS > ACOMP RENOVAÇÕES
        # ========================================
        print("\n=== Acomp. Renovações ===")
        rdp.keyboard.press('Alt+m')
        time.sleep(2)
        for i in range(3):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "60_renovacoes")
        time.sleep(3)
        ss(rdp, "61_renovacoes_2")
        
        print("\n✅ EXPLORAÇÃO COMPLETA!")
        browser.close()

if __name__ == "__main__":
    main()
