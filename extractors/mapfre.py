import re
from .base import BaseExtractor


class MapfreExtractor(BaseExtractor):
    def extract(self):
        self.data['insurer'] = 'MAPFRE'
        text = self.full_text
        lines = text.split('\n')

        # --- Basic Data ---
        # Segurado:RAFAEL BARBIERI CPF/CNPJ:000...
        self.data["segurado"] = self._find_value_after_keyword(text, "Segurado:", "CPF") or "N/D"

        # Veículo:21;26;23; FD214222 FORD - ECOSPORT...
        veic_line = self._find_value_after_keyword(text, "Veículo:", "Ano Modelo")
        if veic_line:
             # Remove codes like "21;26;23; FD214222 "
             veic_cleaned = re.sub(r'^[\d;]+\s+[A-Z0-9]+\s+', '', veic_line).strip()
             self.data["veiculo"] = veic_cleaned

        # Vigência: das 24 horas do dia 03/01/2026até as 24 horas do dia 03/01/2027
        vig_match = re.search(r'Vigência:.*?(\d{2}/\d{2}/\d{4}).*?(\d{2}/\d{2}/\d{4})', text, re.IGNORECASE)
        if vig_match:
             self.data["vigencia"] = f"{vig_match.group(1)} a {vig_match.group(2)}"

        # Condutor / Uso / CEP
        # - Nome do Principal Condutor:RAFAEL BARBIERI
        cond_match = re.search(r'Nome do Principal Condutor:(.*?)(?:\n|$)', text, re.I)
        if cond_match: self.data["condutor"] = cond_match.group(1).strip()

        uso_match = re.search(r'Uso:(\d+\s*-\s*.*?)(?:\n|Tipo)', text, re.I)
        if uso_match: self.data["uso"] = uso_match.group(1).strip()

        cep_match = re.search(r'CEP\s+de\s+pernoite.*?:?\s*(\d{5}-?\d{3})', text, re.I)
        if cep_match: self.data["cep_pernoite"] = cep_match.group(1).strip()

        # --- Coberturas & Franquias ---
        coberturas = []
        franquias_lista = []

        assistencia_entry = None
        ext_reboque_entry = None
        mode = None
        for line in lines:
            line_upper = line.strip().upper()
            if "COBERTURAS LIM. MÁX." in line_upper:
                mode = "coberturas"
                continue
            elif "FRANQUIA(S) VALOR" in line_upper:
                mode = "franquias"
                continue
            elif "PRÊMIOS" in line_upper and "TOTAL" in line_upper: # Section break
                mode = None
            elif "FORMAS DE PAGAMENTO" in line_upper:
                mode = None

            if mode == "coberturas":
                # Filter unwanted
                if "COBERTURAS" in line_upper or "LIM. MÁX" in line_upper: continue
                if "CARTA VERDE" in line_upper: continue

                if "100% FIPE" in line_upper:
                     coberturas.append(("Compreensiva", "100% FIPE"))
                elif "DANOS MATERIAIS" in line_upper:
                     val = re.search(r'([\d\.,]+)', line)
                     if val: coberturas.append(("Danos Materiais", f"R$ {val.group(1)}"))
                elif "DANOS CORPORAIS" in line_upper:
                     val = re.search(r'([\d\.,]+)', line)
                     if val: coberturas.append(("Danos Corporais", f"R$ {val.group(1)}"))
                elif "DANOS MORAIS" in line_upper:
                     val = re.search(r'([\d\.,]+)', line)
                     if val: coberturas.append(("Danos Morais", f"R$ {val.group(1)}"))
                elif "APP - MORTE" in line_upper:
                     val = re.search(r'([\d\.,]+)', line)
                     if val: coberturas.append(("APP Morte", f"R$ {val.group(1)}"))
                elif "APP - INVALIDEZ" in line_upper:
                     val = re.search(r'([\d\.,]+)', line)
                     if val: coberturas.append(("APP Invalidez", f"R$ {val.group(1)}"))
                elif "VIDROS" in line_upper:
                     coberturas.append(("Vidros", "Contratada (Ver Franquias)"))
                elif "CARRO RESERVA" in line_upper:
                     days_match = re.search(r'(\d+)\s*dias', line, re.I)
                     if days_match:
                          coberturas.append(("Carro Reserva", f"{days_match.group(1)} Dias"))
                     else:
                          coberturas.append(("Carro Reserva", "Contratada"))
                elif "ASSISTÊNCIA" in line_upper and "CASA" not in line_upper:
                     assistencia_entry = line
                elif "EXTENSÃO DE REBOQUE" in line_upper:
                     ext_reboque_entry = line
                elif "ASSISTÊNCIA CASA" in line_upper:
                     coberturas.append(("Assistência Casa", "Gratuita"))

            elif mode == "franquias":
                 if "FRANQUIA" in line_upper or re.match(r'^\d', line.strip()): continue

                 val_match = re.search(r'([\d\.,]+)$', line.strip())
                 if val_match:
                      val = val_match.group(1)
                      label = line.replace(val, "").strip()
                      # Normalize label
                      if "CASCO" in label.upper() or "REDUZIDA" in label.upper():
                           fr_text = f"R$ {val}"
                           self.data["franquia"] = fr_text
                           coberturas.append(("Franquia", f"{label.strip()} {fr_text}"))
                           franquias_lista.insert(0, f"Casco: {label.strip()} {fr_text}")
                      else:
                           if "VALOR" not in label.upper() and len(label) > 3:
                                franquias_lista.append(f"{label}: R$ {val}")

        # Resolve Guincho: sum Assistência base km + Extensão de Reboque km
        guincho_val = "Guincho 200 Km (Padrão)"
        base_km = 0
        ext_km = 0

        if assistencia_entry:
             if "ILIMITADO" in assistencia_entry.upper():
                  guincho_val = "Guincho Ilimitado"
                  coberturas.append(("Assistência 24h", guincho_val))
                  assistencia_entry = None  # skip sum logic
             else:
                  km_m = re.search(r'(\d+)\s*(?:KM|km|Km)', assistencia_entry)
                  if km_m: base_km = int(km_m.group(1))

        if ext_reboque_entry:
             if "ILIMITADO" in ext_reboque_entry.upper():
                  guincho_val = "Guincho Ilimitado"
             else:
                  km_m = re.search(r'(\d+)\s*(?:KM|km|Km)', ext_reboque_entry)
                  if km_m: ext_km = int(km_m.group(1))

        # Sum if we have numeric values
        if assistencia_entry is not None:  # not already set to Ilimitado
             total_km = base_km + ext_km
             if total_km > 0:
                  guincho_val = f"Guincho {total_km} Km"

        coberturas.append(("Assistência 24h", guincho_val))

        self.data["coberturas"] = coberturas
        self.data["franquias_lista"] = franquias_lista

        # --- Pagamento ---
        # 4 Columns: Boleto, Debito, Debito+1Boleto, Cartao
        # We want the last column (Cartão) logic.

        pag_opcoes = []

        # Total
        premio_match = re.search(r'Prêmio Total[\s\S]*?([\d\.,]+)(?:\n|$)', text, re.I)
        if premio_match:
             # Ensure it's the right total, usually at bottom of Page 2 or Top of Page 3 intro
             # The dump shows "Prêmio Total ... 2.333,85"
             self.data["premio_total"] = f"R$ {premio_match.group(1)}"

        # Table parsing
        # "1x Sem Juros R$ 2.333,85 ... 1x Sem Juros R$ 2.333,85" (Repeated 4 times)
        # We need to robustly pick the last occurrence in the line for Cartão?

        max_credit = 0
        best_credit_v = None

        max_debit = 0
        best_debit_v = None

        lines_iter = iter(lines)
        for line in lines_iter:
             if "Sem Juros" in line or "Com Juros" in line:
                  # "1x Sem Juros R$ 2.333,85 ... 1x Sem Juros R$ 2.333,85"
                  matches = re.findall(r'(\d+)x\s+(Sem|Com)\s+Juros\s+R\$\s*([\d\.,]+)', line, re.I)

                  if matches:
                       # Credit (Last Col)
                       m_inst, m_type, m_val = matches[-1]
                       inst_num = int(m_inst)
                       if m_type.upper() == "SEM" and inst_num > max_credit:
                            max_credit = inst_num
                            best_credit_v = m_val

                       # Debit (Column 2 usually, Index 1)
                       if len(matches) >= 2:
                            d_inst, d_type, d_val = matches[1]
                            inst_d = int(d_inst)
                            if d_type.upper() == "SEM" and inst_d <= 6 and inst_d > max_debit:
                                 max_debit = inst_d
                                 best_debit_v = d_val

        if max_credit > 0 and best_credit_v:
             pag_opcoes.append({"tipo": "Cartão de Crédito", "parcelas": f"{max_credit}x", "valor": f"R$ {best_credit_v}"})

        if max_debit > 0 and best_debit_v:
             pag_opcoes.append({"tipo": "Débito em Conta", "parcelas": f"{max_debit}x", "valor": f"R$ {best_debit_v}"})

        # À Vista
        # Usually 1x Sem Juros is À Vista too.
        # But Mapfre often splits "À Vista" in boleto column?
        # Let's take 1x from the FIRST match of the line (Boleto)

        # Reset iter for À Vista pass or just assume 1x of max_installments logic if 1x?
        # Better: explicitly search for 1x Boleto

        for line in lines:
             if "1x " in line and "Sem Juros" in line:
                  matches = re.findall(r'1x\s+Sem\s+Juros\s+R\$\s*([\d\.,]+)', line)
                  if matches:
                       # First match is Boleto
                       val_vista = matches[0]
                       pag_opcoes.insert(0, {"tipo": "À Vista", "parcelas": "1x", "valor": f"R$ {val_vista}"})
                       break

        self.data["pagamento_opcoes"] = pag_opcoes

        self._apply_casing()
        return self.data
