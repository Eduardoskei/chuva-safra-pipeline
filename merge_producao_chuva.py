import pandas as pd
from utils import normalizar_nome


def validar_chave_unica(df: pd.DataFrame, chave: list[str], nome_base: str):
    #Garante que não há chaves repetidas antes do merge.
    if df.duplicated(subset=chave).any():
        raise ValueError(f"Erro: chaves duplicadas encontradas na base de {nome_base}!")


def cruzar_producao_clima_por_nome(df_producao: pd.DataFrame, df_clima: pd.DataFrame) -> pd.DataFrame:
    """
    Cruza produção e clima usando (nome_municipio normalizado + UF + ano)
    Espera que df_producao e df_clima tenham as colunas:
    'nome_municipio', 'uf', 'ano' (mais as colunas de valor de cada base).
    """
    df_producao = df_producao.copy()
    df_clima = df_clima.copy()

    df_producao["chave_nome"] = df_producao["nome_municipio"].map(normalizar_nome)
    df_clima["chave_nome"] = df_clima["nome_municipio"].map(normalizar_nome)
    df_producao["chave_uf"] = df_producao["uf"].map(normalizar_nome)
    df_clima["chave_uf"] = df_clima["uf"].map(normalizar_nome)

    chave = ["chave_nome", "chave_uf", "ano"]

    validar_chave_unica(df_producao, chave, "PRODUÇÃO")
    validar_chave_unica(df_clima, chave, "CLIMA")

    linhas_antes = len(df_producao)

    df_final = pd.merge(
        df_producao,
        df_clima,
        on=chave,
        how="left",
        validate="one_to_one",
        indicator=True,
        suffixes=("", "_clima"),
    )

    assert len(df_final) == linhas_antes, "O merge alterou a quantidade de linhas!"

    sem_clima = df_final[df_final["_merge"] == "left_only"]
    if not sem_clima.empty:
        print(f"⚠ Aviso: {len(sem_clima)} registro(s) sem dados climáticos (chave por nome).")
        print(sem_clima[["nome_municipio", "uf", "ano"]].head())

    df_final = df_final.drop(columns=["_merge", "chave_nome", "chave_uf"])
    return df_final