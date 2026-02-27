from .porto import PortoBaseExtractor


class AzulExtractor(PortoBaseExtractor):
    def extract(self):
        self.data['insurer'] = 'AZUL'
        return self._extract_porto_common()
