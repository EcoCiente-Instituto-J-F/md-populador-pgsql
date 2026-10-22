FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY sql/ ./sql/

WORKDIR /app/src

# Configuração via variáveis de ambiente (ECOCIENTE_DSN etc.); o .env não vai para a imagem.
# Sem terminal interativo não há como confirmar o TRUNCATE: passe --force ou ECOCIENTE_ALLOW_RESET=1.
ENTRYPOINT ["python", "main.py"]
