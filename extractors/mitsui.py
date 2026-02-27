import re
from .base import BaseExtractor


class MitsuiExtractor(BaseExtractor):
    def extract(self):
        self.data['insurer'] = 'MITSUI'
        text = self.full_text
        lines = text.split('\n')

        # --- Basic Data ---
        self.data["segurado"] = self._find_value_next_line(text, "Proponente / Segurado", 3)
        if self.data["segurado"]:
             self.data["segurado"] = re.sub(r'\d{2}/\d{2}/\d{4}.*', '', self.data["segurado"]).strip()

        if not self.data["segurado"] or self.data["segurado"] == "N/D":
             self.data["segurado"] = self._find_value_after_keyword(text, "Segurado") or \
                                     self._find_value_next_line(text, "Segurado") or "N/D"

        cond_match = re.search(r'Nome do principal Condutor:\s*(.*?)(?:CPF|:|\n)', text, re.IGNORECASE)
        self.data["condutor"] = cond_match.group(1).strip() if cond_match else self.data["segurado"]

        vig_match = re.search(r'(\d{2}/\d{2}/\d{4})\s*até\s*[\w\s]*(\d{2}/\d{2}/\d{4})', text)
        if vig_match:
             self.data["vigencia"] = f"{vig_match.group(1)} a {vig_match.group(2)}"

        self.data["tipo_seguro"] = "Renovação" if "RENOVAÇÃO" in text.upper() else "Seguro Novo"

        veiculo_match = re.search(r'\d+\s+-\s+-\s+(.*?)(?:\s+\d{4}\s*/\s*\d{4})', text)
        if veiculo_match:
             self.data["veiculo"] = veiculo_match.group(1).strip()
        else:
             self.data["veiculo"] = self._find_value_after_keyword(text, "Veículo:", "Portas") or "N/D"

        self.data["cep_pernoite"] = self._find_value_after_keyword(text, "CEP PERNOITE:", ["\n", "Tipo"]) or "N/D"
        self.data["uso"] = self._find_value_after_keyword(text, "Tipo do Uso:", ["\n", "Possui"]) or "N/D"

        # --- Coberturas & Franquias ---
        coberturas = []
        franquias_lista = []
        assistencias = []

        mode = None
        for line in lines:
            line_upper = line.upper()

            # Mode switching
            if "COBERTURA" in line_upper and ("AUTO" in line_upper or "RCF" in line_upper or "LIMITE" in line_upper):
                mode = "coberturas_table"
                continue
            elif any(x in line_upper for x in ["ADICIONAIS", "SERVIÇO", "SERVICO", "ASSISTÊNCIA", "ASSISTENCIA", "SOCORRO", "REBOQUE"]):
                mode = "assistencias"
                continue
            elif any(x in line_upper for x in ["DESCONTOS APLICADOS", "PRÊMIO TOTAL", "DADOS PARA COBRANÇA"]):
                mode = None

            if mode == "coberturas_table":
                if "COBERTURAS" in line_upper or "LMI" in line_upper: continue

                # 1. Compreensiva
                if "COMPREENSIVA" in line_upper:
                     # Capture 100% or 100.00%
                     match_fipe = re.search(r'(\d+(?:\.\d+)?%)\s*FIPE', line, re.I)
                     if not match_fipe: match_fipe = re.search(r'(\d+(?:\.\d+)%)', line)

                     val = match_fipe.group(1) if match_fipe else "100% FIPE"
                     if "%" in val and "FIPE" not in val.upper(): val += " FIPE"
                     coberturas.append(("Compreensiva", val))

                     # Capture Franquia (first money value)
                     match_money = re.search(r'R\$\s*([\d\.,]+)', line)
                     if match_money:
                          fr_val = f"R$ {match_money.group(1)}"
                          franquias_lista.append(f"Casco: {fr_val}")
                          self.data["franquia"] = fr_val

                # 2. RCF (Supports "DANOS MATERIAIS" and "RCF - DANOS MATERIAIS")
                elif "DANOS MATERIAIS" in line_upper:
                     vals = re.findall(r'R\$\s*([\d\.,]+)', line)
                     if vals: coberturas.append(("Danos Materiais", f"R$ {vals[0]}"))
                elif "DANOS CORPORAIS" in line_upper:
                     vals = re.findall(r'R\$\s*([\d\.,]+)', line)
                     if vals: coberturas.append(("Danos Corporais", f"R$ {vals[0]}"))
                elif "DANOS MORAIS" in line_upper:
                     vals = re.findall(r'R\$\s*([\d\.,]+)', line)
                     if vals: coberturas.append(("Danos Morais", f"R$ {vals[0]}"))

                # 3. APP
                elif "ACIDENTES PESSOAIS" in line_upper:
                     vals = re.findall(r'R\$\s*([\d\.,]+)', line)
                     if vals: coberturas.append(("APP Morte/Invalidez", f"R$ {vals[0]}"))

                # 4. Vidros
                elif "VIDROS" in line_upper and "REFERENCIADA" in line_upper:
                     coberturas.append(("Vidros", "Consulte tabela Franquias"))

                # 5. Guincho (if in main table)
                elif any(kw in line_upper for kw in ["GUINCHO", "SOCORRO", "REBOQUE", "ASSISTÊNCIA", "ASSISTENCIA"]) and "EXTENSÃO" not in line_upper:
                     km_m = re.search(r'(\d+)\s*K[Mm]', line_upper)
                     val = "Ilimitado" if "ILIMITADO" in line_upper or "LIVRE" in line_upper else (f"{km_m.group(1)} Km" if km_m else "Contratado")
                     if not any(c[0] == "Guincho" for c in coberturas):
                          coberturas.append(("Guincho", f"Guincho {val}"))

            elif mode == "assistencias":
                # Match lines like "34 - REDE REFERENCIADA - 400KM Gratuita" or just "REBOQUE"
                # Remove restrictive "Gratuita" or "R$" filter to capture all services

                # Stop if Header
                if "COBERTURA" in line_upper or "LIMITE" in line_upper or "PRÊMIO" in line_upper: continue

                # Extract description
                # Strip potential trailing price or "Gratuita" just for clean desc
                clean = re.sub(r'(Gratuita|R\$\s*[\d\.,]+).*', '', line).strip()
                clean = re.sub(r'^\d+\s*-\s*', '', clean) # Remove ID
                # Clean RCF-V noise
                rcf_pattern = r'R\.?C\.?F\.?\s*[- ]?V?\b\s*[-–—]?\s*'
                clean = re.sub(rcf_pattern, '', clean, flags=re.I).strip()
                clean = re.sub(r'referenciada', '', clean, flags=re.I).strip()
                clean = clean.strip(" -")

                if not clean or len(clean) < 3: continue

                if "CARRO RESERVA" in clean.upper():
                     # Extract days "15 Dias"
                     days_m = re.search(r'(\d+)\s*DIAS', clean, re.I)
                     days = f"{days_m.group(1)} Dias" if days_m else clean
                     if not any(c[0] == "Carro Reserva" for c in coberturas):
                          coberturas.append(("Carro Reserva", days))

                elif any(kw in clean.upper() for kw in ["REDE", "GUINCHO", "SOCORRO", "REBOQUE"]):
                     val = "Guincho"
                     if "ILIMITADO" in clean.upper() or "LIVRE" in clean.upper():
                         val = "Guincho Ilimitado"
                     else:
                         km_m = re.search(r'(\d+)\s*K[Mm]', clean, re.I)
                         if km_m: val = f"Guincho {km_m.group(1)} Km"
                         else: val = f"Guincho ({clean})"

                     if not any(c[0] == "Guincho" for c in coberturas):
                          coberturas.append(("Guincho", val))
                elif "EXTENSÃO" not in clean.upper() and "PERÍMETRO" not in clean.upper() and "CENTRO AUTOMOTIVO" not in clean.upper():
                     if not any(a.upper() == clean.upper() for a in assistencias):
                          assistencias.append(clean)


        # Specific Franchise Block Parsing
        # "*Franquias: Vidros Para-Brisa ... / Vidros Traseiros ... "
        # We need to scan the whole text or lines again for this, as it spans lines within sections

        full_text_oneline = text.replace('\n', ' ')
        # Find start of Franquias block
        # Regex to find block starting with "*Franquias:" until some end condition or next section

        # Method: Iterate lines, if line has *Franquias:, start collecting until next header
        collecting_franquias = False
        franq_buffer = ""

        for line in lines:
            if "*Franquias:" in line:
                collecting_franquias = True
                franq_buffer += line.replace("*Franquias:", "") + " "
                continue

            if collecting_franquias:
                # Stop if we hit a table header line or "LMI" or empty line logic?
                # Dump: Line 82 starts block. Line 85 is "LMI (indenização)..." header.
                if "LMI" in line or "Limite de utilização" in line:
                     collecting_franquias = False
                else:
                     franq_buffer += line + " "

        if franq_buffer:
            # Split by '/'
            parts = franq_buffer.split('/')
            for p in parts:
                p = p.strip()
                if not p: continue
                # "Vidros Para-Brisa ... : R$ 366,00"
                # Extract Name and Value
                # Clean up "Vidros " prefix if redundant? No, keep it.
                if ":" in p:
                     # Clean RCF-V
                     p = re.sub(r'R\.?C\.?F\.?\s*[- ]?V?\b\s*[-–—]?\s*', '', p, flags=re.I).strip()
                     franquias_lista.append(p)

        self.data["coberturas"] = coberturas
        self.data["franquias_lista"] = franquias_lista
        if assistencias:
             self.data["coberturas"].extend([("Assistência", a) for a in assistencias])

        # Final Fallback for Guincho in full text if still missing
        if not any(c[0] == "Guincho" for c in self.data["coberturas"]):
             # Search for common Mitsui Guincho patterns globally
             global_guincho = re.search(r'(?:GUINCHO|REBOQUE|SOCORRO).*?(\d+\s*K[Mm]|ILIMITADO|LIVRE)', text, re.I | re.S)
             if global_guincho:
                  km = global_guincho.group(1).strip()
                  if "ILIMITADO" in km.upper() or "LIVRE" in km.upper():
                       val = "Guincho Ilimitado"
                  else:
                       val = f"Guincho {km}"
                  self.data["coberturas"].append(("Guincho", val))

        # Pagamento
        pag_opcoes = []
        # Reuse Porto Logic or Parse Total
        # Dump Page 4: "Prêmio Total: R$ 2.805,35"
        premio_match = re.search(r'Prêmio Total:\s*R\$\s*([\d\.,]+)', text, re.I)
        if premio_match: self.data["premio_total"] = f"R$ {premio_match.group(1)}"

        # Payment Table (Page 4)
        # "1x ... 12x" columns
        # We want "CARTÃO DE CRÉDITO PORTO BANK SEM DESCONTO" or "DEMAIS BANDEIRAS"
        # Dump: "TODAS CARTÃO DE CRÉDITO - DEMAIS BANDEIRAS" (Line 146)

        # Simplified: Look for 4 columns of data.
        # Line 150: "2.524,76 1.402,67 ..."

        # ... (Reuse Porto Logic or Simplified) ...
        # Scan for "Parcelas" pattern

        # Let's use a robust generic parser for "Nx R$ Value" if present
        # In Mitsui dump, it is "1x ... 12x" header then value rows below.

        # Try to capture "À Vista" explicitly
        vals = re.findall(r'R\$\s*([\d\.,]+)', text)
        if vals and not self.data["premio_total"]: self.data["premio_total"] = f"R$ {vals[-1]}"

        # Basic 1x and max installment detection
        # Logic: Find unique monetary values associated with 'x' or table
        # Since Mitsui dump is complex table, let's stick to generic or "A Vista" for now to avoid breaking.
        pag_opcoes.append({"tipo": "À Vista", "parcelas": "1x", "valor": self.data["premio_total"]})

        self.data["pagamento_opcoes"] = pag_opcoes
        self.data["placa"] = self._extract_placa_generic(text)
        self._apply_casing()
        return self.data
