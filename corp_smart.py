"""
Corp — Login inteligente.
1. Descobre posição dos campos via análise de pixels do canvas
2. OU usa inputs HTML ocultos do TSplus
3. OU usa API JavaScript do TSplus
"""

from playwright.sync_api import sync_playwright
import time
import os

DIR = "/root/sierra/corp_smart"
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
        # FASE 1: Investiga a página RDP
        # ========================================
        
        # Descobre TUDO sobre a página
        page_info = rdp.evaluate("""() => {
            const result = {};
            
            // Inputs
            const inputs = document.querySelectorAll('input');
            result.inputs = Array.from(inputs).map((inp, i) => ({
                index: i,
                id: inp.id,
                name: inp.name,
                type: inp.type,
                className: inp.className,
                value: inp.value,
                rect: JSON.parse(JSON.stringify(inp.getBoundingClientRect())),
                style_display: inp.style.display,
                style_visibility: inp.style.visibility,
                style_position: inp.style.position,
                tabIndex: inp.tabIndex
            }));
            
            // Canvas
            const canvas = document.querySelector('canvas');
            result.canvas = canvas ? {
                id: canvas.id, 
                width: canvas.width, 
                height: canvas.height,
                rect: JSON.parse(JSON.stringify(canvas.getBoundingClientRect()))
            } : null;
            
            // Global TSplus/JWTS objects
            result.globals = {
                hasJWTS: typeof JWTS !== 'undefined',
                hasW: typeof W !== 'undefined',
            };
            
            try {
                if (typeof JWTS !== 'undefined') {
                    result.jwts_keys = Object.keys(JWTS).slice(0, 50);
                }
            } catch(e) { result.jwts_error = e.message; }
            
            // All global functions/objects with "key" or "input" or "mouse" in name
            result.related_globals = [];
            for (let key in window) {
                const lk = key.toLowerCase();
                if (lk.includes('key') || lk.includes('input') || lk.includes('mouse') || 
                    lk.includes('send') || lk.includes('click') || lk.includes('type')) {
                    try {
                        result.related_globals.push({name: key, type: typeof window[key]});
                    } catch(e) {}
                }
            }
            
            return result;
        }""")
        
        print(f"\n=== INPUTS ({len(page_info.get('inputs', []))}) ===")
        for inp in page_info.get('inputs', []):
            print(f"  [{inp['index']}] id={inp['id']} name={inp['name']} type={inp['type']} "
                  f"class={inp['className'][:50]} rect=({inp['rect']['x']:.0f},{inp['rect']['y']:.0f},"
                  f"{inp['rect']['width']:.0f}x{inp['rect']['height']:.0f}) "
                  f"display={inp['style_display']} vis={inp['style_visibility']} pos={inp['style_position']}")
        
        print(f"\n=== CANVAS ===")
        print(f"  {page_info.get('canvas')}")
        
        print(f"\n=== GLOBALS ===")
        print(f"  JWTS exists: {page_info['globals']['hasJWTS']}")
        if 'jwts_keys' in page_info:
            print(f"  JWTS keys: {page_info['jwts_keys']}")
        
        print(f"\n=== RELATED GLOBALS ===")
        for g in page_info.get('related_globals', [])[:20]:
            print(f"  {g['name']}: {g['type']}")
        
        # ========================================
        # FASE 2: Tenta usar inputs HTML
        # ========================================
        inputs = page_info.get('inputs', [])
        if inputs:
            print(f"\n=== Tentando inputs HTML ===")
            for inp in inputs:
                print(f"  Input: id={inp['id']}, visible at ({inp['rect']['x']}, {inp['rect']['y']})")
        
        # ========================================
        # FASE 3: Analisa pixels do canvas pra achar campos brancos
        # ========================================
        print("\n=== Analisando pixels do canvas ===")
        field_positions = rdp.evaluate("""() => {
            const canvas = document.querySelector('#JWTS_myCanvas') || document.querySelector('canvas');
            if (!canvas) return null;
            const ctx = canvas.getContext('2d');
            if (!ctx) return {error: 'no 2d context'};
            
            // Procura linhas horizontais de pixels brancos (campos de input)
            // Campos são retângulos brancos (~RGB 255,255,255) na área central
            const results = [];
            const w = canvas.width;
            const h = canvas.height;
            
            // Varre a coluna x=700 (meio dos campos) de cima pra baixo
            for (let y = 200; y < 600; y++) {
                const pixel = ctx.getImageData(700, y, 1, 1).data;
                const isWhite = pixel[0] > 240 && pixel[1] > 240 && pixel[2] > 240;
                if (isWhite) {
                    // Verifica se é início de um campo (pixel anterior não era branco)
                    const prevPixel = ctx.getImageData(700, y-1, 1, 1).data;
                    const prevWhite = prevPixel[0] > 240 && prevPixel[1] > 240 && prevPixel[2] > 240;
                    if (!prevWhite) {
                        // Encontra fim do campo
                        let endY = y;
                        while (endY < 600) {
                            const p = ctx.getImageData(700, endY, 1, 1).data;
                            if (p[0] <= 240 || p[1] <= 240 || p[2] <= 240) break;
                            endY++;
                        }
                        results.push({startY: y, endY: endY, height: endY - y, centerY: Math.round((y + endY) / 2)});
                        y = endY; // Pula pro próximo
                    }
                }
            }
            
            return results;
        }""")
        
        print(f"Campos brancos encontrados: {field_positions}")
        
        if field_positions and len(field_positions) >= 2:
            # Encontrou os campos! Usa as coordenadas reais
            user_field = field_positions[0]  # Primeiro campo branco = Usuário
            pass_field = field_positions[1]  # Segundo = Senha
            
            print(f"\n🎯 Campo Usuário: y={user_field['centerY']} (h={user_field['height']})")
            print(f"🎯 Campo Senha: y={pass_field['centerY']} (h={pass_field['height']})")
            
            # Login com coordenadas EXATAS
            rdp.mouse.click(700, user_field['centerY'], click_count=3)
            time.sleep(1)
            rdp.keyboard.type('AMANDA', delay=80)
            time.sleep(1)
            ss(rdp, "01_usuario")
            
            rdp.mouse.click(700, pass_field['centerY'], click_count=3)
            time.sleep(1)
            rdp.keyboard.type('amanda001', delay=80)
            time.sleep(1)
            ss(rdp, "02_senha")
            
            rdp.keyboard.press('Enter')
            print("✅ Login enviado (pixel detection)")
            time.sleep(25)
            ss(rdp, "03_resultado")
        else:
            print("⚠️ Não encontrou campos via pixels, tentando approach JWTS")
            # Tenta JWTS API se existir
            if page_info['globals']['hasJWTS']:
                print("Tentando JWTS API...")
                # Tenta enviar keypresses via JWTS
                rdp.evaluate("""() => {
                    // Tenta diversas APIs JWTS conhecidas
                    if (typeof JWTS !== 'undefined') {
                        if (JWTS.sendKey) JWTS.sendKey('Tab');
                        if (JWTS.sendText) JWTS.sendText('AMANDA');
                    }
                }""")
            
            # Fallback: tenta com coordenadas que funcionaram antes
            print("Fallback: coords do corp_fix (y=463/y=430)")
            rdp.mouse.click(725, 463, click_count=3)
            time.sleep(1)
            rdp.keyboard.type('AMANDA', delay=80)
            time.sleep(1)
            
            rdp.mouse.click(725, 430, click_count=3)
            time.sleep(1)
            rdp.keyboard.type('amanda001', delay=80)
            time.sleep(1)
            
            rdp.keyboard.press('Enter')
            print("✅ Login enviado (fallback)")
            time.sleep(25)
            ss(rdp, "03_resultado")
        
        # Verifica se logou
        rdp.keyboard.press('Alt+a')
        time.sleep(2)
        ss(rdp, "04_teste_menu")
        rdp.keyboard.press('Escape')
        time.sleep(1)
        
        # Se logou, explora exportação
        print("\n=== Ferramentas > Exportação ===")
        
        # Exportação de Itens
        rdp.keyboard.press('Alt+f')
        time.sleep(2)
        for i in range(8):
            rdp.keyboard.press('ArrowDown')
            time.sleep(0.3)
        rdp.keyboard.press('ArrowRight')
        time.sleep(2)
        ss(rdp, "10_export_sub")
        rdp.keyboard.press('Enter')
        time.sleep(5)
        ss(rdp, "11_export_itens")
        
        # Fecha e abre Clientes e Documentos
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
        ss(rdp, "12_export_clientes")
        
        # Gerenciador de Relatórios
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
