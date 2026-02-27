import re
from .base import BaseExtractor


class EzzeExtractor(BaseExtractor):
    def extract(self):
        self.data['insurer'] = 'EZZE'
        text = self.full_text
        lines = text.split('\n')

        # --- Basic Info ---
        # "Nome: CPF/CNPJ:"
        # Next line has value: "Rafael Barbieri 000.982.330-17"
        seg_raw = self._find_value_next_line(text, "Nome: CPF/CNPJ:") or self._find_value_after_keyword(text, "Nome:")
        if seg_raw:
             # Remove CPF if attached (000.000.000-00)
             parts = re.split(r'\s+\d{3}\.\d{3}\.\d{3}-\d{2}', seg_raw)
             self.data["segurado"] = parts[0].strip()

        # Condutor
        # "Nome completo do condutor RAFAEL BARBIERI"
        # Often on same line
        cond_match = re.search(r'Nome completo do condutor\s*(.*?)$', text, re.MULTILINE | re.I)
        if cond_match:
             self.data["condutor"] = cond_match.group(1).strip()
        else:
             self.data["condutor"] = self.data["segurado"]

        # Veiculo
        # "Modelo Placa"
        # "Ecosport Freestyle 1.6 16V Flex 5P IWC0930"
        veic_line = self._find_value_next_line(text, "Modelo Placa") or self._find_value_after_keyword(text, "Modelo Placa")
        if veic_line:
             # Remove Plate (ABC1234 or IWC0930)
             # Regex for plate at end
             veic_cleaned = re.split(r'\s+[A-Z]{3}\d[A-Z0-9]\d{2}', veic_line)[0].strip()
             self.data["veiculo"] = veic_cleaned

        # Vigencia
        # "Vigência:"
        # "das 00:00 do dia 03/01/2026 até 23:59 do dia 03/01/2027"
        vig_match = re.search(r'das\s*[\d:]*\s*do\s*dia\s*(\d{2}/\d{2}/\d{4})\s*até\s*[\d:]*\s*do\s*dia\s*(\d{2}/\d{2}/\d{4})', text, re.IGNORECASE)
        if vig_match:
             self.data["vigencia"] = f"{vig_match.group(1)} a {vig_match.group(2)}"

        # CEP / Uso
        # "CEP de Pernoite:" -> Next line or same
        cep_match = re.search(r'CEP de Pernoite:.*?(\d{8}|\d{5}-?\d{3})', text, re.S | re.I)
        if cep_match:
              self.data["cep_pernoite"] = cep_match.group(1)

        # Uso
        if "Particular" in text or "Lazer" in text:
             self.data["uso"] = "Passeio"

        # --- Coberturas (Page 2) ---
        coberturas = []

        for line in lines:
             # Coberturas logic
             l_strip = line.strip()
             if "Danos Materiais" in line and "Cobertura" not in line:
                  val = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                  if val: coberturas.append(("Danos Materiais", f"R$ {val[0]}"))
             elif "Danos Corporais" in line and "Valor IS" not in line.upper():
                  val = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                  if val: coberturas.append(("Danos Corporais", f"R$ {val[0]}"))
             elif "Danos Morais" in line:
                  val = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                  if val: coberturas.append(("Danos Morais", f"R$ {val[0]}"))
             elif "APP Morte" in line:
                   val = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                   if val: coberturas.append(("APP Morte", f"R$ {val[0]}"))
             elif "APP Invalidez" in line:
                   val = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                   if val: coberturas.append(("APP Invalidez", f"R$ {val[0]}"))
             elif "Vidros" in line and "Premium" in line:
                   coberturas.append(("Vidros", "Planos Premium"))
             elif "Carro Reserva" in line:
                   # Standardize: "Carro Reserva 20 Dias"
                   match_days = re.search(r'(\d+)\s+dias', line, re.IGNORECASE)
                   if match_days:
                        coberturas.append(("Carro Reserva", f"{match_days.group(1)} Dias"))
                   else:
                        coberturas.append(("Carro Reserva", "Contratado"))

             elif "Assistência" in line:
                   # Standardize: "Guincho 2000 Km"
                   # Input: "Assistência Passeio Premium 2.000km 256,58"
                   km_match = re.search(r'(\d+(?:\.\d+)*)\s*km', line, re.IGNORECASE)
                   if km_match:
                        km_val = km_match.group(1).replace('.', '')
                        coberturas.append(("Assistência 24h", f"Guincho {km_val} Km"))
                   elif "ILIMITADO" in line.upper():
                        coberturas.append(("Guincho", "Ilimitado"))
                   else:
                        # Fallback
                        cleaned = re.sub(r'\s+\d{1,3}(?:\.\d{3})*,\d{2}.*$', '', line)
                        match_ast = re.search(r'Assistência\s+(.*)', cleaned)
                        val_ast = match_ast.group(1).strip() if match_ast else "Contratada"
                        coberturas.append(("Assistência 24h", val_ast))

        if "100% Fipe" in text:
             coberturas.insert(0, ("Compreensiva", "100% FIPE"))

        self.data["coberturas"] = coberturas

        # --- Franquias (Page 3) ---
        franquias_lista = []

        in_franquia_section = False

        for i, line in enumerate(lines):
             if "Franquias" in line and i+4 < len(lines):
                  # Check if nearby lines contain "Franquia ("
                  # Dump: Line 86 Franquias, Line 87 Franquia (R$)
                  if "Franquia (" in lines[i+1] or "Franquia (" in lines[i+2]:
                        in_franquia_section = True
                        continue

             if "Informações Importantes" in line or "Informações do Corretor" in line:
                  in_franquia_section = False

             if in_franquia_section:
                 l = line.strip()

                 # Check keywords + Money
                 matches = re.findall(r'([A-Za-z0-9 \-\(\)\/]+)\s+(\d{1,3}(?:\.\d{3})*,\d{2})', l)
                 for m in matches:
                      name = m[0].strip()
                      val = m[1]
                      # Filter out header noise
                      if "Franquia" in name or " Valor " in name: continue
                      if len(name) < 3: continue

                      franquias_lista.append(f"{name}: R$ {val}")

                      # Capture Main Casco Franquia for Page 1 Card
                      if "Casco" in name or "Compreensiva" in name:
                           self.data["franquia"] = f"R$ {val}"
                           # Ensure it's in Coberturas too if desired, but "Franquia" key usually handles card.
                           # But for "Page 2" list, it uses 'franquias_lista'.

        self.data["franquias_lista"] = franquias_lista

        # --- Pagamento ---
        pag_opcoes = []

        # Prefer left column for 10x

        # À Vista
        total_val = 0.0
        vista_match = re.search(r'À Vista\s+(\d{1,3}(?:\.\d{3})*,\d{2})', text)
        if vista_match:
             self.data["premio_total"] = f"R$ {vista_match.group(1)}"
             pag_opcoes.append({"tipo": "À Vista", "parcelas": "1x", "valor": f"R$ {vista_match.group(1)}"})
             total_val = float(vista_match.group(1).replace('.', '').replace(',', '.'))

        # Installments (look for '1 + N' pattern)
        matches = re.findall(r'(1\s+\+\s+(\d+))\s+(\d{1,3}(?:\.\d{3})*,\d{2})', text)

        max_credit = 0
        best_credit = None

        max_debit = 0 # Explicitly ignore Debit for Ezze as requested

        for m in matches:
             count = int(m[1]) + 1
             val_str = m[2]
             val = float(val_str.replace('.', '').replace(',', '.'))
             calc_total = count * val

             # Check if interest free
             is_int_free = False
             if total_val > 0 and abs(calc_total - total_val) < (total_val * 0.05):
                  is_int_free = True
             elif count == 1:
                  is_int_free = True

             if is_int_free:
                  # Update Credit (No Limit)
                  if count > max_credit:
                       max_credit = count
                       best_credit = {"tipo": "Cartão de Crédito", "parcelas": f"{count}x", "valor": f"R$ {val_str}"}

                  # Debit Ignored for Ezze

        if best_credit and max_credit > 1:
             pag_opcoes.append(best_credit)

        self.data["pagamento_opcoes"] = pag_opcoes

        self.data["placa"] = self._extract_placa_generic(text)
        self._apply_casing()
        return self.data
