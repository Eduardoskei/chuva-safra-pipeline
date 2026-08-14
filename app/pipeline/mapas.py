from typing import Literal
import branca.colormap as cm
import folium
import pandas as pd
import requests

from app.database import get_data, update_data
from app.utils import normalizar_nome, MAPA_UF

PerfilType = Literal["produtor", "tecnico", "gestor"]
MetricaType = Literal["produtividade", "chuva"]

# Códigos de UF do IBGE (mesmos do pipeline de ingestão)
CODIGO_UF_POR_SIGLA = {
    "ma": 21, "pi": 22, "ce": 23, "rn": 24, "pb": 25,
    "pe": 26, "al": 27, "se": 28, "ba": 29,
}

CENTRO_NORDESTE = (-9.5, -40.0)

LABEL_METRICA = {
    "produtividade": "Produtividade média no período (t/ha)",
    "chuva": "Chuva total média no período (mm)",
}

COLUNA_POR_METRICA = {
    "produtividade": "produtividade",
    "chuva": "chuva_total",
}

# ----------------------------------------------------------------------
# Tradução nome -> código do município e malha GeoJSON (cacheadas)
# ----------------------------------------------------------------------

def uf_para_codigo(uf: str) -> int | None:
    sigla = MAPA_UF.get(normalizar_nome(uf), normalizar_nome(uf))
    return CODIGO_UF_POR_SIGLA.get(sigla)


def obter_municipios_uf(codigo_uf: int) -> list[dict]:
    """[{'id': '2300101', 'nome': 'Abaiara'}, ...] para uma UF. Cacheada."""
    chave = f"municipios_uf_{codigo_uf}"
    cache = get_data(chave)
    if cache:
        return cache

    url = f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{codigo_uf}/municipios"
    try:
        resposta = requests.get(url, timeout=(3, 15))
        resposta.raise_for_status()
        dados = resposta.json()
    except (requests.exceptions.RequestException, ValueError) as e:
        print(f"Erro ao buscar municípios da UF {codigo_uf}: {e}")
        return []

    municipios = [{"id": str(m["id"]), "nome": m["nome"]} for m in dados]
    update_data(chave, municipios)
    return municipios


def mapa_nome_para_codigo(codigo_uf: int) -> dict[str, str]:
    """{'nome normalizado': 'codigo_ibge'} de uma UF."""
    return {normalizar_nome(m["nome"]): m["id"] for m in obter_municipios_uf(codigo_uf)}


def obter_geojson_uf(codigo_uf: int) -> dict:
    """Malha municipal da UF em GeoJSON (propriedade 'codarea' por feature). Cacheada."""
    chave = f"malha_uf_{codigo_uf}"
    cache = get_data(chave)
    if cache:
        return cache

    url = f"https://servicodados.ibge.gov.br/api/v3/malhas/estados/{codigo_uf}"
    params = {
        "formato": "application/vnd.geo+json",
        "intrarregiao": "municipio",
        "qualidade": "minima",  
    }
    try:
        resposta = requests.get(url, params=params, timeout=(3, 30))
        resposta.raise_for_status()
        geojson = resposta.json()
    except (requests.exceptions.RequestException, ValueError) as e:
        print(f"Erro ao buscar malha da UF {codigo_uf}: {e}")
        return {"type": "FeatureCollection", "features": []}

    update_data(chave, geojson)
    return geojson


# ----------------------------------------------------------------------
# Fonte dos dados (produção x clima já cruzados)
# ----------------------------------------------------------------------

def carregar_dados(municipios: list[str], cultura: str, de: int, ate: int) -> pd.DataFrame:
    """
    Busca o df_final (produção + clima já cruzados) do orquestrador.
    Enquanto app/pipeline/orchestrator não existir, cai num mock local
    só para o /mapa não quebrar em desenvolvimento -- mesma postura do
    _pipeline_mock em routes.py.
    """
    try:
        from app.pipeline.orchestrator import executar_pipeline_completo
        return executar_pipeline_completo(municipios, cultura, de, ate)
    except ImportError:
        print("Aviso: app/pipeline/orchestrator ainda não existe; usando mock local no mapa.")
        return pd.DataFrame({
            "nome_municipio": ["Amontada", "Amontada", "Abaiara", "Abaiara"],
            "uf": ["Ceará", "Ceará", "Ceará", "Ceará"],
            "ano": [2020, 2021, 2020, 2021],
            "cultura": ["Milho", "Milho", "Feijão", "Milho"],
            "chuva_total": [812.4, 650.1, 900.5, 700.0],
            "produtividade": [2.7, 1.5, 2.1, 1.9],
        })


def _agregar_metrica(df: pd.DataFrame, metrica: MetricaType) -> pd.DataFrame:
    """Uma linha por (município, uf): média da métrica nos anos do recorte."""
    coluna = COLUNA_POR_METRICA[metrica]
    if coluna not in df.columns:
        raise KeyError(f"Coluna '{coluna}' ausente para montar o mapa de {metrica}")

    agrupado = (
        df.dropna(subset=[coluna])
        .groupby(["nome_municipio", "uf"], as_index=False)[coluna]
        .mean()
        .rename(columns={coluna: "valor"})
    )
    agrupado["valor"] = agrupado["valor"].round(2)
    return agrupado


# ----------------------------------------------------------------------
# Montagem do mapa
# ----------------------------------------------------------------------

def mapa_mensagem(mensagem: str) -> str:
    """HTML simples (sem Folium) para os casos em que não há o que desenhar."""
    fmap = folium.Map(location=CENTRO_NORDESTE, zoom_start=5, tiles="cartodbpositron")
    folium.Marker(
        location=CENTRO_NORDESTE,
        tooltip=mensagem,
        icon=folium.Icon(color="gray", icon="info-sign"),
    ).add_to(fmap)
    fmap.get_root().html.add_child(folium.Element(
        f'<div style="position:fixed;top:10px;left:50px;z-index:9999;'
        f'background:white;padding:8px 12px;border-radius:6px;'
        f'box-shadow:0 1px 4px rgba(0,0,0,.3);font-family:sans-serif;">{mensagem}</div>'
    ))
    return fmap.get_root().render()


def gerar_mapa(
    perfil: PerfilType,
    municipios: list[str],
    cultura: str,
    de: int,
    ate: int,
    metrica: MetricaType = "produtividade",
    df_final: pd.DataFrame | None = None,
) -> str:
    """
    Monta o mapa coroplético e devolve o HTML já renderizado
    (folium.Map.get_root().render()), pronto para a rota GET /mapa
    devolver como HTMLResponse.

    perfil='gestor'            -> malha inteira da(s) UF(s) envolvida(s),
                                   municípios sem valor ficam cinza (visão de risco/cobertura).
    perfil='tecnico'/'produtor' -> só os municípios do recorte pedido, com zoom ajustado.
    """
    if de > ate:
        raise ValueError("'de' não pode ser maior que 'ate'")
    if not municipios:
        return mapa_mensagem("Informe ao menos um município.")

    if df_final is None:
        df_final = carregar_dados(municipios, cultura, de, ate)

    if df_final is None or df_final.empty:
        return mapa_mensagem(f"Sem dados de {cultura} entre {de} e {ate}.")

    municipios_norm = {normalizar_nome(m) for m in municipios}
    df_recorte = df_final[
        df_final["nome_municipio"].map(normalizar_nome).isin(municipios_norm)
        & df_final["cultura"].map(normalizar_nome).eq(normalizar_nome(cultura))
        & df_final["ano"].between(de, ate)
    ]
    if df_recorte.empty:
        return mapa_mensagem("Nenhum dos municípios pedidos tem dado nesse recorte.")

    df_valores = _agregar_metrica(df_recorte, metrica)

    codigos_uf = sorted({c for c in df_valores["uf"].map(uf_para_codigo) if c is not None})
    if not codigos_uf:
        return mapa_mensagem("UF não reconhecida para os municípios pedidos.")

    # junta a malha de todas as UFs envolvidas (no caso do técnico/gestor
    # cobrindo mais de um estado do Nordeste)
    features = []
    nome_por_codigo: dict[str, str] = {}
    for codigo_uf in codigos_uf:
        geojson_uf = obter_geojson_uf(codigo_uf)
        features.extend(geojson_uf.get("features", []))
        nome_por_codigo.update({v: k for k, v in mapa_nome_para_codigo(codigo_uf).items()})

    if not features:
        return mapa_mensagem("Não foi possível carregar a malha do IBGE para essa(s) UF(s).")

    # nome_municipio -> codigo_ibge, município a município (uma UF por vez,
    # pra não confundir municípios homônimos de estados diferentes)
    def _buscar_codigo(linha) -> str | None:
        codigo_uf = uf_para_codigo(linha["uf"])
        if codigo_uf is None:
            return None
        return mapa_nome_para_codigo(codigo_uf).get(normalizar_nome(linha["nome_municipio"]))

    df_valores["codigo_ibge"] = df_valores.apply(_buscar_codigo, axis=1)

    sem_codigo = df_valores[df_valores["codigo_ibge"].isna()]
    df_valores = df_valores.dropna(subset=["codigo_ibge"]).copy()

    if not sem_codigo.empty:
        nomes = ", ".join(sem_codigo["nome_municipio"].tolist())
        print(f"Aviso: {len(sem_codigo)} município(s) sem código IBGE localizado (nome não bateu na malha): {nomes}")

    if df_valores.empty:
        return mapa_mensagem("Nenhum município do recorte foi localizado na malha do IBGE.")

    valor_por_codigo = dict(zip(df_valores["codigo_ibge"], df_valores["valor"]))
    municipio_por_codigo = dict(zip(df_valores["codigo_ibge"], df_valores["nome_municipio"]))

    # gestor enxerga o estado inteiro (cinza onde não há dado = sinaliza cobertura);
    # produtor/técnico só o recorte pedido, pra não vazar dado de fora do que o perfil vê
    if perfil == "gestor":
        features_exibidas = features
    else:
        features_exibidas = [f for f in features if f["properties"].get("codarea") in valor_por_codigo]

    # injeta nome e valor nas properties do GeoJSON, pra tooltip mostrar
    # município + valor (a malha do IBGE só traz 'codarea')
    for feature in features_exibidas:
        codigo = feature["properties"].get("codarea")
        feature["properties"]["nome_municipio"] = municipio_por_codigo.get(
            codigo, nome_por_codigo.get(codigo, "—")
        )
        valor = valor_por_codigo.get(codigo)
        feature["properties"]["valor_str"] = f"{valor:.2f}" if valor is not None else "sem dado"

    escala = cm.linear.YlGnBu_09.scale(df_valores["valor"].min(), df_valores["valor"].max())
    escala.caption = LABEL_METRICA[metrica]

    fmap = folium.Map(location=CENTRO_NORDESTE, zoom_start=6, tiles="cartodbpositron")

    def _estilo(feature):
        codigo = feature["properties"].get("codarea")
        valor = valor_por_codigo.get(codigo)
        return {
            "fillColor": escala(valor) if valor is not None else "#d9d9d9",
            "color": "#555555",
            "weight": 0.7,
            "fillOpacity": 0.78 if valor is not None else 0.35,
        }

    camada = folium.GeoJson(
        {"type": "FeatureCollection", "features": features_exibidas},
        name=LABEL_METRICA[metrica],
        style_function=_estilo,
        highlight_function=lambda f: {"weight": 2, "color": "#222222"},
        tooltip=folium.GeoJsonTooltip(
            fields=["nome_municipio", "valor_str"],
            aliases=["Município:", f"{LABEL_METRICA[metrica]}:"],
            sticky=True,
        ),
    )
    camada.add_to(fmap)
    escala.add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)

    if perfil in ("produtor", "tecnico"):
        # zoom só na área do recorte pedido; gestor mantém a visão do estado inteiro
        try:
            fmap.fit_bounds(camada.get_bounds())
        except (ValueError, AttributeError):
            pass  # bounds vazio (ex: geometria ausente) -> mantém o zoom padrão

    return fmap.get_root().render()