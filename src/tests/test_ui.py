"""Self-check da lógica da tela. Rode a partir de src/:  python -m tests.test_ui"""
import http.client
import threading

from ui import Handler, Servidor, etapa_da_linha, grupo_da_tabela, resumir_carga, tempos_por_etapa


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


def test_servidor_recusa_host_estranho_e_post_sem_json():
    servidor = Servidor(("127.0.0.1", 0), Handler)
    porta = servidor.server_address[1]
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    def pedir(metodo, caminho, headers, corpo=None):
        c = http.client.HTTPConnection("127.0.0.1", porta)
        c.request(metodo, caminho, corpo, headers)
        return c.getresponse().status

    try:
        assert pedir("GET", "/", {"Host": "evil.com"}) == 403, "DNS rebinding"
        assert pedir("GET", "/", {"Host": f"127.0.0.1:{porta}"}) == 200
        assert pedir("POST", "/api/popular", {"Host": f"127.0.0.1:{porta}", "Content-Type": "text/plain"}, "x") == 415
        json = {"Host": f"127.0.0.1:{porta}", "Content-Type": "application/json"}
        assert pedir("POST", "/api/popular", json, '{"escala": "gigante", "seed": 1}') == 400
        assert pedir("POST", "/api/popular", json, '{"escala": "leve", "seed": "42"}') == 400, "seed é inteiro, não texto"
    finally:
        servidor.shutdown()


if __name__ == "__main__":
    test_etapa_da_linha()
    test_tempos_por_etapa()
    test_grupo_da_tabela()
    test_resumir_carga()
    test_servidor_recusa_host_estranho_e_post_sem_json()
    print("ok")
