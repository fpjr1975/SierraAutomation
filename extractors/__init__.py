from .base import BaseExtractor
from .factory import ExtractorFactory
from .yelum import YelumExtractor
from .mitsui import MitsuiExtractor
from .porto import PortoExtractor, PortoBaseExtractor
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

# Backward compatibility alias
PortoGroupExtractor = PortoExtractor

__all__ = [
    'BaseExtractor',
    'ExtractorFactory',
    'YelumExtractor',
    'MitsuiExtractor',
    'PortoExtractor',
    'PortoBaseExtractor',
    'PortoGroupExtractor',
    'AzulExtractor',
    'ItauExtractor',
    'PortoMitsuiExtractor',
    'BradescoExtractor',
    'DarwinExtractor',
    'AllianzExtractor',
    'AlfaExtractor',
    'EzzeExtractor',
    'HdiExtractor',
    'MapfreExtractor',
    'SuhaiExtractor',
    'TokioExtractor',
    'ZurichExtractor',
    'SuicaExtractor',
    'AliroExtractor',
]
