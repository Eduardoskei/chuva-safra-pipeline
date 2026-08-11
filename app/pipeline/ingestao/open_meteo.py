import time
import requests
import pandas as pd
from app.pipeline.ingestao.geocoding import buscar_coordenadas

COLUNAS_CLIMA = ["nome_municipio", "uf", "data", "precipitacao_mm", "temperatura_maxima_c"]


def buscar_serie_climatica(latitude: float, longitude: float, data_inicio: str, data_fim: str) -> pd.DataFrame:
    url = "https://archive-api.open-meteo.com/v1/archive"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": data_inicio,
        "end_date": data_fim,
        "daily": "precipitation_sum,temperature_2m_max",
        "timezone": "America/Fortaleza",
    }

    try:
        resposta = requests.get(url, params=params, timeout=(3, 15))
        resposta.raise_for_status()
        dados = resposta.json()
    except requests.exceptions.RequestException as e:
        print(f"Erro ao consultar a API de histórico climático: {e}")
        return pd.DataFrame(columns=["data", "precipitacao_mm", "temperatura_maxima_c"])
    except ValueError:
        print("Resposta inválida (não é JSON) da API de histórico climático")
        return pd.DataFrame(columns=["data", "precipitacao_mm", "temperatura_maxima_c"])

    diario = dados.get("daily", {})
    datas = diario.get("time", [])

    if not datas:
        return pd.DataFrame(columns=["data", "precipitacao_mm", "temperatura_maxima_c"])

    return pd.DataFrame({
        "data": pd.to_datetime(datas),
        "precipitacao_mm": diario.get("precipitation_sum", []),
        "temperatura_maxima_c": diario.get("temperature_2m_max", []),
    })


def buscar_clima_municipio(nome_municipio: str, uf: str, data_inicio: str, data_fim: str) -> pd.DataFrame:
    latitude, longitude = buscar_coordenadas(nome_municipio, uf)
    if latitude is None or longitude is None:
        print(f"Aviso: não foi possível geocodificar '{nome_municipio}' ({uf}); sem dado climático.")
        return pd.DataFrame(columns=COLUNAS_CLIMA)

    serie = buscar_serie_climatica(latitude, longitude, data_inicio, data_fim)
    if serie.empty:
        return pd.DataFrame(columns=COLUNAS_CLIMA)

    serie["nome_municipio"] = nome_municipio
    serie["uf"] = uf
    return serie[COLUNAS_CLIMA]


def buscar_clima_municipios(municipios, data_inicio, data_fim):
    series = []
    falhas = []

    for nome_municipio, uf in municipios:
        print(f"Buscando clima de {nome_municipio} ({uf})...")

        latitude, longitude = buscar_coordenadas(nome_municipio, uf)
        if latitude is None or longitude is None:
            falhas.append({
                "nome_municipio": nome_municipio,
                "uf": uf,
                "motivo": "geocoding_nao_encontrado",
            })
            time.sleep(0.5)
            continue

        serie = buscar_serie_climatica(latitude, longitude, data_inicio, data_fim)
        if serie.empty:
            falhas.append({
                "nome_municipio": nome_municipio,
                "uf": uf,
                "motivo": "api_clima_sem_dados",
            })
            time.sleep(0.5)
            continue

        serie["nome_municipio"] = nome_municipio
        serie["uf"] = uf
        series.append(serie[COLUNAS_CLIMA])
        time.sleep(0.5)

    df_clima = pd.concat(series, ignore_index=True) if series else pd.DataFrame(columns=COLUNAS_CLIMA)
    df_falhas = pd.DataFrame(falhas, columns=["nome_municipio", "uf", "motivo"])

    return df_clima, df_falhas
