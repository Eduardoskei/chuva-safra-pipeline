"""
Transformação e limpeza dos dados brutos coletados no pipeline:

- Produção agrícola (IBGE, agregados 1612/1613) -> DataFrame limpo
- Clima (Open-Meteo, via buscar_clima_municipios)  -> DataFrame limpo

Função principal: processar_dados_brutos(...)
"""
from __future__ import annotations

import pandas as pd

# Códigos que o IBGE usa para indicar dado ausente/sigiloso/não aplicável
VALORES_AUSENTES_IBGE = {"-", "..", "...", "X", ""}


def _dividir_municipio_uf(nome_localidade: str) -> tuple[str, str]:
    """Ex: 'Abaiara - CE' -> ('Abaiara', 'CE')."""
    if " - " in nome_localidade:
        municipio, uf = nome_localidade.rsplit(" - ", 1)
        return municipio.strip(), uf.strip()
    return nome_localidade.strip(), ""


def transformar_produtos_ibge(dados_brutos: list[dict]) -> pd.DataFrame:
    """
    Recebe a lista bruta retornada por buscar_produtos_nordeste()
    (uma lista de variáveis do IBGE, cada uma com resultados aninhados
    por classificação e por localidade/ano) e devolve um DataFrame
    em formato "long": uma linha por localidade x classificação x ano.
    """
    linhas = []

    for bloco_variavel in dados_brutos:
        variavel_id = bloco_variavel.get("id")
        variavel_nome = bloco_variavel.get("variavel")
        unidade = bloco_variavel.get("unidade")
        tipo_lavoura = bloco_variavel.get("tipo_lavoura")

        for resultado in bloco_variavel.get("resultados", []):
            classificacoes = resultado.get("classificacoes", [])
            categoria_id, categoria_nome = None, None
            if classificacoes:
                categoria_dict = classificacoes[0].get("categoria", {})
                if categoria_dict:
                    categoria_id, categoria_nome = next(iter(categoria_dict.items()))

            for serie_item in resultado.get("series", []):
                localidade = serie_item.get("localidade", {})
                municipio, uf_sigla = _dividir_municipio_uf(localidade.get("nome", ""))

                for ano, valor in serie_item.get("serie", {}).items():
                    linhas.append({
                        "variavel_id": variavel_id,
                        "variavel_nome": variavel_nome,
                        "unidade": unidade,
                        "categoria_id": categoria_id,
                        "categoria_nome": categoria_nome,
                        "municipio": municipio,
                        "uf": uf_sigla,
                        "ano": ano,
                        "valor": valor,
                        "tipo_lavoura": tipo_lavoura,
                    })

    colunas = [
        "variavel_id", "variavel_nome", "unidade", "categoria_id",
        "categoria_nome", "municipio", "uf", "ano", "valor", "tipo_lavoura",
    ]
    return pd.DataFrame(linhas, columns=colunas)


def limpar_produtos_df(df: pd.DataFrame) -> pd.DataFrame:
    """Trata tipos, remove valores ausentes/sigilosos e duplicatas."""
    if df.empty:
        return df

    df = df.copy()

    # Valores ausentes/sigilosos do IBGE -> NaN
    df["valor"] = df["valor"].where(~df["valor"].isin(VALORES_AUSENTES_IBGE))
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")

    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")

    for coluna in ["municipio", "uf", "categoria_nome", "variavel_nome", "tipo_lavoura"]:
        df[coluna] = df[coluna].astype(str).str.strip()

    df = df.dropna(subset=["ano", "municipio"])
    df = df.drop_duplicates(
        subset=["municipio", "uf", "ano", "categoria_id", "variavel_id", "tipo_lavoura"]
    )
    df = df.sort_values(["uf", "municipio", "ano", "tipo_lavoura"]).reset_index(drop=True)

    return df


def limpar_clima_df(df: pd.DataFrame) -> pd.DataFrame:
    """Trata tipos, remove nulos e duplicatas do DataFrame climático."""
    if df.empty:
        return df

    df = df.copy()

    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df["precipitacao_mm"] = pd.to_numeric(df["precipitacao_mm"], errors="coerce")
    df["temperatura_maxima_c"] = pd.to_numeric(df["temperatura_maxima_c"], errors="coerce")

    for coluna in ["nome_municipio", "uf"]:
        df[coluna] = df[coluna].astype(str).str.strip()

    df = df.dropna(subset=["data"])
    df = df.drop_duplicates(subset=["nome_municipio", "uf", "data"])
    df = df.sort_values(["uf", "nome_municipio", "data"]).reset_index(drop=True)

    return df


def processar_dados_brutos(
    dados_produtos_brutos: list[dict],
    dados_clima_brutos: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Recebe:
      - dados_produtos_brutos: saída de buscar_produtos_nordeste()
      - dados_clima_brutos: saída de buscar_clima_municipios(...)

    Transforma e limpa cada fonte e devolve os DataFrames separadamente:
      (df_produtos, df_clima)
    """
    df_produtos = transformar_produtos_ibge(dados_produtos_brutos)
    df_produtos = limpar_produtos_df(df_produtos)

    df_clima = limpar_clima_df(dados_clima_brutos)

    return df_produtos, df_clima