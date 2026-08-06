import requests
import unicodedata

    
def buscar_produtos_temporarias() -> list[dict[str, any]]:
    url = 'https://servicodados.ibge.gov.br/api/v3/agregados/1612/periodos/2015|2016|2017|2018|2019|2020|2021|2022|2023|2024/variaveis/216|214?localidades=N6[N3[23]]&classificacao=81[2692,2702,2708,2711]'

    try:
        response = requests.get(url, timeout=(3, 10))
        response.raise_for_status()
        data = response.json()

        print("Produtos temporárias buscados com sucesso!")
        return data

    except requests.RequestException as error:
        print(f"Falha ao buscar produtos temporárias: {error}")
        return []

def buscar_produtos_permanentes() -> list[dict[str, any]]:
    url = 'https://servicodados.ibge.gov.br/api/v3/agregados/1613/periodos/2015|2016|2017|2018|2019|2020|2021|2022|2023|2024/variaveis/216|214?localidades=N6[N3[23]]&classificacao=82[2720,40473,2727]'

    try:
        response = requests.get(url, timeout=(3, 10))
        response.raise_for_status()
        data = response.json()

        print("Produtos permanentes buscados com sucesso!")
        return data

    except requests.RequestException as error:
        print(f"Falha ao buscar produtos permanentes: {error}")
        return []


def normalizar_nome(nome: str) -> str:
    #Remove acentos, espaços extras e padroniza para minúsculas.
    nome = nome.strip().lower()
    return ''.join(
        c for c in unicodedata.normalize('NFD', nome)
        if unicodedata.category(c) != 'Mn'
    )

def buscar_coordenadas(nome: str, uf_esperada: str = "Ceará"):
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
        if normalizar_nome(uf_esperada) in normalizar_nome(estado_encontrado):
            return lugar["latitude"], lugar["longitude"]

    return None, None