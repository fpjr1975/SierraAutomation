"""
Corp — Login via JavaScript canvas events diretos.
Envia mousedown/mouseup diretamente no canvas com coordenadas corretas.
"""

from playwright.sync_api import sync_playwright
import time
import os

DIR = "/root/sierra/corp_js"
os.makedirs(DIR, exist_ok=True)

def ss(page, name):
    path = f"{DIR}/{name}.jpg"
    page.screenshot(path=path, quality=90, type="jpeg")
    print(f"📸 {name}")

def canvas_click(rdp, x, y):
    """Envia click via JavaScript diretamente no canvas."""
    rdp.evaluate(f"""() => {{
        const canvas = document.querySelector('#JWTS_myCanvas') || document.querySelector('canvas');
        if (!canvas) return;
        const rect = canvas.getBoundingClientRect();
        const evt_down = new MouseEvent('mousedown', {{
            clientX: rect.left + {x}, clientY: rect.top + {y},
            bubbles: true, cancelable: true, button: 0
        }});
        const evt_up = new MouseEvent('mouseup', {{
            clientX: rect.left + {x}, clientY: rect.top + {y},
            bubbles: true, cancelable: true, button: 0
        }});
        const evt_click = new MouseEvent('click', {{
            clientX: rect.left + {x}, clientY: rect.top + {y},
            bubbles: true, cancelable: true, button: 0
        }});
        canvas.dispatchEvent(evt_down);
        canvas.dispatchEvent(evt_up);
        canvas.dispatchEvent(evt_click);
    }}""")

def canvas_key(rdp, key, code=''):
    """Envia keydown/keypress/keyup via JavaScript."""
    if not code:
        code = f'Key{key.upper()}' if len(key) == 1 and key.isalpha() else key
    rdp.evaluate(f"""() => {{
        const canvas = document.querySelector('#JWTS_myCanvas') || document.querySelector('canvas');
        if (!canvas) return;
        const opts = {{ key: '{key}', code: '{code}', bubbles: true, cancelable: true }};
        canvas.dispatchEvent(new KeyboardEvent('keydown', opts));
        canvas.dispatchEvent(new KeyboardEvent('keypress', opts));
        canvas.dispatchEvent(new KeyboardEvent('keyup', opts));
    }}""")

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
        
        # Analisa a estrutura da página RDP
        info = rdp.evaluate("""() => {
            const canvas = document.querySelector('#JWTS_myCanvas') || document.querySelector('canvas');
            const all_canvas = document.querySelectorAll('canvas');
            const inputs = document.querySelectorAll('input');
            const iframes = document.querySelectorAll('iframe');
            return {
                canvas: canvas ? {id: canvas.id, w: canvas.width, h: canvas.height, 
                    rect: JSON.parse(JSON.stringify(canvas.getBoundingClientRect()))} : null,
                all_canvas_count: all_canvas.length,
                input_count: inputs.length,
                iframe_count: iframes.length,
                body_scroll: {top: document.body.scrollTop, left: document.body.scrollLeft},
                url: window.location.href,
                title: document.title,
                // Procura por qualquer div/toolbar TSplus acima do canvas
                toolbar_height: (() => {
                    const tb = document.querySelector('.toolbar') || document.querySelector('#toolbar') 
                        || document.querySelector('[class*="toolbar"]') || document.querySelector('[id*="toolbar"]');
                    return tb ? JSON.parse(JSON.stringify(tb.getBoundingClientRect())) : null;
                })()
            };
        }""")
        print(f"Page info: {info}")
        ss(rdp, "00_rdp")
        
        # Tenta abordagem híbrida: Playwright mouse.click + posições variadas
        # Primeiro, descobre se há offset do canvas
        canvas_rect = info.get('canvas', {}).get('rect', {})
        canvas_top = canvas_rect.get('top', 0)
        canvas_left = canvas_rect.get('left', 0)
        print(f"Canvas top={canvas_top}, left={canvas_left}")
        
        # Se o canvas tem offset, preciso ajustar as coordenadas
        # Campo usuario: ~y=430 relativo ao canvas
        # Campo senha: ~y=460 relativo ao canvas
        
        # Mas com Playwright mouse.click, as coords são relativas ao viewport
        # Se canvas.top > 0, preciso adicionar esse offset
        
        OFFSET_Y = canvas_top
        OFFSET_X = canvas_left
        
        # Abordagem 1: Focus no campo usuario com coordenadas ajustadas
        user_y = 430 + OFFSET_Y
        pass_y = 463 + OFFSET_Y  # 33px abaixo baseado no screenshot
        enter_y = 495 + OFFSET_Y
        field_x = 725 + OFFSET_X
        
        print(f"\nCoords ajustadas: user_y={user_y}, pass_y={pass_y}, enter_y={enter_y}")
        
        # Click triplo no campo usuario
        rdp.mouse.click(field_x, user_y, click_count=3)
        time.sleep(1)
        rdp.keyboard.type('AMANDA', delay=80)
        time.sleep(1)
        ss(rdp, "01_usuario")
        
        # Click no campo SENHA - coordenada ajustada
        rdp.mouse.click(field_x, pass_y, click_count=3)
        time.sleep(1)
        rdp.keyboard.type('amanda001', delay=80)
        time.sleep(1)
        ss(rdp, "02_senha")
        
        # Enter
        rdp.keyboard.press('Enter')
        print("✅ Login tentativa 1")
        time.sleep(22)
        ss(rdp, "03_resultado1")
        
        # Se falhou, tenta com JavaScript canvas events
        rdp.mouse.click(600, 457 + OFFSET_Y)  # OK do erro
        time.sleep(2)
        
        print("\n=== Tentativa 2: JS canvas events ===")
        # JS click no campo usuario
        canvas_click(rdp, 725, 430)
        time.sleep(1)
        rdp.keyboard.press('Control+a')
        rdp.keyboard.type('AMANDA', delay=80)
        time.sleep(1)
        
        # JS click no campo senha
        canvas_click(rdp, 725, 463)
        time.sleep(1)
        rdp.keyboard.press('Control+a')
        rdp.keyboard.type('amanda001', delay=80)
        time.sleep(1)
        ss(rdp, "04_js_preenchido")
        
        # JS click em Entrar
        canvas_click(rdp, 725, 495)
        time.sleep(2)
        rdp.keyboard.press('Enter')
        print("✅ Login tentativa 2 (JS)")
        time.sleep(22)
        ss(rdp, "05_js_resultado")
        
        # Se falhou, tenta focusando canvas primeiro
        rdp.mouse.click(600, 457 + OFFSET_Y)
        time.sleep(2)
        
        print("\n=== Tentativa 3: Focus canvas + type AMANDA Tab amanda001 ===")
        # Foca o canvas clicando nele
        rdp.evaluate("""() => {
            const canvas = document.querySelector('#JWTS_myCanvas') || document.querySelector('canvas');
            if (canvas) canvas.focus();
        }""")
        time.sleep(1)
        
        # Click no centro da tela e depois nos campos
        rdp.mouse.click(640, 450)
        time.sleep(1)
        
        # Campo usuario
        rdp.mouse.click(field_x, user_y, click_count=3)
        time.sleep(1)
        rdp.keyboard.type('AMANDA', delay=100)
        time.sleep(2)
        
        # Tenta TAB com delay longo
        rdp.keyboard.press('Tab')
        time.sleep(3)
        
        rdp.keyboard.type('amanda001', delay=100)
        time.sleep(1)
        ss(rdp, "06_tab_preenchido")
        
        rdp.keyboard.press('Enter')
        print("✅ Login tentativa 3 (Tab longo)")
        time.sleep(22)
        ss(rdp, "07_tab_resultado")
        
        # Testa menu
        rdp.keyboard.press('Alt+a')
        time.sleep(2)
        ss(rdp, "08_teste_menu")
        rdp.keyboard.press('Escape')
        
        # Explora menus se logou
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
        
        # Cada item
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
        
        print("\n✅ Concluído!")
        browser.close()

if __name__ == "__main__":
    main()
