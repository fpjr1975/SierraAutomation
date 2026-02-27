import os
import pdfplumber

from .yelum import YelumExtractor
from .mitsui import MitsuiExtractor
from .porto import PortoExtractor
from .azul import AzulExtractor
from .itau import ItauExtractor
from .porto_mitsui import PortoMitsuiExtractor
from .bradesco import BradescoExtractor
from .darwin import DarwinExtractor
from .allianz import AllianzExtractor
from .alfa import AlfaExtractor
from .ezze import EzzeExtractor
from .hdi import HdiExtractor
from .mapfre import MapfreExtractor
from .suhai import SuhaiExtractor
from .tokio import TokioExtractor
from .zurich import ZurichExtractor
from .suica import SuicaExtractor
from .aliro import AliroExtractor


class ExtractorFactory:
    @staticmethod
    def get_extractor(pdf_path):
        try:
            filename = os.path.basename(pdf_path).upper()
            print(f"Checking filename: {filename}")

            # 1. Read content FIRST
            text_upper = ""
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    if pdf.pages:
                        for i in range(min(2, len(pdf.pages))):
                            text_upper += (pdf.pages[i].extract_text() or "").upper() + "\n"
            except Exception as e:
                print(f"Error reading PDF content for ID: {e}")

            # 2. Strong Content Signals (Prioritize clear headers)
            # Use limited character range for most to avoid competitive mentions in footer/renewal sections
            head_300 = text_upper[:300]
            head_500 = text_upper[:500]
            head_1000 = text_upper[:1000]

            if "YELUM" in head_300 and "AUTOPERFIL" in head_300:
                 return YelumExtractor(pdf_path)

            if "TOKIO MARINE" in head_300:
                 return TokioExtractor(pdf_path)

            if "ALIRO" in head_300:
                 return AliroExtractor(pdf_path)

            # Porto Group: Sub-route to individual extractors based on header
            is_porto_group = False
            if "PORTO SEGURO" in head_500 or "PORTO SEGURO CIA DE SEGUROS" in head_1000:
                 is_porto_group = True
            elif "AZUL" in head_500 and ("SEGUROS" in head_500 or "COMPANHIA" in head_500 or "SEGURO AUTO" in head_500):
                 is_porto_group = True
            elif ("ITAÚ" in head_500 or "ITAU" in head_500) and "SEGURO AUTO" in head_500:
                 is_porto_group = True

            if is_porto_group:
                 # Use header (head_500) for sub-routing to avoid false matches
                 # from competitor mentions in body text
                 if "AZUL" in head_500:
                      return AzulExtractor(pdf_path)
                 elif "ITAÚ" in head_500 or "ITAU" in head_500:
                      return ItauExtractor(pdf_path)
                 elif "MITSUI" in head_500:
                      return PortoMitsuiExtractor(pdf_path)
                 else:
                      return PortoExtractor(pdf_path)

            if "SUHAI" in head_500:
                 return SuhaiExtractor(pdf_path)

            # HDI CHECK
            if ("HDI SEGUROS" in head_1000 and "AUTO PERFIL" in head_1000) or "HDI GLOBAL SEGUROS" in head_500:
                 return HdiExtractor(pdf_path)

            if "MITSUI" in head_500:
                 return MitsuiExtractor(pdf_path)

            if "EZZE SEGUROS" in head_500 or "EZZE SEGURADORA" in head_500:
                 return EzzeExtractor(pdf_path)

            if "ALFA SEGURADORA" in head_500:
                 return AlfaExtractor(pdf_path)

            if "ALLIANZ" in head_500:
                 return AllianzExtractor(pdf_path)

            if "BRADESCO" in head_500:
                 return BradescoExtractor(pdf_path)

            if "MAPFRE" in head_500:
                 return MapfreExtractor(pdf_path)

            if "ZURICH" in head_500:
                 return ZurichExtractor(pdf_path)

            if "SUÍÇA" in head_500 or "SUICA SEGURADORA" in head_500:
                 return SuicaExtractor(pdf_path)

            if "DARWIN" in head_500:
                 return DarwinExtractor(pdf_path)

            # Secondary checks (broad fallback)
            if "PORTO SEGURO" in text_upper: return PortoExtractor(pdf_path)
            if "TOKIO MARINE" in text_upper: return TokioExtractor(pdf_path)
            if "YELUM" in text_upper: return YelumExtractor(pdf_path)
            if "HDI SEGUROS" in text_upper: return HdiExtractor(pdf_path)
            if "ALIRO" in text_upper: return AliroExtractor(pdf_path)
            if "LIBERTY SEGUROS" in text_upper: return YelumExtractor(pdf_path)

            # 3. Fallback to Filename if content ambiguous
            if "ALFA" in filename: return AlfaExtractor(pdf_path)
            if "AZUL" in filename or "AZU" in filename: return AzulExtractor(pdf_path)
            if "PORTO" in filename: return PortoExtractor(pdf_path)
            if "ITA" in filename: return ItauExtractor(pdf_path)
            if "MITSUI" in filename or "MITISUI" in filename: return MitsuiExtractor(pdf_path)
            if "YELUM" in filename: return YelumExtractor(pdf_path)
            if "SUHAI" in filename: return SuhaiExtractor(pdf_path)
            if "ZURICH" in filename: return ZurichExtractor(pdf_path)
            if "ALLIANZ" in filename: return AllianzExtractor(pdf_path)
            if "BRADESCO" in filename: return BradescoExtractor(pdf_path)
            if "EZZE" in filename: return EzzeExtractor(pdf_path)
            if "MAPFRE" in filename: return MapfreExtractor(pdf_path)
            if "HDI" in filename: return HdiExtractor(pdf_path)
            if "TOKIO" in filename: return TokioExtractor(pdf_path)
            if "ALIRO" in filename: return AliroExtractor(pdf_path)
            if "SUICA" in filename or "SUIÇA" in filename: return SuicaExtractor(pdf_path)
            if "DARWIN" in filename: return DarwinExtractor(pdf_path)

            return None
        except Exception as e:
            print(f"Error identifying PDF: {e}")
            return None
