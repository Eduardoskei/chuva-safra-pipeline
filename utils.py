import unicodedata

def normalizar_nome(nome: str) -> str:
    #Remove acentos, espaços extras e padroniza para minúsculas.
    nome = nome.strip().lower()
    return ''.join(
        c for c in unicodedata.normalize('NFD', nome)
        if unicodedata.category(c) != 'Mn'
    )