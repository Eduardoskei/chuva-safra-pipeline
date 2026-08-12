import pandas as pd
import numpy as np

def numero_ou_none(valor, casas: int):
    if pd.isna(valor):
        return None
    return round(float(valor), casas)


def serie_json(serie: pd.Series) -> dict:
    return {
        chave: (None if pd.isna(valor) else float(valor))
        for chave, valor in serie.to_dict().items()
    }

def calcular_produtividade(df: pd.DataFrame, col_qtd: str, col_area: str) -> pd.DataFrame:
    #Calcula a produtividade e trata a divisão por zero.
    df_analise = df.copy()
    area_valida = (df_analise[col_area] > 0) & (df_analise[col_area].notna())
    
    df_analise['produtividade'] = np.where(
        area_valida, 
        df_analise[col_qtd] / df_analise[col_area], 
        np.nan
    )
    
    qtd_zerados = (~area_valida).sum()
    if qtd_zerados > 0:
        print(f"⚠ Aviso: {qtd_zerados} registro(s) com '{col_area}' igual a zero ou nula.")
        print("   -> Produtividade definida como NaN para evitar divisão por zero.")
        
    return df_analise



def calcular_kpis(df: pd.DataFrame, perfil: str) -> dict:
    """
    Calcula KPIs dinâmicos conforme a regra de negócio central da rota.
    Conforme Item 1.6 - api_grafico.py
    """
    if perfil == "produtor":
        # Produtor vê médias do seu próprio município
        chuva_valida = df["chuva_total"].dropna()
        return {
            "produtividade_media": numero_ou_none(df["produtividade"].mean(), 2),
            "chuva_total": (
                numero_ou_none(chuva_valida.sum(), 1)
                if not chuva_valida.empty
                else None
            ),
        }

    if perfil == "tecnico":
        # Técnico vê comparação entre os municípios
        agrupado = df.groupby("nome_municipio")["produtividade"].mean().round(2)
        return {"produtividade_por_municipio": serie_json(agrupado)}

    if perfil == "gestor":
        # Gestor vê ranking estadual completo (ordenado)
        ranking = (
            df.groupby("nome_municipio")["produtividade"]
            .mean()
            .sort_values(ascending=False)
            .round(2)
        )
        return {"ranking_estadual": serie_json(ranking)}

    # perfil desconhecido -> resposta mínima, nunca vazar dado de outro perfil
    return {}
