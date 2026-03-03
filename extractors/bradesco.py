import re
from .base import BaseExtractor


class BradescoExtractor(BaseExtractor):
    def extract(self):
        self.data['insurer'] = 'BRADESCO'
        text = self.full_text



        # --- Basic Info ---
        # "Nome: RAFAEL BARBIERI" under DADOS DO PROPONENTE
        self.data["segurado"] = self._find_value_after_keyword(text, "Nome:", ["Vigência", "CPF"])
        if not self.data["segurado"]:
             cand = self._find_value_after_keyword(text, "DADOS DO PROPONENTE", ["\n"])
             if cand: self.data["segurado"] = cand.replace("Nome:", "").strip()
             else: self.data["segurado"] = "N/D"

        # "Vigência: das 24h de 03/01/2026 às 24h de 03/01/2027"
        vig_match = re.search(r'Vigência:.*?(\d{2}/\d{2}/\d{4}).*?(\d{2}/\d{2}/\d{4})', text, re.I | re.S)
        if vig_match:
             self.data["vigencia"] = f"{vig_match.group(1)} a {vig_match.group(2)}"

        # "Tipo do Veículo:Ecosport..."
        veiculo_match = re.search(r'Tipo do Veículo:\s*(.*?)(?:Chassi|Data)', text, re.I)
        if veiculo_match:
             self.data["veiculo"] = veiculo_match.group(1).strip()

        self.data["cep_pernoite"] = self._find_value_after_keyword(text, "CEP de Pernoite:", ["\n", "Bônus"]) or "N/D"
        self.data["uso"] = self._find_value_after_keyword(text, "Uso Veículo:", ["\n", "Chassi"]) or "N/D"

        # --- Coberturas & Franquias ---
        coberturas = []
        franquias_lista = []

        lines = text.split('\n')
        mode = None
        for line in lines:
            ls = line.strip()
            # Headers
            if "LIMITES MÁXIMOS DE INDENIZAÇÃO" in ls: mode = "coberturas"
            elif "FRANQUIAS (R$)" in ls: mode = "franquias"
            elif "PRÊMIOS (R$)" in ls: mode = "premios"
            elif "PAGAMENTO (R$)" in ls: mode = "pagamento_table"

            # Global Clause Scan (running always)
            if "Vidro Protegido" in ls:
                 if not any(c[0] == "Vidros" for c in coberturas):
                      coberturas.append(("Vidros", "Contratado"))
            if "Assist Auto" in ls or "Assist Dia" in ls or "Assistência" in ls:
                 if not any(c[0] == "Assistência" for c in coberturas):
                     match_ast = re.search(r'\(\d+\)\s*(Assist.*?)(?:\(\d+\)|$)', ls)
                     if match_ast:
                          raw_val = match_ast.group(1).strip()
                          # Extract the description parts: "Assist Auto Dia/Noite - Passeio 400 KM"
                          # Keep Dia/Noite info and km
                          km_m = re.search(r'(\d+)\s*[Kk][Mm]', raw_val)
                          has_dia_noite = "Dia" in raw_val and "Noite" in raw_val
                          if "Ilimitado" in raw_val:
                               final_val = "Guincho Ilimitado"
                          elif km_m and has_dia_noite:
                               final_val = f"Assist Dia/Noite {km_m.group(1)}Km"
                          elif km_m:
                               final_val = f"Guincho {km_m.group(1)} Km"
                          else:
                               final_val = raw_val

                          coberturas.append(("Assistência", final_val))
            if "Auto Reserva" in ls or "Carro Reserva" in ls:
                 if not any(c[0] == "Carro Reserva" for c in coberturas):
                      match_cr = re.search(r'(?:Auto|Carro) Reserva.*?(\d+\s*Dias)', ls, re.IGNORECASE)
                      if match_cr:
                           days = int(re.search(r'\d+', match_cr.group(1)).group(0))
                           coberturas.append(("Carro Reserva", f"{days} Dias"))
                      else:
                           if "Não Contratado" not in ls:
                                coberturas.append(("Carro Reserva", "Contratado"))

            if mode == "coberturas":
                if "D.M.:" in ls:
                    dm = re.search(r'D\.M\.:\s*([\d\.,]+)', ls)
                    if dm: coberturas.append(("Danos Materiais", f"R$ {dm.group(1)}"))
                if "D.C.:" in ls:
                    dc = re.search(r'D\.C\.:\s*([\d\.,]+)', ls)
                    if dc: coberturas.append(("Danos Corporais", f"R$ {dc.group(1)}"))
                if "D. Morais" in ls:
                    dmor = re.search(r'D\. Morais\.?:\s*([\d\.,]+)', ls)
                    if dmor: coberturas.append(("Danos Morais", f"R$ {dmor.group(1)}"))
                if "APP" in ls and "Morte" in ls:
                    morte = re.search(r'Morte[\w\s\/]*:\s*([\d\.,]+)', ls)
                    if morte: coberturas.append(("APP Morte", f"R$ {morte.group(1)}"))
                if "APP" in ls and "Invalidez" in ls:
                    inv = re.search(r'Invalidez[\w\s\/]*:\s*([\d\.,]+)', ls)
                    if inv: coberturas.append(("APP Invalidez", f"R$ {inv.group(1)}"))
                # APP em linhas separadas: "Morte p/ Passageiro: 5.000,00"
                if "Morte" in ls and "Passageiro" in ls and not any(c[0] == "APP Morte" for c in coberturas):
                    morte = re.search(r'Morte\s*p/\s*Passageiro:\s*([\d\.,]+)', ls)
                    if morte: coberturas.append(("APP Morte", f"R$ {morte.group(1)}"))
                if "Invalidez" in ls and "Passageiro" in ls and not any(c[0] == "APP Invalidez" for c in coberturas):
                    inv = re.search(r'Invalidez\s*p/\s*Passageiro:\s*([\d\.,]+)', ls)
                    if inv: coberturas.append(("APP Invalidez", f"R$ {inv.group(1)}"))

                if "Fator de Ajuste:" in ls:
                     fator = re.search(r'Fator de Ajuste:\s*([\d\.,]+)', ls)
                     if fator:
                          val_f = float(fator.group(1).replace(",", "."))
                          if val_f > 0:
                               coberturas.insert(0, ("Compreensiva", f"{fator.group(1)}% FIPE"))

            elif mode == "franquias":
                if "Veículo:" in ls:
                     v_franq = re.search(r'Veículo:\s*([\d\.,]+)\s*(\(.*?\))?', ls)
                     if v_franq:
                          val = v_franq.group(1)
                          type_label = v_franq.group(2) if v_franq.group(2) else ""
                          label = f"Casco {type_label}".strip()
                          franquias_lista.append(f"{label}: R$ {val}")

                keywords = ["Para-Brisa", "Vidro Traseiro", "Lanternas", "Faróis", "Retrovisores", "Repare Fácil", "Reparo Rápido", "Super Martelinho"]
                for kw in keywords:
                    if kw in ls:
                        kw_match = re.search(rf'{re.escape(kw)}.*?\:\s*([\d\.,]+)', ls)
                        if kw_match:
                             # Skip items with zero value (not contracted)
                             val_str = kw_match.group(1).replace(".", "").replace(",", ".")
                             try:
                                 if float(val_str) == 0:
                                     continue
                             except ValueError:
                                 pass
                             franquias_lista.append(f"{kw}: R$ {kw_match.group(1)}")

            elif mode == "premios":
                if "TOTAL A PAGAR:" in ls:
                     total = re.search(r'TOTAL A PAGAR:\s*([\d\.,]+)', ls)
                     if total: self.data["premio_total"] = f"R$ {total.group(1)}"

        # --- Condutor 18-25 Anos ---
        cond_18_25_match = re.search(
            r'CONDUTOR\s+ENTRE\s+18\s+E\s+25\s+ANOS.*?R\.:\s*(Sim|S[íi]m|N[ãa]o|Não)',
            text, re.IGNORECASE | re.DOTALL
        )
        if cond_18_25_match:
            resposta = cond_18_25_match.group(1).strip()
            if resposta.upper().startswith('S'):
                valor = "Sim"
            else:
                valor = "Não"
            if not any(c[0] == "Condutor 18-25 anos" for c in coberturas):
                coberturas.append(("Condutor 18-25 anos", valor))

        self.data["coberturas"] = coberturas
        self.data["franquias_lista"] = franquias_lista

        # --- Pagamento ---
        pag_opcoes = []
        started_table = False
        max_inst = 0
        best_v = None

        max_credit = 0
        best_credit_v = None

        max_debit = 0
        best_debit_v = None

        for line in lines:
            if "PAGAMENTO (R$)" in line:
                started_table = True
                continue
            if started_table:
                if "QUESTIONÁRIO" in line: break

                vals = re.findall(r'(\d+[\d\.,]*,\d{2})', line)
                if not vals: continue

                parcel_match = re.match(r'(\d+)x', line.strip())
                if parcel_match:
                    p_int = int(parcel_match.group(1))

                    if len(vals) >= 6:
                        val_credit = vals[4]
                        val_debit = vals[0]

                        if p_int == 1:
                             pag_opcoes.append({"tipo": "À Vista", "parcelas": "1x", "valor": f"R$ {val_debit}"})

                        if p_int > max_credit:
                             max_credit = p_int
                             best_credit_v = val_credit

                        if p_int <= 6 and p_int > max_debit:
                             max_debit = p_int
                             best_debit_v = val_debit

        if max_credit > 1:
             pag_opcoes.append({"tipo": "Cartão de Crédito", "parcelas": f"{max_credit}x", "valor": f"R$ {best_credit_v}"})

        if max_debit > 1:
             pag_opcoes.append({"tipo": "Débito em Conta", "parcelas": f"{max_debit}x", "valor": f"R$ {best_debit_v}"})

        # Condutor
        self.data["condutor"] = self._find_value_after_keyword(text, "Condutor:", ["CPF", "Data", "Estado"])
        if not self.data["condutor"]:
             match_header = re.search(r'DADOS DO CONDUTOR\s*Nome:\s*(.*?)(?:CPF|Data)', text, re.IGNORECASE)
             if match_header:
                  self.data["condutor"] = match_header.group(1).strip()
             else:
                  # Try "Características do principal condutor" section (page 3)
                  match_princ = re.search(
                      r'(?:Caracter.sticas|CARACTER.STICAS)\s+do\s+principal\s+condutor\s*(?:\n\s*)*Nome:\s*(.*?)(?:\n|CPF|Data)',
                      text, re.IGNORECASE
                  )
                  if match_princ:
                       self.data["condutor"] = match_princ.group(1).strip()
                  else:
                       self.data["condutor"] = self.data["segurado"]

        self.data["pagamento_opcoes"] = pag_opcoes

        self.data["placa"] = self._extract_placa_generic(text)
        self._apply_casing()
        return self.data
