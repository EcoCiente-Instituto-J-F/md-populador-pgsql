"""
ui.py

Interface local do Populador EcoCiente. Sobe um servidor em 127.0.0.1 (só a
biblioteca padrão), abre o navegador e serve ui_static/index.html mais uma API
JSON: confere o banco, roda o main.py mostrando o progresso e, no fim, mede o
banco para o painel de resultado (linhas por tabela, tempo por etapa, tamanho).

Uso (a partir de src/):
    python ui.py
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from psycopg2 import sql

from utils.helpers import colunas_esperadas, colunas_faltando, get_connection, target_description

AQUI = Path(__file__).resolve().parent
SCHEMA_SQL = AQUI.parent / "sql" / "ecociente_schema.sql"
HOST, PORT = "127.0.0.1", 8766
ARQUIVOS = {
    "/": (AQUI / "ui_static" / "index.html", "text/html; charset=utf-8"),
    "/logo.png": (AQUI / "assets" / "logo_branca.png", "image/png"),
}
ESCALAS = ("leve", "medio", "pesado")

# Sem isso, um banco fora do ar deixaria a verificação pendurada por minutos.
os.environ.setdefault("PGCONNECT_TIMEOUT", "10")


# ==============================================================================
# CÁLCULOS DO PAINEL (sem rede nem banco; cobertos por tests/test_ui.py)
# ==============================================================================

def etapa_da_linha(linha):
    """(número, nome) se a linha do main.py abre uma etapa, como '[3/10] Usuários comuns...'."""
    achou = re.match(r"\[(\d+)/10\]\s*(.*)", linha.strip())
    return (int(achou.group(1)), achou.group(2).rstrip(".")) if achou else None


def tempos_por_etapa(marcos, fim):
    """marcos = [(número, nome, instante de início)]. Cada etapa dura até a próxima começar."""
    proximos = [t for _, _, t in marcos[1:]] + [fim]
    return [(f"{n}. {nome}", round(prox - t, 1)) for (n, nome, t), prox in zip(marcos, proximos)]


def grupo_da_tabela(nome):
    for prefixo, grupo in (("tb_lkp_", "Domínio"), ("tb_log_", "Auditoria"), ("tb_rel_", "Relacionamento")):
        if nome.startswith(prefixo):
            return grupo
    return "Entidade"


def resumir_carga(medidas, segundos):
    """medidas = [(tabela, linhas, bytes)]; segundos = duração da carga, ou None se não houve carga."""
    linhas = sum(n for _, n, _ in medidas)
    vazias = [t for t, n, _ in medidas if n == 0]
    return dict(
        linhas=linhas, tabelas=len(medidas), populadas=len(medidas) - len(vazias), vazias=vazias,
        linhas_por_segundo=round(linhas / segundos) if segundos else None,
    )


# ==============================================================================
# BANCO
# ==============================================================================

def verificar_banco():
    """Conecta e devolve as colunas do schema que faltam no banco ([] = tudo certo)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema = current_schema()")
        return colunas_faltando(colunas_esperadas(SCHEMA_SQL.read_text(encoding="utf-8")), set(cur.fetchall()))
    finally:
        conn.close()


def medir_banco():
    """([(tabela, linhas, bytes em disco)] de todas as tb_* do banco, tamanho total do banco)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema() "
                    "AND table_type = 'BASE TABLE' AND table_name LIKE 'tb\\_%' ORDER BY 1")
        tabelas = [t for (t,) in cur.fetchall()]
        medidas = []
        if tabelas:   # uma consulta só: contra a Aiven, 46 idas e voltas custariam segundos
            cur.execute(sql.SQL(" UNION ALL ").join(
                sql.SQL("SELECT {}, count(*), pg_total_relation_size({}::regclass) FROM {}").format(
                    sql.Literal(t), sql.Literal(t), sql.Identifier(t))
                for t in tabelas))
            medidas = [(t, int(n), int(b)) for t, n, b in cur.fetchall()]
        cur.execute("SELECT pg_database_size(current_database())")
        return medidas, cur.fetchone()[0]
    finally:
        conn.close()


def texto_do_erro(erro):
    return str(erro).strip().splitlines()[0] if str(erro).strip() else type(erro).__name__


# ==============================================================================
# CARGA (o main.py roda como subprocesso; este módulo só lê a saída dele)
# ==============================================================================

_lock = threading.Lock()
_carga = {"proc": None}   # estado da última carga; vazio de verdade até a primeira


def _acompanhar(proc, estado):
    marcos, fim = [], None
    for linha in proc.stdout:
        instante = time.time()   # é quando o main.py imprimiu, não quando a tela leu
        etapa = etapa_da_linha(linha)
        if etapa:
            marcos.append((*etapa, instante))
            estado.update(etapa=etapa[0], nome=etapa[1])
        elif linha.startswith("Carga concluída"):   # depois disso o main.py só conta linhas para o resumo
            fim = instante
        estado["log"].append(linha.rstrip())
    codigo = proc.wait()
    if codigo == 0 and marcos and fim is not None:
        estado.update(segundos=fim - marcos[0][2], etapas=tempos_por_etapa(marcos, fim),
                      quando=time.strftime("%H:%M"))
    estado.update(codigo=codigo, rodando=False)


def popular(escala, seed):
    with _lock:
        if _carga["proc"] is not None and _carga["proc"].poll() is None:
            return 409, {"erro": "Já existe uma carga em andamento."}
        proc = subprocess.Popen(
            # --force: a confirmação já foi feita no diálogo da página.
            [sys.executable, "-u", str(AQUI / "main.py"), "--escala", escala, "--seed", str(seed), "--force"],
            cwd=AQUI, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        estado = dict(rodando=True, escala=escala, seed=seed, etapa=0, nome="", log=[], codigo=None,
                      segundos=None, etapas=[], quando=None)
        _carga.update(proc=proc, estado=estado)
        threading.Thread(target=_acompanhar, args=(proc, estado), daemon=True).start()
    return 202, {}


def status():
    estado = _carga.get("estado")
    return {"alvo": target_description(),
            "carga": None if estado is None else {**estado, "log": estado["log"][-400:]}}


def resultado():
    medidas, bytes_banco = medir_banco()
    estado = _carga.get("estado")
    carga = estado if estado and estado["segundos"] is not None else None
    return {
        "carga": carga and {k: carga[k] for k in ("escala", "seed", "quando", "segundos", "etapas")},
        "resumo": resumir_carga(medidas, carga["segundos"] if carga else None),
        "bytes_banco": bytes_banco,
        "tabelas": [dict(tabela=t, grupo=grupo_da_tabela(t), linhas=n, bytes=b) for t, n, b in medidas],
    }


# ==============================================================================
# SERVIDOR
# ==============================================================================

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, code, body):
        data = json.dumps(body, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _host_ok(self):
        # Barra DNS rebinding: só atende quem pediu por 127.0.0.1/localhost.
        porta = self.server.server_address[1]
        if self.headers.get("Host") in (f"127.0.0.1:{porta}", f"localhost:{porta}"):
            return True
        self._json(403, {"erro": "Host não permitido."})
        return False

    def do_GET(self):
        if not self._host_ok():
            return
        try:
            if self.path == "/api/status":
                return self._json(200, status())
            if self.path == "/api/banco":
                return self._json(200, {"alvo": target_description(), "faltando": verificar_banco()})
            if self.path == "/api/resultado":
                return self._json(200, resultado())
        except Exception as erro:   # banco fora do ar, sem .env etc.: a página mostra a mensagem
            return self._json(200, {"erro": texto_do_erro(erro), "alvo": target_description()})
        if self.path in ARQUIVOS:
            caminho, tipo = ARQUIVOS[self.path]
            data = caminho.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return self.wfile.write(data)
        self._json(404, {"erro": "Não encontrado."})

    def do_POST(self):
        if not self._host_ok():
            return
        # Exigir JSON impede que outro site dispare a carga (que apaga dados) com um <form>.
        if self.headers.get("Content-Type") != "application/json":
            return self._json(415, {"erro": "Envie application/json."})
        try:
            corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return self._json(400, {"erro": "JSON inválido."})

        if self.path == "/api/popular":
            escala, seed = corpo.get("escala"), corpo.get("seed")
            if escala not in ESCALAS:
                return self._json(400, {"erro": "Escolha leve, médio ou pesado."})
            if isinstance(seed, bool) or not isinstance(seed, int):
                return self._json(400, {"erro": "A seed precisa ser um número inteiro, por exemplo 42."})
            return self._json(*popular(escala, seed))
        if self.path == "/api/encerrar":
            proc = _carga["proc"]
            if proc is not None and proc.poll() is None:
                return self._json(409, {"erro": "Aguarde a carga terminar."})
            self._json(200, {})
            return threading.Thread(target=self.server.shutdown).start()
        self._json(404, {"erro": "Não encontrado."})


class Servidor(ThreadingHTTPServer):
    allow_reuse_address = False   # no Windows, True deixaria abrir duas instâncias
    daemon_threads = True


def main():
    url = f"http://{HOST}:{PORT}"
    try:
        servidor = Servidor((HOST, PORT), Handler)
    except OSError:   # já está aberto: só mostra a janela
        webbrowser.open(url)
        return
    if "--sem-navegador" not in sys.argv:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    print(f"Populador EcoCiente aberto em {url}  (Ctrl+C encerra)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        proc = _carga["proc"]
        if proc is not None and proc.poll() is None:
            proc.terminate()   # sem isso o main.py seguiria apagando e populando sozinho


if __name__ == "__main__":
    main()
