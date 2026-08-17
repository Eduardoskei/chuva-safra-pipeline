"""
Transformação e limpeza dos dados brutos coletados no pipeline:

- Produção agrícola (IBGE, agregados 1612/1613) -> DataFrame limpo
- Clima (Open-Meteo, via buscar_clima_municipios)  -> DataFrame limpo

Função principal: processar_dados_brutos(...)
"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

# Códigos que o IBGE usa para indicar dado ausente/sigiloso/não aplicável
VALORES_AUSENTES_IBGE = {"-", "..", "...", "X", ""}


def normalizar_nome_municipio(nome: object) -> str:
    """Cria uma forma estavel do municipio para comparacoes e juncoes."""
    if pd.isna(nome):
        return ""

    texto = unicodedata.normalize("NFKD", str(nome).strip().casefold())
    texto = "".join(caractere for caractere in texto if not unicodedata.combining(caractere))
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return " ".join(texto.split())


def normalizar_uf(uf: object) -> str:
    """Padroniza a UF para uso na chave do municipio."""
    if pd.isna(uf):
        return ""
    return re.sub(r"[^A-Z]", "", str(uf).strip().upper())


def _adicionar_chaves_municipio(
    df: pd.DataFrame,
    coluna_municipio: str,
) -> pd.DataFrame:

    coluna_original = f"{coluna_municipio}_original"
    df[coluna_municipio] = df[coluna_municipio].astype("string").str.strip()
    df["uf"] = df["uf"].astype("string").str.strip().str.upper()
    df[coluna_original] = df[coluna_municipio]
    df["municipio_normalizado"] = df[coluna_municipio].map(normalizar_nome_municipio)
    df["uf_normalizada"] = df["uf"].map(normalizar_uf)
    df["municipio_uf_chave"] = (
        df["municipio_normalizado"] + "|" + df["uf_normalizada"]
    )
    return df


def _dividir_municipio_uf(nome_localidade: str) -> tuple[str, str]:
    
    if " - " in nome_localidade:
        municipio, uf = nome_localidade.rsplit(" - ", 1)
        return municipio.strip(), uf.strip()
    return nome_localidade.strip(), ""


def transformar_produtos_ibge(dados_brutos: list[dict]) -> pd.DataFrame:
   
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

    for coluna in ["categoria_nome", "variavel_nome", "tipo_lavoura"]:
        df[coluna] = df[coluna].astype(str).str.strip()

    df = _adicionar_chaves_municipio(df, "municipio")

    df = df.dropna(subset=["ano", "municipio"])
    df = df[df["municipio_normalizado"] != ""]
    df = df.drop_duplicates(
        subset=[
            "municipio_uf_chave", "ano", "categoria_id", "variavel_id", "tipo_lavoura"
        ]
    )
    df = df.sort_values(
        ["uf_normalizada", "municipio_normalizado", "ano", "tipo_lavoura"]
    ).reset_index(drop=True)

    return df


def limpar_clima_df(df: pd.DataFrame) -> pd.DataFrame:
    """Trata tipos, remove nulos e duplicatas do DataFrame climático."""
    if df.empty:
        return df

    df = df.copy()

    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df["precipitacao_mm"] = pd.to_numeric(df["precipitacao_mm"], errors="coerce")
    df["temperatura_maxima_c"] = pd.to_numeric(df["temperatura_maxima_c"], errors="coerce")

    df = _adicionar_chaves_municipio(df, "nome_municipio")

    df = df.dropna(subset=["data"])
    df = df[df["municipio_normalizado"] != ""]
    df = df.drop_duplicates(subset=["municipio_uf_chave", "data"])
    df = df.sort_values(
        ["uf_normalizada", "municipio_normalizado", "data"]
    ).reset_index(drop=True)

    return df


def processar_dados_brutos(
    dados_produtos_brutos: list[dict],
    dados_clima_brutos: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    
    df_produtos = transformar_produtos_ibge(dados_produtos_brutos)
    df_produtos = limpar_produtos_df(df_produtos)

    df_clima = limpar_clima_df(dados_clima_brutos)

    return df_produtos, df_clima
