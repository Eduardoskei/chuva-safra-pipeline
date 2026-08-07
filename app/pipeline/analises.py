import pandas as pd
import numpy as np

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
        return {
            "produtividade_media": round(df["produtividade"].mean(), 2),
            "chuva_total": round(df["chuva_total"].sum(), 1),
        }

    if perfil == "tecnico":
        # Técnico vê comparação entre os municípios
        agrupado = df.groupby("municipio")["produtividade"].mean().round(2)
        return {"produtividade_por_municipio": agrupado.to_dict()}

    if perfil == "gestor":
        # Gestor vê ranking estadual completo (ordenado)
        ranking = (
            df.groupby("municipio")["produtividade"]
            .mean()
            .sort_values(ascending=False)
            .round(2)
        )
        return {"ranking_estadual": ranking.to_dict()}

    # perfil desconhecido -> resposta mínima, nunca vazar dado de outro perfil
    return {}