from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm
from utils import resource_path
import os
import re

class SierraPDFGeneratorV7:
    def __init__(self, data, output_path):
        self.data = data
        self.output_path = output_path
        self.width, self.height = A4
        self.margin = 30
        self.page_w = self.width - 2 * self.margin
        
        # --- FINTECH COLORS ---
        self.col_brand_bg = colors.HexColor("#0047AB")
        self.col_brand_dark = colors.HexColor("#002e70")
        self.col_accent = colors.HexColor("#00D4FF")
        self.col_paper_bg = colors.HexColor("#F5F7FA")
        self.col_card_bg = colors.white
        self.col_text_main = colors.HexColor("#1A1A1A")
        self.col_text_muted = colors.HexColor("#666666")
        self.col_price = colors.HexColor("#00C853")
        
        # Merge Guincho/Carro Reserva from assistencias into coberturas if missing
        if "coberturas" not in self.data: self.data["coberturas"] = []
        # Filter out Carta Verde entries (not relevant for output)
        self.data["coberturas"] = [(n, v) for n, v in self.data["coberturas"] if "carta verde" not in n.lower()]
        covs = self.data["coberturas"]
        assists = self.data.get("assistencias", [])
        
        has_guincho = any("guincho" in str(c[0]).lower() for c in covs)
        has_carro = any(x in str(c[0]).lower() for x in ["carro", "reserva"] for c in covs)
        
        for ast in assists:
            if not has_guincho and "guincho" in ast.lower():
                covs.append(("Guincho", ast))
                has_guincho = True
            elif not has_carro and "carro" in ast.lower():
                covs.append(("Carro Reserva", ast))
                has_carro = True

        # Third Party Detection (RCF Only)
        # Logic: Has RCF/Danos but NO Casco/Compreensiva
        self.is_third_party = False
        has_casco = False
        has_rcf = False
        for n, v in covs:
            n_lower = n.lower()
            v_lower = v.lower()
            if any(x in n_lower for x in ['casco', 'compreensiva', 'valor de mercado', 'colisão']):
                # "Casco Não contratada" or value "Não contratad" should NOT count
                if 'não contratad' not in n_lower and 'não contratad' not in v_lower:
                    has_casco = True
            if any(x in n_lower for x in ['danos', 'rcf', 'material', 'corporal']):
                has_rcf = True
        self.is_third_party = has_rcf and not has_casco
        
    def _draw_shadow_card(self, c, x, y, w, h, radius=10):
        c.saveState()
        c.setFillColor(colors.black)
        c.setFillAlpha(0.05)
        c.roundRect(x+2, y-2, w, h, radius, fill=1, stroke=0)
        c.roundRect(x+4, y-4, w, h, radius, fill=1, stroke=0)
        c.setFillAlpha(1)
        c.setFillColor(self.col_card_bg)
        c.roundRect(x, y, w, h, radius, fill=1, stroke=0)
        c.restoreState()

    def generate(self):
        c = canvas.Canvas(self.output_path, pagesize=A4)
        c.setTitle(f"Proposta Digital - {self.data.get('segurado', 'Cliente')}")

        # PAGE 1 (Fixed Layout)
        self._draw_background(c)
        self.draw_page_1_header(c)
        self.draw_page_1_content(c)

        if self.is_third_party:
            # Single-page layout for Terceiros
            # self.curr_y was set by draw_page_1_content()
            self.draw_section_dados(c)
            self.draw_section_coberturas(c)
            self._draw_price_card(c, self.curr_y)
            self.draw_section_obs(c)
            self._draw_footer_branding(c)
        else:
            # Standard 2-page layout for Compreensiva
            self._draw_footer_branding(c)
            c.showPage()

            # PAGE 2+ (Flow Layout)
            self._draw_background(c)
            self.draw_page_2_header(c)

            # Init cursor for Page 2
            self.curr_y = self.height - 100

            # Draw Sections with Flow Check
            self.draw_section_dados(c)
            self.draw_section_coberturas(c)
            self.draw_section_franquias(c)
            self.draw_section_obs(c)

            self._draw_footer_branding(c)
        c.save()

    def _draw_background(self, c):
        c.setFillColor(self.col_paper_bg)
        c.rect(0, 0, self.width, self.height, fill=1, stroke=0)

    def _draw_footer_branding(self, c):
        c.saveState()
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.gray)
        c.drawCentredString(self.width/2, 30, "Sierra Corretora - Orçamento Digital Inteligente")
        c.restoreState()
        
    def _check_space(self, c, height_needed):
        """ Checks if space is available, else new page """
        bottom_limit = 50 # Space for footer
        if self.curr_y - height_needed < bottom_limit:
            self._draw_footer_branding(c)
            c.showPage()
            self._draw_background(c)
            self.draw_page_2_header(c)
            self.curr_y = self.height - 100

    # --- PAGE 1 ---
    def draw_page_1_header(self, c):
        h_header = 180
        # Bezier Curve for "Soft" feel
        c.saveState()
        
        # Back Wave
        c.setFillColor(self.col_brand_dark)
        p = c.beginPath()
        p.moveTo(0, self.height)
        p.lineTo(self.width, self.height)
        p.lineTo(self.width, self.height - h_header + 20)
        p.curveTo(self.width * 0.6, self.height - h_header - 20, 
                  self.width * 0.3, self.height - h_header + 40,
                  0, self.height - h_header + 10)
        p.lineTo(0, self.height)
        p.close()
        c.drawPath(p, fill=1, stroke=0)
        
        # Front Wave (Main)
        c.setFillColor(self.col_brand_bg)
        p = c.beginPath()
        p.moveTo(0, self.height)
        p.lineTo(self.width, self.height)
        p.lineTo(self.width, self.height - h_header + 40) 
        p.curveTo(self.width * 0.7, self.height - h_header - 10,
                  self.width * 0.3, self.height - h_header + 50,
                  0, self.height - h_header)
        p.lineTo(0, self.height)
        p.close()
        c.drawPath(p, fill=1, stroke=0)
        
        # Logo Area
        logo_path = resource_path("logo.png")
        if os.path.exists(logo_path):
             # Solid White Circle Backdrop (Classic & Clean)
             c.setFillColor(colors.white)
             c.circle(60, self.height - 50, 35, fill=1, stroke=0)
             
             # Logo (Centered)
             c.drawImage(logo_path, 35, self.height - 70, width=50, height=40, preserveAspectRatio=True, mask='auto')
             
        # Greeting
        segurado_raw = str(self.data.get('segurado', 'Você'))
        
        # Clean PJ suffixes for greeting
        name_clean = segurado_raw.upper()
        pj_suffixes = [r'\bLTDA\b', r'\bS/A\b', r'\bS\.A\.\b', r'\bME\b', r'\bEPP\b', r'\bSA\b']
        is_pj = False
        for suffix in pj_suffixes:
            if re.search(suffix, name_clean):
                name_clean = re.sub(suffix, '', name_clean)
                is_pj = True
        name_clean = name_clean.strip()

        if is_pj:
            # For PJ, use the cleaned name
            segurado = name_clean.title()
        else:
            # For PF, keep just the first name
            segurado = name_clean.split()[0].title() if name_clean else "Você"
        
        # Position Greeting relative to curve
        text_x = 105
        text_y = self.height - 55
        
        c.setFont("Helvetica-Bold", 20) 
        c.setFillColor(colors.white)
        c.drawString(text_x, text_y, f"Olá, {segurado}")
        
        c.setFont("Helvetica", 11)
        c.setFillColor(self.col_accent) 
        c.drawString(text_x, text_y - 18, "Aqui está seu orçamento personalizado.")
        
        c.restoreState()

    def draw_page_1_content(self, c):
        start_y = self.height - 140
        margin = self.margin
        page_w = self.page_w
        
        # CARD 1: VEICULO
        card_h = 80 if self.is_third_party else 100
        self._draw_shadow_card(c, margin, start_y - card_h, page_w, card_h)
        
        c.saveState()
        veiculo = self.data.get('veiculo', 'Veículo')
        placa = self.data.get('placa', '---')
        # Vertically center content in card (3 lines: title 14pt, veiculo 16pt, placa 10pt ≈ 50pt total)
        content_h = 50
        top_pad = (card_h - content_h) / 2
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(self.col_brand_bg)
        c.drawString(margin + 20, start_y - top_pad - 12, "Seu Carro")
        # Dynamic font size based on vehicle name length
        veiculo_font = 14 if len(veiculo) > 40 else (15 if len(veiculo) > 30 else 16)
        c.setFont("Helvetica", veiculo_font)
        c.setFillColor(self.col_text_main)
        c.drawString(margin + 20, start_y - top_pad - 32, veiculo)
        c.setFont("Helvetica", 10)
        c.setFillColor(self.col_text_muted)
        c.drawString(margin + 20, start_y - top_pad - 48, f"Placa: {placa}  |  Vigência: {self.data.get('vigencia','')}")

        insurer = self.data.get('insurer', '')
        if insurer:
            found = self._find_logo(insurer)
            if found:
                 c.drawImage(found, self.width - margin - 80, start_y - top_pad - 40, width=60, height=30, preserveAspectRatio=True, mask='auto', anchor='e')
        c.restoreState()

        gap_after_vehicle = 10 if self.is_third_party else 20
        curr_y = start_y - card_h - gap_after_vehicle

        # CARD 3: PROTECOES GRID
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(self.col_text_muted)
        
        covs = self.data.get('coberturas', [])
        
        suffix = self.data.get('titulo_inclusos_suffix', '')
        title_inclusos = "Seu carro protegido. Sem complicação." + suffix
        # Normalize check to avoid duplicates with different spacing (e.g. "( Seguro Terceiros )" vs "(Seguro Terceiros)")
        if self.is_third_party and "SEGURO TERCEIROS" not in title_inclusos.upper():
            title_inclusos += " (Seguro Terceiros)"
            
        c.drawString(margin + 5, curr_y - 5, title_inclusos)
        curr_y -= 15
        
        fipe = self.data.get('fipe_custom') or "100% FIPE"
        danos = "R$ 0"
        guincho = "Guincho N/D"
        carro = "Não contratado"
        
        def parse_currency(s):
            """Extract numeric value from currency string like 'R$ 400.000,00'"""
            m = re.search(r'[\d\.\,]+', s.replace(' ', ''))
            if m:
                return float(m.group(0).replace('.', '').replace(',', '.'))
            return 0.0

        for n, v in covs:
            if 'fipe' in v.lower(): fipe = v
            if 'materiais' in n.lower():
                if parse_currency(v) > parse_currency(danos):
                    danos = v
            
            # Extract Guincho/Carro from Coberturas if present (Common in HDI/Azul/Porto)
            # Use robust regex for Guincho/Assistência
            if re.search(r'GUINCHO|ASSIST[E\xC0-\xFF]NCIA', n, re.I):
                guincho = v
            
            if 'carro' in n.lower() or 'reserva' in n.lower():
                carro = v
                
        # Also check separate 'assistencias' list (used by some extractors)
        # Only overwrite if we didn't find anything in Coberturas
        assists = self.data.get('assistencias', [])
        for a in assists:
            if re.search(r'GUINCHO|SOCORRO|REBOQUE|ITA[UÚ].*?KM|ITA[UÚ]\s+ESSENCIAL|ASSIST[E\xC0-\xFF]NCIA', a, re.I) and 'carta verde' not in a.lower() and (guincho == "Guincho N/D" or guincho == "N/D"): 
                 guincho = a
            if 'carro' in a.lower() and (carro == "Não contratado" or carro == "N/D"):
                 carro = a
            
        # Find Franquia Casco
        franquia_casco = "R$ 0,00"
        # Try to find in list
        for f in self.data.get('franquias_lista', []):
            if 'Casco' in f or 'Basica' in f or 'Básica' in f:
                # Extract just the value if possible "Casco: R$ 1000"
                parts = f.split('R$')
                if len(parts) > 1:
                    val_f = parts[1].strip()
                    franquia_casco = f"R$ {val_f}"
                    
                    # Check for Reduzida tag in the label part
                    if "Reduzida" in parts[0]:
                        # Try to extract the full tag like "(50% Reduzida)"
                        tag_match = re.search(r'(\(.*?\))', parts[0])
                        if tag_match:
                             franquia_casco += f" {tag_match.group(1)}"
                        else:
                             franquia_casco += " (Reduzida)"
                else:
                    franquia_casco = f
                break
        if franquia_casco == "R$ 0,00" and self.data.get('franquia'):
             franquia_casco = self.data.get('franquia')

        # Young Driver
        # Seguradoras que não trabalham com cobertura 18/25
        insurer_code = self.data.get('insurer', '').upper()
        no_young_driver_insurers = ['AZUL', 'ITAU', 'PORTO', 'POR']
        if any(x in insurer_code for x in no_young_driver_insurers):
            young_driver = "N/D"
        else:
            young_driver = self.data.get('condutor_jovem', 'Não')
            # Fallback: Check in Coberturas list if not explicitly set
            if young_driver in ["N/D", "Não"]:
                 for name, val in self.data.get('coberturas', []):
                      if "18" in name and "25" in name:
                           if val.lower().startswith("sim") or val.lower() == "contratado":
                                young_driver = "Sim"
                                break
                      if "Jovem" in name and "Condutor" in name:
                           if val.lower().startswith("sim"):
                                young_driver = "Sim"
                                break

        # --- Force "Não contratado" for Third Party ---
        if self.is_third_party:
            fipe = "Não contratado"
            franquia_casco = "Não contratado"
            carro = "Não contratado"

        # Helper to format Guincho for Page 1 display
        def format_guincho(g_val):
            # If "N/D", return as is (but avoid Guincho Guincho N/D)
            if "N/D" in g_val.upper(): return "N/D"
            
            # Check for "Ilimitado" anywhere in the value
            # This handles both simple "Ilimitado" and "800km p/ Pane + Ilimitado p/ Sinistro"
            if "ilimitado" in g_val.lower():
                return "Ilimitado"
            
            # Remove "Guincho" label for cleanliness
            clean_g = g_val.lower().replace("guincho", "").strip()
            
            # Match 400 KM or similar (handles KM, K.M., km)
            km_match = re.search(r'(\d+)\s*k\.?m\.?', clean_g)
            if km_match:
                return f"{km_match.group(1)} KM"
            
            # If contains numbers, assume it's the distance
            if any(c.isdigit() for c in clean_g):
                # Try to clean it up (e.g. "200" -> "200 Km")
                # But be careful of "24 horas"
                # Let's take the safe route: return cleaned string title cased
                return clean_g.title() + (" Km" if "km" not in clean_g.lower() else "")
            
            # Fallback: return original (cleaned)
            return clean_g.title() if clean_g else g_val

        items = [
            ("FIPE", fipe, self.col_text_muted if fipe == "Não contratado" else None),
            ("Danos 3º", danos, None),
            ("Guincho", format_guincho(guincho), None),
            ("Reserva", carro, self.col_text_muted if carro == "Não contratado" else None),
            ("Franquia - Casco", franquia_casco, self.col_text_muted if franquia_casco == "Não contratado" else self.col_price), # Green
            ("Cobertura 18/25", young_driver, None)
        ]

        col_gap = 10

        if self.is_third_party:
            # Terceiros: 1 row × 3 cols (only relevant items)
            grid_h = 80
            grid_w = (page_w - 2 * col_gap) / 3
            self._draw_mini_card(c, margin, curr_y - grid_h, grid_w, grid_h, "danos.png", items[1][0], items[1][1])
            self._draw_mini_card(c, margin + grid_w + col_gap, curr_y - grid_h, grid_w, grid_h, "guincho.png", items[2][0], items[2][1])
            self._draw_mini_card(c, margin + 2*(grid_w + col_gap), curr_y - grid_h, grid_w, grid_h, "condutor.png", items[5][0], items[5][1])
            curr_y = curr_y - grid_h - 15
        else:
            # Compreensiva: 3 rows × 2 cols (all 6 items)
            grid_h = 100
            grid_w = (page_w - col_gap) / 2

            # Row 1
            self._draw_mini_card(c, margin, curr_y - grid_h, grid_w, grid_h, "franquia.png", items[0][0], items[0][1])
            self._draw_mini_card(c, margin + grid_w + col_gap, curr_y - grid_h, grid_w, grid_h, "danos.png", items[1][0], items[1][1])
            curr_y -= (grid_h + 10)

            # Row 2
            self._draw_mini_card(c, margin, curr_y - grid_h, grid_w, grid_h, "guincho.png", items[2][0], items[2][1])
            self._draw_mini_card(c, margin + grid_w + col_gap, curr_y - grid_h, grid_w, grid_h, "reserva.png", items[3][0], items[3][1])
            curr_y -= (grid_h + 10)

            # Row 3
            self._draw_mini_card(c, margin, curr_y - grid_h, grid_w, grid_h, "franquia.png", items[4][0], items[4][1], items[4][2])
            self._draw_mini_card(c, margin + grid_w + col_gap, curr_y - grid_h, grid_w, grid_h, "condutor.png", items[5][0], items[5][1])
            curr_y = curr_y - grid_h - 20
        
        if self.is_third_party:
            # For terceiros, price card is drawn later (after coberturas)
            self.curr_y = curr_y
        else:
            # CARD 2: PREÇO (compreensiva only - drawn inline on page 1)
            self._draw_price_card(c, curr_y, margin, page_w)

    def _draw_price_card(self, c, curr_y, margin=None, page_w=None):
        if margin is None:
            margin = self.margin
        if page_w is None:
            page_w = self.page_w
        price_h = 100 if self.is_third_party else 160
        self._draw_shadow_card(c, margin, curr_y - price_h, page_w, price_h)

        opts = self.data.get('pagamento_opcoes', [])
        vista = "R$ 0,00"
        best_credit = None
        max_credit_p = 0
        best_debit = None
        max_debit_p = 0

        for p in opts:
            tipo = p.get('tipo', '').lower()
            val_p = 0
            try:
                raw_p = str(p.get('parcelas', '0')).lower().replace('x', '').strip()
                val_p = int(raw_p)
            except: pass
            if 'vista' in tipo or val_p == 1:
                if "antecipado" not in tipo:
                     vista = p.get('valor', '')
                continue
            if val_p > 1:
                is_debit = 'débito' in tipo or 'debito' in tipo or 'boleto' in tipo
                if is_debit:
                    if val_p > max_debit_p:
                        max_debit_p = val_p
                        best_debit = p
                else:
                    if val_p > max_credit_p:
                        max_credit_p = val_p
                        best_credit = p

        credit_txt = ""
        if best_credit:
             credit_txt = f"parcelado em {best_credit.get('parcelas')} de {best_credit.get('valor')} sem juros no cartão de crédito"
        else:
             credit_txt = "Consulte condições no cartão de crédito"

        debit_txt = ""
        antecipado_txt = ""
        for p in opts:
             if p.get('tipo') == "Débito Antecipado":
                  val = p.get('valor', '')
                  date = p.get('validade', '')
                  antecipado_txt = f"Débito antecipado {val}, pagando até {date}"
        if best_debit:
             debit_txt = f"ou parcelado em {best_debit.get('parcelas')} de {best_debit.get('valor')} sem juros com débito em conta corrente"

        ins_u = self.data.get('insurer', '').upper()
        is_porto_group = any(x in ins_u for x in ['ITAU', 'ITAÚ', 'PORTO', 'AZUL', 'MITSUI'])
        if is_porto_group:
             if self.data.get('premio_total'):
                  vista = self.data.get('premio_total')
             vista_label = ""
        else:
             vista_label = ""

        c.saveState()
        if self.is_third_party:
            c.setFont("Helvetica", 9)
            c.setFillColor(self.col_text_muted)
            c.drawCentredString(self.width/2, curr_y - 20, "INVESTIMENTO ANUAL")
            c.setFont("Helvetica-Bold", 28)
            c.setFillColor(self.col_price)
            c.drawCentredString(self.width/2, curr_y - 48, vista)
            c.setStrokeColor(colors.HexColor("#eeeeee"))
            c.line(margin+20, curr_y - 60, self.width - margin - 20, curr_y - 60)
            next_y = curr_y - 75
        else:
            c.setFont("Helvetica", 10)
            c.setFillColor(self.col_text_muted)
            c.drawCentredString(self.width/2, curr_y - 30, "INVESTIMENTO ANUAL")
            c.setFont("Helvetica-Bold", 32)
            c.setFillColor(self.col_price)
            c.drawCentredString(self.width/2, curr_y - 65, vista)
            c.setFont("Helvetica", 12)
            c.setFillColor(self.col_text_main)
            c.drawCentredString(self.width/2, curr_y - 85, vista_label)
            c.setStrokeColor(colors.HexColor("#eeeeee"))
            c.line(margin+20, curr_y - 100, self.width - margin - 20, curr_y - 100)
            next_y = curr_y - 118

        if antecipado_txt:
             c.setFont("Helvetica-Bold", 11)
             c.setFillColor(self.col_price)
             c.drawCentredString(self.width/2, next_y, antecipado_txt)
             next_y -= 15

        c.setFont("Helvetica", 11)
        c.setFillColor(self.col_brand_bg)
        c.drawCentredString(self.width/2, next_y, credit_txt)
        next_y -= 15

        if debit_txt and "ZURICH" not in ins_u:
            c.setFont("Helvetica", 10)
            c.setFillColor(self.col_text_muted)
            c.drawCentredString(self.width/2, next_y, debit_txt)
        c.restoreState()

        self.curr_y = curr_y - price_h - (10 if self.is_third_party else 15)

    def _draw_mini_card(self, c, x, y, w, h, icon_name, title, val, val_color=None):
        self._draw_shadow_card(c, x, y, w, h, radius=12) 
        c.saveState()
        
        # Icon (Large, Left)
        icon_path = resource_path(f"icones/{icon_name}")
        
        # Icon Sizing - Normalize visual weight
        # 'danos', 'franquia', 'condutor' appear smaller, so we boost them considerably.
        # 'guincho', 'reserva' are naturally large/square.
        if icon_name in ['franquia.png', 'danos.png', 'condutor.png']:
            icon_size = 53  # Reduced by ~30% from 75
        else:
            icon_size = 50  # Standard
            
        icon_y = y + (h - icon_size) / 2
        
        if os.path.exists(icon_path):
            # Draw Image
            c.drawImage(icon_path, x + 10, icon_y, width=icon_size, height=icon_size, preserveAspectRatio=True, mask=None)
        else:
            c.setFont("Helvetica", 20)
            c.drawString(x + 25, y + (h/2) - 5, "?")
            
        # Text (Right of Icon)
        # Shift text further right to accommodate icon
        # Max icon width 53. 
        text_x = x + 10 + 53 + 10 
        text_center_y = y + (h/2)
        
        # Title
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(self.col_text_muted)
        c.drawString(text_x, text_center_y + 6, title.upper())
        
        # Value
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(val_color if val_color else self.col_text_main)
        c.drawString(text_x, text_center_y - 8, val[:30])
        
        c.restoreState()

    # --- PAGE 2 SECTIONS ---
    def draw_page_2_header(self, c):
        h_header = 80
        c.saveState()
        
        # Back Wave
        c.setFillColor(self.col_brand_dark)
        p = c.beginPath()
        p.moveTo(0, self.height)
        p.lineTo(self.width, self.height)
        p.lineTo(self.width, self.height - h_header + 10)
        p.curveTo(self.width * 0.6, self.height - h_header - 10, 
                  self.width * 0.3, self.height - h_header + 20,
                  0, self.height - h_header + 5)
        p.lineTo(0, self.height)
        p.close()
        c.drawPath(p, fill=1, stroke=0)
        
        # Main Wave
        c.setFillColor(self.col_brand_bg)
        p = c.beginPath()
        p.moveTo(0, self.height)
        p.lineTo(self.width, self.height)
        p.lineTo(self.width, self.height - h_header + 20)
        p.curveTo(self.width * 0.7, self.height - h_header - 5,
                  self.width * 0.3, self.height - h_header + 25,
                  0, self.height - h_header)
        p.lineTo(0, self.height)
        p.close()
        c.drawPath(p, fill=1, stroke=0)

        c.setFont("Helvetica-Bold", 16)
        c.setFillColor(colors.white)
        c.drawString(40, self.height - 50, "Detalhamento Completo")
        c.restoreState()

    def draw_section_dados(self, c):
        h_c = 100 if self.is_third_party else 120
        self._check_space(c, h_c)
        
        margin = self.margin
        page_w = self.page_w
        y = self.curr_y - h_c
        
        self._draw_shadow_card(c, margin, y, page_w, h_c)
        
        c.saveState()
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(self.col_brand_dark)
        c.drawString(margin + 20, self.curr_y - 30, "DADOS DA PROPOSTA")
        
        d = self.data
        infos = [
            ("Segurado", d.get('segurado', '')), ("Condutor", d.get('condutor', '')),
            ("Veículo", d.get('veiculo', '')), ("Uso", d.get('uso', '')),
            ("CEP", d.get('cep_pernoite', '')), ("Vigência", d.get('vigencia', ''))
        ]
        
        col_x = margin + 20
        row_y = self.curr_y - 50
        for i, (k, v) in enumerate(infos):
            x_pos = col_x if i % 2 == 0 else col_x + 230
            y_pos = row_y - (i//2 * 20)
            c.setFont("Helvetica", 9)
            c.setFillColor(self.col_text_muted)
            c.drawString(x_pos, y_pos, k + ":")
            c.setFont("Helvetica-Bold", 9)
            c.setFillColor(self.col_text_main)
            c.drawString(x_pos + 60, y_pos, v[:35])
        c.restoreState()

        self.curr_y -= (h_c + (10 if self.is_third_party else 15))

    def draw_section_coberturas(self, c):
        # Filter out Franquia entries - they belong in the Franquias section
        covs = [(n, v) for n, v in self.data.get('coberturas', []) if 'franquia' not in n.lower()]
        row_h = 16 if self.is_third_party else 20
        base_h = 45 if self.is_third_party else 80
        h_c = base_h + (len(covs) * row_h)
        
        # Check if HUUUGE. If so, we might need simple split?
        # For now, just page break whole block.
        # If block > page height, this will break (but unlikely for < 30 covs)
        self._check_space(c, h_c)
        
        margin = self.margin
        page_w = self.page_w
        y = self.curr_y - h_c
        
        self._draw_shadow_card(c, margin, y, page_w, h_c)
        
        c.saveState()
        cob_font = 9 if self.is_third_party else 10
        c.setFont("Helvetica-Bold", 11 if self.is_third_party else 12)
        c.setFillColor(self.col_brand_dark)
        c.drawString(margin + 20, self.curr_y - (18 if self.is_third_party else 25), "COBERTURAS E LIMITES")

        start_list_y = self.curr_y - (30 if self.is_third_party else 60)
        for i, (name, val) in enumerate(covs):
            y_line = start_list_y - (i * row_h)

            # --- Text Replacements ---
            if "Compreensiva" in val:
                val = val.replace("Compreensiva", "Proteção Full")
            if "Compreensiva" in name:
                name = name.replace("Compreensiva", "Proteção Full")

            rcf_pattern = r'\bR\.?C\.?F\.?\s*[-–— ]?\s*V?\.?\b\s*[-–—:]?\s*'
            val = re.sub(rcf_pattern, '', val, flags=re.I).strip()
            name = re.sub(rcf_pattern, '', name, flags=re.I).strip()

            if "APP" in val:
                val = val.replace("APP", "Proteção para Passageiros")
            if "APP" in name:
                name = name.replace("APP", "Proteção para Passageiros")
            # -------------------------

            c.setFillColor(self.col_accent)
            c.circle(margin + 25, y_line + 4, 3 if not self.is_third_party else 2, fill=1, stroke=0)

            c.setFont("Helvetica", cob_font)
            c.setFillColor(self.col_text_main)
            c.drawString(margin + 35, y_line, name)

            c.setFont("Helvetica-Bold", cob_font)
            if "franquia" in name.lower():
                 c.setFillColor(self.col_price)
            else:
                 c.setFillColor(self.col_brand_dark)
            c.drawRightString(self.width - margin - 25, y_line, val)
            
            c.setStrokeColor(colors.HexColor("#f0f0f0"))
            c.line(margin + 20, y_line - 5, self.width - margin - 20, y_line - 5)
            
        # Check for Legend (* or specific string)
        has_limit_asterisk = any("Ilimitado somente para colisão*" in val for _, val in covs)
        if has_limit_asterisk:
             legend_y = start_list_y - (len(covs) * row_h) - 10
             c.setFont("Helvetica-Oblique", 8)
             c.setFillColor(self.col_text_muted)
             legend_text = "* Guincho ilimitado somente para colisão quando não puder trafegar, demais situações limita-se a 500km."
             # Draw wrapping if needed or single line (it is long but fits in width)
             c.drawString(margin + 20, legend_y, legend_text)

        c.restoreState()

        self.curr_y -= (h_c + (10 if self.is_third_party else 15))

    def draw_section_franquias(self, c):
        franquias = self.data.get('franquias_lista', [])
        
        # In RCF/Third Party policies, ensure Casco shows as "Não contratada"
        if self.is_third_party:
             has_basica = any(any(x in f for x in ["Casco", "Básica", "Basica"]) for f in franquias)
             if not has_basica:
                  franquias = ["Casco: Não contratada"] + franquias

        if not franquias: return

        row_h = 20
        h_c = 80 + (len(franquias) * row_h)
        
        self._check_space(c, h_c)
        margin = self.margin
        page_w = self.page_w
        y = self.curr_y - h_c
        
        self._draw_shadow_card(c, margin, y, page_w, h_c)
        c.saveState()
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(self.col_brand_dark)
        c.drawString(margin + 20, self.curr_y - 30, "FRANQUIAS")
        
        start_fr_y = self.curr_y - 60
        for i, f_str in enumerate(franquias):
             y_line = start_fr_y - (i*row_h)
             
             # Parse Name/Value if possible
             if ":" in f_str:
                  parts = f_str.split(":", 1)
                  name = parts[0].strip()
                  val = parts[1].strip()
             else:
                  # Try finding last R$
                  if "R$" in f_str:
                       parts = f_str.rsplit("R$", 1)
                       name = parts[0].strip()
                       val = "R$ " + parts[1].strip()
                  else:
                       name = f_str
                       val = ""
             
             # Clean RCF-V variations from name
             rcf_pattern = r'\bR\.?C\.?F\.?\s*[-–— ]?\s*V?\.?\b\s*[-–—:]?\s*'
             name = re.sub(rcf_pattern, '', name, flags=re.I).strip()
             
             c.setFillColor(self.col_accent)
             c.circle(margin + 25, y_line + 4, 3, fill=1, stroke=0)
             
             c.setFont("Helvetica", 10)
             c.setFillColor(self.col_text_main)
             c.drawString(margin + 35, y_line, name)
             
             if val:
                   c.setFont("Helvetica-Bold", 10)
                   # Only color the value green if it's the first/main franchise (likely Casco)
                   if "não contratada" in val.lower():
                        c.setFillColor(self.col_text_muted) # Gray
                   elif i == 0 or (self.is_third_party and i == 1 and len(franquias) > 1):
                        # If third party, the second item might be the "main" one if first is injected
                        c.setFillColor(self.col_price) 
                   else:
                        c.setFillColor(self.col_brand_dark)
                   c.drawRightString(self.width - margin - 25, y_line, val)
             
             c.setStrokeColor(colors.HexColor("#f0f0f0"))
             c.line(margin + 20, y_line - 5, self.width - margin - 20, y_line - 5)
             
        c.restoreState()
        self.curr_y -= (h_c + 15)

    def draw_section_obs(self, c):
        # Calculate dynamic height based on lines
        if self.is_third_party:
            lines_text = [
                "Quem dirige: A cotação vale para quem usa o carro 85% do tempo ou mais.",
                "Uso: Apenas particular. Não cobre rodar por apps (Uber, 99, etc.).",
                "Endereço: Mudou de CEP? Avise agora. Endereço errado pode anular a cobertura.",
            ]
            h_c = 60
        else:
            lines_text = [
                "Quem dirige: A cotação vale para quem usa o carro 85% do tempo ou mais.",
                "Uso: Apenas particular. Não cobre rodar por apps (Uber, 99, etc.).",
                "Vidros: Reparos ou trocas apenas na rede credenciada da seguradora.",
                "Endereço: Mudou de CEP? Avise agora. Endereço errado pode anular a cobertura.",
                "Carro Reserva: Liberação só acontece após a autorização do conserto ou da Perda Total.",
                "Regras da Locadora: Para pegar o reserva precisa de: +21 anos, 2 anos de CNH e cartão de crédito no nome do segurado."
            ]
            h_c = 160
        self._check_space(c, h_c)
        margin = self.margin
        page_w = self.page_w
        y = self.curr_y - h_c
        
        self._draw_shadow_card(c, margin, y, page_w, h_c)
        c.saveState()
        if self.is_third_party:
            c.setFont("Helvetica-Bold", 10)
            c.setFillColor(self.col_brand_dark)
            c.drawString(margin + 20, self.curr_y - 15, "BOM SABER")
            c.setFont("Helvetica", 8)
            c.setFillColor(self.col_text_muted)
            text_start_y = self.curr_y - 28
            line_height = 12
        else:
            c.setFont("Helvetica-Bold", 12)
            c.setFillColor(self.col_brand_dark)
            c.drawString(margin + 20, self.curr_y - 30, "BOM SABER")
            c.setFont("Helvetica", 9)
            c.setFillColor(self.col_text_muted)
            text_start_y = self.curr_y - 50
            line_height = 15
        
        for i, line in enumerate(lines_text):
            c.drawString(margin + 20, text_start_y - (i * line_height), f"• {line}")
            
        c.restoreState()
        self.curr_y -= (h_c + 15)

    def _find_logo(self, insurer):
        for cand in [insurer, insurer.upper(), insurer.title(), "Aliro" if insurer == "ALIRO" else insurer]:
            for ext in ['.jpg', '.png', '.jpeg']:
                p = resource_path(os.path.join("logos", f"{cand}{ext}"))
                if os.path.exists(p): return p
        return None
