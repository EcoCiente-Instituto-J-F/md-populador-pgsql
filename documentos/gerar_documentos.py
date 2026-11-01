"""Gera os documentos de documentos/ em HTML e converte cada um para PDF (Playwright/Chromium).

Uso, a partir da raiz do repositório:
    python documentos/gerar_documentos.py            # HTML + PDF
    python documentos/gerar_documentos.py --sem-pdf  # só HTML

Cada documento tem uma função gerar_*() que devolve (nome_arquivo_html, html, n_paginas);
main() grava os HTML e converte todos com um único Chromium.
"""
import argparse
import math
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

AQUI = Path(__file__).resolve().parent
if str(AQUI) not in sys.path:
    sys.path.insert(0, str(AQUI))

from design import arte, base  # noqa: E402
import extrair_catalogo  # noqa: E402

CSS = "design/documento.css"
esc = base.esc


# ═════════════ regras derivadas (nível de acesso e PII) ═════════════
NIVEIS = ["publico", "interno", "restrito", "confidencial"]
PERFIS_FORA_DA_REGRA = {"Sistema", "DBA"}  # perfis de negócio = todos os outros
BADGES_LIVRES = {"R", "W", "RW"}
BADGES_RESTRITOS = {"R*", "W*", "RW*"}

PII_GERAL = {"nome_usuario", "email_usuario", "senha_hash", "data_nascimento", "cpf", "url_avatar"}
PII_POR_TABELA = {
    "tb_enderecos": {"cep", "bairro", "logradouro", "numero", "complemento"},
    "tb_telefones": {"numero_contato"},
}


def nivel_tabela(tabela_json):
    """PUBLICO/INTERNO/RESTRITO/CONFIDENCIAL a partir das permissões dos perfis de negócio."""
    negocio = [p for p in tabela_json["permissoes"] if p["perfil"] not in PERFIS_FORA_DA_REGRA]
    for p in negocio:
        if p["badge"] not in BADGES_LIVRES | BADGES_RESTRITOS | {"0"}:
            raise ValueError(f"badge desconhecido em {tabela_json['nome']}: {p['badge']!r}")
    livres = [p for p in negocio if p["badge"] in BADGES_LIVRES]
    restritos = [p for p in negocio if p["badge"] in BADGES_RESTRITOS]
    if negocio and len(livres) == len(negocio):
        return "publico"
    if livres:
        return "interno"
    if restritos:
        return "restrito"
    return "confidencial"


def eh_pii(nome_tabela, nome_coluna):
    return nome_coluna in PII_GERAL or nome_coluna in PII_POR_TABELA.get(nome_tabela, ())


def nivel_coluna(nivel_da_tabela, nome_tabela, nome_coluna):
    """Nível da tabela, elevado a RESTRITO se a coluna for PII e a CONFIDENCIAL se for senha_hash."""
    i = NIVEIS.index(nivel_da_tabela)
    if eh_pii(nome_tabela, nome_coluna):
        i = max(i, NIVEIS.index("restrito"))
        if nome_coluna == "senha_hash":
            i = NIVEIS.index("confidencial")
    return NIVEIS[i]


def montar_modelo(catalogo, schema):
    """Camadas do catálogo com as colunas do schema (na ordem do schema) e os campos derivados."""
    camadas = []
    for c in catalogo["camadas"]:
        tabelas = []
        for t in c["tabelas"]:
            sc = schema.get(t["nome"])
            if sc is None:
                raise ValueError(f"tabela do catálogo ausente do schema: {t['nome']}")
            nivel = nivel_tabela(t)
            em_fk = {col for f in sc["fks"] for col in f["colunas"]}
            colunas = []
            for col in sc["colunas"]:
                chaves = [k for k, sim in (("pk", col["pk"]),
                                           ("fk", col["fk"] is not None or col["nome"] in em_fk),
                                           ("uk", col["uk"])) if sim]
                colunas.append({
                    "nome": col["nome"], "tipo": col["tipo"], "nulo": col["nulo"], "chaves": chaves,
                    "pii": eh_pii(t["nome"], col["nome"]),
                    "nivel": nivel_coluna(nivel, t["nome"], col["nome"]),
                    "descricao": col["comentario"],
                })
            fks = [(o, f["tabela"], d) for f in sc["fks"] for o, d in zip(f["colunas"], f["colunas_destino"])]
            tabelas.append({**t, "nivel": nivel, "colunas": colunas, "fks": fks})
        camadas.append({"numero": c["numero"], "nome": c["nome"], "descricao": c["descricao"],
                        "tabelas": tabelas})
    return camadas


def todas_tabelas(camadas):
    return [t for c in camadas for t in c["tabelas"]]


def perfis_de_negocio(camadas):
    vistos = []
    for t in todas_tabelas(camadas):
        for p in t["permissoes"]:
            if p["perfil"] not in PERFIS_FORA_DA_REGRA and p["perfil"] not in vistos:
                vistos.append(p["perfil"])
    return vistos


def enumerar(itens):
    """['a', 'b', 'c'] -> 'a, b e c'."""
    itens = list(itens)
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


# ═════════════ auxiliares de HTML e de altura ═════════════
# fontes e alturas de linha usadas nas estimativas (as mesmas do documento.css)
F_CORPO, L_CORPO = 12.5, 18
F_FICHA, L_FICHA = 11.5, 16.5  # .ficha-lista
F_PERM, L_PERM = 11, 15  # .perm-linha, .perm e .ficha-lista.mono (linha)
F_MONO_LISTA = 10.5  # .ficha-lista.mono
F_TAB, F_MONO_TAB = 10.5, 9.7  # table.compacta e td.mono
F_MONO_ITEM, L_ITEM = 10.2, 15  # .ind-item
ALT_ROT = 14 + 8  # .rot-sec + .ficha-rot (margem de baixo)
ALT_SUB = 12 + 25  # p.sub de uma linha, com a margem de cima


def tag_neutra(texto):
    """Etiqueta sem cor (o tipo da tabela, como está no catálogo)."""
    return f'<span class="tag">{esc(texto.upper())}</span>'


def quebravel(texto):
    """Nome técnico que pode quebrar depois de '_' e '.', sem cortar no meio da palavra."""
    return esc(texto).replace("_", "_<wbr>").replace(".", ".<wbr>")


def prosa(texto):
    """Texto corrido do catálogo: escapado, podendo quebrar depois de '/' (ex.: tipos_a/tipos_b)."""
    return esc(texto).replace("/", "/<wbr>")


# ───── estimativa de linhas pela largura de cada caractere ─────
# A média fixa de base.linhas_texto (0,56 em) erra uma linha inteira com frequência; aqui cada caractere
# tem a largura medida da fonte, e a quebra só acontece onde o navegador quebra (espaço, '-' antes de
# letra e os <wbr> que o gerador insere). JetBrains Mono tem 0,6 em em todos os caracteres.
# avanço de cada caractere do Plus Jakarta Sans, em milésimos de em (medido no Chromium, arredondado para cima)
_CARACTERES = ' !"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[]^_`abcdefghijklmnopqrstuvwxyz{|}~ª°·ºÀÁÂÃÇÉÊÍÓÔÕ×Úàáâãçéêíóôõúü–—‘’“”…'
_MILESIMOS_500 = (
    "173 312 429 832 646 998 754 267 323 323 499 624 299 532 317 455 724 382 599 610 638 616 599 548 629 "
    "599 317 337 624 624 624 527 928 672 692 779 741 606 583 817 735 264 386 662 535 855 738 878 645 878 "
    "648 646 522 706 667 996 618 635 580 349 349 624 620 362 575 669 603 669 614 388 659 580 237 237 558 "
    "237 913 580 654 669 669 350 511 396 580 533 826 511 553 460 344 332 344 624 452 500 317 498 672 672 "
    "672 672 779 606 606 264 878 878 878 624 706 575 575 575 575 603 614 614 209 654 654 654 580 580 597 "
    "927 299 299 467 467 717 "
)
_MILESIMOS_800 = (
    "180 400 532 956 647 1070 813 333 407 407 560 678 386 634 408 532 700 413 596 612 662 614 604 564 633 "
    "604 408 428 678 678 678 611 926 732 690 772 739 589 587 804 732 287 396 687 547 912 742 878 649 878 "
    "667 647 552 724 712 1032 682 672 567 449 449 678 684 391 583 673 611 673 611 401 648 599 260 260 586 "
    "260 929 599 651 673 673 386 515 421 599 582 912 582 602 492 425 426 425 678 442 552 408 481 732 732 "
    "732 732 772 589 589 287 878 878 878 678 724 583 583 583 583 611 611 611 238 651 651 651 599 599 684 "
    "1014 386 386 606 606 808 "
)


def _tabela(milesimos):
    return dict(zip(_CARACTERES, (int(v) for v in milesimos.split())))


LARGURA_CHAR = {500: _tabela(_MILESIMOS_500), 800: _tabela(_MILESIMOS_800)}


def _larg(c, fonte, peso, mono):
    if mono:
        return 0.6 * fonte
    return LARGURA_CHAR[peso].get(" " if c == " " else c, 1000) / 1000 * fonte  # desconhecido: 1 em


def unidades(segmentos):
    """segmentos: [(texto, fonte_px, peso, mono, espacamento_em, quebra_depois)].
    Devolve os pedaços entre oportunidades de quebra: [(largura, largura do espaço que vem depois)]."""
    plano = [(c, s) for s in segmentos for c in s[0]]
    saida, atual = [], 0.0
    for i, (c, (_, fonte, peso, mono, esp, quebra)) in enumerate(plano):
        if c == " ":
            saida.append((atual, _larg(" ", fonte, peso, mono) + esp * fonte))
            atual = 0.0
            continue
        atual += _larg(c, fonte, peso, mono) + esp * fonte
        prox = plano[i + 1][0] if i + 1 < len(plano) else ""
        if prox and prox != " " and (c in quebra or (c == "-" and prox.isalpha())):
            saida.append((atual, 0.0))
            atual = 0.0
    saida.append((atual, 0.0))
    return saida


def contar_linhas(pedacos, largura_px):
    """Quebra gulosa, como o navegador; 1 px de folga na largura."""
    n, linha, espaco = 1, 0.0, 0.0
    limite = largura_px - 1
    for w, sp in pedacos:
        if linha == 0:
            linha = w
        elif linha + espaco + w <= limite:
            linha += espaco + w
        else:
            n, linha = n + 1, w
        espaco = sp
    return n


def seg(texto, fonte, peso=500, mono=False, espacamento=0.0, quebra="/"):
    return (str(texto), fonte, peso, mono, espacamento, quebra)


def linhas(texto, largura_px, fonte_px, peso=500):
    """Linhas de texto corrido em Plus Jakarta Sans (com quebra depois de '/')."""
    return contar_linhas(unidades([seg(texto, fonte_px, peso)]), largura_px)


def linhas_quebravel(texto, largura_px, fonte_px):
    """Linhas de um nome técnico em JetBrains Mono, com quebra depois de '_' e '.' (ver quebravel)."""
    return contar_linhas(unidades([seg(texto, fonte_px, mono=True, quebra="_.")]), largura_px)


def alt(linhas, altura_linha):
    return math.ceil(linhas * altura_linha)


def badge_legivel(badge, badges):
    """'RW*' -> 'Leitura e escrita*', com os textos do próprio catálogo."""
    return badges[badge.rstrip("*")] + ("*" if badge.endswith("*") else "")


def regra_de_acesso(permissoes):
    """Permissões compactas: 'Usuário R* (só o próprio) · … · DBA RW'."""
    return " · ".join(f'{p["perfil"]} {p["badge"]}' + (f' ({p["detalhe"]})' if p["detalhe"] else "")
                      for p in permissoes)


def thead_fixo(colunas, a_direita=()):
    """<colgroup> com larguras fixas + cabeçalho (a tabela usa a classe 'fixa')."""
    grupo = "".join(f'<col style="width:{w}px">' for _, w in colunas)
    ths = "".join(f'<th class="v">{n}</th>' if n in a_direita else f"<th>{n}</th>" for n, _ in colunas)
    return f"<colgroup>{grupo}</colgroup><thead><tr>{ths}</tr></thead>"


def conteudo(pedacos):
    """Contêiner do corpo paginado (left 60, top 100, largura 980)."""
    return f'<div class="a" style="left:60px;top:100px;width:980px">{"".join(pedacos)}</div>'


@dataclass
class Pagina:
    classes: str
    corpo: str
    fichas: list = field(default_factory=list)  # tabelas cuja ficha começa nesta página


def arvores_lado(i):
    """Duas árvores da arte lateral, variando posição, tamanho e paleta com i."""
    a, b = (arte.PALETA_VERDE, arte.PALETA_ROSA) if i % 2 else (arte.PALETA_ROSA, arte.PALETA_VERDE)
    return [{"x": 100 + (i * 37) % 70, "y": 800, "s": 70 + (i * 13) % 25, "paleta": a},
            {"x": 370 + (i * 23) % 60, "y": 815, "s": 62 + (i * 17) % 28, "paleta": b}]


# ═════════════ catálogo: peças ═════════════
# árvores pequenas no pé da arte, para os dois vidros altos da página "Como ler" não as cobrirem
ARVORES_BAIXAS = [{"x": 90, "y": 850, "s": 44, "paleta": arte.PALETA_VERDE},
                  {"x": 360, "y": 852, "s": 38, "paleta": arte.PALETA_ROSA}]
CAB_CATALOGO = "Catálogo de dados · EcoCiente · PostgreSQL"

COLS_FICHA = [("Coluna", 196), ("Tipo", 96), ("Nulo", 40), ("Chave", 72), ("PII", 42), ("Nível", 100),
              ("Descrição", 434)]
LARG_INDICE = [300, 306, 307]
GAP_INDICE = [37, 30]


def item_indice(nome, nivel, pagina, largura):
    """Linha 'nome · nível · página' (índice e aberturas). Devolve (html, altura)."""
    html = (f'<div class="ind-item"><a class="v ind-nome" href="#{esc(nome)}">{quebravel(nome)}</a>'
            f'{base.tag(nivel)}<span class="v ind-pg">{pagina}</span></div>')
    return html, alt(linhas_quebravel(nome, largura - 88 - 24 - 16, F_MONO_ITEM), L_ITEM) + 7


def secao(rotulo, html, altura):
    return base.Bloco(f'<div class="rot-sec ficha-rot">{rotulo}</div>{html}', ALT_ROT + altura + 2)


def secao_lista(rotulo, itens, vazio="—", mono=False):
    """itens: [(html, altura)]. Lista com losango, ou o texto de vazio em cinza."""
    if not itens:
        return secao(rotulo, f'<p class="ficha-vazio cinza">{vazio}</p>', L_FICHA)
    classe = "lista ficha-lista mono" if mono else "lista ficha-lista"
    html = f'<ul class="{classe}">' + "".join(f"<li>{h}</li>" for h, _ in itens) + "</ul>"
    return secao(rotulo, html, sum(a for _, a in itens) + 7 * (len(itens) - 1))


def itens_texto(textos, largura):
    return [(prosa(t), alt(linhas(t, largura - 14, F_FICHA), L_FICHA)) for t in textos]


def secao_permissoes(permissoes, badges, largura):
    """Permissões numa linha corrida: perfil em negrito, badge legível e o detalhe em cinza."""
    partes, plano = [], []
    for p in permissoes:
        texto = badge_legivel(p["badge"], badges)
        detalhe = f' <span class="cinza">({prosa(p["detalhe"])})</span>' if p["detalhe"] else ""
        partes.append(f'<b>{esc(p["perfil"])}</b>&nbsp;{esc(texto)}{detalhe}')
        plano.append(f'{p["perfil"]}xx {texto}' + (f' ({p["detalhe"]})' if p["detalhe"] else ""))
    html = '<p class="perm-linha">' + '<span class="cinza"> · </span>'.join(partes) + "</p>"
    # o negrito é mais largo que a média: estima com 10% menos de largura
    altura = alt(linhas(" · ".join(plano), largura * 0.9, F_PERM), L_PERM)
    if any(p["badge"].endswith("*") for p in permissoes):
        html += f'<p class="nota" style="margin-top:6px">* {esc(badges["*"])}</p>'
        altura += 6 + 15
    return secao("Permissões", html, altura)


def secao_fks(fks, largura):
    # quebra só nos espaços e depois do '.', para não partir nome de coluna
    itens = [(f"{esc(o)} → {esc(t)}.<wbr>{esc(d)}",
              alt(base.linhas_texto(f"{o} → {t}. {d}", largura - 14, F_MONO_LISTA, mono=True), L_PERM))
             for o, t, d in fks]
    return secao_lista("FKs de saída", itens, vazio="nenhuma", mono=True)


def linha_coluna(c):
    w = dict(COLS_FICHA)
    chaves = " ".join(base.tag(k) for k in c["chaves"])
    pii = base.tag("pii") if c["pii"] else ""
    desc = prosa(c["descricao"]) if c["descricao"] else '<span class="cinza">—</span>'
    html = (f'<tr><td class="mono">{quebravel(c["nome"])}</td><td class="mono">{esc(c["tipo"])}</td>'
            f'<td>{"sim" if c["nulo"] else "não"}</td><td>{chaves}</td><td>{pii}</td>'
            f'<td>{base.tag(c["nivel"])}</td><td>{desc}</td></tr>')
    n = max(linhas_quebravel(c["nome"], w["Coluna"] - 12, F_MONO_TAB),
            linhas_quebravel(c["tipo"], w["Tipo"] - 12, F_MONO_TAB),
            linhas(c["descricao"] or "—", w["Descrição"] - 12, F_TAB))
    return html, base.altura_linha_tabela(n, compacta=True)


def ficha(t, badges):
    """Ficha da tabela. O cabeçalho e a faixa de 3 colunas vão no título da TabelaPaginavel das colunas:
    assim a ficha só começa numa página se couberem também o título e 2 linhas da tabela."""
    nome = t["nome"]
    cab = (f'<div class="ficha-nome"><span class="v">{esc(nome)}</span>{tag_neutra(t["tipo"])}'
           f'{base.tag(t["nivel"])}{base.tag("derivado")}</div>'
           f'<p class="ficha-desc">{prosa(t["descricao"])}</p>')
    alt_cab = 1.5 + 12 + 26 + 6 + alt(linhas(t["descricao"], 643, F_CORPO), L_CORPO)
    faixa = base.FaixaColunas(
        [[secao_lista("Regras de negócio", itens_texto(t["regras"], 300))],
         [secao_lista("Observações", itens_texto(t["observacoes"], 306))],
         [secao_permissoes(t["permissoes"], badges, 307), secao_fks(t["fks"], 307)]],
        [300, 306, 307], gap=[37, 30])
    rotulo = f'Colunas de <span class="v">{esc(nome)}</span>'
    titulo = (f'<div class="ficha" id="{esc(nome)}">{cab}<div style="margin-top:16px">{faixa.html}</div>'
              f'<div class="rot-sec ficha-rot" style="margin-top:18px">{rotulo}</div></div>')
    linhas_tab = [linha_coluna(c) for c in t["colunas"]]
    altura_titulo = math.ceil(alt_cab + 16 + faixa.altura + 18 + ALT_ROT)
    # ficha que cabe inteira numa página não é dividida: vai toda para a página seguinte
    inteira = altura_titulo + base.ALT_THEAD_COMPACTA + sum(h for _, h in linhas_tab) <= base.ALTURA_UTIL
    return base.TabelaPaginavel(
        thead_html=thead_fixo(COLS_FICHA), linhas=linhas_tab,
        titulo_html=titulo, titulo_altura=altura_titulo,
        classe_tabela="compacta fixa", minimo_linhas=len(linhas_tab) if inteira else 2, id=nome, nome=nome,
        titulo_continuacao_html=f'<div class="rot-sec ficha-rot">{rotulo} (continuação)</div>',
        titulo_continuacao_altura=ALT_ROT)


def cabecalho(titulo_html, sub_html, largura_sub=643):
    """h2 + p.sub de uma linha (bloco de abertura de página clara)."""
    return base.Bloco(f'<h2>{titulo_html}</h2><p class="sub" style="width:{largura_sub}px">{sub_html}</p>',
                      base.ALT_TITULO_H2 + ALT_SUB)


def paginas_claras(blocos, seed, cheio=True):
    """Pagina os blocos no contêiner padrão, cada página com a faixa .topo e a arte do topo."""
    paginas, onde = base.paginar(blocos)
    saida = []
    for i, pedacos in enumerate(paginas):
        fichas = [nome for nome, j in onde.items() if j == i]
        c = cheio if isinstance(cheio, bool) else cheio(i)
        saida.append(Pagina("", base.abre(seed + i, c) + "\n" + conteudo(pedacos), fichas))
    return saida


# ═════════════ catálogo: páginas ═════════════
def capa_catalogo(camadas, hoje):
    meta = ["<b>EcoCiente</b> PostgreSQL 14+", f"gerado em {hoje}",
            f"{len(todas_tabelas(camadas))} tabelas · {len(camadas)} camadas", "fonte: catalogo_atual.html + sql/"]
    return base.pagina_capa("EcoCiente · PostgreSQL", "Catálogo<br>de dados", meta, seed=17)


def legenda(itens):
    """ul.legenda.larga (coluna de etiqueta de 104px): [(etiqueta_html, texto)]."""
    return '<ul class="legenda larga">' + "".join(f"<li>{e}<span>{esc(t)}</span></li>" for e, t in itens) + "</ul>"


def pagina_como_ler(catalogo, camadas):
    perfis = enumerar(perfis_de_negocio(camadas))
    intro = f"Perfis de negócio: {perfis}. Sistema e DBA não entram na regra."
    niveis = legenda([
        (base.tag("publico"), "todos os perfis de negócio da tabela têm acesso sem restrição (R, W ou RW)."),
        (base.tag("interno"), "ao menos um perfil de negócio tem acesso sem restrição, mas não todos."),
        (base.tag("restrito"), "nenhum perfil de negócio tem acesso sem restrição; ao menos um tem acesso restrito (*)."),
        (base.tag("confidencial"), "nenhum perfil de negócio tem acesso: todos estão com 0."),
        (base.tag("derivado"), "nível e PII saem de uma regra fixa (permissões do catálogo e nome da coluna); "
                               "não são uma classificação oficial."),
    ])
    etiquetas = legenda([
        (base.tag("pk"), "chave primária."),
        (base.tag("fk"), "chave estrangeira; o destino aparece na ficha, em FKs de saída."),
        (base.tag("uk"), "valor único (UNIQUE), sozinho ou junto com outras colunas."),
        (base.tag("pii"), "dado pessoal, pelo nome da coluna: nome, e-mail, senha, nascimento, CPF e avatar "
                          "do usuário, endereço e telefone. A coluna fica no mínimo RESTRITO; senha_hash, "
                          "CONFIDENCIAL."),
    ])
    # os dois vidros empilhados num contêiner: a posição do segundo não depende de estimativa
    direita = ('<div class="a" style="left:600px;top:118px;width:440px">\n'
               '<div class="vidro" style="position:relative">\n  <h3>Níveis de acesso</h3>\n'
               f'  <p style="margin-bottom:16px">{esc(intro)}</p>\n  {niveis}\n</div>\n'
               '<div class="vidro" style="position:relative;margin-top:20px">\n  <h3>Etiquetas das colunas</h3>\n'
               f'  {etiquetas}\n</div>\n</div>')
    return Pagina("escura", base.pagina_escura("Como ler este catálogo", catalogo["como_ler"], direita, seed=29,
                                               arvores=ARVORES_BAIXAS))


def paginas_camadas_perfis(catalogo, camadas):
    n_tab = len(todas_tabelas(camadas))
    cab = cabecalho("Camadas e perfis de acesso",
                    f'<span class="m">As {n_tab} tabelas estão em {len(camadas)} camadas;</span> '
                    f'o acesso é dado por perfil.')
    cols = [("Nº", 44), ("Camada", 196), ("Tabelas", 64), ("Descrição", 676)]
    linhas_c = []
    for c in camadas:
        html = (f'<tr><td class="v">{c["numero"]:02d}</td><th scope="row">{esc(c["nome"])}</th>'
                f'<td class="v">{len(c["tabelas"])}</td><td>{prosa(c["descricao"])}</td></tr>')
        n = max(linhas(c["nome"], 196 - 12, F_TAB), linhas(c["descricao"], 676 - 12, F_TAB))
        linhas_c.append((html, base.altura_linha_tabela(n, compacta=True)))
    tabela = base.TabelaPaginavel(
        thead_html=thead_fixo(cols, a_direita=("Nº", "Tabelas")), linhas=linhas_c,
        titulo_html='<div class="rot-sec ficha-rot">Camadas</div>', titulo_altura=ALT_ROT,
        classe_tabela="compacta fixa", nome="camadas")
    # perfis (tabela) e legenda das permissões, lado a lado
    cols_p = [("Perfil", 130), ("Descrição", 513)]
    linhas_p, h_p = "", 0
    for p in catalogo["perfis"]:
        linhas_p += f'<tr><th scope="row">{esc(p["nome"])}</th><td>{esc(p["descricao"])}</td></tr>'
        h_p += base.altura_linha_tabela(linhas(p["descricao"], 513 - 12, F_TAB), compacta=True)
    perfis = secao("Perfis de acesso",
                   f'<table class="compacta fixa">{thead_fixo(cols_p)}<tbody>{linhas_p}</tbody></table>',
                   base.ALT_THEAD_COMPACTA + h_p)
    legenda_b = "".join(f'<div class="perm"><b class="v">{esc(k)}</b><span>{esc(v)}</span></div>'
                        for k, v in catalogo["badges"].items())
    badges = secao("Legenda das permissões", legenda_b, len(catalogo["badges"]) * (L_PERM + 5))
    faixa = base.FaixaColunas([[perfis], [badges]], [643, 300], gap=37)
    return paginas_claras([cab, tabela, faixa], seed=31)


def cartao(cls, rot, big, small, texto, tags=()):
    ori = f'<div class="ori">{" ".join(base.tag(t) for t in tags)}</div>' if tags else ""
    return (f'<div class="card {cls}"><div class="rot">{rot}</div><div class="big">{big}<small>{small}</small>'
            f'</div><p>{texto}</p>{ori}</div>')


def pagina_resumo(camadas, div):
    tabelas = todas_tabelas(camadas)
    n_tab, n_cam = len(tabelas), len(camadas)
    n_col = sum(len(t["colunas"]) for t in tabelas)
    pii = [(t["nome"], c["nome"]) for t in tabelas for c in t["colunas"] if c["pii"]]
    n_tab_pii = len({t for t, _ in pii})
    conf_por_camada = sorted(((sum(t["nivel"] == "confidencial" for t in c["tabelas"]), c["nome"]) for c in camadas),
                             key=lambda x: -x[0])
    conf_por_camada = [(n, nome) for n, nome in conf_por_camada if n]
    n_conf = sum(n for n, _ in conf_por_camada)
    n_fk = sum("fk" in c["chaves"] for t in tabelas for c in t["colunas"])
    fora = [d["tabela"] for d in div["sem_catalogo"]]
    n_schema = div["totais"]["schema"]
    cartoes = [
        cartao("g-rosa", "Tabelas", str(n_tab), f"no catálogo · {n_cam} camadas",
               f"O schema SQL tem {n_schema}: <b>{len(fora)}</b> ficam fora do catálogo."),
        cartao("g-verde", "Colunas", str(n_col), f"nas {n_tab} tabelas",
               "Lidas do schema SQL, porque o catálogo atual não documenta colunas."),
        cartao("g-azul", "Colunas PII", str(len(pii)), f"em {n_tab_pii} tabelas",
               "Dados pessoais de usuário, endereço e telefone, pelo nome da coluna.", ["derivado"]),
        cartao("g-rosa", "Tabelas CONFIDENCIAL", str(n_conf), "nenhum perfil de negócio acessa",
               "Por camada: " + enumerar(f"{n} em {esc(nome)}" for n, nome in conf_por_camada) + ".",
               ["derivado"]),
        cartao("g-verde", "FKs", str(n_fk), "colunas com chave estrangeira",
               "Contadas por coluna. O destino de cada uma está na ficha da tabela."),
    ]
    nomes_fora = ", ".join(f'<span class="v">{esc(n)}</span>' for n in fora)
    corpo = f"""{base.abre(37, True)}
<div class="a" style="left:60px;top:104px;width:980px"><div class="grande">O resumo em cinco números</div><p class="sub" style="margin-top:14px">Cada cartão é calculado do catálogo e do schema SQL. As páginas seguintes detalham tabela por tabela.</p></div>
<div class="cinco">
  {(chr(10) + "  ").join(cartoes)}
</div>
<div class="nao">
  <div class="sig"><div class="rot">O que este catálogo não afirma</div><p>Três limites que valem para todo o documento.</p></div>
  <ul class="lista">
    <li>Que nível de acesso e PII sejam oficiais: os dois são derivados por regra fixa, das permissões do catálogo e do nome da coluna.</li>
    <li>Nada sobre colunas a partir do HTML: o catálogo atual não documenta colunas; tipos, chaves e descrições vêm do schema SQL.</li>
    <li>Que cubra todo o schema: {len(fora)} tabelas ficam fora.<span style="display:block;margin-top:4px;font-size:10.5px;line-height:14px">{nomes_fora}.</span></li>
  </ul>
</div>"""
    return Pagina("", corpo)


def pagina_matriz(camadas):
    tabelas = todas_tabelas(camadas)
    n_tab = len(tabelas)
    total = {n: sum(t["nivel"] == n for t in tabelas) for n in NIVEIS}

    def celula(v):
        return f'<td class="v">{v}</td>' if v else '<td class="v cinza">—</td>'

    corpo_t = ""
    for c in camadas:
        cont = [sum(t["nivel"] == n for t in c["tabelas"]) for n in NIVEIS]
        corpo_t += (f'<tr><th scope="row">{esc(c["nome"])}</th>{"".join(celula(v) for v in cont)}'
                   f'<td class="v">{len(c["tabelas"])}</td></tr>')
    corpo_t += (f'<tr class="soma"><th scope="row">Total</th>{"".join(celula(total[n]) for n in NIVEIS)}'
               f'<td class="v">{n_tab}</td></tr>')
    thead = ("<thead><tr><th>Camada</th>" + "".join(f'<th class="v">{base.tag(n)}</th>' for n in NIVEIS)
             + '<th class="v">Total</th></tr></thead>')
    todas_conf = [c["nome"] for c in camadas if all(t["nivel"] == "confidencial" for t in c["tabelas"])]
    extra = (f'<p class="corpo" style="margin-top:14px">Todas as tabelas de {enumerar(esc(n) for n in todas_conf)} '
             f'estão nesse nível.</p>') if todas_conf else ""
    perfis = enumerar(perfis_de_negocio(camadas))
    rot = "font:800 11px/14px 'Plus Jakarta Sans',sans-serif;letter-spacing:.07em;text-transform:uppercase;margin-bottom:9px"
    corpo = f"""{base.abre(41, True, 590)}
<div class="a c1 l1">
  <h2>Camada × nível de acesso {base.tag("derivado")}</h2>
  <p class="sub"><span class="m">{total["confidencial"]} das {n_tab} tabelas são CONFIDENCIAL:</span> nenhum perfil de negócio tem acesso a elas.</p>
  {extra}
</div>
<div class="a c23" style="top:130px">
  <table>{thead}<tbody>{corpo_t}</tbody></table>
</div>
<div class="a c1 sig" style="top:630px"><div class="rot">O que isso significa</div><p>{total["publico"]} tabelas são abertas a todos os perfis de negócio; {total["confidencial"]} ficam fora do alcance de todos eles.</p></div>
<div class="a c2 corpo" style="top:630px">
  <div class="rot" style="{rot}">Como o nível é calculado</div>
  <p>Pelas permissões de cada tabela no catálogo, contando só os perfis de negócio: {esc(perfis)}. Acesso marcado com * conta como restrito.</p>
</div>
<div class="a c3 corpo" style="top:630px">
  <div class="rot" style="{rot}">Limite</div>
  <p>É uma leitura das permissões, não uma classificação oficial. Por isso o nível aparece com a etiqueta {base.tag("derivado")} em todo o documento.</p>
</div>"""
    return Pagina("", corpo)


def paginas_indice(camadas, pagina_de):
    n_tab = len(todas_tabelas(camadas))
    cab = cabecalho("Índice", f'<span class="m">{n_tab} tabelas em {len(camadas)} camadas,</span> '
                              f'com a página da ficha de cada uma.')
    cap1 = base.ALTURA_UTIL - cab.altura - base.ESPACO_BLOCOS
    cap2 = base.ALTURA_UTIL
    larg = min(LARG_INDICE)
    grupos = [(c, [item_indice(t["nome"], t["nivel"], pagina_de.get(t["nome"], 0), larg) for t in c["tabelas"]])
              for c in camadas]
    alt_cam, margem_cam = 25, 14

    def titulo(c, primeiro_da_coluna, cont=False):
        estilo = "" if primeiro_da_coluna else f' style="margin-top:{margem_cam}px"'
        nome = esc(c["nome"]) + (" (continuação)" if cont else "")
        return (f'<div class="ind-cam"{estilo}><span class="v">{c["numero"]:02d}</span>{nome}</div>',
                alt_cam + (0 if primeiro_da_coluna else margem_cam))

    def distribuir(fator):
        """Enche as colunas de cima para baixo (3 por página). Um título nunca fica sem o 1º item."""
        paginas = [[[]]]
        usados = [0]

        def cap():
            return (cap1 if len(paginas) == 1 else cap2) * fator

        def nova_coluna():
            if len(paginas[-1]) == 3:
                paginas.append([[]])
            else:
                paginas[-1].append([])
            usados.append(0)

        for c, itens in grupos:
            for k, (html, h) in enumerate(itens):
                vazia = not paginas[-1][-1]
                precisa = h + (titulo(c, vazia)[1] if (k == 0 or vazia) else 0)
                if not vazia and usados[-1] + precisa > cap():
                    nova_coluna()
                    vazia = True
                if k == 0 or vazia:
                    th, hh = titulo(c, vazia, cont=k > 0)
                    paginas[-1][-1].append((th, hh))
                    usados[-1] += hh
                paginas[-1][-1].append((html, h))
                usados[-1] += h
        maior = max(sum(h for _, h in col) for pg in paginas for col in pg)
        return paginas, maior

    paginas, _ = distribuir(1.0)
    alvo = len(paginas)
    baixo, alto = 0.3, 1.0  # equilibra as colunas: menor fator que mantém o mesmo nº de páginas
    for _ in range(30):
        meio = (baixo + alto) / 2
        if len(distribuir(meio)[0]) == alvo:
            alto = meio
        else:
            baixo = meio
    paginas, _ = distribuir(alto)
    saida = []
    for i, pg in enumerate(paginas):
        colunas = [[base.Bloco("".join(h for h, _ in col), sum(a for _, a in col))] if col else [] for col in pg]
        colunas += [[] for _ in range(3 - len(colunas))]
        faixa = base.FaixaColunas(colunas, LARG_INDICE, gap=GAP_INDICE)
        blocos = [cab, faixa] if i == 0 else [faixa]
        partes, _ = base.paginar(blocos)
        if len(partes) != 1:
            raise ValueError("índice: coluna maior que a página")
        saida.append(Pagina("", base.abre(43 + i, True) + "\n" + conteudo(partes[0])))
    return saida


def pagina_abertura(c, pagina_de):
    n = len(c["tabelas"])
    itens = [item_indice(t["nome"], t["nivel"], pagina_de.get(t["nome"], 0), 440 - 48) for t in c["tabelas"]]
    altura = 44 + 26 + sum(h for _, h in itens)
    topo = 236 if 236 + altura <= 700 else max(118, 750 - altura)
    vidro = (f'<div class="vidro" style="left:600px;top:{topo}px;width:440px">\n'
             f'  <h3>Camada {c["numero"]:02d} · {n} tabela{"s" if n != 1 else ""}</h3>\n  {"".join(h for h, _ in itens)}\n</div>')
    titulo = c["nome"]  # o número da camada vai no título do vidro
    corpo = base.pagina_escura(titulo, c["descricao"], vidro, seed=100 + 7 * c["numero"],
                               arvores=arvores_lado(c["numero"]))
    return Pagina("escura", corpo)


def paginas_fichas(c, badges):
    blocos = [ficha(t, badges) for t in c["tabelas"]]
    # alterna a faixa creme cheia e a de 703px, como a referência
    return paginas_claras(blocos, seed=200 + 10 * c["numero"], cheio=lambda i: i % 2 == 1)


def paginas_pii(camadas, pagina_de):
    linhas_pii = [(t, c) for t in todas_tabelas(camadas) for c in t["colunas"] if c["pii"]]
    n_tab = len({t["nome"] for t, _ in linhas_pii})
    cab = cabecalho(f'Mapa de PII {base.tag("derivado")}',
                    f'<span class="m">{len(linhas_pii)} colunas PII em {n_tab} tabelas,</span> '
                    f'com o nível e a regra de acesso de cada uma.')
    cols = [("Tabela", 168), ("Coluna", 140), ("Tipo", 96), ("Nível", 100), ("Regra de acesso", 424), ("Pág.", 52)]
    w = dict(cols)

    def montar(agrupar):
        saida, anterior = [], None
        for t, c in linhas_pii:
            mesma = agrupar and t["nome"] == anterior
            regra = '<span class="cinza">a mesma da linha acima</span>' if mesma else prosa(regra_de_acesso(t["permissoes"]))
            texto_regra = "a mesma da linha acima" if mesma else regra_de_acesso(t["permissoes"])
            html = (f'<tr><td class="mono">{quebravel(t["nome"])}</td><td class="mono">{quebravel(c["nome"])}</td>'
                    f'<td class="mono">{esc(c["tipo"])}</td><td>{base.tag(c["nivel"])}</td><td>{regra}</td>'
                    f'<td class="v">{pagina_de.get(t["nome"], 0)}</td></tr>')
            n = max(linhas_quebravel(t["nome"], w["Tabela"] - 12, F_MONO_TAB),
                    linhas_quebravel(c["nome"], w["Coluna"] - 12, F_MONO_TAB),
                    linhas(texto_regra, w["Regra de acesso"] - 12, F_TAB))
            saida.append((html, base.altura_linha_tabela(n, compacta=True)))
            anterior = t["nome"]
        return saida

    # a regra só é omitida nas linhas seguintes da mesma tabela se tudo couber numa página
    linhas_t = montar(agrupar=True)
    cabe = (cab.altura + base.ESPACO_BLOCOS + ALT_ROT + base.ALT_THEAD_COMPACTA + sum(h for _, h in linhas_t)
            <= base.ALTURA_UTIL)
    if not cabe:
        linhas_t = montar(agrupar=False)
    tabela = base.TabelaPaginavel(
        thead_html=thead_fixo(cols, a_direita=("Pág.",)), linhas=linhas_t,
        titulo_html='<div class="rot-sec ficha-rot">Colunas PII</div>', titulo_altura=ALT_ROT,
        classe_tabela="compacta fixa", nome="pii")
    texto_nota = (
        "PII marcada pelo nome da coluna, só nas tabelas do catálogo: nome_usuario, email_usuario, senha_hash, "
        "data_nascimento, cpf e url_avatar onde aparecerem; cep, bairro, logradouro, numero e complemento em "
        "tb_enderecos; numero_contato em tb_telefones. Dados de pessoa jurídica (CNPJ, contato de cooperativa ou "
        "de condomínio) não entram. Coluna PII fica no mínimo RESTRITO, e senha_hash, CONFIDENCIAL. A regra de "
        "acesso repete as permissões da tabela no catálogo: perfil, badge e detalhe.")
    nota = base.Bloco(f'<p class="nota" style="width:860px">{base.tag("derivado")} {esc(texto_nota)}</p>',
                      9 + alt(linhas("DERIVADO " + texto_nota, 860, 10.5), 15) + 4)
    return paginas_claras([cab, tabela, nota], seed=47)


def pagina_final():
    passos = [
        'Se o HTML de origem mudar: <span class="v">python documentos/extrair_catalogo.py</span>. '
        'Reextrai <span class="v">dados/catalogo.json</span> e lista as divergências com o schema.',
        '<span class="v">python documentos/gerar_documentos.py</span> gera o HTML e o PDF; '
        'com <span class="v">--sem-pdf</span>, só o HTML.',
        'Dependências: <span class="v">pip install -r requirements.txt</span> e '
        '<span class="v">python -m playwright install chromium</span>.',
    ]
    direita = ('<div class="vidro" style="left:600px;top:130px;width:440px">\n  <h3>Passo a passo</h3>\n'
               '  <ol class="passos">' + "".join(f"<li>{p}</li>" for p in passos) + '</ol>\n</div>\n'
               '<div class="vidro" style="left:600px;top:450px;width:440px">\n  <h3>Backup e recuperação</h3>\n'
               '  <p>Os procedimentos estão em <span class="v">documentos/backup_e_recuperacao.pdf</span> e os '
               'scripts em <span class="v">scripts/backup/</span>: <span class="v">backup.sh</span>, '
               '<span class="v">restore.sh</span>, <span class="v">backup.ps1</span> e '
               '<span class="v">restore.ps1</span>.</p>\n</div>')
    lead = "Comandos a partir da raiz do repositório. O catálogo sai sempre do HTML de origem e do schema SQL."
    return Pagina("escura", base.pagina_escura("Para regerar este catálogo", lead, direita, seed=53,
                                               arvores=arvores_lado(12)))


def paginas_catalogo(catalogo, camadas, div, pagina_de):
    """Todas as páginas depois da capa, na ordem. pagina_de: tabela -> página da ficha (0 = ainda sem número)."""
    paginas = [pagina_como_ler(catalogo, camadas)]
    paginas += paginas_camadas_perfis(catalogo, camadas)
    paginas += [pagina_resumo(camadas, div), pagina_matriz(camadas)]
    paginas += paginas_indice(camadas, pagina_de)
    for c in camadas:
        paginas.append(pagina_abertura(c, pagina_de))
        paginas += paginas_fichas(c, catalogo["badges"])
    paginas += paginas_pii(camadas, pagina_de)
    paginas.append(pagina_final())
    return paginas


def gerar_catalogo():
    catalogo = extrair_catalogo.carregar_catalogo()
    schema = extrair_catalogo.ler_schema()
    camadas = montar_modelo(catalogo, schema)
    div = extrair_catalogo.divergencias(catalogo, schema)

    def numeracao(paginas):  # a capa é a página 1
        return {nome: i + 2 for i, p in enumerate(paginas) for nome in p.fichas}

    # duas passadas: a 1ª descobre em que página cada ficha começa; a 2ª escreve os números
    pagina_de = numeracao(paginas_catalogo(catalogo, camadas, div, {}))
    paginas = paginas_catalogo(catalogo, camadas, div, pagina_de)
    if numeracao(paginas) != pagina_de or len(pagina_de) != len(todas_tabelas(camadas)):
        raise RuntimeError("a paginação mudou entre as duas passadas")

    doc = base.Documento(CAB_CATALOGO)
    doc.capa(capa_catalogo(camadas, date.today().strftime("%d/%m/%Y")))
    for p in paginas:
        doc.pagina(p.classes, p.corpo)
    return "catalogo_dados.html", doc.html("Catálogo de dados · EcoCiente", CSS), doc.numero_atual


# ═════════════ linha de comando ═════════════
DOCUMENTOS = [gerar_catalogo]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gera os documentos de documentos/ (HTML e PDF).")
    ap.add_argument("--sem-pdf", action="store_true", help="só grava os HTML, sem converter para PDF")
    args = ap.parse_args(argv)

    gerados = []
    for gerar in DOCUMENTOS:
        nome, html, n = gerar()
        caminho = AQUI / nome
        caminho.write_text(html, encoding="utf-8", newline="\n")
        gerados.append((caminho, n))

    if args.sem_pdf:
        for caminho, n in gerados:
            print(f"ok: documentos/{caminho.name} ({n} páginas)")
        return 0

    try:
        with base.Conversor() as conversor:
            for caminho, n in gerados:
                pdf = caminho.with_suffix(".pdf")
                paginas = conversor.converter(caminho, pdf)
                if conversor.avisos:
                    print(f"erro: problemas em documentos/{pdf.name}:", file=sys.stderr)
                    for aviso in conversor.avisos:
                        print(f"  - {aviso}", file=sys.stderr)
                    return 1
                if paginas != n:
                    print(f"erro: documentos/{pdf.name} tem {paginas} páginas; o gerador emitiu {n}.",
                          file=sys.stderr)
                    return 1
                print(f"ok: documentos/{pdf.name} ({paginas} páginas)")
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
