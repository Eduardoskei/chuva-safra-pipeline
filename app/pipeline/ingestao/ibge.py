import requests
import json
import time

ESTADOS_NORDESTE = {
    21: "Maranhão",
    22: "Piauí",
    23: "Ceará",
    24: "Rio Grande do Norte",
    25: "Paraíba",
    26: "Pernambuco",
    27: "Alagoas",
    28: "Sergipe",
    29: "Bahia",
}

def buscar_dados_ibge(url: str) -> list[dict[str, any]]:
    try:
        response = requests.get(url, timeout=(3, 10))
        response.raise_for_status()
        data = response.json()

        print("Produtos temporárias buscados com sucesso!")
        return data

    except requests.RequestException as error:
        print(f"Falha ao buscar produtos temporárias: {error}")
        return []

def buscar_produtos_temporarios_nordeste() -> list[dict[str, any]]:
    todos_registros = []
    
    for uf_codigo, uf_nome in ESTADOS_NORDESTE.items():
        print(f"Buscando {uf_nome} ({uf_codigo})...")

        url = f'https://servicodados.ibge.gov.br/api/v3/agregados/1612/periodos/2015|2016|2017|2018|2019|2020|2021|2022|2023|2024/variaveis/216|214?localidades=N6[N3[{uf_codigo}]]&classificacao=81[2692,2702,2708,2711]'

        resposta = buscar_dados_ibge(url)
        if resposta:
            todos_registros.extend(resposta)
        time.sleep(0.5)

    return todos_registros

def buscar_produtos_permanentes_nordeste() -> list[dict[str, any]]:

    todos_registros = []
    
    for uf_codigo, uf_nome in ESTADOS_NORDESTE.items():
        print(f"Buscando {uf_nome} ({uf_codigo})...")

        url = f'https://servicodados.ibge.gov.br/api/v3/agregados/1613/periodos/2015|2016|2017|2018|2019|2020|2021|2022|2023|2024/variaveis/216|214?localidades=N6[N3[{uf_codigo}]]&classificacao=82[2720,40473,2727]'

        resposta = buscar_dados_ibge(url)
        if resposta:
            todos_registros.extend(resposta)
        time.sleep(0.5)

    return todos_registros

def buscar_produtos_nordeste():
    temporarios = buscar_produtos_temporarios_nordeste()
    permanentes = buscar_produtos_permanentes_nordeste()

    for bloco in temporarios:
        bloco["tipo_lavoura"] = "temporaria"
    for bloco in permanentes:
        bloco["tipo_lavoura"] = "permanente"
    return temporarios + permanentes