import re
from .base import BaseExtractor


class AllianzExtractor(BaseExtractor):
    def extract(self):
        self.data['insurer'] = 'ALLIANZ'
        text = self.full_text



        lines = text.split('\n')

        # --- Basic Info ---
        self.data["segurado"] = self._find_value_after_keyword(text, "Nome:", "CPF") or "N/D"
        cond_match = re.search(r'INFORMAÇÕES DO CONDUTOR PRINCIPAL\s*Nome:\s*(.*?)\s+CPF', text, re.IGNORECASE)
        self.data["condutor"] = cond_match.group(1).strip() if cond_match else self.data["segurado"]

        vig_match = re.search(r'Vigência.*?(\d{2}/\d{2}/\d{4}).*?(\d{2}/\d{2}/\d{4})', text, re.IGNORECASE | re.S)
        if vig_match:
            self.data["vigencia"] = f"{vig_match.group(1)} a {vig_match.group(2)}"

        self.data["tipo_seguro"] = self._find_value_after_keyword(text, "Tipo de Seguro:", "Produto") or "N/D"
        if "Renovação" in self.data["tipo_seguro"]:
            self.data["tipo_seguro"] = "Renovação"

        self.data["veiculo"] = self._find_value_after_keyword(text, "Veículo:", "Versão") or "N/D"
        self.data["cep_pernoite"] = self._find_value_after_keyword(text, "CEP Pernoite:", "Ano") or "N/D"
        self.data["uso"] = self._find_value_after_keyword(text, "Finalidade de Uso:", ["Categoria", "\n"]) or "N/D"

        # --- Coberturas (Multicolumn) ---
        block_cols = []
        active_block = False
        target_block_found = False
        first_block_done = False  # Prevent reactivation after first COMPLETO block
        parsed_coberturas = []
        last_line_text = ""

        for i, line in enumerate(lines):
             line_strip = line.strip()
             if not line_strip: continue

             # Detect Column Headers - Broader check
             # Line 40: "Roubo e Furto * Básico Ampliado"
             # Line 71: "Completo Master Exclusivo"
             upper_line = line.upper()


             # Don't reactivate if we already completed first COMPLETO block
             if first_block_done:
                  continue

             if any(col in upper_line for col in ["BÁSICO", "AMPLIADO", "COMPLETO", "MASTER", "EXCLUSIVO"]) and \
                len(line.split()) > 1 and "COBERTURAS" not in upper_line and not re.search(r"\d+,\d{2}", line):

                  clean = re.sub(r'Roubo e Furto', '', line, flags=re.I).replace('*', ' ')
                  parts = clean.split()
                  candidates = [p for p in parts if p.upper() in ["BÁSICO", "AMPLIADO", "COMPLETO", "MASTER", "EXCLUSIVO"]]

                  if candidates:
                      # If we find Completo, prioritize it
                      if "COMPLETO" in [c.upper() for c in candidates]:
                           block_cols = candidates
                           active_block = True
                           target_block_found = True
                           # If we had a previous fallback block active, we might want to clear,
                           # but now we are just strictly looking for Completo.
                      else:
                           # Strict: We only want Completo/Master block.
                           # This avoids duplicates from Basic/Ampliado block appearing first.
                           active_block = False

                  continue

             # Force activate for Guincho if we have columns
             if "GUINCHO" in line.upper() and target_block_found:
                 active_block = True
             if active_block:
                  if "PREÇO TOTAL" in upper_line or "IOF" in upper_line:
                       active_block = False
                       # Mark first block as done to prevent payment tables from reactivating
                       if target_block_found:
                            first_block_done = True
                       continue

                  val_regex = r'(?i)(\d{1,3}(?:\.\d{3})*,\d{2}|\d+\s*%\s*FIPE|Plano\s*\d+|[\d\.,]+\s*Dias|Km\s*Livre|\d+\s*Km)'
                  matches = list(re.finditer(val_regex, line))
                  if not matches:
                       last_line_text = line
                       continue

                  vals_found = [m.group(0) for m in matches]

                  try:
                       # Determine which index we want from this block
                       # If block has Completo, use it. Else use Ampliado (fallback)
                       c_ups = [c.upper() for c in block_cols]
                       if "COMPLETO" in c_ups: target_idx = c_ups.index("COMPLETO")
                       elif "AMPLIADO" in c_ups: target_idx = c_ups.index("AMPLIADO")
                       elif "BÁSICO" in c_ups: target_idx = c_ups.index("BÁSICO")
                       else: continue
                  except: continue

                  # Allianz = Limit | Price pairs?
                  # Line 78: "RCF... 200k 1k ... 400k 1.1k" -> Yes (2 values per col)
                  # Line 88: "Plano 3 329,01 ... Plano 3 329,01" -> Yes (2 values per col)

                  target_val_idx = target_idx * 2

                  if len(vals_found) > target_val_idx:
                       # We want Limit (first of pair) usually.
                       # For Coverage amount: Limit.
                       # For Vidros: Plan Name.

                       limit_val = vals_found[target_val_idx]

                       desc_end = matches[0].start()
                       desc = line[:desc_end].strip()

                       # Context check for split lines (Vidros)
                       if not desc and "VIDROS" in last_line_text.upper():
                            desc = "Vidros"

                       if "CASCO" in desc.upper() or "COMPREENSIVA" in desc.upper():
                            parsed_coberturas.append(("Compreensiva", limit_val))
                       elif "DANOS MATERIAIS" in desc.upper():
                            parsed_coberturas.append(("Danos Materiais", f"R$ {limit_val}"))
                       elif "DANOS CORPORAIS" in desc.upper():
                            parsed_coberturas.append(("Danos Corporais", f"R$ {limit_val}"))
                       elif "DANOS MORAIS" in desc.upper():
                            parsed_coberturas.append(("Danos Morais", f"R$ {limit_val}"))
                       elif "APP" in desc.upper() and ("MORTE" in desc.upper() or "INVALIDEZ" in desc.upper()):
                            if "MORTE" in desc.upper(): parsed_coberturas.append(("APP Morte", f"R$ {limit_val}"))
                            else: parsed_coberturas.append(("APP Invalidez", f"R$ {limit_val}"))
                       elif "ASSISTÊNCIA" in desc.upper():
                            # Map Plano to human readable - keep as is, Guincho will be extracted separately
                            # Plano 3 is the name, but km comes from Guincho line
                            pass  # Skip, will extract from Guincho line below
                       elif "GUINCHO" in desc.upper():
                            # User Request: "Guincho Km Livre" or "Guincho 500 Km"
                            # limit_val e.g. "Km Livre" or "200 Km"
                            if "LIVRE" in limit_val.upper() or "ILIMITADO" in limit_val.upper():
                                 parsed_coberturas.append(("Assistência 24h", "Guincho Km Livre"))
                            else:
                                 # Try to extract numeric km
                                 km_match = re.search(r'(\d+)\s*[Kk][Mm]', limit_val)
                                 if km_match:
                                      parsed_coberturas.append(("Assistência 24h", f"Guincho {km_match.group(1)} Km"))
                                 else:
                                      parsed_coberturas.append(("Assistência 24h", f"Guincho {limit_val}"))

                       elif "VIDROS" in desc.upper():
                             # If "Plano 3", we want that.
                            parsed_coberturas.append(("Vidros", limit_val))
                       elif "CARRO RESERVA" in desc.upper():
                            # User Request: "Carro Reserva X Dias"
                            # limit_val e.g. "15 Dias" or "7 Dias"
                            if "DIAS" in limit_val.upper():
                                 parsed_coberturas.append(("Carro Reserva", limit_val))
                            else:
                                 # If just "Básico", try to find days in description or assume 7?
                                 # Or just Append "Contratado"
                                 parsed_coberturas.append(("Carro Reserva", f"{limit_val}"))

             last_line_text = line

        # Fallback if specific extraction failed (e.g. not a multicolumn?)
        if not parsed_coberturas and not target_block_found:
             # Basic single column fallback check
             pass

        self.data["coberturas"] = parsed_coberturas

        # --- Franquias ---
        franquias_lista = []
        # Casco: Look for "Franquia" header or similar
        # "Franquia Valor (R$) - 50% da Normal 3.695,26" or "Reduzida R$ 2000,00"
        casco_fr = re.search(r'Franquia.*?Valor\s*\(R\$\)\s*(.*?)\s*(\d{1,3}(?:\.\d{3})*,\d{2})', text, re.S | re.I)
        if not casco_fr:
             # Try simpler pattern: "Casco ... R$ X" found in some dumps (e.g. Line 38)
             casco_fr = re.search(r'Casco\s+(.*?)\s+R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})', text, re.I)

        if casco_fr:
             fr_desc = casco_fr.group(1).strip()
             fr_val = f"R$ {casco_fr.group(2)}"
             full_fr = f"{fr_desc} {fr_val}"

             self.data["franquia"] = full_fr
             # Ensure it appears on Page 2
             self.data["coberturas"].append(("Franquia", full_fr))
             franquias_lista.append(f"Casco: {full_fr}")
        else:
             # Line 16/17: "FRANQUIA - CASCO... \n R$ 16.300,48"
             match_new_layout = re.search(r'FRANQUIA\s*-\s*CASCO.*?\n\s*R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})', text, re.S | re.I)
             if match_new_layout:
                  val = match_new_layout.group(1)
                  self.data["franquia"] = f"R$ {val}"
                  self.data["coberturas"].append(("Franquia", f"Casco R$ {val}"))
                  franquias_lista.append(f"Casco: R$ {val}")

        # Vidros: Section starts with "ASSISTÊNCIA AVIDROS" (possibly no space)
        found_vidros = False
        for line in lines:
             if "ASSISTÊNCIA" in line.upper() and "VIDROS" in line.upper():
                  found_vidros = True
                  continue
             if found_vidros:
                  if "Consulte" in line or "Página" in line or "Serviços" in line:
                       if len(line.strip()) > 30 : # Might be just a long legal line
                            found_vidros = False
                       continue
                  # Parse pairs: "Parabrisa 385,00 Lanterna Convencional 200,00"
                  # Regex matching name and value
                  matches = re.findall(r'([A-Za-zÀ-ÿ\s/-]+?)\s+(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                  for n, v in matches:
                       cleaned_n = n.strip()
                       if cleaned_n and len(cleaned_n) > 3:
                            franquias_lista.append(f"{cleaned_n}: R$ {v}")

        self.data["franquias_lista"] = franquias_lista

        # --- Pagamento ---
        pag_opcoes = []
        premio_total = "N/D"
        # 1x value extraction
        for line in lines:
             # Match "01 sem juros" followed by multiple money values
             if "01" in line and "sem juros" in line:
                  ms = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                  # Completo is index 3 in 6-value row (Roubo, Basico, Ampliado, Completo...)
                  # If row has fewer values, fallback to last or first?
                  # Dump showed 6 values.
                  if len(ms) >= 4:
                       val = ms[3]
                       premio_total = f"R$ {val}"
                       pag_opcoes.append({"tipo": "À Vista", "parcelas": "1x", "valor": f"R$ {val}"})
                       # Also set self.data["premio_total"] here
                       self.data["premio_total"] = f"R$ {val}"
                       break
                  elif ms:
                       # Fallback if columns confusing
                       val = ms[-1] # Most expensive? or ms[0] cheapest?
                       # Usually client wants Completo, which is middle-high.
                       # If we failed column logic, stick to what we found or just N/D
                       pass

        # 10x value extraction
        # 10x value extraction and general parcel search
        # Capture all lines with "N sem juros"

        max_credit = 0
        best_credit = None

        max_debit = 0
        best_debit = None

        for line in lines:
             if "sem juros" in line:
                  # Parse Parcel Count
                  # "10 sem juros" or "06 sem juros"
                  m_parc = re.search(r'(\d{2})\s+sem juros', line)
                  if m_parc:
                       p_count = int(m_parc.group(1))

                       # Extract Values
                       ms = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                       if len(ms) >= 4:
                            val = ms[3]

                            # Credit (Max)
                            if p_count > max_credit:
                                 max_credit = p_count
                                 best_credit = {"tipo": "Cartão de Crédito", "parcelas": f"{p_count}x", "valor": f"R$ {val}"}

                            # Debit (Max <= 6)
                            if p_count <= 6 and p_count > max_debit:
                                 max_debit = p_count
                                 best_debit = {"tipo": "Débito em Conta", "parcelas": f"{p_count}x", "valor": f"R$ {val}"}

        if best_credit and max_credit > 1:
             pag_opcoes.append(best_credit)

        if best_debit and max_debit > 1:
             pag_opcoes.append(best_debit)

        self.data["pagamento_opcoes"] = pag_opcoes
        self._apply_casing()
        return self.data
