from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Literal
import pandas as pd

from app.pipeline.analises import calcular_kpis


# from app.pipeline.orchestrator import executar_pipeline_completo

router = APIRouter()

# ==========================================
# MODELOS DE CONTRATO (PYDANTIC)
# ==========================================
PerfilType = Literal["produtor", "tecnico", "gestor"]


class PontoData(BaseModel):
    ano: int
    chuva: Optional[float] = None
    produtividade: Optional[float] = None


class DadosResponse(BaseModel):
    pontos: List[PontoData]
    kpis: Dict[str, Any]


# Colunas que a rota /dados exige de quem quer que produza o df final.
COLUNAS_ESPERADAS = {"nome_municipio", "uf", "ano", "cultura", "chuva_total", "produtividade"}


def _pipeline_mock(municipios: list[str], cultura: str, de: int, ate: int) -> pd.DataFrame:
    
    #Mock temporário até app/pipeline/orchestrator.executar_pipeline_completo

    return pd.DataFrame({
        "nome_municipio": ["Amontada", "Amontada", "Abaiara", "Abaiara"],
        "uf": ["Ceará", "Ceará", "Ceará", "Ceará"],
        "ano": [2020, 2021, 2020, 2021],
        "cultura": ["Milho", "Milho", "Feijão", "Milho"],
        "chuva_total": [812.4, 650.1, 900.5, 700.0],
        "produtividade": [2.7, 1.5, 2.1, 1.9],
    })


def _validar_contrato(df: pd.DataFrame) -> None:
    faltando = COLUNAS_ESPERADAS - set(df.columns)
    if faltando:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Pipeline devolveu dados incompletos, faltam colunas: {sorted(faltando)}. "
                "Isso normalmente indica que app/pipeline/merge.py ou analises.py "
                "mudou de schema sem atualizar o contrato desta rota."
            ),
        )


# ==========================================
# ROTA: GET /dados
# ==========================================
@router.get("/dados", response_model=DadosResponse)
def obter_dados(
    perfil: PerfilType = Query(..., description="Perfil do usuário (produtor, tecnico, gestor)"),
    municipios: str = Query(..., description="Municípios separados por vírgula"),
    cultura: str = Query(..., description="Cultura agrícola"),
    de: int = Query(..., description="Ano de início"),
    ate: int = Query(..., description="Ano de fim"),
):
    lista_municipios = [m.strip() for m in municipios.split(",") if m.strip()]
    if not lista_municipios:
        raise HTTPException(400, "informe ao menos um município em 'municipios'")
    if de > ate:
        raise HTTPException(400, "'de' não pode ser maior que 'ate'")

    # ------------------------------------------------------------------
    # PONTO DE TROCA: comente a linha do mock e descomente as duas
    # linhas abaixo assim que executar_pipeline_completo() existir.
    # ------------------------------------------------------------------
    df_final = _pipeline_mock(lista_municipios, cultura, de, ate)
    # df_final = executar_pipeline_completo(
    #     municipios=lista_municipios, cultura=cultura, de=de, ate=ate
    # )

    _validar_contrato(df_final)

    df_final = df_final[
        df_final["nome_municipio"].isin(lista_municipios)
        & (df_final["cultura"] == cultura)
        & df_final["ano"].between(de, ate)
    ]

    if df_final.empty:
        return {"pontos": [], "kpis": {}}

    df_contrato = df_final[["ano", "chuva_total", "produtividade"]].rename(
        columns={"chuva_total": "chuva"}
    )
    pontos = df_contrato.to_dict(orient="records")

    try:
        kpis = calcular_kpis(df=df_final, perfil=perfil)
    except KeyError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Não foi possível calcular os KPIs, coluna ausente: {e}",
        )

    return {"pontos": pontos, "kpis": kpis}


# ==========================================
# ROTA: GET /mapa
# ==========================================
@router.get("/mapa", response_class=HTMLResponse)
def obter_mapa(
    perfil: PerfilType = Query(...),
    municipios: str = Query(...),
    cultura: str = Query(...),
    de: int = Query(...),
    ate: int = Query(...),
):
    """Devolve o HTML do mapa Folium conforme perfil e recorte."""
    lista_municipios = [m.strip() for m in municipios.split(",") if m.strip()]
    if not lista_municipios:
        raise HTTPException(400, "informe ao menos um município em 'municipios'")

    # Mesmo ponto de troca do /dados: app/pipeline/mapas.py ainda não
    # existe. Quando existir com uma função gerar_mapa(...), esta rota
    # passa a usá-la automaticamente — nenhuma mudança de código aqui.
    try:
        from app.pipeline.mapas import gerar_mapa
    except ImportError:
        return HTMLResponse(
            """
            <html>
                <body style="font-family: sans-serif; text-align: center; margin-top: 50px;">
                    <h2>🗺️ Mapa em construção</h2>
                    <p>Aguardando app/pipeline/mapas.py do time de Dados
                    (depende de folium + GeoJSON dos municípios do Ceará).</p>
                </body>
            </html>
            """
        )

    try:
        html_mapa = gerar_mapa(
            perfil=perfil,
            municipios=lista_municipios,
            cultura=cultura,
            de=de,
            ate=ate,
        )
    except Exception as e:
        return HTMLResponse(
            f"""
            <html>
                <body style="font-family: sans-serif; text-align: center; margin-top: 50px;">
                    <h2>⚠️ Não foi possível gerar o mapa</h2>
                    <p>{type(e).__name__}: não foi possível processar o recorte pedido.</p>
                </body>
            </html>
            """
        )

    return HTMLResponse(html_mapa)