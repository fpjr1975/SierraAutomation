import re
import pdfplumber
import os

class BaseExtractor:
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        self.data = {
            "vigencia": "N/D",
            "veiculo": "N/D",
            "coberturas": [],
            "franquia": "N/D",
            "premio_total": "N/D",
            "tipo_seguro": "Seguro Auto",
            "segurado": "N/D",
            "condutor": "N/D",
            "uso": "N/D",
            "cep_pernoite": "N/D",
            "pagamento_opcoes": [],
            "placa": "Placa não informada",
            "insurer": None,  # ALFA, AZUL, etc.
            "classe_bonus": "N/D",  # Classe de bônus (1-10) da apólice
        }
        self.full_text = ""
        self.full_text_upper = ""
        self._load_text()

    def _load_text(self):
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                for page in pdf.pages:
                    # layout=False often preserves line structure better for basic extraction
                    self.full_text += (page.extract_text(x_tolerance=1) or "") + "\n"
        except Exception as e:
            print(f"Error reading PDF: {e}")
        self.full_text_upper = self.full_text.upper()

    def _get_full_text(self):
        return self.full_text # Backward compatibility if needed, but self.full_text is preferred

    def extract(self):
        self._apply_casing()
        return self.data

    def _standardize_coberturas(self):
        """Standardizes coverage names (RCFV, APP) and values."""
        if not self.data.get("coberturas"): return
        new_cob = []
        for name, val in self.data["coberturas"]:
            # 1. Global Rule: Vidros -> Consulte tabela Franquias
            if "Vidros" in name or "Faróis" in name or "Lanternas" in name or "Retrovisores" in name:
                 val = "Consulte tabela Franquias"

            # 2. RCFV Prefix REMOVAL per user request
            # We explicitly REMOVE any RCFV prefixes here too
            rcf_pattern = r'\bR\.?C\.?F\.?\s*[-–— ]?\s*V?\.?\b\s*[-–—:]?\s*'
            name = re.sub(rcf_pattern, '', name, flags=re.I).strip()

            # 3. APP Standardization
            # "Acidentes Pessoais Passageiros" -> "APP" (cobre morte e invalidez)
            if "ACIDENTES PESSOAIS" in name.upper() or "ACIDENTE PESSOAL" in name.upper():
                 name = "Acidentes Pessoais Passageiros"
            # "APP Morte" -> "APP - Morte"
            elif name.upper().startswith("APP") and " - " not in name:
                 parts = name.split(None, 1)
                 if len(parts) > 1:
                      name = f"{parts[0]} - {parts[1]}"
            elif "MORTE" in name.upper() or "INVALIDEZ" in name.upper():
                  # Ensure it has APP prefix if not present (heuristic)
                  if not name.upper().startswith("APP") and not name.upper().startswith("RCFV"):
                       name = f"APP - {name}"

            new_cob.append((name, val))
        self.data["coberturas"] = new_cob

    def _sort_coberturas(self):
        """Sorts coberturas list based on a standard priority."""
        if not self.data.get("coberturas"): return

        def priority(item):
            name = item[0].upper()
            # 1. Compreensiva / Casco
            if "COMPREENSIVA" in name or "CASCO" in name or "COLISÃO" in name or "INCÊNDIO" in name: return 1
            # 2. Danos Materiais
            if "MATERIAIS" in name: return 2
            # 3. Danos Corporais
            if "CORPORAIS" in name: return 3
            # 4. Danos Morais
            if "MORAIS" in name: return 4
            # 5. APP (Morte/Invalidez)
            if "APP" in name or "MORTE" in name or "INVALIDEZ" in name: return 5
            # 6. Assistencia
            if "ASSISTÊNCIA" in name or "ASSISTENCIA" in name or "GUINCHO" in name: return 6
            # 7. Vidros
            if "VIDROS" in name or "FARÓIS" in name or "LANTERNAS" in name: return 7
            # 8. Carro Reserva
            if "RESERVA" in name: return 8
            # 9. Others
            return 99

        self.data["coberturas"].sort(key=priority)

    def _apply_casing(self):
        """Converts SHOUTING CASE to Title Case to avoid being 'grosseiro'."""
        # Fields to normalize
        simple_fields = ["segurado", "condutor", "veiculo", "uso", "tipo_seguro", "cep_pernoite"]
        for f in simple_fields:
            val = self.data.get(f)
            if val and isinstance(val, str) and val != "N/D":
                # Check if it looks like SHOUTING (mostly uppercase)
                # Ignore short strings or those starting with R$
                if len(val) > 3 and not val.startswith("R$"):
                    # Heuristic: if > 60% of letters are upper
                    letters = [c for c in val if c.isalpha()]
                    if letters:
                        upper_count = sum(1 for c in letters if c.isupper())
                        if upper_count / len(letters) > 0.6:
                             fixed = val.title()
                             # Fix common particles
                             fixed = re.sub(r'\bDe\b', 'de', fixed)
                             fixed = re.sub(r'\bDa\b', 'da', fixed)
                             fixed = re.sub(r'\bDo\b', 'do', fixed)
                             fixed = re.sub(r'\bE\b', 'e', fixed)
                             # Restore common acronyms if needed
                             fixed = fixed.replace("Cpf", "CPF").replace("Cnpj", "CNPJ").replace("Fipe", "FIPE").replace("App", "APP")
                             self.data[f] = fixed

        # Lists (Cob, Franq, Pag)
        # Coberturas: list of tuples (Name, Val)
        if self.data.get("coberturas"):
            new_cob = []
            for name, val in self.data["coberturas"]:
                 # Fix Name
                 if name.isupper(): name = name.title().replace("App", "APP")
                 # Fix Val (often R$ ...)
                 # If Val is "100% FIPE" -> "100% Fipe" -> Fix back
                 if any(c.isalpha() for c in val) and val.isupper():
                      val = val.title().replace("Fipe", "FIPE")

                 new_cob.append((name, val))
            self.data["coberturas"] = new_cob

        # Franquias: list of strings
        if self.data.get("franquias_lista"):
            new_franq = []
            for item in self.data["franquias_lista"]:
                 # "Casco: R$ 1000"
                 # "LANTERNA: R$ 200"
                 if any(c.isalpha() for c in item) and sum(1 for c in item if c.isupper()) > sum(1 for c in item if c.islower()):
                      fixed_item = item.title().replace("R$", "R$") # title() keeps R$ as R$ usually
                      # Particles
                      fixed_item = re.sub(r'\bDe\b', 'de', fixed_item)
                      new_franq.append(fixed_item)
                 else:
                      new_franq.append(item)
            self.data["franquias_lista"] = new_franq

        # Trigger standardization strings and sorting
        # This is placed here because _apply_casing is guaranteed to be called by all extractors
        self._standardize_coberturas()
        self._sort_coberturas()

        # --- GLOBAL FIX: Ensure both Credit and Debit options exist for display ---
        opts = self.data.get("pagamento_opcoes", [])
        has_credit = any("Cartão" in p.get("tipo", "") for p in opts)
        has_debit = any("Débito" in p.get("tipo", "") for p in opts)

        # Find a suitable candidate to clone if one is missing
        candidate = None
        for p in opts:
             t = p.get("tipo", "")
             if "Vista" in t: continue
             candidate = p
             break

        if candidate:
             # If missing Credit, clone candidate as Credit
             if not has_credit:
                  new_opt = candidate.copy()
                  new_opt["tipo"] = "Cartão de Crédito"
                  opts.append(new_opt)

             # If missing Debit, clone candidate as Debit (Unless denied)
             # User Rule: Ezze and Suhai do NOT have Debit option.
             insurer_nm = self.data.get("insurer", "").upper()
             if not has_debit and "EZZE" not in insurer_nm and "SUHAI" not in insurer_nm and "SUICA" not in insurer_nm:
                  new_opt = candidate.copy()
                  new_opt["tipo"] = "Débito em Conta"
                  opts.append(new_opt)

        self.data["pagamento_opcoes"] = opts


    def _find_value_after_keyword(self, text, keyword, terminator=None):
        """Finds value on the same line after a keyword (Case Insensitive)."""
        pattern = re.escape(keyword) + r'\s*(.*)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            if terminator:
                if isinstance(terminator, list):
                    for t in terminator:
                        value = value.split(t)[0]
                else:
                    value = value.split(terminator)[0]
            return value.replace('\n', ' ').strip()
        return None

    def _find_value_next_line(self, text, keyword, lookahead=2):
        """Finds value on the line immediately following the line containing the keyword (or within lookahead lines)."""
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if keyword.lower() in line.lower():
                # Check next 'lookahead' lines
                for j in range(1, lookahead + 1):
                    if i + j < len(lines):
                        val = lines[i+j].replace('\n', ' ').strip()
                        if val and len(val) > 2: # Ignore empty/tinylines
                            return val
        return None

    def _extract_monetary(self, text):
        """Extracts R$ value."""
        if not text: return None
        match = re.search(r'(?:R\$|RS)\s*([\d\.]+,\d{2})', text)
        if match:
            return f"R$ {match.group(1)}"
        return None

    def _extract_classe_bonus(self, text):
        """
        Extrai classe de bônus do texto do PDF.
        Bônus vai de 1 (sem desconto) a 10 (máximo desconto).
        Presente em apólices (não cotações).
        """
        # Padrões comuns nos PDFs de seguradoras
        patterns = [
            # "Classe de Bônus: 8" ou "Classe de Bônus 08"
            r'[Cc]lasse\s+de\s+[Bb][ôo]nus\s*[:\-]?\s*0?(\d{1,2})',
            # "Bônus: 8" ou "Bônus 08"
            r'[Bb][ôo]nus\s*[:\-]\s*0?(\d{1,2})',
            # "Classe: 8" (contexto de bônus)
            r'[Cc]lasse\s*[:\-]\s*0?(\d{1,2})',
            # "Perfil / Bônus ... 8"
            r'[Bb][ôo]nus[^\n]{0,30}?(\d{1,2})\b',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                val = int(match.group(1))
                if 1 <= val <= 10:
                    return str(val)
        return "N/D"

    def _extract_placa_generic(self, text):
        """Generic regex for Brazilian license plates (Mercosul or Old)."""
        # Patterns: ABC-1234 or ABC1234 or ABC1C34
        # Look for "Placa: XYZ..." or just the pattern if explicit

        # 1. Search for explicit "Placa" label
        match_lbl = re.search(r'Placa\s*[:\.]?\s*([A-Z]{3}[-\s]?\d[A-Z0-9]\d{2})', text, re.IGNORECASE)
        if match_lbl:
            return match_lbl.group(1).upper()

        # 2. Search for isolated pattern
        matches = re.findall(r'\b([A-Z]{3}[-\s]?\d[A-Z0-9]\d{2})\b', text)
        if matches:
            return matches[0].upper()

        return "Placa não informada"
