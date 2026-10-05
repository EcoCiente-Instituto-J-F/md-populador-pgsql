"""Self-check dos cálculos do painel da tela. Rode a partir de src/:  python -m tests.test_ui"""
from ui import (duracao, etapa_da_linha, grupo_da_tabela, inteiro, percentual, resumir_carga,
                segundos_curtos, tamanho, tempos_por_etapa)


def test_etapa_da_linha():
    assert etapa_da_linha("[3/10] Usuários comuns...\n") == (3, "Usuários comuns")
    assert etapa_da_linha("      votos 1-5000 de 25618") is None, "linha de detalhe não é etapa"
    assert etapa_da_linha("[ERRO] column does not exist") is None


def test_tempos_por_etapa():
    marcos = [(1, "Lookup", 100.0), (2, "Cursos", 101.5), (3, "Usuários", 104.0)]
    assert tempos_por_etapa(marcos, fim=110.0) == [("1. Lookup", 1.5), ("2. Cursos", 2.5), ("3. Usuários", 6.0)], \
        "cada etapa dura até a próxima começar; a última vai até o fim da carga"
    assert tempos_por_etapa([], fim=110.0) == []


def test_grupo_da_tabela():
    assert grupo_da_tabela("tb_lkp_dias_semanas") == "Domínio"
    assert grupo_da_tabela("tb_log_auditoria") == "Auditoria"
    assert grupo_da_tabela("tb_rel_votos_postagens") == "Relacionamento"
    assert grupo_da_tabela("tb_usuarios") == "Entidade"


def test_resumir_carga():
    medidas = [("tb_a", 300, 8192), ("tb_b", 0, 8192), ("tb_c", 100, 16384)]
    r = resumir_carga(medidas, segundos=8)
    assert (r["linhas"], r["populadas"], r["tabelas"], r["vazias"]) == (400, 2, 3, ["tb_b"])
    assert r["linhas_por_segundo"] == 50
    assert resumir_carga(medidas, segundos=None)["linhas_por_segundo"] is None, "sem carga nesta sessão não há ritmo"
    assert resumir_carga([], segundos=0)["linhas_por_segundo"] is None, "duração zero não divide"


def test_formatos():
    assert inteiro(1234567) == "1.234.567"
    assert tamanho(57_671_680) == "55 MB"
    assert tamanho(8192) == "8 kB"
    assert duracao(9.4) == "9 s"
    assert duracao(75) == "1 min 15 s"
    assert duracao(0.4) == "menos de 1 s"
    assert segundos_curtos(2.44) == "2,4 s"
    assert segundos_curtos(0.01) == "< 0,1 s"
    assert percentual(273, 1000) == "27,3%"
    assert percentual(5, 0) == "0%", "banco vazio não divide por zero"


if __name__ == "__main__":
    test_etapa_da_linha()
    test_tempos_por_etapa()
    test_grupo_da_tabela()
    test_resumir_carga()
    test_formatos()
    print("ok")
