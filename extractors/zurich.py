import re
from .base import BaseExtractor

class ZurichExtractor(BaseExtractor):
    def extract(self):
        self.data['insurer'] = 'ZURICH'
        text = self.full_text
        lines = text.split('\n')

        # Vigência
        # "Inicio de vigência: 24H 03/01/2026 Término de vigência: 24H 03/01/2027"
        match_vig = re.search(r'In[ií]cio.*?(\d{2}/\d{2}/\d{4}).*?T[ée]rmino.*?(\d{2}/\d{2}/\d{4})', text, re.IGNORECASE | re.DOTALL)
        if match_vig:
             self.data["vigencia"] = f"{match_vig.group(1)} a {match_vig.group(2)}"

        # Veículo
        # "Veículo: NEW ECOSPORT FREEST. 1.6 FLEX Ano Modelo: 2015"
        match_veic = re.search(r'Veículo:(.*?)(?:Ano Modelo|$)', text, re.IGNORECASE)
        if match_veic:
             self.data["veiculo"] = match_veic.group(1).strip()

        # Segurado
        # "Nome completo/Razão social: RAFAEL BARBIERI"
        match_nome = self._find_value_after_keyword(text, "Nome completo/Razão social:", "Tipo de pessoa")
        if match_nome:
             self.data["segurado"] = match_nome

        # Condutor
        # "Condutor principal: RAFAEL BARBIERI"
        match_cond = self._find_value_after_keyword(text, "Condutor principal:", "Sexo")
        if match_cond:
             self.data["condutor"] = match_cond
        else:
             self.data["condutor"] = self.data["segurado"]

        # Uso
        # "Uso veículo: APENAS LAZER/LOCOMOÇÃO..."
        match_uso =  re.search(r'Uso veículo:(.*?)(?:\n|$)', text, re.IGNORECASE)
        if match_uso:
             self.data["uso"] = match_uso.group(1).split(',')[0].strip()

        # CEP
        # "CEP do local de pernoite do veículo: 95096060"
        match_cep = re.search(r'CEP.*?pernoite.*?:.*?(\d{5}-?\d{3})', text.replace(" ", ""), re.IGNORECASE)
        if not match_cep:
             # Try finding 8 digits
             match_cep = re.search(r'CEP.*?pernoite.*?:.*?(\d{8})', text, re.IGNORECASE)

        if match_cep:
             val = match_cep.group(1)
             if "-" not in val: val = f"{val[:5]}-{val[5:]}"
             self.data["cep_pernoite"] = val



        # Prêmio Total
        match_total = re.search(r'Prêmio Total \(R\$\).*?\n.*?(\d[\d\.,]*)', text, re.IGNORECASE | re.DOTALL)
        # Dump: "Prêmio Total (R$)" \n "2.462,87"
        # Or look for "Valor da Entrada... Premio Total" table

        # Fallback search for simple "Prêmio Total" line logic
        pt_idx = -1
        for i, line in enumerate(lines):
             if "Prêmio Total (R$)" in line:
                  pt_idx = i
                  break

        if pt_idx != -1 and pt_idx + 1 < len(lines):
             # "2.462,87 1 2.462,87" -> Last element likely total
             parts = lines[pt_idx+1].split()
             if parts:
                  self.data["premio_total"] = f"R$ {parts[-1]}"

        # Coberturas & Franquias

        # Dump: "Veículo - Colisão/Incêndio/Roubo 100% FIPE A - 3.755,36 1.086,09"
        # Franquia is "A - 3.755,36"
        self.data["franquias_lista"] = []

        # Regex for Casco
        for line in lines:
             if "Colisão/Incêndio/Roubo" in line or "100% FIPE" in line:
                  self.data["tipo_seguro"] = "Cobertura Compreensiva (100% FIPE)"
                  # Extract Franchise
                  # Looking for "A - 3.755,36" or similar pattern "X - Value"
                  franq_match = re.search(r'[A-Z]\s+-\s+([\d\.,]+)', line)
                  if franq_match:
                       val = franq_match.group(1)
                       self.data["franquia"] = f"R$ {val}"
                       # 'Casco' is not in PDF, using 'Franquia'
                       self.data["franquias_lista"].append(f"Franquia: R$ {val}")

        # "Lanterna de LED 470,00"
        # "Para-brisa 430,00"
        # List of keywords to scan
        franq_keywords = [
             "Lanterna", "Farol", "Retrovisor", "Para-brisa", "Vidro",
             "Martelinho", "Reparo de Para-choque", "Reparo de Arranh"
        ]

        for line in lines:
             # Find all money values in the line (e.g. 150,00)
             # Matches return (start, end) spans
             money_matches = list(re.finditer(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line))
             if not money_matches: continue

             for k in franq_keywords:
                  if "Cobertura Especial" in line or "LMG" in line or "Prêmio" in line: continue

                  # Find keyword match
                  k_match = re.search(re.escape(k), line, re.IGNORECASE)
                  if k_match:
                       # Find the first money match that starts AFTER the keyword
                       # "Martelinho 150,00" -> k_end < money_start
                       valid_money = [m for m in money_matches if m.start() >= k_match.end()]
                       if valid_money:
                            m = valid_money[0]
                            val = m.group(1)

                            # Extract description from keyword start to money start
                            # This naturally excludes the money part and any preceding garbage if we use k_match.start()
                            # But we might want words "before" the keyword?
                            # E.g. "Farol de Milha 100". k="Farol".
                            # If we take `line[k_match.start():m.start()]` -> "Farol de Milha ". Good.
                            desc_raw = line[k_match.start():m.start()]

                            # Clean "R$" and whitespace
                            desc = desc_raw.replace("R$", "").strip()

                            # Clean specific Zurich patterns "Martelinho (Franquia Teto 300)"
                            # Remove (Franquia ...) blocks
                            desc = re.sub(r'\(Franquia.*?\)', '', desc, flags=re.IGNORECASE).strip()

                            # Clean trailing separators, digits, or parenthesis leftovers
                            # e.g. "Martelinho 300)" -> "Martelinho"
                            desc = re.sub(r'[\d\)\(\.\-:]+$', '', desc).strip()

                            # One more pass to clean internal excessive spaces
                            desc = re.sub(r'\s+', ' ', desc)

                            # Add if valid
                            if len(desc) >= 3:
                                 self.data["franquias_lista"].append(f"{desc}: R$ {val}")

        # deduplication while preserving order?
        # Actually, let's just keep them as they are found.
        # self.data["franquias_lista"] = sorted(list(set(self.data["franquias_lista"])))

        # Deduplicate preserving order
        seen = set()
        unique_franq = []
        for x in self.data["franquias_lista"]:
            if x not in seen:
                unique_franq.append(x)
                seen.add(x)
        self.data["franquias_lista"] = unique_franq

        # Coberturas Values
        # Compreensiva
        if "Compreensiva" in text or "Colisão/Incêndio" in text:
             # Try to find FIPE percentage
             fipe_match = re.search(r'(\d+%)\s*FIPE', text)
             val = fipe_match.group(1) if fipe_match else "100%"
             self.data["coberturas"].append(("Compreensiva", f"{val} FIPE"))

        dm_match = re.search(r'Danos Materiais\.*R\$\s*([\d\.,]+)', text, re.IGNORECASE)
        # Assuming regex above might fail if R$ is missing in some dumps, try looser:
        if not dm_match: dm_match = re.search(r'Danos Materiais\s+([\d\.,]+)', text, re.IGNORECASE)
        if dm_match: self.data["coberturas"].append(("Danos Materiais", f"R$ {dm_match.group(1)}"))

        dc_match = re.search(r'Danos Corporais\.*R\$\s*([\d\.,]+)', text, re.IGNORECASE)
        if not dc_match: dc_match = re.search(r'Danos Corporais\s+([\d\.,]+)', text, re.IGNORECASE)
        if dc_match: self.data["coberturas"].append(("Danos Corporais", f"R$ {dc_match.group(1)}"))

        dmo_match = re.search(r'Danos Morais\s+([\d\.,]+)', text, re.IGNORECASE)
        if dmo_match: self.data["coberturas"].append(("Danos Morais", f"R$ {dmo_match.group(1)}"))

        # APP
        # 36: APP - Acidentes Pessoais de Passageiros (LMG por passageiro) 5.000,00 14,38
        app_match = re.search(r'APP\s+-\s+Acidentes.*?(?:LMG.*?)?(\d[\d\.,]*)', text, re.IGNORECASE)
        if app_match:
             self.data["coberturas"].append(("APP Morte", f"R$ {app_match.group(1)}"))

        # Vidros
        # 38: Cobertura Especial para Vidros 15.000,00 486,07
        # 73 - VIDROS VIP
        if "VIDROS VIP" in text.upper():
             self.data["coberturas"].append(("Vidros", "Consulte tabela Franquias"))
        elif "Cobertura Especial para Vidros" in text:
             self.data["coberturas"].append(("Vidros", "Consulte tabela Franquias"))

        # Assistencia
        # 82 - ASSISTÊNCIA 24 HS COMPLETA 300 Km/Caminhões: 400 Km
        # Or "Cláusula 38 - Carro Reserva..." if user feedback implies that.

        # 1. Assistência / Guincho
        assist_match = re.search(r'ASSISTÊNCIA\s*24\s*HS\s*(.*?)(?:\n|$)', text, re.IGNORECASE)
        if assist_match:
             val = assist_match.group(1).strip()
             val = val.split("Prêmio")[0]
             self.data["coberturas"].append(("Assistência 24h", val))
        else:
             # Fallback: Search for "Guincho" explicitly
             guincho_match = re.search(r'(?:Serviço de )?Guincho\s*(.*?)(?:\n|$)', text, re.IGNORECASE)
             if guincho_match:
                 self.data["coberturas"].append(("Assistência 24h", f"Guincho {guincho_match.group(1).strip()}"))

        # 2. Carro Reserva
        # Look for "Carro Reserva" keyword and days
        # "Carro Reserva 7 Dias" or "Cláusula 38 - Carro Reserva..."
        cr_match = re.search(r'Carro\s+Reserva.*?(?:\n|$)', text, re.IGNORECASE)
        if cr_match:
             line_cr = cr_match.group(0)
             # Extract days
             days = re.search(r'(\d+)\s*Dias', line_cr, re.IGNORECASE)
             if days:
                  self.data["coberturas"].append(("Carro Reserva", f"{days.group(1)} Dias"))
             elif "Contratado" in line_cr or "Sim" in line_cr:
                  self.data["coberturas"].append(("Carro Reserva", "Contratado"))
             elif "Não Contratado" not in line_cr:
                  # Maybe just "Carro Reserva Basico"
                  if "Básico" in line_cr or "Executivo" in line_cr:
                        self.data["coberturas"].append(("Carro Reserva", line_cr.strip()))

        # 3. Check "Cláusulas" specifically - ROBUST PARSING
        # "74 - CARRO RESERVA BÁSICO 15 DIAS - LMG R$50,00 (DIÁRIA)"
        # "83 - ASSISTÊNCIA 24 HS VIP 400 Km / Caminhões: 400 Km"

        # Regex for "NN - DESCRICAO"
        # We want to capture lines that start with a number code and dash
        clause_lines = re.findall(r'^\d+\s+-\s+(.*?)(?:\n|$)', text, re.MULTILINE)

        for c_text in clause_lines:
             c_upper = c_text.upper()

             # Carro Reserva
             if "CARRO RESERVA" in c_upper or "AUTO RESERVA" in c_upper:
                  days_match = re.search(r'(\d+)\s*DIAS', c_upper)
                  if days_match:
                       days = days_match.group(1)
                       desc = f"{days} Dias"
                       # Add details if basic/exec
                       if "BÁSICO" in c_upper or "BASICO" in c_upper: desc += " (Básico)"
                       if "EXECUTIVO" in c_upper: desc += " (Executivo)"
                       if "PLUS" in c_upper: desc += " (Plus)"

                       # Remove existing weak entries if any
                       self.data["coberturas"] = [x for x in self.data["coberturas"] if x[0] != "Carro Reserva"]
                       self.data["coberturas"].append(("Carro Reserva", desc))

             # Assistencia
             if "ASSISTÊNCIA" in c_upper or "GUINCHO" in c_upper:
                  # Extract Km
                  km_match = re.search(r'(\d+)\s*KM', c_upper)
                  desc = "Contratada"
                  if km_match:
                       desc = f"Guincho {km_match.group(1)}Km"
                  elif "VIP" in c_upper:
                       desc = "Assistência VIP"
                  elif "COMPLETA" in c_upper:
                       desc = "Assistência Completa"

                  # Remove existing weak entries
                  self.data["coberturas"] = [x for x in self.data["coberturas"] if x[0] != "Assistência 24h"]
                  self.data["coberturas"].append(("Assistência 24h", desc))

             # Vidros (VIP)
             if "VIDROS" in c_upper:
                  if "VIP" in c_upper:
                       self.data["coberturas"] = [x for x in self.data["coberturas"] if x[0] != "Vidros"]
                       self.data["coberturas"].append(("Vidros", "Vidros VIP (Completo)"))

        # --- Guincho from "Assistência 24 Horas" section ---
        # User feedback: SUM the Km values from "Assistência 24 Horas" line AND clause line
        # Example: "400 Km de Reboque e Km ilimitado para Sinistro" + "ASSISTÊNCIA 24 HS VIP 400 Km"
        # Result: 800 Km for pane + Ilimitado for sinistro

        # Step 1: Extract Km from "Assistência 24 Horas" section (the detailed line)
        # Pattern: "400 Km de Reboque e Km ilimitado para Sinistro"
        assist_km = 0
        has_ilimitado_sinistro = False

        # Find the "Assistência 24 Horas" section and the next few lines
        assist_section = re.search(r'Assistência 24 Horas.*?(?:ZURICH|SUSEP|Prêmio)', text, re.IGNORECASE | re.DOTALL)
        if assist_section:
            section_text = assist_section.group(0)
            # Look for "NNN Km de Reboque"
            km_match = re.search(r'(\d+)\s*Km\s*de\s*Reboque', section_text, re.IGNORECASE)
            if km_match:
                assist_km = int(km_match.group(1))
            # Check for "ilimitado para sinistro" or similar
            if re.search(r'ilimitado\s*(?:para\s*)?sinistro', section_text, re.IGNORECASE):
                has_ilimitado_sinistro = True

        # Step 2: Extract Km from clause (already parsed, get the value)
        clause_km = 0
        for k, v in self.data["coberturas"]:
            if k == "Assistência 24h":
                km_m = re.search(r'(\d+)', v)
                if km_m:
                    clause_km = int(km_m.group(1))
                break

        # Step 3: Sum the values
        total_km = assist_km + clause_km

        # Step 4: Format the description
        if total_km > 0:
            if has_ilimitado_sinistro:
                # Full description: "800km p/ Pane + Ilimitado p/ Sinistro"
                desc = f"{total_km}km p/ Pane + Ilimitado p/ Sinistro"
            else:
                desc = f"Guincho {total_km} Km"

            # Update the coberturas entry
            self.data["coberturas"] = [x for x in self.data["coberturas"] if x[0] != "Assistência 24h"]
            self.data["coberturas"].append(("Assistência 24h", desc))

        # Remove the debug logic we injected earlier (cleanup)
        # (Implicitly handled by overwriting the file if we revert, or just leaving it is fine,
        # but better to avoid dumping files)

        # Pagamento
        if self.data["premio_total"] != "N/D":
             self.data["pagamento_opcoes"].insert(0, {
                 "tipo": "À Vista",
                 "parcelas": "1x",
                 "valor": self.data["premio_total"]
             })

        # 1. Try to find "01 + NN" pattern (Boleto/Debit) (Legacy)
        matches_parc = re.findall(r'01\s+\+\s+(\d{2})\s+([\d\.,]+)\s+([\d\.,]+)\s+([\d\.,]+)', text)
        if matches_parc:
             max_p = 0
             max_val = None
             for m in matches_parc:
                  p = int(m[0]) + 1
                  val_parcela = m[2]
                  if p > max_p:
                       max_p = p
                       max_val = val_parcela

             if max_p > 1:
                  self.data["pagamento_opcoes"].append({
                      "tipo": "Parcelado (Débito/Boleto)",
                      "parcelas": f"{max_p}x",
                      "valor": f"R$ {max_val}"
                  })

        seen_parcels = set()

        # 1. Try to find "01 + NN" pattern (Boleto/Debit) (Legacy?)
        # Or just generic scan.

        for line in lines:
             l = line.strip()

             # Pattern A: 4 values (01 2.462,87 0,00 2.462,87) -> Parc Entry Demais Total
             match_4 = re.search(r'^\s*(\d{1,2})\s+(\d{1,3}(?:\.\d{3})*,\d{2})\s+(\d{1,3}(?:\.\d{3})*,\d{2})\s+(\d{1,3}(?:\.\d{3})*,\d{2})', l)
             if match_4:
                  parc = int(match_4.group(1))
                  val_entry = match_4.group(2)
                  val_demais = match_4.group(3)
                  val_total = match_4.group(4)

                  if parc in seen_parcels: continue
                  seen_parcels.add(parc)

                  if parc == 1:
                       self.data["premio_total"] = f"R$ {val_total}"
                       self.data["pagamento_opcoes"].append({"tipo": "À Vista", "parcelas": "1x", "valor": f"R$ {val_total}"})
                  else:
                       # If 4 columns, Col 3 is usually Installment Value
                       self.data["pagamento_opcoes"].append({"tipo": "Cartão de Crédito", "parcelas": f"{parc}x", "valor": f"R$ {val_demais}"})
                  continue

             # Pattern B: 3 values (2.462,87 1 2.462,87) -> Entry Parc Total
             match_3 = re.search(r'^([\d\.,]+)\s+(\d{1,2})\s+([\d\.,]+)$', l)
             if match_3:
                  val_entry = match_3.group(1)
                  parc = int(match_3.group(2))
                  val_total = match_3.group(3)

                  if parc in seen_parcels: continue
                  seen_parcels.add(parc)

                  if parc == 1:
                       self.data["premio_total"] = f"R$ {val_total}"
                       self.data["pagamento_opcoes"].append({"tipo": "À Vista", "parcelas": "1x", "valor": f"R$ {val_total}"})
                  else:
                       # Calculate installment from Total / Parcels
                       try:
                            t_float = float(val_total.replace('.','').replace(',','.'))
                            inst_float = t_float / parc
                            val_inst = f"R$ {inst_float:,.2f}".replace(',','X').replace('.',',').replace('X','.')
                            self.data["pagamento_opcoes"].append({"tipo": "Cartão de Crédito", "parcelas": f"{parc}x", "valor": val_inst})
                       except: pass
                  continue

             # Pattern C: "01 + 01 ..." (Old logic?)
             # ...

        self._apply_casing()
        return self.data
