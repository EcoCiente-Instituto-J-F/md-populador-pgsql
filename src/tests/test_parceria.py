"""Self-check da parceria cooperativa x condomínio pela cidade. Rode a partir de src/:  python -m tests.test_parceria"""
import random

from utils.database import sortear_parceiras

# (id, nome, usuario_id, qualidade, cidade)
COOPERATIVAS = [
    (1, "Verde Ponto", 10, 0.60, "Campinas"),
    (2, "Reciclo Já", 11, 0.70, "São Paulo"),
    (3, "Coleta Sul", 12, 0.80, "Campinas"),
    (4, "Papel Forte", 13, 0.90, "Recife"),
]


def test_parceiras_sao_da_mesma_cidade():
    for seed in range(100):
        escolhidas = sortear_parceiras(COOPERATIVAS, "Campinas", random.Random(seed))
        assert all(c[4] == "Campinas" for c in escolhidas), "nenhuma parceira de outra cidade"
        assert len({c[0] for c in escolhidas}) == len(escolhidas), "sem repetição"


def test_limite_e_cidade_sem_cooperativa():
    assert len(sortear_parceiras(COOPERATIVAS, "Campinas", random.Random(1))) == 2
    assert len(sortear_parceiras(COOPERATIVAS, "Recife", random.Random(1))) == 1
    assert sortear_parceiras(COOPERATIVAS, "Manaus", random.Random(1)) == []


if __name__ == "__main__":
    test_parceiras_sao_da_mesma_cidade()
    test_limite_e_cidade_sem_cooperativa()
    print("ok")
