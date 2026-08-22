# ==============================================================================
# EcoCiente – camada de acesso a dados para a carga inicial de massa
# ==============================================================================
import random
import hashlib
import psycopg2
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
MORADORES_POR_TORRE         = (2, 5)
USUARIOS_POR_COMERCIAL      = (4, 8)

PONTOS_COLETA_POR_COOPERATIVA = (2, 3)
POSTAGENS_POR_OCUPANTE        = (0, 6)
VOTOS_POR_POSTAGEM            = (0, 6)
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


def criar_usuario(cur, tipo_usuario_id, n_telefones=(1, 1)):
    """
    Insere em tb_usuarios + tb_telefones. Retorna (usuario_id, nome).

    Não insere no subtipo -- chame criar_subtipo_sindico ou criar_morador
    logo após, quando aplicável. "Usuário Comum", "Cooperativa" e
    "Administrador" não têm tabela de subtipo.
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
               (nome_usuario, email_usuario, senha_hash, data_nascimento, cpf,
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


def criar_vinculo_condominio(cur, usuario_id, condominio_id, aprovado_por_usuario_id=None):
    """
    Cria o vínculo em tb_rel_usuarios_condominios com contadores de
    confiança plausíveis (trust_score via fn_calcular_trust_score) --
    recalcular_trust_scores() depois substitui pelos valores reais.

    Retorna (id_usuario_condominio, aprovado): `aprovado` indica se esse
    usuário pode votar em postagens do condomínio via
    sp_processar_voto_postagem.
    """
    data_entrada = fk.date_time_between(700, 30)
    aprovado     = fk.boolean(92)
    saiu         = fk.boolean(8)
    data_saida   = fk.date_time_between(29, 0) if saiu else None

    postagens_validadas   = rng.randint(0, 15)
    denuncias_realizadas  = rng.randint(0, 4)
    denuncias_procedentes = rng.randint(0, denuncias_realizadas)
    taxa_acerto_denuncias = (
        round(100.0 * denuncias_procedentes / denuncias_realizadas, 2)
        if denuncias_realizadas > 0 else None
    )

    cur.execute(
        "SELECT fn_calcular_trust_score(%s, %s, %s)",
        (postagens_validadas, denuncias_realizadas, denuncias_procedentes),
    )
    trust_score = cur.fetchone()[0]

    usuario_condominio_id = fetch_id(
        cur,
        """INSERT INTO tb_rel_usuarios_condominios
               (usuario_id, condominio_id, data_entrada, data_saida,
                aprovado, aprovado_por_usuario_id, trust_score,
                postagens_validadas_sem_contestacao, denuncias_realizadas,
                denuncias_procedentes, taxa_acerto_denuncias)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id_usuario_condominio""",
        (usuario_id, condominio_id, data_entrada, data_saida,
         aprovado, aprovado_por_usuario_id, trust_score,
         postagens_validadas, denuncias_realizadas,
         denuncias_procedentes, taxa_acerto_denuncias),
    )
    return usuario_condominio_id, aprovado


def recalcular_trust_scores(cur):
    """
    Chama sp_atualizar_trust_score para cada vínculo usuário x condomínio,
    recalculando trust_score/nivel_confianca a partir das postagens e
    votos reais. Rodar depois de simular postagens e votos.
    """
    cur.execute("SELECT usuario_id, condominio_id FROM tb_rel_usuarios_condominios")
    vinculos = cur.fetchall()
    for usuario_id, condominio_id in vinculos:
        call_procedure(
            cur, "CALL sp_atualizar_trust_score(%s, %s)", (usuario_id, condominio_id)
        )


# ==============================================================================
# 4. COOPERATIVAS, PONTOS DE COLETA, CATEGORIAS
# ==============================================================================

def criar_cooperativa(cur, usuario_id):
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
# 5. POSTAGENS DE DESCARTE + MODERAÇÃO (VOTOS)
# ==============================================================================

def criar_postagem(cur, usuario_id, condominio_id, categoria_id, data_postagem, torre_id=None):
    # saldo_confianca nasce em 0 -- simular_votos_postagem() é quem
    # incrementa via sp_processar_voto_postagem. status_validacao_id fica
    # no DEFAULT (aprovada) até algum voto resolver a postagem.
    capturada_em = data_postagem - timedelta(minutes=rng.randint(1, 30))
    hash_foto = hashlib.sha256(
        f"{usuario_id}-{condominio_id}-{categoria_id}-"
        f"{data_postagem.isoformat()}-{rng.random()}".encode("utf-8")
    ).hexdigest()

    return fetch_id(
        cur,
        """INSERT INTO tb_postagens
               (usuario_id, condominio_id, torre_id, categoria_id, url_foto,
                hash_foto, capturada_em, data_postagem, saldo_confianca)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id_postagem""",
        (
            usuario_id, condominio_id, torre_id, categoria_id,
            fk.url(path="postagens", ext="jpg"), hash_foto,
            capturada_em, data_postagem, 0,
        ),
    )


def simular_votos_postagem(cur, postagem_id, usuario_dono_id, votantes_do_condominio,
                            motivos_denuncia_ids):
    """
    Simula de 0 a VOTOS_POR_POSTAGEM votos via sp_processar_voto_postagem,
    que calcula o peso do voto, atualiza saldo_confianca e resolve o
    status da postagem ao atingir os limiares. votantes_do_condominio deve
    conter só usuario_ids com vínculo aprovado=TRUE nesse condomínio.
    """
    candidatos = [uid for uid in votantes_do_condominio if uid != usuario_dono_id]
    if not candidatos:
        return

    qtd_votos = rng.randint(0, min(len(candidatos), VOTOS_POR_POSTAGEM[1]))
    if qtd_votos == 0:
        return

    votantes = fk.random_elements(candidatos, length=qtd_votos, unique=True)
    for usuario_id in votantes:
        tipo_voto = "aprovar" if fk.boolean(75) else "denunciar"
        motivo_id = fk.random_element(motivos_denuncia_ids) if tipo_voto == "denunciar" else None
        comentario = fk.sentence(6) if fk.boolean(30) else None
        try:
            call_procedure(
                cur,
                "CALL sp_processar_voto_postagem(%s, %s, %s, %s, %s)",
                (postagem_id, usuario_id, tipo_voto, motivo_id, comentario),
            )
        except psycopg2.Error:
            # postagem já foi resolvida por um voto anterior desta rodada
            break


# ==============================================================================
# 6. AGENDAMENTOS, VISITAS, RECORRÊNCIAS E AVALIAÇÕES
# ==============================================================================

def criar_agendamento(cur, condominio_id, cooperativa_id,
                      status_agendamento_id, recorrente):
    # possui_recorrencia é setado direto aqui -- não há trigger que
    # recalcule a partir de tb_rel_recorrencias_agendamentos.
    data_inicio = fk.date_time_between(180, 0)
    data_fim    = data_inicio + timedelta(hours=2)
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
    cur.execute(
        """UPDATE tb_visitas_coletas
           SET foi_realizada = %s,
               houve_confirmacao = TRUE,
               confirmado_em = now(),
               observacao = %s
           WHERE id_visita_coleta = %s""",
        (confirmou, observacao, visita_id),
    )


def criar_avaliacao_visita(cur, visita_coleta_id, usuario_avaliador_id):
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
# 7. CURSOS, AULAS, QUIZZES E PROGRESSO
# ==============================================================================

def popular_cursos_e_aulas(cur):
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


# Banco fixo de perguntas/alternativas reaproveitado por todos os quizzes.
_PERGUNTAS_MODELO = [
    ("Qual desses materiais é reciclável?",
     ["Papel limpo e seco", "Isopor sujo de comida", "Fralda descartável usada", "Absorvente"], 0),
    ("Antes de descartar uma embalagem de vidro, o ideal é:",
     ["Lavar e secar", "Quebrar em pedaços pequenos", "Embrulhar em papel jornal", "Descartar suja mesmo"], 0),
    ("Pilhas e baterias usadas devem ir para:",
     ["O lixo comum", "Um ponto de coleta especializado", "O vaso sanitário", "A composteira"], 1),
    ("A compostagem é indicada principalmente para:",
     ["Resíduo orgânico", "Vidro", "Metal", "Lixo eletrônico"], 0),
    ("O símbolo de reciclagem em uma embalagem plástica indica:",
     ["Que ela é biodegradável", "O tipo de resina/polímero usado", "Que não pode ser reciclada", "O peso da embalagem"], 1),
]


def popular_quizzes(cur, cursos_ids, aulas_por_curso):
    """
    Cria 1 quiz por aula (tb_quizzes.aula_id é UNIQUE), com 3 perguntas do
    banco fixo acima.

    Retorna {aula_id: {"quiz_id", "nota_minima", "perguntas": [(pergunta_id, [(alt_id, correta), ...]), ...]}}
    """
    quizzes_por_aula = {}
    for titulo_curso, aula_ids in aulas_por_curso.items():
        curso_id = cursos_ids[titulo_curso]
        for aula_id in aula_ids:
            cur.execute(
                "SELECT id_quiz, nota_minima_aprovacao FROM tb_quizzes WHERE aula_id = %s",
                (aula_id,),
            )
            row = cur.fetchone()
            if row:
                quiz_id, nota_minima = row
            else:
                quiz_id = fetch_id(
                    cur,
                    """INSERT INTO tb_quizzes
                           (curso_id, aula_id, titulo_quiz, nota_minima_aprovacao, pontos_recompensa)
                       VALUES (%s, %s, %s, %s, %s) RETURNING id_quiz""",
                    (curso_id, aula_id, "Quiz de fixação", 70, 20),
                )
                nota_minima = 70

            cur.execute(
                "SELECT id_pergunta FROM tb_perguntas_quiz WHERE quiz_id = %s ORDER BY ordem",
                (quiz_id,),
            )
            perguntas_existentes = cur.fetchall()

            perguntas = []
            if perguntas_existentes:
                for (pergunta_id,) in perguntas_existentes:
                    cur.execute(
                        "SELECT id_alternativa, correta FROM tb_alternativas_quiz "
                        "WHERE pergunta_id = %s",
                        (pergunta_id,),
                    )
                    perguntas.append((pergunta_id, cur.fetchall()))
            else:
                escolhidas = fk.random_elements(
                    _PERGUNTAS_MODELO, length=min(3, len(_PERGUNTAS_MODELO)), unique=True
                )
                for ordem, (enunciado, alternativas, idx_correta) in enumerate(escolhidas, start=1):
                    pergunta_id = fetch_id(
                        cur,
                        """INSERT INTO tb_perguntas_quiz (quiz_id, enunciado, ordem)
                           VALUES (%s, %s, %s) RETURNING id_pergunta""",
                        (quiz_id, enunciado, ordem),
                    )
                    alt_ids = []
                    for i_alt, texto in enumerate(alternativas):
                        alt_id = fetch_id(
                            cur,
                            """INSERT INTO tb_alternativas_quiz
                                   (pergunta_id, texto_alternativa, correta)
                               VALUES (%s, %s, %s) RETURNING id_alternativa""",
                            (pergunta_id, texto, i_alt == idx_correta),
                        )
                        alt_ids.append((alt_id, i_alt == idx_correta))
                    perguntas.append((pergunta_id, alt_ids))

            quizzes_por_aula[aula_id] = {
                "quiz_id": quiz_id,
                "nota_minima": float(nota_minima),
                "perguntas": perguntas,
            }

    return quizzes_por_aula


def matricular_usuario_em_aulas(cur, usuario_id, lista_aula_ids):
    """
    Matricula o usuário em cada aula e, para ~55% delas, marca conclusão.
    Retorna a lista de aula_ids concluídas.
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
        progresso.append((uc_id, aula_id, vai_concluir, data_inicio))

    aulas_concluidas = []
    for uc_id, aula_id, vai_concluir, data_inicio in progresso:
        if not vai_concluir:
            continue
        data_conclusao = data_inicio + timedelta(days=rng.randint(1, 14))
        cur.execute(
            """UPDATE tb_rel_usuarios_cursos
               SET concluido = TRUE, data_conclusao = %s
               WHERE id_usuario_curso = %s""",
            (data_conclusao, uc_id),
        )
        aulas_concluidas.append(aula_id)

    return aulas_concluidas


def simular_tentativa_quiz(cur, usuario_id, quiz_info, condominio_id=None, torre_id=None):
    """
    Simula uma tentativa completa de um quiz: responde cada pergunta
    (acertando com ~70% de chance) e fecha com nota/aprovado calculados a
    partir dos acertos, respeitando quiz_info["nota_minima"].
    condominio_id/torre_id são nullable -- usuários comuns passam None.
    """
    iniciado_em = fk.date_time_between(120, 1)
    tentativa_id = fetch_id(
        cur,
        """INSERT INTO tb_tentativas_quiz
               (usuario_id, quiz_id, condominio_id, torre_id, iniciado_em)
           VALUES (%s, %s, %s, %s, %s) RETURNING id_tentativa""",
        (usuario_id, quiz_info["quiz_id"], condominio_id, torre_id, iniciado_em),
    )

    perguntas = quiz_info["perguntas"]
    acertos = 0
    for pergunta_id, alternativas in perguntas:
        corretas = [aid for aid, correta in alternativas if correta]
        erradas  = [aid for aid, correta in alternativas if not correta]
        vai_acertar = fk.boolean(70) or not erradas
        alt_escolhida = fk.random_element(corretas if vai_acertar else erradas)
        acertou = alt_escolhida in corretas

        cur.execute(
            """INSERT INTO tb_rel_respostas_tentativas_quiz
                   (tentativa_id, pergunta_id, alternativa_escolhida_id, correta)
               VALUES (%s, %s, %s, %s)""",
            (tentativa_id, pergunta_id, alt_escolhida, acertou),
        )
        if acertou:
            acertos += 1

    total = len(perguntas)
    nota = round(100.0 * acertos / total, 2) if total else 0.0
    aprovado = nota >= quiz_info["nota_minima"]
    concluido_em = iniciado_em + timedelta(minutes=rng.randint(3, 25))
    cur.execute(
        """UPDATE tb_tentativas_quiz
           SET nota = %s, aprovado = %s, concluido_em = %s
           WHERE id_tentativa = %s""",
        (nota, aprovado, concluido_em, tentativa_id),
    )


# ==============================================================================
# 8. NOTIFICAÇÕES
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
        data_envio = fk.date_time_between(120, 0)
        cur.execute(
            """INSERT INTO tb_notificacoes
                   (usuario_id, titulo_mensagem, corpo_mensagem,
                    tipo_notificacao, data_envio)
               VALUES (%s, %s, %s, %s, %s)""",
            (
                usuario_id, titulos[tipo], fk.sentence(10),
                tipo, data_envio,
            ),
        )


# ==============================================================================
# ATOMICIDADE / LIMPEZA
# ==============================================================================

def limpar_dados_banco(cur):
    """
    TRUNCATE em ordem de dependência (filhos antes dos pais). Tabelas
    tb_lkp_* ficam de fora: são seeds fixos reaproveitados entre execuções.
    """
    tabelas = [
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
