#!/usr/bin/env python3
"""Extrai o catálogo de dados (HTML -> JSON) e lê o schema SQL.

Uso, a partir da raiz do repositório:
    python documentos/extrair_catalogo.py

Também importável (Tarefa 4): ler_schema(), divergencias(), carregar_catalogo().
Não há eval, Node nem regex para trocar aspas: o literal JS é lido por um
mini-analisador próprio e o SQL por um tokenizador próprio.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
HTML_ORIGEM = AQUI / "origem" / "catalogo_atual.html"
JSON_SAIDA = AQUI / "dados" / "catalogo.json"
SQL_SCHEMA = RAIZ / "sql" / "ecociente_schema.sql"
SQL_DATAMART = RAIZ / "sql" / "ecociente_datamart.sql"

BADGES = {
    "R": "Leitura",
    "W": "Escrita",
    "RW": "Leitura e escrita",
    "0": "Sem acesso",
    "*": "acesso restrito",
}


# ---------------------------------------------------------------------------
# A. Mini-analisador do literal de objeto JavaScript
# ---------------------------------------------------------------------------
class ErroJS(ValueError):
    pass


_ESCAPES_JS = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "0": "\0",
               "'": "'", '"': '"', "\\": "\\", "/": "/", "`": "`"}


class _AnalisadorJS:
    def __init__(self, texto: str, pos: int = 0):
        self.t = texto
        self.i = pos

    def _pular(self):
        t = self.t
        while self.i < len(t):
            c = t[self.i]
            if c.isspace():
                self.i += 1
            elif t.startswith("//", self.i):
                fim = t.find("\n", self.i)
                self.i = len(t) if fim < 0 else fim + 1
            elif t.startswith("/*", self.i):
                fim = t.find("*/", self.i + 2)
                if fim < 0:
                    raise ErroJS("comentário não fechado")
                self.i = fim + 2
            else:
                break

    def _erro(self, msg):
        ctx = self.t[max(0, self.i - 30): self.i + 30].replace("\n", " ")
        raise ErroJS(f"{msg} na posição {self.i}: ...{ctx}...")

    def valor(self):
        self._pular()
        if self.i >= len(self.t):
            self._erro("fim inesperado")
        c = self.t[self.i]
        if c == "[":
            return self._array()
        if c == "{":
            return self._objeto()
        if c in "'\"":
            return self._string()
        if c == "-" or c.isdigit() or c == ".":
            return self._numero()
        ident = self._identificador()
        if ident == "true":
            return True
        if ident == "false":
            return False
        if ident == "null":
            return None
        self._erro(f"valor não suportado '{ident}'")

    def _identificador(self) -> str:
        ini = self.i
        while self.i < len(self.t) and (self.t[self.i].isalnum() or self.t[self.i] in "_$"):
            self.i += 1
        if ini == self.i:
            self._erro("identificador esperado")
        return self.t[ini:self.i]

    def _numero(self):
        ini = self.i
        while self.i < len(self.t) and (self.t[self.i].isdigit() or self.t[self.i] in "+-.eE"):
            self.i += 1
        bruto = self.t[ini:self.i]
        try:
            return int(bruto)
        except ValueError:
            return float(bruto)

    def _string(self) -> str:
        aspa = self.t[self.i]
        self.i += 1
        partes = []
        while True:
            if self.i >= len(self.t):
                self._erro("string não fechada")
            c = self.t[self.i]
            if c == aspa:
                self.i += 1
                return "".join(partes)
            if c == "\\":
                prox = self.t[self.i + 1]
                if prox == "u":
                    partes.append(chr(int(self.t[self.i + 2:self.i + 6], 16)))
                    self.i += 6
                    continue
                if prox == "\n":  # continuação de linha
                    self.i += 2
                    continue
                partes.append(_ESCAPES_JS.get(prox, prox))
                self.i += 2
                continue
            partes.append(c)
            self.i += 1

    def _array(self) -> list:
        self.i += 1
        itens = []
        while True:
            self._pular()
            if self.t[self.i] == "]":
                self.i += 1
                return itens
            itens.append(self.valor())
            self._pular()
            if self.t[self.i] == ",":
                self.i += 1
            elif self.t[self.i] != "]":
                self._erro("',' ou ']' esperado")

    def _objeto(self) -> dict:
        self.i += 1
        obj = {}
        while True:
            self._pular()
            if self.t[self.i] == "}":
                self.i += 1
                return obj
            chave = self._string() if self.t[self.i] in "'\"" else self._identificador()
            self._pular()
            if self.t[self.i] != ":":
                self._erro("':' esperado")
            self.i += 1
            obj[chave] = self.valor()
            self._pular()
            if self.t[self.i] == ",":
                self.i += 1
            elif self.t[self.i] != "}":
                self._erro("',' ou '}' esperado")


def analisar_literal_js(texto: str, a_partir_de: int = 0):
    """Lê o primeiro valor JS (array/objeto) a partir da posição indicada."""
    return _AnalisadorJS(texto, a_partir_de).valor()


def _extrair_groups(soup: BeautifulSoup) -> list:
    for script in soup.find_all("script"):
        codigo = script.string or script.get_text()
        m = re.search(r"const\s+GROUPS\s*=\s*", codigo)
        if m:
            return analisar_literal_js(codigo, m.end())
    raise ErroJS("const GROUPS não encontrado")


def _norm(texto: str) -> str:
    return " ".join(texto.split())


def extrair_catalogo(html_path: Path = HTML_ORIGEM) -> dict:
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    groups = _extrair_groups(soup)

    perfis = [{"nome": _norm(c.find("h4").get_text()), "descricao": _norm(c.find("p").get_text())}
              for c in soup.select(".role-card")]

    camadas = []
    for g in groups:
        tabelas = []
        for t in g["tabelas"]:
            tabelas.append({
                "nome": t["nome"].strip(),
                "tipo": t["tipo"].strip(),
                "descricao_curta": t["descricaoCurta"].strip(),
                "descricao": t["descricaoCompleta"].strip(),
                "permissoes": [{"perfil": p["perfil"].strip(), "badge": p["badge"].strip(),
                                "detalhe": p["detalhe"].strip() if p.get("detalhe") else None}
                               for p in t["permissoes"]],
                "regras": [r.strip() for r in t["regras"]],
                "observacoes": [o.strip() for o in t["observacoes"]],
            })
        camadas.append({
            "id": g["id"].strip(),
            "numero": g["numero"],
            "nome": g["nome"].strip(),
            "descricao": g["descricao"].strip(),
            "qtd_tabelas_texto": g["qtdTabelasTexto"].strip(),
            "tabelas": tabelas,
        })

    return {
        "fonte": "documentos/origem/catalogo_atual.html",
        "titulo": soup.title.get_text().strip(),
        "apresentacao": _norm(soup.select_one(".hero-text p").get_text()),
        "como_ler": _norm(soup.select_one(".intro-block p").get_text()),
        "perfis": perfis,
        "badges": dict(BADGES),
        "camadas": camadas,
    }


def carregar_catalogo(json_path: Path = JSON_SAIDA) -> dict:
    return json.loads(json_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# B. Leitor do schema SQL
# ---------------------------------------------------------------------------
_TAG_DOLAR = re.compile(r"\$[A-Za-z_]*\$")


def _limpar_sql(sql: str) -> str:
    """Remove comentários e corpos dollar-quoted (viram '' ); mantém strings."""
    out = []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        if c == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            out.append(sql[i:j + 1])
            i = j + 1
        elif c == '"':
            j = sql.find('"', i + 1)
            j = n - 1 if j < 0 else j
            out.append(sql[i:j + 1])
            i = j + 1
        elif sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j < 0 else j
        elif sql.startswith("/*", i):
            nivel, j = 1, i + 2
            while j < n and nivel:
                if sql.startswith("/*", j):
                    nivel += 1
                    j += 2
                elif sql.startswith("*/", j):
                    nivel -= 1
                    j += 2
                else:
                    j += 1
            out.append(" ")
            i = j
        elif c == "$" and (i == 0 or not (sql[i - 1].isalnum() or sql[i - 1] == "_")) \
                and (m := _TAG_DOLAR.match(sql, i)):
            fim = sql.find(m.group(0), m.end())
            fim = n if fim < 0 else fim + len(m.group(0))
            out.append("''")
            i = fim
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _dividir_comandos(sql: str) -> list[str]:
    """Divide em comandos por ';' fora de strings/identificadores entre aspas."""
    cmds, atual, i, n = [], [], 0, len(sql)
    while i < n:
        c = sql[i]
        if c in "'\"":
            j = i + 1
            while j < n:
                if sql[j] == c:
                    if c == "'" and j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            atual.append(sql[i:j + 1])
            i = j + 1
        elif c == ";":
            cmds.append("".join(atual).strip())
            atual = []
            i += 1
        else:
            atual.append(c)
            i += 1
    if "".join(atual).strip():
        cmds.append("".join(atual).strip())
    return [c for c in cmds if c]


class _Tok:
    __slots__ = ("tipo", "val", "ini", "fim")

    def __init__(self, tipo, val, ini, fim):
        self.tipo, self.val, self.ini, self.fim = tipo, val, ini, fim

    def kw(self) -> str:
        return self.val.upper() if self.tipo == "w" else ""

    def __repr__(self):
        return f"{self.tipo}:{self.val!r}"


def _tokenizar(txt: str) -> list[_Tok]:
    """Tokens: w=palavra/identificador, s=string, p=grupo entre parênteses
    (val = conteúdo interno), y=símbolo. Aspas duplas viram palavra."""
    toks, i, n = [], 0, len(txt)
    while i < n:
        c = txt[i]
        if c.isspace():
            i += 1
        elif c == "'":
            j = i + 1
            while j < n:
                if txt[j] == "'":
                    if j + 1 < n and txt[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            toks.append(_Tok("s", txt[i + 1:j].replace("''", "'"), i, j + 1))
            i = j + 1
        elif c == '"':
            j = txt.find('"', i + 1)
            toks.append(_Tok("w", txt[i + 1:j], i, j + 1))
            i = j + 1
        elif c == "(":
            nivel, j = 0, i
            while j < n:
                d = txt[j]
                if d == "'":
                    j += 1
                    while j < n:
                        if txt[j] == "'":
                            if j + 1 < n and txt[j + 1] == "'":
                                j += 2
                                continue
                            break
                        j += 1
                elif d == "(":
                    nivel += 1
                elif d == ")":
                    nivel -= 1
                    if nivel == 0:
                        break
                j += 1
            toks.append(_Tok("p", txt[i + 1:j], i, j + 1))
            i = j + 1
        elif c.isalnum() or c in "_$":
            j = i
            while j < n and (txt[j].isalnum() or txt[j] in "_$"):
                j += 1
            toks.append(_Tok("w", txt[i:j], i, j))
            i = j
        else:
            toks.append(_Tok("y", c, i, i + 1))
            i += 1
    return toks


def _dividir_virgulas(toks: list[_Tok]) -> list[list[_Tok]]:
    grupos, atual = [], []
    for t in toks:
        if t.tipo == "y" and t.val == ",":
            grupos.append(atual)
            atual = []
        else:
            atual.append(t)
    if atual:
        grupos.append(atual)
    return grupos


def _nomes(conteudo: str) -> list[str]:
    """Lista de identificadores 'a, b, "c"' -> ['a','b','c']."""
    return [t.val for t in _tokenizar(conteudo) if t.tipo == "w"]


def _nome_tabela(toks: list[_Tok], pos: int) -> tuple[str, int]:
    """Lê [schema.]nome a partir de pos; devolve (nome, próxima posição)."""
    nome = toks[pos].val
    pos += 1
    while pos + 1 < len(toks) and toks[pos].tipo == "y" and toks[pos].val == ".":
        nome = toks[pos + 1].val
        pos += 2
    return nome, pos


_PALAVRAS_RESTRICAO = {"NOT", "NULL", "DEFAULT", "PRIMARY", "UNIQUE", "REFERENCES", "CHECK",
                       "GENERATED", "CONSTRAINT", "COLLATE"}
_INICIO_RESTRICAO_TABELA = {"CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "EXCLUDE", "LIKE"}


def _compactar_tipo(txt: str) -> str:
    txt = " ".join(txt.split()).upper()
    txt = re.sub(r"\s*\(\s*", "(", txt)
    txt = re.sub(r"\s*,\s*", ",", txt)
    txt = re.sub(r"\s*\)", ")", txt)
    return txt


class _Tabela:
    def __init__(self, nome: str, arquivo: str):
        self.nome = nome
        self.arquivo = arquivo
        self.comentario = None
        self.colunas: list[dict] = []
        self.pk: list[str] = []
        self.uks: list[list[str]] = []
        self.fks: list[dict] = []
        self.herdadas: list[tuple] = []  # (tabela mae, coluna) vindas de INHERITS

    def coluna(self, nome):
        for c in self.colunas:
            if c["nome"] == nome:
                return c
        return None

    def add_uk(self, cols):
        if cols and cols not in self.uks:
            self.uks.append(cols)

    def remover_coluna(self, nome):
        self.colunas = [c for c in self.colunas if c["nome"] != nome]
        self.pk = [] if nome in self.pk else self.pk
        self.uks = [u for u in self.uks if nome not in u]
        self.fks = [f for f in self.fks if nome not in f["colunas"]]

    def adicionar_coluna(self, txt: str, toks: list[_Tok]):
        """toks = definição de coluna (nome, tipo, restrições inline)."""
        nome = toks[0].val
        k = 1
        while k < len(toks) and toks[k].kw() not in _PALAVRAS_RESTRICAO:
            k += 1
        tipo = _compactar_tipo(txt[toks[1].ini:toks[k - 1].fim]) if k > 1 else ""
        col = {"nome": nome, "tipo": tipo, "nulo": True, "pk": False, "uk": False,
               "fk": None, "default": None, "comentario": None}
        existente = self.coluna(nome)
        if existente is None:
            self.colunas.append(col)
        else:
            return  # ADD COLUMN IF NOT EXISTS de coluna já presente
        while k < len(toks):
            kw = toks[k].kw()
            if kw == "CONSTRAINT":
                k += 2
                continue
            if kw == "NOT" and k + 1 < len(toks) and toks[k + 1].kw() == "NULL":
                col["nulo"] = False
                k += 2
            elif kw == "NULL":
                k += 1
            elif kw == "PRIMARY":
                self.pk = [nome]
                k += 2
            elif kw == "UNIQUE":
                self.add_uk([nome])
                k += 1
            elif kw == "REFERENCES":
                tab, k = _nome_tabela(toks, k + 1)
                dest = None
                if k < len(toks) and toks[k].tipo == "p":
                    dest = _nomes(toks[k].val)
                    k += 1
                self.fks.append({"colunas": [nome], "tabela": tab, "colunas_destino": dest, "nome": None})
                while k < len(toks) and toks[k].kw() in ("ON", "MATCH", "DEFERRABLE", "INITIALLY", "NOT"):
                    if toks[k].kw() == "NOT" and toks[k + 1].kw() != "DEFERRABLE":
                        break
                    k += 1
                    if k < len(toks) and toks[k].kw() in ("DELETE", "UPDATE"):
                        k += 1
                        if toks[k].kw() in ("SET", "NO"):
                            k += 1
                        k += 1
                    elif k < len(toks) and toks[k].kw() in ("FULL", "SIMPLE", "PARTIAL", "DEFERRABLE",
                                                           "IMMEDIATE", "DEFERRED"):
                        k += 1
            elif kw == "CHECK":
                k += 2
            elif kw == "DEFAULT":
                ini = k + 1
                k = ini
                while k < len(toks) and toks[k].kw() not in _PALAVRAS_RESTRICAO:
                    k += 1
                col["default"] = txt[toks[ini].ini:toks[k - 1].fim].strip()
            elif kw == "GENERATED":
                k += 1
                while k < len(toks) and toks[k].kw() not in ("AS",):
                    k += 1
                k += 1  # após AS
                if k < len(toks) and toks[k].tipo == "p":  # coluna gerada: AS (expr) STORED
                    col["default"] = txt[toks[k].ini:toks[k].fim].strip()
                    k += 1
                    if k < len(toks) and toks[k].kw() == "STORED":
                        k += 1
                else:  # AS IDENTITY [(opções)]
                    k += 1
                    if k < len(toks) and toks[k].tipo == "p":
                        k += 1
            elif kw == "COLLATE":
                k += 2
            else:
                k += 1

    def restricao_tabela(self, toks: list[_Tok]):
        """toks = restrição de tabela (sem a vírgula), com ou sem CONSTRAINT nome."""
        nome = None
        k = 0
        if toks[0].kw() == "CONSTRAINT":
            nome = toks[1].val
            k = 2
        kw = toks[k].kw() if k < len(toks) else ""
        if kw == "PRIMARY":
            self.pk = _nomes(toks[k + 2].val)
        elif kw == "UNIQUE":
            p = next(t for t in toks[k:] if t.tipo == "p")
            self.add_uk(_nomes(p.val))
        elif kw == "FOREIGN":
            cols = _nomes(toks[k + 2].val)
            k += 3
            if toks[k].kw() == "REFERENCES":
                tab, k = _nome_tabela(toks, k + 1)
                dest = _nomes(toks[k].val) if k < len(toks) and toks[k].tipo == "p" else None
                self.fks.append({"colunas": cols, "tabela": tab, "colunas_destino": dest, "nome": nome})

    def finalizar(self, tabelas: dict) -> dict:
        for fk in self.fks:
            if fk["colunas_destino"] is None:  # REFERENCES t sem colunas -> PK do destino
                alvo = tabelas.get(fk["tabela"])
                fk["colunas_destino"] = list(alvo.pk) if alvo else []
        uk_cols = {c for u in self.uks for c in u}
        for c in self.colunas:
            c["pk"] = c["nome"] in self.pk
            if c["pk"]:
                c["nulo"] = False
            c["uk"] = c["nome"] in uk_cols
            c["fk"] = None
            for fk in self.fks:
                if c["nome"] in fk["colunas"]:
                    idx = fk["colunas"].index(c["nome"])
                    dest = fk["colunas_destino"]
                    c["fk"] = {"tabela": fk["tabela"], "coluna": dest[idx] if idx < len(dest) else None}
                    break
        return {
            "arquivo": self.arquivo,
            "comentario": self.comentario,
            "colunas": self.colunas,
            "pk": list(self.pk),
            "uks": [list(u) for u in self.uks],
            "fks": [dict(f) for f in self.fks],
        }


def _relativo(caminho: Path) -> str:
    try:
        return caminho.resolve().relative_to(RAIZ).as_posix()
    except ValueError:
        return caminho.as_posix()


def _criar_tabela(cmd: str, toks: list[_Tok], arquivo: str, tabelas: dict):
    k = 1
    while toks[k].kw() in ("TEMP", "TEMPORARY", "UNLOGGED", "GLOBAL", "LOCAL"):
        k += 1
    if toks[k].kw() != "TABLE":
        return
    k += 1
    if toks[k].kw() == "IF":
        k += 3
    nome, k = _nome_tabela(toks, k)
    if k >= len(toks) or toks[k].tipo != "p":
        return
    corpo = toks[k].val
    base = toks[k].ini + 1
    tab = _Tabela(nome, arquivo)
    # INHERITS (mae, ...): a filha recebe as colunas da mae (nome, tipo, nulo, default), mas nao PK, FK nem UNIQUE
    pais = []
    for m in range(k + 1, len(toks) - 1):
        if toks[m].kw() == "INHERITS" and toks[m + 1].tipo == "p":
            pais = _nomes(toks[m + 1].val)
    for pai in pais:
        if pai in tabelas:
            for c in tabelas[pai].colunas:
                tab.colunas.append({**c, "pk": False, "uk": False, "fk": None, "comentario": None})
                tab.herdadas.append((pai, c["nome"]))
    for item in _dividir_virgulas(_tokenizar(corpo)):
        if not item:
            continue
        # reposiciona os offsets em relação ao texto do comando
        item = [_Tok(t.tipo, t.val, t.ini + base, t.fim + base) for t in item]
        if item[0].kw() in _INICIO_RESTRICAO_TABELA and not (item[0].kw() == "LIKE"):
            tab.restricao_tabela(item)
        elif item[0].kw() != "LIKE":
            tab.adicionar_coluna(cmd, item)
    tabelas[nome] = tab


def _alterar_tabela(cmd: str, toks: list[_Tok], tabelas: dict):
    k = 2
    if toks[k].kw() == "IF":
        k += 2
    if toks[k].kw() == "ONLY":
        k += 1
    nome, k = _nome_tabela(toks, k)
    tab = tabelas.get(nome)
    if tab is None:
        return
    for acao in _dividir_virgulas(toks[k:]):
        if not acao:
            continue
        kw = acao[0].kw()
        if kw == "ADD":
            resto = acao[1:]
            if resto[0].kw() == "COLUMN":
                resto = resto[1:]
                if resto[0].kw() == "IF":
                    resto = resto[3:]
                tab.adicionar_coluna(cmd, resto)
            elif resto[0].kw() in _INICIO_RESTRICAO_TABELA:
                tab.restricao_tabela(resto)
            else:
                tab.adicionar_coluna(cmd, resto)
        elif kw == "DROP" and len(acao) > 1 and acao[1].kw() in ("COLUMN",) or \
                (kw == "DROP" and len(acao) > 1 and acao[1].tipo == "w"
                 and acao[1].kw() not in ("CONSTRAINT", "DEFAULT", "NOT")):
            resto = acao[2:] if acao[1].kw() == "COLUMN" else acao[1:]
            if resto and resto[0].kw() == "IF":
                resto = resto[2:]
            tab.remover_coluna(resto[0].val)
        elif kw == "ALTER":
            resto = acao[1:]
            if resto[0].kw() == "COLUMN":
                resto = resto[1:]
            col = tab.coluna(resto[0].val)
            kws = [t.kw() for t in resto[1:]]
            if col is not None and kws[:3] == ["SET", "NOT", "NULL"]:
                col["nulo"] = False
            elif col is not None and kws[:3] == ["DROP", "NOT", "NULL"]:
                col["nulo"] = True


_SIMPLES = re.compile(r'^\s*"?(\w+)"?\s*(?:ASC|DESC)?\s*$', re.I)


def _indice_unico(toks: list[_Tok], tabelas: dict):
    k = 2
    if toks[k].kw() == "CONCURRENTLY":
        k += 1
    if toks[k].kw() == "IF":
        k += 3
    k += 1  # nome do índice
    if toks[k].kw() != "ON":
        return
    k += 1
    if toks[k].kw() == "ONLY":
        k += 1
    nome, k = _nome_tabela(toks, k)
    if toks[k].kw() == "USING":
        k += 2
    if k >= len(toks) or toks[k].tipo != "p" or nome not in tabelas:
        return
    cols = []
    for item in _dividir_virgulas(_tokenizar(toks[k].val)):
        if len(item) == 1 and item[0].tipo == "w":
            cols.append(item[0].val)
        elif len(item) == 2 and item[0].tipo == "w" and item[1].kw() in ("ASC", "DESC"):
            cols.append(item[0].val)
    tabelas[nome].add_uk(cols)


def _comentario(toks: list[_Tok], tabelas: dict, pendentes: list):
    # COMMENT ON TABLE t IS '...'  |  COMMENT ON COLUMN t.c IS '...'
    alvo = toks[2].kw()
    if alvo not in ("TABLE", "COLUMN"):
        return
    ks = [i for i, t in enumerate(toks) if t.kw() == "IS"]
    if not ks:
        return
    ident = [t for t in toks[3:ks[0]] if not (t.tipo == "y" and t.val == ".")]
    txt_tok = toks[ks[0] + 1]
    texto = txt_tok.val if txt_tok.tipo == "s" else None
    pendentes.append((alvo, [t.val for t in ident], texto))


def ler_schema(caminhos: list[Path] | None = None) -> dict[str, dict]:
    """Lê os arquivos SQL (ignora os que não existem) e devolve as tabelas
    na ordem de criação, no formato descrito na Tarefa 2."""
    if caminhos is None:
        caminhos = [SQL_SCHEMA, SQL_DATAMART]
    tabelas: dict[str, _Tabela] = {}
    pendentes = []
    for caminho in caminhos:
        caminho = Path(caminho)
        if not caminho.exists():
            continue
        arquivo = _relativo(caminho)
        limpo = _limpar_sql(caminho.read_text(encoding="utf-8"))
        for cmd in _dividir_comandos(limpo):
            toks = _tokenizar(cmd)
            if len(toks) < 3:
                continue
            a, b = toks[0].kw(), toks[1].kw()
            if a == "CREATE" and b in ("TABLE", "TEMP", "TEMPORARY", "UNLOGGED", "GLOBAL", "LOCAL"):
                _criar_tabela(cmd, toks, arquivo, tabelas)
            elif a == "ALTER" and b == "TABLE":
                _alterar_tabela(cmd, toks, tabelas)
            elif a == "DROP" and b == "TABLE":
                k = 2
                if toks[k].kw() == "IF":
                    k += 2
                for item in _dividir_virgulas(toks[k:]):
                    if item and item[0].tipo == "w" and item[0].kw() not in ("CASCADE", "RESTRICT"):
                        nome, _ = _nome_tabela(item, 0)
                        tabelas.pop(nome, None)
            elif a == "CREATE" and b == "UNIQUE" and toks[2].kw() == "INDEX":
                _indice_unico(toks[1:], tabelas)
            elif a == "COMMENT" and b == "ON":
                _comentario(toks, tabelas, pendentes)
    for alvo, ident, texto in pendentes:
        if alvo == "TABLE":
            t = tabelas.get(ident[-1])
            if t is not None:
                t.comentario = texto
        elif len(ident) >= 2:
            t = tabelas.get(ident[-2])
            c = t.coluna(ident[-1]) if t else None
            if c is not None:
                c["comentario"] = texto
    for t in tabelas.values():  # a filha herda tambem o comentario da coluna da mae, se nao tem o proprio
        for pai, nome_col in t.herdadas:
            c, cp = t.coluna(nome_col), tabelas[pai].coluna(nome_col)
            if c is not None and cp is not None and c["comentario"] is None:
                c["comentario"] = cp["comentario"]
    return {nome: t.finalizar(tabelas) for nome, t in tabelas.items()}


# ---------------------------------------------------------------------------
# C. Divergências
# ---------------------------------------------------------------------------
def _numeros_citados(texto: str, palavra: str) -> list[int]:
    return [int(m) for m in re.findall(r"(\d+)\s+" + palavra.rstrip("s") + "s?", texto)]


def divergencias(catalogo: dict, schema: dict[str, dict]) -> dict:
    no_html = [t["nome"] for c in catalogo["camadas"] for t in c["tabelas"]]
    conj_html = set(no_html)
    faltam = [{"tabela": n, "arquivo": d["arquivo"]} for n, d in schema.items() if n not in conj_html]
    extras = [n for n in no_html if n not in schema]

    camadas = []
    for c in catalogo["camadas"]:
        citado = _numeros_citados(c["qtd_tabelas_texto"], "tabelas")
        real = len(c["tabelas"])
        camadas.append({"id": c["id"], "nome": c["nome"], "texto": c["qtd_tabelas_texto"],
                        "citado": citado[0] if citado else None, "real": real,
                        "confere": bool(citado) and citado[0] == real})

    totais_texto = []
    for fonte in ("apresentacao", "como_ler"):
        for palavra, real in (("tabelas", len(no_html)), ("grupos", len(catalogo["camadas"]))):
            for num in _numeros_citados(catalogo[fonte], palavra):
                totais_texto.append({"fonte": fonte, "palavra": palavra, "citado": num,
                                     "real": real, "confere": num == real})

    colunas_catalogadas = sum(len(schema[n]["colunas"]) for n in no_html if n in schema)
    por_arquivo = {}
    for d in schema.values():
        por_arquivo[d["arquivo"]] = por_arquivo.get(d["arquivo"], 0) + 1
    return {
        "sem_catalogo": faltam,
        "sem_schema": extras,
        "camadas": camadas,
        "totais_texto": totais_texto,
        "totais": {"html": len(no_html), "camadas": len(catalogo["camadas"]),
                   "schema": len(schema), "por_arquivo": por_arquivo},
        "colunas_catalogadas": colunas_catalogadas,
        "tabelas_catalogadas_no_schema": sum(1 for n in no_html if n in schema),
    }


def _imprimir_resumo(d: dict):
    t = d["totais"]
    print("== Divergências (apenas relato; nada foi corrigido) ==")
    print(f"\nTabelas do schema/datamart que faltam no catálogo HTML ({len(d['sem_catalogo'])}):")
    for x in d["sem_catalogo"]:
        print(f"  - {x['tabela']}  [{x['arquivo']}]")
    if not d["sem_catalogo"]:
        print("  (nenhuma)")
    print(f"\nTabelas do catálogo HTML que não existem no schema/datamart ({len(d['sem_schema'])}):")
    for x in d["sem_schema"]:
        print(f"  - {x}")
    if not d["sem_schema"]:
        print("  (nenhuma)")
    print(f"\nColunas: o catálogo HTML não documenta colunas; as {d['colunas_catalogadas']} colunas "
          f"das {d['tabelas_catalogadas_no_schema']} tabelas catalogadas vêm do schema.")
    print("\nInconsistências internas do HTML:")
    ruim = False
    for c in d["camadas"]:
        if not c["confere"]:
            ruim = True
            print(f"  - camada '{c['nome']}': texto diz '{c['texto']}', mas tem {c['real']} tabelas")
    for x in d["totais_texto"]:
        if not x["confere"]:
            ruim = True
            print(f"  - {x['fonte']} cita {x['citado']} {x['palavra']}, mas a contagem real é {x['real']}")
    if not ruim:
        print("  (nenhuma: quantidades por camada e totais citados conferem com a contagem real)")
    print("\nTotais:")
    print(f"  - tabelas no catálogo HTML: {t['html']} (em {t['camadas']} camadas)")
    for arq, qtd in t["por_arquivo"].items():
        print(f"  - tabelas em {arq}: {qtd}")
    print(f"  - tabelas no schema + datamart: {t['schema']}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    catalogo = extrair_catalogo()
    JSON_SAIDA.parent.mkdir(parents=True, exist_ok=True)
    JSON_SAIDA.write_text(json.dumps(catalogo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    schema = ler_schema([SQL_SCHEMA, SQL_DATAMART])
    _imprimir_resumo(divergencias(catalogo, schema))
    n_tab = sum(len(c["tabelas"]) for c in catalogo["camadas"])
    print(f"\nok: documentos/dados/catalogo.json ({n_tab} tabelas, {len(catalogo['camadas'])} camadas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
