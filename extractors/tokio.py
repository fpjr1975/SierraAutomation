import re
from .base import BaseExtractor

class TokioExtractor(BaseExtractor):
    def extract(self):
        self.data['insurer'] = 'TOKIO'
        text = self.full_text



        lines = text.split('\n')

        # --- Segurado & Condutor ---
        # Dump Line 18: "Proponente CPF/CNPJ: Principal Condutor"
        # Dump Line 19: "DELTA FIRE LTDA 09.523.815/0001-20 É possível determinar"
        # Dump Line 20: "Nome Principal condutor CPF principal condutor Estado Civil principal condutor"
        # Dump Line 21: "AUGUSTO ROBERTO MINUSCOLI 011.584.370-13 Casado(a) ou vive em união estável"
        # Debug Collision: Line 29: "RAFAEL BARBIERI 000.982.330-17 Próprio Segurado"

        self.data["segurado"] = "N/D"
        self.data["condutor"] = "N/D"

        # Scan for specific headers
        for i, line in enumerate(lines):
             l_strip = line.strip()
             # Segurado
             if "Proponente CPF/CNPJ" in line or "Proponente :" in line:
                  # Scan next few lines for CPF/CNPJ pattern
                  # Pattern: \d{3}\.\d{3}\.\d{3}-\d{2} or \d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}
                  found_seg = False
                  for offset in range(1, 6):
                       if i+offset >= len(lines): break
                       cand_seg = lines[i+offset].strip()

                       # Look for ID pattern
                       # Match <Name> <ID>
                       # We want everything before the ID
                       match_id = re.search(r'(\d{2,3}\.\d{3}\.\d{3}.{5})', cand_seg)
                       if match_id:
                            # Split at ID
                            parts = cand_seg.split(match_id.group(1))
                            raw_name = parts[0].strip()
                            # Clean up
                            # Sometimes "Estado Civil" or "Principal Condutor" leaks if left side? No, ID is usually early.
                            # Collision dump: RAFAEL BARBIERI 000...
                            if raw_name:
                                 self.data["segurado"] = raw_name
                                 found_seg = True
                                 break
                  if found_seg: continue # Skip old logic

                  # Old Logic Fallback
                  if i+1 < len(lines):
                       cand_seg = lines[i+1].strip()
                       match_seg = re.match(r'([^\d]+)', cand_seg)
                       if match_seg:
                            clean_seg = match_seg.group(1).strip()
                            clean_seg = re.sub(r'Principal Condutor.*', '', clean_seg, flags=re.I).strip()
                            self.data["segurado"] = clean_seg

             # Condutor
             if "Nome Principal condutor" in line or "Principal Condutor" in line:
                  if "Nome Principal condutor" in line and i+1 < len(lines):
                       cand_cond = lines[i+1].strip()
                       match_cond = re.match(r'([^\d]+)', cand_cond)
                       if match_cond:
                            self.data["condutor"] = match_cond.group(1).strip()

        # Fallback if values still N/D
        if self.data["condutor"] == "N/D" and self.data["segurado"] != "N/D":
             self.data["condutor"] = self.data["segurado"]

        # --- Validade Antecipado ---
        # Dump: "contratando até12/01/2026" or "contratando o seguro até 12/01/2026"
        ant_match = re.search(r'contratando.*?at.\s*(\d{2}/\d{2}/\d{4})', text, re.IGNORECASE | re.DOTALL)
        if ant_match:
             self.data["validade_antecipado"] = ant_match.group(1)

        # --- Veiculo ---
        # "Fabricante Veículo" (Line 35) -> Next line Value
        veic_line = self._find_value_next_line(text, "Fabricante Veículo")
        if veic_line:
             self.data["veiculo"] = veic_line.strip()
        else:
             self.data["veiculo"] = self._find_value_after_keyword(text, "Modelo do Veículo") or "N/D"

        # --- Vigencia ---
        # "Vigência: 17/01/2026 a 17/01/2027" or "17/01/2026 - 17/01/2027"
        vig_match = re.search(r'(\d{2}/\d{2}/\d{4})\s*[-a]\s*(\d{2}/\d{2}/\d{4})', text)
        if vig_match:
             self.data["vigencia"] = f"{vig_match.group(1)} a {vig_match.group(2)}"

        # --- CEP / Uso ---
        # Scan for "CEP de pernoite" and look ahead for the pattern \d{5}-?\d{3}
        # This handles cases where questionnaire text appears between the label and the value.
        self.data["cep_pernoite"] = "N/D"
        for i, line in enumerate(lines):
            if "CEP de pernoite" in line:
                # Look at same line first
                cep_match = re.search(r'(\d{5}-?\d{3})', line)
                if cep_match:
                    self.data["cep_pernoite"] = cep_match.group(1)
                    break
                # Look ahead up to 5 lines
                found_cep = False
                for offset in range(1, 6):
                    if i + offset < len(lines):
                        cand = lines[i + offset].strip()
                        cep_match = re.search(r'(\d{5}-?\d{3})', cand)
                        if cep_match:
                            self.data["cep_pernoite"] = cep_match.group(1)
                            found_cep = True
                            break
                if found_cep: break

        # "Tipo de utilização" -> Next Line -> "Particular - Lazer ..."
        uso_line = self._find_value_next_line(text, "Tipo de utilização")
        if uso_line:
             self.data["uso"] = uso_line.split('-')[0].strip()
        else: self.data["uso"] = "N/D"

        # --- Special Franchise Parsing (Indenização Partial) ---
        # Look for "Indenização Parcial do Veículo" block
        # Collision Dump:
        # Line 87: Indenização Parcial do Veículo R$ 2.936,00 (50% da Básica)
        # OR
        # Line 19: Indenização Parcial - 50% da Básica | R$
        # Line 20: Franquia Indenização Integral 2.936,00
        # Wait, Line 19/20 in Debug Collision top block is weird.
        # But Line 87 in Page 3 block is clear: "Indenização Parcial do Veículo R$ 2.936,00 (50% da Básica)"

        found_franquia_direct = None
        reduction_tag = None

        for line in lines:
            line_clean = line.strip()
            if "Indenização Parcial" in line_clean and "Veículo" in line_clean:
                 # Check for value
                 val_match = re.search(r'R\$\s*([\d\.]+,\d{2})', line_clean)
                 if val_match:
                      found_franquia_direct = f"R$ {val_match.group(1)}"

                 # Check for reduced / Percentage tag
                 # Capture "(50% da Básica)" or "(25% Reduzida)"
                 # We look for something in parens with a % symbol
                 tag_match = re.search(r'\(([^)]*?%[^)]*?)\)', line_clean)
                 if tag_match:
                      # e.g. "50% da Básica"
                      # We want to format it nicely? Or keep as is?
                      # User says "a regra do (50% Reduzida) nao esta sendo escrita quando é 25% Reduzida"
                      # So we probably want "Franquia Casco (25% Reduzida)"
                      # If the tag is "25% da Básica", maybe we change it to "25% Reduzida" for consistency?
                      # Or just use the raw tag. "50% da Básica" is clear enough.
                      # Let's clean it up:
                      raw_tag = tag_match.group(1)
                      if "Básica" in raw_tag or "Basic" in raw_tag:
                           # "50% da Básica" -> "50% Reduzida" ?
                           # Tokio "Reduzida" usually means "Reduced from Basic".
                           # Let's try to standardize to "XX% Reduzida" if it's a reduction.
                           # Check for digit
                           digit_m = re.search(r'(\d+)', raw_tag)
                           if digit_m:
                                reduction_tag = f"({digit_m.group(1)}% Reduzida)"
                           else:
                                reduction_tag = f"({raw_tag})"
                      else:
                           reduction_tag = f"({raw_tag})"

        # --- Coberturas ---
        coberturas = []
        franquias_lista = []

        mode = None
        # Tokio layout:
        # Table "Descrição ... Prêmio Líquido" (Main Covers)

        for i, line in enumerate(lines):
             line_upper = line.upper()
             line_strip = line.strip()

             # Mode switching
             if "DESCRIÇÃO" in line_upper and "PRÊMIO LÍQUIDO" in line_upper:
                  mode = "table_desc"
                  continue

             # End table conditions
             if mode == "table_desc":
                  # "Prêmio Líquido total" ends table
                  if "PRÊMIO LÍQUIDO TOTAL" in line_upper:
                       mode = None

                  # Parse Rows

                  # Case 1: Full Row (3 cols)
                  # "RCF-V - Danos Materiais R$ 300.000,00 R$ 1.057,54"
                  match_full = re.match(r'^(.+?)\s+(R\$\s*[\d\.]+,\d{2})\s+(R\$\s*[\d\.]+,\d{2})$', line_strip)

                  # Case 2: Missing Limit Middle Col? (Rare, usually "Não contratada" or "Ilimitado")
                  # "Casco Não contratada R$ 0,00" -> This one has 3 parts technically if we count "Não contratada" as limit
                  # But "Colisão ... R$ 1.434,70" might be missing limit if it wrapped?

                  # Case 3: "Colisão" or "Casco" with just value (Premium)
                  # In Debug Collision: "Colisão, Incêndio e Roubo/Furto R$ 1.434,70" -> Only 2 parts!
                  # Regex for 2 parts: Description + Value

                  if match_full:
                       desc = match_full.group(1).strip()
                       # Cleanup "RCF-V" prefix
                       desc = re.sub(r'RCF-V\s*-?\s*', '', desc, flags=re.I).strip()
                       val = match_full.group(2).strip() # Limit
                       # Add
                       coberturas.append((desc, val))
                  else:
                       # Try 2 parts (Desc + Money)
                       match_two = re.match(r'^(.+?)\s+(R\$\s*[\d\.]+,\d{2})$', line_strip)
                       if match_two:
                            desc = match_two.group(1).strip()
                            # Remove RCF-V variations (even more aggressive universal regex)
                            # Cleans "RCF - V", "Rcf.V", "R.C.F.V.", "RCFV", etc.
                            rcf_pattern = r'R\s*C\s*F\s*[-–—\.]?\s*V\s*[-–—]?\s*'
                            desc = re.sub(rcf_pattern, '', desc, flags=re.I).strip()
                            val = match_two.group(2).strip() # This is likely Premium in this context, but wait.
                            # In "Colisão ... R$ 1434", 1434 is Premium. The Limit is on next line "100%".
                            # But we NEED 'Colisão' in coverages to detect type.
                            # So let's add it. We can say val is "Contratado" or just use the premium (it won't be displayed as limit usually if logic prefers Limit col).
                            # Actually, Sierra Generator uses the Value we pass.
                            # If we pass premium R$ 1434, it shows "Colisão ... R$ 1434". That's confusing.
                            # We should look for the Limit.
                            # In Debug Collision:
                            # Line 63: Colisão, Incêndio e Roubo/Furto R$ 1.434,70
                            # Line 64: 100,00%

                            # If it's Colisão/Casco, look ahead for %
                            if "COLISÃO" in desc.upper() or "CASCO" in desc.upper() or "VMR" in desc.upper():
                                 # Seek limit in next line
                                 next_l = lines[i+1].strip() if i+1 < len(lines) else ""
                                 if "%" in next_l:
                                      coberturas.append((desc, next_l)) # "Colisão...", "100%"
                                 else:
                                      coberturas.append((desc, "Contratado"))

                       # Also handle "Casco Não contratada"
                       if "CASCO" in line_upper and "NÃO CONTRATADA" in line_upper:
                            pass # Ignored or add?

        # --- Add Franchise to List ---
        # If we found it via dedicated search
        if found_franquia_direct:
             label = "Franquia Casco"
             if reduction_tag:
                  label += f" {reduction_tag}"

             franquias_lista.append(f"{label}: {found_franquia_direct}")

        # Fallback: Check if Franchise is in Coberturas table
        # Sometimes Tokio puts "Franquia" items in the main coverage table
        for c_desc, c_val in coberturas:
             if "Franquia" in c_desc:
                  # Avoid duplicates if found by direct search
                  if not any(c_desc in f for f in franquias_lista):
                       franquias_lista.append(f"{c_desc}: {c_val}")

        # Fallback 2: General scan for "Franquia" + Value lines if list still empty
        if not franquias_lista:
             for line in lines:
                  if "Franquia" in line and "R$" in line:
                       # exclude headers
                       if "Valor" not in line and "Prêmio" not in line:
                           clean = line.strip()
                           # Try to extract Description and Value
                           # "Franquia de Vidros R$ 150,00"
                           # Just add the whole line if short
                           if len(clean) < 60:
                                franquias_lista.append(clean)

        # Also parse other franchises from coverage table if any (usually Tokio puts them in separate block/page)
        # Assuming dedicated search is better.



        # Franquias Checks outside loop
        # Check for specific isolated lines
        # "Sem Franquia para Casco"
        if "SEM FRANQUIA PARA CASCO" in text.upper():
             franquias_lista.append("Casco: Isento (Sem Franquia)")



        # Franchise List Keywords (Glass, Repairs, etc.)
        f_kws = ["Parabrisa", "Farol", "Lanterna", "Retrovisor", "Vidro Traseiro", "Vigia", "Lateral", "Martelinho", "Para-choque", "Lataria", "Máquina", "Teto Solar"]
        for line in lines:
             if "R$" in line and any(k.lower() in line.lower() for k in f_kws):
                  # Extract "Name R$ Value" (Handles parens, hyphens, and multi-column lines)
                  # Refined regex to include special chars like ( ) and -
                  matches = re.findall(r'([A-Z][\w\s\/\-\(\),]+?)\s+R\$\s*([\d\.,]+)', line)
                  for m in matches:
                       name_clean = m[0].strip()
                       val_clean = m[1]
                       if any(k.lower() in name_clean.lower() for k in f_kws) and len(name_clean) < 40:
                            franquias_lista.append(f"{name_clean}: R$ {val_clean}")

        # --- Carro Reserva (Global Scoring System) ---
        potential_vals = []
        found_contratado = False

        # Phase 1: Scan Numbered Clauses (High Quality Data)
        clause_iter = re.finditer(r'^\d+\s*-\s*(.*?)(?:\n|$)', text, re.MULTILINE)
        for match in clause_iter:
            c_text = match.group(1).upper()
            if "CARRO RESERVA" in c_text or "AUTO RESERVA" in c_text:
                # Extract all number+day patterns in this clause
                days_matches = re.finditer(r'(\d+)\s*(?:DIAS|DIÁRIAS|DIARIAS)', c_text)
                for dm in days_matches:
                    val_num = int(dm.group(1))
                    desc = f"{val_num} Dias"
                    score = 0

                    # Score based on category indicators
                    if any(kw in c_text for kw in ["BÁSICO", "BASICO", "EXECUTIVO", "VIP", "PLUS", "100%"]):
                        score += 1000
                        if "BÁSICO" in c_text or "BASICO" in c_text: desc += " (Básico)"
                        if "EXECUTIVO" in c_text: desc += " (Executivo)"

                    # Score based on standard limit range (1-60)
                    if 1 <= val_num <= 60:
                        score += 500
                    else:
                        # Heavy penalty for disclaimers (e.g. 180 days for notification)
                        score -= 500

                    potential_vals.append((score, desc))

        # Phase 2: Scan Table/Service blocks globally
        cr_iter = re.finditer(r'(?:Carro|Auto)\s*Reserva', text, re.IGNORECASE)
        for match in cr_iter:
            # Context: Current line + next 3 lines
            start_pos = match.start()
            context_text = text[start_pos:start_pos + 400] # Slightly larger buffer
            context_lines = [l.strip() for l in context_text.split('\n') if l.strip()]

            for line_idx, cl in enumerate(context_lines[:4]):
                # Skip very long lines (likely disclaimers or paragraphs)
                if len(cl) > 150: continue
                l_upper = cl.upper()

                # Check for explicit day matches in context
                days_matches = re.finditer(r'(\d+)\s*(?:DIAS|DIÁRIAS|DIARIAS)', l_upper)
                for dm in days_matches:
                    val_num = int(dm.group(1))
                    desc = f"{val_num} Dias"
                    score = 0

                    # Boost for categories
                    if any(kw in l_upper for kw in ["BÁSICO", "BASICO", "EXECUTIVO", "VIP", "PLUS", "100%"]):
                        score += 1000
                        if "BÁSICO" in l_upper or "BASICO" in l_upper: desc += " (Básico)"
                        if "EXECUTIVO" in l_upper: desc += " (Executivo)"

                    # Boost for standard ranges
                    if 1 <= val_num <= 60:
                        score += 500
                    else:
                        score -= 500

                    # Boost for being on the same line as the label
                    if line_idx == 0:
                        score += 100

                    potential_vals.append((score, desc))

                # Secondary indicator: Contracted status
                if not found_contratado and any(kw in l_upper for kw in ["CONTRATADO", "SIM", "POSSUI"]):
                    if "NÃO" not in l_upper:
                        found_contratado = True

        # Final Decision: Global Match
        final_cr = None
        if potential_vals:
            # Pick highest scorer globally
            potential_vals.sort(key=lambda x: x[0], reverse=True)
            final_cr = potential_vals[0][1]
        elif found_contratado:
            final_cr = "Contratado"

        if final_cr:
            coberturas = [x for x in coberturas if x[0] != "Carro Reserva"]
            coberturas.append(("Carro Reserva", final_cr))

        # --- Guincho / Assistencia Fix ---
        # User Feedback: "200 km (padrão) + 300 km (adicional) = 500 KM"
        # Logic: Try to extract the explicit Total first. If not, sum components.

        guincho_val = "24h" # Default

        # 1. explicit total check
        total_match = re.search(r'=\s*(\d+)\s*KM', text, re.IGNORECASE)
        if total_match:
             guincho_val = f"Guincho {total_match.group(1)} Km"
        else:
             # 2. Summing Logic
             # Extract all km mentions related to Towing
             # "Assistência 24 Horas (Guincho) 200 Km"
             # "Km adicional de reboque 300 Km"

             # Base
             base_km = 0
             base_match = re.search(r'(?:Guincho|Reboque).*?(\d{3,4})\s*Km', text, re.IGNORECASE)
             if base_match:
                  base_km = int(base_match.group(1))

             # Additional
             add_km = 0
             # Check explicitly for "Ilimitado" in additional line first
             add_ilimitado = re.search(r'(?:Km adicional|Adicional).*?(Ilimitado|Livre)', text, re.IGNORECASE)

             if add_ilimitado:
                  guincho_val = "Guincho Ilimitado"
             else:
                  add_match = re.search(r'(?:Km adicional|Adicional).*?(\d{3,4})\s*Km', text, re.IGNORECASE)
                  if add_match:
                       add_km = int(add_match.group(1))

                  # Ilimitado check (Global fallback)
                  if (base_km > 0 or add_km > 0) and guincho_val == "24h":
                       total = base_km + add_km
                       guincho_val = f"Guincho {total} Km"
                  elif "ILIMITADO" in text.upper() and ("GUINCHO" in text.upper() or "REBOQUE" in text.upper()) and guincho_val == "24h":
                       guincho_val = "Guincho Ilimitado"

        # Add to coberturas
        coberturas.append(("Assistência 24h", guincho_val))

        self.data["coberturas"] = coberturas

        # Sort Franquias: "Franquia Casco" first
        deduped_franquias = list(set(franquias_lista))
        def fr_sort_key(s):
             # Priority 0: "Franquia Casco"
             if "Franquia Casco" in s: return (0, s)
             # Priority 1: Others
             return (1, s)
        self.data["franquias_lista"] = sorted(deduped_franquias, key=fr_sort_key)

        # --- Pagamento ---
        pag_opcoes = []

        # Scrape "Ficha" or "Débito" tables
        # Look for "1 1.761,35 ... 6 343,85"
        # Best strategy: regex for "N R$ Val Sem Juros" or "N Val Antecipado"

        # Extract all (Installment, Value) pairs found with "Sem Juros" or "Antecipado"
        # To avoid duplicates (columns), we store in a dict keyed by Installment

        installments_map = {}

        # Regex: Digit(s) + Space + Money + Space + (Sem Juros|Antecipado)
        # matches: ('1', '1.761,35', 'Antecipado')
        # Be careful with columns merging.
        # dump: "1 1.761,35 Antecipado* 1.761,35" -> Matches "1 1.761,35 Antecipado"

        # We prefer "Sem Juros".

        raw_matches = re.findall(r'\b(\d{1,2})\s+([\d\.,]+)\s+(Sem Juros|Antecipado)', text, re.I)

        val_antecipado = None

        for m in raw_matches:
             inst = int(m[0])
             val = m[1]
             desc_type = m[2]

             if inst == 1 and "Antecipado" in desc_type:
                  val_antecipado = val
                  # Do NOT add to installments_map.
                  # This ensures map[1] is only populated by "Sem Juros" (Standard).
             else:
                  installments_map[inst] = val

        if installments_map:
             max_inst = max(installments_map.keys())
             val_max = installments_map[max_inst]
             val_1x = installments_map.get(1, val_max) # Fallback

             # Add Vista
             pag_opcoes.append({"tipo": "À Vista", "parcelas": "1x", "valor": f"R$ {val_1x}"})
             self.data["premio_total"] = f"R$ {val_1x}"

             # Add Debit Anticipated (If found)
             if val_antecipado:
                  pag_opcoes.append({
                      "tipo": "Débito Antecipado",
                      "parcelas": "1x",
                      "valor": f"R$ {val_antecipado}",
                      "validade": self.data.get("validade_antecipado", "")
                  })

             # Add Credit (Max)
             if max_inst > 1:
                  pag_opcoes.append({"tipo": "Cartão de Crédito", "parcelas": f"{max_inst}x", "valor": f"R$ {val_max}"})

             # Add Debit (Cap 5x)
             debit_opts = {k:v for k,v in installments_map.items() if k <= 5}
             if debit_opts:
                  max_d = max(debit_opts.keys())
                  val_d = debit_opts[max_d]
                  if max_d > 1:
                       pag_opcoes.append({"tipo": "Débito em Conta", "parcelas": f"{max_d}x", "valor": f"R$ {val_d}"})

        if not pag_opcoes:
             # Fallback
             total_match = re.search(r'Prêmio Líquido total\s*R\$\s*([\d\.,]+)', text, re.I)
             if total_match:
                  p = f"R$ {total_match.group(1)}"
                  self.data["premio_total"] = p
                  pag_opcoes.append({"tipo": "À Vista", "parcelas": "1x", "valor": p})

        self.data["pagamento_opcoes"] = pag_opcoes
        self.data["placa"] = self._extract_placa_generic(text)
        self._apply_casing()
        return self.data
