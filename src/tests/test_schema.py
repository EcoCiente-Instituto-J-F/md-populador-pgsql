"""Self-check da checagem de schema usada pela tela. Rode a partir de src/:  python -m tests.test_schema"""
from pathlib import Path

from utils import helpers
from utils.helpers import colunas_esperadas, colunas_faltando

SCHEMA = (Path(__file__).resolve().parents[2] / "sql" / "ecociente_schema.sql").read_text(encoding="utf-8")


def test_colunas_esperadas():
    esperado = colunas_esperadas(SCHEMA)
    assert len(esperado) == 46, "o schema tem 46 tabelas"
    assert sum(len(c) for c in esperado.values()) == 276, "276 colunas no total (conferido no PostgreSQL 16)"
    assert esperado["tb_autenticacoes_api"] == {
        "id_autenticao_api", "usuario_id", "token", "tipo_token", "criado_em", "expira_em"}
    assert "tb_metricas_dau" in esperado, "tabelas com IF NOT EXISTS também contam"


def test_colunas_faltando():
    esperado = {"tb_a": {"id_a", "nome"}, "tb_b": {"id_b"}}
    assert colunas_faltando(esperado, {("tb_a", "id_a"), ("tb_a", "nome"), ("tb_b", "id_b")}) == []
    assert colunas_faltando(esperado, {("tb_a", "id_a"), ("tb_x", "sobra")}) == ["tb_a.nome", "tb_b.id_b"], \
        "lista o que falta em ordem; coluna a mais no banco não é problema"


def test_target_description_nao_expoe_senha():
    original = helpers.DSN
    helpers.DSN = "postgres://avnadmin:segredo@pg-eco.aivencloud.com:12345/defaultdb?sslmode=require"
    try:
        assert helpers.target_description() == "pg-eco.aivencloud.com:12345/defaultdb"
    finally:
        helpers.DSN = original


if __name__ == "__main__":
    test_colunas_esperadas()
    test_colunas_faltando()
    test_target_description_nao_expoe_senha()
    print("ok")
