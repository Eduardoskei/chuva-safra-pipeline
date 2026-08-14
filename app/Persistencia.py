"""
Persistência dos dados tratados (produção agrícola e clima) no banco.

Espera receber os DataFrames já limpos por
app.pipeline.transformacao.limpar_produtos_df / limpar_clima_df,
com as colunas municipio_uf_chave / uf_normalizada já calculadas.
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd
from psycopg2.extras import execute_values

from app.database import get_conn, put_conn


COLUNAS_PRODUCAO = [
    "municipio_uf_chave", "municipio", "municipio_original", "uf",
    "uf_normalizada", "ano", "tipo_lavoura", "variavel_id", "variavel_nome",
    "unidade", "categoria_id", "categoria_nome", "valor",
]

COLUNAS_CLIMA = [
    "municipio_uf_chave", "nome_municipio", "nome_municipio_original", "uf",
    "uf_normalizada", "data", "precipitacao_mm", "temperatura_maxima_c",
]


def _valor_sql(valor: Any) -> Any:
    """Converte NaN/NaT/pd.NA para None e escalares numpy/pandas para tipo nativo."""
    if valor is None:
        return None
    if isinstance(valor, float) and math.isnan(valor):
        return None
    if pd.isna(valor):
        return None
    if hasattr(valor, "item"):
        return valor.item()
    return valor


def _preparar_linhas(df: pd.DataFrame, colunas: list[str]) -> list[tuple]:
    faltando = set(colunas) - set(df.columns)
    if faltando:
        raise ValueError(
            f"DataFrame não tem as colunas esperadas para persistência: {sorted(faltando)}. "
            "Confira se ele passou por limpar_produtos_df/limpar_clima_df."
        )

    df_preparado = df[colunas].copy()

    # categoria_id é parte da chave de unicidade -> não pode ir como NULL
    if "categoria_id" in df_preparado.columns:
        df_preparado["categoria_id"] = df_preparado["categoria_id"].fillna("")

    return [
        tuple(_valor_sql(v) for v in linha)
        for linha in df_preparado.itertuples(index=False, name=None)
    ]


def salvar_producao_agricola(df: pd.DataFrame) -> int:
    """Upsert das linhas de df_produtos na tabela producao_agricola."""
    if df.empty:
        return 0

    linhas = _preparar_linhas(df, COLUNAS_PRODUCAO)

    sql = """
        INSERT INTO producao_agricola (
            municipio_uf_chave, municipio, municipio_original, uf,
            uf_normalizada, ano, tipo_lavoura, variavel_id, variavel_nome,
            unidade, categoria_id, categoria_nome, valor
        )
        VALUES %s
        ON CONFLICT (municipio_uf_chave, ano, categoria_id, variavel_id, tipo_lavoura)
        DO UPDATE SET
            municipio          = EXCLUDED.municipio,
            municipio_original = EXCLUDED.municipio_original,
            uf                 = EXCLUDED.uf,
            uf_normalizada     = EXCLUDED.uf_normalizada,
            variavel_nome      = EXCLUDED.variavel_nome,
            unidade            = EXCLUDED.unidade,
            categoria_nome     = EXCLUDED.categoria_nome,
            valor              = EXCLUDED.valor,
            updated_at         = now();
    """

    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            execute_values(cur, sql, linhas)
    finally:
        put_conn(conn)

    return len(linhas)


def salvar_dados_clima(df: pd.DataFrame) -> int:
    """Upsert das linhas de df_clima na tabela clima_diario."""
    if df.empty:
        return 0

    df = df.copy()
    df["data"] = pd.to_datetime(df["data"]).dt.date  # datetime -> date puro

    linhas = _preparar_linhas(df, COLUNAS_CLIMA)

    sql = """
        INSERT INTO clima_diario (
            municipio_uf_chave, nome_municipio, nome_municipio_original, uf,
            uf_normalizada, data, precipitacao_mm, temperatura_maxima_c
        )
        VALUES %s
        ON CONFLICT (municipio_uf_chave, data)
        DO UPDATE SET
            nome_municipio          = EXCLUDED.nome_municipio,
            nome_municipio_original = EXCLUDED.nome_municipio_original,
            uf                      = EXCLUDED.uf,
            uf_normalizada          = EXCLUDED.uf_normalizada,
            precipitacao_mm         = EXCLUDED.precipitacao_mm,
            temperatura_maxima_c    = EXCLUDED.temperatura_maxima_c,
            updated_at              = now();
    """

    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            execute_values(cur, sql, linhas)
    finally:
        put_conn(conn)

    return len(linhas)


def salvar_dados_tratados(df_produtos: pd.DataFrame, df_clima: pd.DataFrame) -> dict[str, int]:
    """Ponto único de entrada: grava produção + clima, devolve quantas linhas cada tabela recebeu."""
    return {
        "producao_agricola": salvar_producao_agricola(df_produtos),
        "clima_diario": salvar_dados_clima(df_clima),
    }