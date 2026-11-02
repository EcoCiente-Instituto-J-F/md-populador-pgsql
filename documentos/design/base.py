"""Base de design dos documentos (HTML para PDF) no padrão do relatório de referência.

Os HTML finais ficam em documentos/ e referenciam design/documento.css e design/fontes/.
Importar com documentos/ no sys.path:  from design import base, arte
"""
import html as _html
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from .arte import PALETA_ROSA, PALETA_VERDE, arte

# ───────── geometria da página ─────────
LARGURA = 1100
ALTURA = 850
ESQ = 60
LARGURA_UTIL = 980
TOPO_CONTEUDO = 100  # abaixo da faixa .topo / cabeçalho corrido
BASE_CONTEUDO = 790  # o .num fica em bottom:26px
ALTURA_UTIL = BASE_CONTEUDO - TOPO_CONTEUDO

# ───────── rampas de cor (iguais às de gerar.mjs) ─────────
TAB = [[0, "#a9dcd6"], [1, "#4a9fb5"]]
CEU_CAPA = [[0, "#0f3a47"], [0.3, "#1d5e70"], [0.5, "#3f94a0"], [0.62, "#8fcfc8"], [0.74, "#2e5c41"], [1, "#064e3b"]]
CEU_LADO = [[0, "#205867"], [0.35, "#4fa3b0"], [0.65, "#cde6de"], [0.82, "#a7b7aa"], [1, "#2e5c41"]]

# elementos de arte padrão da referência (capa e página escura)
TIRAS_CAPA = [[160, 0, 545, 56], [412, 140, 688, 72], [0, 290, 660, 70]]
ARVORES_CAPA = [
    {"x": 95, "y": 470, "s": 120, "paleta": PALETA_ROSA},
    {"x": 850, "y": 500, "s": 70, "paleta": PALETA_VERDE},
    {"x": 955, "y": 505, "s": 80, "paleta": PALETA_VERDE},
    {"x": 1040, "y": 500, "s": 52, "paleta": PALETA_ROSA},
]
ARVORES_LADO = [
    {"x": 130, "y": 800, "s": 85, "paleta": PALETA_VERDE},
    {"x": 430, "y": 815, "s": 70, "paleta": PALETA_ROSA},
]

# ───────── alturas fixas (px) usadas no orçamento de página ─────────
# altura de linha de parágrafo por tamanho de fonte (px de fonte -> px de linha)
ALT_LINHA_PARAGRAFO = {10.5: 15, 11: 17, 11.5: 15, 12.5: 18, 17: 24, 18: 26}
ALT_TITULO_H2 = 30  # h2: 26px/30px (uma linha)
ESPACO_TITULO = 12  # folga entre o título e o conteúdo abaixo
ALT_THEAD = 29  # th: 7+7 de padding + 13 de linha + 1,5 de borda (arredondado para cima)
ALT_THEAD_COMPACTA = 25  # th: 5+5 + 13 + 1,5
ALT_LINHA_TABELA = 31  # td de 1 linha: 7+7 + 15 + 1 = 30; medido até 30,16 com .tag/.v (CSS os neutraliza)
ALT_LINHA_TABELA_COMPACTA = 26  # 5+5 + 14 + 1 = 25; medido até 25,42 com .tag/.v
ALT_EXTRA_TABELA = 15  # cada linha de texto adicional numa célula
ALT_EXTRA_TABELA_COMPACTA = 14
ESPACO_BLOCOS = 18  # entre blocos empilhados na mesma página
ESPACO_COLUNA = 12  # entre blocos dentro de uma coluna de FaixaColunas

# largura média de caractere, em fração do tamanho da fonte (conservador)
LARG_CHAR = 0.56
LARG_CHAR_MONO = 0.62

ERRO_PLAYWRIGHT = "Playwright não encontrado. Instale com: pip install playwright && python -m playwright install chromium"


def esc(texto):
    return _html.escape(str(texto), quote=True)


def pos(x, y, svg):
    return f'<div class="a" style="left:{x}px;top:{y}px">{svg}</div>'


def abre(seed, cheio=False, altura=None):
    """Faixa .topo creme com a tira de arte 705×60 em x=395."""
    estilo = f' style="height:{altura}px"' if altura else ""
    classe = " cheio" if cheio else ""
    return (f'<div class="topo{classe}"{estilo}></div>'
            + pos(395, 0, arte(705, 60, seed=seed, cols=18, rows=2, stops=TAB)))


_TEXTO_TAG = {
    "medido": "MEDIDO", "estimado": "ESTIMADO", "premissa": "PREMISSA", "amedir": "A MEDIR",
    "publico": "PUBLICO", "interno": "INTERNO", "restrito": "RESTRITO", "confidencial": "CONFIDENCIAL",
    "pii": "PII", "pk": "PK", "fk": "FK", "uk": "UK", "derivado": "DERIVADO",
}


def tag(tipo, texto=None):
    if tipo not in _TEXTO_TAG:
        raise ValueError(f"tipo de etiqueta desconhecido: {tipo!r}")
    return f'<span class="tag tag--{tipo}">{esc(texto if texto is not None else _TEXTO_TAG[tipo])}</span>'


# ───────── documento e páginas ─────────
class Documento:
    """Acumula as páginas e numera como a referência: a capa é a página 1."""

    def __init__(self, cabecalho):
        self.cabecalho = cabecalho
        self._n = 1
        self._secoes = []

    @property
    def numero_atual(self):
        return self._n

    @property
    def proximo_numero(self):
        return self._n + 1

    def capa(self, html):
        self._secoes.append(f'<section class="pg">\n{html}\n</section>')

    def pagina(self, classes, corpo):
        self._n += 1
        self._secoes.append(
            f'<section class="pg {classes}">\n{corpo}\n'
            f'<div class="run">{self.cabecalho}</div><div class="num">{self._n}</div>\n</section>')

    def html(self, titulo, caminho_css):
        return ('<!doctype html>\n<html lang="pt-BR">\n<head>\n<meta charset="utf-8">\n'
                f'<title>{esc(titulo)}</title>\n<link rel="stylesheet" href="{esc(caminho_css)}">\n'
                '</head>\n<body>\n' + "\n".join(self._secoes) + '\n</body>\n</html>\n')


def pagina_capa(chip, titulo_html, meta_itens, seed, tiras=None, arvores=None):
    """Corpo da capa (passe a Documento.capa). meta_itens: HTML de cada item da linha de metadados."""
    tiras = TIRAS_CAPA if tiras is None else tiras
    arvores = ARVORES_CAPA if arvores is None else arvores
    meta = "".join(f"<span>{m}</span>" for m in meta_itens)
    return (f'<div class="capa-topo"></div>\n<div class="capa-chip">{esc(chip)}</div>\n'
            '<img class="capa-logo" src="design/fontes/logo-verde.svg" alt="EcoCiente">\n'
            f'<div class="capa-titulo">{titulo_html}</div>\n<div class="capa-meta">{meta}</div>\n'
            + pos(0, 330, arte(1100, 520, seed=seed, cols=26, rows=13, stops=CEU_CAPA, tiras=tiras, arvores=arvores)))


def pagina_escura(titulo, lead, conteudo_direita_html, seed, arvores=None):
    """Corpo de página escura (passe a Documento.pagina('escura', ...)). O chamador posiciona o conteúdo da direita."""
    arvores = ARVORES_LADO if arvores is None else arvores
    return ('<div class="metade-esc"></div>\n'
            + pos(550, 0, arte(550, 850, seed=seed, cols=12, rows=18, stops=CEU_LADO, arvores=arvores))
            + '\n<div class="a" style="left:60px;top:118px;width:440px">\n'
            f'  <h2 class="grande" style="font-size:80px;line-height:74px">{esc(titulo)}</h2>\n'
            f'  <p class="lead" style="margin-top:24px">{esc(lead)}</p>\n</div>\n'
            + conteudo_direita_html)


# ───────── estimativa de altura ─────────
def linhas_texto(texto, largura_px, fonte_px, mono=False):
    """Estima as linhas de um texto; conservador (erra para mais linhas)."""
    cpl = max(1, int(largura_px / ((LARG_CHAR_MONO if mono else LARG_CHAR) * fonte_px)))
    total = 0
    for trecho in str(texto).split("\n"):
        linhas, atual = 1, 0
        for palavra in trecho.split():
            n = len(palavra)
            if n > cpl:  # palavra maior que a linha: quebra por caractere
                if atual:
                    linhas += 1
                linhas += math.ceil(n / cpl) - 1
                atual = n % cpl or cpl
            elif atual == 0:
                atual = n
            elif atual + 1 + n <= cpl:
                atual += 1 + n
            else:
                linhas += 1
                atual = n
        total += linhas
    return max(1, total)


def altura_paragrafo(texto, largura_px, fonte_px=12.5, mono=False):
    lin = ALT_LINHA_PARAGRAFO.get(fonte_px) or math.ceil(fonte_px * 1.45)
    return linhas_texto(texto, largura_px, fonte_px, mono) * lin


def altura_linha_tabela(linhas_na_maior_celula, compacta=False):
    base, extra = ((ALT_LINHA_TABELA_COMPACTA, ALT_EXTRA_TABELA_COMPACTA) if compacta
                   else (ALT_LINHA_TABELA, ALT_EXTRA_TABELA))
    return base + extra * (max(1, linhas_na_maior_celula) - 1)


# ───────── paginação por orçamento de altura ─────────
@dataclass
class Bloco:
    html: str
    altura: float
    id: object = None
    nome: str = ""


@dataclass
class TabelaPaginavel:
    """Tabela divisível entre linhas. Sem `titulo_continuacao_html`, `titulo_html` deve ser um único
    elemento (ex.: <h2>…</h2>): " (continuação)" é inserido antes da última tag de fechamento."""
    thead_html: str
    linhas: list  # [(html_linha, altura_linha)]
    titulo_html: str
    titulo_altura: float
    classe_tabela: str = ""
    minimo_linhas: int = 2
    id: object = None
    nome: str = ""
    altura_thead: float = None
    titulo_continuacao_html: str = None  # título das páginas seguintes; se None, usa titulo_html + " (continuação)"
    titulo_continuacao_altura: float = None  # altura do título de continuação; se None, usa titulo_altura

    def alt_thead(self):
        if self.altura_thead is not None:
            return self.altura_thead
        return ALT_THEAD_COMPACTA if "compacta" in self.classe_tabela.split() else ALT_THEAD


@dataclass
class FaixaColunas:
    """Faixa horizontal indivisível de N colunas (grade CSS); larguras como .c1/.c2/.c3 ([300, 306, 307]).
    gap: int, ou lista com o espaço de cada par de colunas (a referência usa 37 e 30)."""
    colunas: list  # list[list[Bloco]]
    larguras: list
    gap: object = 37
    id: object = None
    nome: str = ""
    altura: float = field(init=False)

    def __post_init__(self):
        if len(self.colunas) != len(self.larguras):
            raise ValueError("FaixaColunas: colunas e larguras têm tamanhos diferentes")
        if sum(self.larguras) > LARGURA_UTIL:
            raise ValueError(f"FaixaColunas: larguras somam mais que {LARGURA_UTIL}px")
        self.altura = max((sum(b.altura for b in c) + ESPACO_COLUNA * (len(c) - 1)) if c else 0
                          for c in self.colunas)

    @property
    def html(self):
        n = len(self.colunas)
        gaps = list(self.gap) if isinstance(self.gap, (list, tuple)) else [self.gap] * (n - 1)
        modelo, celulas = [], ""
        for i, (w, col) in enumerate(zip(self.larguras, self.colunas)):
            modelo.append(f"{w}px")
            corpo = "".join(f'<div style="margin-top:{ESPACO_COLUNA if j else 0}px">{b.html}</div>'
                            for j, b in enumerate(col))
            celulas += f"<div>{corpo}</div>"
            if i < n - 1:  # a folga entra como coluna vazia, para aceitar valores diferentes por par
                modelo.append(f"{gaps[i]}px")
                celulas += "<div></div>"
        return ('<div class="bloco" style="display:grid;align-items:start;'
                f'grid-template-columns:{" ".join(modelo)}">{celulas}</div>')


def _nome(item):
    return item.nome or (str(item.id) if item.id is not None else type(item).__name__)


def _titulo_continuacao(titulo_html):
    m = re.search(r"</[a-zA-Z0-9]+>\s*$", titulo_html)
    if m:
        return titulo_html[:m.start()] + " (continuação)" + titulo_html[m.start():]
    return titulo_html + " (continuação)"


def _html_tabela(t, linhas, continuacao):
    titulo = t.titulo_html
    if continuacao:
        titulo = t.titulo_continuacao_html or _titulo_continuacao(t.titulo_html)
    classe = f' class="{t.classe_tabela}"' if t.classe_tabela else ""
    corpo = "".join(l for l, _ in linhas)
    return f'<div class="bloco">{titulo}<table{classe}>{t.thead_html}<tbody>{corpo}</tbody></table></div>'


def paginar(blocos, altura_disponivel=ALTURA_UTIL):
    """Empilha os blocos em páginas, de cima para baixo.

    Devolve (paginas, onde): paginas = lista (por página) de listas de pedaços HTML;
    onde = {id: índice relativo da página em que o item começou}.
    """
    if not blocos:
        return [], {}
    paginas = [[]]
    usado = 0
    onde = {}

    def nova():
        nonlocal usado
        paginas.append([])
        usado = 0

    def colocar(html, altura):
        nonlocal usado
        espaco = ESPACO_BLOCOS if paginas[-1] else 0
        paginas[-1].append(f'<div style="margin-top:{espaco}px">{html}</div>' if espaco else html)
        usado += espaco + altura

    def espaco():
        return ESPACO_BLOCOS if paginas[-1] else 0

    def marca(item):
        if item.id is not None and item.id not in onde:
            onde[item.id] = len(paginas) - 1

    def cabem(item, i, livre):
        k = soma = 0
        while i + k < len(item.linhas) and soma + item.linhas[i + k][1] <= livre:
            soma += item.linhas[i + k][1]
            k += 1
        # sem linha órfã: se sobrariam menos de minimo_linhas para a página seguinte, desce linhas
        # daqui até a continuação ter o mínimo (desde que este pedaço também fique com o mínimo)
        resto = len(item.linhas) - (i + k)
        falta = item.minimo_linhas - resto
        if 0 < resto and falta > 0 and k - falta >= item.minimo_linhas:
            soma -= sum(h for _, h in item.linhas[i + k - falta:i + k])
            k -= falta
        return k, soma

    for item in blocos:
        if isinstance(item, TabelaPaginavel):
            n, cab = len(item.linhas), item.titulo_altura + item.alt_thead()
            cab_cont = item.alt_thead() + (item.titulo_altura if item.titulo_continuacao_altura is None
                                           else item.titulo_continuacao_altura)
            if max(cab, cab_cont) > altura_disponivel:
                raise ValueError(f"cabeçalho maior que uma página: {_nome(item)}")
            while True:  # primeiro pedaço: exige título + minimo_linhas
                k, soma = cabem(item, 0, altura_disponivel - usado - espaco() - cab)
                # se ainda sobrariam menos de minimo_linhas (cabem não conseguiu reequilibrar),
                # a tabela inteira vai para a página seguinte, salvo se esta já está vazia
                orfa = 0 < n - k < item.minimo_linhas
                if k >= min(item.minimo_linhas, n) and not (orfa and paginas[-1]):
                    break
                if not paginas[-1]:
                    raise ValueError(f"título e linhas mínimas não cabem numa página vazia: {_nome(item)}")
                nova()
            marca(item)
            colocar(_html_tabela(item, item.linhas[:k], False), cab + soma)
            i = k
            while i < n:  # continuação: página nova, título com " (continuação)" e thead repetido
                nova()
                k, soma = cabem(item, i, altura_disponivel - cab_cont)
                if k == 0:
                    raise ValueError(f"linha maior que uma página vazia: {_nome(item)}")
                colocar(_html_tabela(item, item.linhas[i:i + k], True), cab_cont + soma)
                i += k
        else:
            if item.altura > altura_disponivel:
                raise ValueError(f"bloco maior que uma página: {_nome(item)}")
            if usado + espaco() + item.altura > altura_disponivel:
                nova()
            marca(item)
            colocar(item.html, item.altura)
    return paginas, onde


# ───────── HTML para PDF e verificação ─────────
_JS_VERIFICAR = """
() => {
  const avisos = [];
  document.querySelectorAll('section.pg').forEach((sec, idx) => {
    const r0 = sec.getBoundingClientRect();
    const w = document.createTreeWalker(sec, NodeFilter.SHOW_TEXT);
    let no;
    while ((no = w.nextNode())) {
      const txt = no.nodeValue.replace(/\\s+/g, ' ').trim();
      const el = no.parentElement;
      if (!txt || !el || el.closest('.num, .run, svg')) continue;
      const rg = document.createRange();
      rg.selectNodeContents(no);
      const r = rg.getBoundingClientRect();
      if (!r.width && !r.height) continue;
      if (r.bottom - r0.top > %(alt)d - 20 || r.right - r0.left > %(larg)d || r.top < r0.top || r.left < r0.left) {
        avisos.push('pág ' + (idx + 1) + ': ' + txt.slice(0, 60) + ' ultrapassa a página');
      }
    }
  });
  return avisos;
}
""" % {"alt": ALTURA, "larg": LARGURA}

_JS_FONTES = """
async () => {
  const falhas = [];
  for (const f of ['Nunito', 'Plus Jakarta Sans', 'JetBrains Mono', 'Bebas Neue']) {
    try { await document.fonts.load('16px "' + f + '"'); } catch (e) {}
    if (!document.fonts.check('16px "' + f + '"')) falhas.push(f);
  }
  for (const ff of document.fonts) {
    const nome = ff.family.replace(/"/g, '');
    if (ff.status === 'error' && !falhas.includes(nome)) falhas.push(nome);
  }
  return falhas;
}
"""


def verificar_paginas(page):
    """Texto fora da página e fontes não carregadas; lista vazia = tudo certo."""
    avisos = list(page.evaluate(_JS_VERIFICAR))
    avisos += [f"fonte não carregou: {f}" for f in page.evaluate(_JS_FONTES)]
    return avisos


class Conversor:
    """Reaproveita um único Chromium para vários documentos:
    with Conversor() as c: c.converter(html, pdf)  (avisos da verificação em c.avisos)."""

    def __init__(self):
        self.avisos = []
        self._pw = self._navegador = None

    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise RuntimeError(ERRO_PLAYWRIGHT) from e
        self._pw = sync_playwright().start()
        try:
            self._navegador = self._pw.chromium.launch(headless=True)
        except Exception as e:
            self._pw.stop()
            self._pw = None
            raise RuntimeError(ERRO_PLAYWRIGHT) from e
        return self

    def __exit__(self, *_):
        if self._navegador:
            self._navegador.close()
        if self._pw:
            self._pw.stop()

    def converter(self, caminho_html, caminho_pdf):
        """Gera o PDF e devolve o número de páginas."""
        page = self._navegador.new_page()
        try:
            page.goto(Path(caminho_html).resolve().as_uri())
            page.evaluate("document.fonts.ready.then(() => true)")
            page.wait_for_load_state("networkidle")
            self.avisos = verificar_paginas(page)
            page.pdf(path=str(caminho_pdf), width="1100px", height="850px",
                     print_background=True, prefer_css_page_size=True)
            secoes = page.locator("section.pg").count()
        finally:
            page.close()
        try:
            import pymupdf
        except ImportError:
            return secoes
        with pymupdf.open(str(caminho_pdf)) as pdf:
            return pdf.page_count


def html_para_pdf(caminho_html, caminho_pdf):
    with Conversor() as c:
        return c.converter(caminho_html, caminho_pdf)
