import requests
import unicodedata
import pandas as pd

    
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


def cruzar_producao_clima_por_nome(df_producao: pd.DataFrame, df_clima: pd.DataFrame) -> pd.DataFrame:
    """
    Cruza produção e clima usando (nome_municipio normalizado + UF + ano)
    Espera que df_producao e df_clima tenham as colunas:
    'nome_municipio', 'uf', 'ano' (mais as colunas de valor de cada base).
    """
    df_producao = df_producao.copy()
    df_clima = df_clima.copy()

    df_producao["chave_nome"] = df_producao["nome_municipio"].map(normalizar_nome)
    df_clima["chave_nome"] = df_clima["nome_municipio"].map(normalizar_nome)
    df_producao["chave_uf"] = df_producao["uf"].map(normalizar_nome)
    df_clima["chave_uf"] = df_clima["uf"].map(normalizar_nome)

    chave = ["chave_nome", "chave_uf", "ano"]

    if df_producao.duplicated(subset=chave).any():
        raise ValueError(
            "Erro: chaves (nome normalizado + UF + ano) duplicadas na base de PRODUÇÃO! "
            "Provavelmente dois municípios diferentes normalizaram para o mesmo nome."
        )
    if df_clima.duplicated(subset=chave).any():
        raise ValueError("Erro: chaves duplicadas na base de CLIMA!")

    linhas_antes = len(df_producao)

    df_final = pd.merge(
        df_producao,
        df_clima,
        on=chave,
        how="left",
        validate="one_to_one",
        indicator=True,
        suffixes=("", "_clima"),
    )

    assert len(df_final) == linhas_antes, "O merge alterou a quantidade de linhas!"

    sem_clima = df_final[df_final["_merge"] == "left_only"]
    if not sem_clima.empty:
        print(f"⚠ Aviso: {len(sem_clima)} registro(s) sem dados climáticos (chave por nome).")
        print(sem_clima[["nome_municipio", "uf", "ano"]].head())

    df_final = df_final.drop(columns=["_merge", "chave_nome", "chave_uf"])
    return df_final