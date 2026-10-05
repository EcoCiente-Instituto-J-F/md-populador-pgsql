# ==============================================================================
# EcoCiente – camada de acesso a dados para a carga inicial de massa
# ==============================================================================
import random
import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from psycopg2.extras import execute_values

from .helpers import fetch_id
from .faker_br import FakerBR
from .unique_generator import cpf_unico, email_unico, hash_foto_unico, token_unico

# ==============================================================================
# CONFIGURAÇÃO / VOLUMETRIA
# ==============================================================================

SEED = 42  # fixo → massa reprodutível. Use --seed N no main.py para variar.

DIAS_HISTORICO = 365           # janela de histórico simulada (cadastros, postagens, DAU...)
TZ = ZoneInfo("America/Sao_Paulo")

# Escala "medio" (~1.300 usuários, ~55 MB). main.py --escala multiplica
# os N_* abaixo (leve 0.3 / medio 1 / pesado 3).
N_CONDOMINIOS_RESIDENCIAL   = 18
N_CONDOMINIOS_COMERCIAL     = 7
N_COOPERATIVAS              = 10
N_USUARIOS_COMUM            = 400

TORRES_POR_RESIDENCIAL      = (2, 4)
MORADORES_POR_TORRE         = (10, 16)
USUARIOS_POR_COMERCIAL      = (25, 45)

PONTOS_COLETA_POR_COOPERATIVA = (2, 5)
VOTOS_POR_POSTAGEM            = (2, 9)
NOTIFICACOES_POR_USUARIO      = (4, 15)
AGENDAMENTOS_POR_CONDOMINIO   = (4, 8)
VISITAS_POR_AGENDAMENTO       = (3, 8)
TOKENS_API_POR_USUARIO        = (1, 3)

# Perfis de engajamento: amarram postagens, cursos, quizzes, votos e DAU do
# mesmo usuário -- quem posta mais também abre mais o app, vota mais etc.
# abandono = chance de parar de usar o app em algum momento (churn usa
# vida curta de 5–75 dias; os demais, 30–240 dias) -- dá curva de retenção.
PERFIS = {
    "power":   dict(peso=10, p_dia=0.70, postagens=(25, 50), cursos=(3, 6), conclusao=0.95, acerto=0.85, peso_voto=8.0, abandono=0.03),
    "regular": dict(peso=35, p_dia=0.38, postagens=(6, 15),  cursos=(1, 4), conclusao=0.90, acerto=0.75, peso_voto=3.0, abandono=0.20),
    "casual":  dict(peso=35, p_dia=0.12, postagens=(1, 5),   cursos=(0, 2), conclusao=0.75, acerto=0.62, peso_voto=1.0, abandono=0.55),
    "churn":   dict(peso=20, p_dia=0.30, postagens=(0, 3),   cursos=(0, 1), conclusao=0.50, acerto=0.55, peso_voto=0.5, abandono=1.00),
}

# (nome, descrição, permite_reciclagem, cor, pontos_base, limite_pontos_diario,
#  peso residencial, peso comercial, % de postagens que a comunidade aprova)
CATEGORIAS = [
    ("Papel",      "Papel e papelão em geral",          True,  "#1565C0", 10, 20, 20, 38, 84),
    ("Plástico",   "Embalagens e materiais plásticos",  True,  "#F9A825", 10, 20, 30, 22, 82),
    ("Vidro",      "Garrafas, potes e vidro em geral",  True,  "#2E7D32", 12, 24, 12,  6, 86),
    ("Metal",      "Latas e metais recicláveis",        True,  "#757575", 15, 30, 10,  8, 85),
    ("Orgânico",   "Resíduo orgânico / compostável",    True,  "#6D4C41",  5, 10, 22,  8, 64),
    ("Eletrônico", "Lixo eletrônico (e-waste)",         True,  "#512DA8", 30, 30,  6, 18, 72),
    ("Rejeito",    "Resíduo não reciclável",            False, "#212121",  1,  2,  3,  3, 25),
]
_META_CATEGORIA = {c[0]: c for c in CATEGORIAS}

# Horários locais de uso do app (picos de manhã, almoço e noite).
_PESOS_HORA = [1, 0, 0, 0, 0, 1, 3, 6, 8, 6, 5, 6, 8, 7, 5, 5, 5, 6, 8, 10, 10, 8, 5, 2]

AGORA = datetime.now(timezone.utc)
HOJE = AGORA.astimezone(TZ).date()


def _semana_meio_ambiente():
    """1–7 de junho mais recente dentro da janela: pico de engajamento proposital."""
    ano = HOJE.year if date(HOJE.year, 6, 7) < HOJE else HOJE.year - 1
    return date(ano, 6, 1), date(ano, 6, 7)


CAMPANHA = _semana_meio_ambiente()


def gerar_senha_segura(email_usuario: str) -> str:
    """
    Gera uma senha de massa de teste respeitando a política:
    - mínimo 8 caracteres
    - 1 letra maiúscula
    - 1 letra minúscula
    - 1 caractere especial

    A senha gerada é posteriormente armazenada como hash.
    """
    base = re.sub(r"[^a-zA-Z0-9]", "", email_usuario.split("@")[0])
    base = (base[:5] or "Eco") + "A1!"
    return base + "@Eco"


def hash_senha(senha: str) -> str:
    """Hash determinístico para popular o banco de desenvolvimento."""
    return "$2b$12$" + hashlib.sha256(senha.encode("utf-8")).hexdigest()[:53]


fk  = FakerBR(seed=SEED)
rng = random.Random(SEED)

# usuario_id -> {"perfil", "inicio", "fim", "comercial"}: janela em que o
# usuário existe/usa o app. Tudo que é datado (postagem, voto, aula, DAU)
# cai dentro dela.
USUARIOS = {}


# ==============================================================================
# 0. TEMPO E AMOSTRAGEM
# ==============================================================================

def sortear_perfil():
    nomes = list(PERFIS)
    return rng.choices(nomes, weights=[PERFIS[n]["peso"] for n in nomes])[0]


def _peso_dia(dia, comercial):
    """Peso relativo de um dia: fim de semana (↑ residencial, ↓ comercial) e campanha."""
    peso = (0.35 if comercial else 1.25) if dia.weekday() >= 5 else 1.0
    if CAMPANHA[0] <= dia <= CAMPANHA[1]:
        peso *= 1.8
    return peso


def data_no_periodo(inicio, fim, comercial=False):
    """datetime UTC entre inicio e fim, respeitando dia da semana, campanha e horário de pico."""
    fim = max(inicio, min(fim, AGORA))
    total = (fim - inicio).total_seconds()
    for _ in range(20):
        t = inicio + timedelta(seconds=rng.random() * total)
        if rng.random() * 2.25 < _peso_dia(t.astimezone(TZ).date(), comercial):
            break
    local = t.astimezone(TZ)
    hora = rng.choices(range(24), weights=_PESOS_HORA)[0]
    t = local.replace(hour=hora, minute=rng.randint(0, 59), second=rng.randint(0, 59)).astimezone(timezone.utc)
    return min(max(t, inicio), fim)


def amostra_ponderada(itens, pesos, k):
    """k itens distintos, com chance proporcional ao peso (Efraimidis–Spirakis)."""
    chaves = sorted(((rng.random() ** (1.0 / p), i) for i, p in zip(itens, pesos)), reverse=True)
    return [i for _, i in chaves[:k]]


# ==============================================================================
# 1. TABELAS DE DOMÍNIO / LOOKUP
# ==============================================================================

def popular_tipos_usuarios(cur):
    tipos = [
        ("Usuário Comum",
         "Não paga mensalidade, não pertence a condomínio. Acesso a ensino, "
         "mapa de pontos de coleta e notificações."),
        ("Síndico Residencial",
         "Gestor de condomínio residencial. Acesso a ranking, calendário, "
         "mapa, analytics (macro) e ensino."),
        ("Síndico Comercial",
         "Gestor de condomínio comercial. Fluxo corporativo: calendário, "
         "mapa, analytics (macro) e ensino."),
        ("Morador Residencial",
         "Ocupante de condomínio residencial. Ranking, analytics "
         "individual e ensino."),
        ("Usuário Comercial",
         "Ocupante/usuário de condomínio comercial. Analytics individual, "
         "calendário e ensino."),
        ("Cooperativa",
         "Conta de acesso da cooperativa de reciclagem parceira."),
        ("Administrador",
         "Administrador do sistema, com acesso a todas as funcionalidades "
         "de gestão e moderação."),
    ]
    ids = {}
    for nome, desc in tipos:
        cur.execute(
            "SELECT id_tipo_usuario FROM tb_lkp_tipos_usuarios WHERE nome_tipo = %s",
            (nome,),
        )
        row = cur.fetchone()
        if row:
            ids[nome] = row[0]
            continue
        ids[nome] = fetch_id(
            cur,
            "INSERT INTO tb_lkp_tipos_usuarios (nome_tipo, descricao) "
            "VALUES (%s, %s) RETURNING id_tipo_usuario",
            (nome, desc),
        )
    return ids


def popular_tipos_condominios(cur):
    tipos = [
        ("Residencial", "Condomínio residencial (tb_torres + tb_moradores)."),
        ("Comercial",   "Condomínio/edifício comercial."),
    ]
    ids = {}
    for nome, desc in tipos:
        cur.execute(
            "SELECT id_tipo_condominio FROM tb_lkp_tipos_condominios WHERE nome_tipo = %s",
            (nome,),
        )
        row = cur.fetchone()
        if row:
            ids[nome] = row[0]
            continue
        ids[nome] = fetch_id(
            cur,
            "INSERT INTO tb_lkp_tipos_condominios (nome_tipo, descricao) "
            "VALUES (%s, %s) RETURNING id_tipo_condominio",
            (nome, desc),
        )
    return ids


def popular_dias_semana(cur):
    dias = [
        "Segunda-feira", "Terça-feira", "Quarta-feira",
        "Quinta-feira",  "Sexta-feira", "Sábado", "Domingo",
    ]
    ids = {}
    for nome in dias:
        cur.execute(
            "SELECT id_dia_semana FROM tb_lkp_dias_semanas WHERE nome_dia = %s",
            (nome,),
        )
        row = cur.fetchone()
        if row:
            ids[nome] = row[0]
            continue
        ids[nome] = fetch_id(
            cur,
            "INSERT INTO tb_lkp_dias_semanas (nome_dia) VALUES (%s) RETURNING id_dia_semana",
            (nome,),
        )
    return ids


def popular_status_agendamentos(cur):
    nomes = ["Agendado", "Confirmado", "Recusado", "Realizado", "Cancelado"]
    ids = {}
    for nome in nomes:
        cur.execute(
            "SELECT id_status FROM tb_lkp_status_agendamentos WHERE nome_status = %s",
            (nome,),
        )
        row = cur.fetchone()
        if row:
            ids[nome] = row[0]
            continue
        ids[nome] = fetch_id(
            cur,
            "INSERT INTO tb_lkp_status_agendamentos (nome_status) "
            "VALUES (%s) RETURNING id_status",
            (nome,),
        )
    return ids


def popular_categorias_residuos(cur):
    """Insere as categorias, ou atualiza pontos/teto das que já existem de runs anteriores."""
    ids = {}
    for nome, desc, permite, cor, pontos, limite, *_ in CATEGORIAS:
        cur.execute(
            """UPDATE tb_lkp_categorias_residuos
                  SET pontos_base = %s, limite_pontos_diario = %s
                WHERE nome_categoria = %s
            RETURNING id_categoria""",
            (pontos, limite, nome),
        )
        row = cur.fetchone()
        if row:
            ids[nome] = row[0]
            continue
        ids[nome] = fetch_id(
            cur,
            """INSERT INTO tb_lkp_categorias_residuos
                   (nome_categoria, descricao_material, permite_reciclagem, cor_identificacao,
                    pontos_base, limite_pontos_diario)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id_categoria""",
            (nome, desc, permite, cor, pontos, limite),
        )
    return ids


def popular_niveis_confianca(cur):
    # nivel_confianca_id tem DEFAULT 1 = morador_comum, então precisa ser
    # o primeiro inserido para cair no id certo.
    niveis = [
        ("morador_comum",    1, "Nível padrão de qualquer vínculo aprovado."),
        ("pessoa_confiavel", 3, "Promovido automaticamente ao atingir o trust_score mínimo."),
        ("sindico",          3, "Síndico do condomínio."),
    ]
    ids = {}
    for nome, peso, desc in niveis:
        cur.execute(
            "SELECT id_nivel_confianca FROM tb_lkp_niveis_confianca WHERE nome_nivel = %s",
            (nome,),
        )
        row = cur.fetchone()
        if row:
            ids[nome] = row[0]
            continue
        ids[nome] = fetch_id(
            cur,
            """INSERT INTO tb_lkp_niveis_confianca (nome_nivel, peso_voto, descricao)
               VALUES (%s, %s, %s) RETURNING id_nivel_confianca""",
            (nome, peso, desc),
        )
    return ids


def popular_status_validacoes_postagens(cur):
    # status_validacao_id tem DEFAULT 1 = aprovada, então precisa ser o
    # primeiro inserido para cair no id certo.
    status = [
        ("aprovada",   "Postagem validada pela comunidade/moderação."),
        ("em_analise", "Aguardando votos suficientes da comunidade."),
        ("reprovada",  "Postagem reprovada pela comunidade/moderação."),
    ]
    ids = {}
    for nome, desc in status:
        cur.execute(
            "SELECT id_status_validacao FROM tb_lkp_status_validacoes_postagens WHERE nome_status = %s",
            (nome,),
        )
        row = cur.fetchone()
        if row:
            ids[nome] = row[0]
            continue
        ids[nome] = fetch_id(
            cur,
            """INSERT INTO tb_lkp_status_validacoes_postagens (nome_status, descricao)
               VALUES (%s, %s) RETURNING id_status_validacao""",
            (nome, desc),
        )
    return ids


def popular_tipos_votos_postagens(cur):
    tipos = ["aprovar", "denunciar"]
    ids = {}
    for nome in tipos:
        cur.execute(
            "SELECT id_tipo_voto FROM tb_lkp_tipos_votos_postagens WHERE nome_tipo = %s",
            (nome,),
        )
        row = cur.fetchone()
        if row:
            ids[nome] = row[0]
            continue
        ids[nome] = fetch_id(
            cur,
            "INSERT INTO tb_lkp_tipos_votos_postagens (nome_tipo) VALUES (%s) "
            "RETURNING id_tipo_voto",
            (nome,),
        )
    return ids


def popular_motivos_denuncia(cur):
    motivos = [
        "Não é lixo reciclável",
        "Foto não corresponde à categoria",
        "Foto antiga/reutilizada",
        "Spam/abuso",
    ]
    ids = {}
    for desc in motivos:
        cur.execute(
            "SELECT id_motivo_denuncia FROM tb_lkp_motivos_denuncia WHERE descricao = %s",
            (desc,),
        )
        row = cur.fetchone()
        if row:
            ids[desc] = row[0]
            continue
        ids[desc] = fetch_id(
            cur,
            "INSERT INTO tb_lkp_motivos_denuncia (descricao, ativo) VALUES (%s, TRUE) "
            "RETURNING id_motivo_denuncia",
            (desc,),
        )
    return ids


# ==============================================================================
# 2. ENDEREÇOS E USUÁRIOS (+ SUBTIPOS DE HERANÇA)
# ==============================================================================

def criar_endereco(cur):
    uf, cidade, cep, rua, numero = fk.address_tuple()
    return fetch_id(
        cur,
        """INSERT INTO tb_enderecos
               (cep, estado, cidade, logradouro, numero, complemento)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id_endereco""",
        (cep, uf, cidade, rua, numero, fk.secondary_address()),
    )


def criar_usuario(cur, tipo_usuario_id, perfil=None, desde=None, comercial=False, pioneiro=False):
    """
    Insere tb_enderecos + tb_usuarios + tb_telefones num único round trip
    (CTEs de escrita) e registra o usuário em USUARIOS. Retorna (usuario_id, nome).

    `desde`: data mínima de cadastro (ex.: morador não entra antes do condomínio existir).
    `pioneiro`: cadastro nos primeiros 40% da janela (síndicos, cooperativas, admins).
    Não insere no subtipo -- chame criar_subtipo_sindico ou criar_morador
    logo após, quando aplicável.
    """
    perfil      = perfil or sortear_perfil()
    desde       = desde or AGORA - timedelta(days=DIAS_HISTORICO)
    dias        = max(1, (AGORA - desde).days)
    if pioneiro:
        registro_em = fk.date_time_between(DIAS_HISTORICO, int(DIAS_HISTORICO * 0.6))
    else:
        registro_em = fk.date_time_growth(dias, 0, power=1.3)
    fim = AGORA
    if fk.boolean(round(PERFIS[perfil]["abandono"] * 100)):
        vida = rng.randint(5, 75) if perfil == "churn" else rng.randint(30, 240)
        fim = min(registro_em + timedelta(days=vida), AGORA)
    ativo       = not (fim < AGORA and fk.boolean(40)) and fk.boolean(98)

    nome        = fk.name()
    email       = email_unico(fk, nome)
    senha_hash  = hash_senha(gerar_senha_segura(email))
    uf, cidade, cep, rua, numero = fk.address_tuple()

    usuario_id = fetch_id(
        cur,
        """WITH e AS (
               INSERT INTO tb_enderecos (cep, estado, cidade, logradouro, numero, complemento)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id_endereco
           ), u AS (
               INSERT INTO tb_usuarios
                   (nome_usuario, email_usuario, senha_hash, data_nascimento, cpf,
                    url_avatar, ativo, registro_em, tipo_usuario_id, endereco_id)
               SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, id_endereco FROM e
               RETURNING id_usuario
           ), t AS (
               INSERT INTO tb_telefones (usuario_id, numero_contato, tipo_telefone, ativo)
               SELECT id_usuario, %s, %s, %s FROM u
           )
           SELECT id_usuario FROM u""",
        (
            cep, uf, cidade, rua, numero, fk.secondary_address(),
            nome, email, senha_hash, fk.date_of_birth(18, 75), cpf_unico(fk),
            fk.url(path="avatares", ext="jpg") if fk.boolean(40) else None,
            ativo, registro_em, tipo_usuario_id,
            fk.phone(), fk.random_element(["celular", "fixo", "whatsapp"]), fk.boolean(90),
        ),
    )
    USUARIOS[usuario_id] = dict(perfil=perfil, inicio=registro_em, fim=fim, comercial=comercial)
    return usuario_id, nome


# --- Subtipos de herança ------------------------------------------------------

def criar_subtipo_sindico(cur, usuario_id):
    return fetch_id(
        cur,
        "INSERT INTO tb_sindicos (usuario_id) VALUES (%s) RETURNING id_sindico",
        (usuario_id,),
    )


# ==============================================================================
# 3. CONDOMÍNIOS, TORRES, MORADORES
# ==============================================================================

_codigo_acesso_seq = 0


def proximo_codigo_acesso():
    global _codigo_acesso_seq
    _codigo_acesso_seq += 1
    return fk.codigo_acesso(_codigo_acesso_seq)


def criar_condominio(cur, tipo_condominio_id, sindico_id, nome_fantasia, comercial=False):
    endereco_id  = criar_endereco(cur)
    cnpj         = fk.cnpj() if comercial else (fk.cnpj() if fk.boolean(20) else None)
    codigo_acesso = proximo_codigo_acesso()
    ativo        = fk.boolean(92)

    return fetch_id(
        cur,
        """INSERT INTO tb_condominios
               (nome_condominio, cnpj, codigo_acesso, ativo,
                tipo_condominio_id, sindico_id, endereco_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           RETURNING id_condominio""",
        (nome_fantasia, cnpj, codigo_acesso, ativo,
         tipo_condominio_id, sindico_id, endereco_id),
    )


def criar_torre(cur, condominio_id, nome_torre):
    return fetch_id(
        cur,
        "INSERT INTO tb_torres (nome_torre, condominio_id) "
        "VALUES (%s, %s) RETURNING id_torre",
        (nome_torre, condominio_id),
    )


def criar_morador(cur, usuario_id, condominio_id):
    # tb_moradores só tem usuario_id x condominio_id -- sem unidade/torre.
    # A torre de um ocupante residencial fica só no dict `ocupante` em
    # main.py, para popular tb_postagens.torre_id e as tentativas de quiz.
    return fetch_id(
        cur,
        """INSERT INTO tb_moradores (usuario_id, condominio_id)
           VALUES (%s, %s) RETURNING id_morador""",
        (usuario_id, condominio_id),
    )


def criar_vinculo_condominio(cur, usuario_id, condominio_id, aprovado_por_usuario_id=None,
                             nivel_confianca_id=None, aprovado=None):
    """
    Cria o vínculo em tb_rel_usuarios_condominios com contadores zerados --
    recalcular_trust_scores() preenche os valores reais depois das votações.

    Retorna (id_usuario_condominio, pode_votar): pode_votar = aprovado e sem
    data_saida, exatamente a condição que sp_processar_voto_postagem exige.
    """
    u = USUARIOS[usuario_id]
    data_entrada = min(u["inicio"] + timedelta(hours=rng.randint(1, 96)), AGORA)
    aprovado     = fk.boolean(92) if aprovado is None else aprovado
    saiu         = fk.boolean(5) and nivel_confianca_id is None
    data_saida   = data_no_periodo(data_entrada, AGORA) if saiu else None

    usuario_condominio_id = fetch_id(
        cur,
        """INSERT INTO tb_rel_usuarios_condominios
               (usuario_id, condominio_id, data_entrada, data_saida,
                aprovado, aprovado_por_usuario_id, nivel_confianca_id, trust_score,
                postagens_validadas_sem_contestacao, denuncias_realizadas,
                denuncias_procedentes, taxa_acerto_denuncias)
           VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s, 1),
                   fn_calcular_trust_score(0, 0, 0), 0, 0, 0, NULL)
           RETURNING id_usuario_condominio""",
        (usuario_id, condominio_id, data_entrada, data_saida,
         aprovado, aprovado_por_usuario_id, nivel_confianca_id),
    )
    return usuario_condominio_id, aprovado and not saiu


def recalcular_trust_scores(cur):
    """
    Chama sp_atualizar_trust_score para cada vínculo usuário x condomínio,
    recalculando trust_score/nivel_confianca a partir das postagens e
    votos reais. Loop no servidor: 1 round trip em vez de 1 por vínculo.
    """
    cur.execute(
        """DO $$
           DECLARE r RECORD;
           BEGIN
               FOR r IN SELECT usuario_id, condominio_id FROM tb_rel_usuarios_condominios LOOP
                   CALL sp_atualizar_trust_score(r.usuario_id, r.condominio_id);
               END LOOP;
           END $$"""
    )


# ==============================================================================
# 4. COOPERATIVAS, PONTOS DE COLETA, CATEGORIAS
# ==============================================================================

def criar_cooperativa(cur, usuario_id):
    """Retorna (cooperativa_id, nome, qualidade). `qualidade` (0.55–0.97) é
    latente: move taxa de comparecimento e nota das avaliações da cooperativa."""
    endereco_id = criar_endereco(cur)
    nome        = fk.company()
    cooperativa_id = fetch_id(
        cur,
        """INSERT INTO tb_cooperativas
               (cnpj_cooperativa, nome_cooperativa, email_cooperativa,
                telefone_cooperativa, data_cadastro, usuario_id, endereco_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           RETURNING id_cooperativa""",
        (
            fk.cnpj(), nome, fk.email(nome), fk.phone(),
            USUARIOS[usuario_id]["inicio"], usuario_id, endereco_id,
        ),
    )
    return cooperativa_id, nome, round(rng.uniform(0.55, 0.97), 2)


def criar_ponto_coleta(cur, cooperativa_id, nome_cooperativa):
    endereco_id = criar_endereco(cur)
    nome_ponto  = f"Ecoponto {nome_cooperativa} - {fk.street_name()}"
    return fetch_id(
        cur,
        """INSERT INTO tb_pontos_coletas
               (nome_ponto, endereco_id, cooperativa_id,
                horario_abertura, horario_fechamento, ativo)
           VALUES (%s, %s, %s, %s, %s, %s)
           RETURNING id_ponto_coleta""",
        (nome_ponto, endereco_id, cooperativa_id,
         fk.random_element(["07:00", "08:00", "09:00"]),
         fk.random_element(["17:00", "18:00", "20:00", "22:00"]),
         fk.boolean(92)),
    )


def vincular_categorias_cooperativa(cur, cooperativa_id, categoria_ids_reciclaveis):
    escolhidas = fk.random_elements(
        categoria_ids_reciclaveis, length=rng.randint(3, 5), unique=True
    )
    for cat_id in escolhidas:
        cur.execute(
            """INSERT INTO tb_rel_cooperativas_categorias_materiais
                   (cooperativa_id, categoria_residuo_id)
               VALUES (%s, %s)""",
            (cooperativa_id, cat_id),
        )


def vincular_categorias_ponto_coleta(cur, ponto_coleta_id, categoria_ids_reciclaveis):
    escolhidas = fk.random_elements(
        categoria_ids_reciclaveis, length=rng.randint(2, 4), unique=True
    )
    for cat_id in escolhidas:
        cur.execute(
            """INSERT INTO tb_rel_pontos_coletas_categorias
                   (ponto_coleta_id, categoria_residuo_id)
               VALUES (%s, %s)""",
            (ponto_coleta_id, cat_id),
        )


# ==============================================================================
# 5. POSTAGENS DE DESCARTE + MODERAÇÃO (VOTOS, JANELA 24H, LEDGER)
# ==============================================================================

def gerar_postagens(cur, ocupantes, votantes_por_condominio, categorias,
                    status_em_analise_id, motivos_denuncia_ids):
    """
    Gera as postagens de todos os ocupantes e os votos da comunidade.
    Postagens entram em lote; os votos vão para uma tabela temporária e são
    processados por sp_processar_voto_postagem num loop no servidor (o
    banco calcula peso, saldo e histerese da pontuação -- não o Python).

    Cada postagem sorteia um veredito (aprovar/denunciar) conforme a
    categoria e o perfil do dono; ~93% dos votos seguem o veredito.
    Retorna (qtd_postagens, qtd_votos).
    """
    nomes_cat = [n for n in categorias]
    postagens, meta = [], {}
    for o in ocupantes:
        u = USUARIOS[o["usuario_id"]]
        perfil = PERFIS[u["perfil"]]
        dias_ativos = max(1, (u["fim"] - u["inicio"]).days)
        qtd = round(rng.randint(*perfil["postagens"]) * min(1.0, dias_ativos / 180))
        pesos = [_META_CATEGORIA[n][7 if u["comercial"] else 6] for n in nomes_cat]
        data_postagem = None
        for _ in range(qtd):
            nome_cat = rng.choices(nomes_cat, weights=pesos)[0]
            # ~35% saem em rajada (vários itens descartados no mesmo dia) --
            # é o que faz o teto diário de pontos da categoria aparecer.
            if data_postagem and fk.boolean(35):
                data_postagem = min(data_postagem + timedelta(minutes=rng.randint(1, 40)), u["fim"])
            else:
                data_postagem = data_no_periodo(u["inicio"], u["fim"], u["comercial"])
            chance = _META_CATEGORIA[nome_cat][8] + {"power": 6, "churn": -12}.get(u["perfil"], 0)
            aprovar = fk.boolean(chance)
            # triagem automática (modelo fraco): acerta ~85%, confiança mais baixa quando erra
            triagem_ok = fk.boolean(88) if aprovar else fk.boolean(30)
            confianca = round(rng.uniform(70, 99) if triagem_ok == aprovar else rng.uniform(40, 80), 2)
            hash_foto = hash_foto_unico(f"{o['usuario_id']}-{nome_cat}-{data_postagem.isoformat()}")
            postagens.append((
                o["usuario_id"], o["condominio_id"], o.get("torre_id"), categorias[nome_cat],
                fk.url(path="postagens", ext="jpg"), hash_foto,
                data_postagem - timedelta(seconds=rng.randint(20, 1800)), data_postagem,
                status_em_analise_id, 0, triagem_ok, confianca,
            ))
            meta[hash_foto] = (o["usuario_id"], o["condominio_id"], data_postagem, aprovar)

    # saldo_confianca nasce em 0 e status em_analise (o DEFAULT da coluna é
    # aprovada, mas toda postagem nova aguarda a comunidade). data_limite_analise
    # fica no DEFAULT now()+24h para a procedure aceitar os votos; o
    # encerramento depois ajusta para data_postagem + 24h.
    linhas = execute_values(
        cur,
        """INSERT INTO tb_postagens
               (usuario_id, condominio_id, torre_id, categoria_id, url_foto, hash_foto,
                capturada_em, data_postagem, status_validacao_id, saldo_confianca,
                triagem_automatica_aprovada, triagem_automatica_confianca)
           VALUES %s RETURNING id_postagem, hash_foto""",
        postagens, page_size=1000, fetch=True,
    )

    votos = []
    for postagem_id, hash_foto in linhas:
        dono, condominio_id, data_postagem, aprovar = meta[hash_foto]
        candidatos = [
            v for v in votantes_por_condominio.get(condominio_id, [])
            if v != dono and USUARIOS[v]["inicio"] <= data_postagem <= USUARIOS[v]["fim"]
        ]
        if not candidatos:
            continue
        qtd = min(rng.randint(*VOTOS_POR_POSTAGEM), len(candidatos))
        votantes = amostra_ponderada(
            candidatos, [PERFIS[USUARIOS[v]["perfil"]]["peso_voto"] for v in candidatos], qtd
        )
        minutos = sorted(rng.uniform(2, 23 * 60) for _ in votantes)
        for usuario_id, minuto in zip(votantes, minutos):
            segue = fk.boolean(93)
            tipo = "aprovar" if aprovar == segue else "denunciar"
            votos.append([
                postagem_id, usuario_id, tipo,
                fk.random_element(motivos_denuncia_ids) if tipo == "denunciar" else None,
                fk.sentence(6) if fk.boolean(25) else None,
                min(data_postagem + timedelta(minutes=minuto), AGORA),
            ])

    votos.sort(key=lambda v: (v[0], v[5]))
    cur.execute(
        """DROP TABLE IF EXISTS tmp_votos;
           CREATE TEMP TABLE tmp_votos (
               ordem INTEGER PRIMARY KEY, postagem_id INTEGER, usuario_id INTEGER,
               tipo_voto VARCHAR(20), motivo_denuncia_id INTEGER,
               comentario VARCHAR(255), votado_em TIMESTAMPTZ)"""
    )
    execute_values(cur, "INSERT INTO tmp_votos VALUES %s",
                   [[i] + v for i, v in enumerate(votos)], page_size=5000)
    lote = 5000
    for ini in range(0, len(votos), lote):
        print(f"      votos {ini + 1}-{min(ini + lote, len(votos))} de {len(votos)}", flush=True)
        cur.execute(
            f"""DO $$
                DECLARE r RECORD;
                BEGIN
                    FOR r IN SELECT * FROM tmp_votos
                              WHERE ordem >= {ini} AND ordem < {ini + lote} ORDER BY ordem LOOP
                        CALL sp_processar_voto_postagem(r.postagem_id, r.usuario_id, r.tipo_voto,
                                                        r.motivo_denuncia_id, r.comentario);
                    END LOOP;
                END $$"""
        )
    # votado_em tem DEFAULT now(); traz de volta para a janela real da postagem.
    cur.execute(
        """UPDATE tb_rel_votos_postagens v
              SET votado_em = t.votado_em
             FROM tmp_votos t
            WHERE v.postagem_id = t.postagem_id AND v.usuario_id = t.usuario_id;
           DROP TABLE tmp_votos"""
    )
    return len(postagens), len(votos)


def encerrar_janelas_postagens(cur, seed):
    """
    Fecha a janela de 24h de cada postagem via sp_encerrar_janela_postagem
    (>=0 aprovada, -1..-4 em_analise, <=-5 reprovada) e, para ~60% das que
    ficaram em_analise há mais de 3 dias, simula a decisão manual do síndico
    via sp_decidir_postagem_analise. Postagens das últimas 24h continuam
    abertas (fila de moderação). As procedures carimbam resolvido_em = now();
    aqui ele volta para a data real do fechamento.
    """
    cur.execute(
        """UPDATE tb_postagens SET data_limite_analise = data_postagem + INTERVAL '24 hours';

           DO $$
           DECLARE r RECORD;
           BEGIN
               FOR r IN SELECT id_postagem FROM tb_postagens
                         WHERE resolvido_em IS NULL AND data_limite_analise <= now()
                         ORDER BY id_postagem LOOP
                   CALL sp_encerrar_janela_postagem(r.id_postagem);
               END LOOP;
           END $$;

           UPDATE tb_postagens SET resolvido_em = data_limite_analise WHERE resolvido_em IS NOT NULL;"""
    )
    cur.execute("SELECT setseed(%s)", ((seed % 1000) / 1000.0,))
    cur.execute(
        """DO $$
           DECLARE r RECORD;
           BEGIN
               FOR r IN SELECT p.id_postagem
                          FROM tb_postagens p
                          JOIN tb_lkp_status_validacoes_postagens s
                            ON s.id_status_validacao = p.status_validacao_id
                         WHERE s.nome_status = 'em_analise'
                           AND p.data_limite_analise < now() - INTERVAL '3 days'
                         ORDER BY p.id_postagem LOOP
                   IF random() < 0.6 THEN
                       CALL sp_decidir_postagem_analise(r.id_postagem, random() < 0.45);
                       UPDATE tb_postagens
                          SET resolvido_em = data_limite_analise
                                             + make_interval(hours => 1 + floor(random() * 72)::INT)
                        WHERE id_postagem = r.id_postagem;
                   END IF;
               END LOOP;
           END $$"""
    )


def registrar_ledger_pontos(cur, seed):
    """
    Popula tb_movimentacoes_pontos como a API faria:
      - CREDITO provisório na postagem, valor de fn_pontos_disponiveis_postagem
        (respeita o teto diário -- com teto estourado não há crédito);
      - ESTORNO quando a pontuação ficou inativa (saldo <= -5 / reprovada);
      - RESTAURACAO quando caiu e depois voltou a ativa;
      - CREDITO de quiz na 1a tentativa aprovada de cada usuário x quiz.
    Só postagens já resolvidas são reconciliadas; as abertas mantêm a flag
    pontuacao_reconciliacao_pendente. ~3% dos eventos recentes ficam sem
    sincronizar no Redis (fila de retry).
    """
    cur.execute(
        """DO $$
           DECLARE r RECORD; v_pontos INTEGER;
           BEGIN
               FOR r IN SELECT id_postagem, usuario_id, condominio_id, torre_id, categoria_id, data_postagem
                          FROM tb_postagens ORDER BY data_postagem LOOP
                   v_pontos := fn_pontos_disponiveis_postagem(r.usuario_id, r.categoria_id, r.data_postagem);
                   IF v_pontos > 0 THEN
                       INSERT INTO tb_movimentacoes_pontos
                           (usuario_id, condominio_id, torre_id, categoria_id, origem_tipo, postagem_id,
                            tipo_movimentacao, pontos, idempotency_key, ocorrido_em)
                       VALUES (r.usuario_id, r.condominio_id, r.torre_id, r.categoria_id, 'POSTAGEM',
                               r.id_postagem, 'CREDITO', v_pontos,
                               'POSTAGEM:' || r.id_postagem || ':CREDITO', r.data_postagem);
                   END IF;
               END LOOP;
           END $$;

           INSERT INTO tb_movimentacoes_pontos
               (usuario_id, condominio_id, torre_id, categoria_id, origem_tipo, postagem_id,
                tipo_movimentacao, pontos, movimentacao_referencia_id, idempotency_key, ocorrido_em)
           SELECT m.usuario_id, m.condominio_id, m.torre_id, m.categoria_id, 'POSTAGEM', m.postagem_id,
                  'ESTORNO', m.pontos, m.id_movimentacao,
                  'POSTAGEM:' || m.postagem_id || ':ESTORNO:1',
                  LEAST(p.data_postagem + INTERVAL '12 hours', p.resolvido_em)
             FROM tb_movimentacoes_pontos m
             JOIN tb_postagens p ON p.id_postagem = m.postagem_id
            WHERE m.tipo_movimentacao = 'CREDITO'
              AND p.resolvido_em IS NOT NULL
              AND (p.pontuacao_ativa = FALSE OR p.pontuacao_reconciliacao_pendente);

           INSERT INTO tb_movimentacoes_pontos
               (usuario_id, condominio_id, torre_id, categoria_id, origem_tipo, postagem_id,
                tipo_movimentacao, pontos, movimentacao_referencia_id, idempotency_key, ocorrido_em)
           SELECT m.usuario_id, m.condominio_id, m.torre_id, m.categoria_id, 'POSTAGEM', m.postagem_id,
                  'RESTAURACAO', m.pontos, m.id_movimentacao,
                  'POSTAGEM:' || m.postagem_id || ':RESTAURACAO:1', p.resolvido_em
             FROM tb_movimentacoes_pontos m
             JOIN tb_postagens p ON p.id_postagem = m.postagem_id
            WHERE m.tipo_movimentacao = 'CREDITO'
              AND p.resolvido_em IS NOT NULL
              AND p.pontuacao_ativa AND p.pontuacao_reconciliacao_pendente;

           UPDATE tb_postagens SET pontuacao_reconciliacao_pendente = FALSE
            WHERE resolvido_em IS NOT NULL AND pontuacao_reconciliacao_pendente;

           INSERT INTO tb_movimentacoes_pontos
               (usuario_id, condominio_id, torre_id, origem_tipo, tentativa_quiz_id,
                tipo_movimentacao, pontos, idempotency_key, ocorrido_em)
           SELECT DISTINCT ON (t.usuario_id, t.quiz_id)
                  t.usuario_id, t.condominio_id, t.torre_id, 'QUIZ', t.id_tentativa,
                  'CREDITO', q.pontos_recompensa, 'QUIZ:' || t.id_tentativa || ':CREDITO', t.concluido_em
             FROM tb_tentativas_quiz t
             JOIN tb_quizzes q ON q.id_quiz = t.quiz_id
            WHERE t.aprovado
            ORDER BY t.usuario_id, t.quiz_id, t.concluido_em;"""
    )
    cur.execute("SELECT setseed(%s)", ((seed % 997) / 997.0,))
    cur.execute(
        """UPDATE tb_movimentacoes_pontos
              SET redis_sincronizado = TRUE,
                  redis_sincronizado_em = ocorrido_em + make_interval(secs => 0.2 + random() * 5),
                  tentativas_sync_redis = CASE WHEN random() < 0.04 THEN 2 ELSE 1 END
            WHERE ocorrido_em < now() - INTERVAL '2 days' OR random() < 0.9;

           UPDATE tb_movimentacoes_pontos
              SET tentativas_sync_redis = 1 + floor(random() * 5)::INT,
                  ultimo_erro_redis = (ARRAY['Connection reset by peer',
                                             'READONLY You can''t write against a read only replica.',
                                             'Timeout after 2000 ms'])[1 + floor(random() * 3)::INT]
            WHERE NOT redis_sincronizado AND random() < 0.5;"""
    )


# ==============================================================================
# 6. AGENDAMENTOS, VISITAS, RECORRÊNCIAS E AVALIAÇÕES
# ==============================================================================

def criar_agendamento(cur, condominio_id, cooperativa_id, status_ids, data_inicio,
                      status_final, recorrente):
    """
    Insere como "Agendado" e, se o status final for outro, faz o UPDATE --
    a trigger de auditoria registra a transição como no app.
    possui_recorrencia é setado direto aqui -- não há trigger que
    recalcule a partir de tb_rel_recorrencias_agendamentos.
    """
    data_fim = data_inicio + timedelta(hours=rng.choice([1, 2, 3]))
    agendamento_id = fetch_id(
        cur,
        """INSERT INTO tb_agendamentos_coletas
               (condominio_id, cooperativa_id, status_agendamento_id,
                data_inicio, data_fim, possui_recorrencia)
           VALUES (%s, %s, %s, %s, %s, %s)
           RETURNING id_agendamento_coleta""",
        (condominio_id, cooperativa_id, status_ids["Agendado"],
         data_inicio, data_fim, recorrente),
    )
    if status_final != "Agendado":
        cur.execute(
            "UPDATE tb_agendamentos_coletas SET status_agendamento_id = %s WHERE id_agendamento_coleta = %s",
            (status_ids[status_final], agendamento_id),
        )
    return agendamento_id


def criar_recorrencia(cur, agendamento_coleta_id, dia_semana_id):
    cur.execute(
        """INSERT INTO tb_rel_recorrencias_agendamentos
               (agendamento_coleta_id, dia_semana_id)
           VALUES (%s, %s)""",
        (agendamento_coleta_id, dia_semana_id),
    )


def criar_visita(cur, agendamento_coleta_id, data_visita, foi_realizada=False,
                 houve_confirmacao=False, confirmado_em=None, observacao=None):
    return fetch_id(
        cur,
        """INSERT INTO tb_visitas_coletas
               (agendamento_coleta_id, data_visita,
                foi_realizada, houve_confirmacao, confirmado_em, observacao)
           VALUES (%s, %s, %s, %s, %s, %s)
           RETURNING id_visita_coleta""",
        (agendamento_coleta_id, data_visita, foi_realizada,
         houve_confirmacao, confirmado_em, observacao),
    )


def criar_avaliacao_visita(cur, visita_coleta_id, usuario_avaliador_id, qualidade,
                           foi_realizada, data_visita):
    """Nota puxada pela qualidade da cooperativa e por a coleta ter acontecido."""
    base = 1 + 4 * qualidade if foi_realizada else 1.6
    nota = min(5, max(1, round(rng.gauss(base, 0.8))))
    comentarios = {
        5: "Coleta pontual e equipe muito educada.",
        4: "Coleta ok, pequeno atraso.",
        3: "Atendeu, mas deixou parte do material.",
        2: "Atrasou bastante e não avisou.",
        1: "Não compareceu no horário combinado.",
    }
    cur.execute(
        """INSERT INTO tb_avaliacoes_visitas_coletas
               (visita_coleta_id, usuario_avaliador_id, nota, comentario, avaliado_em)
           VALUES (%s, %s, %s, %s, %s)""",
        (
            visita_coleta_id, usuario_avaliador_id, nota,
            comentarios[nota] if fk.boolean(60) else None,
            min(data_visita + timedelta(hours=rng.randint(1, 72)), AGORA),
        ),
    )


# ==============================================================================
# 7. CURSOS, AULAS, QUIZZES E PROGRESSO
#
# Conteúdo real da trilha EcoCiente (40 cursos, 238 aulas, 20 quizzes,
# 246 perguntas, 840 alternativas), carregado de utils/data/curriculo_ecociente.json.
# Cada quiz é ancorado na última aula do seu 1o "curso relacionado" (o quiz
# funciona como revisão de fechamento daquele curso); tb_quizzes.aula_id é
# UNIQUE, então cada quiz precisa de uma aula própria -- só uma fração das
# 238 aulas tem quiz associado, o resto fica só como conteúdo de curso.
# ==============================================================================

_CURRICULO_PATH = os.path.join(os.path.dirname(__file__), "data", "curriculo_ecociente.json")


def _carregar_curriculo():
    with open(_CURRICULO_PATH, encoding="utf-8") as f:
        return json.load(f)


def popular_cursos_e_aulas(cur):
    """
    Popula os 40 cursos e 238 aulas reais da trilha. Retorna
    (cursos_ids, aulas_por_curso) no mesmo formato de antes:
    {titulo_curso: id_curso} e {titulo_curso: [id_aula, ...]} (em ordem).
    """
    curriculo = _carregar_curriculo()

    cursos_ids = {}
    aulas_por_curso = {}
    for curso in curriculo["cursos"]:
        titulo = curso["titulo_curso"]
        cur.execute("SELECT id_curso FROM tb_cursos WHERE titulo_curso = %s", (titulo,))
        row = cur.fetchone()
        if row:
            curso_id = row[0]
        else:
            curso_id = fetch_id(
                cur,
                """INSERT INTO tb_cursos (titulo_curso, descricao_curso, esta_ativo)
                   VALUES (%s, %s, TRUE) RETURNING id_curso""",
                (titulo, curso["descricao_curso"]),
            )
        cursos_ids[titulo] = curso_id

        cur.execute(
            "SELECT id_aula FROM tb_aulas WHERE curso_id = %s ORDER BY ordem", (curso_id,)
        )
        existentes = [r[0] for r in cur.fetchall()]
        if existentes:
            aulas_por_curso[titulo] = existentes
            continue

        aulas = sorted(curso["aulas"], key=lambda a: a["ordem"])
        linhas = execute_values(
            cur,
            "INSERT INTO tb_aulas (curso_id, titulo_aula, conteudo_aula, ordem) VALUES %s RETURNING id_aula",
            [(curso_id, a["titulo_aula"], a["conteudo_aula"], a["ordem"]) for a in aulas],
            fetch=True,
        )
        aulas_por_curso[titulo] = [r[0] for r in linhas]

    return cursos_ids, aulas_por_curso


def popular_quizzes(cur, cursos_ids, aulas_por_curso):
    """
    Cria os 20 quizzes reais da trilha, cada um na última aula do seu curso
    âncora (aulas_por_curso[curso][-1]), com as perguntas/alternativas reais
    do banco de quizzes.

    Retorna {aula_id: {"quiz_id", "nota_minima", "perguntas": [(pergunta_id, [(alt_id, correta), ...]), ...]}}
    -- só as aulas que têm quiz aparecem nesse dict.
    """
    curriculo = _carregar_curriculo()
    quizzes_por_aula = {}

    for quiz in curriculo["quizzes"]:
        curso_id = cursos_ids[quiz["curso_ancora"]]
        aula_id = aulas_por_curso[quiz["curso_ancora"]][-1]

        cur.execute(
            "SELECT id_quiz, nota_minima_aprovacao FROM tb_quizzes WHERE aula_id = %s",
            (aula_id,),
        )
        row = cur.fetchone()
        if row:
            quiz_id, nota_minima = row
        else:
            nota_minima = 70
            # pontos_recompensa precisa superar o maior pontos_base de categoria (30)
            pontos_recompensa = 25 + len(quiz["perguntas"]) * 2
            quiz_id = fetch_id(
                cur,
                """INSERT INTO tb_quizzes
                       (curso_id, aula_id, titulo_quiz, nota_minima_aprovacao, pontos_recompensa)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id_quiz""",
                (curso_id, aula_id, quiz["titulo_quiz"], nota_minima, pontos_recompensa),
            )

        cur.execute(
            "SELECT id_pergunta FROM tb_perguntas_quiz WHERE quiz_id = %s ORDER BY ordem",
            (quiz_id,),
        )
        perguntas_existentes = cur.fetchall()

        perguntas = []
        if perguntas_existentes:
            for (pergunta_id,) in perguntas_existentes:
                cur.execute(
                    "SELECT id_alternativa, correta FROM tb_alternativas_quiz WHERE pergunta_id = %s",
                    (pergunta_id,),
                )
                perguntas.append((pergunta_id, cur.fetchall()))
        else:
            for ordem, pergunta in enumerate(quiz["perguntas"], start=1):
                pergunta_id = fetch_id(
                    cur,
                    """INSERT INTO tb_perguntas_quiz (quiz_id, enunciado, ordem)
                       VALUES (%s, %s, %s) RETURNING id_pergunta""",
                    (quiz_id, pergunta["enunciado"], ordem),
                )
                linhas = execute_values(
                    cur,
                    """INSERT INTO tb_alternativas_quiz (pergunta_id, texto_alternativa, correta)
                       VALUES %s RETURNING id_alternativa, correta""",
                    [(pergunta_id, alt["texto"], alt["correta"]) for alt in pergunta["alternativas"]],
                    fetch=True,
                )
                perguntas.append((pergunta_id, [tuple(r) for r in linhas]))

        quizzes_por_aula[aula_id] = {
            "quiz_id": quiz_id,
            "nota_minima": float(nota_minima),
            "perguntas": perguntas,
        }

    return quizzes_por_aula


def simular_trilhas(cur, usuarios_ensino, ocupante_por_usuario, aulas_por_curso, quizzes_por_aula):
    """
    Cada usuário escolhe N cursos (conforme o perfil) e avança aula a aula,
    em ordem; ao não concluir uma aula, abandona o curso -- gera um funil
    de conclusão real por curso. Quem conclui a última aula de um curso com
    quiz faz a tentativa (e, se reprovar, ~55% tentam de novo).
    Retorna (qtd_matriculas, qtd_tentativas).
    """
    cursos = list(aulas_por_curso.values())
    matriculas, respostas, qtd_tentativas = [], [], 0

    for usuario_id in usuarios_ensino:
        u = USUARIOS[usuario_id]
        perfil = PERFIS[u["perfil"]]
        ocupante = ocupante_por_usuario.get(usuario_id) or {}
        qtd_cursos = rng.randint(*perfil["cursos"])
        for aulas in rng.sample(cursos, min(qtd_cursos, len(cursos))):
            cursor = data_no_periodo(u["inicio"], u["fim"], u["comercial"])
            concluiu_tudo = True
            for aula_id in aulas:
                inicio = cursor
                concluiu = fk.boolean(round(perfil["conclusao"] * 100))
                conclusao = inicio + timedelta(minutes=rng.randint(8, 60 * 24 * 3))
                if conclusao > u["fim"]:
                    concluiu = False
                matriculas.append((usuario_id, aula_id, concluiu, inicio, conclusao if concluiu else None))
                if not concluiu:
                    concluiu_tudo = False
                    break
                cursor = conclusao + timedelta(hours=rng.randint(1, 24 * 6))
                if cursor > u["fim"]:
                    concluiu_tudo = aula_id == aulas[-1]
                    break

            quiz = quizzes_por_aula.get(aulas[-1])
            if concluiu_tudo and quiz:
                acerto = perfil["acerto"]
                quando = min(conclusao + timedelta(minutes=rng.randint(1, 600)), AGORA)
                for _ in range(2):
                    aprovado, quando = _tentativa_quiz(
                        cur, usuario_id, quiz, acerto, quando, respostas,
                        ocupante.get("condominio_id"), ocupante.get("torre_id"),
                    )
                    qtd_tentativas += 1
                    if aprovado or not fk.boolean(55):
                        break
                    acerto = min(0.95, acerto + 0.1)
                    quando = min(quando + timedelta(days=rng.randint(1, 10)), AGORA)

    execute_values(
        cur,
        """INSERT INTO tb_rel_usuarios_cursos
               (usuario_id, aula_id, concluido, data_inicio, data_conclusao) VALUES %s""",
        matriculas, page_size=5000,
    )
    execute_values(
        cur,
        """INSERT INTO tb_rel_respostas_tentativas_quiz
               (tentativa_id, pergunta_id, alternativa_escolhida_id, correta) VALUES %s""",
        respostas, page_size=5000,
    )
    return len(matriculas), qtd_tentativas


def _tentativa_quiz(cur, usuario_id, quiz_info, acerto, iniciado_em, respostas,
                    condominio_id=None, torre_id=None):
    """
    Uma tentativa: responde cada pergunta (acerta com prob. `acerto`), grava
    a tentativa já fechada e acumula as respostas em `respostas` para o
    insert em lote. ~5% são abandonadas no meio (nota/concluido_em nulos).
    Retorna (aprovado, concluido_em).
    """
    perguntas = quiz_info["perguntas"]
    abandonou = fk.boolean(5)
    respondidas = perguntas[: rng.randint(1, len(perguntas) - 1)] if abandonou and len(perguntas) > 1 else perguntas

    escolhas, acertos = [], 0
    for pergunta_id, alternativas in respondidas:
        corretas = [aid for aid, correta in alternativas if correta]
        erradas  = [aid for aid, correta in alternativas if not correta]
        acertou = fk.boolean(round(acerto * 100)) or not erradas
        escolhas.append((pergunta_id, fk.random_element(corretas if acertou else erradas), acertou))
        acertos += acertou

    concluido_em = None if abandonou else min(iniciado_em + timedelta(minutes=rng.randint(3, 25)), AGORA)
    nota = None if abandonou else round(100.0 * acertos / len(perguntas), 2)
    aprovado = nota is not None and nota >= quiz_info["nota_minima"]

    tentativa_id = fetch_id(
        cur,
        """INSERT INTO tb_tentativas_quiz
               (usuario_id, quiz_id, condominio_id, torre_id, nota, aprovado, iniciado_em, concluido_em)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id_tentativa""",
        (usuario_id, quiz_info["quiz_id"], condominio_id, torre_id,
         nota, aprovado, iniciado_em, concluido_em),
    )
    respostas.extend((tentativa_id, p, a, c) for p, a, c in escolhas)
    return aprovado, concluido_em or iniciado_em


# ==============================================================================
# 8. NOTIFICAÇÕES E TOKENS DE API
# ==============================================================================

# Lembretes diários de reciclagem (tipo "motivacional") -- texto real usado
# pelo app, não texto gerado.
_MENSAGENS_MOTIVACIONAIS = [
    "Cada atitude conta! Separe seus recicláveis e faça a diferença. ♻️",
    "Reciclar hoje é cuidar do planeta amanhã. 🌱",
    "Pequenas ações geram grandes mudanças. Que tal reciclar?",
    "Seu reciclável pode ganhar uma nova vida. Separe corretamente!",
    "Vamos juntos deixar o mundo mais sustentável? Comece reciclando!",
    "Menos desperdício, mais consciência. Recicle!",
    "O planeta agradece cada material que você encaminha para a reciclagem.",
    "Que tal transformar seus resíduos em novas oportunidades? Recicle!",
    "Uma embalagem separada hoje pode fazer parte de algo novo amanhã.",
    "Sua atitude faz parte da mudança. Separe seus recicláveis!",
    "Reciclar é simples e o impacto pode ser enorme. Vamos nessa?",
    "Dê uma segunda chance aos materiais: recicle! ♻️",
    "Hoje é um ótimo dia para fazer uma escolha mais sustentável.",
    "Cada reciclável no lugar certo é um passo a mais para um futuro melhor.",
    "Faça sua parte: separe, recicle e inspire outras pessoas!",
    "Seu hábito pode inspirar uma comunidade inteira. Comece reciclando!",
    "Vamos manter os materiais circulando e o desperdício diminuindo?",
    "Mais reciclagem, menos desperdício. Juntos podemos fazer a diferença!",
    "Não deixe a oportunidade passar: separe seus recicláveis hoje!",
    "Uma pequena ação sua pode contribuir para uma grande mudança. Recicle!",
]

_NOTIFICACOES = {
    "seguranca":       ("Alerta de segurança", ["Novo acesso à sua conta detectado.",
                                                "Sua senha foi alterada com sucesso."]),
    "motivacional":    ("Continue reciclando!", _MENSAGENS_MOTIVACIONAIS),
    "lembrete_coleta": ("Coleta se aproximando", ["A coleta seletiva do seu condomínio é amanhã.",
                                                  "Separe os recicláveis: a cooperativa passa hoje."]),
    "aviso_conta":     ("Atualização da sua conta", ["Sua postagem foi validada pela comunidade.",
                                                     "Você subiu no ranking do condomínio!",
                                                     "Novo curso disponível na trilha EcoCiente."]),
}


def popular_notificacoes(cur, usuario_ids):
    """Notificações seguem chegando depois que o usuário some -- como na vida real."""
    linhas = []
    for usuario_id in usuario_ids:
        u = USUARIOS[usuario_id]
        for _ in range(rng.randint(*NOTIFICACOES_POR_USUARIO)):
            tipo = rng.choices(list(_NOTIFICACOES), weights=[1, 5, 3, 3])[0]
            titulo, corpos = _NOTIFICACOES[tipo]
            linhas.append((usuario_id, titulo, rng.choice(corpos), tipo,
                           data_no_periodo(u["inicio"], AGORA, u["comercial"])))
    execute_values(
        cur,
        """INSERT INTO tb_notificacoes
               (usuario_id, titulo_mensagem, corpo_mensagem, tipo_notificacao, data_envio) VALUES %s""",
        linhas, page_size=5000,
    )
    return len(linhas)


def popular_autenticacoes_api(cur, usuario_ids):
    linhas = []
    for usuario_id in usuario_ids:
        u = USUARIOS[usuario_id]
        for _ in range(rng.randint(*TOKENS_API_POR_USUARIO)):
            linhas.append((usuario_id, token_unico(), "Bearer",
                           data_no_periodo(u["inicio"], u["fim"], u["comercial"]),
                           rng.choice([3600, 86400, 604800])))
    # O banco compartilhado criou esta tabela com "expirado_em" (e PK "id"); o
    # schema do repositório usa "expira_em". Aceita as duas.
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = 'tb_autenticacoes_api' "
        "AND column_name IN ('expira_em', 'expirado_em')"
    )
    col_expira = cur.fetchone()[0]
    execute_values(
        cur,
        f"INSERT INTO tb_autenticacoes_api (usuario_id, token, tipo_token, criado_em, {col_expira}) VALUES %s",
        linhas, page_size=5000,
    )
    return len(linhas)


# ==============================================================================
# 9. DAU (ATIVIDADE DIÁRIA)
# ==============================================================================

def dias_ativos(inicio, fim, perfil, comercial, forcados, rnd):
    """
    Dias (date local) em que o usuário abriu o app entre inicio e fim.
    Probabilidade diária = base do perfil x dia da semana x campanha x
    novidade (1a semana) x desgaste; quem abandonou (fim antes de hoje)
    decai até sumir em `fim`.
    Dias em `forcados` (houve postagem/voto/aula/quiz) e o dia do cadastro
    sempre entram.
    """
    base = PERFIS[perfil]["p_dia"]
    total = max(1, (fim - inicio).days)
    dias = set(forcados) | {inicio}
    d = inicio
    while d <= fim:
        idade = (d - inicio).days
        p = base * _peso_dia(d, comercial)
        p *= 1.5 if idade < 7 else max(0.6, 1 - idade / 900)
        if fim < HOJE:
            p *= 1 - 0.85 * idade / total
        if rnd.random() < min(p, 0.97):
            dias.add(d)
        d += timedelta(days=1)
    return sorted(dias)


def popular_atividades_diarias(cur):
    """
    Gera tb_atividades_diarias_usuarios a partir de USUARIOS, forçando como
    ativos os dias com eventos reais já gravados, e consolida tb_metricas_dau
    via sp_consolidar_metricas_dau. Retorna a quantidade de linhas.
    """
    cur.execute(
        """SELECT usuario_id, dia, SUM(n)::INT FROM (
               SELECT usuario_id, (data_postagem AT TIME ZONE 'America/Sao_Paulo')::DATE dia, COUNT(*) n
                 FROM tb_postagens GROUP BY 1, 2
               UNION ALL
               SELECT usuario_id, (votado_em AT TIME ZONE 'America/Sao_Paulo')::DATE, COUNT(*)
                 FROM tb_rel_votos_postagens GROUP BY 1, 2
               UNION ALL
               SELECT usuario_id, (data_inicio AT TIME ZONE 'America/Sao_Paulo')::DATE, COUNT(*)
                 FROM tb_rel_usuarios_cursos GROUP BY 1, 2
               UNION ALL
               SELECT usuario_id, (iniciado_em AT TIME ZONE 'America/Sao_Paulo')::DATE, COUNT(*)
                 FROM tb_tentativas_quiz GROUP BY 1, 2
               UNION ALL
               SELECT usuario_avaliador_id, (avaliado_em AT TIME ZONE 'America/Sao_Paulo')::DATE, COUNT(*)
                 FROM tb_avaliacoes_visitas_coletas GROUP BY 1, 2
           ) x GROUP BY 1, 2"""
    )
    eventos = {}
    for usuario_id, dia, n in cur.fetchall():
        eventos.setdefault(usuario_id, {})[dia] = n

    linhas = []
    for usuario_id, u in USUARIOS.items():
        acoes = eventos.get(usuario_id, {})
        plataforma = rng.choices(["android", "ios", "web"],
                                 weights=[50, 25, 25] if u["comercial"] else [62, 28, 10])[0]
        inicio = u["inicio"].astimezone(TZ).date()
        fim = u["fim"].astimezone(TZ).date()
        for dia in dias_ativos(inicio, fim, u["perfil"], u["comercial"], acoes, rng):
            sessoes = 1 + min(int(rng.expovariate(1.2 if u["perfil"] == "power" else 2.0)), 8)
            minutos = sum(rng.randint(1, 9) for _ in range(sessoes))
            hora = rng.choices(range(24), weights=_PESOS_HORA)[0]
            primeira = datetime(dia.year, dia.month, dia.day, hora, rng.randint(0, 59), tzinfo=TZ)
            ultima = min(primeira + timedelta(minutes=minutos + (sessoes - 1) * rng.randint(20, 180)),
                         datetime(dia.year, dia.month, dia.day, 23, 59, 59, tzinfo=TZ))
            linhas.append((
                usuario_id, dia,
                plataforma if fk.boolean(90) else rng.choice(["android", "ios", "web"]),
                sessoes, minutos, acoes.get(dia, 0) + rng.randint(0, 3 * sessoes),
                primeira, ultima,
            ))

    execute_values(
        cur,
        """INSERT INTO tb_atividades_diarias_usuarios
               (usuario_id, data_atividade, plataforma, qtd_sessoes, minutos_ativos,
                qtd_acoes, primeira_atividade_em, ultima_atividade_em) VALUES %s""",
        linhas, page_size=5000,
    )
    cur.execute("CALL sp_consolidar_metricas_dau(%s, %s)", (min(l[1] for l in linhas), HOJE))
    return len(linhas)


# ==============================================================================
# ATOMICIDADE / LIMPEZA
# ==============================================================================

def limpar_dados_banco(cur):
    """
    TRUNCATE de todas as tabelas de negócio num único comando (o Postgres
    resolve a ordem das FKs). Tabelas tb_lkp_* ficam de fora: são seeds
    fixos reaproveitados entre execuções.
    """
    tabelas = [
        "tb_metricas_dau",
        "tb_atividades_diarias_usuarios",
        "tb_movimentacoes_pontos",
        "tb_autenticacoes_api",
        "tb_notificacoes",
        "tb_log_auditoria_postagens",
        "tb_log_auditoria_agendamentos_coletas",
        "tb_log_auditoria_usuarios_condominios",
        "tb_log_auditoria",
        "tb_rel_respostas_tentativas_quiz",
        "tb_tentativas_quiz",
        "tb_alternativas_quiz",
        "tb_perguntas_quiz",
        "tb_quizzes",
        "tb_rel_usuarios_cursos",
        "tb_aulas",
        "tb_cursos",
        "tb_rel_votos_postagens",
        "tb_postagens",
        "tb_avaliacoes_visitas_coletas",
        "tb_visitas_coletas",
        "tb_rel_recorrencias_agendamentos",
        "tb_agendamentos_coletas",
        "tb_rel_usuarios_condominios",
        "tb_moradores",
        "tb_sindicos",
        "tb_torres",
        "tb_condominios",
        "tb_pontos_coletas",
        "tb_cooperativas",
        "tb_rel_cooperativas_categorias_materiais",
        "tb_rel_pontos_coletas_categorias",
        "tb_enderecos",
        "tb_telefones",
        "tb_usuarios",
    ]
    cur.execute(f"TRUNCATE TABLE {', '.join(tabelas)} RESTART IDENTITY CASCADE")
    print("Banco limpo: dados removidos, estrutura mantida.")