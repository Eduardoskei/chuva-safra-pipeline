import unittest

import pandas as pd

from app.pipeline.limpeza import limpar_clima_df, normalizar_nome_municipio


class TestNormalizacaoMunicipios(unittest.TestCase):
    def test_acentos_caixa_e_espacos_geram_o_mesmo_nome(self):
        variantes = ["São Luís", "Sao Luis", "  SÃO   LUÍS  "]

        self.assertEqual(
            {normalizar_nome_municipio(nome) for nome in variantes},
            {"sao luis"},
        )

    def test_variantes_do_mesmo_municipio_e_uf_sao_deduplicadas(self):
        df = pd.DataFrame(
            {
                "nome_municipio": ["São Luís", " sao  luis "],
                "uf": ["MA", "ma"],
                "data": ["2025-01-01", "2025-01-01"],
                "precipitacao_mm": [10, 10],
                "temperatura_maxima_c": [30, 30],
            }
        )

        resultado = limpar_clima_df(df)

        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado.loc[0, "nome_municipio_original"], "São Luís")
        self.assertEqual(resultado.loc[0, "municipio_uf_chave"], "sao luis|MA")

    def test_municipios_homonimos_em_ufs_diferentes_sao_preservados(self):
        df = pd.DataFrame(
            {
                "nome_municipio": ["Bom Jesus", "BOM JESUS"],
                "uf": ["PI", "RN"],
                "data": ["2025-01-01", "2025-01-01"],
                "precipitacao_mm": [5, 8],
                "temperatura_maxima_c": [31, 29],
            }
        )

        resultado = limpar_clima_df(df)

        self.assertEqual(len(resultado), 2)
        self.assertEqual(set(resultado["municipio_uf_chave"]), {"bom jesus|PI", "bom jesus|RN"})


if __name__ == "__main__":
    unittest.main()
