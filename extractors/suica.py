import re
from .base import BaseExtractor


class SuicaExtractor(BaseExtractor):
    def extract(self):
        self.data['insurer'] = 'SUICA'
        text = self.full_text
        lines = text.split('\n')

        # --- Basic Data ---
        # "Proponente Nome Social ..."
        # "NILTON JORGE ZATTERA N/A ..."
        # Scan for "Nome Social" or "Proponente" and avoid header lines
        self.data["segurado"] = self._find_value_next_line(text, "Nome Social", lookahead=2)
        if not self.data["segurado"] or "Nome Social" in self.data["segurado"] or "Proponente" in self.data["segurado"]:
             self.data["segurado"] = self._find_value_next_line(text, "Proponente", lookahead=4)

        # Check if we still captured a header
        if self.data["segurado"] and ("Nome Social" in self.data["segurado"] or "CPF" in self.data["segurado"]):
              # Try skipping that line manually?
              # Let's find index of header and take next.
              pass

        if self.data["segurado"]:
             # If it contains header keywords, it's wrong.
             if "Nome Social" in self.data["segurado"] or "CPF/CNPJ" in self.data["segurado"]:
                  # Find this line in text and take next
                  lines = text.split('\n')
                  for i, line in enumerate(lines):
                      if "Nome Social" in line and "CPF" in line:
                           if i+1 < len(lines):
                                self.data["segurado"] = lines[i+1].strip()
                                break

             parts = re.split(r'N/A|\d', self.data["segurado"])
             self.data["segurado"] = parts[0].strip()

        # Vigencia
        vig_match = re.search(r'Vigência do seguro:.*?(\d{2}/\d{2}/\d{4}).*?(\d{2}/\d{2}/\d{4})', text)
        if vig_match:
             self.data["vigencia"] = f"{vig_match.group(1)} a {vig_match.group(2)}"

        # Veiculo
        # Veiculo
        # Dump:
        # "Modelo"
        # "JBN9G10 005483-6 2022 VW - VolksWage"
        # "AMAROK Highline CD 3.0 4x4 TB Dies. Aut."

        veic_final = "N/D"

        # Locate "Modelo" keyword
        lines = text.split('\n')
        model_idx = -1

        # Strategy 1: Find "Modelo" header
        for i, line in enumerate(lines):
             # Check for "Modelo" but be careful not to pick "Ano Modelo"
             if "Modelo" in line and "Ano" not in line:
                  # If line is short, it's likely a column header
                  if len(line.strip()) < 30:
                       model_idx = i
                       break

        # Strategy 2: If header not found, look for Line composed of "Plate FIPE Year Manufacturer"
        # Regex: Plate (7 chars) + digits + Year (4 digits)
        if model_idx == -1:
             prior_regex = re.compile(r'^[A-Z]{3}\d[A-Z0-9]\d{2}\s+\d+-\d\s+\d{4}')
             for i, line in enumerate(lines):
                  if prior_regex.search(line.strip()):
                       model_idx = i - 1 # Pretend previous line is header
                       break

        if model_idx != -1 and model_idx + 1 < len(lines):
             line1 = lines[model_idx+1].strip()
             line1 = lines[model_idx+1].strip()
             line2 = ""

             line1 = lines[model_idx+1].strip()
             line2 = ""

             # Scan next few lines for Model
             # Debug showed Line 34 is header: "Modelo Isenção..."
             # Line 35 is data: "Model... Não ..."

             collected_parts = []
             headers_to_skip = ["ISENÇÃO", "FISCAL", "COMBUSTÍVEL", "TIPO DE UTILIZAÇÃO", "MODELO", "CHASSI"]

             for offset in range(2, 6): # Check line +2, +3, +4, +5
                  if model_idx + offset >= len(lines): break
                  l_candidate = lines[model_idx + offset].strip()
                  if not l_candidate: continue
                  l_upper = l_candidate.upper()

                  # Check if it's the intermediate header line
                  # If it has "Modelo" AND "Isenção", it is 100% header. Skip.
                  if ("MODELO" in l_upper and "ISENÇÃO" in l_upper) or "TIPO DE UTILIZAÇÃO" in l_upper:
                       continue

                  # Check if it's the Data line (contains "Não" or "Sim")
                  # "AMAROK ... Aut. Não ..."
                  if "NÃO" in l_upper or "SIM" in l_upper:
                      # Split and take first part
                      parts = re.split(r'\s+(?:Não|Sim|NÃO|SIM)\b', l_candidate)
                      if parts and len(parts[0]) > 2:
                           collected_parts.append(parts[0].strip())
                      # We found the data line, so we are likely done
                      break

                  # If it stops matching structure or hits another block header
                  if "LOCAL DE RISCO" in l_upper or "DADOS" in l_upper:
                      break

                  collected_parts.append(l_candidate)

             if collected_parts:
                  line2 = " ".join(collected_parts)




             # Clean Line 1
             # Remove Plate
             clean_l1 = re.sub(r'^[A-Z]{3}\d[A-Z0-9]\d{2}\s+', '', line1)
             # Remove FIPE
             clean_l1 = re.sub(r'\s*\d{6}-\d\s+', '', clean_l1)
             # Remove Year
             clean_l1 = re.sub(r'\s*\d{4}\s+', ' ', clean_l1)

             # Brand Cleanup
             # "VW - VolksWage" -> "VW"
             clean_l1 = re.sub(r'VolksWage\w*', '', clean_l1, flags=re.IGNORECASE)
             clean_l1 = re.sub(r'Volkswagen', '', clean_l1, flags=re.IGNORECASE)
             clean_l1 = clean_l1.replace("-", "").strip()

             full_veic = f"{clean_l1} {line2}".strip()

             # Remove booleans if attached
             parts = re.split(r'\s+(?:Não|Sim)\s+', full_veic)
             veic_final = parts[0].strip()

        self.data["veiculo"] = veic_final

        # Condutor
        cond_match = self._find_value_next_line(text, "Principal condutor", lookahead=2)
        if cond_match:
             parts = re.split(r'\d{2}/\d{2}/\d{4}', cond_match)
             self.data["condutor"] = parts[0].strip()
        else:
             self.data["condutor"] = self.data["segurado"]

        # CEP
        cep_line = self._find_value_next_line(text, "CEP de pernoite", lookahead=2)
        if cep_line:
             self.data["cep_pernoite"] = cep_line.strip()

        # Uso
        if "Locomoção diária" in text:
             self.data["uso"] = "Passeio"
        elif "Comercial" in text:
             self.data["uso"] = "Comercial"

        # --- Coberturas ---
        coberturas = []
        franquias_lista = []

        mode = None
        for line in lines:
             l = line.strip()
             if "COBERTURAS" in l:
                  mode = "coberturas"
                  continue
             if "SERVIÇOS" in l:
                  mode = "servicos"
                  continue
             if "FRANQUIA" in l:
                  mode = "franquias_block"
                  continue
             if "OBSERVAÇÕES" in l:
                  mode = None

             if mode == "coberturas":
                  if "100% da tabela FIPE" in l:
                       coberturas.append(("Compreensiva", "100% FIPE"))
                  if "Danos morais" in l:
                       val = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', l)
                       if val: coberturas.append(("Danos Morais", f"R$ {val[0]}"))
                  if "Danos Pessoais" in l:
                       val = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', l)
                       if val: coberturas.append(("Danos Corporais", f"R$ {val[0]}"))
                  if "Danos Materiais" in l:
                       val = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', l)
                       if val: coberturas.append(("Danos Materiais", f"R$ {val[0]}"))
                  if "APP" in l and "Morte" in l:
                       val = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', l)
                       if val: coberturas.append(("APP Morte", f"R$ {val[0]}"))
                  if "APP" in l and "Invalidez" in l:
                       val = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', l)
                       if val: coberturas.append(("APP Invalidez", f"R$ {val[0]}"))

             elif mode == "servicos":
                  if "Assistência 24 horas" in l: continue
                  if "Pacote Premium" in l:
                       # User Request: "Ilimitado somente para colisão*"
                       coberturas.append(("Assistência 24h", "Ilimitado somente para colisão*"))
                  if "Coberturas para vidros" in l:
                       coberturas.append(("Vidros", "Completo"))
                  if "Carro Reserva" in l:
                       match_cr = re.search(r'(\d+\s+dias)', l)
                       if match_cr: coberturas.append(("Carro Reserva", match_cr.group(1)))

             elif mode == "franquias_block":
                  # "R$ 10.728,00 (REDUZIDA) Não possui"
                  if "R$" in l and ("REDUZIDA" in l or "BASICA" in l or "NORMAL" in l):
                       match_f = re.search(r'R\$\s*([\d\.,]+)\s*(\([A-Z]+\))', l)
                       if match_f:
                            val_f = f"R$ {match_f.group(1)}"
                            type_f = match_f.group(2).title()
                            self.data["franquia"] = val_f
                            franquias_lista.append(f"Casco: {val_f} {type_f}")
                       else:
                            # Fallback just value
                            match_f_val = re.search(r'R\$\s*([\d\.,]+)', l)
                            if match_f_val:
                                 self.data["franquia"] = f"R$ {match_f_val.group(1)}"
                                 franquias_lista.append(f"Casco: R$ {match_f_val.group(1)}")

        self.data["coberturas"] = coberturas
        self.data["franquias_lista"] = franquias_lista

        # --- Pagamento ---
        pag_opcoes = []
        boleto_inst = 0
        boleto_val = None
        cartao_inst = 0
        cartao_val = None
        val_vista = None

        current_section = None
        for line in lines:
             l_up = line.upper()
             if "BOLETO" in l_up and "PIX" in l_up and "CARTÃO" not in l_up and "CARTAO" not in l_up:
                  current_section = "boleto"
             elif "CARTÃO" in l_up or "CARTAO" in l_up:
                  current_section = "cartao"

             if "Sem juros" in line:
                  matches = re.findall(r'(\d{1,2})\s+([\d\.,]+)\s+Sem juros', line)
                  for m in matches:
                       p = int(m[0])
                       v = m[1]
                       if p == 1 and val_vista is None:
                            val_vista = v
                       if current_section == "boleto":
                            if p > boleto_inst:
                                 boleto_inst = p
                                 boleto_val = v
                       elif current_section == "cartao":
                            if p > cartao_inst:
                                 cartao_inst = p
                                 cartao_val = v
                       else:
                            # fallback sem seção detectada
                            if p > cartao_inst:
                                 cartao_inst = p
                                 cartao_val = v

        if val_vista:
             self.data["premio_total"] = f"R$ {val_vista}"
             pag_opcoes.append({"tipo": "À Vista", "parcelas": "1x", "valor": f"R$ {val_vista}"})

        if boleto_inst > 1 and boleto_val:
             pag_opcoes.append({"tipo": "Boleto/PIX", "parcelas": f"{boleto_inst}x", "valor": f"R$ {boleto_val}"})
        elif cartao_inst > 1 and cartao_val and boleto_inst == 0:
             # Se não detectou boleto separado, cria boleto igual ao cartão (Suíça usa mesmas parcelas)
             pag_opcoes.append({"tipo": "Boleto/PIX", "parcelas": f"{cartao_inst}x", "valor": f"R$ {cartao_val}"})

        if cartao_inst > 1 and cartao_val:
             pag_opcoes.append({"tipo": "Cartão de Crédito", "parcelas": f"{cartao_inst}x", "valor": f"R$ {cartao_val}"})

        self.data["pagamento_opcoes"] = pag_opcoes
        self.data["placa"] = self._extract_placa_generic(text)
        self._apply_casing()
        return self.data
