"""Self-check das oscilações de pontuação. Rode a partir de src/:  python -m tests.test_ledger"""
import random
from datetime import datetime, timedelta, timezone

from utils.database import gerar_oscilacoes

INICIO = datetime(2026, 1, 1, tzinfo=timezone.utc)
FIM = INICIO + timedelta(days=5)


def test_oscilacoes_alternam_e_terminam_no_estado_final():
    for seed in range(300):
        for ativa in (True, False):
            for pendente in (True, False):
                eventos = gerar_oscilacoes(INICIO, FIM, ativa, pendente, random.Random(seed))
                tipos = [t for t, _, _ in eventos]

                assert all(t == ("ESTORNO" if i % 2 == 0 else "RESTAURACAO") for i, t in enumerate(tipos)), \
                    "ESTORNO e RESTAURACAO alternam, começando por ESTORNO"

                estornos = tipos.count("ESTORNO")
                restauracoes = tipos.count("RESTAURACAO")
                if ativa:
                    assert estornos == restauracoes, "ativa no fim: cada saída tem uma volta"
                else:
                    assert estornos == restauracoes + 1 and estornos >= 1, "inativa no fim: sobra um ESTORNO"

                assert [n for t, _, n in eventos if t == "ESTORNO"] == list(range(1, estornos + 1))
                assert [n for t, _, n in eventos if t == "RESTAURACAO"] == list(range(1, restauracoes + 1))


def test_datas_dentro_da_janela_e_em_ordem():
    for seed in range(300):
        eventos = gerar_oscilacoes(INICIO, FIM, False, True, random.Random(seed))
        instantes = [q for _, q, _ in eventos]
        assert instantes == sorted(instantes), "eventos em ordem cronológica"
        assert all(INICIO <= q <= FIM for q in instantes), "nenhum evento fora da vida da postagem"


def test_oscilacao_multipla_acontece():
    maximo = max(
        sum(t == "ESTORNO" for t, _, _ in gerar_oscilacoes(INICIO, FIM, True, False, random.Random(seed)))
        for seed in range(300)
    )
    assert maximo >= 2, "com 15% de chance de oscilações extras, alguma postagem oscila mais de uma vez"


def test_postagem_ativa_sem_pendencia_quase_sempre_nao_oscila():
    sem_evento = sum(
        not gerar_oscilacoes(INICIO, FIM, True, False, random.Random(seed)) for seed in range(300)
    )
    assert sem_evento > 200, "a maioria das postagens ativas não gera ESTORNO/RESTAURACAO"


if __name__ == "__main__":
    test_oscilacoes_alternam_e_terminam_no_estado_final()
    test_datas_dentro_da_janela_e_em_ordem()
    test_oscilacao_multipla_acontece()
    test_postagem_ativa_sem_pendencia_quase_sempre_nao_oscila()
    print("ok")
