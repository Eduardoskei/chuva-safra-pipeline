import numpy as np
import pandas as pd

def calcular_produtividade(df: pd.DataFrame, col_qtd: str = "producao", col_area: str = "area_colhida") -> pd.DataFrame:
    """Calcula produção/área colhida e invalida denominadores não positivos."""
    faltantes = {col_qtd, col_area} - set(df.columns)
    if faltantes:
        raise KeyError(f"Colunas ausentes para calcular produtividade: {sorted(faltantes)}")

    resultado = df.copy()
    producao = pd.to_numeric(resultado[col_qtd], errors="coerce")
    area = pd.to_numeric(resultado[col_area], errors="coerce")
    area_valida = area.gt(0) & area.notna()

    resultado["produtividade"] = producao.div(area).where(area_valida)
    return resultado


def preparar_producao_ibge(df: pd.DataFrame) -> pd.DataFrame:
    obrigatorias = {
        "variavel_id", "valor", "municipio", "uf", "ano",
        "categoria_id", "categoria_nome", "tipo_lavoura",
    }

    faltantes = obrigatorias - set(df.columns)

    if faltantes:
        raise KeyError(f"Colunas ausentes nos dados do IBGE: {sorted(faltantes)}")

    dados = df.copy()
    dados["variavel_id"] = dados["variavel_id"].astype(str)
    dados["valor"] = pd.to_numeric(dados["valor"], errors="coerce")
    dados["ano"] = pd.to_numeric(dados["ano"], errors="coerce")
    dados = dados[dados["variavel_id"].isin({"214", "216"})]

    indice = [
        "municipio", "uf", "ano", "categoria_id", "categoria_nome",
        "tipo_lavoura",
    ]
    tabela = (
        dados.pivot_table(index=indice, columns="variavel_id", values="valor", aggfunc="first")
        .rename(columns={"214": "producao", "216": "area_colhida"})
        .reset_index()
        .rename(columns={"municipio": "nome_municipio", "categoria_nome": "cultura"})
    )
    for coluna in ("producao", "area_colhida"):
        if coluna not in tabela:
            tabela[coluna] = np.nan

    tabela["ano"] = tabela["ano"].astype("Int64")
    return calcular_produtividade(tabela)


def agregar_chuva_por_safra(df_clima: pd.DataFrame, mes_inicio: int = 10, mes_fim: int = 3) -> pd.DataFrame:
    if not 1 <= mes_inicio <= 12 or not 1 <= mes_fim <= 12:
        raise ValueError("mes_inicio e mes_fim devem estar entre 1 e 12")

    obrigatorias = {"nome_municipio", "uf", "data", "precipitacao_mm"}
    faltantes = obrigatorias - set(df_clima.columns)
    if faltantes:
        raise KeyError(f"Colunas ausentes nos dados climáticos: {sorted(faltantes)}")

    clima = df_clima.copy()
    clima["data"] = pd.to_datetime(clima["data"], errors="coerce")
    clima["precipitacao_mm"] = pd.to_numeric(clima["precipitacao_mm"], errors="coerce")
    clima = clima.dropna(subset=["data"])
    mes = clima["data"].dt.month

    cruza_ano = mes_inicio > mes_fim
    if cruza_ano:
        na_janela = mes.ge(mes_inicio) | mes.le(mes_fim)
        clima = clima.loc[na_janela].copy()
        clima["ano"] = clima["data"].dt.year + clima["data"].dt.month.ge(mes_inicio).astype(int)
    else:
        clima = clima.loc[mes.between(mes_inicio, mes_fim)].copy()
        clima["ano"] = clima["data"].dt.year

    return (
        clima.groupby(["nome_municipio", "uf", "ano"], as_index=False, dropna=False)
        .agg(chuva_total=("precipitacao_mm", lambda serie: serie.sum(min_count=1)))
        .sort_values(["uf", "nome_municipio", "ano"])
        .reset_index(drop=True)
    )


def calcular_correlacao(df: pd.DataFrame, col_chuva: str = "chuva_total", col_produtividade: str = "produtividade") -> float:
    """Retorna a correlação de Pearson; NaN indica amostra/variação insuficiente."""
    faltantes = {col_chuva, col_produtividade} - set(df.columns)
    if faltantes:
        raise KeyError(f"Colunas ausentes para calcular correlação: {sorted(faltantes)}")

    pares = df[[col_chuva, col_produtividade]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(pares) < 2 or pares.nunique().min() < 2:
        return float("nan")
    return float(pares[col_chuva].corr(pares[col_produtividade], method="pearson"))


def resumir_analise(df: pd.DataFrame) -> dict:
    """Produz o resultado reportável da análise exploratória."""
    pares_validos = df[["chuva_total", "produtividade"]].dropna()
    correlacao = calcular_correlacao(df)
    return {
        "metodo_correlacao": "Pearson",
        "correlacao_chuva_produtividade": None if np.isnan(correlacao) else round(correlacao, 4),
        "observacoes_validas": int(len(pares_validos)),
        "janela_chuva": "outubro do ano anter"
        ""
        "ior a março do ano da safra",
    }

def sanitizar(valor):
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except TypeError:
        pass
    return valor


def calcular_kpis(df: pd.DataFrame, perfil: str) -> dict:
    if df is None or df.empty:
        return {}

    if perfil == "produtor":
        produtividade_media = df["produtividade"].mean() if df["produtividade"].notna().any() else None
        chuva_total = df["chuva_total"].sum() if df["chuva_total"].notna().any() else None
        return {
            "produtividade_media": sanitizar(round(produtividade_media, 2)) if produtividade_media is not None else None,
            "chuva_total": sanitizar(round(chuva_total, 1)) if chuva_total is not None else None,
            "anos_sem_dado_climatico": int(df["chuva_total"].isna().sum()),
        }

    if perfil == "tecnico":
        agrupado = df.groupby("nome_municipio")["produtividade"].mean().round(2)
        sem_clima = (
            df.groupby("nome_municipio")["chuva_total"]
            .apply(lambda s: bool(s.isna().all()))
        )
        return {
            "produtividade_por_municipio": {m: sanitizar(v) for m, v in agrupado.items()},
            "municipios_sem_clima": [m for m, sem in sem_clima.items() if sem],
        }

    if perfil == "gestor":
        ranking = df.groupby("nome_municipio")["produtividade"].mean().sort_values(ascending=False).round(2)
        total = df["nome_municipio"].nunique()
        com_clima = df.loc[df["chuva_total"].notna(), "nome_municipio"].nunique()
        return {
            "ranking_estadual": {m: sanitizar(v) for m, v in ranking.items()},
            "cobertura_climatica": {
                "total_municipios": int(total),
                "com_dado_climatico": int(com_clima),
                "sem_dado_climatico": int(total - com_clima),
            },
        }

    return {}