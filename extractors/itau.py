from .porto import PortoBaseExtractor


class ItauExtractor(PortoBaseExtractor):
    def extract(self):
        self.data['insurer'] = 'ITAU'
        return self._extract_porto_common()
