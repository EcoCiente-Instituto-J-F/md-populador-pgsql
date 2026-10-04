"""
ui.py

Tela do Populador EcoCiente: escolhe o tamanho da massa e a seed, confere o
banco de destino, roda o main.py mostrando o progresso e, no fim, monta um
painel só com números da inserção (linhas por tabela, tempo por etapa, tamanho).

Uso (a partir de src/):
    python ui.py
"""

import os
import queue
import random
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import messagebox, ttk

from psycopg2 import sql

from utils.helpers import colunas_esperadas, colunas_faltando, get_connection, target_description

AQUI = Path(__file__).resolve().parent
SCHEMA_SQL = AQUI.parent / "sql" / "ecociente_schema.sql"

# ==============================================================================
# DESIGN SYSTEM -- toda cor, fonte e espaço da tela sai daqui
# ==============================================================================

COR = dict(
    marca="#4f7942",          # verde da logo: ação principal, opção selecionada, barras dos gráficos
    marca_escura="#3f6335",   # verde pressionado
    noite="#0f1723",          # azul-noite da logo: painel lateral, log e texto principal
    noite_2="#1b2535",        # campos e botões sobre o painel lateral
    noite_borda="#2c3a4f",    # contorno e hover sobre o painel lateral
    fundo="#f4f6f2",          # fundo da área de conteúdo
    superficie="#ffffff",     # cartões, gráficos e tabela
    borda="#dde3d8",          # contorno de cartões; trilho da barra de progresso
    selecao="#dfe9da",        # linha selecionada na tabela
    texto="#0f1723",
    texto_2="#5b6470",        # rótulos e legendas
    claro="#ffffff",          # texto sobre noite/marca
    claro_2="#aab4c0",        # texto secundário sobre noite
    ok="#2f6b3a", erro="#b3261e",              # estados sobre fundo claro
    ok_claro="#9fd3a0", erro_claro="#ff9b93",  # os mesmos estados sobre noite
)
FONTE = dict(
    base=("Segoe UI", 10), forte=("Segoe UI", 10, "bold"), pequena=("Segoe UI", 9),
    titulo=("Segoe UI", 15, "bold"), numero=("Segoe UI", 19, "bold"), mono=("Consolas", 9),
)
ESP = dict(xs=4, s=8, m=12, l=16, xl=24)   # escala de espaçamento, em px

# Números medidos em PostgreSQL 16 local com --seed 42 (os mesmos do README).
ESCALAS = [
    ("leve", "Leve", "~400 usuários, ~25 MB, ~6 s"),
    ("medio", "Médio", "~1.300 usuários, ~55 MB, ~20 s"),
    ("pesado", "Pesado", "~4.300 usuários, ~145 MB, ~55 s"),
]
LIMITE_AIVEN = 1024 ** 3   # disco do plano gratuito da Aiven

# Sem isso, um banco fora do ar deixaria a verificação pendurada por minutos.
os.environ.setdefault("PGCONNECT_TIMEOUT", "10")


# ==============================================================================
# CÁLCULOS DO PAINEL (sem tela; cobertos por tests/test_ui.py)
# ==============================================================================

def inteiro(n):
    return f"{n:,}".replace(",", ".")


def percentual(parte, total):
    return f"{100 * parte / total:.1f}%".replace(".", ",") if total else "0%"


def tamanho(nbytes):
    if nbytes < 1024 ** 2:
        return f"{round(nbytes / 1024)} kB"
    if nbytes < 1024 ** 3:
        return f"{round(nbytes / 1024 ** 2)} MB"
    return f"{nbytes / 1024 ** 3:.1f} GB".replace(".", ",")


def duracao(segundos):
    if segundos < 1:
        return "menos de 1 s"
    minutos, resto = divmod(round(segundos), 60)
    return f"{minutos} min {resto} s" if minutos else f"{resto} s"


def segundos_curtos(segundos):
    """Tempo de uma etapa, com uma casa: '2,4 s'. Abaixo da resolução, '< 0,1 s'."""
    return "< 0,1 s" if segundos < 0.05 else f"{segundos:.1f} s".replace(".", ",")


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


def resumo_faltando(faltando):
    mostra = ", ".join(faltando[:5]) + (f" e mais {len(faltando) - 5}" if len(faltando) > 5 else "")
    return f"faltam {len(faltando)} colunas do schema: {mostra}"


# ==============================================================================
# COMPONENTES
# ==============================================================================

def botao(pai, texto, comando, principal=False):
    """Botão sobre o painel lateral. principal=True é a ação da tela (um só)."""
    cor = COR["marca"] if principal else COR["noite_2"]
    return tk.Button(
        pai, text=texto, command=comando, bg=cor, fg=COR["claro"],
        activebackground=COR["marca_escura"] if principal else COR["noite_borda"], activeforeground=COR["claro"],
        disabledforeground=COR["claro_2"], relief="flat", bd=0, cursor="hand2",
        padx=ESP["m"], pady=9 if principal else 5, font=FONTE["forte"] if principal else FONTE["base"],
        highlightthickness=1, highlightbackground=cor, highlightcolor=COR["claro"])   # anel de foco visível


class Cartao(tk.Frame):
    """Número de destaque do painel: rótulo, valor e uma nota opcional."""

    def __init__(self, pai, rotulo):
        super().__init__(pai, bg=COR["superficie"], highlightthickness=1, highlightbackground=COR["borda"],
                         padx=ESP["l"], pady=ESP["m"])
        self.rotulo = tk.Label(self, text=rotulo, bg=COR["superficie"], fg=COR["texto_2"], font=FONTE["pequena"])
        self.rotulo.pack(anchor="w")
        self.valor = tk.Label(self, text="—", bg=COR["superficie"], fg=COR["texto"], font=FONTE["numero"])
        self.valor.pack(anchor="w")
        self.nota = tk.Label(self, text="", bg=COR["superficie"], fg=COR["texto_2"], font=FONTE["pequena"],
                             justify="left")
        self.nota.pack(anchor="w")
        self.bind("<Configure>", self.ajustar)

    def ajustar(self, evento):
        for texto in (self.rotulo, self.valor, self.nota):   # quebra na largura útil em vez de cortar
            texto.configure(wraplength=max(evento.width - 2 * ESP["l"] - 2, 60), justify="left")

    def mostrar(self, valor, nota="", rotulo=None):
        self.valor.configure(text=valor)
        self.nota.configure(text=nota)
        if rotulo:
            self.rotulo.configure(text=rotulo)


class Barras(tk.Frame):
    """Gráfico de barras horizontais de uma série só: título, barras com o valor na ponta e legenda de hover."""

    PASSO, ESPESSURA, RAIO = 20, 10, 4

    def __init__(self, pai, titulo, legenda):
        super().__init__(pai, bg=COR["superficie"], highlightthickness=1, highlightbackground=COR["borda"],
                         padx=ESP["l"], pady=ESP["m"])
        tk.Label(self, text=titulo, bg=COR["superficie"], fg=COR["texto"], font=FONTE["forte"]).pack(anchor="w")
        self.tela = tk.Canvas(self, bg=COR["superficie"], highlightthickness=0, height=10 * self.PASSO + 8)
        self.tela.pack(fill="x", pady=(ESP["s"], ESP["xs"]))
        self.legenda_padrao = legenda
        self.legenda = tk.Label(self, text=legenda, bg=COR["superficie"], fg=COR["texto_2"], font=FONTE["pequena"],
                                anchor="w", justify="left")
        self.legenda.pack(fill="x")
        self.itens, self.vazio = [], ""
        self.fonte = tkfont.Font(font=FONTE["pequena"])
        self.tela.bind("<Configure>", lambda e: self.desenhar())
        # O alvo do hover é a linha inteira, não só a barra (barras curtas seriam difíceis de acertar).
        self.tela.bind("<Motion>", self.ao_passar)
        self.tela.bind("<Leave>", lambda e: self.legenda.configure(text=self.legenda_padrao))

    def mostrar(self, itens, vazio):
        """itens = [(rótulo, valor, texto do valor, texto de hover)], já na ordem de exibição."""
        self.itens, self.vazio = itens, vazio
        self.desenhar()

    def ao_passar(self, evento):
        i = (evento.y - 4) // self.PASSO
        self.legenda.configure(text=self.itens[i][3] if 0 <= i < len(self.itens) else self.legenda_padrao)

    def encurtar(self, texto, largura):
        if self.fonte.measure(texto) <= largura:
            return texto
        while texto and self.fonte.measure(texto + "…") > largura:
            texto = texto[:-1]
        return texto.rstrip() + "…"

    def desenhar(self):
        tela, largura = self.tela, self.tela.winfo_width()
        tela.delete("all")
        if not self.itens:
            tela.create_text(0, 4, anchor="nw", text=self.vazio, fill=COR["texto_2"], font=FONTE["pequena"],
                             width=max(largura, 100))
            return
        largura_valor = max(self.fonte.measure(t) for _, _, t, _ in self.itens)
        largura_rotulo = min(max(self.fonte.measure(r) for r, *_ in self.itens), int(largura * 0.5))
        x0 = largura_rotulo + 10
        util = max(largura - x0 - largura_valor - 12, 10)
        maior = max(v for _, v, _, _ in self.itens) or 1
        for i, (rotulo, valor, texto, _) in enumerate(self.itens):
            meio = 4 + i * self.PASSO + self.PASSO / 2
            y0, y1, r = meio - self.ESPESSURA / 2, meio + self.ESPESSURA / 2, self.RAIO
            x1 = x0 + max(util * valor / maior, 2)
            tela.create_text(largura_rotulo, meio, anchor="e", text=self.encurtar(rotulo, largura_rotulo),
                             fill=COR["texto"], font=FONTE["pequena"])
            if x1 - x0 < 2 * r:   # barra curta demais para arredondar
                tela.create_rectangle(x0, y0, x1, y1, fill=COR["marca"], width=0)
            else:                 # reta na base, ponta arredondada
                tela.create_rectangle(x0, y0, x1 - r, y1, fill=COR["marca"], width=0)
                tela.create_rectangle(x1 - r, y0 + r, x1, y1 - r, fill=COR["marca"], width=0)
                tela.create_oval(x1 - 2 * r, y0, x1, y0 + 2 * r, fill=COR["marca"], outline="")
                tela.create_oval(x1 - 2 * r, y1 - 2 * r, x1, y1, fill=COR["marca"], outline="")
            tela.create_text(x1 + 6, meio, anchor="w", text=texto, fill=COR["texto"], font=FONTE["pequena"])


# ==============================================================================
# TELA
# ==============================================================================

class Tela:
    COLUNAS = [("tabela", "Tabela", "w", 300), ("grupo", "Grupo", "w", 130), ("linhas", "Linhas", "e", 110),
               ("pct", "% das linhas", "e", 110), ("disco", "Em disco", "e", 100)]

    def __init__(self, root):
        self.root = root
        self.fila = queue.Queue()   # (função, argumento) vindos das threads; só a thread da tela mexe nos widgets
        self.proc = None
        self.marcos = []            # [(número, nome, instante)] das etapas da carga em andamento
        self.fim_insercao = None
        self.ultima = None          # dados da última carga concluída nesta sessão
        self.linhas_tabela = []     # [(tabela, grupo, linhas, bytes)] mostradas na tabela
        self.total_linhas = 0
        self.ordem = ("linhas", True)

        root.title("Populador EcoCiente")
        root.configure(bg=COR["fundo"])
        root.geometry("1180x760")
        root.minsize(1020, 680)
        root.protocol("WM_DELETE_WINDOW", self.fechar)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        self.estilos()
        self.montar_lateral()
        self.montar_conteudo()
        self.controles = [self.btn_testar, self.btn_sortear, self.btn_popular, self.campo_seed, *self.opcoes]
        root.after(100, self.ler_fila)

    def estilos(self):
        estilo = ttk.Style(self.root)
        estilo.theme_use("clam")
        estilo.configure(".", background=COR["fundo"], foreground=COR["texto"], font=FONTE["base"])
        contorno = dict(bordercolor=COR["borda"], lightcolor=COR["borda"], darkcolor=COR["borda"])
        estilo.configure("TNotebook", background=COR["fundo"], tabmargins=(0, 0, 0, 0), **contorno)
        estilo.configure("TNotebook.Tab", background=COR["fundo"], foreground=COR["texto_2"], font=FONTE["forte"],
                         padding=(ESP["l"], ESP["s"]), **contorno)
        estilo.configure("TScrollbar", background=COR["borda"], troughcolor=COR["fundo"], arrowcolor=COR["texto_2"],
                         **contorno)
        estilo.map("TNotebook.Tab", background=[("selected", COR["superficie"])],
                   foreground=[("selected", COR["texto"])], lightcolor=[("selected", COR["superficie"])])
        estilo.configure("TButton", background=COR["superficie"], bordercolor=COR["borda"], padding=(ESP["m"], 4))
        estilo.map("TButton", background=[("active", COR["selecao"])])
        estilo.configure("Horizontal.TProgressbar", background=COR["marca"], troughcolor=COR["borda"],
                         bordercolor=COR["borda"], lightcolor=COR["marca"], darkcolor=COR["marca"])
        estilo.configure("Treeview", background=COR["superficie"], fieldbackground=COR["superficie"],
                         foreground=COR["texto"], rowheight=24, borderwidth=0, font=FONTE["base"])
        estilo.configure("Treeview.Heading", background=COR["superficie"], foreground=COR["texto_2"],
                         font=FONTE["forte"], relief="flat", padding=(ESP["s"], 6))
        estilo.map("Treeview.Heading", background=[("active", COR["selecao"])])
        estilo.map("Treeview", background=[("selected", COR["selecao"])], foreground=[("selected", COR["texto"])])

    # ---------------------------------------------------------------- lateral
    def montar_lateral(self):
        lado = tk.Frame(self.root, bg=COR["noite"], padx=ESP["xl"], pady=ESP["xl"], width=310)
        lado.grid(row=0, column=0, sticky="ns")
        lado.pack_propagate(False)

        def rotulo(texto, cor="claro", fonte="forte", **pack):
            item = tk.Label(lado, text=texto, bg=COR["noite"], fg=COR[cor], font=FONTE[fonte], justify="left",
                            anchor="w", wraplength=262)
            item.pack(fill="x", **pack)
            return item

        cabecalho = tk.Frame(lado, bg=COR["noite"])
        cabecalho.pack(fill="x")
        self.logo = tk.PhotoImage(file=str(AQUI / "assets" / "logo_branca.png"))
        tk.Label(cabecalho, image=self.logo, bg=COR["noite"]).pack(side="left")
        tk.Label(cabecalho, text="Populador\nde dados", bg=COR["noite"], fg=COR["claro"], font=FONTE["titulo"],
                 justify="left").pack(side="left", padx=(ESP["l"], 0))

        rotulo("Banco de destino", pady=(ESP["xl"], ESP["xs"]))
        rotulo(target_description(), fonte="mono")
        self.btn_testar = botao(lado, "Testar conexão", self.testar)
        self.btn_testar.pack(anchor="w", pady=(ESP["s"], ESP["xs"]))
        self.status_banco = rotulo("Conexão ainda não testada.", cor="claro_2", fonte="pequena")

        rotulo("Tamanho da massa", pady=(ESP["l"], ESP["xs"]))
        self.escala = tk.StringVar(value="medio")
        self.opcoes = []
        for valor, nome, numeros in ESCALAS:   # opção selecionada fica verde
            opcao = tk.Radiobutton(
                lado, text=f"{nome}\n{numeros}", value=valor, variable=self.escala, indicatoron=False,
                bg=COR["noite_2"], fg=COR["claro"], selectcolor=COR["marca"],
                activebackground=COR["noite_borda"], activeforeground=COR["claro"],
                disabledforeground=COR["claro_2"], relief="flat", offrelief="flat", bd=0, cursor="hand2",
                anchor="w", justify="left", padx=ESP["m"], pady=6, font=FONTE["base"],
                highlightthickness=1, highlightbackground=COR["noite"], highlightcolor=COR["claro"])
            opcao.pack(fill="x", pady=1)
            self.opcoes.append(opcao)
        rotulo("Tempos medidos em banco local. Em banco remoto (Aiven), conte com alguns minutos.",
               cor="claro_2", fonte="pequena", pady=(ESP["xs"], 0))

        rotulo("Seed", pady=(ESP["l"], ESP["xs"]))
        linha_seed = tk.Frame(lado, bg=COR["noite"])
        linha_seed.pack(fill="x")
        self.seed = tk.StringVar(value="42")
        self.campo_seed = tk.Entry(
            linha_seed, textvariable=self.seed, width=10, font=("Consolas", 11), relief="flat", bd=6,
            bg=COR["noite_2"], fg=COR["claro"], insertbackground=COR["claro"],
            disabledbackground=COR["noite_2"], disabledforeground=COR["claro_2"],
            highlightthickness=1, highlightbackground=COR["noite_borda"], highlightcolor=COR["claro"])
        self.campo_seed.pack(side="left")
        self.btn_sortear = botao(linha_seed, "Sortear seed",
                                 lambda: self.seed.set(str(random.randint(1, 999_999))))
        self.btn_sortear.pack(side="left", padx=(ESP["s"], 0))
        rotulo("A mesma seed gera sempre a mesma massa.", cor="claro_2", fonte="pequena", pady=(ESP["xs"], 0))

        self.btn_popular = botao(lado, "Popular banco", self.popular, principal=True)
        self.btn_popular.pack(side="bottom", fill="x")

    # --------------------------------------------------------------- conteúdo
    def montar_conteudo(self):
        self.abas = ttk.Notebook(self.root)
        self.abas.grid(row=0, column=1, sticky="nsew", padx=ESP["xl"], pady=ESP["xl"])

        # Aba Andamento: etapa atual, barra e log do main.py
        andamento = tk.Frame(self.abas, bg=COR["superficie"], padx=ESP["xl"], pady=ESP["xl"])
        self.abas.add(andamento, text="Andamento")
        self.status_carga = tk.Label(andamento, text="Nenhuma carga em andamento.", bg=COR["superficie"],
                                     fg=COR["texto"], font=FONTE["forte"], anchor="w")
        self.status_carga.pack(fill="x")
        self.barra = ttk.Progressbar(andamento, maximum=10)
        self.barra.pack(fill="x", pady=(ESP["s"], ESP["l"]))
        quadro_log = tk.Frame(andamento, bg=COR["noite"])
        quadro_log.pack(fill="both", expand=True)
        self.log = tk.Text(quadro_log, bg=COR["noite"], fg="#dbe4d6", insertbackground=COR["claro"], relief="flat",
                           font=FONTE["mono"], padx=ESP["m"], pady=ESP["s"], state="disabled", wrap="none")
        rolagem = ttk.Scrollbar(quadro_log, command=self.log.yview)
        self.log.configure(yscrollcommand=rolagem.set)
        rolagem.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)

        # Aba Resultado: estado vazio OU painel da inserção
        resultado = tk.Frame(self.abas, bg=COR["fundo"])
        self.abas.add(resultado, text="Resultado")
        self.aba_resultado = resultado

        self.vazio = tk.Frame(resultado, bg=COR["fundo"], padx=ESP["xl"], pady=ESP["xl"])
        self.vazio_texto = tk.Label(self.vazio, bg=COR["fundo"], fg=COR["texto"], font=FONTE["base"],
                                    justify="left", anchor="w", wraplength=620)
        self.vazio_texto.pack(anchor="w")
        self.btn_ler = ttk.Button(self.vazio, text="Ler o banco agora", command=self.atualizar_painel)
        self.btn_ler.pack(anchor="w", pady=(ESP["m"], 0))

        self.painel = tk.Frame(resultado, bg=COR["fundo"], padx=ESP["l"], pady=ESP["l"])
        self.painel.columnconfigure((0, 1), weight=1, uniform="grafico")
        self.painel.rowconfigure(3, weight=1)

        topo = tk.Frame(self.painel, bg=COR["fundo"])
        topo.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.contexto = tk.Label(topo, bg=COR["fundo"], fg=COR["texto"], font=FONTE["base"], anchor="w",
                                 justify="left")
        self.contexto.pack(side="left")
        self.btn_atualizar = ttk.Button(topo, text="Ler o banco de novo", command=self.atualizar_painel)
        self.btn_atualizar.pack(side="right")

        cartoes = tk.Frame(self.painel, bg=COR["fundo"])
        cartoes.grid(row=1, column=0, columnspan=2, sticky="ew", pady=ESP["m"])
        self.cartoes = {}
        for i, (chave, texto) in enumerate([
                ("linhas", "Linhas inseridas"), ("tabelas", "Tabelas populadas"), ("duracao", "Duração da carga"),
                ("ritmo", "Linhas por segundo"), ("tamanho", "Tamanho do banco")]):
            cartoes.columnconfigure(i, weight=1, uniform="cartao")
            self.cartoes[chave] = Cartao(cartoes, texto)
            self.cartoes[chave].grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else ESP["s"], 0))

        self.g_tabelas = Barras(self.painel, "Tabelas com mais linhas",
                                "Passe o mouse sobre uma barra para ver o detalhe.")
        self.g_tabelas.grid(row=2, column=0, sticky="nsew", padx=(0, ESP["s"]))
        self.g_etapas = Barras(self.painel, "Tempo por etapa da carga",
                               "Passe o mouse sobre uma barra para ver o nome completo.")
        self.g_etapas.grid(row=2, column=1, sticky="nsew")

        quadro = tk.Frame(self.painel, bg=COR["superficie"], highlightthickness=1, highlightbackground=COR["borda"])
        quadro.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(ESP["m"], 0))
        self.tabela = ttk.Treeview(quadro, columns=[c for c, *_ in self.COLUNAS], show="headings", height=6)
        for chave, _, ancora, largura in self.COLUNAS:
            self.tabela.heading(chave, anchor=ancora, command=lambda c=chave: self.ordenar(c))
            self.tabela.column(chave, anchor=ancora, width=largura, stretch=chave == "tabela")
        rolagem_tabela = ttk.Scrollbar(quadro, command=self.tabela.yview)
        self.tabela.configure(yscrollcommand=rolagem_tabela.set)
        rolagem_tabela.pack(side="right", fill="y")
        self.tabela.pack(fill="both", expand=True)

        self.mostrar_vazio("Ainda não há resultado. Rode uma carga, ou leia o que já está no banco.")

    def mostrar_vazio(self, texto, cor="texto", pode_ler=True):
        self.painel.pack_forget()
        self.vazio_texto.configure(text=texto, fg=COR[cor])
        self.btn_ler.configure(state="normal" if pode_ler else "disabled")
        self.vazio.pack(fill="both", expand=True)

    # ---------------------------------------------------------------- threads
    def em_segundo_plano(self, tarefa, ao_terminar):
        """Roda `tarefa` fora da thread da tela e entrega o resultado (ou a exceção) a `ao_terminar`."""
        def alvo():
            try:
                resultado = tarefa()
            except Exception as erro:
                resultado = erro
            self.fila.put((ao_terminar, resultado))
        threading.Thread(target=alvo, daemon=True).start()

    def ler_fila(self):
        try:
            while True:
                funcao, argumento = self.fila.get_nowait()
                funcao(argumento)
        except queue.Empty:
            pass
        self.root.after(100, self.ler_fila)

    def travar(self, travado):
        for controle in self.controles:
            controle.configure(state="disabled" if travado else "normal")

    @staticmethod
    def texto_do_erro(erro):
        return str(erro).strip().splitlines()[0] if str(erro).strip() else type(erro).__name__

    # ----------------------------------------------------------------- banco
    def mostrar_banco(self, resultado):
        """Atualiza a linha de status do banco. Devolve True se a conexão funcionou."""
        if isinstance(resultado, Exception):
            self.status_banco.configure(text=f"Não foi possível conectar: {self.texto_do_erro(resultado)}",
                                        fg=COR["erro_claro"])
            return False
        if resultado:
            self.status_banco.configure(text=f"Conectado, mas {resumo_faltando(resultado)}.", fg=COR["erro_claro"])
        else:
            self.status_banco.configure(text="Conectado. O banco confere com o schema.", fg=COR["ok_claro"])
        return True

    def testar(self):
        self.travar(True)
        self.status_banco.configure(text="Testando a conexão…", fg=COR["claro_2"])
        self.em_segundo_plano(verificar_banco, lambda r: (self.mostrar_banco(r), self.travar(False)))

    # ----------------------------------------------------------------- carga
    def popular(self):
        try:
            seed = int(self.seed.get())
        except ValueError:
            messagebox.showerror("Seed inválida", "A seed precisa ser um número inteiro, por exemplo 42.")
            return
        self.travar(True)
        self.status_banco.configure(text="Conferindo o banco antes da carga…", fg=COR["claro_2"])
        self.em_segundo_plano(verificar_banco, lambda r: self.confirmar(r, seed))

    def confirmar(self, resultado, seed):
        if not self.mostrar_banco(resultado):
            self.travar(False)
            return
        escala = self.escala.get()
        aviso = (f"Isso apaga todos os dados de negócio em:\n{target_description()}\n\n"
                 f"e gera a massa \"{escala}\" com a seed {seed}.")
        if resultado:
            aviso += (f"\n\nAtenção: {resumo_faltando(resultado)}.\n"
                      "A carga pode falhar no meio. Aplique sql/ecociente_schema.sql antes, se puder.")
        if not messagebox.askyesno("Apagar e popular o banco?", aviso + "\n\nContinuar?", icon="warning"):
            self.travar(False)
            return

        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.barra["value"] = 0
        self.status_carga.configure(text="Iniciando a carga…", fg=COR["texto"])
        self.marcos, self.fim_insercao, self.ultima = [], None, None
        self.mostrar_vazio("Carga em andamento. O resultado aparece aqui quando ela terminar.", pode_ler=False)
        self.abas.select(0)
        self.proc = subprocess.Popen(
            # --force: a confirmação já foi feita no diálogo acima.
            [sys.executable, "-u", str(AQUI / "main.py"), "--escala", escala, "--seed", str(seed), "--force"],
            cwd=AQUI, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        carga = dict(escala=escala, seed=seed)

        def acompanhar():
            for linha in self.proc.stdout:
                self.fila.put((self.escrever_log, (linha, time.time())))
            self.fila.put((lambda codigo: self.terminou(codigo, carga), self.proc.wait()))
        threading.Thread(target=acompanhar, daemon=True).start()

    def escrever_log(self, evento):
        linha, instante = evento   # o instante vem da thread leitora: é quando o main.py imprimiu
        etapa = etapa_da_linha(linha)
        if etapa:
            self.marcos.append((*etapa, instante))
            self.barra["value"] = etapa[0] - 1
            self.status_carga.configure(text=f"Etapa {etapa[0]} de 10: {etapa[1]}")
        elif linha.startswith("Carga concluída"):   # depois disso o main.py só conta linhas para o resumo
            self.fim_insercao = instante
        self.log.configure(state="normal")
        self.log.insert("end", linha)
        self.log.see("end")
        self.log.configure(state="disabled")

    def terminou(self, codigo, carga):
        self.proc = None
        self.travar(False)
        if codigo != 0 or not self.marcos or self.fim_insercao is None:
            self.status_carga.configure(text="A carga falhou. O erro está no log abaixo.", fg=COR["erro"])
            self.mostrar_vazio("A carga falhou. O erro está na aba Andamento.", cor="erro")
            return
        segundos = self.fim_insercao - self.marcos[0][2]
        self.barra["value"] = 10
        self.status_carga.configure(text=f"Carga concluída em {duracao(segundos)}.", fg=COR["ok"])
        self.ultima = dict(carga, segundos=segundos, etapas=tempos_por_etapa(self.marcos, self.fim_insercao),
                           quando=time.strftime("%H:%M"))
        self.atualizar_painel()

    # ---------------------------------------------------------------- painel
    def atualizar_painel(self):
        self.btn_ler.configure(state="disabled")
        self.btn_atualizar.configure(state="disabled")
        self.em_segundo_plano(medir_banco, self.mostrar_painel)

    def mostrar_painel(self, resultado):
        self.btn_atualizar.configure(state="normal")
        if isinstance(resultado, Exception):
            self.mostrar_vazio(f"Não foi possível ler o banco: {self.texto_do_erro(resultado)}", cor="erro")
            return
        medidas, bytes_banco = resultado
        carga = self.ultima
        r = resumir_carga(medidas, carga["segundos"] if carga else None)

        lido = f"Banco lido às {time.strftime('%H:%M')}."
        self.contexto.configure(text=(
            f"Massa \"{carga['escala']}\", seed {carga['seed']}, concluída às {carga['quando']}. {lido}"
            if carga else f"{lido} Nenhuma carga foi feita nesta sessão, então não há tempos."))

        vazias = r["vazias"]
        self.cartoes["linhas"].mostrar(inteiro(r["linhas"]), rotulo="Linhas inseridas" if carga else "Linhas no banco")
        self.cartoes["tabelas"].mostrar(
            f"{r['populadas']} de {r['tabelas']}",
            "Vazias: " + ", ".join(vazias[:2]) + (f" e mais {len(vazias) - 2}" if len(vazias) > 2 else "")
            if vazias else "Nenhuma vazia")
        self.cartoes["duracao"].mostrar(duracao(carga["segundos"]) if carga else "—",
                                        "Etapas 1 a 10" if carga else "")
        self.cartoes["ritmo"].mostrar(inteiro(r["linhas_por_segundo"]) if r["linhas_por_segundo"] else "—",
                                      "Contando as de triggers" if carga else "")
        self.cartoes["tamanho"].mostrar(tamanho(bytes_banco),
                                        f"{percentual(bytes_banco, LIMITE_AIVEN)} do 1 GB da Aiven")

        maiores = sorted((m for m in medidas if m[1]), key=lambda m: -m[1])[:10]
        self.g_tabelas.mostrar(
            [(t, n, inteiro(n),
              f"{t}: {inteiro(n)} linhas, {percentual(n, r['linhas'])} do total, {tamanho(b)} em disco")
             for t, n, b in maiores],
            "O banco não tem nenhuma linha nas tabelas tb_*.")
        self.g_etapas.mostrar(
            [(nome, s, segundos_curtos(s),
              f"{nome}: {segundos_curtos(s)}, {percentual(s, carga['segundos'])} da inserção")
             for nome, s in carga["etapas"]] if carga else [],
            "Os tempos só existem logo depois de uma carga feita por esta tela.")

        self.linhas_tabela = [(t, grupo_da_tabela(t), n, b) for t, n, b in medidas]
        self.total_linhas = r["linhas"]
        self.ordem = ("linhas", True)
        self.preencher_tabela()

        self.vazio.pack_forget()
        self.painel.pack(fill="both", expand=True)
        self.abas.select(self.aba_resultado)

    def ordenar(self, coluna):
        # Novo clique na mesma coluna inverte; coluna nova começa pelo maior (ou A-Z nos textos).
        mesma = self.ordem[0] == coluna
        self.ordem = (coluna, not self.ordem[1] if mesma else coluna not in ("tabela", "grupo"))
        self.preencher_tabela()

    def preencher_tabela(self):
        coluna, decrescente = self.ordem
        indice = {"tabela": 0, "grupo": 1, "linhas": 2, "pct": 2, "disco": 3}[coluna]
        for chave, titulo, *_ in self.COLUNAS:
            seta = (" ▼" if decrescente else " ▲") if chave == coluna else ""
            self.tabela.heading(chave, text=titulo + seta)
        self.tabela.delete(*self.tabela.get_children())
        for t, grupo, n, b in sorted(self.linhas_tabela, key=lambda l: l[indice], reverse=decrescente):
            self.tabela.insert("", "end", values=(t, grupo, inteiro(n), percentual(n, self.total_linhas), tamanho(b)))

    def fechar(self):
        if self.proc is not None:
            if not messagebox.askyesno(
                    "Carga em andamento",
                    "Fechar agora interrompe a carga e deixa o banco pela metade.\n\nFechar mesmo assim?",
                    icon="warning"):
                return
            self.proc.terminate()
        self.root.destroy()


if __name__ == "__main__":
    janela = tk.Tk()
    Tela(janela)
    janela.mainloop()
