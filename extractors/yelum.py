import re
import pdfplumber
from .base import BaseExtractor


class YelumExtractor(BaseExtractor):
    def _load_text(self):
        # Override to use default x_tolerance which seems to work better for Yelum table
        self.full_text = ""
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                for page in pdf.pages:
                    self.full_text += (page.extract_text(x_tolerance=1) or "") + "\n"
        except Exception as e:
            print(f"Error reading PDF: {e}")

    def extract(self):
        self.data['insurer'] = 'YELUM'
        text = self.full_text



        # --- AUTO CONSCIENTE Detection ---
        # "YELUMAUTOCONSCIENTE" often glued
        text_collapsed = text.replace(" ", "").upper()

        is_auto_consciente = "AUTOCONSCIENTE" in text_collapsed
        self.data['is_auto_consciente'] = is_auto_consciente

        if is_auto_consciente:
             # Force specifics for Auto Consciente (Third Party Only)
             self.data['titulo_inclusos_suffix'] = " ( Seguro Terceiros )"
             self.data['fipe_custom'] = "Não contratado"
             # We will override values later or inject them now


        lines = text.split('\n')

        # --- Basic Data ---
        # Vigencia "28/12/2025a28/12/2026"
        # Relax to allow spaces or not
        # Vigencia "28/12/2025a28/12/2026"
        # Relax regex to capture start and end dates flexibly
        vig_match = re.search(r'(\d{2}/\d{2}/\d{4}).*?(\d{2}/\d{2}/\d{4})', text, re.S)
        if vig_match:
            self.data["vigencia"] = f"{vig_match.group(1)} a {vig_match.group(2)}"

        # Segurado
        # Try both patterns:
        # 1. "NomedoSegurado(a)..." -> Next line (Glued layout)
        # 2. "DADOS DO PROPONENTE/SEGURADO(A)" -> Header line (Spaced layout)

        # Pattern 2 (Spaced/Jeancarlos layout)
        # Find header, skip 1 line, take next
        seg_idx = -1
        for i, line in enumerate(lines):
             if "DADOS DO PROPONENTE" in line:
                  seg_idx = i
                  break

        if seg_idx != -1 and seg_idx + 2 < len(lines):
             # Likely spaced layout
             raw_seg = lines[seg_idx + 2]
             # "JEAN CARLOS KLERING 679..."
             match_name = re.match(r'^([A-Z\s\.]+?)(?=\s\d)', raw_seg)
             if match_name:
                  self.data["segurado"] = match_name.group(1).strip()
             else:
                  # Fallback split
                  parts = raw_seg.split(' 0')[0].split(' 1')[0]
                  self.data["segurado"] = parts.strip()
        else:
             # Pattern 1 (Glued/Allan layout)
             # "NomedoSegurado(a)..." -> Next line "PRISCILLA..."
             val_seg = self._find_value_next_line(text, "NomedoSegurado", lookahead=3)
             if val_seg:
                  match_cpf = re.search(r'\d{3}\.', val_seg)
                  if match_cpf:
                       self.data["segurado"] = val_seg[:match_cpf.start()].strip()
                  else:
                       self.data["segurado"] = val_seg
             else:
                  self.data["segurado"] = "N/D"

        self.data["condutor"] = self.data["segurado"]

        # Veiculo
        veic_found = False

        # Pattern 2 (Spaced)
        # "ITEM 1 - DADOS DO VEICULO SEGURADO"
        veic_idx = -1
        for i, line in enumerate(lines):
            if "DADOS DO VEICULO SEGURADO" in line:
                veic_idx = i
                break

        if veic_idx != -1 and veic_idx + 2 < len(lines):
             val_line = lines[veic_idx + 2]
             # "015069-0 AZERA GLS ... 2010/2010"
             # Remove FIPE
             val_line = re.sub(r'^\d{6}-\d\s+', '', val_line)
             val_line = re.sub(r'\d{4}/\d{4}.*$', '', val_line)
             # Fix glued text if necessary
             val_line = re.sub(r'(?<=[A-Z])(?=\d)', ' ', val_line)
             val_line = re.sub(r'(?<=\d)(?=[A-Z])', ' ', val_line)
             self.data["veiculo"] = val_line.strip()
             veic_found = True

        if not veic_found:
             # Pattern 1 (Glued)
             # "TipodoVe" -> Next line
             val_veic = self._find_value_next_line(text, "TipodoVe", lookahead=3)
             if val_veic:
                  val_veic = re.sub(r'^\d+-\d\s+', '', val_veic)
                  val_veic = re.split(r'\d{4}/\d{4}', val_veic)[0]
                  # Inject spaces
                  val_veic = re.sub(r'(?<=[A-Z])(?=\d)', ' ', val_veic)
                  val_veic = re.sub(r'(?<=\d)(?=[A-Z])', ' ', val_veic)

                  self.data["veiculo"] = val_veic.strip()
             else:
                  self.data["veiculo"] = "N/D"

        # Uso: "Utilização"
        # Spaced: "Utilização ... PARTICULAR" (Same line or next?)
        # Glued: "Utiliza" -> "PARTICULAR"

        # Generic approach
        uso_match = re.search(r'Utiliza(?:ção)?\s*(\w+)', text, re.IGNORECASE)
        if uso_match and "Antifurto" not in uso_match.group(1):
             self.data["uso"] = uso_match.group(1).title()
        else:
             # Try next line
             val_uso = self._find_value_next_line(text, "Utiliza", lookahead=3)
             if val_uso:
                  self.data["uso"] = val_uso.split()[0].title()
             else:
                  self.data["uso"] = "N/D"

        # CEP
        self.data["cep_pernoite"] = "N/D"
        # Yelum layout: header "CEP de Pernoite" on one line, data on next line
        # Data line example: "5 10 - VEÍCULOS NACIONAIS DE PASSEIO 1178 04635 0.25 - FACULTATIVA"
        # The CEP is a 5-digit block (sometimes 5+3) near the end of the data line
        for i, line in enumerate(lines):
            if "CEP" in line.upper() and "PERNOITE" in line.upper():
                if i + 1 < len(lines):
                    data_line = lines[i + 1]
                    # Look for 5-digit + optional 3-digit CEP pattern
                    cep_8 = re.search(r'(\d{5})[-\s]?(\d{3})', data_line)
                    cep_5 = re.findall(r'\b(\d{5})\b', data_line)
                    if cep_8:
                        self.data["cep_pernoite"] = f"{cep_8.group(1)}-{cep_8.group(2)}"
                    elif cep_5:
                        # Take the last 5-digit group (CEP is after Reg.Tarif number)
                        self.data["cep_pernoite"] = f"{cep_5[-1]}-000"
                break

        # --- Coberturas ---
        coberturas = []
        if "COMPREENSIVA" in text.upper():
             coberturas.append(("Compreensiva", "100% FIPE"))

        # Parse table lines (handles both glued and spaced if we are flexible)
        # Scan for specific keywords

        text_collapsed = text.replace(" ", "")

        # Danos Materiais
        # "RESPCIVIL...DANOSMATERIAIS...150.000,00"
        dm_match = re.search(r'DANOSMATERIAIS.*?(\d{1,3}(?:\.\d{3})*,\d{2})', text_collapsed)
        if dm_match:
             coberturas.append(("Danos Materiais", f"R$ {dm_match.group(1)}"))

        # Danos Corporais
        dc_match = re.search(r'DANOSCORPORAIS.*?(\d{1,3}(?:\.\d{3})*,\d{2})', text_collapsed)
        if dc_match:
             coberturas.append(("Danos Corporais", f"R$ {dc_match.group(1)}"))

        # Danos Morais
        # "RESP CIVIL FACULTATIVA VEÍCULOS - DANOS MORAIS E 40.000,00"
        # "ESTÉTICOS"
        # Flatten text to handle split lines?
        # Use regex on full text with re.DOTALL or just collapsed text

        dmo_match = re.search(r'DANOS\s*MORAIS.*?(\d{1,3}(?:\.\d{3})*,\d{2})', text, re.IGNORECASE | re.DOTALL)
        if dmo_match:
             coberturas.append(("Danos Morais", f"R$ {dmo_match.group(1)}"))

        # APP Morte - multiple patterns for different formats
        # Yelum Format: "ACIDENTES PESSOAIS PASSAGEIROS - LMI POR PASSAGEIRO - 5.000,00"
        #               "MORTE" (next line)
        # The value appears BEFORE the keyword, so we search for the keyword and capture value from preceding content
        app_morte_found = False

        # Pattern 1: Collapsed text (no spaces)
        app_match = re.search(r'PORPASSAGEIRO-MORTE.*?([\d\.,]{5,})', text_collapsed)
        if app_match:
             coberturas.append(("APP Morte", f"R$ {app_match.group(1)}"))
             app_morte_found = True

        if not app_morte_found:
             # Pattern 2: Line scan - find line with "POR PASSAGEIRO" followed by "MORTE" line
             for i, line in enumerate(lines):
                  l_up = line.upper()
                  if "POR PASSAGEIRO" in l_up and "MORTE" not in l_up:
                       # Check if next lines contain "MORTE"
                       for j in range(i+1, min(i+3, len(lines))):
                            if "MORTE" in lines[j].upper() and "INVALIDEZ" not in lines[j].upper():
                                 # Value should be on the POR PASSAGEIRO line
                                 vals = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                                 if vals:
                                      coberturas.append(("APP Morte", f"R$ {vals[0]}"))
                                      app_morte_found = True
                                      break
                       if app_morte_found:
                            break

        # APP Invalidez - similar approach
        app_inv_found = False
        app_inv_match = re.search(r'PORPASSAGEIRO-INVALIDEZ.*?([\d\.,]{5,})', text_collapsed)
        if app_inv_match:
             coberturas.append(("APP Invalidez", f"R$ {app_inv_match.group(1)}"))
             app_inv_found = True

        if not app_inv_found:
             # Pattern 2: Line scan - find line with "POR PASSAGEIRO" followed by "INVALIDEZ" line
             for i, line in enumerate(lines):
                  l_up = line.upper()
                  if "POR PASSAGEIRO" in l_up and "INVALIDEZ" not in l_up:
                       # Check if next lines contain "INVALIDEZ"
                       for j in range(i+1, min(i+3, len(lines))):
                            if "INVALIDEZ" in lines[j].upper():
                                 # Value should be on the POR PASSAGEIRO line
                                 vals = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                                 if vals:
                                      coberturas.append(("APP Invalidez", f"R$ {vals[0]}"))
                                      app_inv_found = True
                                      break
                       if app_inv_found:
                            break

        # Loop to find specific coverage lines
        for line in lines:
             l_upper = line.upper()

             if "VIDROS" in l_upper:
                   if "PLANO M" in l_upper or "COMPLETO" in l_upper or "SUPERIOR" in l_upper or "INTERMEDIARIO" in l_upper:
                        if not any(c[0] == "Vidros" for c in coberturas):
                             if "SUPERIOR" in l_upper:
                                  coberturas.append(("Vidros", "Plano Superior"))
                             elif "INTERMEDIARIO" in l_upper:
                                  coberturas.append(("Vidros", "Plano Intermediário"))
                             else:
                                  coberturas.append(("Vidros", "Completo"))

             if "CARRO RESERVA" in l_upper:
                   # "CARRO RESERVA - 15 DIAS BÁSICO"
                   m_dias = re.search(r'(\d+)\s*DIAS', l_upper)
                   if m_dias:
                        if not any(c[0] == "Carro Reserva" for c in coberturas):
                             desc = f"{m_dias.group(1)} Dias"
                             if "BÁSICO" in l_upper or "BASICO" in l_upper: desc += " (Básico)"
                             coberturas.append(("Carro Reserva", desc))

             if "ASSISTENCIA" in l_upper or "ASSISTÊNCIA" in l_upper or "PLANO SUPERIOR" in l_upper or "PLANO COMPLETO" in l_upper or "PLANO INTERMEDIARIO" in l_upper or "PLANO BASICO" in l_upper:
                   # "ASSISTENCIA - SUPERIOR" ou com km
                   # Tenta extrair km primeiro
                   km_match = re.search(r"(\d+)\s*[Kk][Mm]", line)
                   if km_match:
                        if not any(c[0] == "Assistência 24h" for c in coberturas):
                             coberturas.append(("Assistência 24h", f"Guincho {km_match.group(1)} Km"))
                   elif "SUPERIOR" in l_upper:
                        if not any(c[0] == "Assistência 24h" for c in coberturas):
                             coberturas.append(("Assistência 24h", "Guincho Ilimitado (sinistro)/1000Km(pane)"))
                   elif "INTERMEDIARIO" in l_upper or "INTERMEDIÁRIO" in l_upper:
                        if not any(c[0] == "Assistência 24h" for c in coberturas):
                             coberturas.append(("Assistência 24h", "Guincho Ilimitado (sinistro)/500Km(pane)"))
                   elif "COMPLETA" in l_upper:
                        if not any(c[0] == "Assistência 24h" for c in coberturas):
                             # Yelum Completa = 300 Km (padrão)
                             coberturas.append(("Assistência 24h", "Guincho 300 Km (Completa)"))
                   elif "BASICA" in l_upper or "BÁSICA" in l_upper or "BASICO" in l_upper or "BÁSICO" in l_upper:
                        if not any(c[0] == "Assistência 24h" for c in coberturas):
                             coberturas.append(("Assistência 24h", "Guincho 300Km (sinistro)/300Km(pane)"))
                   elif "EXCLUSIV" in l_upper:
                        if not any(c[0] == "Assistência 24h" for c in coberturas):
                             coberturas.append(("Assistência 24h", "Guincho Ilimitado"))
                   elif "PLANO RCF" in l_upper:
                        if not any(c[0] == "Assistência 24h" for c in coberturas):
                             coberturas.append(("Assistência 24h", "Guincho 300 Km (RCF)"))

             if "PEQUENOS REPAROS" in l_upper:
                   if not any(c[0] == "Pequenos Reparos" for c in coberturas):
                        coberturas.append(("Pequenos Reparos", "Contratado"))

             # Young Driver (18-25) Extraction (Regex)
             # "Deseja estender cobertura p/ residentes habilitados com idade 18 a 24 anos?"
             # "Sim, Util lim 2 dias"
             m_yd = re.search(r'(?:18\s*A\s*24\s*ANOS|18\s*A\s*25\s*ANOS).*?[\r\n]+\s*(SIM.*)', text.upper())



             if m_yd:
                  val = m_yd.group(1).strip()
                  # Validate it's a real Sim
                  if val.startswith("SIM"):
                       if not any(c[0] == "Condutor 18-25 anos" for c in coberturas):
                            coberturas.append(("Condutor 18-25 anos", "Sim"))

        self.data["coberturas"] = coberturas

        # --- AUTO CONSCIENTE OVERRIDES ---
        if self.data.get('is_auto_consciente'):
             # 1. Guincho Override
             # "300km sinistro e 200 mecânico"
             new_cobs = [c for c in self.data["coberturas"] if c[0] != "Assistência 24h" and c[0] != "Carro Reserva"]

             new_cobs.append(("Assistência 24h", "Guincho 300 Km (Sinistro) / 200 Km (Mecânico)"))
             new_cobs.append(("Carro Reserva", "Não contratado"))

             self.data["coberturas"] = new_cobs
             self.data["franquia"] = "Não contratado"

        # --- INFORMAÇÕES COMPLEMENTARES (Franquias) ---
        # Scan specifically for this block
        info_idx = -1
        for i, line in enumerate(lines):
             if "INFORMAÇÕES COMPLEMENTARES" in line.upper():
                  info_idx = i
                  break

        franquias_lista = []
        if info_idx != -1:
             # Read subsequent lines
             # "VIDROS SUPERIOR ... - Franquia Para-brisa R$740,00 / Vigia R$670,00 ..."

             # Capture block text until "ATENÇÃO" or similar
             block_text = ""
             for i in range(info_idx + 1, len(lines)):
                  line = lines[i].strip()
                  if "ATENÇÃO" in line.upper() or "DADOS DO PERFIL" in line.upper():
                       break
                  block_text += " " + line

             # Busca franquias por padrões específicos conhecidos
             # Padrão 1: "Item R$XXX,XX"
             patterns_franquias = [
                  (r'Para-?brisa\s*R\$\s*([\d\.,]+)', 'Para-brisa'),
                  (r'Vigia\s*R\$\s*([\d\.,]+)', 'Vigia'),
                  (r'Laterais\s*R\$\s*([\d\.,]+)', 'Laterais'),
                  (r'Retrovisores(?:\s+LED)?\s*R\$\s*([\d\.,]+)', 'Retrovisores'),
                  (r'Faróis?(?:\s+LED)?\s*R\$\s*([\d\.,]+)', 'Faróis'),
                  (r'Farol\s+Auxiliar\s*R\$\s*([\d\.,]+)', 'Farol Auxiliar'),
                  (r'Lanternas?(?:\s+LED)?\s*R\$\s*([\d\.,]+)', 'Lanternas'),
                  (r'Maquina\s+de\s+Vidros?\s*R\$\s*([\d\.,]+)', 'Máquina de Vidros'),
                  (r'Reparo\s+de\s+Para-?choque\s*R\$\s*([\d\.,]+)', 'Reparo Para-choque'),
                  (r'SRA-?\s*Servico.*?R\$\s*([\d\.,]+)', 'SRA Arranhões'),
                  (r'SRA\s*Plus.*?R\$\s*([\d\.,]+)', 'SRA Plus Martelinho'),
                  (r'Farol\s+Matrix\s*R\$\s*([\d\.,]+)', 'Farol Matrix'),
             ]

             for pattern, name in patterns_franquias:
                  match = re.search(pattern, block_text, re.IGNORECASE)
                  if match:
                       franquias_lista.append(f"{name}: R$ {match.group(1)}")

             # Pequenos Reparos (pode estar em linha separada)
             pr_match = re.search(r'PEQUENOS\s*REPAROS.*?Franquia\s*R\$\s*([\d\.,]+)', block_text, re.IGNORECASE)
             if pr_match:
                  franquias_lista.append(f"Pequenos Reparos: R$ {pr_match.group(1)}")

        # Always check original Franquia keywords scan for Casco (Basic)
        # "BASICA" in line and "COMPREENSIVA" in line
        found_casco = False
        for i, line in enumerate(lines):
             if "BASICA" in line and "COMPREENSIVA" in line:
                  vals = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                  if vals:
                       val = vals[-1]
                       self.data["franquia"] = f"R$ {val}"
                       franquias_item = f"Casco: R$ {val}"
                       if franquias_item not in franquias_lista:
                           franquias_lista.insert(0, franquias_item)
                       found_casco = True

        self.data["franquias_lista"] = sorted(list(set(franquias_lista)))

        if self.data.get('is_auto_consciente'):
             self.data["franquias_lista"] = ["Casco: Não contratado"]

        # --- Pagamento ---
        pag_opcoes = []
        max_inst = 0
        val_parcela = None

        # Vista
        # "Àvista 3.016,73"
        vista_match = re.search(r'(?:À|A)\s*vista.*?(\d{1,3}(?:\.\d{3})*,\d{2})', text_collapsed, re.IGNORECASE)
        if vista_match:
             val = vista_match.group(1)
             self.data["premio_total"] = f"R$ {val}"
             pag_opcoes.append({"tipo": "À Vista", "parcelas": "1x", "valor": f"R$ {val}"})

        # Installments
        # "1+1 ...", "1+2 ..."
        # Scan raw lines for "1 + N" pattern

        # Spaced: "1 + 10 270,10"
        # Glued: "1+6 148,40"

        all_insts = re.findall(r'1\s*\+\s*(\d{1,2})', text)
        if all_insts:
             ints = sorted([int(x) for x in all_insts], reverse=True)
             if ints:
                  # Credit: Absolute Max
                  max_credit_n = ints[0] + 1
                  target_credit = ints[0]

                  # Debit: Max installment <= 6 (1+5)
                  max_debit_n = 0
                  target_debit = 0
                  for x in ints:
                       if (x + 1) <= 6:
                            max_debit_n = x + 1
                            target_debit = x
                            break

                  # Extract Values
                  val_credit = None
                  val_debit = None

                  for line in lines:
                       # Credit value
                       if val_credit is None and (f"1 + {target_credit}" in line or f"1+{target_credit}" in line):
                            moneys = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                            if moneys: val_credit = moneys[-1]

                       # Debit value (only if found potential debit target)
                       if max_debit_n > 0 and val_debit is None and (f"1 + {target_debit}" in line or f"1+{target_debit}" in line):
                            moneys = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                            if moneys: val_debit = moneys[-1]

                  if val_credit and max_credit_n > 1:
                       pag_opcoes.append({"tipo": "Cartão de Crédito", "parcelas": f"{max_credit_n}x", "valor": f"R$ {val_credit}"})

                  if val_debit and max_debit_n > 1:
                       pag_opcoes.append({"tipo": "Débito em Conta", "parcelas": f"{max_debit_n}x", "valor": f"R$ {val_debit}"})

        self.data["pagamento_opcoes"] = pag_opcoes
        self.data["placa"] = self._extract_placa_generic(text)
        self._apply_casing()
        return self.data
