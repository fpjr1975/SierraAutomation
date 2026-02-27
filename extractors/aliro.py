import re
from .base import BaseExtractor


class AliroExtractor(BaseExtractor):
    def extract(self):
        self.data['insurer'] = 'ALIRO'
        text = self.full_text
        lines = text.split('\n')

        # --- Basic Data ---
        # Vigencia "12/01/2026 a 12/01/2027"
        vig_match = re.search(r'(\d{2}/\d{2}/\d{4})\s*a\s*(\d{2}/\d{2}/\d{4})', text)
        if vig_match:
             self.data["vigencia"] = f"{vig_match.group(1)} a {vig_match.group(2)}"

        # Segurado "Nome do Segurado(a)"
        val_seg = self._find_value_next_line(text, "Nome do Segurado", lookahead=3)
        if val_seg:
             # "ALLAN... 000.000..."
             match_cpf = re.search(r'\d{3}\.', val_seg)
             if match_cpf:
                  self.data["segurado"] = val_seg[:match_cpf.start()].strip()
             else:
                  self.data["segurado"] = val_seg
        else:
             # Try partial
             val_seg = self._find_value_next_line(text, "NomedoSegurado", lookahead=3)
             if val_seg: self.data["segurado"] = val_seg

        # Veiculo "Marca / Tipo do Veículo" ???
        # Try looser keyword
        val_veic = self._find_value_next_line(text, "Tipo do Ve", lookahead=3)
        if not val_veic: val_veic = self._find_value_next_line(text, "TipodoVe", lookahead=3)

        if val_veic:
             val_veic = re.sub(r'^\d+-\d\s+', '', val_veic) # Remove FIPE
             val_veic = re.split(r'\d{4}/\d{4}', val_veic)[0] # Remove year
             self.data["veiculo"] = val_veic.strip()
        else:
             self.data["veiculo"] = "N/D"

        # Condutor
        val_cond = self._find_value_next_line(text, "Nome do Principal Condutor", lookahead=3)
        if val_cond:
             val_cond = re.split(r'Casado|Solteiro|Masculino|Feminino|\d{2}/\d{2}/\d{4}', val_cond)[0]
             self.data["condutor"] = val_cond.strip()
        else:
             self.data["condutor"] = self.data["segurado"]

        # CEP "CEP de Pernoite"
        # Often in table: header -> value next line
        cep_line = self._find_value_next_line(text, "CEP de Pernoite", lookahead=3)
        if cep_line:
             m_cep = re.search(r'(\d{5}[-\s]?\d{3})', cep_line)
             if m_cep:
                  val = m_cep.group(1).replace(" ", "").replace("-", "")
                  self.data["cep_pernoite"] = f"{val[:5]}-{val[5:]}"
             else:
                  # Maybe simple number?
                  # "95020" -> 95020-000 check?
                  m_cep_simple = re.search(r'(\d{5})', cep_line)
                  if m_cep_simple:
                        self.data["cep_pernoite"] = f"{m_cep_simple.group(1)}-000"

        if self.data.get("cep_pernoite") == "N/D":
            # Fallback regex over full text with DOTALL
            m_cep = re.search(r'CEP\s*de\s*Pernoite.*?(\d{5}[-\s]?\d{3})', text, re.IGNORECASE | re.DOTALL)
            if m_cep:
                 val = m_cep.group(1).replace(" ", "").replace("-", "")
                 self.data["cep_pernoite"] = f"{val[:5]}-{val[5:]}"

        # Uso "Utilização"
        val_uso = self._find_value_next_line(text, "Utiliza", lookahead=3)
        if val_uso:
             self.data["uso"] = val_uso.split()[0].title()

        # --- Coberturas ---
        coberturas = []
        assistencias = []
        franquias_lista = []

        if "COMPREENSIVA" in text.upper():
             coberturas.append(("Compreensiva", "100% FIPE"))

        for i, line in enumerate(lines):
             l_upper = line.upper()

             if "DANOS MATERIAIS" in l_upper and "CARTA VERDE" not in l_upper:
                  vals = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                  if vals: coberturas.append(("Danos Materiais", f"R$ {vals[0]}"))

             if "DANOS CORPORAIS" in l_upper and "CARTA VERDE" not in l_upper:
                  vals = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                  if vals: coberturas.append(("Danos Corporais", f"R$ {vals[0]}"))

             if "DANOS MORAIS" in l_upper:
                  vals = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                  if vals: coberturas.append(("Danos Morais", f"R$ {vals[0]}"))

             if "ACIDENTES" in l_upper and "PASSAGEIROS" in l_upper:
                   vals = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                   if vals:
                        # Check current line or next line for Morte/Invalidez
                        context = l_upper
                        if i + 1 < len(lines):
                            context += " " + lines[i+1].upper()

                        if "MORTE" in context:
                            coberturas.append(("APP Morte", f"R$ {vals[0]}"))
                        elif "INVALIDEZ" in context:
                            coberturas.append(("APP Invalidez", f"R$ {vals[0]}"))




             # Liberty Style Plans (Básico, Intermediário, Superior)
             # "Assistência 24h Auto Intermediário"
             if ("ASSISTENCIA" in l_upper or "ASSISTÊNCIA" in l_upper) and any(k in l_upper for k in ["BASICO", "BÁSICO", "INTERMEDIÁRIO", "INTERMEDIARIO", "SUPERIOR"]):
                   p_map = {
                       "SUPERIOR": "Ilimitado (sinistro)/1000Km(pane)",
                       "INTERMEDIÁRIO": "Ilimitado (sinistro)/500Km(pane)",
                       "INTERMEDIARIO": "Ilimitado (sinistro)/500Km(pane)",
                       "BÁSICO": "300Km (sinistro)/300Km(pane)",
                       "BASICO": "300Km (sinistro)/300Km(pane)"
                   }
                   val_g = "24h"
                   for k, v in p_map.items():
                        if k in l_upper:
                             val_g = v
                             break

                   # Avoid duplicating if Aliro logic also runs?
                   # Aliro requires "PLANO". Liberty usually doesn't have "PLANO" with these names.
                   coberturas.append(("Guincho", val_g))
                   assistencias.append(f"Guincho {val_g}")

             # Assistencia (Aliro - Plano G / M / etc)
             # "ASSISTENCIA-PLANOG VerCond.Gerais 182,89 0,00"
             if "ASSISTENCIA" in l_upper and "PLANO" in l_upper:
                  match_plano = re.search(r'PLANO\s*([A-Z0-9]+)', l_upper.replace('-', ' '))
                  if match_plano:
                       p_letter = match_plano.group(1).upper()
                       p_val = f"Plano {p_letter}"

                       # Aliro Plan to KM Mapping
                       mapping = {"G": "500 Km", "M": "200 Km", "P": "100 Km"}
                       km_info = mapping.get(p_letter, p_val)

                       # Check if any explicit KM or ILIMITADO exists in the FULL text for this item
                       # Detect Plan Config (Superior/Intermediário/Básico)
                       plan_map = {
                           "SUPERIOR": "Ilimitado (sinistro) / 1000 Km (pane)",
                           "INTERMEDIÁRIO": "Ilimitado (sinistro) / 500 Km (pane)",
                           "INTERMEDIARIO": "Ilimitado (sinistro) / 500 Km (pane)",
                           "BÁSICO": "300 Km (sinistro) / 300 Km (pane)",
                           "BASICO": "300 Km (sinistro) / 300 Km (pane)"
                       }

                       found_plan = False
                       for k, v in plan_map.items():
                            if k in l_upper:
                                 km_info = v
                                 found_plan = True
                                 break

                       if not found_plan:
                           # Fallback to existing logic
                           full_text_upper = text.upper()
                           explicit_km = re.search(r'(\d+)\s*KM', full_text_upper)
                           if "ILIMITADO" in full_text_upper:
                               km_info = "Ilimitado"
                           elif explicit_km:
                               km_info = f"{explicit_km.group(1)} Km"

                       # Special for Aliro: Planos G usually mean Guincho
                       # We remove "Assistência 24h" from page 2 (coberturas) to avoid redundancy
                       if "PLANO G" in l_upper or "PLANO" in l_upper:
                            coberturas.append(("Guincho", km_info))

                       assistencias.append(f"Guincho {km_info}")

             # Vidros (Plano M)
             if "VIDROS" in l_upper and "PLANO" in l_upper:
                  match_plano = re.search(r'PLANO\s*([A-Z0-9]+)', l_upper.replace('-', ' '))
                  if match_plano:
                       p_val = f"Plano {match_plano.group(1)}"
                       coberturas.append(("Vidros", p_val))
                       assistencias.append(f"Vidros {p_val}")

             if "CARRO RESERVA" in l_upper:
                  days_match = re.search(r'(\d+)\s*DIAS', l_upper)
                  if days_match:
                       val = f"{days_match.group(1)} Dias"
                       if not any(c[0] == "Carro Reserva" for c in coberturas):
                            coberturas.append(("Carro Reserva", val))
                       assistencias.append(f"Carro Reserva {val}")
                  else:
                       if not any(c[0] == "Carro Reserva" for c in coberturas):
                            coberturas.append(("Carro Reserva", "Sim"))
                       assistencias.append("Carro Reserva Sim")

             # Franquia from line "BASICA ... 6.268,00" or next line
             if "BASICA" in l_upper and "COMPREENSIVA" in l_upper:
                  vals = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                  if not vals and i + 1 < len(lines):
                       # Try next line
                       vals = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', lines[i+1])

                  if vals:
                       val = vals[-1]
                       self.data["franquia"] = f"R$ {val}"
                       franquias_item = f"Casco: R$ {val}"
                       if franquias_item not in franquias_lista:
                            franquias_lista.insert(0, franquias_item)
                  # Young Driver (18-25) Extraction (Regex) - Copied from YelumExtractor
             m_yd = re.search(r'(?:18\s*A\s*24\s*ANOS|18\s*A\s*25\s*ANOS).*?[\r\n]+\s*(SIM.*)', text.upper())
             if m_yd:
                  val = m_yd.group(1).strip()
                  if val.startswith("SIM"):
                       if not any(c[0] == "Condutor 18-25 anos" for c in coberturas):
                            coberturas.append(("Condutor 18-25 anos", "Sim"))


        if not franquias_lista and self.data.get("franquia"):
             franquias_lista.append(f"Casco: {self.data['franquia']}")

        # Deduplicate coberturas
        unique_c = []
        seen_c = set()
        for n, v in coberturas:
             if (n, v) not in seen_c:
                  unique_c.append((n, v))
                  seen_c.add((n, v))

        self.data["coberturas"] = unique_c
        self.data["assistencias"] = assistencias
        self.data["franquias_lista"] = franquias_lista

        # --- Pagamento ---
        pag_opcoes = []
        # "À vista 2.971,19"
        # "1 + 1 1.500,32"
        max_p = 0
        best_v = None
        vista_v = None

        for line in lines:
             l_clean = line.strip()
             if "À VISTA" in l_upper or "À vista" in line:
                  vals = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                  if vals:
                       vista_v = vals[0]

             # "1 + 1"
             match_p = re.match(r'1\s*\+\s*(\d+)', l_clean)
             if match_p:
                  p_num = int(match_p.group(1)) + 1
                  vals = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                  if vals:
                       val_parc = vals[0]
                       if p_num > max_p:
                            max_p = p_num
                            best_v = val_parc

        if vista_v:
             self.data["premio_total"] = f"R$ {vista_v}"
             pag_opcoes.append({"tipo": "À Vista", "parcelas": "1x", "valor": f"R$ {vista_v}"})

        if max_p > 1:
             pag_opcoes.append({"tipo": "Débito em Conta", "parcelas": f"{max_p}x", "valor": f"R$ {best_v}"})
             pag_opcoes.append({"tipo": "Cartão de Crédito", "parcelas": f"{max_p}x", "valor": f"R$ {best_v}"})

        self.data["pagamento_opcoes"] = pag_opcoes
        self.data["placa"] = self._extract_placa_generic(text)
        self._apply_casing()
        return self.data
