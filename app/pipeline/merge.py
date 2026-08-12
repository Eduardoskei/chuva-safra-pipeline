import pandas as pd
from app.utils import normalizar_nome, MAPA_UF

COLUNAS_CHAVE_ORIGINAIS = ["nome_municipio", "uf", "ano"]
COLUNAS_RELATORIO_SEM_CLIMA = ["nome_municipio", "uf", "ano", "mensagem"]
MENSAGEM_SEM_CLIMA = "Sem dado climático correspondente para município/ano"


def validar_chave_unica(df: pd.DataFrame, chave: list[str], nome_base: str):
    if df.duplicated(subset=chave).any():
        raise ValueError(f"Erro: chaves duplicadas encontradas na base de {nome_base}!")


def normalizar_chaves(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")
    df["chave_nome"] = df["nome_municipio"].map(normalizar_nome)
    df["chave_uf"] = df["uf"].map(normalizar_nome).replace(MAPA_UF)
    return df


def clima_vazio() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUNAS_CHAVE_ORIGINAIS)


def preparar_clima_para_merge(df_clima: pd.DataFrame) -> pd.DataFrame:
    if df_clima.empty:
        return clima_vazio()

    df_clima = df_clima.copy()

    if "nome_municipio" not in df_clima.columns or "uf" not in df_clima.columns:
        return clima_vazio()

    if "ano" not in df_clima.columns:
        if "data" not in df_clima.columns:
            return clima_vazio()
        df_clima["data"] = pd.to_datetime(df_clima["data"], errors="coerce")
        df_clima["ano"] = df_clima["data"].dt.year

    if "chuva_total" not in df_clima.columns and "precipitacao_mm" in df_clima.columns:
        df_clima["precipitacao_mm"] = pd.to_numeric(df_clima["precipitacao_mm"], errors="coerce")
        agregacoes = {"precipitacao_mm": "sum"}
        if "temperatura_maxima_c" in df_clima.columns:
            df_clima["temperatura_maxima_c"] = pd.to_numeric(df_clima["temperatura_maxima_c"], errors="coerce")
            agregacoes["temperatura_maxima_c"] = "mean"

        df_clima = (
            df_clima
            .dropna(subset=["ano"])
            .groupby(COLUNAS_CHAVE_ORIGINAIS, as_index=False)
            .agg(agregacoes)
            .rename(columns={
                "precipitacao_mm": "chuva_total",
                "temperatura_maxima_c": "temperatura_maxima_media_c",
            })
        )

    return df_clima


def montar_relatorio_sem_clima(df_merge: pd.DataFrame) -> list[dict]:
    if "_merge" not in df_merge.columns:
        return []

    colunas_existentes = [coluna for coluna in COLUNAS_CHAVE_ORIGINAIS if coluna in df_merge.columns]
    if len(colunas_existentes) != len(COLUNAS_CHAVE_ORIGINAIS):
        return []

    relatorio = (
        df_merge.loc[df_merge["_merge"] == "left_only", COLUNAS_CHAVE_ORIGINAIS]
        .drop_duplicates()
        .sort_values(["uf", "nome_municipio", "ano"])
        .reset_index(drop=True)
    )

    if relatorio.empty:
        return []

    relatorio["ano"] = relatorio["ano"].astype(int)
    relatorio["mensagem"] = MENSAGEM_SEM_CLIMA
    return relatorio[COLUNAS_RELATORIO_SEM_CLIMA].to_dict(orient="records")


def gerar_relatorio_municipios_sem_clima(df_producao: pd.DataFrame, df_clima: pd.DataFrame) -> list[dict]:
    if df_producao.empty:
        return []

    df_producao = normalizar_chaves(df_producao)
    df_clima = normalizar_chaves(preparar_clima_para_merge(df_clima))
    chave = ["chave_nome", "chave_uf", "ano"]
    colunas_producao = ["nome_municipio", "uf", "ano", "chave_nome", "chave_uf"]

    df_merge = pd.merge(
        df_producao[colunas_producao].drop_duplicates(),
        df_clima[chave].drop_duplicates(),
        on=chave,
        how="left",
        indicator=True,
    )

    return montar_relatorio_sem_clima(df_merge)


def cruzar_producao_clima_por_nome(df_producao: pd.DataFrame, df_clima: pd.DataFrame) -> pd.DataFrame:
    df_producao = normalizar_chaves(df_producao)
    df_clima = normalizar_chaves(preparar_clima_para_merge(df_clima))

    chave = ["chave_nome", "chave_uf", "ano"]

    validar_chave_unica(df_producao, chave, "PRODUÇÃO")
    validar_chave_unica(df_clima, chave, "CLIMA")

    linhas_antes = len(df_producao)

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
        sem_clima = pd.DataFrame(montar_relatorio_sem_clima(df_final))
        print(sem_clima[COLUNAS_RELATORIO_SEM_CLIMA].head())

    if clima_descartado > 0:
        print(f"Info: {clima_descartado} registro(s) de CLIMA descartados por não terem produção correspondente ('right_only').")
    print("----------------------------\n")

    relatorio_sem_clima = montar_relatorio_sem_clima(df_final)

    df_final = df_final[df_final["_merge"].isin(["both", "left_only"])].copy()
    df_final["clima_disponivel"] = df_final["_merge"].eq("both")
    df_final["mensagem_clima"] = None
    df_final.loc[~df_final["clima_disponivel"], "mensagem_clima"] = MENSAGEM_SEM_CLIMA

    if "chuva_total" not in df_final.columns:
        df_final["chuva_total"] = pd.NA

    assert len(df_final) == linhas_antes, "O merge alterou a quantidade de linhas originais da produção!"

    df_final = df_final.drop(columns=["_merge", "chave_nome", "chave_uf"])
    df_final.attrs["municipios_sem_clima"] = relatorio_sem_clima

    return df_final
