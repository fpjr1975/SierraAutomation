from .porto import PortoBaseExtractor


class PortoMitsuiExtractor(PortoBaseExtractor):
    def extract(self):
        self.data['insurer'] = 'MITSUI'
        return self._extract_porto_common()
