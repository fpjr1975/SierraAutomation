import re
from .base import BaseExtractor


class HdiExtractor(BaseExtractor):
    def extract(self):
        self.data['insurer'] = 'HDI'
        text = self.full_text
        lines = text.split('\n')

        # --- Basic Info ---
        # "Proponente:RAFAEL BARBIERI CPF:..."
        match_seg = re.search(r'Proponente:\s*(.*?)\s+CPF', text)
        if match_seg:
             self.data["segurado"] = match_seg.group(1).strip()

        # CPF
        match_cpf = re.search(r'CPF:(\d{11})', text)
        # Veiculo
        # "Veículo:0016577 - FORD - ECOSPORT - FREESTYLE..."
        # "Veículo:COD - MAKE - MODEL - VERSION (FIPE code)"
        match_veic = re.search(r'Veículo:.*?\s+-\s+(.*?)\s*\(FIPE', text)
        if match_veic:
             self.data["veiculo"] = match_veic.group(1).strip()
        else:
             # Fallback
             match_veic_simple = re.search(r'Veículo:(.*?)$', text, re.MULTILINE)
             if match_veic_simple: self.data["veiculo"] = match_veic_simple.group(1).strip()

        # Vigencia
        # "Vigência: DAS 24 HS DO DIA 13/03/2026 ÀS 24 HS DO DIA 13/03/2027 ( 365 DIAS)"
        match_vig = re.search(r'Vig[eê]ncia:.*?(\d{2}/\d{2}/\d{4}).*?(\d{2}/\d{2}/\d{4})', text, re.S | re.I)
        if match_vig:
             self.data["vigencia"] = f"{match_vig.group(1)} a {match_vig.group(2)}"

        # Condutor
        # "Nome do Condutor:Rafael Barbieri"
        match_cond = re.search(r'Nome do Condutor:(.*?)$', text, re.MULTILINE)
        if match_cond:
             self.data["condutor"] = match_cond.group(1).strip()

        # Uso (Not explicit in dump snippet, usually "Utilizacao do VeiculoExclusivamente para Locomocao Diaria")
        if "Locomocao Diaria" in text:
             self.data["uso"] = "Passeio"

        # CEP
        # "CEP Pernoite: 95096060 Cobertura:Compreensiva"
        match_cep = re.search(r'CEP\s*Pernoite:\s*(\d+)', text)
        if match_cep:
             self.data["cep_pernoite"] = match_cep.group(1)

        # --- Cobertura Type Logic ---
        # Rule: Cobertura: Compreensiva -> Normal, Cobertura: Responsabilidade Civil -> Third Party
        coberturas = []
        match_cob_type = re.search(r'Cobertura:\s*(Compreensiva|Responsabilidade Civil)', text, re.I)
        if match_cob_type:
            cob_type = match_cob_type.group(1)
            if "Compreensiva" in cob_type:
                # Pre-insert to ensure categorization works even if table parsing fails
                coberturas.append(("Compreensiva", "Contratada"))

        # Footnotes Map
        # (*1) Text... (*3) Text...
        fn_map = {}
        # improved regex to capture (*N)
        raw_footnotes = re.findall(r'(\(\*\d+\))(.*?)(?=\(\*\d+\)|$)', text, re.DOTALL)
        for ref, content in raw_footnotes:
            # ref: (*1), content: text
            key = ref.replace('(*', '').replace(')', '')
            fn_map[key] = content.strip().replace('\n', ' ')


        # --- Coberturas (Garantias de Auto) ---
        # Line oriented parsing
        # "RCF-V DANOS MATERIAIS 200.000,00 821,72"
        # "CASCO 100,00% FIPE ... "

        for line in lines:
             l = line.strip()
             if "DANOS MATERIAIS" in l and "RCF-V" in l:
                  val = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', l)
                  if val: coberturas.append(("Danos Materiais", f"R$ {val[0]}")) # First number is Limit
             elif "DANOS CORPORAIS" in l and "RCF-V" in l:
                  val = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', l)
                  if val: coberturas.append(("Danos Corporais", f"R$ {val[0]}"))
             elif "DANOS MORAIS" in l:
                  val = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', l)
                  if val: coberturas.append(("Danos Morais", f"R$ {val[0]}"))
             elif "APP MORTE" in l:
                  val = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', l)
                  if val: coberturas.append(("APP Morte", f"R$ {val[0]}"))
             elif "APP INVALIDEZ" in l:
                  val = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', l)
                  if val: coberturas.append(("APP Invalidez", f"R$ {val[0]}"))
             elif "CASCO" in l and not any("Compreensiva" in c[0] for c in coberturas):
                  # Only add if not already added by header logic
                  # Search for percentage and reference (FIPE or V.M.)
                  fipe_match = re.search(r'(\d+[\.,]\d+|\d+)\s*%\s*(FIPE|V\.?M\.?)', l, re.I)
                  if fipe_match:
                       val = f"{fipe_match.group(1)}% {fipe_match.group(2).upper()}"
                       coberturas.insert(0, ("Compreensiva", val))
                  elif "FIPE" in l:
                       coberturas.insert(0, ("Compreensiva", "100% FIPE"))
                  else:
                       coberturas.insert(0, ("Compreensiva", "Contratada"))
             elif "CASCO" in l:
                  # If already exists (added by header), try to update the value if table has more detail
                  fipe_match = re.search(r'(\d+[\.,]\d+|\d+)\s*%\s*(FIPE|V\.?M\.?)', l, re.I)
                  if fipe_match:
                       new_val = f"{fipe_match.group(1)}% {fipe_match.group(2).upper()}"
                       # Update the first item (which we know is Compreensiva)
                       for idx, (name, old_val) in enumerate(coberturas):
                            if name == "Compreensiva":
                                 coberturas[idx] = ("Compreensiva", new_val)
                                 break
             elif "HDI AUTO VIDROS" in l:
                   coberturas.append(("Vidros", "HDI Auto Vidros"))
             elif "ESPECIAL AUTO" in l or "VIP AUTO" in l:
                   # "ESPECIAL AUTO - 600KM" or "ESPECIAL AUTO (*5)"
                   # Check direct mention first
                   dist_match = re.search(r'(\d+)\s*KM', l, re.IGNORECASE)
                   if "ILIMITAD" in l.upper() or "SEM LIMITE" in l.upper():
                        coberturas.append(("Guincho", "Ilimitado"))
                   elif dist_match:
                        coberturas.append(("Guincho", f"{dist_match.group(1)} KM"))
                   else:
                        # Check footnote
                        fn_ref = re.search(r'\(\*(\d+)\)', l)
                        if fn_ref:
                            fn_id = fn_ref.group(1)
                            if fn_id in fn_map:
                                fn_text = fn_map[fn_id]
                                # Look for "Guincho X Km" or "Ilimitado" in footnote
                                fn_dist = re.search(r'(\d+)\s*KM', fn_text, re.IGNORECASE)
                                if "ILIMITAD" in fn_text.upper() or "SEM LIMITE" in fn_text.upper():
                                     coberturas.append(("Guincho", "Ilimitado"))
                                elif fn_dist:
                                     coberturas.append(("Guincho", f"{fn_dist.group(1)} KM"))
                                else:
                                     coberturas.append(("Guincho", "Contratado"))
                            else:
                                coberturas.append(("Guincho", "Contratado"))
                        else:
                             coberturas.append(("Guincho", "Contratado"))
             elif "DIAS CR" in l or "CARRO RESERVA" in l:
                   # Try direct capture
                   days_match = re.search(r'(\d+)\s+DIAS', l)
                   if days_match:
                       # Standardize: "X Dias"
                       coberturas.append(("Carro Reserva", f"{days_match.group(1)} Dias"))
                   else:
                       # Try footnote capture
                       fn_ref = re.search(r'\(\*(\d+)\)', l)
                       if fn_ref:
                           fn_id = fn_ref.group(1)
                           if fn_id in fn_map:
                               fn_text = fn_map[fn_id]
                               fn_days = re.search(r'(\d+)\s+DIAS', fn_text, re.IGNORECASE)
                               if fn_days:
                                    desc = f"{fn_days.group(1)} Dias Carro Reserva"
                                    coberturas.append(("Carro Reserva", desc))
                               else:
                                    coberturas.append(("Carro Reserva", "Contratado (Ver Detalhes)"))
                           else:
                               coberturas.append(("Carro Reserva", "Contratado"))
                       else:
                            coberturas.append(("Carro Reserva", "Contratado"))

        self.data["coberturas"] = coberturas

        # --- Franquias ---
        franquias_lista = []
        # Main hull franchise in Casco line
        # "CASCO 100,00% FIPE 812,07 47.857,50 1.094,45 3.434,20" (Last col is Franchise?)
        # Header: "Cobertura ... Franquia" -> Yes.

        # Find Casco line again or store it
        match_casco = re.search(r'CASCO\s+.*?\s+(\d{1,3}(?:\.\d{3})*,\d{2})$', text, re.MULTILINE)
        if match_casco:
             franquias_lista.append(f"Casco: R$ {match_casco.group(1)}")
        else:
             # Scan line
             for line in lines:
                  if "CASCO" in line and "FIPE" in line:
                       vals = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                       if len(vals) >= 3:
                            franquias_lista.append(f"Casco: R$ {vals[-1]}")
                            break

        # Footnotes (*1), (*2)
        # "(*1)Vidros com franquia de R$ 400,00. Vidro Traseiro..."
        # "(*2)Farol com franquia de..."

        footnotes = re.findall(r'\(\*\d\)(.*?)(?=\(\*\d\)|$)', text, re.DOTALL)
        for fn in footnotes:
             # Clean newlines
             clean_fn = fn.replace('\n', ' ').strip()
             # "Vidros com franquia de R$ 400,00."
             # Split by periods or just capture items
             # Regex for "Item com franquia de R$ X"

             parts = re.split(r'(?:\.|,)\s+', clean_fn)
             for p in parts:
                  match_item = re.search(r'(.*?)com franquia de\s+(R\$\s*[\d\.,]+)', p, re.IGNORECASE)
                  if match_item:
                       item_name = match_item.group(1).strip()
                       item_val = match_item.group(2).strip()
                       franquias_lista.append(f"{item_name}: {item_val}")

        self.data["franquias_lista"] = franquias_lista

        # --- Pagamento ---
        pag_opcoes = []

        # Total À Vista
        # "TOTAL À VISTA (R$) 2.457,48"
        total_val = 0.0
        match_total = re.search(r'TOTAL\s+À\s+VISTA\s*\(R\$\)\s*([\d\.,]+)', text, re.IGNORECASE)
        if match_total:
             self.data["premio_total"] = f"R$ {match_total.group(1)}"
             pag_opcoes.append({"tipo": "À Vista", "parcelas": "1x", "valor": f"R$ {match_total.group(1)}"})
             total_val = float(match_total.group(1).replace('.', '').replace(',', '.'))

        # Parcelamento - Max Sem Juros Strategy
        # Capture all lines starting with "N x"
        patterns = re.findall(r'(\d+)\s+x\s+([\d\.,]+)', text)

        max_credit = 0
        best_credit = None

        max_debit = 0
        best_debit = None

        for p in patterns:
             num = int(p[0])
             val_str = p[1]
             val = float(val_str.replace('.', '').replace(',', '.'))

             # Check if interest free (Tolerance 1% or 2.00 BRL)
             # Expected Total = num * val
             calc_total = num * val

             # If total_val is known, compare. If not, assume "1x" is base.
             is_interest_free = False
             if total_val > 0:
                  if abs(calc_total - total_val) < (total_val * 0.05): # 5% tolerance
                       is_interest_free = True
             elif num == 1:
                  total_val = val
                  is_interest_free = True
             else:
                  pass

             if is_interest_free:
                  # Credit (No Limit)
                  if num > max_credit:
                       max_credit = num
                       best_credit = {"tipo": "Cartão de Crédito", "parcelas": f"{num}x", "valor": f"R$ {val_str}"}

                  # Debit (Limit 6x)
                  if num <= 6 and num > max_debit:
                       max_debit = num
                       best_debit = {"tipo": "Débito em Conta", "parcelas": f"{num}x", "valor": f"R$ {val_str}"}

        if best_credit and max_credit > 1:
             pag_opcoes.append(best_credit)

        if best_debit and max_debit > 1:
             pag_opcoes.append(best_debit)

        self.data["pagamento_opcoes"] = pag_opcoes

        self.data["placa"] = self._extract_placa_generic(text)
        self._apply_casing()
        return self.data
