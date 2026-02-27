import re
from .base import BaseExtractor


class PortoBaseExtractor(BaseExtractor):
    """Base extractor for Porto Group (Porto, Azul, Itaú, Porto Mitsui).
    Subclasses set self.data['insurer'] before calling _extract_porto_common().
    """

    def _extract_porto_common(self):
        text = self.full_text
        text_upper = text.upper()
        lines = text.split('\n')

        # --- Basic Data ---
        # "Proponente / Segurado(a)"
        self.data["segurado"] = self._find_value_next_line(text, "Proponente / Segurado", 3)
        if self.data["segurado"]:
             # Remove dates if attached (e.g. "Rafael Barbieri 01/01/1980")
             self.data["segurado"] = re.sub(r'\d{2}/\d{2}/\d{4}.*', '', self.data["segurado"]).strip()

        if not self.data["segurado"] or self.data["segurado"] == "N/D":
             # Fallback: look for "Segurado:" inline or next line
             self.data["segurado"] = self._find_value_after_keyword(text, "Segurado") or \
                                     self._find_value_next_line(text, "Segurado") or "N/D"

        cond_match = re.search(r'Nome do principal Condutor:\s*(.*?)(?:CPF|:|\n)', text, re.IGNORECASE)
        self.data["condutor"] = cond_match.group(1).strip() if cond_match else self.data["segurado"]

        # Vigência
        vig_match = re.search(r'Vigência.*?(\d{2}/\d{2}/\d{4}).*?(\d{2}/\d{2}/\d{4})', text, re.I | re.S)
        if vig_match:
             self.data["vigencia"] = f"{vig_match.group(1)} a {vig_match.group(2)}"
        else:
             dates = re.findall(r'(\d{2}/\d{2}/\d{4})', text)
             if len(dates) >= 2: self.data["vigencia"] = f" {dates[0]} a {dates[1]}"

        self.data["tipo_seguro"] = "Renovação" if "RENOVAÇÃO" in text_upper else "Seguro Novo"

        veiculo_match = re.search(r'\d+\s+-\s+-\s+(.*?)(?:\s+\d{4}\s*/\s*\d{4})', text)
        if veiculo_match:
             self.data["veiculo"] = veiculo_match.group(1).strip()
        else:
             self.data["veiculo"] = self._find_value_after_keyword(text, "Veículo:", "Portas") or "N/D"

        self.data["cep_pernoite"] = self._find_value_after_keyword(text, "CEP PERNOITE:", ["\n", "Tipo"]) or "N/D"
        self.data["uso"] = self._find_value_after_keyword(text, "Tipo do Uso:", ["\n", "Possui"]) or "N/D"

        # --- Coberturas, Assistencias & Franquias ---
        coberturas = []
        assistencias = []
        franquias_lista = []

        mode = None
        for line in lines:
            line_upper = line.upper()

            # Mode switching logic
            if "COBERTURA" in line_upper and ("AUTO" in line_upper or "LIMITES" in line_upper or "CASCO" in line_upper):
                mode = "coberturas"
                continue
            elif "ADICIONAIS, SERVIÇOS" in line_upper:
                mode = "assistencias"
                continue
            elif "FRANQUIA" in line_upper and "*FRANQUIA" not in line_upper and "ESPECIFICA" not in line_upper and len(line) < 40 and "R$" not in line:
                mode = "franquias"
                continue

            elif any(x in line_upper for x in ["DESCONTOS APLICADOS", "RESUMO DO PRÊMIO", "PRÊMIO TOTAL LÍQUIDO", "FORMAS DE PAGAMENTO"]):
                mode = None

            if line.strip().startswith("*"):
                continue

            if mode == "coberturas":
                vals = re.findall(r'(\d+[\d\.,]*,\d{2})', line)
                if vals:
                    desc = line.split(vals[0])[0].strip()
                    desc = re.sub(r'[*R\$\-\s]+$', '', desc).strip()
                    desc = re.sub(r'^[-\s\*]+', '', desc).strip()
                    desc = re.sub(r'^\d+\s*-\s*', '', desc).strip()
                    desc = re.sub(r'R\.?C\.?F\.?\s*[- ]?V?\b\s*[-–—]?\s*', '', desc, flags=re.I).strip()

                    core_kws = ["DANOS", "ACIDENTES", "APP", "COMPREENSIVA", "COLISÃO", "ASSISTÊNCIA", "CARRO RESERVA", "REPARO", "MARTELINHO"]
                    is_core = any(kw in desc.upper() for kw in core_kws)

                    franchise_kws = ["VIDRO", "FAROL", "FARÓIS", "RETROVISOR", "LANTERNA", "FRANQUIA", "PARTICIPACAO", "PARTICIPAÇÃO", "NEBLINA", "CUSTOS DE DEFESA"]

                    if not is_core and any(kw in desc.upper() for kw in franchise_kws):
                         if not re.match(r'^\d+\s*-', desc) and "CUSTOS DE DEFESA" not in desc.upper():
                              franquias_lista.append(f"{desc}: R$ {vals[0]}")
                         continue

                    if not desc or len(desc) < 3 or "COBERTURAS" in desc.upper() or "% OFF" in desc:
                        continue

                    if "COMPREENSIVA" in desc.upper():
                         fipe_m = re.search(r'(\d{1,3}(?:\.\d{2})?)\s*%', line)
                         limit = f"{fipe_m.group(1)}% FIPE" if fipe_m else "100.00% FIPE"
                         coberturas.append(("Compreensiva", limit))

                         if "ITAU" in self.data['insurer'] or "ITAÚ" in self.data['insurer']:
                              if len(vals) >= 2:
                                   val = f"R$ {vals[0]}"
                                   self.data["franquia"] = val
                                   franquias_lista.append(f"Casco: {val}")
                              elif len(vals) == 1 and float(vals[0].replace('.', '').replace(',', '.')) > 1000:
                                   pass
                         else:
                              franquias_lista.append(f"Casco (50%): R$ {vals[0]}")

                    elif "DANOS MORAIS" in desc.upper():
                         coberturas.append(("Danos Morais", f"R$ {vals[0]}"))

                    elif "REPARO RÁPIDO" in desc.upper():
                         coberturas.append(("Reparo Rápido", f"R$ {vals[0]}"))

                    else:
                         if "EXTENSÃO" not in desc.upper() and "PERÍMETRO" not in desc.upper():
                              if re.search(r'CARTA\s*VERDE', desc, re.I): continue
                              coberturas.append((desc, f"R$ {vals[0]}"))

            elif mode == "assistencias":
                check_line = line_upper.replace("Ã", "A").replace("Ê", "E").replace("Ú", "U").replace("Ç", "C")

                if ("ASSISTENCIA" in check_line or "ITAU KM" in check_line or "GUINCHO" in check_line or "SOCORRO" in check_line or "REBOQUE" in check_line or "REDE REFERENCIADA" in check_line) and "EXTENSAO" not in check_line:
                     if re.search(r'CARTA\s*VERDE', line_upper, re.I): continue

                     val = "Guincho 24h"

                     m_kw = re.search(r'(ASSIST[EÊ]NCIA|ITA[UÚ].*?KM|ITA[UÚ]\s+ESSENCIAL|GUINCHO|SOCORRO|REBOQUE|REDE REFERENCIADA|PLANO)\s*(.*)', line_upper)
                     if m_kw:
                          cleaned_part = m_kw.group(2).strip()
                          cleaned_part = re.sub(r'24H\s*', '', cleaned_part).strip()
                          cleaned_part = re.sub(r'-\s*REFERENCIADA.*', '', cleaned_part).strip()
                          cleaned_part = re.sub(r'^[-\s\*:]+', '', cleaned_part).strip()
                          cleaned_part = re.sub(r'[-\s\*:]+$', '', cleaned_part).strip()

                          if cleaned_part:
                               if "ILIMITADO" in cleaned_part or "LIVRE" in cleaned_part:
                                    val = "Guincho Ilimitado"
                               elif re.search(r'\d+\s*[Kk][Mm]', cleaned_part):
                                    m_km = re.search(r'(\d+\s*[Kk][Mm])', cleaned_part)
                                    val = f"Guincho {m_km.group(1).title()}"
                               else:
                                    val = f"Guincho {cleaned_part.title()}"
                                    if "ILIMITADO" in line_upper: val = "Guincho Ilimitado"

                     if val == "Guincho": val = "Guincho 24h"

                     if not any(c[0] == "Guincho" for c in coberturas) or val != "Guincho 24h":
                          if any(c[0] == "Guincho" for c in coberturas):
                               coberturas = [c for c in coberturas if c[0] != "Guincho"]
                          coberturas.append(("Guincho", val))
                     continue

                elif "CARRO RESERVA" in line_upper:
                     m_dias = re.search(r'(\d+)\s*DIAS', line_upper)
                     val = "Carro Reserva"
                     if m_dias:
                          days_part = f"{m_dias.group(1)} Dias"
                          clean_line = re.sub(r'CARRO RESERVA|PORTE BÁSICO|REFERENCIADA', '', line_upper).strip()
                          clean_line = re.sub(r'^[-\s\*:]+', '', clean_line).strip()
                          clean_line = re.sub(r'[-\s\*:]+$', '', clean_line).strip()

                          plan_match = re.search(r'(ESSENCIAL|CONFORTO|MASTER|EXECUTIVO)', clean_line)
                          if plan_match:
                               val = f"{plan_match.group(1).title()} {days_part}"
                          else:
                               val = days_part

                     if not any(c[0] == "Carro Reserva" for c in coberturas) or val != "Carro Reserva":
                          if any(c[0] == "Carro Reserva" for c in coberturas):
                               coberturas = [c for c in coberturas if c[0] != "Carro Reserva"]
                          coberturas.append(("Carro Reserva", val))
                     continue

                if "R$" in line and "CARRO RESERVA" not in line_upper and "ASSISTÊNCIA" not in line_upper:
                    desc = line.split("R$")[0].strip()
                    desc = re.sub(r'-\s*REFERENCIADA.*', '', desc, flags=re.I).strip()
                    desc = re.sub(r'^[-\s\*]+', '', desc).strip()
                    if desc and len(desc) > 3 and "SERVIÇOS" not in desc.upper() and "% OFF" not in desc.upper() and "EXTENSÃO" not in desc.upper() and "PERÍMETRO" not in desc.upper():
                        if "REFERENCIADA" in desc.upper() and "GUINCHO" not in desc.upper():
                             continue
                        if re.search(r'CARTA\s*VERDE', desc, re.I): continue
                        assistencias.append(desc)

            elif mode == "franquias":
                core_kws_escape = ["DANOS", "ACIDENTES", "APP", "COMPREENSIVA", "COLISÃO", "REPARO", "MARTELINHO"]
                if any(kw in line_upper for kw in core_kws_escape):
                     mode = "coberturas"
                     vals = re.findall(r'(\d+[\d\.,]*,\d{2})', line)
                     if vals:
                          desc = line.split(vals[0])[0].strip()
                          desc = re.sub(r'[*R\$\-\s]+$', '', desc).strip()
                          desc = re.sub(r'^[-\s\*]+', '', desc).strip()
                          coberturas.append((desc, f"R$ {vals[0]}"))
                          continue

                vals = re.findall(r'(\d+[\d\.,]*,\d{2})', line)
                if vals:
                    desc = line.split(vals[0])[0].strip()
                    desc = re.sub(r'[*R\$\-\s:]+$', '', desc).strip()
                    desc = re.sub(r'^[-\s\*]+', '', desc).strip()

                    if re.match(r'^\d+\s*-', desc):
                         continue

                    if desc and len(desc) > 3:
                        if "CUSTOS DE DEFESA" not in desc.upper():
                            item = f"{desc}: R$ {vals[0]}"
                            if not any(desc.upper() in f.upper() for f in franquias_lista):
                                franquias_lista.append(item)

        # Franquias de Vidros (Multi-line note starting with *Franquias:)
        notes_text = ""
        found_notes = False
        for line in lines:
            if "*Franquias:" in line:
                found_notes = True
                notes_text += line + " "
                continue
            if found_notes:
                if "/" in line or ":" in line or "R$" in line:
                    notes_text += line + " "
                else:
                    found_notes = False

        if notes_text:
             parts = re.split(r'(\d+[\d\.,]*,\d{2})', notes_text)
             for i in range(0, len(parts)-1, 2):
                  d = parts[i].strip()
                  v = parts[i+1].strip()
                  d_clean = re.sub(r'.*?Franquias?[:\s]*', '', d, flags=re.I).strip()
                  d_clean = re.sub(r'^[*,/\s]+', '', d_clean).strip()
                  d_clean = re.sub(r'[:R\$\s\-]+$', '', d_clean).strip()
                  if d_clean and len(d_clean) > 2:
                       item = f"{d_clean}: R$ {v}"
                       if not any(d_clean.upper() in f.upper() for f in franquias_lista):
                            franquias_lista.append(item)

        if "100% Fipe" in text:
             coberturas.insert(0, ("Compreensiva", "100% FIPE"))

        self.data["coberturas"] = coberturas
        self.data["franquias_lista"] = franquias_lista
        if assistencias:
             self.data["coberturas"].extend([("Assistência", a) for a in assistencias])

        # Final Fallback for Guincho in full text if still missing
        if not any(c[0] == "Guincho" for c in self.data["coberturas"]):
             global_guincho = re.search(r'(?:GUINCHO|REBOQUE|SOCORRO|ITA[UÚ].*?KM|ITA[UÚ]\s+ESSENCIAL|ASSIST[EÊ]NCIA).*?(\d+\s*K[Mm]|ILIMITADO|LIVRE)', text, re.I)
             if global_guincho:
                  km = global_guincho.group(1).strip()
                  if "ILIMITADO" in km.upper() or "LIVRE" in km.upper():
                       val = "Guincho Ilimitado"
                  else:
                       val = f"Guincho {km}"
                  self.data["coberturas"].append(("Guincho", val))

        # Pagamento
        pag_opcoes = []

        # Total
        premio_match = re.search(r'Prêmio Total:\s*R\$\s*([\d\.,]+)', text, re.IGNORECASE)
        if premio_match: self.data["premio_total"] = f"R$ {premio_match.group(1)}"

        target_block_header = "DEMAIS BANDEIRAS"

        found_block = False
        max_credit = 0
        best_credit_v = None
        max_debit = 0
        best_debit_v = None

        lines_iter = iter(lines)
        for line in lines_iter:
             if target_block_header in line.upper():
                  found_block = True

             if found_block and "1x" in line and "2x" in line:
                  try:
                       val_line = next(lines_iter)
                       if "R$ R$" in val_line: val_line = next(lines_iter)

                       vals = re.findall(r'([\d\.,]+)', val_line.replace('R$', '').strip())
                       if not vals:
                            val_line = next(lines_iter)
                            vals = re.findall(r'([\d\.,]+)', val_line.replace('R$', '').strip())

                       interest_line = next(lines_iter)
                       while "juros" not in interest_line.lower():
                            if "1x" in interest_line or "R$" in interest_line: break
                            interest_line = next(lines_iter)

                       cols = re.findall(r'(\d+)x', line)
                       interest_count = interest_line.lower().count("s/juros") + interest_line.lower().count("sem juros")

                       if interest_count > 0:
                            count_valid = min(len(cols), interest_count)
                            for i in range(count_valid):
                                 inst_num = int(cols[i])
                                 if i < len(vals):
                                      curr_val = vals[i]
                                      if inst_num > max_credit:
                                           max_credit = inst_num
                                           best_credit_v = curr_val
                                      limit = 10 if self.data.get("insurer") in ["ITAU", "MITSUI"] else 6
                                      if inst_num <= limit and inst_num > max_debit:
                                           max_debit = inst_num
                                           best_debit_v = curr_val
                       else:
                            total_f = 0.0
                            if "premio_total" in self.data:
                                 try:
                                     total_str = self.data["premio_total"].replace("R$","").strip().replace(".","").replace(",",".")
                                     total_f = float(total_str)
                                 except: pass

                            limit = min(len(cols), len(vals))
                            for i in range(limit):
                                 inst_num = int(cols[i])
                                 val_str = vals[i]
                                 try:
                                     val_f = float(val_str.replace(".","").replace(",","."))
                                     calc = inst_num * val_f

                                     is_free = False
                                     if total_f > 0 and abs(calc - total_f) < (total_f * 0.05):
                                          is_free = True
                                     elif inst_num == 1:
                                          is_free = True
                                          if total_f == 0: total_f = val_f

                                     if is_free:
                                          if inst_num > max_credit:
                                               max_credit = inst_num
                                               best_credit_v = val_str
                                          limit = 10 if self.data.get("insurer") in ["ITAU", "MITSUI"] else 6
                                          if inst_num <= limit and inst_num > max_debit:
                                               max_debit = inst_num
                                               best_debit_v = val_str
                                 except: pass

                       if max_credit > 0:
                            break

                  except StopIteration:
                       break

        if max_credit == 0:
             lines_iter = iter(lines)
             for line in lines_iter:
                  if "1x" in line and "2x" in line:
                       try:
                            val_line = next(lines_iter)
                            if "R$ R$" in val_line: val_line = next(lines_iter)

                            vals = re.findall(r'([\d\.,]+)', val_line.replace('R$', '').strip())
                            if not vals:
                                 val_line = next(lines_iter)
                                 vals = re.findall(r'([\d\.,]+)', val_line.replace('R$', '').strip())

                            interest_line = next(lines_iter)
                            while "juros" not in interest_line.lower():
                                 if "1x" in interest_line or "R$" in interest_line: break
                                 interest_line = next(lines_iter)

                            cols = re.findall(r'(\d+)x', line)
                            interest_count = interest_line.lower().count("s/juros") + interest_line.lower().count("sem juros")

                            if interest_count > 0:
                                 count_valid = min(len(cols), interest_count)
                                 for i in range(count_valid):
                                      inst_num = int(cols[i])
                                      if i < len(vals):
                                           curr_val = vals[i]
                                           if inst_num > max_credit:
                                                max_credit = inst_num
                                                best_credit_v = curr_val
                                           limit = 10 if self.data.get("insurer") in ["ITAU", "MITSUI"] else 6
                                           if inst_num <= limit and inst_num > max_debit:
                                                max_debit = inst_num
                                                best_debit_v = curr_val
                            else:
                                 total_f = 0.0
                                 if "premio_total" in self.data:
                                      try:
                                          total_str = self.data["premio_total"].replace("R$","").strip().replace(".","").replace(",",".")
                                          total_f = float(total_str)
                                      except: pass

                                 limit = min(len(cols), len(vals))
                                 for i in range(limit):
                                      inst_num = int(cols[i])
                                      val_str = vals[i]
                                      try:
                                          val_f = float(val_str.replace(".","").replace(",","."))
                                          calc = inst_num * val_f

                                          is_free = False
                                          if total_f > 0 and abs(calc - total_f) < (total_f * 0.05):
                                               is_free = True
                                          elif inst_num == 1:
                                               is_free = True
                                               if total_f == 0: total_f = val_f

                                          if is_free:
                                               if inst_num > max_credit:
                                                    max_credit = inst_num
                                                    best_credit_v = val_str
                                               limit = 10 if self.data.get("insurer") in ["ITAU", "MITSUI"] else 6
                                               if inst_num <= limit and inst_num > max_debit:
                                                    max_debit = inst_num
                                                    best_debit_v = val_str
                                      except: pass

                       except StopIteration:
                            break

        if max_credit > 0 and best_credit_v:
             pag_opcoes.append({"tipo": "Cartão de Crédito", "parcelas": f"{max_credit}x", "valor": f"R$ {best_credit_v}"})

        if max_debit > 0 and best_debit_v:
             pag_opcoes.append({"tipo": "Débito em Conta", "parcelas": f"{max_debit}x", "valor": f"R$ {best_debit_v}"})

        # Add Vista
        vista_match = re.search(r'Boleto\s+À\s+vista\s+R\$\s*([\d\.,]+)', text, re.IGNORECASE)
        if vista_match:
             pag_opcoes.insert(0, {"tipo": "À Vista", "parcelas": "1x", "valor": f"R$ {vista_match.group(1)}"})
        elif "premio_total" in self.data:
              pag_opcoes.insert(0, {"tipo": "À Vista", "parcelas": "1x", "valor": self.data["premio_total"]})

        self.data["pagamento_opcoes"] = pag_opcoes

        self.data["placa"] = self._extract_placa_generic(text)
        self._apply_casing()
        return self.data


class PortoExtractor(PortoBaseExtractor):
    def extract(self):
        self.data['insurer'] = 'PORTO'
        return self._extract_porto_common()


# Backward compatibility alias
PortoGroupExtractor = PortoExtractor
