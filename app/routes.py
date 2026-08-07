from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import pandas as pd

from app.pipeline.analises import calcular_kpis

router = APIRouter()

# ==========================================
# MODELOS DE CONTRATO (PYDANTIC)
# ==========================================
class PontoData(BaseModel):
    ano: int
    chuva: float
    produtividade: Optional[float] # Permite nulos para os casos de divisão por zero

class KPIs(BaseModel):
    media_produtividade: float
    media_chuva: float
    variacao_ano_anterior: float
    escopo_visao: str

class DadosResponse(BaseModel):
    pontos: List[PontoData]
    kpis: Dict[str, Any]

# ==========================================
# ROTA: GET /dados
# ==========================================
@router.get("/dados", response_model=DadosResponse)
#query estritamente obrigatório (...) condições de validação e descrição para cada parâmetro 
def obter_dados(
    perfil: str = Query(..., description="Perfil do usuário (produtor, tecnico, gestor)"), 
    municipios: str = Query(..., description="Municípios separados por vírgula"),
    cultura: str = Query(..., description="Cultura agrícola"),
    de: int = Query(..., description="Ano de início"),
    ate: int = Query(..., description="Ano de fim")
):
    lista_municipios = [m.strip() for m in municipios.split(",")]

    #descomentar a linha abaixo quando a função de pipeline estiver implementada
    # df_final = executar_pipeline_completo(lista_municipios, cultura, de, ate)
    
  # DF temporário atualizado com as colunas reais exigidas pelo time:
    df_final = pd.DataFrame({
        'ano': [2020, 2021, 2022],
        'municipio': ['Amontada', 'Amontada', 'Abaiara'], 
        'chuva_total': [812.4, 650.1, 900.5],             
        'produtividade': [2.7, 1.5, 2.1] 
    })
    
    df_contrato = df_final[['ano', 'chuva_total', 'produtividade']].rename(
        columns={'chuva_total': 'chuva'}
    )

    # to_dict('records') converte a tabela perfeitamente para o formato JSON esperado
    pontos_reais = df_contrato.to_dict(orient='records')
    
    # Calcula os KPIs reais passando a tabela para a sua função de análises
    kpis_reais = calcular_kpis(df=df_final, perfil=perfil)
    
    return {"pontos": pontos_reais, "kpis": kpis_reais}

# ==========================================
# ROTA: GET /mapa 
# ==========================================
@router.get("/mapa", response_class=HTMLResponse)
def obter_mapa(
    perfil: str = Query(...),
    municipios: str = Query(...),
    cultura: str = Query(...),
    de: int = Query(...),
    ate: int = Query(...)
):
    """Devolve o HTML do mapa Folium conforme perfil e recorte."""
    lista_municipios = [m.strip() for m in municipios.split(",")]
    
    # ==============================================================
    # Inserir a chamada da função do Folium aqui.
    # Exemplo: html_mapa = gerar_mapa_coropletico(lista_municipios, perfil)
    # ==============================================================
    
    html_provisorio = """
    <html>
        <body style="font-family: sans-serif; text-align: center; margin-top: 50px;">
            <h2>🗺️ Mapa em construção</h2>
            <p>Aguardando renderização do Folium pelo time de Dados.</p>
        </body>
    </html>
    """
    
    return html_provisorio