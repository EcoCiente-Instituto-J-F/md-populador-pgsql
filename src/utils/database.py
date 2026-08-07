# ==============================================================================
# EcoCiente – camada de acesso a dados para a carga inicial de massa
# ==============================================================================
import os
import sys
import random
import hashlib
from datetime import timedelta

from .helpers import fetch_id, call_procedure, DSN
from .faker_br import FakerBR

# ==============================================================================
# CONFIGURAÇÃO / VOLUMETRIA
# ==============================================================================

SEED = 42  # fixo → massa reprodutível. Use None para variar a cada run.

N_CONDOMINIOS_RESIDENCIAL   = 4
N_CONDOMINIOS_COMERCIAL     = 2
N_COOPERATIVAS              = 3
N_USUARIOS_COMUM            = 12

TORRES_POR_RESIDENCIAL      = (2, 3)
UNIDADES_POR_TORRE          = (4, 8)
UNIDADES_POR_COMERCIAL      = (5, 10)
CHANCE_UNIDADE_OCUPADA      = 80

PONTOS_COLETA_POR_COOPERATIVA = (2, 3)
POSTAGENS_POR_OCUPANTE        = (0, 6)
NOTIFICACOES_POR_USUARIO      = (2, 5)
AGENDAMENTOS_POR_CONDOMINIO   = (1, 2)
VISITAS_POR_AGENDAMENTO       = (2, 5)

fk  = FakerBR(seed=SEED)
rng = random.Random(SEED)


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
         "Ocupante de unidade em condomínio residencial. Ranking, analytics "
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
        ("Residencial", "Condomínio residencial (tb_torres/tb_unidades habitacionais)."),
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


def popular_tipos_avisos(cur):
    tipos = [
        ("Comunicado",        "Aviso geral do condomínio."),
        ("Manutenção",        "Aviso de manutenção predial."),
        ("Evento",            "Evento ou campanha do condomínio."),
        ("Campanha Ambiental","Campanha de conscientização ambiental/reciclagem."),
        ("Segurança",         "Aviso de segurança do condomínio."),
    ]
    ids = {}
    for nome, desc in tipos:
        cur.execute(
            "SELECT id_tipo_aviso FROM tb_lkp_tipos_avisos WHERE nome_tipo = %s",
            (nome,),
        )
        row = cur.fetchone()
        if row:
            ids[nome] = row[0]
            continue
        ids[nome] = fetch_id(
            cur,
            "INSERT INTO tb_lkp_tipos_avisos (nome_tipo, descricao) "
            "VALUES (%s, %s) RETURNING id_tipo_aviso",
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


def popular_niveis_confianca(cur):
    """
    tb_rel_usuarios_condominios.nivel_confianca_id tem DEFAULT 1 e a
    procedure sp_atualizar_trust_score busca 'pessoa_confiavel' pelo nome
    (ver a.sql). Por isso a ordem de inserção importa: 'morador_comum'
    precisa ser a primeira linha (id 1), já que é o default de todo vínculo
    novo em tb_rel_usuarios_condominios.
    """
    niveis = [
        ("morador_comum",    1, "Morador/usuário comum recém-vinculado ao condomínio."),
        ("pessoa_confiavel", 3, "Promovido automaticamente após acúmulo de trust_score."),
        ("sindico",          3, "Síndico do condomínio."),
    ]
    ids = {}
    for nome, peso_voto, desc in niveis:
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
            "INSERT INTO tb_lkp_niveis_confianca (nome_nivel, peso_voto, descricao) "
            "VALUES (%s, %s, %s) RETURNING id_nivel_confianca",
            (nome, peso_voto, desc),
        )
    return ids


def popular_categorias_residuos(cur):
    categorias = [
        ("Papel",      "Papel e papelão em geral",           True,  "#1565C0"),
        ("Plástico",   "Embalagens e materiais plásticos",   True,  "#F9A825"),
        ("Vidro",      "Garrafas, potes e vidro em geral",   True,  "#2E7D32"),
        ("Metal",      "Latas e metais recicláveis",         True,  "#757575"),
        ("Orgânico",   "Resíduo orgânico / compostável",     True,  "#6D4C41"),
        ("Eletrônico", "Lixo eletrônico (e-waste)",          True,  "#512DA8"),
        ("Rejeito",    "Resíduo não reciclável",             False, "#212121"),
    ]
    ids = {}
    for nome, desc, permite, cor in categorias:
        cur.execute(
            "SELECT id_categoria FROM tb_lkp_categorias_residuos WHERE nome_categoria = %s",
            (nome,),
        )
        row = cur.fetchone()
        if row:
            ids[nome] = row[0]
            continue
        ids[nome] = fetch_id(
            cur,
            """INSERT INTO tb_lkp_categorias_residuos
                   (nome_categoria, descricao_material, permite_reciclagem, cor_identificacao)
               VALUES (%s, %s, %s, %s) RETURNING id_categoria""",
            (nome, desc, permite, cor),
        )
    return ids


# ==============================================================================
# 2. ENDEREÇOS E USUÁRIOS (+ SUBTIPOS DE HERANÇA)
# ==============================================================================

def criar_endereco(cur):
    uf, cidade, cep, rua, numero, lat, lng = fk.address_tuple()
    return fetch_id(
        cur,
        """INSERT INTO tb_enderecos
               (cep, estado, cidade, logradouro, numero, complemento, latitude, longitude)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id_endereco""",
        (cep, uf, cidade, rua, numero, fk.secondary_address(), lat, lng),
    )


def criar_usuario(cur, tipo_usuario_id, n_telefones=(1, 1)):
    """
    Insere em tb_usuarios + tb_telefones.
    Retorna (usuario_id, nome).

    ATENÇÃO: NÃO insere no subtipo (tb_sindicos / tb_usuarios_comuns / tb_moradores /
    tb_cooperativas). Chame a função de subtipo adequada logo após:
        - criar_subtipo_sindico(cur, usuario_id)
        - criar_subtipo_usuario_comum(cur, usuario_id)
        - criar_morador(cur, usuario_id, unidade_id)          ← já existia
        - criar_cooperativa(cur, usuario_id)                  ← já existia
    """
    nome        = fk.name()
    email       = fk.email(nome)
    senha_hash  = fk.password(email)
    nascimento  = fk.date_of_birth(18, 75)
    cpf         = fk.cpf()
    avatar      = fk.url(path="avatares", ext="jpg") if fk.boolean(40) else None
    ativo       = fk.boolean(95)
    registro_em = fk.date_time_between(900, 0)

    usuario_id = fetch_id(
        cur,
        """INSERT INTO tb_usuarios
               (nome_usuario, email_usuario, senha_hash, data_nascimento, cpf_cnpj,
                url_avatar, ativo, registro_em, tipo_usuario_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id_usuario""",
        (nome, email, senha_hash, nascimento, cpf,
         avatar, ativo, registro_em, tipo_usuario_id),
    )

    qtd_tel = rng.randint(*n_telefones)
    for _ in range(qtd_tel):
        cur.execute(
            """INSERT INTO tb_telefones
                   (usuario_id, numero_contato, tipo_telefone, ativo)
               VALUES (%s, %s, %s, %s)""",
            (
                usuario_id,
                fk.phone(),
                fk.random_element(["celular", "fixo", "whatsapp"]),
                fk.boolean(90),
            ),
        )

    return usuario_id, nome


# --- Subtipos de herança ------------------------------------------------------

def criar_subtipo_sindico(cur, usuario_id):
    """
    Insere na tabela tb_sindicos (subtipo de tb_usuarios).
    Retorna id_sindico — que é a FK usada em tb_condominios.sindico_id.
    """
    return fetch_id(
        cur,
        "INSERT INTO tb_sindicos (usuario_id) VALUES (%s) RETURNING id_sindico",
        (usuario_id,),
    )


def criar_subtipo_usuario_comum(cur, usuario_id):
    """
    Insere na tabela tb_usuarios_comuns (subtipo de tb_usuarios).
    Retorna id_usuario_comum.
    """
    return fetch_id(
        cur,
        "INSERT INTO tb_usuarios_comuns (usuario_id) VALUES (%s) RETURNING id_usuario_comum",
        (usuario_id,),
    )


# ==============================================================================
# 3. CONDOMÍNIOS, TORRES, UNIDADES, MORADORES
# ==============================================================================

_codigo_acesso_seq = 0


def proximo_codigo_acesso():
    global _codigo_acesso_seq
    _codigo_acesso_seq += 1
    return fk.codigo_acesso(_codigo_acesso_seq)


def criar_condominio(cur, tipo_condominio_id, sindico_id, nome_fantasia, comercial=False):
    """
    sindico_id: id_sindico da tabela tb_sindicos (FK do modelo com herança),
    NÃO o usuario_id direto.
    """
    endereco_id  = criar_endereco(cur)
    cnpj         = fk.cnpj() if comercial else (fk.cnpj() if fk.boolean(20) else None)
    codigo_acesso = proximo_codigo_acesso()
    ativo        = fk.boolean(95)

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


def criar_unidade(cur, numero, tipo_unidade, torre_id=None, condominio_id=None):
    return fetch_id(
        cur,
        """INSERT INTO tb_unidades (numero_unidade, tipo_unidade, torre_id, condominio_id)
           VALUES (%s, %s, %s, %s) RETURNING id_unidade""",
        (numero, tipo_unidade, torre_id, condominio_id),
    )


def criar_morador(cur, usuario_id, unidade_id):
    """
    Insere na tabela tb_moradores (subtipo de tb_usuarios).
    Retorna id_morador.

    A modelagem atual não possui mais pontuacao_acumulada — o cache de
    pontuação/ranking saiu do relacional (era alimentado por
    historico_pontuacao, que deixou de existir) e não é mais gravado aqui.
    """
    return fetch_id(
        cur,
        """INSERT INTO tb_moradores (usuario_id, unidade_id)
           VALUES (%s, %s) RETURNING id_morador""",
        (usuario_id, unidade_id),
    )


def criar_vinculo_condominio(cur, usuario_id, condominio_id, aprovado_por_usuario_id=None):
    """
    aprovado_por_usuario_id: tb_usuarios.id_usuario (o síndico como usuário,
    não o id_sindico da tabela tb_sindicos).

    Todo INSERT/UPDATE nesta tabela dispara trg_auditoria_usuarios_condominios,
    que grava automaticamente em tb_log_auditoria + tb_log_auditoria_usuarios_condominios
    (aprovado_anterior/novo, data_saida_anterior/novo).
    """
    data_entrada = fk.date_time_between(700, 30)
    aprovado     = fk.boolean(92)
    saiu         = fk.boolean(8)
    data_saida   = fk.date_time_between(29, 0) if saiu else None

    # tb_rel_usuarios_condominios exige NOT NULL em trust_score e nos três
    # contadores (postagens_validadas_sem_contestacao, denuncias_realizadas,
    # denuncias_procedentes) — o schema não tem DEFAULT para essas colunas.
    # Todo vínculo novo começa "zerado"; quem for atualizar os contadores
    # depois deve chamar sp_atualizar_trust_score (que recalcula trust_score
    # via fn_calcular_trust_score) em vez de escrever direto nessas colunas.
    postagens_validadas_sem_contestacao = 0
    denuncias_realizadas                = 0
    denuncias_procedentes               = 0
    trust_score                         = 0  # == fn_calcular_trust_score(0, 0, 0)

    return fetch_id(
        cur,
        """INSERT INTO tb_rel_usuarios_condominios
               (usuario_id, condominio_id, data_entrada, data_saida,
                aprovado, aprovado_por_usuario_id,
                trust_score, postagens_validadas_sem_contestacao,
                denuncias_realizadas, denuncias_procedentes)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id_usuario_condominio""",
        (usuario_id, condominio_id, data_entrada, data_saida,
         aprovado, aprovado_por_usuario_id,
         trust_score, postagens_validadas_sem_contestacao,
         denuncias_realizadas, denuncias_procedentes),
    )


# ==============================================================================
# 4. COOPERATIVAS, PONTOS DE COLETA, CATEGORIAS
# ==============================================================================

def criar_cooperativa(cur, usuario_id):
    """
    tb_cooperativas já é o subtipo de tb_usuarios para Cooperativa —
    usuario_id é a FK 1:1 para tb_usuarios.id_usuario.
    """
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
            fk.date_time_between(900, 60), usuario_id, endereco_id,
        ),
    )
    return cooperativa_id, nome


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
        (nome_ponto, endereco_id, cooperativa_id, "08:00", "18:00", fk.boolean(95)),
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
# 5. POSTAGENS DE DESCARTE
# ==============================================================================

def criar_postagem(cur, usuario_id, condominio_id, categoria_id, data_postagem):
    """
    A modelagem atual não possui mais status_postagem/pontos_gerados (a
    moderação de descarte e a procedure sp_validar_postagem foram removidas
    do banco) — a postagem nasce e permanece só com os dados de origem.

    Todo INSERT/UPDATE/DELETE nesta tabela dispara trg_auditoria_postagens,
    que grava automaticamente em tb_log_auditoria + tb_log_auditoria_postagens.
    """
    # hash_foto, capturada_em e saldo_confianca são NOT NULL sem DEFAULT no
    # schema. capturada_em precisa satisfazer ck_postagens_capturada_em
    # (capturada_em <= data_postagem), então geramos um instante um pouco
    # antes da postagem. hash_foto é UNIQUE, então usamos um valor aleatório
    # por postagem (hex de 64 chars, como um SHA-256).
    hash_foto = hashlib.sha256(
        f"{usuario_id}-{condominio_id}-{categoria_id}-{rng.random()}".encode()
    ).hexdigest()
    capturada_em = data_postagem - timedelta(minutes=rng.randint(1, 30))
    saldo_confianca = 0  # ninguém votou ainda na postagem recém-criada

    return fetch_id(
        cur,
        """INSERT INTO tb_postagens
               (usuario_id, condominio_id, categoria_id, url_foto,
                hash_foto, capturada_em, data_postagem, saldo_confianca)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id_postagem""",
        (
            usuario_id, condominio_id, categoria_id,
            fk.url(path="postagens", ext="jpg"),
            hash_foto, capturada_em, data_postagem, saldo_confianca,
        ),
    )


# ==============================================================================
# 6. AVISOS
# ==============================================================================

def criar_aviso(cur, condominio_id, criado_por_usuario_id, tipo_aviso_id):
    """
    criado_por_usuario_id: tb_usuarios.id_usuario (não id_sindico).
    A FK de tb_avisos aponta para tb_usuarios diretamente.
    """
    cur.execute(
        """INSERT INTO tb_avisos
               (titulo_mensagem, conteudo_mensagem, criado_em,
                condominio_id, criado_por_usuario_id, tipo_aviso_id)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (
            fk.sentence(5).rstrip("."),
            fk.sentence(14),
            fk.date_time_between(365, 0),
            condominio_id,
            criado_por_usuario_id,
            tipo_aviso_id,
        ),
    )


# ==============================================================================
# 7. AGENDAMENTOS, VISITAS, RECORRÊNCIAS E AVALIAÇÕES
#    (usa sp_confirmar_passagem_cooperativa)
# ==============================================================================

def criar_agendamento(cur, condominio_id, cooperativa_id,
                      status_agendamento_id, recorrente):
    """
    Todo INSERT/UPDATE/DELETE nesta tabela dispara
    trg_auditoria_agendamentos_coletas, que grava automaticamente em
    tb_log_auditoria + tb_log_auditoria_agendamentos_coletas (status e datas
    antes/depois).
    """
    data_inicio = fk.date_time_between(180, 0)
    data_fim    = data_inicio + timedelta(hours=2)
    # possui_recorrencia: se recorrente=False não haverá INSERT em
    # tb_rel_recorrencias_agendamentos e a trigger não vai tocar nessa linha.
    return fetch_id(
        cur,
        """INSERT INTO tb_agendamentos_coletas
               (condominio_id, cooperativa_id, status_agendamento_id,
                data_inicio, data_fim, possui_recorrencia)
           VALUES (%s, %s, %s, %s, %s, %s)
           RETURNING id_agendamento_coleta""",
        (condominio_id, cooperativa_id, status_agendamento_id,
         data_inicio, data_fim, recorrente),
    )


def criar_recorrencia(cur, agendamento_coleta_id, dia_semana_id):
    """
    O INSERT nesta tabela dispara trg_atualizar_recorrencia_insert, que
    recalcula tb_agendamentos_coletas.possui_recorrencia.
    """
    cur.execute(
        """INSERT INTO tb_rel_recorrencias_agendamentos
               (agendamento_coleta_id, dia_semana_id)
           VALUES (%s, %s)""",
        (agendamento_coleta_id, dia_semana_id),
    )


def criar_visita(cur, agendamento_coleta_id, data_visita):
    return fetch_id(
        cur,
        """INSERT INTO tb_visitas_coletas
               (agendamento_coleta_id, data_visita,
                foi_realizada, houve_confirmacao, confirmado_em, observacao)
           VALUES (%s, %s, FALSE, FALSE, NULL, NULL)
           RETURNING id_visita_coleta""",
        (agendamento_coleta_id, data_visita),
    )


def confirmar_visita(cur, visita_id, confirmou, observacao=None):
    call_procedure(
        cur,
        "CALL sp_confirmar_passagem_cooperativa(%s, %s, %s)",
        (visita_id, confirmou, observacao),
    )
    cur.execute(
        "UPDATE tb_visitas_coletas SET foi_realizada = %s WHERE id_visita_coleta = %s",
        (confirmou, visita_id),
    )


def criar_avaliacao_visita(cur, visita_coleta_id, usuario_avaliador_id):
    """
    usuario_avaliador_id: tb_usuarios.id_usuario do síndico avaliador.
    """
    cur.execute(
        """INSERT INTO tb_avaliacoes_visitas_coletas
               (visita_coleta_id, usuario_avaliador_id, nota, comentario, avaliado_em)
           VALUES (%s, %s, %s, %s, %s)""",
        (
            visita_coleta_id,
            usuario_avaliador_id,
            rng.randint(1, 5),
            fk.sentence(6) if fk.boolean(60) else None,
            fk.date_time_between(30, 0),
        ),
    )


# ==============================================================================
# 8. CURSOS, AULAS E PROGRESSO
# ==============================================================================

def popular_cursos_e_aulas(cur):
    """
    Dois cursos do domínio do produto:
      1. Reciclagem de Materiais
      2. Compostagem Residencial e de Apartamento (Coletiva)
    """
    cursos_def = [
        (
            "Reciclagem de Materiais",
            "Explica os tipos de materiais recicláveis e onde/como reciclar cada um.",
            [
                "O que é reciclagem e por que ela importa",
                "Plásticos: tipos, símbolos e como separar",
                "Papel e papelão: o que pode e o que não pode reciclar",
                "Vidro e metal: cuidados no descarte",
                "Lixo eletrônico: pontos de coleta especializados",
                "Como montar a separação correta em casa",
            ],
        ),
        (
            "Compostagem Residencial e de Apartamento (Coletiva)",
            "Como reciclar resíduo orgânico através da compostagem doméstica e coletiva.",
            [
                "Introdução à compostagem: o que pode ir na composteira",
                "Montando uma composteira em apartamento",
                "Compostagem coletiva no condomínio: como organizar",
                "Resolvendo problemas comuns (odor, moscas, excesso de umidade)",
                "Usando o composto na horta e em vasos",
            ],
        ),
    ]

    cursos_ids = {}
    aulas_ids  = {}
    for titulo, descricao, lista_aulas in cursos_def:
        cur.execute(
            "SELECT id_curso FROM tb_cursos WHERE titulo_curso = %s", (titulo,)
        )
        row = cur.fetchone()
        if row:
            curso_id = row[0]
        else:
            curso_id = fetch_id(
                cur,
                """INSERT INTO tb_cursos (titulo_curso, descricao_curso, esta_ativo)
                   VALUES (%s, %s, TRUE) RETURNING id_curso""",
                (titulo, descricao),
            )
        cursos_ids[titulo] = curso_id

        cur.execute(
            "SELECT id_aula FROM tb_aulas WHERE curso_id = %s ORDER BY ordem",
            (curso_id,),
        )
        existentes = [r[0] for r in cur.fetchall()]
        if existentes:
            aulas_ids[titulo] = existentes
            continue

        ids_aula = []
        for ordem, titulo_aula in enumerate(lista_aulas, start=1):
            aula_id = fetch_id(
                cur,
                """INSERT INTO tb_aulas (curso_id, titulo_aula, conteudo_aula, ordem)
                   VALUES (%s, %s, %s, %s) RETURNING id_aula""",
                (curso_id, titulo_aula, fk.sentence(25), ordem),
            )
            ids_aula.append(aula_id)
        aulas_ids[titulo] = ids_aula

    return cursos_ids, aulas_ids


def matricular_usuario_em_aulas(cur, usuario_id, lista_aula_ids):
    """
    INSERT com concluido=FALSE → UPDATE para TRUE (quando aplicável).

    A modelagem atual não possui mais gamificação por pontos: o UPDATE
    apenas registra a conclusão (concluido/data_conclusao) e não dispara
    mais nenhuma trigger de pontuação (historico_pontuacao deixou de
    existir).
    """
    progresso = []
    for aula_id in lista_aula_ids:
        vai_concluir = fk.boolean(55)
        data_inicio  = fk.date_time_between(180, 1)
        uc_id = fetch_id(
            cur,
            """INSERT INTO tb_rel_usuarios_cursos
                   (usuario_id, aula_id, concluido, data_inicio, data_conclusao)
               VALUES (%s, %s, FALSE, %s, NULL)
               RETURNING id_usuario_curso""",
            (usuario_id, aula_id, data_inicio),
        )
        progresso.append((uc_id, vai_concluir, data_inicio))

    for uc_id, vai_concluir, data_inicio in progresso:
        if not vai_concluir:
            continue
        data_conclusao = data_inicio + timedelta(days=rng.randint(1, 14))
        cur.execute(
            """UPDATE tb_rel_usuarios_cursos
               SET concluido = TRUE, data_conclusao = %s
               WHERE id_usuario_curso = %s""",
            (data_conclusao, uc_id),
        )


# ==============================================================================
# 9. NOTIFICAÇÕES
# ==============================================================================

def criar_notificacoes_usuario(cur, usuario_id, qtd):
    tipos = ["seguranca", "motivacional", "lembrete_coleta", "aviso_conta"]
    titulos = {
        "seguranca":       "Alerta de segurança",
        "motivacional":    "Continue reciclando!",
        "lembrete_coleta": "Coleta se aproximando",
        "aviso_conta":     "Atualização da sua conta",
    }
    for _ in range(qtd):
        tipo       = fk.random_element(tipos)
        foi_lida   = fk.boolean(65)
        data_envio = fk.date_time_between(120, 0)
        data_leitura = (
            data_envio + timedelta(hours=rng.randint(1, 48)) if foi_lida else None
        )
        cur.execute(
            """INSERT INTO tb_notificacoes
                   (usuario_id, titulo_mensagem, corpo_mensagem,
                    tipo_notificacao, foi_lida, data_envio, data_leitura)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                usuario_id, titulos[tipo], fk.sentence(10),
                tipo, foi_lida, data_envio, data_leitura,
            ),
        )


# ==============================================================================
# ATOMICIDADE / LIMPEZA
# ==============================================================================

def limpar_dados_banco(cur):
    """
    TRUNCATE em ordem de dependência (filhos antes dos pais).

    Inclui tb_sindicos e tb_usuarios_comuns (subtipos de tb_usuarios) e os 3 subtipos
    de auditoria (tb_log_auditoria_postagens, tb_log_auditoria_agendamentos_coletas,
    tb_log_auditoria_usuarios_condominios), truncados antes do supertipo
    tb_log_auditoria. historico_pontuacao e regras_pontuacao NÃO aparecem mais
    aqui: deixaram de existir na modelagem atual.

    Tabelas de domínio/lookup (tb_lkp_tipos_usuarios, tb_lkp_tipos_condominios,
    tb_lkp_tipos_avisos, tb_lkp_status_agendamentos, tb_lkp_dias_semanas,
    tb_lkp_categorias_residuos, tb_lkp_tipos_eventos_auditados,
    tb_lkp_tipos_operacoes_auditoria) são mantidas propositalmente fora desta
    lista: são seeds fixos, populados uma única vez e reaproveitados entre
    execuções.
    """
    tabelas = [
        "tb_notificacoes",
        "tb_log_auditoria_postagens",
        "tb_log_auditoria_agendamentos_coletas",
        "tb_log_auditoria_usuarios_condominios",
        "tb_log_auditoria",
        "tb_postagens",
        "tb_avaliacoes_visitas_coletas",
        "tb_visitas_coletas",
        "tb_rel_recorrencias_agendamentos",
        "tb_agendamentos_coletas",
        "tb_rel_usuarios_cursos",
        "tb_aulas",
        "tb_cursos",
        "tb_avisos",
        "tb_rel_usuarios_condominios",
        "tb_moradores",
        "tb_usuarios_comuns",
        "tb_sindicos",
        "tb_unidades",
        "tb_torres",
        "tb_condominios",
        "tb_cooperativas",
        "tb_pontos_coletas",
        "tb_rel_cooperativas_categorias_materiais",
        "tb_rel_pontos_coletas_categorias",
        "tb_enderecos",
        "tb_telefones",
        "tb_usuarios",
    ]
    for tabela in tabelas:
        cur.execute(f"TRUNCATE TABLE {tabela} CASCADE")
    print("Banco limpo: dados removidos, estrutura mantida.")