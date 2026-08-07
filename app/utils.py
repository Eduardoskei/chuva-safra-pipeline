import unicodedata
import pandas as pd

# Mapeamento universal de estados para siglas (já em minúsculas e sem acentos)
MAPA_UF = {
    "acre": "ac", "alagoas": "al", "amapa": "ap", "amazonas": "am",
    "bahia": "ba", "ceara": "ce", "distrito federal": "df",
    "espirito santo": "es", "goias": "go", "maranhao": "ma",
    "mato grosso": "mt", "mato grosso do sul": "ms", "minas gerais": "mg",
    "para": "pa", "paraiba": "pb", "parana": "pr", "pernambuco": "pe",
    "piaui": "pi", "rio de janeiro": "rj", "rio grande do norte": "rn",
    "rio grande do sul": "rs", "rondonia": "ro", "roraima": "rr",
    "santa catarina": "sc", "sao paulo": "sp", "sergipe": "se",
    "tocantins": "to"
}

def normalizar_nome(nome) -> str:
    #Remove acentos, espaços extras, padroniza para minúsculas e trata nulos.
    if pd.isna(nome):
        return ""
    
    nome = str(nome).strip().lower()
    return ''.join(
        c for c in unicodedata.normalize('NFD', nome)
        if unicodedata.category(c) != 'Mn'
    )