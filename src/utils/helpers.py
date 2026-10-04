#helpers.py
import os
import re
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
    cfg = DB_CONFIG
    if DSN:
        try:
            cfg = psycopg2.extensions.parse_dsn(DSN)
        except psycopg2.Error:
            return "conexão via ECOCIENTE_DSN"
    return f"{cfg.get('host')}:{cfg.get('port')}/{cfg.get('dbname')}"


def colunas_esperadas(sql):
    """{tabela: {colunas}} lidas dos CREATE TABLE de sql/ecociente_schema.sql."""
    return {
        tabela: set(re.findall(r"^\s+([a-z_][a-z0-9_]*)\s+[A-Z]", corpo, re.M))
        for tabela, corpo in re.findall(r"CREATE TABLE (?:IF NOT EXISTS )?(\w+) \((.*?)\);$", sql, re.S | re.M)
    }


def colunas_faltando(esperado, existentes):
    """Lista 'tabela.coluna' do schema que não estão em `existentes` (pares tabela, coluna do banco)."""
    return sorted(f"{t}.{c}" for t, colunas in esperado.items() for c in colunas if (t, c) not in existentes)


def fetch_id(cur, sql, params):
    """Executa um INSERT ... RETURNING <pk> e devolve o id gerado."""
    cur.execute(sql, params)
    return cur.fetchone()[0]


def call_procedure(cur, sql, params):
    cur.execute(sql, params)

