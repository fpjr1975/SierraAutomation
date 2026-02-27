import re
from .base import BaseExtractor


class AlfaExtractor(BaseExtractor):
    def extract(self):
        self.data['insurer'] = 'ALFA'
        text = self.full_text

        # --- Dados Básicos ---
        self.data["segurado"] = self._find_value_after_keyword(text, "Proponente:", "Corretor") or "N/D"

        # Condutor
        condutor_match = self._find_value_after_keyword(text, "Nome do Condutor Principal", "CPF")
        if condutor_match:
             self.data["condutor"] = condutor_match
        else:
             self.data["condutor"] = self.data["segurado"]

        # Veículo
        self.data["veiculo"] = self._find_value_after_keyword(text, "Veículo:", "Ano") or "N/D"

        # Placa
        self.data["placa"] = self._extract_placa_generic(text)
        if self.data["placa"] == "Placa não informada":
             val_placa = self._find_value_after_keyword(text, "Placa:", "Chassi")
             if val_placa: self.data["placa"] = val_placa

        # Vigência
        vigencia_match = re.search(r'Vigência.*?(\d{2}/\d{2}/\d{4}).*?(\d{2}/\d{2}/\d{4})', text, re.IGNORECASE)
        if vigencia_match:
             self.data["vigencia"] = f"{vigencia_match.group(1)} a {vigencia_match.group(2)}"

        # Uso
        self.data["uso"] = self._find_value_after_keyword(text, "Utilização do Veículo")

        # CEP
        self.data["cep_pernoite"] = self._find_value_after_keyword(text, "CEP Pernoite:")

        # Tipo (Renovação?)
        self.data["tipo_seguro"] = "Seguro Novo"
        fidelidade = self._find_value_after_keyword(text, "Fidelidade:")
        if fidelidade and "RENOVAÇÃO" in fidelidade.upper():
             self.data["tipo_seguro"] = "Renovação"

        # Prêmio Total
        self.data["premio_total"] = self._find_value_after_keyword(text, "Valor Total R$:", "Cálculo") or "N/D"

        # --- Coberturas (Tabela) ---
        lines = text.split('\n')
        mode = None

        coberturas = []
        assistencias = []
        franquias = []

        # Franquia Casco (Header)
        frq_casco = self._find_value_after_keyword(text, "Franquia Casco:", "Opção")
        if frq_casco:
             franquias.append(f"Casco: {frq_casco}")

        for line in lines:
            line_strip = line.strip()
            if ("COBERTURA" in line.upper() and "LIMITE" in line.upper()) or "COBERTURAS DO SEGURO" in line.upper():
                mode = 'coberturas'
                continue
            if ("SERVIÇOS" in line.upper() or "SERVICOS" in line.upper() or "ASSISTÊNCIA" in line.upper() or "ASSISTENCIA" in line.upper()) and "PLANO" in line.upper():
                mode = 'servicos'
                continue
            if "FRANQUIA" in line.upper() and "VIDROS" in line.upper():
                mode = 'franquias_vidros'
                continue
            if "Opções de Pagamento" in line:
                mode = 'pagamento'
                continue
            if "Questionário de Avaliação" in line or "Informações Adicionais" in line:
                mode = None

            if mode == 'coberturas':
                # "Auto - Casco 100 % da Tabela Fipe 1.116,01 3.304,00"
                # "APP- Morte Acidental 5.000,00 20,59 -"
                if not line_strip: continue
                # Regex attempting to separate Description | Limit | Premium
                # Limit can be "100 % da..." or "200.000,00"
                # Look for first Money occurrence (X.XXX,XX)

                # If "Não Contratado"
                if "NÃO CONTRATADO" in line_strip.upper():
                     parts_nc = re.split(r'N[ãa]o Contratado', line_strip, flags=re.IGNORECASE)
                     desc = parts_nc[0].strip()
                     # Clean trailing dashes or numbers
                     desc = re.sub(r'[\d\.\-]*$', '', desc).strip()
                     desc = re.sub(r'[\d\.\-]*$', '', desc).strip()
                     # User wants to hide N/C items to avoid clutter
                     continue

                # Find the premium start (Money at end of line usually, or Limit in middle)
                # Alfa often: "Description Limit Premium"
                # "RCF-V - Danos Materiais 100.000,00 123,45"
                # "Auto - Casco 100 % FIPE 1.234,00"

                # Broad Casco Check
                if "CASCO" in line_strip.upper():
                     # Extract values
                     moneys = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line_strip)
                     # Usually at least 2 values (Prem, Franch) or (Limit?? no Limit is text usually)
                     # Dump: 1116, 3304.

                     # Add coverage
                     # Limit? "100 % FIPE"
                     fipe_m = re.search(r'(\d+\s*%.*?FIPE)', line_strip, re.I)
                     limit = fipe_m.group(1).strip() if fipe_m else "100% FIPE"
                     coberturas.append(("Compreensiva", limit))

                     if len(moneys) >= 1:
                         # Last value is likely franchise (highest usually?)
                         # Or 2nd val.
                         # Dump: 1116, 3304.
                         franquia_val = moneys[-1]

                         found = False
                         for idx, f in enumerate(franquias):
                             if "CASCO" in f.upper():
                                 franquias[idx] = f"{f} - R$ {franquia_val}"
                                 found = True
                                 break
                         if not found:
                              franquias.insert(0, f"Casco: R$ {franquia_val}")
                     continue

                # Check for Percentage Limit (Other than Casco?)
                match_pct = re.search(r'(.*?)\s+(\d+\s*%.*?)\s+[\d\.,]', line_strip)
                if match_pct:
                    desc = match_pct.group(1).strip()
                    limit = match_pct.group(2).strip()
                    if "COBERTURA" not in desc.upper():
                         coberturas.append((desc, limit))
                    continue

                # Check for Money Limit
                # Use regex to find 2 money values? Or 1 money value followed by another?
                # "Desc R$ 50.000,00 R$ 100,00"
                moneys = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line_strip)
                if len(moneys) >= 2:
                     # Suggests Limit + Premium
                     # First money is limit
                     limit = f"R$ {moneys[0]}"
                     # Description is everything before first money
                     # Be careful if description contains digits
                     parts = line_strip.split(moneys[0])
                     desc = parts[0].strip()
                     # Clean clutter
                     desc = re.sub(r'[_\-\.]+$', '', desc).strip()

                     if "COBERTURA" not in desc.upper() and len(desc) > 3:
                          coberturas.append((desc, limit))
                elif len(moneys) == 1:
                     # Could be Limit only or Premium only?
                     # Usually Coverages have a limit.
                     # "Vidros ... R$ 10.000,00"
                     pass

            elif mode == 'servicos':
                # "Assistência - 24 horas Assist. 24h Completo - 400km 117,12 -"
                # "Assistência - Reparo de Lataria Reparo de Lataria 45,60"
                # Clean prefixes
                text_clean = re.sub(r'^(Assistência|Serviços)\s*[-–]\s*', '', line_strip, flags=re.I).strip()

                # Check for cost (optional)
                match_cost = re.search(r'\s+\d{1,3}(?:\.\d{3})*,\d{2}', text_clean)
                if match_cost:
                     text_clean = text_clean[:match_cost.start()].strip()

                # Deduplicate repeated phrases
                words = text_clean.split()
                mid = len(words) // 2
                if mid > 0 and words[:mid] == words[mid:]:
                     text_clean = " ".join(words[:mid])

                # Remove adjacent duplicates
                words = text_clean.split()
                cleaned_words = []
                for w in words:
                     if not cleaned_words or w.lower() != cleaned_words[-1].lower():
                          cleaned_words.append(w)
                text_clean = " ".join(cleaned_words)

                if "Não Contratado" not in text_clean:
                     # Unified mapping logic
                     upper_t = text_clean.upper()
                     orig_upper = line_strip.upper()

                     if "GUINCHO" in upper_t or "REBOQUE" in upper_t:
                          km_m = re.search(r'(\d+)\s*KM', upper_t)
                          if km_m: assistencias.append(f"Guincho {km_m.group(1)} Km")
                          elif "ILIMITADO" in upper_t or "LIVRE" in upper_t: assistencias.append("Guincho Ilimitado")
                          else: assistencias.append(text_clean)
                     elif ("ASSIST" in orig_upper or "24H" in upper_t) and ("KM" in upper_t or "LIVRE" in upper_t or "ILIMITADO" in upper_t):
                          km_m = re.search(r'(\d+)\s*KM', upper_t)
                          if km_m: assistencias.append(f"Guincho {km_m.group(1)} Km")
                          elif "LIVRE" in upper_t or "ILIMITADO" in upper_t: assistencias.append("Guincho Ilimitado")
                          else: assistencias.append(f"Guincho ({text_clean})")
                     elif "CARRO RESERVA" in upper_t:
                          days_m = re.search(r'(\d+)\s*DIAS', upper_t)
                          if days_m: assistencias.append(f"Carro Reserva {days_m.group(1)} Dias")
                          else: assistencias.append(text_clean)
                     else:
                          if len(text_clean) > 3 and "Serviços" not in text_clean:
                               assistencias.append(text_clean)

            elif mode == 'franquias_vidros':
                # "Para-brisa 325,00 Lanterna Led 530,00"
                if "Reparos Referenciada" in line_strip: continue

                # Find all pairs of Name + Value
                # Non-greedy name, Value with comma
                # Allow accents in name: unicode chars or broad dot
                matches = re.findall(r'([A-Za-z0-9\s\/\-\(\)\u00C0-\u00FF]+?)\s+(\d{1,3}(?:\.\d{3})*,\d{2})', line_strip)
                if matches:
                     for name, val in matches:
                          clean_name = name.strip()
                          if len(clean_name) > 2:
                               franquias.append(f"{clean_name}: R$ {val}")
                else:
                     # Check if line has just one unparsed item or text
                     if len(line_strip) > 3 and "Franquia" not in line_strip:
                          franquias.append(line_strip)



        # Store detailed lists
        # We need to map to self.data standard or new fields?
        # For now, put in coberturas as tuples, distinction by name
        self.data["coberturas"] = coberturas
        self.data["assistencias"] = assistencias  # New field, need to ensure Generator handles it or we merge
        self.data["franquias_lista"] = franquias # New field

        # Pagamento
        # Parse table lines manually for best accuracy
        linhas_pag = re.findall(r'^(\d+)\s+Sem juros\s+(.*)$', text, re.MULTILINE)

        vista_val = None
        max_inst = 0
        max_val = None

        for parc_str, rest in linhas_pag:
             parc = int(parc_str)
             vals = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', rest)
             if not vals: continue

             # Headers imply: Ficha | Débito | Cartão
             # Usually Ficha is first and cheapest.
             val_ficha = vals[0]

             if parc == 1:
                  vista_val = val_ficha

             if parc > max_inst:
                  max_inst = parc
                  max_val = vals[-1] # Usually Cartão allows more installments or same?
                  # If we want the *cheapest* max installment, maybe use vals[0].
                  # But usually "Max Installments" is credit card specific.
                  # Let's check line 88/89.
                  # 10x is available.
                  # If we use vals[0] (Ficha), does it exist for 10x?
                  # Dump Line 98: "10 Sem juros 410,13" -> Only one value?
                  # Line 88: "1 Sem juros 3.934,74 4.100,94" (2 values)
                  # It seems columns merge.
                  # If only 1 value, use it.
                  max_val = vals[0]

        if vista_val:
             self.data["pagamento_opcoes"].append({
                 "tipo": "À Vista",
                 "parcelas": "1x",
                 "valor": f"R$ {vista_val}"
             })

        if max_inst > 1 and max_val:
             self.data["pagamento_opcoes"].append({
                 "tipo": "Cartão de Crédito",
                 "parcelas": f"{max_inst}x",
                 "valor": f"R$ {max_val}"
             })

        # Logic for Debit (Ficha) - Usually Column 0
        # Check if we have valid max debit installment
        # Reparse to find max parcel for Ficha/Debit specifically
        max_debit_p = 0
        max_debit_v = None

        for parc_str, rest in linhas_pag:
            parc = int(parc_str)
            vals = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', rest)
            if vals:
                 val_ficha = vals[0]
                 # Assume Ficha/Debit is available if listed?
                 # Avoid 1x (already covered by Vista)
                 # Cap at 6x (User feedback: Alfa nao oferece 10x)
                 if parc > 1 and parc <= 6:
                     if parc > max_debit_p:
                         max_debit_p = parc
                         max_debit_v = val_ficha

        if max_debit_p > 1 and max_debit_v:
             self.data["pagamento_opcoes"].append({
                 "tipo": "Débito em Conta",
                 "parcelas": f"{max_debit_p}x",
                 "valor": f"R$ {max_debit_v}"
             })

        self._apply_casing()
        return self.data
