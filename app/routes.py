from fastapi import APIRouter, Query, HTTPException, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict, Literal
from app.utils import normalizar
import pandas as pd
from app.pipeline.analises import calcular_kpis, resumir_analise
from app.pipeline.orchestrator import executar_pipeline_completo, obter_relatorio_sem_clima

router = APIRouter()
PerfilType = Literal["produtor", "tecnico", "gestor"]
class PontoData(BaseModel):
    municipio: str
    ano: int
    chuva: Optional[float] = None
    produtividade: Optional[float] = None

class KPIsProdutor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    produtividade_media: Optional[float] = None
    chuva_total: Optional[float] = None
    anos_sem_dado_climatico: Optional[int] = None

class KPIsTecnico(BaseModel):
    model_config = ConfigDict(extra="forbid")
    produtividade_por_municipio: Dict[str, Optional[float]]
    municipios_sem_clima: List[str] = []

class KPIsGestor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ranking_estadual: Dict[str, Optional[float]]
    cobertura_climatica: Optional[Dict[str, int]] = None

class KPIsVazio(BaseModel):
    model_config = ConfigDict(extra="forbid")


KPIsType = KPIsProdutor | KPIsTecnico | KPIsGestor | KPIsVazio


class AnaliseResponse(BaseModel):
    metodo_correlacao: str
    correlacao_chuva_produtividade: Optional[float] = None
    observacoes_validas: int
    janela_chuva: str
    interpretacao: str

class DadosResponse(BaseModel):
    pontos: List[PontoData]
    kpis: KPIsType
    analise: AnaliseResponse
    avisos: List[str] = []

class RegistroSemClima(BaseModel):
    nome_municipio: str
    uf: str
    ano: int
    motivo: str


class RelatorioSemClimaResponse(BaseModel):
    total: int
    registros: List[RegistroSemClima]


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

def _relatorio_mock() -> pd.DataFrame:
    # Mock temporário até existir app/pipeline/orchestrator com o
    # df_final completo (todos municípios, não só o recorte pedido).
    return pd.DataFrame(columns=["nome_municipio", "uf", "ano", "motivo"])

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
    lista_municipios: list[str] = Depends(parse_municipios),
    cultura: str = Query(..., description="Cultura agrícola"),
    de: int = Query(..., description="Ano de início"),
    ate: int = Query(..., description="Ano de fim"),
):
    if de > ate:
        raise HTTPException(400, "'de' não pode ser maior que 'ate'")

    df_final = executar_pipeline_completo(lista_municipios, cultura, de, ate)
    _validar_contrato(df_final)

    lista_municipios_norm = [normalizar(m) for m in lista_municipios]
    cultura_norm = normalizar(cultura)

    df_final = df_final[
        df_final["nome_municipio"].apply(normalizar).isin(lista_municipios_norm)
        & (df_final["cultura"].apply(normalizar) == cultura_norm)
        & df_final["ano"].between(de, ate)
    ]

    if df_final.empty:
        return {"pontos": [], "kpis": {}, "analise": resumir_analise(df_final), "avisos": [
            "Nenhum dado encontrado para esse recorte (município/cultura/período)."
        ]}

    municipios_retornados = set(df_final["nome_municipio"].apply(normalizar))
    faltando = [m for m, n in zip(lista_municipios, lista_municipios_norm) if n not in municipios_retornados]
    avisos = [f"Sem dado para '{m}' nesse recorte (possivelmente sem clima ou sem cultivo dessa cultura)." for m in faltando]

    df_contrato = df_final[["nome_municipio", "ano", "chuva_total", "produtividade"]].rename(
        columns={"nome_municipio": "municipio", "chuva_total": "chuva"}
    )

    df_contrato = df_contrato.where(pd.notna(df_contrato), None)
    pontos = df_contrato.to_dict(orient="records")

    try:
        kpis = calcular_kpis(df=df_final, perfil=perfil)
    except KeyError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Não foi possível calcular os KPIs, coluna ausente: {e}",
        )

    return {"pontos": pontos, "kpis": kpis, "analise": resumir_analise(df_final), "avisos": avisos}


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

@router.get("/relatorio/sem-clima", response_model=RelatorioSemClimaResponse)
def relatorio_sem_clima():
    """
    Transparência do merge: quais município/ano têm produção no IBGE
    mas ficaram sem correspondência climática, e por quê.
    """
    try:
        from app.pipeline.merge import construir_relatorio_sem_clima
        # df_final = executar_pipeline_completo(...)  # troque quando existir
        df_final = obter_relatorio_sem_clima([], "", 0, 9999)  # placeholder
        relatorio = construir_relatorio_sem_clima(df_final)
    except ImportError:
        relatorio = _relatorio_mock()
    except Exception as e:
        print(f"Erro ao gerar relatório de clima ausente: {e}")
        return {"total": 0, "registros": []}

    return {"total": int(len(relatorio)), "registros": relatorio.to_dict(orient="records")}