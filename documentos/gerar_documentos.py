"""Gera os documentos de documentos/ em HTML e converte cada um para PDF (Playwright/Chromium).

Uso, a partir da raiz do repositório:
    python documentos/gerar_documentos.py            # HTML + PDF
    python documentos/gerar_documentos.py --sem-pdf  # só HTML

Cada documento tem uma função gerar_*() que devolve (nome_arquivo_html, html, n_paginas);
main() grava os HTML e converte todos com um único Chromium.
"""
import argparse
import json
import re
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
F_PERM, L_PERM = 11, 15  # .perm (legenda dos badges)
F_LINHA, L_LINHA = 11, 15  # .ficha-linha (permissões, FKs)
F_MONO_LINHA = 11 * 0.92  # .v dentro de .ficha-linha
LARGURA_FICHA = 980
ALT_FICHA_TOPO = 1.5 + 12  # régua e padding de .ficha
ALT_FICHA_NOME = 26  # .ficha-nome (.v 20/26)
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
    return base.Bloco(f'<div class="rot-sec ficha-rot">{rotulo}</div>{html}', ALT_ROT + altura)


def secao_lista(rotulo, textos, largura):
    """Lista com losango (texto verbatim do catálogo), ou "—" em cinza se vazia."""
    if not textos:
        return secao(rotulo, '<p class="ficha-vazio cinza">—</p>', L_FICHA)
    html = '<ul class="lista ficha-lista">' + "".join(f"<li>{prosa(t)}</li>" for t in textos) + "</ul>"
    altura = sum(alt(linhas(t, largura - 14, F_FICHA), L_FICHA) for t in textos) + 7 * (len(textos) - 1)
    return secao(rotulo, html, altura)


def rotulo_linha(rotulo):
    """Rótulo no estilo .rot (caixa alta, 800, 0,07 em) no início de uma linha corrida, e seus segmentos."""
    return (f'<span class="rot-sec">{rotulo}</span> ',
            [seg(rotulo.upper(), F_LINHA, 800, espacamento=0.07), seg(" ", F_LINHA)])


def linha_permissoes(permissoes, badges):
    """Uma linha de largura total: perfil em negrito, badge legível e o detalhe em cinza."""
    html, segs = rotulo_linha("Permissões")
    partes = []
    for i, p in enumerate(permissoes):
        texto = badge_legivel(p["badge"], badges)
        detalhe = f' <span class="cinza">({prosa(p["detalhe"])})</span>' if p["detalhe"] else ""
        partes.append(f'<b>{esc(p["perfil"])}</b>&nbsp;{esc(texto)}{detalhe}')
        if i:
            segs.append(seg(" · ", F_LINHA))
        segs += [seg(p["perfil"], F_LINHA, 800), seg(" " + texto, F_LINHA)]
        if p["detalhe"]:
            segs.append(seg(f' ({p["detalhe"]})', F_LINHA))
    html += '<span class="cinza"> · </span>'.join(partes)
    if any(p["badge"].endswith("*") for p in permissoes):
        html += f'<span class="cinza"> — * {esc(badges["*"])}</span>'
        segs.append(seg(f' — * {badges["*"]}', F_LINHA))
    return f'<p class="ficha-linha">{html}</p>', contar_linhas(unidades(segs), LARGURA_FICHA)


def linha_fks(fks):
    """Uma linha de largura total: 'coluna -> tabela.coluna' em .v, separados por ' · '."""
    html, segs = rotulo_linha("FKs de saída")
    if not fks:
        html += '<span class="cinza">nenhuma</span>'
        segs.append(seg("nenhuma", F_LINHA))
    for i, (o, t, d) in enumerate(fks):
        if i:
            html += '<span class="cinza"> · </span>'
            segs.append(seg(" · ", F_LINHA))
        # quebra nos espaços e depois do '.', para não partir nome de coluna
        html += f'<span class="v">{esc(o)} -&gt; {esc(t)}.<wbr>{esc(d)}</span>'
        segs.append(seg(f"{o} -> {t}.{d}", F_MONO_LINHA, mono=True, quebra="."))
    return f'<p class="ficha-linha">{html}</p>', contar_linhas(unidades(segs), LARGURA_FICHA)


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
    """Ficha da tabela: nome e etiquetas; descrição; linha de permissões; linha de FKs; faixa de 2 colunas
    com regras e observações (omitida se ambas vazias); tabela das colunas. Tudo antes da tabela vai no
    título da TabelaPaginavel, para a ficha só começar numa página se couberem também 3 linhas."""
    nome = t["nome"]
    perm_html, n_perm = linha_permissoes(t["permissoes"], badges)
    fks_html, n_fks = linha_fks(t["fks"])
    html = (f'<div class="ficha" id="{esc(nome)}">'
            f'<div class="ficha-nome"><span class="v">{esc(nome)}</span>{tag_neutra(t["tipo"])}'
            f'{base.tag(t["nivel"])}{base.tag("derivado")}</div>'
            f'<p class="ficha-desc">{prosa(t["descricao"])}</p>{perm_html}{fks_html}')
    altura = (ALT_FICHA_TOPO + ALT_FICHA_NOME + 6 + alt(linhas(t["descricao"], LARGURA_FICHA, F_CORPO), L_CORPO)
              + 8 + alt(n_perm, L_LINHA) + 4 + alt(n_fks, L_LINHA))
    if t["regras"] or t["observacoes"]:
        faixa = base.FaixaColunas([[secao_lista("Regras de negócio", t["regras"], 471)],
                                   [secao_lista("Observações", t["observacoes"], 472)]], [471, 472], gap=37)
        html += f'<div style="margin-top:14px">{faixa.html}</div>'
        altura += 14 + faixa.altura
    rotulo = f'Colunas de <span class="v">{esc(nome)}</span>'
    html += f'<div class="rot-sec ficha-rot" style="margin-top:14px">{rotulo}</div></div>'
    altura += 14 + ALT_ROT
    linhas_tab = [linha_coluna(c) for c in t["colunas"]]
    return base.TabelaPaginavel(
        thead_html=thead_fixo(COLS_FICHA), linhas=linhas_tab, titulo_html=html, titulo_altura=math.ceil(altura),
        classe_tabela="compacta fixa", minimo_linhas=3, id=nome, nome=nome,
        titulo_continuacao_html=f'<div class="rot-sec ficha-rot">{rotulo} (continuação)</div>',
        titulo_continuacao_altura=ALT_ROT)


def cabecalho(titulo_html, sub_html, largura_sub=643):
    """h2 + p.sub de uma linha (bloco de abertura de página clara)."""
    return base.Bloco(f'<h2>{titulo_html}</h2><p class="sub" style="width:{largura_sub}px">{sub_html}</p>',
                      base.ALT_TITULO_H2 + ALT_SUB)


ALTURA_FAIXA = 84  # faixa .topo das páginas paginadas: termina acima do conteúdo (top 100)


def paginas_claras(blocos, seed):
    """Pagina os blocos no contêiner padrão; cada página tem a faixa .topo curta e a arte do topo."""
    paginas, onde = base.paginar(blocos)
    saida = []
    for i, pedacos in enumerate(paginas):
        fichas = [nome for nome, j in onde.items() if j == i]
        saida.append(Pagina("", base.abre(seed + i, True, ALTURA_FAIXA) + "\n" + conteudo(pedacos), fichas))
    return saida


# ═════════════ catálogo: páginas ═════════════
def capa_catalogo(camadas, hoje):
    meta = ["<b>EcoCiente</b> PostgreSQL 14+", f"gerado em {hoje}",
            f"{len(todas_tabelas(camadas))} tabelas · {len(camadas)} camadas", "fonte: dados/catalogo.json + sql/"]
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
               (f"O schema SQL tem {n_schema}: <b>{len(fora)}</b> ficam fora do catálogo." if fora
                else f"Cobre as {n_schema} tabelas do schema SQL e do Data Mart.")),
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
    item_cobertura = (
        f'<li>Que cubra todo o schema: {len(fora)} tabelas ficam fora.<span style="display:block;margin-top:4px;'
        f'font-size:10.5px;line-height:14px">{nomes_fora}.</span></li>' if fora else
        "<li>Nada sobre o conteúdo das tabelas: o catálogo descreve a estrutura, as regras e o acesso, não os dados.</li>")
    corpo = f"""{base.abre(37, True)}
<div class="a" style="left:60px;top:104px;width:980px"><div class="grande">O resumo em cinco números</div><p class="sub" style="margin-top:14px">Cada cartão é calculado do catálogo e do schema SQL. As páginas seguintes detalham tabela por tabela.</p></div>
<div class="cinco">
  {(chr(10) + "  ").join(cartoes)}
</div>
<div class="nao">
  <div class="sig"><div class="rot">O que este catálogo não afirma</div><p>Três limites que valem para todo o documento.</p></div>
  <ul class="lista">
    <li>Que nível de acesso e PII sejam oficiais: os dois são derivados por regra fixa, das permissões do catálogo e do nome da coluna.</li>
    <li>Colunas, tipos, chaves e descrições de coluna vêm do schema SQL, não do texto do catálogo.</li>
    {item_cobertura}
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
  <div class="rot-sec ficha-rot">Como o nível é calculado</div>
  <p>Pelas permissões de cada tabela no catálogo, contando só os perfis de negócio: {esc(perfis)}. Acesso marcado com * conta como restrito.</p>
</div>
<div class="a c3 corpo" style="top:630px">
  <div class="rot-sec ficha-rot">Limite</div>
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
        saida.append(Pagina("", base.abre(43 + i, True, ALTURA_FAIXA) + "\n" + conteudo(partes[0])))
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
    return paginas_claras([ficha(t, badges) for t in c["tabelas"]], seed=200 + 10 * c["numero"])


def paginas_pii(camadas, pagina_de):
    linhas_pii = [(t, c) for t in todas_tabelas(camadas) for c in t["colunas"] if c["pii"]]
    n_tab = len({t["nome"] for t, _ in linhas_pii})
    cab = cabecalho(f'Mapa de PII {base.tag("derivado")}',
                    f'<span class="m">{len(linhas_pii)} colunas PII em {n_tab} tabelas,</span> '
                    f'com o nível e a regra de acesso de cada uma.')
    cols = [("Tabela", 168), ("Coluna", 140), ("Tipo", 96), ("Nível", 100), ("Regra de acesso", 424), ("Pág.", 52)]
    w = dict(cols)

    # cada tabela vira um grupo indivisível de <tr>: a regra (verbatim) aparece uma vez, em rowspan,
    # e o grupo nunca é cortado por uma quebra de página
    grupos = {}
    for t, c in linhas_pii:
        grupos.setdefault(t["nome"], (t, []))[1].append(c)
    linhas_t = []
    for t, cols_t in grupos.values():
        regra = regra_de_acesso(t["permissoes"])
        trs, soma = [], 0
        for i, c in enumerate(cols_t):
            celula_regra = (f'<td class="regra" rowspan="{len(cols_t)}">{prosa(regra)}</td>' if i == 0 else "")
            trs.append(f'<tr><td class="mono">{quebravel(t["nome"])}</td><td class="mono">{quebravel(c["nome"])}</td>'
                       f'<td class="mono">{esc(c["tipo"])}</td><td>{base.tag(c["nivel"])}</td>{celula_regra}'
                       f'<td class="v">{pagina_de.get(t["nome"], 0)}</td></tr>')
            n = max(linhas_quebravel(t["nome"], w["Tabela"] - 12, F_MONO_TAB),
                    linhas_quebravel(c["nome"], w["Coluna"] - 12, F_MONO_TAB))
            soma += base.altura_linha_tabela(n, compacta=True)
        alt_regra = base.altura_linha_tabela(linhas(regra, w["Regra de acesso"] - 12, F_TAB), compacta=True)
        linhas_t.append(("".join(trs), max(soma, alt_regra)))
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
        'Descrições, permissões e regras de negócio ficam em <span class="v">dados/catalogo.json</span>; '
        'tipos, chaves e colunas vêm de <span class="v">sql/</span>.',
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
    lead = "Comandos a partir da raiz do repositório. O catálogo sai sempre de dados/catalogo.json e do schema SQL."
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


# ═════════════ backup e recuperação ═════════════
CAB_BACKUP = "Backup e recuperação · EcoCiente · PostgreSQL"


def pt(valor, casas=1):
    """Número em pt-BR: 28.1 -> '28,1'."""
    return f"{valor:.{casas}f}".replace(".", ",")


def v(texto):
    return f'<span class="v">{esc(texto)}</span>'


def bloco_rot(texto):
    return base.Bloco(f'<div class="rot-sec ficha-rot">{texto}</div>', ALT_ROT)


def junto(*blocos):
    """Blocos indivisíveis num só (um título nunca fica sozinho no fim da página)."""
    html = "".join(f'<div style="margin-top:{base.ESPACO_BLOCOS if i else 0}px">{b.html}</div>' for i, b in enumerate(blocos))
    return base.Bloco(html, sum(b.altura for b in blocos) + base.ESPACO_BLOCOS * (len(blocos) - 1))


def bloco_para(html, plano, largura=980, fonte=F_CORPO, altura_linha=L_CORPO):
    return base.Bloco(f'<p class="corpo" style="width:{largura}px">{html}</p>',
                      alt(linhas(plano, largura, fonte), altura_linha) + 2)


def bloco_formula(linhas_cmd, titulo=None):
    """Comandos em .formula, num painel branco; uma linha por elemento (sem quebra automática)."""
    for linha in linhas_cmd:
        if len(linha) > 128:
            raise ValueError(f"comando longo demais para uma linha da .formula: {linha[:40]}…")
    cab = f'<div class="rot-sec ficha-rot" style="margin:0 0 6px">{esc(titulo)}</div>' if titulo else ""
    html = (f'<div style="background:var(--creme);border-radius:10px;padding:12px 16px">{cab}'
            f'<pre class="formula">{esc(chr(10).join(linhas_cmd))}</pre></div>')
    return base.Bloco(html, 24 + (ALT_ROT - 8 + 6 if titulo else 0) + 17 * len(linhas_cmd))


def bloco_passos(itens, largura=980):
    """ol.passos; itens: [(html, texto_plano)]."""
    html = '<ol class="passos">' + "".join(f"<li>{h}</li>" for h, _ in itens) + "</ol>"
    altura = sum(alt(linhas(p, largura - 30, F_CORPO), L_CORPO) for _, p in itens) + 11 * (len(itens) - 1) + 2
    return base.Bloco(html, altura)


def tabela_simples(colunas, linhas_dados, rotulo, nome, mono=(), soma=False, a_direita=()):
    """colunas: [(nome, largura)]; linhas_dados: [[texto, ...]] (texto simples; colunas em `mono` em JetBrains)."""
    saida = []
    for k, cels in enumerate(linhas_dados):
        tds, n = "", 1
        for (cn, w), t in zip(colunas, cels):
            if cn in mono:
                tds += f'<td class="mono">{esc(t)}</td>'
                n = max(n, contar_linhas(unidades([seg(t, F_MONO_TAB, mono=True, quebra=" _/")]), w - 12))
            else:
                tds += f'<td class="v">{esc(t)}</td>' if cn in a_direita else f"<td>{esc(t)}</td>"
                n = max(n, linhas(t, w - 12, F_TAB))
        ultima = soma and k == len(linhas_dados) - 1
        saida.append((f'<tr class="soma">{tds}</tr>' if ultima else f"<tr>{tds}</tr>",
                      base.altura_linha_tabela(n, compacta=True)))
    return base.TabelaPaginavel(
        thead_html=thead_fixo(colunas, a_direita=a_direita), linhas=saida,
        titulo_html=f'<div class="rot-sec ficha-rot">{rotulo}</div>', titulo_altura=ALT_ROT,
        classe_tabela="compacta fixa", nome=nome, minimo_linhas=2)


def capa_backup(med, hoje):
    pg = re.search(r"postgres:(\d+)", med["ambiente"]).group(1)
    meta = ["<b>EcoCiente</b> md-populador-pgsql", f"gerado em {hoje}", "scripts/backup/",
            f"testado em PostgreSQL {pg}"]
    return base.pagina_capa("EcoCiente · PostgreSQL", "Backup e<br>recuperação", meta, seed=71)


def pagina_resumo_backup(med):
    t_b, t_r = pt(med["tempo_backup_s"]), pt(med["tempo_restauracao_s"])
    cartoes = [
        cartao("g-rosa", "RPO", '24<span class="u">h</span>', "perda máxima de dados",
               "No pior caso perde-se o que foi escrito desde o último dump diário.", ["premissa"]),
        cartao("g-verde", "RTO", '1<span class="u">h</span>', "meta para voltar a operar",
               "Criar o serviço, restaurar, conferir e trocar ECOCIENTE_DSN. A restauração em si foi medida em segundos.",
               ["premissa"]),
        cartao("g-azul", "Frequência", '<span class="menor">DIÁRIA</span>', "dump completo",
               "pg_dump -Fc todo dia, e --schema-only a cada mudança de schema.", ["premissa"]),
        cartao("g-rosa", "Retenção", "7 + 4", "diários + semanais",
               "Configurável por ECOCIENTE_RETENCAO_DIARIOS e ECOCIENTE_RETENCAO_SEMANAIS.", ["premissa"]),
        cartao("g-verde", "Tempos medidos", f'{t_b}<span class="u">s</span><br>{t_r}<span class="u">s</span>',
               "backup · restauração",
               f"Escala {med['escala_populador']}: banco de {pt(med['tamanho_banco_mb'])} MB, "
               f"dump de {pt(med['tamanho_dump_mb'])} MB.", ["medido"]),
    ]
    corpo = f"""{base.abre(73, True)}
<div class="a" style="left:60px;top:104px;width:980px"><div class="grande">O resumo em cinco números</div><p class="sub" style="margin-top:14px">Metas definidas para o projeto e os tempos de um teste real. Cada etiqueta diz qual é qual.</p></div>
<div class="cinco">
  {(chr(10) + "  ").join(cartoes)}
</div>
<div class="nao">
  <div class="sig"><div class="rot">O que este documento não afirma</div><p>Três limites que valem para todo o documento.</p></div>
  <ul class="lista">
    <li>Que os tempos valham para produção: foram medidos na escala {esc(med["escala_populador"])}, num PostgreSQL local em Docker, sem rede. Contra o Neon entram latência e o tamanho real.</li>
    <li>Que RPO, RTO, frequência e retenção sejam SLA do provedor: são metas definidas aqui.</li>
    <li>O que o provedor gerenciado oferece (backups automáticos, PITR) depende do plano contratado. Confira no console antes de contar com isso.</li>
  </ul>
</div>"""
    return Pagina("", corpo)


def paginas_estrategia():
    cab = cabecalho("Estratégia", '<span class="m">Dump lógico diário, guardado fora do banco,</span> mais o que o provedor já faz.', 980)
    cols = [("O quê", 130), ("Comando", 250), ("Quando", 230), ("Onde fica", 370)]
    tab = tabela_simples(cols, [
        ["Banco inteiro", "pg_dump -Fc", "diário", "backups/ecociente_AAAAMMDD_HHMMSS.dump"],
        ["Só o schema", "pg_dump --schema-only", "a cada mudança em sql/", "….schema.sql, com o mesmo carimbo"],
        ["Retenção", "backup.sh / backup.ps1", "depois de cada backup bem-sucedido", "7 diários + 4 semanais"],
        ["Cópia externa", "cópia do arquivo", "diária",
         "fora do servidor do banco: outra máquina ou armazenamento em nuvem da equipe; nunca só no mesmo serviço do banco"],
    ], "O que é feito", "estrategia", mono=("Comando",))
    p1 = ("O sistema aceita Neon e Aiven (a conexão é uma DSN PostgreSQL comum); o ambiente de referência é o Neon, plano free, com "
          "limite de 1 GB. Os recursos de recuperação do provedor dependem do plano; o console diz o que o free cobre. "
          "Mantemos o backup lógico mesmo assim, por quatro motivos.")
    motivos = [
        ("<b>Independe da conta.</b> Os backups do provedor em geral somem junto com o serviço; o dump fica com a equipe.",
         "Independe da conta. Os backups do provedor em geral somem junto com o serviço; o dump fica com a equipe."),
        ("<b>É portátil.</b> Serve entre provedores e versões: Neon, Aiven ou PostgreSQL local.",
         "É portátil. Serve entre provedores e versões: Neon, Aiven ou PostgreSQL local."),
        ("<b>Restaura uma tabela só,</b> sem voltar o serviço inteiro no tempo.",
         "Restaura uma tabela só, sem voltar o serviço inteiro no tempo."),
        ("<b>Dá para testar todo mês</b> num PostgreSQL local, sem tocar na produção.",
         "Dá para testar todo mês num PostgreSQL local, sem tocar na produção."),
    ]
    return paginas_claras([cab, tab, junto(bloco_rot("Por que manter o backup lógico"), bloco_para(esc(p1), p1), bloco_passos(motivos))], seed=75)


def paginas_fazer_backup():
    cab = cabecalho("Como fazer backup", '<span class="m">Um comando,</span> do <span class="v">backup.sh</span> ou do <span class="v">backup.ps1</span>.', 980)
    passos = [
        (f'Defina {v("ECOCIENTE_DSN")} no ambiente ou no {v(".env")} (o script lê só essa linha; veja {v(".env.example")}).',
         "Defina ECOCIENTE_DSN no ambiente ou no .env (o script lê só essa linha; veja .env.example)."),
        (f'Tenha o {v("pg_dump")} 16 ou mais novo no PATH, ou aponte {v("PG_BIN")} para a pasta dele. A versão deve ser igual ou maior que a do servidor.',
         "Tenha o pg_dump 16 ou mais novo no PATH, ou aponte PG_BIN para a pasta dele. A versão deve ser igual ou maior que a do servidor."),
        ("Rode o script (comandos abaixo), da raiz do repositório.", "Rode o script (comandos abaixo), da raiz do repositório."),
        (f'Confira a linha {v("ok:")} e as linhas {v("mantido:")} e {v("apagado:")} da retenção.',
         "Confira a linha ok: e as linhas mantido: e apagado: da retenção."),
        ("Copie o .dump para fora do servidor do banco.", "Copie o .dump para fora do servidor do banco."),
    ]
    p_erro = ("Se o pg_dump falhar, o script imprime ERRO: pg_dump falhou (código N). Nenhum backup novo foi gravado. "
              "e sai com código 1. Não fica arquivo parcial.")
    cols = [("Variável", 230), ("Padrão", 200), ("Para quê", 550)]
    tab = tabela_simples(cols, [
        ["ECOCIENTE_DSN", "(obrigatória)", "conexão com o banco; também lida da linha ECOCIENTE_DSN= do .env"],
        ["ECOCIENTE_BACKUP_DIR", "<raiz>/backups", "pasta onde os arquivos são gravados"],
        ["ECOCIENTE_RETENCAO_DIARIOS", "7", "quantos dumps mais novos manter; deve ser 1 ou mais"],
        ["ECOCIENTE_RETENCAO_SEMANAIS", "4", "quantas semanas anteriores manter, com o dump mais novo de cada uma; 0 desliga"],
        ["PG_BIN", "(PATH)", "pasta do pg_dump, se não estiver no PATH"],
    ], "Variáveis de ambiente", "variaveis", mono=("Variável", "Padrão"))
    return paginas_claras([
        cab, bloco_passos(passos),
        bloco_formula(["scripts/backup/backup.sh"], "Linux, macOS e Git Bash"),
        bloco_formula([".\\scripts\\backup\\backup.ps1"], "Windows (PowerShell)"),
        bloco_para(esc(p_erro), p_erro), tab,
        junto(bloco_rot("Agendamento diário"),
              bloco_formula(["0 2 * * * cd /caminho/md-populador-pgsql && ECOCIENTE_DSN=... scripts/backup/backup.sh"], "cron (Linux)"),
              bloco_formula(['schtasks /Create /SC DAILY /ST 02:00 /TN "EcoCiente backup" ^',
                             '  /TR "powershell -NoProfile -File C:\\caminho\\md-populador-pgsql\\scripts\\backup\\backup.ps1"'],
                            "Agendador de Tarefas (Windows)")),
    ], seed=79)


def paginas_restaurar(med):
    cab = cabecalho("Como restaurar", '<span class="m">Banco inteiro, uma tabela</span> ou só a conferência por contagem.', 980)
    inteiro = [
        ("Crie um banco novo e vazio (no serviço novo ou num PostgreSQL local).", "Crie um banco novo e vazio (no serviço novo ou num PostgreSQL local)."),
        (f'Rode {v("restore.sh")} com o dump e a DSN do banco novo. Ele executa '
         f'{v("pg_restore --clean --if-exists --no-owner --no-privileges --exit-on-error")}.',
         "Rode restore.sh com o dump e a DSN do banco novo. Ele executa pg_restore --clean --if-exists --no-owner --no-privileges --exit-on-error."),
        (f'O script recusa um destino igual a {v("ECOCIENTE_DSN")}. Para restaurar por cima de propósito, exporte {v("ECOCIENTE_ALLOW_RESET=1")}.',
         "O script recusa um destino igual a ECOCIENTE_DSN. Para restaurar por cima de propósito, exporte ECOCIENTE_ALLOW_RESET=1."),
        (f'Confira com {v("--comparar")} (abaixo).', "Confira com --comparar (abaixo)."),
    ]
    tabela_p = ("Restaurar uma tabela só (pg_restore --data-only -t). Sem --truncar, linhas que já existem colidem com a chave "
                "primária. O --truncar não usa CASCADE: se outras tabelas referenciam a restaurada por FK, liste todas juntas "
                "com -t. O caminho mais seguro é restaurar o dump inteiro num banco novo e copiar as linhas de lá.")
    contagens = [[n, str(o), str(r)] for n, (o, r) in med["contagens"].items()]
    iguais = sum(o == r for o, r in med["contagens"].values())
    contagens.append([f"Contagens iguais: {iguais} de {len(contagens)}", "", ""])
    tab = tabela_simples([("Tabela", 400), ("Origem", 190), ("Restaurado", 190)], contagens,
                         "Contagens conferidas no teste", "contagens", mono=("Tabela",), soma=True,
                         a_direita=("Origem", "Restaurado"))
    texto_cmp = ("--comparar (no PowerShell, -Comparar) mostra origem × restaurado das 17 tabelas principais, marca "
                 "<-- DIVERGE e sai com código 1 se algo diferir. Precisa de ECOCIENTE_DSN apontando para a origem, "
                 "e a origem não pode ter mudado desde o backup. MEDIDO")
    html_cmp = (f'{v("--comparar")} (no PowerShell, {v("-Comparar")}) mostra origem × restaurado das 17 tabelas principais, '
                f'marca {v("<-- DIVERGE")} e sai com código 1 se algo diferir. Precisa de {v("ECOCIENTE_DSN")} apontando '
                f'para a origem, e a origem não pode ter mudado desde o backup. {base.tag("medido")}')
    return paginas_claras([
        cab, junto(bloco_rot("Banco inteiro, num banco novo"), bloco_passos(inteiro)),
        bloco_formula(["scripts/backup/restore.sh backups/ecociente_AAAAMMDD_HHMMSS.dump \\",
                       '  "postgres://usuario:senha@host:5432/ecociente_restaurado?sslmode=require"'], "Linux, macOS e Git Bash"),
        bloco_formula([".\\scripts\\backup\\restore.ps1 backups\\ecociente_AAAAMMDD_HHMMSS.dump `",
                       '  "postgres://usuario:senha@host:5432/ecociente_restaurado?sslmode=require"'], "Windows (PowerShell)"),
        junto(bloco_rot("Uma tabela isolada"), bloco_para(esc(tabela_p), tabela_p)),
        bloco_formula(['scripts/backup/restore.sh -t tb_cursos [--truncar] backups/ecociente_AAAAMMDD_HHMMSS.dump "<dsn_destino>"',
                       '.\\scripts\\backup\\restore.ps1 backups\\ecociente_AAAAMMDD_HHMMSS.dump "<dsn_destino>" -Tabela tb_cursos [-Truncar]']),
        junto(bloco_rot("Conferência por contagem"), bloco_para(html_cmp, texto_cmp)), tab,
    ], seed=83)


def paginas_falhas():
    cab = cabecalho("Recuperação de falhas", '<span class="m">Seis falhas previstas,</span> o que se vê e o que fazer.', 980)
    cols = [("Falha", 170), ("Sintoma", 300), ("Procedimento", 510)]
    nota = ("Nota: o ecociente_schema.sql aplica direto num banco vazio. Antes, o índice idx_esqueci_senha_usuario_id vinha antes do "
            "CREATE TABLE tb_recuperacoes_senha e o script falhava; o índice foi movido para depois da tabela.")
    tab = tabela_simples(cols, [
        ["Carga do populador interrompida", "python src/main.py para no meio (queda de conexão, timeout); as tabelas ficam com contagens parciais.",
         "O populador trunca e recarrega: rode de novo com a mesma escala e --force (ou ECOCIENTE_ALLOW_RESET=1)."],
        ["Schema corrompido", "relation … does not exist, colunas faltando, ou a checagem de schema de python ui.py acusa diferença.",
         "Banco novo; psql \"$ECOCIENTE_DSN\" -v ON_ERROR_STOP=1 -f sql/ecociente_schema.sql e depois -f sql/ecociente_datamart.sql, nessa ordem. Depois repopule ou restaure só os dados."],
        ["Data Mart inconsistente", "fato_postagens e fato_coletas com números diferentes do OLTP; dashboard desatualizado.",
         "CALL sp_carga_datamart(); (refresh completo)."],
        ["Exclusão acidental de dados", "linhas sumiram de uma tabela.", "Restauração da tabela a partir do último dump (página \"Como restaurar\")."],
        ["Falha na migração RPA", "a migração parou no meio ou deixou registros pela metade.",
         "Carga transacional, tb_migracao_ids_map (mapa legado para novo, que torna a nova execução idempotente) e reconciliação do repo md-rpa-integration."],
        ["Perda total do servidor", "serviço inacessível ou excluído.",
         "Restauração completa a partir do dump externo num serviço novo, conferência por contagem e troca de ECOCIENTE_DSN."],
    ], "Falha, sintoma e procedimento", "falhas")
    return paginas_claras([cab, tab, bloco_para(esc(nota), nota, fonte=11.5, altura_linha=16.5)], seed=87)


def paginas_checklist():
    cab = cabecalho("Teste de restauração mensal", '<span class="m">Todo mês,</span> na primeira semana, pelo responsável pelo banco.', 980)
    quem = "Quem executa: o responsável pelo banco (perfil DBA / Admin do catálogo de dados), com uma segunda pessoa conferindo o resultado."
    itens = [
        ("O último dump existe e tem menos de 24 h.", "O último dump existe e tem menos de 24 h."),
        ("O tamanho é coerente com o do mês anterior.", "O tamanho é coerente com o do mês anterior."),
        (f'Suba um PostgreSQL 16 local: {v("docker run --rm -d -p 15432:5432 -e POSTGRES_PASSWORD=teste postgres:16")}.',
         "Suba um PostgreSQL 16 local: docker run --rm -d -p 15432:5432 -e POSTGRES_PASSWORD=teste postgres:16."),
        ("Crie um banco novo e vazio nele.", "Crie um banco novo e vazio nele."),
        (f'Faça um backup novo e rode {v("restore.sh --comparar")} logo em seguida, para a origem não ter mudado.',
         "Faça um backup novo e rode restore.sh --comparar logo em seguida, para a origem não ter mudado."),
        ("Confira que as contagens são iguais (sem linha DIVERGE).", "Confira que as contagens são iguais (sem linha DIVERGE)."),
        (f'Aplique o {v(".schema.sql")} num banco vazio e confira que não dá erro.',
         "Aplique o .schema.sql num banco vazio e confira que não dá erro."),
        ("Anote os tempos de backup e de restauração e compare com o mês anterior.",
         "Anote os tempos de backup e de restauração e compare com o mês anterior."),
        ("Apague o banco de teste e confira que a retenção mantém 7 + 4 arquivos.",
         "Apague o banco de teste e confira que a retenção mantém 7 + 4 arquivos."),
    ]
    reg = tabela_simples([("Data", 160), ("Responsável", 300), ("Tempo de restauração", 280), ("Contagens ok?", 240)],
                         [["\u00a0", "", "", ""]] * 4, "Registro", "registro")
    return paginas_claras([cab, bloco_para(esc(quem), quem), bloco_passos(itens), reg], seed=91)


def pagina_como_medimos(med):
    amb = med["ambiente"].split(" (")[0].replace("Docker ", "")
    passos = [
        f"Contêiner {amb}.",
        "Schema e depois o Data Mart (o teste foi feito com o índice corrigido numa cópia; o arquivo do repositório já tem a correção).",
        f"Populador com --escala {med['escala_populador']} --force: {pt(med['tempo_populador_s'])} s.",
        "CALL sp_carga_datamart();",
        f"backup.sh dentro do contêiner: {pt(med['tempo_backup_s'])} s, dump de {pt(med['tamanho_dump_mb'])} MB.",
        f"restore.sh --comparar num banco novo (ecociente_restaurado): {pt(med['tempo_restauracao_s'])} s, 17 de 17 contagens iguais.",
    ]
    limites = [
        f"Escala {med['escala_populador']}, uma máquina local, uma execução, sem rede.",
        f"O banco tem {pt(med['tamanho_banco_mb'])} MB; o de produção será maior e os tempos crescem com ele.",
        "O tempo de restauração é só a etapa do pg_restore; o script inteiro, com as contagens, leva mais.",
        "Os scripts .ps1 foram validados de ponta a ponta no PowerShell 7 (em contêiner); no Windows PowerShell 5.1 só até a checagem do pg_dump.",
    ]
    corpo = f"""{base.abre(95, True)}
<div class="a c1 l1"><div class="grande">Como medimos</div><p class="sub" style="margin-top:14px"><span class="m">Um teste real,</span> num PostgreSQL 16 local.</p></div>
<div class="a c2 l1 corpo"><div class="rot-sec ficha-rot">Como o teste foi feito</div><ol class="passos">{"".join(f"<li>{esc(p)}</li>" for p in passos)}</ol></div>
<div class="a c3 l1 corpo"><div class="rot-sec ficha-rot">Limitações</div><ul class="lista">{"".join(f"<li>{esc(p)}</li>" for p in limites)}</ul></div>"""
    return Pagina("", corpo)


def pagina_final_backup():
    itens = [("scripts/backup/backup.sh", "e backup.ps1: geram o dump e o .schema.sql"),
             ("scripts/backup/restore.sh", "e restore.ps1: restauram e conferem"),
             ("backups/", "pasta dos dumps (ignorada pelo git)"),
             ("sql/ecociente_schema.sql", "e ecociente_datamart.sql: o schema, nessa ordem"),
             ("documentos/catalogo_dados.pdf", "o catálogo de dados"),
             ("python documentos/gerar_documentos.py", "regera este documento")]
    lis = "".join(f'<li><span class="v">{esc(a)}</span> {esc(b)}</li>' for a, b in itens)
    direita = ('<div class="vidro" style="left:600px;top:130px;width:440px">\n  <h3>Arquivos</h3>\n'
               f'  <ul class="lista">{lis}</ul>\n</div>')
    return Pagina("escura", base.pagina_escura("Onde está cada coisa", "Tudo sai do repositório: scripts, schema e este documento.",
                                               direita, seed=99, arvores=arvores_lado(7)))


def gerar_backup():
    med = json.loads((AQUI / "dados" / "medicoes_backup.json").read_text(encoding="utf-8"))
    paginas = [pagina_resumo_backup(med)]
    paginas += paginas_estrategia()
    paginas += paginas_fazer_backup()
    paginas += paginas_restaurar(med)
    paginas += paginas_falhas()
    paginas += paginas_checklist()
    paginas += [pagina_como_medimos(med), pagina_final_backup()]
    doc = base.Documento(CAB_BACKUP)
    doc.capa(capa_backup(med, date.today().strftime("%d/%m/%Y")))
    for p in paginas:
        doc.pagina(p.classes, p.corpo)
    return "backup_e_recuperacao.html", doc.html("Backup e recuperação · EcoCiente", CSS), doc.numero_atual


# ═════════════ linha de comando ═════════════
DOCUMENTOS = [gerar_catalogo, gerar_backup]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gera os documentos de documentos/ (HTML e PDF).")
    ap.add_argument("--sem-pdf", action="store_true", help="só grava os HTML, sem converter para PDF")
    args = ap.parse_args(argv)

    try:
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
