"""
corp_full_map.py — Mapeamento completo do Corp
Executa login e captura screenshots de TODOS os módulos.
Coordenadas corretas (invertidas!): usuário y=463, senha y=430, x=725
"""

from playwright.sync_api import sync_playwright
import time
import os

DIR = "/root/sierra/docs/screenshots"
os.makedirs(DIR, exist_ok=True)

def ss(page, name):
    path = f"{DIR}/{name}.png"
    page.screenshot(path=path, full_page=False)
    print(f"📸 {name}")
    return path

def press_escape_and_wait(rdp, t=1):
    rdp.keyboard.press('Escape')
    time.sleep(t)

def open_menu_and_capture(rdp, alt_key, label, items_count=8):
    """Abre menu via Alt+key, captura screenshot, fecha."""
    rdp.keyboard.press(f'Alt+{alt_key}')
    time.sleep(2)
    ss(rdp, f"menu_{label}")
    press_escape_and_wait(rdp)

def main():
    print("=" * 60)
    print("Corp Full Map — Iniciando")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()

        # === STEP 1: Login Portal ===
        print("\n🔐 Login portal...")
        page.goto('https://corpnuvem-14.ddns.net/software/html5.html',
                  timeout=30000, wait_until='networkidle')
        page.fill('#Editbox1', 'sierra')
        page.fill('#Editbox2', 'sierr@seg0418')
        page.click('#buttonLogOn')
        print("✅ Portal OK")
        time.sleep(12)

        # === STEP 2: Abre aba RDP ===
        print("📡 Abrindo aba RDP...")
        with ctx.expect_page(timeout=20000) as npi:
            page.click('text=Sierra')
        rdp = npi.value
        print("✅ Aba RDP aberta")

        # Aguarda RDP carregar completamente
        print("⏳ Aguardando RDP carregar (35s)...")
        time.sleep(35)
        ss(rdp, "00_rdp_carregado")

        # === STEP 3: Login Corp (coords INVERTIDAS!) ===
        print("\n🔑 Login Corp...")
        # Usuário fica VISUALMENTE acima mas y=463 no canvas
        rdp.mouse.click(725, 463, click_count=3)
        time.sleep(1)
        rdp.keyboard.type('AMANDA', delay=80)
        time.sleep(1)
        ss(rdp, "01_usuario_digitado")

        # Senha fica VISUALMENTE abaixo mas y=430 no canvas
        rdp.mouse.click(725, 430, click_count=3)
        time.sleep(1)
        rdp.keyboard.type('amanda001', delay=80)
        time.sleep(1)
        ss(rdp, "02_senha_digitada")

        # Submete
        rdp.keyboard.press('Enter')
        print("⏳ Aguardando login Corp (25s)...")
        time.sleep(25)
        ss(rdp, "03_pos_login")

        # === STEP 4: Verifica login e captura tela inicial ===
        print("\n📊 Verificando login...")
        rdp.keyboard.press('Alt+a')
        time.sleep(2)
        ss(rdp, "04_menu_arquivos_aberto")
        rdp.keyboard.press('Escape')
        time.sleep(1)
        ss(rdp, "05_tela_inicial_home")

        # === STEP 5: Arquivos > Clientes ===
        print("\n👥 Arquivos > Clientes...")
        rdp.keyboard.press('Alt+a')
        time.sleep(2)
        rdp.keyboard.press('ArrowDown')  # Clientes é 1º item
        time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "10_clientes_lista")
        time.sleep(2)
        ss(rdp, "11_clientes_lista2")
        press_escape_and_wait(rdp, 2)

        # === STEP 6: Arquivos > Apólices ===
        print("\n📋 Arquivos > Apólices...")
        rdp.keyboard.press('Alt+a')
        time.sleep(2)
        # Navega até Apólices (2º item geralmente)
        for i in range(2):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "12_apolices")
        press_escape_and_wait(rdp, 2)

        # === STEP 7: Movimentos ===
        print("\n🔄 Movimentos...")
        rdp.keyboard.press('Alt+m')
        time.sleep(2)
        ss(rdp, "20_movimentos_menu")

        # === STEP 8: Movimentos > Acomp. Renovações (3x ArrowDown) ===
        print("\n🔄 Movimentos > Acomp. Renovações...")
        rdp.keyboard.press('Escape')
        time.sleep(0.5)
        rdp.keyboard.press('Alt+m')
        time.sleep(2)
        for i in range(3):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        ss(rdp, "21_renovacoes_highlighted")
        rdp.keyboard.press('Enter')
        time.sleep(6)
        ss(rdp, "22_renovacoes_tela")
        time.sleep(3)
        ss(rdp, "23_renovacoes_tela2")

        # Tenta ver os campos disponíveis
        time.sleep(2)
        ss(rdp, "24_renovacoes_campos")
        press_escape_and_wait(rdp, 2)

        # === STEP 9: Movimentos > Parcelas e Comissões ===
        print("\n💰 Movimentos > Parcelas e Comissões...")
        rdp.keyboard.press('Alt+m')
        time.sleep(2)
        for i in range(5):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "25_parcelas_comissoes")
        press_escape_and_wait(rdp, 2)

        # === STEP 10: Consultas ===
        print("\n🔍 Consultas...")
        rdp.keyboard.press('Alt+c')
        time.sleep(2)
        ss(rdp, "30_consultas_menu")

        # Gerenciador de Relatórios
        for i in range(4):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "31_gerenciador_relatorios")
        press_escape_and_wait(rdp, 2)

        # Gráficos
        rdp.keyboard.press('Alt+c')
        time.sleep(2)
        for i in range(5):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "32_graficos_analise")
        press_escape_and_wait(rdp, 2)

        # === STEP 11: Ferramentas > Exportação de Dados ===
        print("\n📤 Ferramentas > Exportação...")
        rdp.keyboard.press('Alt+f')
        time.sleep(2)
        ss(rdp, "40_ferramentas_menu")
        press_escape_and_wait(rdp)

        rdp.keyboard.press('Alt+f')
        time.sleep(2)
        # 8 ArrowDown = Exportação de Dados
        for i in range(8):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('ArrowRight')
        time.sleep(2)
        ss(rdp, "41_exportacao_submenu")

        # Captura cada item do submenu
        for i in range(5):
            ss(rdp, f"42_export_item_{i}")
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.4)

        # Volta e abre o primeiro item
        for i in range(5):
            rdp.keyboard.press('ArrowUp')
            time.sleep(0.2)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "43_export_itens_tela")
        time.sleep(3)
        ss(rdp, "44_export_itens_campos")
        press_escape_and_wait(rdp, 2)

        # Abre segundo item (Clientes e Documentos)
        rdp.keyboard.press('Alt+f')
        time.sleep(1.5)
        for i in range(8):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.2)
        rdp.keyboard.press('ArrowRight')
        time.sleep(1.5)
        rdp.keyboard.press('ArrowDown')
        time.sleep(0.3)
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "45_export_clientes_tela")
        press_escape_and_wait(rdp, 2)

        print("\n" + "=" * 60)
        print("✅ Mapeamento completo!")
        print(f"📁 Screenshots salvos em: {DIR}")
        print("=" * 60)

        browser.close()

    print("\nLista de screenshots:")
    for f in sorted(os.listdir(DIR)):
        if f.endswith('.png'):
            print(f"  {f}")

if __name__ == "__main__":
    main()
