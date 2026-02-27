import re
from .base import BaseExtractor


class DarwinExtractor(BaseExtractor):
    def extract(self):
        self.data['insurer'] = 'DARWIN'
        text = self.full_text



        lines = text.split('\n')

        # --- Basic Info ---
        # Segurado
        if len(lines) > 2:
             candidates = lines[:6]
             for l in candidates:
                 if len(l) > 5 and not re.search(r'\d{10}', l) and "Seguros" not in l:
                      self.data["segurado"] = l.strip()
                      break
        if not self.data["segurado"] or self.data["segurado"] == "N/D":
             match_cpf_line = re.search(r'\n(.*?)\n\d{3}\.\d{3}\.\d{3}-\d{2}', text)
             if match_cpf_line: self.data["segurado"] = match_cpf_line.group(1).strip()

        # CEP & Uso (Usually on same line, e.g. "Uso pessoal 95096-060 ...")
        # Global search for CEP pattern
        match_cep = re.search(r'(\d{5}-\d{3})', text)
        if match_cep:
             self.data["cep_pernoite"] = match_cep.group(1)

        # Global search for Uso
        if re.search(r'Uso\s+Pessoal', text, re.I) or re.search(r'Passeio', text, re.I):
             self.data["uso"] = "Passeio/Particular"
        elif re.search(r'Uso\s+Comercial', text, re.I):
             self.data["uso"] = "Comercial"

        # Condutor
        # Heuristic: Find line with Segurado name on Page 1, or just assume Segurado if not found different
        # In dump line 5: "Rafael Barbieri 23/08/1983 ..."
        # Check if we have another name associated with CPF/DOB distinct from Segurado
        # For now, if "Condutor" is not explicit, we default to Segurado, but let's try to match line 5 pattern
        if len(lines) >= 5:
             l5 = lines[4] # 0-indexed
             if self.data["segurado"] in l5:
                  self.data["condutor"] = self.data["segurado"]
             else:
                  # Maybe extract name from start of line until number
                  match_cond = re.match(r'^([^\d]+)', l5)
                  if match_cond:
                       self.data["condutor"] = match_cond.group(1).strip()

        if not self.data["condutor"] or self.data["condutor"] == "N/D":
             self.data["condutor"] = self.data["segurado"]

        # Veiculo
        match_veic = re.search(r'(?:Veículo|Modelo)\s*[:\n]\s*(.*?)$', text, re.MULTILINE)
        if match_veic:
             self.data["veiculo"] = match_veic.group(1).strip()
        else:
             match_desc = re.search(r'\n(.*?(?:Flex|Gasolina|Diesel|Ecosport|Compass|Jeep|Fiat|Ford).*?)\n', text, re.I)
             if match_desc: self.data["veiculo"] = match_desc.group(1).strip()

        # Vigencia
        # Vigencia
        # Find dates that look like a 1-year interval?
        # Or just find the pair after "Vigência"
        vig_match = re.search(r'Vigência.*?(\d{2}/\d{2}/\d{4}).*?(\d{2}/\d{2}/\d{4})', text, re.IGNORECASE | re.DOTALL)
        if vig_match:
             self.data["vigencia"] = f"{vig_match.group(1)} a {vig_match.group(2)}"
        else:
             # Fallback: Find 2 dates appearing sorted
             dates = re.findall(r'(\d{2}/\d{2}/\d{4})', text)
             if len(dates) >= 2:
                  # Sort by year, then month?
                  # Just take first two valid-looking future dates?
                  # No, just take the ones from the top, likely header.
                  # Sort?
                  pass

             # Try stricter regex for Period
             period_match = re.search(r'(\d{2}/\d{2}/\d{4})\s*a\s*(\d{2}/\d{2}/\d{4})', text)
             if period_match:
                  self.data["vigencia"] = f"{period_match.group(1)} a {period_match.group(2)}"

        # --- Coberturas (Text Search) ---
        coberturas = []

        # --- Coberturas (Dynamic Search) ---
        coberturas = []

        # Regex to find Line with Description and Money
        # e.g. "RCF-V - Danos Materiais 100.000,00 123,45"
        # or "Danos Corporais R$ 50.000,00"

        for line in lines:
            line_u = line.upper()
            desc = None
            val = None

            # Danos Materiais
            if "MATERIAIS" in line_u and "DANOS" in line_u:
                 desc = "Danos Materiais"
            # Danos Corporais
            elif "CORPORAIS" in line_u and "DANOS" in line_u:
                 desc = "Danos Corporais"
            # Danos Morais
            elif "MORAIS" in line_u and "DANOS" in line_u:
                 desc = "Danos Morais"
            # APP (Morte/Invalidez)
            elif "APP" in line_u or "MORTE" in line_u or "INVALIDEZ" in line_u:
                 if "MORTE" in line_u: desc = "APP - Morte"
                 elif "INVALIDEZ" in line_u: desc = "APP - Invalidez"
                 else: desc = "APP"
            # Vidros (if appearing in list format)
            elif "VIDROS" in line_u:
                 desc = "Vidros"
                 val = "Consulte tabela Franquias"

            if desc:
                 # Extract value (Limit)
                 # Usually the first Money pattern in the line?
                 # Or "100.000,00"
                 moneys = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                 if moneys and not val:
                      val = f"R$ {moneys[0]}"

                 if val:
                      # Avoid duplicates or multiple hits
                      # Check if already added?
                      if not any(c[0] == desc for c in coberturas):
                           coberturas.append((desc, val))

        # Fallback: Scan for lines with money BUT no text description matched (Hybrid Logic)
        if len(coberturas) < 3:
             for line in lines:
                 moneys = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line)

                 # Require at least 2 values (Limit + Premium) to avoid picking up Total Premium or single costs
                 if len(moneys) < 2: continue

                 if len(moneys) >= 1:
                      val_str = moneys[0]
                      val_float = float(val_str.replace('.', '').replace(',', '.'))

                      if val_float > 1000000: continue

                      # Check matches. Allow 2 entries for >30k (DM+DC).
                      count_val = sum(1 for c in coberturas if c[1] == f"R$ {val_str}")
                      if count_val >= 2: continue
                      if count_val == 1 and val_float < 30000: continue

                      desc = None
                      # Heauristic by Value Magnitude
                      if val_float >= 50000: # 50k+ -> Likely DM, DC, or high APP
                           if not any("Materiais" in c[0] for c in coberturas):
                                desc = "Danos Materiais"
                           elif not any("Corporais" in c[0] for c in coberturas):
                                desc = "Danos Corporais"
                           # If DM and DC are filled, and we have another big item (e.g. 80k), it's likely APP
                           elif not any("APP" in c[0] for c in coberturas):
                                desc = "APP - Morte/Invalidez"

                      elif 15000 <= val_float < 50000: # 15k-50k -> Likely Moral or APP?
                           if not any("Morais" in c[0] for c in coberturas):
                                desc = "Danos Morais"
                           elif not any("APP" in c[0] for c in coberturas):
                                desc = "APP - Morte/Invalidez"

                      elif val_float < 15000: # < 15k -> Likely APP (or DMO if small?)
                           if not any("APP" in c[0] for c in coberturas):
                                desc = "APP - Morte/Invalidez"
                           elif not any("Morais" in c[0] for c in coberturas) and val_float > 5000:
                                desc = "Danos Morais"

                      if desc:
                           coberturas.append((desc, f"R$ {val_str}"))

        # Fallback for Casco if not found above
        if "100% da tabela" in text and not any("Compreensiva" in c[0] for c in coberturas):
             coberturas.insert(0, ("Compreensiva", "100% FIPE"))

        self.data["coberturas"] = coberturas

        # --- Franquias ---
        franquias_lista = []
        keywords = ["Parabrisa", "Farol", "Lanterna", "Retrovisor", "Vigia", "Lateral", "Casco", "Ret.", "Retrov", "Maquina", "RLP", "Vidro", "RPS"]
        for line in lines:
             l_clean = line.strip()
             for kw in keywords:
                 if kw in l_clean and "R$" in l_clean:
                      franquias_lista.append(l_clean)
                      break
        self.data["franquias_lista"] = franquias_lista

        # --- Pagamento ---
        pag_opcoes = []

        all_money = re.findall(r'R\$\s*([\d\.,]+)', text)
        money_vals = []
        for m in all_money:
             try:
                 v = float(m.replace('.', '').replace(',', '.'))
                 # Filter standard limits to avoid confusion with Total Premium
                 if v not in [200000.0, 100000.0, 50000.0, 20000.0, 10000.0, 5000.0] and v < 50000:
                      money_vals.append(v)
             except: pass

        if money_vals:
             total_cand = max(money_vals)
             self.data["premio_total"] = f"R$ {total_cand:,.2f}".replace('.', '#').replace(',', '.').replace('#', ',')

             # Check for 10x ~ Total / 10
             ten_x_cand = total_cand / 10.0

             closest = None
             min_diff = 999999

             for v in money_vals:
                 diff = abs(v - ten_x_cand)
                 if diff < min_diff:
                     min_diff = diff
                     closest = v

             if closest and min_diff < (ten_x_cand * 0.1):
                  val_str = f"R$ {closest:,.2f}".replace('.', '#').replace(',', '.').replace('#', ',')
                  pag_opcoes.append({"tipo": "Cartão de Crédito", "parcelas": "10x", "valor": val_str})

             pag_opcoes.append({"tipo": "À Vista", "parcelas": "1x", "valor": self.data["premio_total"]})

        self.data["pagamento_opcoes"] = pag_opcoes

        self.data["placa"] = self._extract_placa_generic(text)
        self._apply_casing()
        return self.data
