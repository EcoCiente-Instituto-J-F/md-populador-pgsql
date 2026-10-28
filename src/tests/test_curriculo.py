"""Self-check do conteúdo da trilha. Rode a partir de src/:  python -m tests.test_curriculo"""
from utils.database import _carregar_curriculo


def test_quizzes_tem_explicacao():
    quizzes = _carregar_curriculo()["quizzes"]
    assert len(quizzes) == 20, "a trilha tem 20 quizzes"
    assert sum(len(q["perguntas"]) for q in quizzes) == 246, "246 perguntas no total"

    for quiz in quizzes:
        for numero, pergunta in enumerate(quiz["perguntas"], start=1):
            explicacao = pergunta.get("explicacao")
            assert isinstance(explicacao, str) and explicacao.strip(), \
                f"quiz '{quiz['titulo_quiz']}', pergunta {numero}: sem explicação"


if __name__ == "__main__":
    test_quizzes_tem_explicacao()
    print("ok")
