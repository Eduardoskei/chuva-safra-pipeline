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