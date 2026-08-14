"""

Liga as pontas do pipeline: ingestão (IBGE + Open-Meteo) -> transformação
-> merge -> análise, e cacheia o resultado final na tabela genérica
`ibge_cache` (já usada pelo geocoding e pelo mapa) para que as rotas
/dados, /mapa e /relatorio/sem-clima não refaçam o pipeline inteiro a
cada requisição.

Uso para atualizar o cache (cron / job manual, NÃO a cada request):
    from app.pipeline.orchestrator import atualizar_cache_pipeline
    atualizar_cache_pipeline()

⚠️ IMPORTANTE (leia antes de rodar):
Este pipeline busca clima diário para TODOS os municípios do Nordeste
que aparecem na produção agrícola (milhares de chamadas à Open-Meteo,
uma por município, com sleep entre elas). É pesado e demorado — não é
para rodar dentro do ciclo de uma requisição HTTP em produção. O cache
de 24h evita repetir isso a todo request, mas a PRIMEIRA carga deve ser
feita por fora (script/cron), não pelo usuário esperando na tela.

⚠️ Ponto de atenção em merge.py:
`cruzar_producao_clima_por_nome` valida chave única (nome+uf+ano) nos
DOIS lados antes do merge. Só que `df_producao` tem uma linha por
(município, uf, ano, CULTURA) — ou seja, um município com milho e
feijão no mesmo ano gera duas linhas com a mesma chave (nome+uf+ano),
e `validar_chave_unica` vai estourar `ValueError` nesse caso (que é o
caso normal, não a exceção). O clima não depende de cultura, então o
certo é ou (a) incluir `cultura` na chave de validação apenas do lado
da produção, ou (b) trocar `validate="one_to_one"` por
`validate="many_to_one"` e não validar unicidade de `df_producao`.
Isso é um ajuste em `app/pipeline/merge.py`, fora do escopo deste
arquivo — mas o orchestrator vai quebrar até isso ser corrigido lá.
"""
from datetime import datetime, timedelta, timezone
import pandas as pd
from app.database import get_data, update_data
from app.pipeline.ingestao.ibge import buscar_produtos_nordeste
from app.pipeline.ingestao.open_meteo import buscar_clima_municipios
from app.pipeline.limpeza import transformar_produtos_ibge, limpar_produtos_df, limpar_clima_df
from app.pipeline.analises import preparar_producao_ibge, agregar_chuva_por_safra
from app.pipeline.merge import (
    cruzar_producao_clima_por_nome,
    construir_relatorio_sem_clima,
    enriquecer_relatorio_com_motivo_geocoding,
)

# ----------------------------------------------------------------------
# Configuração
# ----------------------------------------------------------------------

CHAVE_CACHE_PIPELINE = "pipeline_completo_nordeste_v1"
CACHE_TTL = timedelta(hours=24)

DATA_INICIO_CLIMA = "2015-01-01"
DATA_FIM_CLIMA = "2024-12-31"

MES_INICIO_SAFRA = 10
MES_FIM_SAFRA = 3

COLUNAS_FINAL_ESPERADAS = {
    "nome_municipio", "uf", "ano", "cultura", "chuva_total", "produtividade",
}


# ----------------------------------------------------------------------
# Cache (serialização do df_final + relatório em JSON, na ibge_cache)
# ----------------------------------------------------------------------

def cache_valido(payload: dict | None) -> bool:
    if not payload or "gerado_em" not in payload:
        return False
    try:
        gerado_em = datetime.fromisoformat(payload["gerado_em"])
    except (ValueError, TypeError):
        return False
    return datetime.now(timezone.utc) - gerado_em < CACHE_TTL


def serializar(df_final: pd.DataFrame, df_relatorio: pd.DataFrame) -> dict:
    return {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "df_final": df_final.to_json(orient="records", date_format="iso"),
        "df_relatorio": df_relatorio.to_json(orient="records", date_format="iso"),
    }


def desserializar(payload: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    df_final = pd.read_json(payload["df_final"], orient="records")
    df_relatorio = pd.read_json(payload["df_relatorio"], orient="records")

    if not df_final.empty and "ano" in df_final.columns:
        df_final["ano"] = pd.to_numeric(df_final["ano"], errors="coerce").astype("Int64")
    for coluna in ("nome_municipio", "uf", "cultura"):
        if coluna in df_final.columns:
            df_final[coluna] = df_final[coluna].astype(str)

    if not df_relatorio.empty and "ano" in df_relatorio.columns:
        df_relatorio["ano"] = pd.to_numeric(df_relatorio["ano"], errors="coerce").astype("Int64")

    return df_final, df_relatorio


# ----------------------------------------------------------------------
# Etapas do pipeline
# ----------------------------------------------------------------------

def ingestao_e_preparo_producao() -> pd.DataFrame:
    """IBGE bruto -> long -> limpo -> pivotado com produtividade calculada."""
    dados_brutos = buscar_produtos_nordeste()
    df_long = transformar_produtos_ibge(dados_brutos)
    df_long = limpar_produtos_df(df_long)
    return preparar_producao_ibge(df_long)


def pares_municipio_uf(df_producao: pd.DataFrame) -> list[tuple[str, str]]:
    """Lista única de (município, uf) presentes na produção, para não
    geocodificar/buscar clima de município que não tem dado agrícola."""
    return list(
        df_producao[["nome_municipio", "uf"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )


def ingestao_e_agregacao_clima(
    pares_municipio_uf: list[tuple[str, str]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Open-Meteo bruto (diário) -> limpo -> somado por safra."""
    df_clima_bruto, df_falhas_geocoding = buscar_clima_municipios(
        pares_municipio_uf, DATA_INICIO_CLIMA, DATA_FIM_CLIMA
    )
    df_clima = limpar_clima_df(df_clima_bruto)
    df_chuva_safra = agregar_chuva_por_safra(
        df_clima, mes_inicio=MES_INICIO_SAFRA, mes_fim=MES_FIM_SAFRA
    )
    return df_chuva_safra, df_falhas_geocoding


def _validar_saida(df_final: pd.DataFrame) -> None:
    faltando = COLUNAS_FINAL_ESPERADAS - set(df_final.columns)
    if faltando:
        raise RuntimeError(
            f"Pipeline gerou df_final sem as colunas esperadas: {sorted(faltando)}. "
            "Confira se merge.py/analises.py mudaram de schema."
        )


# ----------------------------------------------------------------------
# API pública
# ----------------------------------------------------------------------

def construir_pipeline_bruto(forcar: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Roda o pipeline do zero (ou lê do cache, se válido) e devolve
    (df_final, df_relatorio_sem_clima). `forcar=True` ignora o cache —
    use para o job de atualização, não em código de request HTTP.
    """
    if not forcar:
        cache = get_data(CHAVE_CACHE_PIPELINE)
        if cache_valido(cache):
            return desserializar(cache)

    df_producao = ingestao_e_preparo_producao()
    pares = pares_municipio_uf(df_producao)
    df_chuva_safra, df_falhas_geocoding = ingestao_e_agregacao_clima(pares)

    df_final = cruzar_producao_clima_por_nome(df_producao, df_chuva_safra)
    _validar_saida(df_final)

    df_relatorio = construir_relatorio_sem_clima(df_final)
    df_relatorio = enriquecer_relatorio_com_motivo_geocoding(df_relatorio, df_falhas_geocoding)

    update_data(CHAVE_CACHE_PIPELINE, serializar(df_final, df_relatorio))
    return df_final, df_relatorio


def executar_pipeline_completo(
    municipios: list[str],
    cultura: str,
    de: int,
    ate: int,
) -> pd.DataFrame:
    """
    Ponto de entrada chamado por routes.py e mapas.py.

    Devolve o df_final COMPLETO (todos os municípios do Nordeste, todas
    as culturas e anos) — filtrar por `municipios`/`cultura`/`de`/`ate`
    é responsabilidade de quem chama (routes.py já faz esse filtro),
    assim o cache do pipeline fica único e reaproveitado entre perfis
    e recortes diferentes, em vez de recalcular por combinação.

    Os parâmetros ficam na assinatura por compatibilidade com o
    contrato das rotas; se no futuro o recorte de datas passar a
    controlar a janela de busca do clima (em vez da janela fixa
    2015-2024), é aqui que isso entraria.
    """
    df_final, _ = construir_pipeline_bruto(forcar=False)
    return df_final


def obter_relatorio_sem_clima() -> pd.DataFrame:
    """Usado pela rota GET /relatorio/sem-clima."""
    _, df_relatorio = construir_pipeline_bruto(forcar=False)
    return df_relatorio


def atualizar_cache_pipeline() -> pd.DataFrame:
    """Força recomputar tudo e regravar o cache. Chame isso de um
    cron/script separado (ex: 1x/dia), nunca de dentro de uma rota."""
    df_final, _ = construir_pipeline_bruto(forcar=True)
    return df_final


if __name__ == "__main__":
    # python -m app.pipeline.orchestrator
    resultado = atualizar_cache_pipeline()
    print(f"Pipeline atualizado: {len(resultado)} linhas no df_final.")