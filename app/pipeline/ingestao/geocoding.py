import requests
from app.utils import normalizar_nome, MAPA_UF
from app.database import get_coordenadas, salvar_coordenadas

NOME_POR_SIGLA = {sigla: nome for nome, sigla in MAPA_UF.items()}

def para_nome_completo(uf: str) -> str:
    chave = normalizar_nome(uf)
    if chave in MAPA_UF:
        return chave
    return NOME_POR_SIGLA.get(chave, chave)

def buscar_coordenadas(nome: str, uf_esperada: str):
    cache = get_coordenadas(nome, uf_esperada)
    if cache:
        return cache

    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {
        "name": normalizar_nome(nome),
        "country": "BR",
        "count": 5,
        "language": "pt",
        "format": "json",
    }

    try:
        resposta = requests.get(url, params=params, timeout=10)
        resposta.raise_for_status()
        dados = resposta.json()
    except requests.exceptions.RequestException as e:
        print(f"Erro ao consultar a API de geocodificação: {e}")
        return None, None
    except ValueError:
        print("Resposta inválida (não é JSON) da API")
        return None, None

    nome_uf_esperado = para_nome_completo(uf_esperada)

    for lugar in dados.get("results", []):
        estado_encontrado = lugar.get("admin1", "")  # API sempre devolve nome completo
        nome_uf_encontrado = normalizar_nome(estado_encontrado)

        if nome_uf_esperado == nome_uf_encontrado:
            latitude, longitude = lugar["latitude"], lugar["longitude"]
            print(f"{nome}, {uf_esperada}: ({latitude}, {longitude})")
            salvar_coordenadas(nome, uf_esperada, latitude, longitude)
            return latitude, longitude

    return None, None