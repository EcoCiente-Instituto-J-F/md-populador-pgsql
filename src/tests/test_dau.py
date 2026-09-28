"""Self-check da geração de DAU. Rode a partir de src/:  python -m tests.test_dau"""
import random
from datetime import timedelta

from utils.database import HOJE, amostra_ponderada, dias_ativos


def test_dias_ativos():
    inicio, fim = HOJE - timedelta(days=300), HOJE - timedelta(days=100)
    forcados = {inicio + timedelta(days=150), HOJE - timedelta(days=20)}

    dias = dias_ativos(inicio, fim, "regular", False, forcados, random.Random(1))
    assert forcados <= set(dias), "dias com evento real precisam estar ativos"
    assert inicio in dias, "dia do cadastro sempre conta como ativo"
    assert dias == sorted(set(dias)), "sem duplicata usuário x dia"
    assert all(d <= fim for d in dias if d not in forcados), "nada depois do abandono, salvo eventos reais"

    metade = inicio + (fim - inicio) / 2
    antes = sum(d < metade for d in dias)
    assert antes > len(dias) - antes, "quem abandonou tem atividade decrescente"

    assert dias == dias_ativos(inicio, fim, "regular", False, forcados, random.Random(1)), "reprodutível por seed"

    power = dias_ativos(inicio, HOJE, "power", False, set(), random.Random(2))
    casual = dias_ativos(inicio, HOJE, "casual", False, set(), random.Random(2))
    assert len(power) > 3 * len(casual), "perfil power abre o app bem mais que o casual"


def test_amostra_ponderada():
    escolhidos = amostra_ponderada(list(range(10)), [1] * 9 + [1000], 4)
    assert len(escolhidos) == len(set(escolhidos)) == 4
    assert 9 in escolhidos, "item de peso dominante quase sempre é sorteado"


if __name__ == "__main__":
    test_dias_ativos()
    test_amostra_ponderada()
    print("ok")
