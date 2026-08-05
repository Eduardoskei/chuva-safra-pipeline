import requests
    
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