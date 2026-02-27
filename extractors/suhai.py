import re
from .base import BaseExtractor


class SuhaiExtractor(BaseExtractor):
    def extract(self):
        self.data['insurer'] = 'SUHAI'
        text = self.full_text
        lines = text.split('\n')

        # --- Segurado ---
        # "Nome/Razão Social ... \n RAFAEL BARBIERI Física ..."
        # Extract line after "Nome/Razão Social"
        seg_line = self._find_value_next_line(text, "Nome/Razão Social")
        if seg_line:
             # Remove "Física", "Jurídica", digits from end
             seg_clean = re.sub(r'(Física|Jurídica).*', '', seg_line, flags=re.I).strip()
             self.data["segurado"] = seg_clean
        else:
             self.data["segurado"] = "N/D"

        # --- Veiculo ---
        # "Código FIPE Marca Modelo do Veículo\n... Ford EcoSport..."
        veic_match = re.search(r'Marca Modelo do Veículo\s*\n\S+\s+(.*?)(?:\n|$)', text, re.I)
        if veic_match:
             self.data["veiculo"] = veic_match.group(1).strip()
        else:
             self.data["veiculo"] = self._find_value_after_keyword(text, "Modelo do Veículo")

        # --- Vigencia ---
        vig_match = re.search(r'Vigência Proposta:.*?(\d{2}/\d{2}/\d{4}).*?(\d{2}/\d{2}/\d{4})', text)
        if vig_match:
             self.data["vigencia"] = f"{vig_match.group(1)} a {vig_match.group(2)}"

        self.data["condutor"] = self.data["segurado"]

        # --- CEP / Uso ---
        # "CEP Pernoite ... \n ... 95096060"
        cep_match = re.search(r'CEP Pernoite.*?\n.*?\/?(\d{8})', text, re.I)
        if cep_match:
             c = cep_match.group(1)
             self.data["cep_pernoite"] = f"{c[:5]}-{c[5:]}"

        uso_match = re.search(r'Utilização.*?\n(.*?)(?:\d|$)', text, re.I)
        if uso_match:
             self.data["uso"] = uso_match.group(1).split('  ')[0].strip()

        # --- Options & Coberturas ---
        # Identify Best Option
        selected_option = "COMPREENSIVA"
        if "OPÇÃO COMPREENSIVA" in text.upper():
             selected_option = "COMPREENSIVA"
        elif "PT COLISÃO" in text.upper():
             selected_option = "ROUBO + FURTO + PT COLISÃO"
        elif "ROUBO + FURTO" in text.upper():
             selected_option = "ROUBO + FURTO"

        coberturas = []
        is_compreensiva = "COMPREENSIVA" in selected_option

        for line in lines:
             line_upper = line.upper()
             if "COMPREENSIVA" in line_upper and "100% FIPE" in line_upper and is_compreensiva:
                  coberturas.append(("Compreensiva", "100% FIPE"))

             # RCF usually generic for all options
             if "DANOS MATERIAIS" in line_upper:
                  vals = re.findall(r'([\d\.,]{5,})', line)
                  if vals: coberturas.append(("Danos Materiais", f"R$ {vals[0]}"))
             if "DANOS CORPORAIS" in line_upper:
                  vals = re.findall(r'([\d\.,]{5,})', line)
                  if vals: coberturas.append(("Danos Corporais", f"R$ {vals[0]}"))
             if "DANOS MORAIS" in line_upper:
                  vals = re.findall(r'([\d\.,]{5,})', line)
                  if vals: coberturas.append(("Danos Morais", f"R$ {vals[0]}"))
             if "APP" in line_upper or "ACIDENTES PESSOAIS" in line_upper:
                  vals = re.findall(r"([\d\.,]{4,})", line)
                  if vals: coberturas.append(("APP", f"R$ {vals[0]}"))

             if "GUINCHO" in line_upper or "ASSISTÊNCIA 24 HORAS" in line_upper:
                  # Use collapsed line to find distance and avoid "24" from "Assistência 24h"
                  line_collapsed = line.replace(" ", "").upper()
                  km_match = re.search(r"(\d+)KM", line_collapsed)
                  if km_match:
                       coberturas.append(("Assistência 24h", f"Guincho {km_match.group(1)} Km"))
                  elif "ILIMITADO" in line_collapsed:
                       coberturas.append(("Guincho", "Ilimitado"))

             if "CARRO RESERVA" in line_upper:
                  # "Carro Reserva 7 Dias"
                  m_dias = re.search(r"(\d+)\s*Dias", line, re.I)
                  if m_dias:
                       coberturas.append(("Carro Reserva", f"{int(m_dias.group(1))} Dias"))
                  elif "NÃO CONTRATADO" not in line_upper:
                       coberturas.append(("Carro Reserva", "Contratado"))

        # Franquias
        self.data["franquias_lista"] = []
        # Suhai dump check: "Reduzida: R$ 3.206,25 Não se aplica"
        franquia_match = re.search(r'Franquia Perdas Parciais.*?((?:Reduzida|Básica).*?R\$\s*[\d\.,]+)', text, re.I | re.S)
        if franquia_match and is_compreensiva:
             val = franquia_match.group(1)
             # Sanitize if digits merged (though the regex above should be safer)
             # but let's be extra careful
             val = re.sub(r'(R\$\s*[\d\.,]+)\d+.*', r'\1', val).strip()
             self.data["franquias_lista"].append(val)
             self.data["franquia"] = val
             if "R$" in val:
                  coberturas.append(("Franquia", val))
        else:
             self.data["franquias_lista"].append("N/D (Roubo/Furto)")
        self.data["coberturas"] = coberturas

        # --- Pagamento ---
        # Find start of selected option table
        start_idx = -1
        for i, line in enumerate(lines):
             if selected_option in line.upper() and ("OPÇÃO" in line.upper() or "OPCOES" in line.upper()):
                  start_idx = i
                  break

        pag_opcoes = []
        if start_idx != -1:
             max_inst = 0
             val_parcela = None
             val_vista = None

             # Scan next 30 lines
             for i in range(start_idx + 1, min(start_idx + 30, len(lines))):
                  line = lines[i].strip()
                  # Stop if new option header
                  if "OPÇÃO" in line.upper() and i > start_idx + 2:
                       break

                  # Parse row: "1 2.382,82 2.382,82 0,000000"
                  # Must start with digit
                  if not line or not line[0].isdigit(): continue

                  parts = line.split()
                  if len(parts) >= 4:
                       try:
                            parc = int(parts[0])
                            v_total = parts[2] # Total com juros ou a vista
                            juros_str = parts[3].replace(',', '.')
                            is_free = (float(juros_str) == 0.0)

                            if parc == 1:
                                 val_vista = v_total

                            if is_free:
                                 if parc > max_inst:
                                      max_inst = parc
                                      val_parcela = parts[1] # Valor da parcela
                       except:
                            continue

             if val_vista:
                  pag_opcoes.append({"tipo": "À Vista", "parcelas": "1x", "valor": f"R$ {val_vista}"})
                  self.data["premio_total"] = f"R$ {val_vista}"

             if max_inst > 1 and val_parcela:
                  pag_opcoes.append({"tipo": "Cartão de Crédito", "parcelas": f"{max_inst}x", "valor": f"R$ {val_parcela}"})

        self.data["pagamento_opcoes"] = pag_opcoes

        # --- Placa ---
        # Dump: "Sem Rastreador Não Aplica IWC0930"
        placa_match = re.search(r'([A-Z]{3}\d[A-Z0-9]\d{2})', text)
        if placa_match:
             self.data["placa"] = placa_match.group(1)
        else:
             self.data["placa"] = "N/D"

        self._apply_casing()
        return self.data
