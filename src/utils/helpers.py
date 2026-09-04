#helpers.py
import os
from dotenv import load_dotenv
import sys
try:
    import psycopg2
except ImportError:
    print("Este script requer psycopg2. Instale com:")
    print("    pip install psycopg2-binary --break-system-packages")
    sys.exit(1)

load_dotenv()
# ================================
# CONFIGURAÇÃO
# ================================

DB_CONFIG = dict(
    host=os.environ.get("ECOCIENTE_DB_HOST"),
    port=os.environ.get("ECOCIENTE_DB_PORT"),
    dbname=os.environ.get("ECOCIENTE_DB_NAME"),
    user=os.environ.get("ECOCIENTE_DB_USER"),
    password=os.environ.get("ECOCIENTE_DB_PASSWORD"),
    sslmode=os.environ.get("ECOCIENTE_DB_SSLMODE"))
#  connection string completa
DSN = os.environ.get("ECOCIENTE_DSN")

# ==============================================================================
# HELPERS DE BANCO
#===============================================================================

def get_connection():
    if DSN:
        conn = psycopg2.connect(DSN)
    else:
        conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    return conn


def target_description():
    """Descreve o destino da conexão sem expor senha -- usado em prompts de confirmação."""
    if DSN:
        return "conexão via ECOCIENTE_DSN"
    return f"{DB_CONFIG.get('host')}:{DB_CONFIG.get('port')}/{DB_CONFIG.get('dbname')}"


def fetch_id(cur, sql, params):
    """Executa um INSERT ... RETURNING <pk> e devolve o id gerado."""
    cur.execute(sql, params)
    return cur.fetchone()[0]


def call_procedure(cur, sql, params):
    cur.execute(sql, params)

