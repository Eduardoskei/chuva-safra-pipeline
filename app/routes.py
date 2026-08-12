from fastapi import APIRouter, Query, HTTPException, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from app.utils import normalizar
import pandas as pd

from app.pipeline.analises import calcular_kpis
from app.pipeline.merge import MENSAGEM_SEM_CLIMA


# from app.pipeline.orchestrator import executar_pipeline_completo

router = APIRouter()

# ==========================================
# MODELOS DE CONTRATO (PYDANTIC)
# ==========================================
PerfilType = Literal["produtor", "tecnico", "gestor"]


class PontoData(BaseModel):
    municipio: str
    ano: int
    chuva: Optional[float] = None
    produtividade: Optional[float] = None
    clima_disponivel: bool = True
    mensagem_clima: Optional[str] = None

class KPIsProdutor(BaseModel):
    produtividade_media: Optional[float] = None
    chuva_total: Optional[float] = None


class KPIsTecnico(BaseModel):
    produtividade_por_municipio: Dict[str, Optional[float]]


class KPIsGestor(BaseModel):
    ranking_estadual: Dict[str, Optional[float]]


class KPIsVazio(BaseModel):
    pass


KPIsType = KPIsProdutor | KPIsTecnico | KPIsGestor | KPIsVazio


class MunicipioSemClima(BaseModel):
    municipio: str
    uf: Optional[str] = None
    ano: int
    mensagem: str

class DadosResponse(BaseModel):
    pontos: List[PontoData]
    kpis: KPIsType
    municipios_sem_clima: List[MunicipioSemClima] = Field(default_factory=list)


# Colunas que a rota /dados exige de quem quer que produza o df final.
COLUNAS_ESPERADAS = {"nome_municipio", "uf", "ano", "cultura", "chuva_total", "produtividade"}


def parse_municipios(municipios: str = Query(..., description="Municípios separados por vírgula")) -> list[str]:
    """
    Dependency compartilhada entre /dados e /mapa.
    Faz split por vírgula, remove espaços e descarta itens vazios
    (ex: "Amontada,,Sobral" não gera item em branco).
    """
    lista = [m.strip() for m in municipios.split(",") if m.strip()]
    if not lista:
        raise HTTPException(400, "informe ao menos um município em 'municipios'")
    return lista


def _pipeline_mock(municipios: list[str], cultura: str, de: int, ate: int) -> pd.DataFrame:

    # Mock temporário até app/pipeline/orchestrator.executar_pipeline_completo

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


def _valor_json(valor: Any):
    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass

    if hasattr(valor, "item"):
        return valor.item()

    return valor


def _limpar_json(obj: Any):
    if isinstance(obj, dict):
        return {chave: _limpar_json(valor) for chave, valor in obj.items()}
    if isinstance(obj, list):
        return [_limpar_json(item) for item in obj]
    return _valor_json(obj)


def _preparar_info_clima(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "clima_disponivel" not in df.columns:
        df["clima_disponivel"] = df["chuva_total"].notna()
    else:
        df["clima_disponivel"] = df["clima_disponivel"].fillna(False).astype(bool)

    if "mensagem_clima" not in df.columns:
        df["mensagem_clima"] = None

    sem_clima = ~df["clima_disponivel"]
    df.loc[sem_clima & df["mensagem_clima"].isna(), "mensagem_clima"] = MENSAGEM_SEM_CLIMA

    return df


def _gerar_relatorio_sem_clima_api(df: pd.DataFrame) -> list[dict]:
    if df.empty or "clima_disponivel" not in df.columns:
        return []

    sem_clima = df[~df["clima_disponivel"]].copy()
    if sem_clima.empty:
        return []

    relatorio = (
        sem_clima[["nome_municipio", "uf", "ano", "mensagem_clima"]]
        .dropna(subset=["ano"])
        .drop_duplicates()
        .sort_values(["uf", "nome_municipio", "ano"])
        .rename(columns={"nome_municipio": "municipio", "mensagem_clima": "mensagem"})
    )
    relatorio["ano"] = relatorio["ano"].astype(int)

    return _limpar_json(relatorio.to_dict(orient="records"))


# ==========================================
# ROTA: GET /dados
# ==========================================
@router.get("/dados", response_model=DadosResponse)
def obter_dados(
    perfil: PerfilType = Query(..., description="Perfil do usuário (produtor, tecnico, gestor)"),
    lista_municipios: list[str] = Depends(parse_municipios),
    cultura: str = Query(..., description="Cultura agrícola"),
    de: int = Query(..., description="Ano de início"),
    ate: int = Query(..., description="Ano de fim"),
):
    if de > ate:
        raise HTTPException(400, "'de' não pode ser maior que 'ate'")

    # ------------------------------------------------------------------
    # PONTO DE TROCA: comente a linha do mock e descomente as duas
    # linhas abaixo assim que executar_pipeline_completo() existir.
    # ------------------------------------------------------------------
    df_final = _pipeline_mock(lista_municipios, cultura, de, ate)
        # df_final = executar_pipeline_completo(...)

    _validar_contrato(df_final)

    lista_municipios_norm = [normalizar(m) for m in lista_municipios]
    cultura_norm = normalizar(cultura)

    df_final = df_final[
        df_final["nome_municipio"].apply(normalizar).isin(lista_municipios_norm)
        & (df_final["cultura"].apply(normalizar) == cultura_norm)
        & df_final["ano"].between(de, ate)
    ]

    if df_final.empty:
        return {"pontos": [], "kpis": {}, "municipios_sem_clima": []}

    df_final = _preparar_info_clima(df_final)
    municipios_sem_clima = _gerar_relatorio_sem_clima_api(df_final)

    df_contrato = df_final[
        [
            "nome_municipio",
            "ano",
            "chuva_total",
            "produtividade",
            "clima_disponivel",
            "mensagem_clima",
        ]
    ].rename(
        columns={"nome_municipio": "municipio", "chuva_total": "chuva"}
    )

    pontos = _limpar_json(df_contrato.to_dict(orient="records"))

    try:
        kpis = calcular_kpis(df=df_final, perfil=perfil)
    except KeyError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Não foi possível calcular os KPIs, coluna ausente: {e}",
        )

    return {
        "pontos": pontos,
        "kpis": _limpar_json(kpis),
        "municipios_sem_clima": municipios_sem_clima,
    }


# ==========================================
# ROTA: GET /mapa
# ==========================================
@router.get("/mapa", response_class=HTMLResponse)
def obter_mapa(
    perfil: PerfilType = Query(...),
    lista_municipios: list[str] = Depends(parse_municipios),
    cultura: str = Query(...),
    de: int = Query(...),
    ate: int = Query(...),
):
    """Devolve o HTML do mapa Folium conforme perfil e recorte."""

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
