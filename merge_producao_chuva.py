import pandas as pd
from utils import normalizar_nome, MAPA_UF


def validar_chave_unica(df: pd.DataFrame, chave: list[str], nome_base: str):
    #Garante que não há chaves repetidas antes do merge.
    if df.duplicated(subset=chave).any():
        raise ValueError(f"Erro: chaves duplicadas encontradas na base de {nome_base}!")

def cruzar_producao_clima_por_nome(df_producao: pd.DataFrame, df_clima: pd.DataFrame) -> pd.DataFrame:
    """
    Cruza produção e clima usando (nome_municipio normalizado + UF + ano).
    Garante tipagem de ano e consistência de nomenclatura de estado.
    """
    df_producao = df_producao.copy()
    df_clima = df_clima.copy()

    # Tipagem rigorosa para evitar falha de match por int vs str
    df_producao["ano"] = df_producao["ano"].astype(int)
    df_clima["ano"] = df_clima["ano"].astype(int)

    # Normalização dos textos
    df_producao["chave_nome"] = df_producao["nome_municipio"].map(normalizar_nome)
    df_clima["chave_nome"] = df_clima["nome_municipio"].map(normalizar_nome)
    
    df_producao["chave_uf"] = df_producao["uf"].map(normalizar_nome)
    df_clima["chave_uf"] = df_clima["uf"].map(normalizar_nome)

    # Traduz os nomes dos estados para siglas usando o dicionário do utils.py
    df_producao["chave_uf"] = df_producao["chave_uf"].replace(MAPA_UF)
    df_clima["chave_uf"] = df_clima["chave_uf"].replace(MAPA_UF)

    chave = ["chave_nome", "chave_uf", "ano"]

    # Validações pré-merge
    validar_chave_unica(df_producao, chave, "PRODUÇÃO")
    validar_chave_unica(df_clima, chave, "CLIMA")

    linhas_antes = len(df_producao)

    # O Merge (usando outer para capturar o clima descartado)
    df_final = pd.merge(
        df_producao,
        df_clima,
        on=chave,
        how="outer", 
        validate="one_to_one",
        indicator=True,
        suffixes=("", "_clima"),
    )

    # Contabilizar cenários
    bateram = len(df_final[df_final["_merge"] == "both"])
    orfaos = len(df_final[df_final["_merge"] == "left_only"])
    clima_descartado = len(df_final[df_final["_merge"] == "right_only"])

    print("\n📊 --- RELATÓRIO DE MERGE ---")
    print(f"✅ Sucesso: {bateram} registros cruzados perfeitamente ('both').")
    
    if orfaos > 0:
        print(f"⚠ Aviso: {orfaos} registro(s) de PRODUÇÃO ficaram órfãos sem clima ('left_only').")
        sem_clima = df_final[df_final["_merge"] == "left_only"]
        print(sem_clima[["nome_municipio", "uf", "ano"]].head())
        
    if clima_descartado > 0:
        print(f"Info: {clima_descartado} registro(s) de CLIMA descartados por não terem produção correspondente ('right_only').")
    print("----------------------------\n")

    # Restaurando o comportamento de LEFT JOIN (mantém both e left_only)
    df_final = df_final[df_final["_merge"].isin(["both", "left_only"])].copy()

    # Validação pós-merge
    assert len(df_final) == linhas_antes, "O merge alterou a quantidade de linhas originais da produção!"

    # Limpeza final
    df_final = df_final.drop(columns=["_merge", "chave_nome", "chave_uf"])
    
    return df_final