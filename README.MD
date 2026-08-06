# 🌧️ Chuva & Safra — Análise de Dados

Serviço em **FastAPI + pandas** que cruza a produção agrícola municipal (IBGE/SIDRA) com o histórico de chuva (Open-Meteo) dos municípios do Ceará, para responder: **a chuva explica a safra?**

O serviço calcula produtividade, agrega chuva por safra, mede a correlação entre as duas variáveis, e expõe tudo via rota `/grafico`, com dados diferentes conforme o perfil do usuário (produtor, técnico ou gestor público).

---

## 🚀 Getting Started (VSCode)

### Pré-requisitos

- [Python 3.10+](https://www.python.org/)
- [VSCode](https://code.visualstudio.com/)
- Extensões recomendadas: `Python`

### 1. Clonar o repositório

```bash
git clone https://github.com/Eduardoskei/chuva-safra-pipeline.git
cd chuva-safra-pipeline
code .
```

### 2. Criar e ativar o ambiente virtual

```bash
# Criando venv em python
python -m venv venv

# Iniciando no Linux/Mac
source venv/bin/activate

# iniciando no Windows
venv\Scripts\activate
```

No VSCode: `Ctrl+Shift+P` → **Python: Select Interpreter** → selecione o `venv` criado.

### 3. Instalar as dependências

```bash
pip install -r requirements.txt
```

### 4. Configurar variáveis de ambiente

```bash
cp .env.example .env
```

### 5. Subir o serviço

```bash
uvicorn main:app --reload --port 8000
```

- API: `http://localhost:8000`
- Docs (Swagger): `http://localhost:8000/docs`
