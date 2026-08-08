import requests
from app.utils import normalizar_nome
from app.database import get_coordenadas, salvar_coordenadas

def buscar_coordenadas(nome: str, uf_esperada: str = "Ceará"):
    cache = get_coordenadas(nome, uf_esperada)
    if cache:
        return cache

    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {
        "name": normalizar_nome(nome),
        "country": "BR",
        "count": 5,
        "language": "pt",
        "format": "json"
    }

    try:
        resposta = requests.get(url, params=params, timeout=10)
        resposta.raise_for_status()
        dados = resposta.json()
    except requests.exceptions.RequestException as e:
        print(f"Erro ao consultar a API de geocodificação: {e}")
        return None, None
    except ValueError:  # json.JSONDecodeError herda de ValueError
        print("Resposta inválida (não é JSON) da API")
        return None, None

    for lugar in dados.get("results", []):
        estado_encontrado = lugar.get("admin1", "")
        if normalizar_nome(uf_esperada) == normalizar_nome(estado_encontrado):
            latitude, longitude = lugar["latitude"], lugar["longitude"]
            salvar_coordenadas(nome, uf_esperada, latitude, longitude)
            return latitude, longitude

    return None, None

