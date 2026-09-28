-- ============================================================================
-- ECOCIENTE | SCRIPT DE CRIACAO DO SCHEMA (DDL)
-- Gerado a partir de: Modelagem_Logica_EcoCiente_prefixada.dbml (nomenclatura tb_/tb_lkp_/tb_rel_/tb_log_)
-- Compativel com: views_analiticas_ecociente.sql
-- Dialeto: PostgreSQL 14+
--
-- Convencoes adotadas:
--   - PKs: GENERATED ALWAYS AS IDENTITY (integer ou bigint, conforme o DBML)
--   - FKs nomeadas como fk_<tabela>_<coluna>
-- ============================================================================

BEGIN;

-- ============================================================================
-- SECAO 1 - TIPOS E TABELAS DE DOMINIO (LOOKUPS)
-- ============================================================================

CREATE TABLE tb_lkp_tipos_usuarios (
    id_tipo_usuario INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome_tipo       VARCHAR(50)  NOT NULL,
    descricao       VARCHAR(255)
);

CREATE TABLE tb_lkp_tipos_condominios (
    id_tipo_condominio INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome_tipo          VARCHAR(50)  NOT NULL,
    descricao          VARCHAR(255)
);
CREATE TABLE tb_lkp_status_agendamentos (
    id_status   INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome_status VARCHAR(50) NOT NULL
);

CREATE TABLE tb_lkp_dias_semanas (
    id_dia_semana INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome_dia      VARCHAR(20) NOT NULL
);

CREATE TABLE tb_lkp_categorias_residuos (
    id_categoria        INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome_categoria       VARCHAR(100)  NOT NULL,
    descricao_material   VARCHAR(255),
    permite_reciclagem   BOOLEAN       NOT NULL DEFAULT TRUE,
    cor_identificacao    VARCHAR(10),
    pontos_base          INTEGER       NOT NULL DEFAULT 10,
    limite_pontos_diario  INTEGER,
    CONSTRAINT ck_categorias_residuos_pontos_base CHECK (pontos_base > 0),
    CONSTRAINT ck_categorias_residuos_limite_pontos_diario CHECK (limite_pontos_diario IS NULL OR limite_pontos_diario >= 0)
);
COMMENT ON COLUMN tb_lkp_categorias_residuos.pontos_base IS 'Pontos concedidos por postagem aprovada nessa categoria';
COMMENT ON COLUMN tb_lkp_categorias_residuos.limite_pontos_diario IS 'Teto diario de pontos por usuario nessa categoria. NULL = sem teto';

CREATE TABLE tb_lkp_niveis_confianca (
    id_nivel_confianca INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome_nivel         VARCHAR(50)  NOT NULL,
    peso_voto          INTEGER      NOT NULL,
    descricao          VARCHAR(255),
    CONSTRAINT ck_niveis_confianca_peso_voto CHECK (peso_voto > 0)
);
COMMENT ON COLUMN tb_lkp_niveis_confianca.nome_nivel IS 'morador_comum | pessoa_confiavel | sindico';
COMMENT ON COLUMN tb_lkp_niveis_confianca.peso_voto IS 'Peso do voto desse nivel na validacao de tb_postagens (1, 3, 3)';

CREATE TABLE tb_lkp_status_validacoes_postagens (
    id_status_validacao INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome_status         VARCHAR(30)  NOT NULL,
    descricao           VARCHAR(255)
);
COMMENT ON COLUMN tb_lkp_status_validacoes_postagens.nome_status IS 'aprovada | em_analise | reprovada';

CREATE TABLE tb_lkp_tipos_votos_postagens (
    id_tipo_voto INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome_tipo    VARCHAR(30) NOT NULL
);
COMMENT ON COLUMN tb_lkp_tipos_votos_postagens.nome_tipo IS 'aprovar | denunciar';

CREATE TABLE tb_lkp_motivos_denuncia (
    id_motivo_denuncia INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    descricao           VARCHAR(255) NOT NULL,
    ativo               BOOLEAN      NOT NULL DEFAULT TRUE
);
COMMENT ON COLUMN tb_lkp_motivos_denuncia.descricao IS 'Nao e lixo reciclavel / Foto nao corresponde a categoria / Foto antiga-reutilizada / Spam-abuso';

CREATE TABLE tb_lkp_tipos_eventos_auditados (
    id_tipo_evento_auditado INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome_evento              VARCHAR(50),
    descricao                VARCHAR(255)
);
COMMENT ON COLUMN tb_lkp_tipos_eventos_auditados.nome_evento IS 'postagem / agendamento_coleta / usuario_condominio';

CREATE TABLE tb_lkp_tipos_operacoes_auditoria (
    id_tipo_operacao INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome_operacao     VARCHAR(50)
);
COMMENT ON COLUMN tb_lkp_tipos_operacoes_auditoria.nome_operacao IS 'INSERT / UPDATE / DELETE';

-- ============================================================================
-- SECAO 2 - ENDERECOS E USUARIOS
-- ============================================================================

CREATE TABLE tb_enderecos (
    id_endereco   INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cep           VARCHAR(10),
    estado        CHAR(2),
    cidade        VARCHAR(100),
    logradouro    VARCHAR(150),
    numero        VARCHAR(20),
    complemento   VARCHAR(100)
);

CREATE TABLE tb_usuarios (
    id_usuario       INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome_usuario     VARCHAR(100)  NOT NULL,
    email_usuario    VARCHAR(255)  NOT NULL,
    senha_hash       VARCHAR(255)  NOT NULL,
    data_nascimento  DATE,
    cpf         VARCHAR(11),
    url_avatar       VARCHAR(500),
    ativo            BOOLEAN       NOT NULL DEFAULT TRUE,
    registro_em      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    tipo_usuario_id  INTEGER       NOT NULL,
    endereco_id      INTEGER       NOT NULL,
    CONSTRAINT fk_usuarios_tipo_usuario_id FOREIGN KEY (tipo_usuario_id) REFERENCES tb_lkp_tipos_usuarios (id_tipo_usuario),
    CONSTRAINT fk_usuarios_endereco_id FOREIGN KEY (endereco_id) REFERENCES tb_enderecos (id_endereco),
    CONSTRAINT uq_usuarios_cpf UNIQUE (cpf)
);

CREATE TABLE tb_sindicos (
    id_sindico  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id  INTEGER NOT NULL,
    CONSTRAINT fk_sindicos_usuario_id FOREIGN KEY (usuario_id) REFERENCES tb_usuarios (id_usuario),
    CONSTRAINT uq_sindicos_usuario_id UNIQUE (usuario_id)
);

CREATE TABLE tb_telefones (
    id_telefone     INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id      INTEGER      NOT NULL,
    numero_contato  VARCHAR(20)  NOT NULL,
    tipo_telefone   VARCHAR(20),
    ativo           BOOLEAN      NOT NULL DEFAULT TRUE,
    CONSTRAINT fk_telefones_usuario_id FOREIGN KEY (usuario_id) REFERENCES tb_usuarios (id_usuario)
);

CREATE TABLE tb_notificacoes (
    id_notificacao    INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id        INTEGER      NOT NULL,
    titulo_mensagem   VARCHAR(255) NOT NULL,
    corpo_mensagem    TEXT,
    tipo_notificacao  VARCHAR(50),
    data_envio        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT fk_notificacoes_usuario_id FOREIGN KEY (usuario_id) REFERENCES tb_usuarios (id_usuario)
);

-- ============================================================================
-- SECAO 3 - CONDOMINIOS E ESTRUTURA FISICA
-- ============================================================================

CREATE TABLE tb_condominios (
    id_condominio        INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome_condominio      VARCHAR(255) NOT NULL,
    cnpj                 VARCHAR(18),
    codigo_acesso        VARCHAR(20),
    ativo                BOOLEAN      NOT NULL DEFAULT TRUE,
    tipo_condominio_id   INTEGER      NOT NULL,
    sindico_id           INTEGER,
    endereco_id          INTEGER,
    CONSTRAINT fk_condominios_tipo_condominio_id FOREIGN KEY (tipo_condominio_id) REFERENCES tb_lkp_tipos_condominios (id_tipo_condominio),
    CONSTRAINT fk_condominios_sindico_id FOREIGN KEY (sindico_id) REFERENCES tb_sindicos (id_sindico),
    CONSTRAINT fk_condominios_endereco_id FOREIGN KEY (endereco_id) REFERENCES tb_enderecos (id_endereco),
    CONSTRAINT uq_condominios_endereco_id UNIQUE (endereco_id)
);

CREATE TABLE tb_torres (
    id_torre       INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome_torre     VARCHAR(100) NOT NULL,
    condominio_id  INTEGER      NOT NULL,
    CONSTRAINT fk_torres_condominio_id FOREIGN KEY (condominio_id) REFERENCES tb_condominios (id_condominio),
    CONSTRAINT torres_index_0 UNIQUE (condominio_id, nome_torre)
);
CREATE TABLE tb_moradores (
    id_morador  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    condominio_id    INTEGER      NOT NULL,
    usuario_id  INTEGER NOT NULL,
    CONSTRAINT fk_moradores_usuario_id FOREIGN KEY (usuario_id) REFERENCES tb_usuarios (id_usuario),
    CONSTRAINT uq_moradores_usuario_id UNIQUE (usuario_id),
    CONSTRAINT fk_moradores_condominio_id FOREIGN KEY (condominio_id) REFERENCES tb_condominios (id_condominio));

-- ============================================================================
-- SECAO 4 - COOPERATIVAS E PONTOS DE COLETA
-- ============================================================================

CREATE TABLE tb_cooperativas (
    id_cooperativa        INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cnpj_cooperativa      VARCHAR(18)  NOT NULL,
    nome_cooperativa      VARCHAR(255) NOT NULL,
    email_cooperativa     VARCHAR(255),
    telefone_cooperativa  VARCHAR(20),
    data_cadastro         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    usuario_id            INTEGER,
    endereco_id           INTEGER,
    CONSTRAINT fk_cooperativas_usuario_id FOREIGN KEY (usuario_id) REFERENCES tb_usuarios (id_usuario),
    CONSTRAINT fk_cooperativas_endereco_id FOREIGN KEY (endereco_id) REFERENCES tb_enderecos (id_endereco),
    CONSTRAINT uq_cooperativas_usuario_id UNIQUE (usuario_id),
    CONSTRAINT uq_cooperativas_endereco_id UNIQUE (endereco_id)
);

CREATE TABLE tb_pontos_coletas (
    id_ponto_coleta     INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome_ponto          VARCHAR(255) NOT NULL,
    endereco_id         INTEGER,
    cooperativa_id      INTEGER,
    horario_abertura    TIME,
    horario_fechamento  TIME,
    ativo               BOOLEAN      NOT NULL DEFAULT TRUE,
    CONSTRAINT fk_pontos_coletas_endereco_id FOREIGN KEY (endereco_id) REFERENCES tb_enderecos (id_endereco),
    CONSTRAINT fk_pontos_coletas_cooperativa_id FOREIGN KEY (cooperativa_id) REFERENCES tb_cooperativas (id_cooperativa)
);

CREATE TABLE tb_rel_cooperativas_categorias_materiais (
    id_cooperativa_categoria  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cooperativa_id            INTEGER NOT NULL,
    categoria_residuo_id      INTEGER NOT NULL,
    CONSTRAINT fk_cooperativas_categorias_materiais_cooperativa_id FOREIGN KEY (cooperativa_id) REFERENCES tb_cooperativas (id_cooperativa),
    CONSTRAINT fk_cooperativas_categorias_materiais_categoria_residuo_id FOREIGN KEY (categoria_residuo_id) REFERENCES tb_lkp_categorias_residuos (id_categoria),
    CONSTRAINT cooperativas_categorias_materiais_index_1 UNIQUE (cooperativa_id, categoria_residuo_id)
);

CREATE TABLE tb_rel_pontos_coletas_categorias (
    id_ponto_coleta_categoria  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ponto_coleta_id            INTEGER NOT NULL,
    categoria_residuo_id       INTEGER NOT NULL,
    CONSTRAINT fk_pontos_coletas_categorias_ponto_coleta_id FOREIGN KEY (ponto_coleta_id) REFERENCES tb_pontos_coletas (id_ponto_coleta),
    CONSTRAINT fk_pontos_coletas_categorias_categoria_residuo_id FOREIGN KEY (categoria_residuo_id) REFERENCES tb_lkp_categorias_residuos (id_categoria),
    CONSTRAINT pontos_coletas_categorias_index_2 UNIQUE (ponto_coleta_id, categoria_residuo_id)
);

-- ============================================================================
-- SECAO 5 - VINCULO USUARIO x CONDOMINIO (CONFIANCA)
-- ============================================================================

CREATE TABLE tb_rel_usuarios_condominios (
    id_usuario_condominio                INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id                           INTEGER       NOT NULL,
    condominio_id                        INTEGER       NOT NULL,
    data_entrada                         TIMESTAMPTZ   NOT NULL DEFAULT now(),
    data_saida                           TIMESTAMPTZ,
    aprovado                             BOOLEAN       NOT NULL DEFAULT FALSE,
    aprovado_por_usuario_id              INTEGER,
    nivel_confianca_id                   INTEGER       NOT NULL DEFAULT 1,
    trust_score                          DECIMAL(6,2)  NOT NULL,
    postagens_validadas_sem_contestacao  INTEGER       NOT NULL,
    denuncias_realizadas                 INTEGER       NOT NULL,
    denuncias_procedentes                INTEGER       NOT NULL,
    taxa_acerto_denuncias                DECIMAL(5,2),
    CONSTRAINT fk_usuarios_condominios_usuario_id FOREIGN KEY (usuario_id) REFERENCES tb_usuarios (id_usuario),
    CONSTRAINT fk_usuarios_condominios_condominio_id FOREIGN KEY (condominio_id) REFERENCES tb_condominios (id_condominio),
    CONSTRAINT fk_usuarios_condominios_aprovado_por_usuario_id FOREIGN KEY (aprovado_por_usuario_id) REFERENCES tb_usuarios (id_usuario),
    CONSTRAINT fk_usuarios_condominios_nivel_confianca_id FOREIGN KEY (nivel_confianca_id) REFERENCES tb_lkp_niveis_confianca (id_nivel_confianca),
    CONSTRAINT usuarios_condominios_index_5 UNIQUE (usuario_id, condominio_id),
    CONSTRAINT ck_usuarios_condominios_postagens_validadas CHECK (postagens_validadas_sem_contestacao >= 0),
    CONSTRAINT ck_usuarios_condominios_denuncias_realizadas CHECK (denuncias_realizadas >= 0),
    CONSTRAINT ck_usuarios_condominios_denuncias_procedentes CHECK (denuncias_procedentes >= 0 AND denuncias_procedentes <= denuncias_realizadas),
    CONSTRAINT ck_usuarios_condominios_taxa_acerto_denuncias CHECK (taxa_acerto_denuncias IS NULL OR taxa_acerto_denuncias BETWEEN 0 AND 100)
);
COMMENT ON COLUMN tb_rel_usuarios_condominios.nivel_confianca_id IS 'Default = morador_comum (id 1)';
COMMENT ON COLUMN tb_rel_usuarios_condominios.trust_score IS 'Score composto usado para promover a pessoa_confiavel';
COMMENT ON COLUMN tb_rel_usuarios_condominios.denuncias_procedentes IS 'Denuncias cujo veredito final concordou com o denunciante';
COMMENT ON COLUMN tb_rel_usuarios_condominios.taxa_acerto_denuncias IS 'denuncias_procedentes / denuncias_realizadas * 100, recalculado pela aplicacao';

-- ============================================================================
-- SECAO 6 - POSTAGENS E MODERACAO (VOTOS)
-- ============================================================================

CREATE TABLE tb_postagens (
    id_postagem                    INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id                     INTEGER       NOT NULL,
    condominio_id                  INTEGER       NOT NULL,
    torre_id                       INTEGER,
    categoria_id                   INTEGER       NOT NULL,
    url_foto                       VARCHAR(500)  NOT NULL,
    hash_foto                      VARCHAR(128)  NOT NULL,
    capturada_em                   TIMESTAMPTZ   NOT NULL,
    data_postagem                  TIMESTAMPTZ   NOT NULL DEFAULT now(),
    status_validacao_id            INTEGER       NOT NULL DEFAULT 1,
    saldo_confianca                INTEGER       NOT NULL DEFAULT 0,
    pontuacao_ativa                 BOOLEAN       NOT NULL DEFAULT TRUE,
    pontuacao_reconciliacao_pendente BOOLEAN      NOT NULL DEFAULT FALSE,
    triagem_automatica_aprovada    BOOLEAN,
    triagem_automatica_confianca   DECIMAL(5,2),
    data_limite_analise            TIMESTAMPTZ   NOT NULL DEFAULT (now() + INTERVAL '24 hours'),
    resolvido_em                   TIMESTAMPTZ,
    CONSTRAINT fk_postagens_usuario_id FOREIGN KEY (usuario_id) REFERENCES tb_usuarios (id_usuario),
    CONSTRAINT fk_postagens_condominio_id FOREIGN KEY (condominio_id) REFERENCES tb_condominios (id_condominio),
    CONSTRAINT fk_postagens_torre_id FOREIGN KEY (torre_id) REFERENCES tb_torres (id_torre),
    CONSTRAINT fk_postagens_categoria_id FOREIGN KEY (categoria_id) REFERENCES tb_lkp_categorias_residuos (id_categoria),
    CONSTRAINT fk_postagens_status_validacao_id FOREIGN KEY (status_validacao_id) REFERENCES tb_lkp_status_validacoes_postagens (id_status_validacao),
    CONSTRAINT uq_postagens_hash_foto UNIQUE (hash_foto),
    CONSTRAINT ck_postagens_capturada_em CHECK (capturada_em <= data_postagem),
    CONSTRAINT ck_postagens_triagem_confianca CHECK (triagem_automatica_confianca IS NULL OR triagem_automatica_confianca BETWEEN 0 AND 100)
);
COMMENT ON COLUMN tb_postagens.condominio_id IS 'Usado pela aplicacao para montar a chave do ranking no Redis';
COMMENT ON COLUMN tb_postagens.torre_id IS 'Nulo quando o condominio nao possui torres (ex.: condominio comercial). Usado para a chave do ranking no Redis';
COMMENT ON COLUMN tb_postagens.hash_foto IS 'Hash (ex.: SHA-256) do arquivo - impede reuso da mesma foto em outra postagem';
COMMENT ON COLUMN tb_postagens.capturada_em IS 'Timestamp de captura da camera (foto instantanea), validado contra data_postagem';
COMMENT ON COLUMN tb_postagens.status_validacao_id IS 'Enquanto resolvido_em IS NULL, status aprovada representa APROVACAO PROVISORIA; a decisao definitiva ocorre no fechamento da janela ou por decisao manual.';
COMMENT ON COLUMN tb_postagens.saldo_confianca IS 'Soma dos pesos de voto: aprovacoes somam, denuncias subtraem. Inicia em 0.';
COMMENT ON COLUMN tb_postagens.pontuacao_ativa IS 'Estado desejado da pontuacao da postagem: TRUE enquanto valida; vira FALSE ao atingir saldo <= -5 e pode voltar a TRUE quando saldo >= 0 dentro da janela.';
COMMENT ON COLUMN tb_postagens.pontuacao_reconciliacao_pendente IS 'TRUE quando a mudanca de estado exige reconciliar CREDITO/ESTORNO/RESTAURACAO no ledger tb_movimentacoes_pontos pela API.';
COMMENT ON COLUMN tb_postagens.triagem_automatica_aprovada IS 'Resultado da checagem automatica fraca (ex.: "parece conter lixo/objeto?"). NULL = ainda nao processada';
COMMENT ON COLUMN tb_postagens.data_limite_analise IS 'Prazo maximo para a comunidade validar/derrubar a postagem';
COMMENT ON COLUMN tb_postagens.resolvido_em IS 'Momento em que a janela comunitaria foi encerrada ou houve decisao manual; quando NULL a postagem ainda esta em validacao comunitaria.';

CREATE TABLE tb_rel_votos_postagens (
    id_voto              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    postagem_id          INTEGER      NOT NULL,
    usuario_id           INTEGER      NOT NULL,
    tipo_voto_id         INTEGER      NOT NULL,
    motivo_denuncia_id   INTEGER,
    peso_aplicado        INTEGER      NOT NULL,
    comentario           VARCHAR(255),
    votado_em            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT fk_votos_postagens_postagem_id FOREIGN KEY (postagem_id) REFERENCES tb_postagens (id_postagem) ON UPDATE CASCADE,
    CONSTRAINT fk_votos_postagens_usuario_id FOREIGN KEY (usuario_id) REFERENCES tb_usuarios (id_usuario),
    CONSTRAINT fk_votos_postagens_tipo_voto_id FOREIGN KEY (tipo_voto_id) REFERENCES tb_lkp_tipos_votos_postagens (id_tipo_voto),
    CONSTRAINT fk_votos_postagens_motivo_denuncia_id FOREIGN KEY (motivo_denuncia_id) REFERENCES tb_lkp_motivos_denuncia (id_motivo_denuncia),
    CONSTRAINT votos_postagens_index_7 UNIQUE (postagem_id, usuario_id),
    CONSTRAINT ck_votos_postagens_peso_aplicado CHECK (peso_aplicado > 0)
);
COMMENT ON COLUMN tb_rel_votos_postagens.motivo_denuncia_id IS 'Obrigatorio quando tipo_voto_id = denunciar';
COMMENT ON COLUMN tb_rel_votos_postagens.peso_aplicado IS 'Snapshot do peso de voto do usuario no momento (1, 3...)';

-- ============================================================================
-- SECAO 7 - AGENDAMENTOS DE COLETA
-- ============================================================================
CREATE TABLE tb_agendamentos_coletas (
    id_agendamento_coleta   INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    condominio_id           INTEGER      NOT NULL,
    cooperativa_id          INTEGER      NOT NULL,
    status_agendamento_id   INTEGER      NOT NULL,
    data_inicio             TIMESTAMPTZ  NOT NULL,
    data_fim                TIMESTAMPTZ,
    possui_recorrencia      BOOLEAN      NOT NULL DEFAULT FALSE,
    CONSTRAINT fk_agendamentos_coletas_condominio_id FOREIGN KEY (condominio_id) REFERENCES tb_condominios (id_condominio),
    CONSTRAINT fk_agendamentos_coletas_cooperativa_id FOREIGN KEY (cooperativa_id) REFERENCES tb_cooperativas (id_cooperativa),
    CONSTRAINT fk_agendamentos_coletas_status_agendamento_id FOREIGN KEY (status_agendamento_id) REFERENCES tb_lkp_status_agendamentos (id_status),
    CONSTRAINT ck_agendamentos_coletas_datas CHECK (data_fim IS NULL OR data_fim >= data_inicio)
);

CREATE TABLE tb_visitas_coletas (
    id_visita_coleta        INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    agendamento_coleta_id   INTEGER      NOT NULL,
    data_visita              TIMESTAMPTZ  NOT NULL,
    foi_realizada            BOOLEAN      NOT NULL DEFAULT FALSE,
    houve_confirmacao        BOOLEAN      NOT NULL DEFAULT FALSE,
    confirmado_em            TIMESTAMPTZ,
    observacao               TEXT,
    CONSTRAINT fk_visitas_coletas_agendamento_coleta_id FOREIGN KEY (agendamento_coleta_id) REFERENCES tb_agendamentos_coletas (id_agendamento_coleta)
);

CREATE TABLE tb_avaliacoes_visitas_coletas (
    id_avaliacao          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    visita_coleta_id      INTEGER      NOT NULL,
    usuario_avaliador_id  INTEGER      NOT NULL,
    nota                  SMALLINT     NOT NULL,
    comentario            VARCHAR(500),
    avaliado_em           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT fk_avaliacoes_visitas_coletas_visita_coleta_id FOREIGN KEY (visita_coleta_id) REFERENCES tb_visitas_coletas (id_visita_coleta),
    CONSTRAINT fk_avaliacoes_visitas_coletas_usuario_avaliador_id FOREIGN KEY (usuario_avaliador_id) REFERENCES tb_usuarios (id_usuario),
    CONSTRAINT uq_avaliacoes_visitas_coletas_visita_coleta_id UNIQUE (visita_coleta_id),
    CONSTRAINT ck_avaliacoes_visitas_coletas_nota CHECK (nota BETWEEN 1 AND 5)
);

CREATE TABLE tb_rel_recorrencias_agendamentos (
    id_recorrencia_agendamento  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    agendamento_coleta_id       INTEGER NOT NULL,
    dia_semana_id               INTEGER NOT NULL,
    CONSTRAINT fk_recorrencias_agendamentos_agendamento_coleta_id FOREIGN KEY (agendamento_coleta_id) REFERENCES tb_agendamentos_coletas (id_agendamento_coleta),
    CONSTRAINT fk_recorrencias_agendamentos_dia_semana_id FOREIGN KEY (dia_semana_id) REFERENCES tb_lkp_dias_semanas (id_dia_semana),
    CONSTRAINT recorrencias_agendamentos_index_3 UNIQUE (agendamento_coleta_id, dia_semana_id)
);

-- ============================================================================
-- SECAO 8 - EDUCACAO: CURSOS, AULAS E QUIZZES
-- ============================================================================

CREATE TABLE tb_cursos (
    id_curso        INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    titulo_curso    VARCHAR(255) NOT NULL,
    descricao_curso TEXT,
    esta_ativo      BOOLEAN      NOT NULL DEFAULT TRUE
);

CREATE TABLE tb_aulas (
    id_aula        INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    curso_id       INTEGER      NOT NULL,
    titulo_aula    VARCHAR(255) NOT NULL,
    conteudo_aula  TEXT,
    ordem          INTEGER      NOT NULL,
    CONSTRAINT fk_aulas_curso_id FOREIGN KEY (curso_id) REFERENCES tb_cursos (id_curso),
    CONSTRAINT aulas_index_4 UNIQUE (curso_id, ordem)
);

CREATE TABLE tb_quizzes (
    id_quiz                 INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    curso_id                 INTEGER      NOT NULL,
    aula_id                 INTEGER      NOT NULL,
    titulo_quiz             VARCHAR(255) NOT NULL,
    nota_minima_aprovacao   DECIMAL(5,2) NOT NULL DEFAULT 70,
    pontos_recompensa       INTEGER      NOT NULL,
    ativo                   BOOLEAN      NOT NULL DEFAULT TRUE,
    criado_em               TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT fk_quizzes_aula_id FOREIGN KEY (aula_id) REFERENCES tb_aulas (id_aula) ON UPDATE CASCADE,
    CONSTRAINT uq_quizzes_aula_id UNIQUE (aula_id),
    CONSTRAINT ck_quizzes_nota_minima_aprovacao CHECK (nota_minima_aprovacao BETWEEN 0 AND 100),
    CONSTRAINT ck_quizzes_pontos_recompensa CHECK (pontos_recompensa > 0),
    CONSTRAINT fk_quizzes_curso_id FOREIGN KEY (curso_id) REFERENCES tb_cursos (id_curso));
COMMENT ON COLUMN tb_quizzes.pontos_recompensa IS 'Deve ser maior que tb_lkp_categorias_residuos.pontos_base de uma postagem comum';

CREATE TABLE tb_perguntas_quiz (
    id_pergunta  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quiz_id      INTEGER NOT NULL,
    enunciado    TEXT    NOT NULL,
    ordem        INTEGER NOT NULL,
    CONSTRAINT fk_perguntas_quiz_quiz_id FOREIGN KEY (quiz_id) REFERENCES tb_quizzes (id_quiz) ON UPDATE CASCADE,
    CONSTRAINT perguntas_quiz_index_12 UNIQUE (quiz_id, ordem)
);

CREATE TABLE tb_alternativas_quiz (
    id_alternativa     INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pergunta_id        INTEGER      NOT NULL,
    texto_alternativa  VARCHAR(500) NOT NULL,
    correta            BOOLEAN      NOT NULL DEFAULT FALSE,
    CONSTRAINT fk_alternativas_quiz_pergunta_id FOREIGN KEY (pergunta_id) REFERENCES tb_perguntas_quiz (id_pergunta) ON UPDATE CASCADE
);

CREATE TABLE tb_tentativas_quiz (
    id_tentativa   INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id     INTEGER      NOT NULL,
    quiz_id        INTEGER      NOT NULL,
    condominio_id  INTEGER,
    torre_id       INTEGER,
    nota           DECIMAL(5,2),
    aprovado       BOOLEAN      NOT NULL DEFAULT FALSE,
    iniciado_em    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    concluido_em   TIMESTAMPTZ,
    CONSTRAINT fk_tentativas_quiz_usuario_id FOREIGN KEY (usuario_id) REFERENCES tb_usuarios (id_usuario),
    CONSTRAINT fk_tentativas_quiz_quiz_id FOREIGN KEY (quiz_id) REFERENCES tb_quizzes (id_quiz),
    CONSTRAINT fk_tentativas_quiz_condominio_id FOREIGN KEY (condominio_id) REFERENCES tb_condominios (id_condominio),
    CONSTRAINT fk_tentativas_quiz_torre_id FOREIGN KEY (torre_id) REFERENCES tb_torres (id_torre),
    CONSTRAINT ck_tentativas_quiz_nota CHECK (nota IS NULL OR nota BETWEEN 0 AND 100)
);
COMMENT ON COLUMN tb_tentativas_quiz.condominio_id IS 'Snapshot do condominio do usuario na conclusao, para atribuicao de pontos ao ciclo';
COMMENT ON COLUMN tb_tentativas_quiz.torre_id IS 'Snapshot da torre do usuario na conclusao';
COMMENT ON COLUMN tb_tentativas_quiz.aprovado IS 'Quando true e a tentativa for elegivel, a API registra CREDITO em tb_movimentacoes_pontos; somente apos COMMIT sincroniza o Redis';

CREATE TABLE tb_rel_respostas_tentativas_quiz (
    id_resposta                INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tentativa_id               INTEGER NOT NULL,
    pergunta_id                INTEGER NOT NULL,
    alternativa_escolhida_id   INTEGER NOT NULL,
    correta                    BOOLEAN NOT NULL,
    CONSTRAINT fk_respostas_tentativas_quiz_tentativa_id FOREIGN KEY (tentativa_id) REFERENCES tb_tentativas_quiz (id_tentativa) ON UPDATE CASCADE,
    CONSTRAINT fk_respostas_tentativas_quiz_pergunta_id FOREIGN KEY (pergunta_id) REFERENCES tb_perguntas_quiz (id_pergunta),
    CONSTRAINT fk_respostas_tentativas_quiz_alternativa_escolhida_id FOREIGN KEY (alternativa_escolhida_id) REFERENCES tb_alternativas_quiz (id_alternativa),
    CONSTRAINT respostas_tentativas_quiz_index_13 UNIQUE (tentativa_id, pergunta_id)
);

CREATE TABLE tb_rel_usuarios_cursos (
    id_usuario_curso  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id        INTEGER      NOT NULL,
    aula_id           INTEGER      NOT NULL,
    concluido         BOOLEAN      NOT NULL DEFAULT FALSE,
    data_inicio       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    data_conclusao    TIMESTAMPTZ,
    CONSTRAINT fk_usuarios_cursos_usuario_id FOREIGN KEY (usuario_id) REFERENCES tb_usuarios (id_usuario),
    CONSTRAINT fk_usuarios_cursos_aula_id FOREIGN KEY (aula_id) REFERENCES tb_aulas (id_aula),
    CONSTRAINT usuarios_cursos_index_6 UNIQUE (usuario_id, aula_id)
);



-- ============================================================================
-- SECAO 9 - LEDGER OFICIAL DE PONTOS E CONTROLE DE TOKEN DE AUTENTICACAO
-- ============================================================================

CREATE TABLE tb_autenticacoes_api (
    id_autenticao_api  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id   INTEGER      NOT NULL,
    token        TEXT         NOT NULL,
    tipo_token   VARCHAR(20)  NOT NULL DEFAULT 'Bearer',
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    expira_em   INTEGER      NOT NULL,

    CONSTRAINT fk_autenticao_api_usuario_id
        FOREIGN KEY (usuario_id)
        REFERENCES tb_usuarios (id_usuario),

    CONSTRAINT uq_autenticao_api_token
        UNIQUE (token),

    CONSTRAINT ck_autenticao_api_token_type
        CHECK (tipo_token = 'Bearer'),

    CONSTRAINT ck_autenticao_api_expira_em
        CHECK (expira_em > 0)
);



-- PostgreSQL e a fonte oficial da pontuacao. O Redis e apenas uma projecao
-- derivada para ranking. Toda concessao, retirada ou restauracao deve ser
-- registrada nesta tabela antes de qualquer atualizacao no Redis.
CREATE TABLE tb_movimentacoes_pontos (
    id_movimentacao               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id                    INTEGER       NOT NULL,
    condominio_id                 INTEGER,
    torre_id                      INTEGER,
    categoria_id                  INTEGER,
    origem_tipo                   VARCHAR(20)   NOT NULL,
    postagem_id                   INTEGER,
    tentativa_quiz_id             INTEGER,
    tipo_movimentacao             VARCHAR(20)   NOT NULL,
    pontos                        INTEGER       NOT NULL,
    movimentacao_referencia_id    BIGINT,
    idempotency_key               VARCHAR(150)  NOT NULL,
    ocorrido_em                   TIMESTAMPTZ   NOT NULL DEFAULT now(),
    redis_sincronizado            BOOLEAN       NOT NULL DEFAULT FALSE,
    redis_sincronizado_em         TIMESTAMPTZ,
    tentativas_sync_redis         INTEGER       NOT NULL DEFAULT 0,
    ultimo_erro_redis             TEXT,

    CONSTRAINT fk_mov_pontos_usuario_id
        FOREIGN KEY (usuario_id) REFERENCES tb_usuarios (id_usuario),
    CONSTRAINT fk_mov_pontos_condominio_id
        FOREIGN KEY (condominio_id) REFERENCES tb_condominios (id_condominio),
    CONSTRAINT fk_mov_pontos_torre_id
        FOREIGN KEY (torre_id) REFERENCES tb_torres (id_torre),
    CONSTRAINT fk_mov_pontos_categoria_id
        FOREIGN KEY (categoria_id) REFERENCES tb_lkp_categorias_residuos (id_categoria),
    CONSTRAINT fk_mov_pontos_postagem_id
        FOREIGN KEY (postagem_id) REFERENCES tb_postagens (id_postagem),
    CONSTRAINT fk_mov_pontos_tentativa_quiz_id
        FOREIGN KEY (tentativa_quiz_id) REFERENCES tb_tentativas_quiz (id_tentativa),
    CONSTRAINT fk_mov_pontos_movimentacao_referencia_id
        FOREIGN KEY (movimentacao_referencia_id) REFERENCES tb_movimentacoes_pontos (id_movimentacao),

    CONSTRAINT uq_mov_pontos_idempotency_key UNIQUE (idempotency_key),
    CONSTRAINT ck_mov_pontos_origem_tipo
        CHECK (origem_tipo IN ('POSTAGEM', 'QUIZ')),
    CONSTRAINT ck_mov_pontos_tipo_movimentacao
        CHECK (tipo_movimentacao IN ('CREDITO', 'ESTORNO', 'RESTAURACAO')),
    CONSTRAINT ck_mov_pontos_pontos_positivo
        CHECK (pontos > 0),
    CONSTRAINT ck_mov_pontos_tentativas_sync
        CHECK (tentativas_sync_redis >= 0),
    CONSTRAINT ck_mov_pontos_origem_consistente CHECK (
        (origem_tipo = 'POSTAGEM'
            AND postagem_id IS NOT NULL
            AND tentativa_quiz_id IS NULL
            AND categoria_id IS NOT NULL)
        OR
        (origem_tipo = 'QUIZ'
            AND tentativa_quiz_id IS NOT NULL
            AND postagem_id IS NULL
            AND categoria_id IS NULL)
    ),
    CONSTRAINT ck_mov_pontos_referencia_consistente CHECK (
        (tipo_movimentacao = 'CREDITO' AND movimentacao_referencia_id IS NULL)
        OR
        (tipo_movimentacao IN ('ESTORNO', 'RESTAURACAO') AND movimentacao_referencia_id IS NOT NULL)
    ),
    CONSTRAINT ck_mov_pontos_sync_timestamp CHECK (
        redis_sincronizado = FALSE OR redis_sincronizado_em IS NOT NULL
    )
);

COMMENT ON TABLE tb_movimentacoes_pontos IS 'Ledger oficial e imutavel de pontuacao. Redis deve ser reconstruivel integralmente a partir deste historico.';
COMMENT ON COLUMN tb_movimentacoes_pontos.origem_tipo IS 'POSTAGEM ou QUIZ';
COMMENT ON COLUMN tb_movimentacoes_pontos.tipo_movimentacao IS 'CREDITO soma; ESTORNO subtrai; RESTAURACAO soma novamente o mesmo credito de referencia';
COMMENT ON COLUMN tb_movimentacoes_pontos.movimentacao_referencia_id IS 'ESTORNO/RESTAURACAO devem apontar para o CREDITO original da mesma origem e do mesmo valor';
COMMENT ON COLUMN tb_movimentacoes_pontos.idempotency_key IS 'Chave unica gerada pela API para tornar retries idempotentes';
COMMENT ON COLUMN tb_movimentacoes_pontos.redis_sincronizado IS 'FALSE enquanto a projecao equivalente ainda nao foi aplicada ao Redis';

-- Um unico credito inicial por origem. Estornos/restauracoes podem ocorrer mais
-- de uma vez durante oscilacoes de moderacao, protegidos por idempotency_key.
CREATE UNIQUE INDEX uq_mov_pontos_credito_postagem
    ON tb_movimentacoes_pontos (postagem_id)
    WHERE origem_tipo = 'POSTAGEM' AND tipo_movimentacao = 'CREDITO';

CREATE UNIQUE INDEX uq_mov_pontos_credito_quiz
    ON tb_movimentacoes_pontos (tentativa_quiz_id)
    WHERE origem_tipo = 'QUIZ' AND tipo_movimentacao = 'CREDITO';

-- Indices minimos para historico, retry Redis e calculo de teto diario.
CREATE INDEX idx_mov_pontos_usuario_ocorrido
    ON tb_movimentacoes_pontos (usuario_id, ocorrido_em);
CREATE INDEX idx_mov_pontos_condominio_ocorrido
    ON tb_movimentacoes_pontos (condominio_id, ocorrido_em);
CREATE INDEX idx_mov_pontos_postagem
    ON tb_movimentacoes_pontos (postagem_id);
CREATE INDEX idx_mov_pontos_tentativa_quiz
    ON tb_movimentacoes_pontos (tentativa_quiz_id);
CREATE INDEX idx_mov_pontos_redis_pendente
    ON tb_movimentacoes_pontos (redis_sincronizado, ocorrido_em);
CREATE INDEX idx_mov_pontos_postagem_tipo
    ON tb_movimentacoes_pontos (postagem_id, tipo_movimentacao);
CREATE INDEX idx_postagens_janela_validacao
    ON tb_postagens (data_limite_analise, resolvido_em);
CREATE INDEX idx_postagens_usuario_categoria_data
    ON tb_postagens (usuario_id, categoria_id, data_postagem);
CREATE INDEX idx_tentativas_quiz_usuario_quiz_aprovado
    ON tb_tentativas_quiz (usuario_id, quiz_id, aprovado);

-- CHECKs nao conseguem consultar outra linha. Este trigger garante que todo
-- ESTORNO/RESTAURACAO referencia um CREDITO da mesma origem, usuario e valor.
CREATE OR REPLACE FUNCTION fn_validar_referencia_movimentacao_pontos()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_ref tb_movimentacoes_pontos%ROWTYPE;
BEGIN
    IF NEW.tipo_movimentacao IN ('ESTORNO', 'RESTAURACAO') THEN
        SELECT *
          INTO v_ref
          FROM tb_movimentacoes_pontos
         WHERE id_movimentacao = NEW.movimentacao_referencia_id;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Movimentacao de referencia % nao encontrada', NEW.movimentacao_referencia_id;
        END IF;

        IF v_ref.tipo_movimentacao <> 'CREDITO' THEN
            RAISE EXCEPTION 'ESTORNO/RESTAURACAO deve referenciar um CREDITO original';
        END IF;

        IF v_ref.usuario_id <> NEW.usuario_id
           OR v_ref.origem_tipo <> NEW.origem_tipo
           OR v_ref.pontos <> NEW.pontos
           OR v_ref.postagem_id IS DISTINCT FROM NEW.postagem_id
           OR v_ref.tentativa_quiz_id IS DISTINCT FROM NEW.tentativa_quiz_id THEN
            RAISE EXCEPTION 'Movimentacao de referencia nao corresponde a mesma origem/usuario/valor';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validar_referencia_movimentacao_pontos
BEFORE INSERT OR UPDATE OF movimentacao_referencia_id, tipo_movimentacao, pontos,
                         usuario_id, origem_tipo, postagem_id, tentativa_quiz_id
ON tb_movimentacoes_pontos
FOR EACH ROW
EXECUTE FUNCTION fn_validar_referencia_movimentacao_pontos();



-- ============================================================================
-- SECAO 10 - AUDITORIA (CLASS TABLE INHERITANCE)
-- ============================================================================


CREATE TABLE tb_log_auditoria (
    id_auditoria              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tipo_evento_auditado_id   INTEGER      NOT NULL,
    tipo_operacao_id          INTEGER      NOT NULL,
    executado_por             VARCHAR(100) NOT NULL DEFAULT CURRENT_USER,
    executado_em              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT fk_auditoria_log_tipo_evento_auditado_id FOREIGN KEY (tipo_evento_auditado_id) REFERENCES tb_lkp_tipos_eventos_auditados (id_tipo_evento_auditado),
    CONSTRAINT fk_auditoria_log_tipo_operacao_id FOREIGN KEY (tipo_operacao_id) REFERENCES tb_lkp_tipos_operacoes_auditoria (id_tipo_operacao)
);
COMMENT ON COLUMN tb_log_auditoria.tipo_evento_auditado_id IS 'Discriminador rapido (qual subtipo tem os detalhes)';
COMMENT ON COLUMN tb_log_auditoria.tipo_operacao_id IS 'INSERT / UPDATE / DELETE';
COMMENT ON COLUMN tb_log_auditoria.executado_por IS 'Usuario/role de banco que executou';
COMMENT ON COLUMN tb_log_auditoria.executado_em IS 'Momento da operacao';

CREATE TABLE tb_log_auditoria_postagens (
    id_auditoria_postagem          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    auditoria_id                   BIGINT  NOT NULL,
    postagem_id                    INTEGER NOT NULL,
    status_validacao_anterior_id   INTEGER,
    status_validacao_novo_id       INTEGER,
    saldo_confianca_anterior       INTEGER,
    saldo_confianca_novo           INTEGER,
    CONSTRAINT fk_auditoria_postagens_auditoria_id FOREIGN KEY (auditoria_id) REFERENCES tb_log_auditoria (id_auditoria),
    CONSTRAINT fk_auditoria_postagens_postagem_id FOREIGN KEY (postagem_id) REFERENCES tb_postagens (id_postagem),
    CONSTRAINT fk_auditoria_postagens_status_validacao_anterior_id FOREIGN KEY (status_validacao_anterior_id) REFERENCES tb_lkp_status_validacoes_postagens (id_status_validacao),
    CONSTRAINT fk_auditoria_postagens_status_validacao_novo_id FOREIGN KEY (status_validacao_novo_id) REFERENCES tb_lkp_status_validacoes_postagens (id_status_validacao),
    CONSTRAINT uq_auditoria_postagens_auditoria_id UNIQUE (auditoria_id)
);
COMMENT ON COLUMN tb_log_auditoria_postagens.auditoria_id IS 'Vinculo 1:1 com a mae';
COMMENT ON COLUMN tb_log_auditoria_postagens.postagem_id IS 'Postagem auditada';
COMMENT ON COLUMN tb_log_auditoria_postagens.status_validacao_anterior_id IS 'Status de validacao antes da operacao';
COMMENT ON COLUMN tb_log_auditoria_postagens.status_validacao_novo_id IS 'Status de validacao apos a operacao';
COMMENT ON COLUMN tb_log_auditoria_postagens.saldo_confianca_anterior IS 'saldo_confianca antes da operacao';
COMMENT ON COLUMN tb_log_auditoria_postagens.saldo_confianca_novo IS 'saldo_confianca apos a operacao';

CREATE TABLE tb_log_auditoria_agendamentos_coletas (
    id_auditoria_agendamento  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    auditoria_id              BIGINT  NOT NULL,
    agendamento_coleta_id     INTEGER NOT NULL,
    status_anterior_id        INTEGER,
    status_novo_id            INTEGER,
    data_inicio_anterior      TIMESTAMPTZ,
    data_inicio_novo          TIMESTAMPTZ,
    data_fim_anterior         TIMESTAMPTZ,
    data_fim_novo             TIMESTAMPTZ,
    CONSTRAINT fk_auditoria_agendamentos_coletas_auditoria_id FOREIGN KEY (auditoria_id) REFERENCES tb_log_auditoria (id_auditoria),
    CONSTRAINT fk_auditoria_agendamentos_coletas_agendamento_coleta_id FOREIGN KEY (agendamento_coleta_id) REFERENCES tb_agendamentos_coletas (id_agendamento_coleta),
    CONSTRAINT fk_auditoria_agendamentos_coletas_status_anterior_id FOREIGN KEY (status_anterior_id) REFERENCES tb_lkp_status_agendamentos (id_status),
    CONSTRAINT fk_auditoria_agendamentos_coletas_status_novo_id FOREIGN KEY (status_novo_id) REFERENCES tb_lkp_status_agendamentos (id_status),
    CONSTRAINT uq_auditoria_agendamentos_coletas_auditoria_id UNIQUE (auditoria_id)
);
COMMENT ON COLUMN tb_log_auditoria_agendamentos_coletas.id_auditoria_agendamento IS 'Identificador do subtipo';
COMMENT ON COLUMN tb_log_auditoria_agendamentos_coletas.auditoria_id IS 'Vinculo 1:1 com a mae';
COMMENT ON COLUMN tb_log_auditoria_agendamentos_coletas.agendamento_coleta_id IS 'Agendamento auditado';
COMMENT ON COLUMN tb_log_auditoria_agendamentos_coletas.status_anterior_id IS 'Status antes da operacao';
COMMENT ON COLUMN tb_log_auditoria_agendamentos_coletas.status_novo_id IS 'Status apos a operacao';
COMMENT ON COLUMN tb_log_auditoria_agendamentos_coletas.data_inicio_anterior IS 'data_inicio antes da alteracao';
COMMENT ON COLUMN tb_log_auditoria_agendamentos_coletas.data_inicio_novo IS 'data_inicio apos a alteracao';
COMMENT ON COLUMN tb_log_auditoria_agendamentos_coletas.data_fim_anterior IS 'data_fim antes da alteracao';
COMMENT ON COLUMN tb_log_auditoria_agendamentos_coletas.data_fim_novo IS 'data_fim apos a alteracao';

CREATE TABLE tb_log_auditoria_usuarios_condominios (
    id_auditoria_usuario_condominio  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    auditoria_id                     BIGINT  NOT NULL,
    usuario_condominio_id            INTEGER NOT NULL,
    aprovado_anterior                BOOLEAN,
    aprovado_novo                    BOOLEAN,
    data_saida_anterior              TIMESTAMPTZ,
    data_saida_novo                  TIMESTAMPTZ,
    CONSTRAINT fk_auditoria_usuarios_condominios_auditoria_id FOREIGN KEY (auditoria_id) REFERENCES tb_log_auditoria (id_auditoria),
    CONSTRAINT fk_auditoria_usuarios_condominios_usuario_condominio_id FOREIGN KEY (usuario_condominio_id) REFERENCES tb_rel_usuarios_condominios (id_usuario_condominio),
    CONSTRAINT uq_auditoria_usuarios_condominios_auditoria_id UNIQUE (auditoria_id)
);
COMMENT ON COLUMN tb_log_auditoria_usuarios_condominios.id_auditoria_usuario_condominio IS 'Identificador do subtipo';
COMMENT ON COLUMN tb_log_auditoria_usuarios_condominios.auditoria_id IS 'Vinculo 1:1 com a mae';
COMMENT ON COLUMN tb_log_auditoria_usuarios_condominios.usuario_condominio_id IS 'Vinculo auditado';
COMMENT ON COLUMN tb_log_auditoria_usuarios_condominios.aprovado_anterior IS 'Valor de aprovado antes da operacao';
COMMENT ON COLUMN tb_log_auditoria_usuarios_condominios.aprovado_novo IS 'Valor de aprovado apos a operacao';
COMMENT ON COLUMN tb_log_auditoria_usuarios_condominios.data_saida_anterior IS 'data_saida antes da operacao';
COMMENT ON COLUMN tb_log_auditoria_usuarios_condominios.data_saida_novo IS 'data_saida apos a operacao';

-- ============================================================================
-- ECOCIENTE | OBJETOS LOGICOS E OTIMIZACAO (DDL COMPLEMENTAR)
-- Continuacao de: ecociente_schema.sql
-- Dialeto: PostgreSQL 14+
--
-- Conteudo:
--   SECAO 11 - FUNCTIONS  (3+)  : regras de negocio criticas, reutilizaveis
--   SECAO 12 - PROCEDURES (4)  : rotinas transacionais criticas (moderacao
--                                 de tb_postagens e recalculo de trust score)
--   SECAO 13 - TRIGGERS DE AUDITORIA (3 tabelas) : populam automaticamente
--                                 as tabelas de auditoria ja existentes no
--                                 schema (tb_log_auditoria + subtipos),
--                                 registrando NEW, OLD, TG_OP e CURRENT_USER
--   SECAO 14 - OTIMIZACAO      : casos de analise com EXPLAIN ANALYZE e
--                                 indices criados para eliminar Seq Scans
--
-- Todos os objetos usam CREATE OR REPLACE / IF NOT EXISTS, portanto o
-- script pode ser executado mais de uma vez com seguranca.
-- ============================================================================


-- ============================================================================
-- SECAO 11 - FUNCTIONS (REGRAS DE NEGOCIO)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- FUNCTION 1: fn_pontos_disponiveis_postagem
-- Regra de negocio: cada categoria possui pontos_base e, opcionalmente, um
-- teto DIARIO por usuario. O calculo usa o saldo liquido do ledger oficial:
-- CREDITO + RESTAURACAO - ESTORNO. A data considerada e a data da POSTAGEM,
-- evitando que uma restauracao posterior consuma o teto do dia da restauracao.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_pontos_disponiveis_postagem(
    p_usuario_id      INTEGER,
    p_categoria_id    INTEGER,
    p_data_referencia TIMESTAMPTZ DEFAULT now(),
    p_timezone        TEXT DEFAULT 'America/Sao_Paulo'
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_pontos_base      INTEGER;
    v_limite_diario    INTEGER;
    v_pontos_validos   INTEGER;
    v_pontos_conceder  INTEGER;
    v_data_local       DATE;
    v_inicio_dia       TIMESTAMPTZ;
    v_fim_dia          TIMESTAMPTZ;
BEGIN
    SELECT pontos_base, limite_pontos_diario
      INTO v_pontos_base, v_limite_diario
      FROM tb_lkp_categorias_residuos
     WHERE id_categoria = p_categoria_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Categoria de residuo % nao encontrada', p_categoria_id;
    END IF;

    IF v_limite_diario IS NULL THEN
        RETURN v_pontos_base;
    END IF;

    -- Converte a referencia para o dia civil do timezone configurado e cria
    -- limites TIMESTAMPTZ para permitir filtro eficiente em data_postagem.
    v_data_local := (p_data_referencia AT TIME ZONE p_timezone)::DATE;
    v_inicio_dia := (v_data_local::TIMESTAMP AT TIME ZONE p_timezone);
    v_fim_dia    := ((v_data_local + 1)::TIMESTAMP AT TIME ZONE p_timezone);

    SELECT COALESCE(SUM(
        CASE mp.tipo_movimentacao
            WHEN 'CREDITO'     THEN mp.pontos
            WHEN 'RESTAURACAO' THEN mp.pontos
            WHEN 'ESTORNO'     THEN -mp.pontos
            ELSE 0
        END
    ), 0)::INTEGER
      INTO v_pontos_validos
      FROM tb_movimentacoes_pontos mp
      JOIN tb_postagens p ON p.id_postagem = mp.postagem_id
     WHERE mp.origem_tipo = 'POSTAGEM'
       AND mp.usuario_id = p_usuario_id
       AND mp.categoria_id = p_categoria_id
       AND p.data_postagem >= v_inicio_dia
       AND p.data_postagem <  v_fim_dia;

    IF v_pontos_validos < 0 THEN
        RAISE EXCEPTION 'Inconsistencia no ledger: saldo diario negativo para usuario %, categoria %',
            p_usuario_id, p_categoria_id;
    END IF;

    v_pontos_conceder := GREATEST(
        LEAST(v_pontos_base, v_limite_diario - v_pontos_validos),
        0
    );

    RETURN v_pontos_conceder;
END;
$$;
COMMENT ON FUNCTION fn_pontos_disponiveis_postagem IS
    'Calcula pontos disponiveis para uma nova postagem usando teto diario e saldo liquido do ledger oficial tb_movimentacoes_pontos, no timezone informado.';


-- ----------------------------------------------------------------------------
-- FUNCTION 2: fn_calcular_trust_score
-- Regra de negocio: formula que determina o trust_score de um usuario dentro
-- de um condominio (tb_rel_usuarios_condominios.trust_score), usada para decidir
-- a promocao ao nivel de confianca "pessoa_confiavel". Isolada em uma
-- function pura (IMMUTABLE) para ser reaproveitada tanto pela procedure de
-- recalculo quanto por relatorios/consultas avulsas.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_calcular_trust_score(
    p_postagens_validadas   INTEGER,
    p_denuncias_realizadas  INTEGER,
    p_denuncias_procedentes INTEGER
)
RETURNS DECIMAL(6,2)
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_taxa_acerto DECIMAL(5,2);
    v_score       DECIMAL(6,2);
BEGIN
    IF p_denuncias_realizadas > 0 THEN
        v_taxa_acerto := ROUND(100.0 * p_denuncias_procedentes / p_denuncias_realizadas, 2);
    ELSE
        v_taxa_acerto := 0;
    END IF;

    -- Regra de negocio:
    --   +2 pontos por postagem validada sem contestacao
    --   +5 pontos por denuncia procedente (credibilidade como moderador)
    --   + metade da taxa de acerto de denuncias (0 a 50 pontos)
    --   teto de 1000 pontos
    v_score := LEAST(
        (p_postagens_validadas * 2) + (p_denuncias_procedentes * 5) + (v_taxa_acerto * 0.5),
        1000
    );

    RETURN v_score;
END;
$$;
COMMENT ON FUNCTION fn_calcular_trust_score IS
    'Formula de calculo do trust_score de tb_rel_usuarios_condominios a partir dos contadores de tb_postagens validadas e denuncias.';


-- ============================================================================
-- SECAO 12 - PROCEDURES (ROTINAS TRANSACIONAIS CRITICAS)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- PROCEDURE 1: sp_processar_voto_postagem
-- Registra o voto ponderado durante a janela comunitaria. Cruzar -5 nao encerra
-- a postagem: apenas muda o estado desejado da pontuacao para inativo e marca
-- reconciliacao pendente. Se a postagem recuperar saldo >= 0 ainda dentro das
-- 24h, a pontuacao volta a ativa e a API deve registrar RESTAURACAO.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE sp_processar_voto_postagem(
    p_postagem_id        INTEGER,
    p_usuario_id         INTEGER,
    p_tipo_voto          VARCHAR,
    p_motivo_denuncia_id INTEGER DEFAULT NULL,
    p_comentario         VARCHAR DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_condominio_id       INTEGER;
    v_resolvido_em        TIMESTAMPTZ;
    v_data_limite         TIMESTAMPTZ;
    v_peso                INTEGER;
    v_tipo_voto_id        INTEGER;
    v_saldo_atual         INTEGER;
    v_novo_saldo          INTEGER;
    v_pontuacao_ativa     BOOLEAN;
    v_nova_pontuacao_ativa BOOLEAN;
    v_mudou_estado        BOOLEAN := FALSE;
BEGIN
    SELECT id_tipo_voto
      INTO v_tipo_voto_id
      FROM tb_lkp_tipos_votos_postagens
     WHERE nome_tipo = p_tipo_voto;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Tipo de voto invalido: %', p_tipo_voto;
    END IF;

    IF p_tipo_voto = 'denunciar' AND p_motivo_denuncia_id IS NULL THEN
        RAISE EXCEPTION 'motivo_denuncia_id e obrigatorio para votos de denuncia';
    END IF;

    IF p_tipo_voto = 'aprovar' AND p_motivo_denuncia_id IS NOT NULL THEN
        RAISE EXCEPTION 'motivo_denuncia_id deve ser nulo para votos de aprovacao';
    END IF;

    -- Trava a postagem para serializar votos concorrentes.
    SELECT condominio_id,
           saldo_confianca,
           resolvido_em,
           data_limite_analise,
           pontuacao_ativa
      INTO v_condominio_id,
           v_saldo_atual,
           v_resolvido_em,
           v_data_limite,
           v_pontuacao_ativa
      FROM tb_postagens
     WHERE id_postagem = p_postagem_id
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Postagem % nao encontrada', p_postagem_id;
    END IF;

    IF v_resolvido_em IS NOT NULL THEN
        RAISE EXCEPTION 'Postagem % ja possui decisao de encerramento e nao aceita novos votos', p_postagem_id;
    END IF;

    IF now() >= v_data_limite THEN
        RAISE EXCEPTION 'Janela comunitaria da postagem % encerrou em %', p_postagem_id, v_data_limite;
    END IF;

    SELECT nc.peso_voto
      INTO v_peso
      FROM tb_rel_usuarios_condominios uco
      JOIN tb_lkp_niveis_confianca nc
        ON nc.id_nivel_confianca = uco.nivel_confianca_id
     WHERE uco.usuario_id    = p_usuario_id
       AND uco.condominio_id = v_condominio_id
       AND uco.aprovado      = TRUE
       AND uco.data_saida IS NULL;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Usuario % nao possui vinculo aprovado e ativo com o condominio da postagem', p_usuario_id;
    END IF;

    INSERT INTO tb_rel_votos_postagens (
        postagem_id,
        usuario_id,
        tipo_voto_id,
        motivo_denuncia_id,
        peso_aplicado,
        comentario
    ) VALUES (
        p_postagem_id,
        p_usuario_id,
        v_tipo_voto_id,
        p_motivo_denuncia_id,
        v_peso,
        p_comentario
    );

    v_novo_saldo := v_saldo_atual
        + CASE WHEN p_tipo_voto = 'aprovar' THEN v_peso ELSE -v_peso END;

    -- Histerese da pontuacao:
    --   ativa  -> inativa ao atingir <= -5;
    --   inativa -> ativa somente quando recuperar >= 0.
    v_nova_pontuacao_ativa := v_pontuacao_ativa;

    IF v_pontuacao_ativa = TRUE AND v_novo_saldo <= -5 THEN
        v_nova_pontuacao_ativa := FALSE;
        v_mudou_estado := TRUE;
    ELSIF v_pontuacao_ativa = FALSE AND v_novo_saldo >= 0 THEN
        v_nova_pontuacao_ativa := TRUE;
        v_mudou_estado := TRUE;
    END IF;

    UPDATE tb_postagens
       SET saldo_confianca = v_novo_saldo,
           pontuacao_ativa = v_nova_pontuacao_ativa,
           pontuacao_reconciliacao_pendente =
               pontuacao_reconciliacao_pendente OR v_mudou_estado
     WHERE id_postagem = p_postagem_id;

    -- Nao altera status_validacao_id nem resolvido_em aqui.
    -- A API deve reconciliar o ledger quando a flag pendente for TRUE.
END;
$$;
COMMENT ON PROCEDURE sp_processar_voto_postagem IS
    'Registra voto ponderado apenas durante a janela de 24h, sem encerrar a postagem ao cruzar limiares. Sinaliza reconciliacao de pontos em transicoes <= -5 e recuperacao >= 0.';


-- ----------------------------------------------------------------------------
-- PROCEDURE 2: sp_encerrar_janela_postagem
-- Fecha a janela comunitaria e aplica a regra definitiva:
--   saldo >= 0  -> aprovada
--   -1 a -4     -> em_analise
--   saldo <= -5 -> reprovada
-- Para aprovada/reprovada, tambem ajusta o estado desejado da pontuacao e
-- sinaliza reconciliacao se necessario. EM_ANALISE preserva o estado atual.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE sp_encerrar_janela_postagem(
    p_postagem_id INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_saldo                  INTEGER;
    v_data_limite            TIMESTAMPTZ;
    v_resolvido_em           TIMESTAMPTZ;
    v_pontuacao_ativa        BOOLEAN;
    v_nova_pontuacao_ativa   BOOLEAN;
    v_status_destino_id      INTEGER;
    v_status_destino_nome    VARCHAR(30);
    v_mudou_estado           BOOLEAN := FALSE;
BEGIN
    SELECT saldo_confianca,
           data_limite_analise,
           resolvido_em,
           pontuacao_ativa
      INTO v_saldo,
           v_data_limite,
           v_resolvido_em,
           v_pontuacao_ativa
      FROM tb_postagens
     WHERE id_postagem = p_postagem_id
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Postagem % nao encontrada', p_postagem_id;
    END IF;

    IF v_resolvido_em IS NOT NULL THEN
        RETURN; -- idempotente para jobs de fechamento
    END IF;

    IF now() < v_data_limite THEN
        RAISE EXCEPTION 'Janela comunitaria da postagem % ainda esta aberta ate %', p_postagem_id, v_data_limite;
    END IF;

    IF v_saldo >= 0 THEN
        v_status_destino_nome := 'aprovada';
    ELSIF v_saldo <= -5 THEN
        v_status_destino_nome := 'reprovada';
    ELSE
        v_status_destino_nome := 'em_analise';
    END IF;

    SELECT id_status_validacao
      INTO v_status_destino_id
      FROM tb_lkp_status_validacoes_postagens
     WHERE nome_status = v_status_destino_nome;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Status de validacao % nao cadastrado', v_status_destino_nome;
    END IF;

    v_nova_pontuacao_ativa := v_pontuacao_ativa;
    IF v_status_destino_nome = 'aprovada' THEN
        v_nova_pontuacao_ativa := TRUE;
    ELSIF v_status_destino_nome = 'reprovada' THEN
        v_nova_pontuacao_ativa := FALSE;
    END IF;

    v_mudou_estado := (v_nova_pontuacao_ativa IS DISTINCT FROM v_pontuacao_ativa);

    UPDATE tb_postagens
       SET status_validacao_id = v_status_destino_id,
           resolvido_em = now(),
           pontuacao_ativa = v_nova_pontuacao_ativa,
           pontuacao_reconciliacao_pendente =
               pontuacao_reconciliacao_pendente OR v_mudou_estado
     WHERE id_postagem = p_postagem_id;
END;
$$;
COMMENT ON PROCEDURE sp_encerrar_janela_postagem IS
    'Encerra idempotentemente a janela comunitaria de 24h: >=0 aprovada, -1..-4 em_analise, <=-5 reprovada.';


-- ----------------------------------------------------------------------------
-- PROCEDURE 3: sp_decidir_postagem_analise
-- Decisao manual posterior para uma postagem que terminou EM_ANALISE.
-- A autorizacao (sindico/admin) deve ser garantida pela API/Spring Security.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE sp_decidir_postagem_analise(
    p_postagem_id INTEGER,
    p_aprovar     BOOLEAN
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_status_atual_nome       VARCHAR(30);
    v_status_destino_nome     VARCHAR(30);
    v_status_destino_id       INTEGER;
    v_pontuacao_ativa         BOOLEAN;
    v_nova_pontuacao_ativa    BOOLEAN;
    v_mudou_estado            BOOLEAN;
BEGIN
    SELECT sv.nome_status, p.pontuacao_ativa
      INTO v_status_atual_nome, v_pontuacao_ativa
      FROM tb_postagens p
      JOIN tb_lkp_status_validacoes_postagens sv
        ON sv.id_status_validacao = p.status_validacao_id
     WHERE p.id_postagem = p_postagem_id
     FOR UPDATE OF p;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Postagem % nao encontrada', p_postagem_id;
    END IF;

    IF v_status_atual_nome <> 'em_analise' THEN
        RAISE EXCEPTION 'Postagem % nao esta em analise; status atual: %', p_postagem_id, v_status_atual_nome;
    END IF;

    v_status_destino_nome  := CASE WHEN p_aprovar THEN 'aprovada' ELSE 'reprovada' END;
    v_nova_pontuacao_ativa := p_aprovar;
    v_mudou_estado := (v_nova_pontuacao_ativa IS DISTINCT FROM v_pontuacao_ativa);

    SELECT id_status_validacao
      INTO v_status_destino_id
      FROM tb_lkp_status_validacoes_postagens
     WHERE nome_status = v_status_destino_nome;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Status de validacao % nao cadastrado', v_status_destino_nome;
    END IF;

    UPDATE tb_postagens
       SET status_validacao_id = v_status_destino_id,
           resolvido_em = now(),
           pontuacao_ativa = v_nova_pontuacao_ativa,
           pontuacao_reconciliacao_pendente =
               pontuacao_reconciliacao_pendente OR v_mudou_estado
     WHERE id_postagem = p_postagem_id;
END;
$$;
COMMENT ON PROCEDURE sp_decidir_postagem_analise IS
    'Finaliza manualmente uma postagem EM_ANALISE como aprovada ou reprovada e sinaliza reconciliacao de pontos quando necessario.';


-- ----------------------------------------------------------------------------
-- PROCEDURE 4: sp_atualizar_trust_score
-- Regra de negocio: recalcula, a partir dos dados reais de tb_postagens e
-- tb_rel_votos_postagens, os contadores de confianca de um usuario dentro de um
-- condominio (tb_rel_usuarios_condominios) e promove o usuario a "pessoa_confiavel"
-- quando o trust_score ultrapassa o limiar configurado. Reutiliza a
-- fn_calcular_trust_score (SECAO 11) para a formula de calculo.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE sp_atualizar_trust_score(
    p_usuario_id    INTEGER,
    p_condominio_id INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_postagens_validadas  INTEGER;
    v_denuncias_realizadas INTEGER;
    v_denuncias_procedentes INTEGER;
    v_taxa_acerto          DECIMAL(5,2);
    v_novo_score           DECIMAL(6,2);
    v_nivel_confiavel_id   INTEGER;
    v_limite_promocao      CONSTANT DECIMAL := 200.00;
BEGIN
    -- Postagens aprovadas do usuario nesse condominio que nunca receberam denuncia
    SELECT COUNT(*) INTO v_postagens_validadas
      FROM tb_postagens p
      JOIN tb_lkp_status_validacoes_postagens svp ON svp.id_status_validacao = p.status_validacao_id
     WHERE p.usuario_id    = p_usuario_id
       AND p.condominio_id = p_condominio_id
       AND svp.nome_status = 'aprovada'
       AND p.resolvido_em IS NOT NULL
       AND NOT EXISTS (
            SELECT 1
              FROM tb_rel_votos_postagens vp
              JOIN tb_lkp_tipos_votos_postagens tvp ON tvp.id_tipo_voto = vp.tipo_voto_id
             WHERE vp.postagem_id = p.id_postagem
               AND tvp.nome_tipo  = 'denunciar'
       );

    -- Total de denuncias feitas pelo usuario (como denunciante)
    SELECT COUNT(*) FILTER (WHERE tvp.nome_tipo = 'denunciar')
      INTO v_denuncias_realizadas
      FROM tb_rel_votos_postagens vp
      JOIN tb_lkp_tipos_votos_postagens tvp ON tvp.id_tipo_voto = vp.tipo_voto_id
     WHERE vp.usuario_id = p_usuario_id;

    -- Denuncias do usuario cuja postagem denunciada acabou reprovada (procedentes)
    SELECT COUNT(*) FILTER (WHERE tvp.nome_tipo = 'denunciar' AND svp.nome_status = 'reprovada')
      INTO v_denuncias_procedentes
      FROM tb_rel_votos_postagens vp
      JOIN tb_lkp_tipos_votos_postagens tvp        ON tvp.id_tipo_voto = vp.tipo_voto_id
      JOIN tb_postagens p                      ON p.id_postagem = vp.postagem_id
      JOIN tb_lkp_status_validacoes_postagens svp  ON svp.id_status_validacao = p.status_validacao_id
     WHERE vp.usuario_id = p_usuario_id
       AND p.resolvido_em IS NOT NULL;

    IF v_denuncias_realizadas > 0 THEN
        v_taxa_acerto := ROUND(100.0 * v_denuncias_procedentes / v_denuncias_realizadas, 2);
    ELSE
        v_taxa_acerto := NULL;
    END IF;

    v_novo_score := fn_calcular_trust_score(v_postagens_validadas, v_denuncias_realizadas, v_denuncias_procedentes);

    UPDATE tb_rel_usuarios_condominios
       SET postagens_validadas_sem_contestacao = v_postagens_validadas,
           denuncias_realizadas                = v_denuncias_realizadas,
           denuncias_procedentes                = v_denuncias_procedentes,
           taxa_acerto_denuncias                = v_taxa_acerto,
           trust_score                          = v_novo_score
     WHERE usuario_id    = p_usuario_id
       AND condominio_id = p_condominio_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Vinculo usuario % / condominio % nao encontrado', p_usuario_id, p_condominio_id;
    END IF;

    -- Promocao automatica a pessoa_confiavel ao ultrapassar o limiar
    IF v_novo_score >= v_limite_promocao THEN
        SELECT id_nivel_confianca INTO v_nivel_confiavel_id
          FROM tb_lkp_niveis_confianca
         WHERE nome_nivel = 'pessoa_confiavel';

        IF v_nivel_confiavel_id IS NOT NULL THEN
            UPDATE tb_rel_usuarios_condominios
               SET nivel_confianca_id = v_nivel_confiavel_id
             WHERE usuario_id         = p_usuario_id
               AND condominio_id      = p_condominio_id
               AND nivel_confianca_id <> v_nivel_confiavel_id;
        END IF;
    END IF;
END;
$$;
COMMENT ON PROCEDURE sp_atualizar_trust_score IS
    'Recalcula os contadores de confianca e o trust_score de um usuario em um condominio, promovendo-o a pessoa_confiavel quando aplicavel.';


-- ============================================================================
-- SECAO 13 - TRIGGERS DE AUDITORIA
-- Popula automaticamente as tabelas ja modeladas no schema original
-- (tb_log_auditoria + subtipos tb_log_auditoria_postagens / tb_log_auditoria_agendamentos_coletas
-- / tb_log_auditoria_usuarios_condominios), registrando NEW, OLD, TG_OP e CURRENT_USER
-- a cada INSERT/UPDATE/DELETE nas 3 tabelas de negocio mais sensiveis.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 12.1 - Dados de dominio necessarios para os triggers (idempotente)
-- ----------------------------------------------------------------------------
INSERT INTO tb_lkp_tipos_eventos_auditados (nome_evento, descricao)
SELECT 'postagem', 'Auditoria de alteracoes em tb_postagens de residuos'
WHERE NOT EXISTS (SELECT 1 FROM tb_lkp_tipos_eventos_auditados WHERE nome_evento = 'postagem');

INSERT INTO tb_lkp_tipos_eventos_auditados (nome_evento, descricao)
SELECT 'agendamento_coleta', 'Auditoria de alteracoes em agendamentos de coleta'
WHERE NOT EXISTS (SELECT 1 FROM tb_lkp_tipos_eventos_auditados WHERE nome_evento = 'agendamento_coleta');

INSERT INTO tb_lkp_tipos_eventos_auditados (nome_evento, descricao)
SELECT 'usuario_condominio', 'Auditoria de alteracoes no vinculo usuario x condominio'
WHERE NOT EXISTS (SELECT 1 FROM tb_lkp_tipos_eventos_auditados WHERE nome_evento = 'usuario_condominio');

INSERT INTO tb_lkp_tipos_operacoes_auditoria (nome_operacao)
SELECT 'INSERT' WHERE NOT EXISTS (SELECT 1 FROM tb_lkp_tipos_operacoes_auditoria WHERE nome_operacao = 'INSERT');

INSERT INTO tb_lkp_tipos_operacoes_auditoria (nome_operacao)
SELECT 'UPDATE' WHERE NOT EXISTS (SELECT 1 FROM tb_lkp_tipos_operacoes_auditoria WHERE nome_operacao = 'UPDATE');

INSERT INTO tb_lkp_tipos_operacoes_auditoria (nome_operacao)
SELECT 'DELETE' WHERE NOT EXISTS (SELECT 1 FROM tb_lkp_tipos_operacoes_auditoria WHERE nome_operacao = 'DELETE');


-- ----------------------------------------------------------------------------
-- 12.2 - Trigger de auditoria em POSTAGENS
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_trg_auditoria_postagens()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_auditoria_id      BIGINT;
    v_tipo_evento_id    INTEGER;
    v_tipo_operacao_id  INTEGER;
BEGIN
    SELECT id_tipo_evento_auditado INTO v_tipo_evento_id
      FROM tb_lkp_tipos_eventos_auditados WHERE nome_evento = 'postagem';

    SELECT id_tipo_operacao INTO v_tipo_operacao_id
      FROM tb_lkp_tipos_operacoes_auditoria WHERE nome_operacao = TG_OP;

    INSERT INTO tb_log_auditoria (tipo_evento_auditado_id, tipo_operacao_id, executado_por, executado_em)
    VALUES (v_tipo_evento_id, v_tipo_operacao_id, CURRENT_USER, now())
    RETURNING id_auditoria INTO v_auditoria_id;

    IF TG_OP = 'INSERT' THEN
        INSERT INTO tb_log_auditoria_postagens (
            auditoria_id, postagem_id,
            status_validacao_anterior_id, status_validacao_novo_id,
            saldo_confianca_anterior, saldo_confianca_novo
        ) VALUES (
            v_auditoria_id, NEW.id_postagem,
            NULL, NEW.status_validacao_id,
            NULL, NEW.saldo_confianca
        );
        RETURN NEW;

    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO tb_log_auditoria_postagens (
            auditoria_id, postagem_id,
            status_validacao_anterior_id, status_validacao_novo_id,
            saldo_confianca_anterior, saldo_confianca_novo
        ) VALUES (
            v_auditoria_id, NEW.id_postagem,
            OLD.status_validacao_id, NEW.status_validacao_id,
            OLD.saldo_confianca, NEW.saldo_confianca
        );
        RETURN NEW;

    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO tb_log_auditoria_postagens (
            auditoria_id, postagem_id,
            status_validacao_anterior_id, status_validacao_novo_id,
            saldo_confianca_anterior, saldo_confianca_novo
        ) VALUES (
            v_auditoria_id, OLD.id_postagem,
            OLD.status_validacao_id, NULL,
            OLD.saldo_confianca, NULL
        );
        RETURN OLD;
    END IF;

    RETURN NULL;
END;
$$;

CREATE OR REPLACE TRIGGER trg_auditoria_postagens
    AFTER INSERT OR UPDATE OR DELETE ON tb_postagens
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_auditoria_postagens();


-- ----------------------------------------------------------------------------
-- 12.3 - Trigger de auditoria em AGENDAMENTOS_COLETAS
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_trg_auditoria_agendamentos_coletas()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_auditoria_id      BIGINT;
    v_tipo_evento_id    INTEGER;
    v_tipo_operacao_id  INTEGER;
BEGIN
    SELECT id_tipo_evento_auditado INTO v_tipo_evento_id
      FROM tb_lkp_tipos_eventos_auditados WHERE nome_evento = 'agendamento_coleta';

    SELECT id_tipo_operacao INTO v_tipo_operacao_id
      FROM tb_lkp_tipos_operacoes_auditoria WHERE nome_operacao = TG_OP;

    INSERT INTO tb_log_auditoria (tipo_evento_auditado_id, tipo_operacao_id, executado_por, executado_em)
    VALUES (v_tipo_evento_id, v_tipo_operacao_id, CURRENT_USER, now())
    RETURNING id_auditoria INTO v_auditoria_id;

    IF TG_OP = 'INSERT' THEN
        INSERT INTO tb_log_auditoria_agendamentos_coletas (
            auditoria_id, agendamento_coleta_id,
            status_anterior_id, status_novo_id,
            data_inicio_anterior, data_inicio_novo,
            data_fim_anterior, data_fim_novo
        ) VALUES (
            v_auditoria_id, NEW.id_agendamento_coleta,
            NULL, NEW.status_agendamento_id,
            NULL, NEW.data_inicio,
            NULL, NEW.data_fim
        );
        RETURN NEW;

    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO tb_log_auditoria_agendamentos_coletas (
            auditoria_id, agendamento_coleta_id,
            status_anterior_id, status_novo_id,
            data_inicio_anterior, data_inicio_novo,
            data_fim_anterior, data_fim_novo
        ) VALUES (
            v_auditoria_id, NEW.id_agendamento_coleta,
            OLD.status_agendamento_id, NEW.status_agendamento_id,
            OLD.data_inicio, NEW.data_inicio,
            OLD.data_fim, NEW.data_fim
        );
        RETURN NEW;

    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO tb_log_auditoria_agendamentos_coletas (
            auditoria_id, agendamento_coleta_id,
            status_anterior_id, status_novo_id,
            data_inicio_anterior, data_inicio_novo,
            data_fim_anterior, data_fim_novo
        ) VALUES (
            v_auditoria_id, OLD.id_agendamento_coleta,
            OLD.status_agendamento_id, NULL,
            OLD.data_inicio, NULL,
            OLD.data_fim, NULL
        );
        RETURN OLD;
    END IF;

    RETURN NULL;
END;
$$;

CREATE OR REPLACE TRIGGER trg_auditoria_agendamentos_coletas
    AFTER INSERT OR UPDATE OR DELETE ON tb_agendamentos_coletas
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_auditoria_agendamentos_coletas();


-- ----------------------------------------------------------------------------
-- 12.4 - Trigger de auditoria em USUARIOS_CONDOMINIOS
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_trg_auditoria_usuarios_condominios()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_auditoria_id      BIGINT;
    v_tipo_evento_id    INTEGER;
    v_tipo_operacao_id  INTEGER;
BEGIN
    SELECT id_tipo_evento_auditado INTO v_tipo_evento_id
      FROM tb_lkp_tipos_eventos_auditados WHERE nome_evento = 'usuario_condominio';

    SELECT id_tipo_operacao INTO v_tipo_operacao_id
      FROM tb_lkp_tipos_operacoes_auditoria WHERE nome_operacao = TG_OP;

    INSERT INTO tb_log_auditoria (tipo_evento_auditado_id, tipo_operacao_id, executado_por, executado_em)
    VALUES (v_tipo_evento_id, v_tipo_operacao_id, CURRENT_USER, now())
    RETURNING id_auditoria INTO v_auditoria_id;

    IF TG_OP = 'INSERT' THEN
        INSERT INTO tb_log_auditoria_usuarios_condominios (
            auditoria_id, usuario_condominio_id,
            aprovado_anterior, aprovado_novo,
            data_saida_anterior, data_saida_novo
        ) VALUES (
            v_auditoria_id, NEW.id_usuario_condominio,
            NULL, NEW.aprovado,
            NULL, NEW.data_saida
        );
        RETURN NEW;

    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO tb_log_auditoria_usuarios_condominios (
            auditoria_id, usuario_condominio_id,
            aprovado_anterior, aprovado_novo,
            data_saida_anterior, data_saida_novo
        ) VALUES (
            v_auditoria_id, NEW.id_usuario_condominio,
            OLD.aprovado, NEW.aprovado,
            OLD.data_saida, NEW.data_saida
        );
        RETURN NEW;

    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO tb_log_auditoria_usuarios_condominios (
            auditoria_id, usuario_condominio_id,
            aprovado_anterior, aprovado_novo,
            data_saida_anterior, data_saida_novo
        ) VALUES (
            v_auditoria_id, OLD.id_usuario_condominio,
            OLD.aprovado, NULL,
            OLD.data_saida, NULL
        );
        RETURN OLD;
    END IF;

    RETURN NULL;
END;
$$;

CREATE OR REPLACE TRIGGER trg_auditoria_usuarios_condominios
    AFTER INSERT OR UPDATE OR DELETE ON tb_rel_usuarios_condominios
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_auditoria_usuarios_condominios();


-- ============================================================================
-- SECAO 14 - OTIMIZACAO (EXPLAIN ANALYZE + INDICES)
--
-- Metodologia: para cada consulta critica do fluxo de moderacao/dashboard,
-- o comando EXPLAIN ANALYZE abaixo permite comparar o plano de execucao
-- antes e depois de criar o indice correspondente. Sem o indice, o
-- planner recorre a Seq Scan na tabela inteira; apos a criacao do indice,
-- o plano passa a usar Index Scan / Index Only Scan, reduzindo o custo
-- estimado e o tempo de execucao real. Execute cada bloco "ANTES" e
-- "DEPOIS" no seu ambiente (com dados de teste carregados) para visualizar
-- a mudanca no plano.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- CASO 1 - Fila de moderacao: tb_postagens pendentes de analise por condominio
-- (consulta usada pelo dashboard do sindico e por jobs que verificam o
-- prazo data_limite_analise). Sem indice, forca Seq Scan em "tb_postagens".
-- ----------------------------------------------------------------------------
-- ANTES (rode e observe "Seq Scan on tb_postagens" no plano):
EXPLAIN ANALYZE
SELECT id_postagem, usuario_id, categoria_id, data_limite_analise
  FROM tb_postagens
 WHERE condominio_id = 1
   AND resolvido_em IS NULL
 ORDER BY data_limite_analise;

CREATE INDEX IF NOT EXISTS idx_postagens_pendentes_moderacao
    ON tb_postagens (condominio_id, data_limite_analise)
    WHERE resolvido_em IS NULL;
-- DEPOIS: repita o EXPLAIN ANALYZE acima e compare -> "Index Scan using idx_postagens_pendentes_moderacao"


-- ----------------------------------------------------------------------------
-- CASO 2 - Historico de denuncias de um usuario (usado por
-- sp_atualizar_trust_score). O indice unico existente (postagem_id, usuario_id)
-- nao atende buscas apenas por usuario_id, exigindo Seq Scan em tb_rel_votos_postagens.
-- ----------------------------------------------------------------------------
-- ANTES:
EXPLAIN ANALYZE
SELECT vp.id_voto, vp.postagem_id, vp.votado_em
  FROM tb_rel_votos_postagens vp
  JOIN tb_lkp_tipos_votos_postagens tvp ON tvp.id_tipo_voto = vp.tipo_voto_id
 WHERE vp.usuario_id = 1
   AND tvp.nome_tipo = 'denunciar';

CREATE INDEX IF NOT EXISTS idx_votos_postagens_usuario_id
    ON tb_rel_votos_postagens (usuario_id);
-- DEPOIS: "Index Scan using idx_votos_postagens_usuario_id" em vez de Seq Scan


-- ----------------------------------------------------------------------------
-- CASO 3 - Relatorio de auditoria por periodo (tela de compliance/LGPD),
-- consulta tb_log_auditoria filtrando por data e ordenando pela mais recente.
-- ----------------------------------------------------------------------------
-- ANTES:
EXPLAIN ANALYZE
SELECT id_auditoria, tipo_evento_auditado_id, tipo_operacao_id, executado_por, executado_em
  FROM tb_log_auditoria
 WHERE executado_em >= now() - INTERVAL '30 days'
 ORDER BY executado_em DESC;

CREATE INDEX IF NOT EXISTS idx_auditoria_log_executado_em
    ON tb_log_auditoria (executado_em DESC);
-- DEPOIS: "Index Scan using idx_auditoria_log_executado_em", elimina o Sort explicito


-- ----------------------------------------------------------------------------
-- CASO 4 - Indicadores de desempenho por condominio (base da view
-- vw_desempenho_condominio), que agrupa tb_postagens por condominio e status.
-- ----------------------------------------------------------------------------
-- ANTES:
EXPLAIN ANALYZE
SELECT condominio_id, status_validacao_id, COUNT(*)
  FROM tb_postagens
 WHERE condominio_id = 1
 GROUP BY condominio_id, status_validacao_id;

CREATE INDEX IF NOT EXISTS idx_postagens_condominio_status
    ON tb_postagens (condominio_id, status_validacao_id);


-- ----------------------------------------------------------------------------
-- Indices adicionais de chave estrangeira / colunas de filtro frequente
-- (Postgres nao cria indice automatico em colunas FK; sem eles, os JOINs
-- das views analiticas e das procedures acima recorrem a Seq Scan+Hash Join
-- em tabelas grandes).
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_postagens_usuario_categoria_data
    ON tb_postagens (usuario_id, categoria_id, data_postagem);
    -- suporta fn_pontos_disponiveis_postagem (SECAO 10)

CREATE INDEX IF NOT EXISTS idx_agendamentos_coletas_condominio_id
    ON tb_agendamentos_coletas (condominio_id);

CREATE INDEX IF NOT EXISTS idx_agendamentos_coletas_cooperativa_id
    ON tb_agendamentos_coletas (cooperativa_id);

CREATE INDEX IF NOT EXISTS idx_visitas_coletas_agendamento_coleta_id
    ON tb_visitas_coletas (agendamento_coleta_id);

CREATE INDEX IF NOT EXISTS idx_tentativas_quiz_usuario_id
    ON tb_tentativas_quiz (usuario_id);

CREATE INDEX IF NOT EXISTS idx_tentativas_quiz_quiz_id
    ON tb_tentativas_quiz (quiz_id);

CREATE INDEX IF NOT EXISTS idx_moradores_condominio_id
    ON tb_moradores (condominio_id);


-- ============================================================================
-- FIM DE OBJETOS LOGICOS
-- ============================================================================

-- ============================================================================
-- ECOCIENTE | VIEWS ANALITICAS
--
-- ============================================================================
-- 1. Acoes realizadas por morador (fotos postadas e tb_quizzes concluidos)
-- ============================================================================
CREATE OR REPLACE VIEW vw_engajamento_moradores AS
WITH morador_base AS (
    SELECT
        m.id_morador,
        u.id_usuario,
        u.nome_usuario,
        m.condominio_id,
        c.nome_condominio
    FROM tb_moradores m
    JOIN tb_usuarios u ON u.id_usuario = m.usuario_id
    LEFT JOIN tb_condominios c ON c.id_condominio = m.condominio_id
),
acoes_foto AS (
    SELECT
        p.usuario_id,
        p.condominio_id,
        COUNT(*)::BIGINT AS qtd_fotos
    FROM tb_postagens p
    GROUP BY p.usuario_id, p.condominio_id
),
acoes_quiz AS (
    SELECT
        uc.usuario_id,
        COUNT(*) FILTER (WHERE uc.concluido = TRUE)::BIGINT AS qtd_quizzes
    FROM tb_rel_usuarios_cursos uc
    GROUP BY uc.usuario_id
)
SELECT
    mb.id_morador,
    mb.id_usuario,
    mb.nome_usuario,
    mb.condominio_id,
    mb.nome_condominio,
    COALESCE(af.qtd_fotos, 0)   AS qtd_fotos_realizadas,
    COALESCE(aq.qtd_quizzes, 0) AS qtd_quizzes_realizados,
    COALESCE(af.qtd_fotos, 0) + COALESCE(aq.qtd_quizzes, 0) AS qtd_acoes_total
FROM morador_base mb
LEFT JOIN acoes_foto af
       ON af.usuario_id = mb.id_usuario
      AND af.condominio_id IS NOT DISTINCT FROM mb.condominio_id
LEFT JOIN acoes_quiz aq ON aq.usuario_id = mb.id_usuario;

-- ============================================================================
-- 2. Indicadores gerais de sustentabilidade por condominio
-- ============================================================================
CREATE OR REPLACE VIEW vw_desempenho_condominio AS
WITH moradores_condominio AS (
    SELECT
        m.id_morador,
        m.usuario_id,
        m.condominio_id
    FROM tb_moradores m
),
metricas_moradores AS (
    SELECT
        condominio_id,
        COUNT(DISTINCT id_morador)::BIGINT AS total_moradores
    FROM moradores_condominio
    GROUP BY condominio_id
),
metricas_postagens AS (
    SELECT
        p.condominio_id,
        COUNT(DISTINCT p.id_postagem)::BIGINT AS total_postagens,
        COUNT(DISTINCT p.id_postagem) FILTER (WHERE svp.nome_status = 'aprovada')::BIGINT AS postagens_aprovadas,
        COUNT(DISTINCT p.id_postagem) FILTER (WHERE svp.nome_status = 'reprovada')::BIGINT AS postagens_rejeitadas,
        COUNT(DISTINCT p.id_postagem) FILTER (WHERE svp.nome_status = 'em_analise')::BIGINT AS postagens_pendentes
    FROM tb_postagens p
    LEFT JOIN tb_lkp_status_validacoes_postagens svp
           ON svp.id_status_validacao = p.status_validacao_id
    GROUP BY p.condominio_id
),
metricas_quizzes AS (
    SELECT
        mc.condominio_id,
        COUNT(DISTINCT uc.id_usuario_curso) FILTER (WHERE uc.concluido = TRUE)::BIGINT AS quizzes_realizados
    FROM moradores_condominio mc
    JOIN tb_rel_usuarios_cursos uc ON uc.usuario_id = mc.usuario_id
    GROUP BY mc.condominio_id
),
metricas_coletas AS (
    SELECT
        ac.condominio_id,
        COUNT(DISTINCT vc.id_visita_coleta)::BIGINT AS tb_visitas_coletas,
        COUNT(DISTINCT vc.id_visita_coleta) FILTER (WHERE vc.foi_realizada = TRUE)::BIGINT AS visitas_coletas_realizadas
    FROM tb_agendamentos_coletas ac
    LEFT JOIN tb_visitas_coletas vc ON vc.agendamento_coleta_id = ac.id_agendamento_coleta
    GROUP BY ac.condominio_id
)
SELECT
    c.id_condominio,
    c.nome_condominio,
    COALESCE(mm.total_moradores, 0)            AS total_moradores,
    COALESCE(mp.total_postagens, 0)            AS total_postagens,
    COALESCE(mp.postagens_aprovadas, 0)        AS postagens_aprovadas,
    COALESCE(mp.postagens_rejeitadas, 0)       AS postagens_rejeitadas,
    COALESCE(mp.postagens_pendentes, 0)        AS postagens_pendentes,
    COALESCE(mq.quizzes_realizados, 0)         AS quizzes_realizados,
    COALESCE(mc.tb_visitas_coletas, 0)         AS tb_visitas_coletas,
    COALESCE(mc.visitas_coletas_realizadas, 0) AS visitas_coletas_realizadas
FROM tb_condominios c
LEFT JOIN metricas_moradores mm ON mm.condominio_id = c.id_condominio
LEFT JOIN metricas_postagens mp ON mp.condominio_id = c.id_condominio
LEFT JOIN metricas_quizzes  mq ON mq.condominio_id = c.id_condominio
LEFT JOIN metricas_coletas  mc ON mc.condominio_id = c.id_condominio;

-- ============================================================================
-- 3. Quantidade de tb_postagens por categoria de residuo
-- ============================================================================
CREATE OR REPLACE VIEW vw_postagens_por_categoria AS
SELECT
    cr.id_categoria,
    cr.nome_categoria,
    COUNT(p.id_postagem)::BIGINT AS qtd_postagens,
    COUNT(p.id_postagem) FILTER (WHERE svp.nome_status = 'aprovada')::BIGINT AS qtd_aprovadas,
    COUNT(p.id_postagem) FILTER (WHERE svp.nome_status = 'reprovada')::BIGINT AS qtd_rejeitadas,
    COUNT(p.id_postagem) FILTER (WHERE svp.nome_status = 'em_analise')::BIGINT AS qtd_pendentes
FROM tb_lkp_categorias_residuos cr
LEFT JOIN tb_postagens p
       ON p.categoria_id = cr.id_categoria
LEFT JOIN tb_lkp_status_validacoes_postagens svp
       ON svp.id_status_validacao = p.status_validacao_id
GROUP BY
    cr.id_categoria,
    cr.nome_categoria;

-- ============================================================================
-- 4. Taxa de aprovacao, rejeicao e pendencia das tb_postagens
-- ============================================================================
CREATE OR REPLACE VIEW vw_postagens_aprovadas_rejeitadas_condominio AS
SELECT
    p.condominio_id,
    c.nome_condominio,
    COUNT(*)::BIGINT AS total_postagens,
    COUNT(*) FILTER (WHERE svp.nome_status = 'aprovada')::BIGINT AS qtd_aprovadas,
    COUNT(*) FILTER (WHERE svp.nome_status = 'reprovada')::BIGINT AS qtd_rejeitadas,
    COUNT(*) FILTER (WHERE svp.nome_status = 'em_analise')::BIGINT AS qtd_pendentes,
    ROUND(100.0 * COUNT(*) FILTER (WHERE svp.nome_status = 'aprovada') / NULLIF(COUNT(*), 0), 2) AS taxa_aprovacao_percentual,
    ROUND(100.0 * COUNT(*) FILTER (WHERE svp.nome_status = 'reprovada') / NULLIF(COUNT(*), 0), 2) AS taxa_rejeicao_percentual,
    ROUND(100.0 * COUNT(*) FILTER (WHERE svp.nome_status = 'em_analise') / NULLIF(COUNT(*), 0), 2) AS taxa_pendencia_percentual
FROM tb_postagens p
LEFT JOIN tb_condominios c ON c.id_condominio = p.condominio_id
LEFT JOIN tb_lkp_status_validacoes_postagens svp ON svp.id_status_validacao = p.status_validacao_id
GROUP BY p.condominio_id, c.nome_condominio;

-- ============================================================================
-- 5. Evolucao dos residuos registrados ao longo do tempo
-- ============================================================================
CREATE OR REPLACE VIEW vw_residuos_por_periodo AS
SELECT
    EXTRACT(YEAR FROM p.data_postagem)::INTEGER AS ano,
    EXTRACT(MONTH FROM p.data_postagem)::INTEGER AS mes,
    MAKE_DATE(
        EXTRACT(YEAR FROM p.data_postagem)::INTEGER,
        EXTRACT(MONTH FROM p.data_postagem)::INTEGER,
        1
    ) AS periodo,
    COUNT(p.id_postagem)::BIGINT AS qtd_residuos_registrados
FROM tb_postagens p
GROUP BY
    EXTRACT(YEAR FROM p.data_postagem),
    EXTRACT(MONTH FROM p.data_postagem)
ORDER BY
    ano,
    mes;

-- ============================================================================
-- 6. Participacao dos tb_moradores nas acoes ambientais
-- ============================================================================
CREATE OR REPLACE VIEW vw_participacao_sustentabilidade AS
WITH moradores_condominio AS (
    SELECT
        m.id_morador,
        m.usuario_id,
        m.condominio_id
    FROM tb_moradores m
),
acoes AS (
    SELECT DISTINCT
        p.usuario_id,
        p.condominio_id
    FROM tb_postagens p
    UNION
    SELECT DISTINCT
        uc.usuario_id,
        mc.condominio_id
    FROM tb_rel_usuarios_cursos uc
    JOIN moradores_condominio mc ON mc.usuario_id = uc.usuario_id
    WHERE uc.concluido = TRUE
)
SELECT
    c.id_condominio,
    c.nome_condominio,
    COUNT(DISTINCT mc.id_morador)::BIGINT AS total_moradores,
    COUNT(DISTINCT mc.id_morador) FILTER (WHERE a.usuario_id IS NOT NULL)::BIGINT AS moradores_participantes,
    ROUND(
        100.0 * COUNT(DISTINCT mc.id_morador) FILTER (WHERE a.usuario_id IS NOT NULL)
        / NULLIF(COUNT(DISTINCT mc.id_morador), 0),
        2
    ) AS taxa_participacao_percentual
FROM tb_condominios c
LEFT JOIN moradores_condominio mc ON mc.condominio_id = c.id_condominio
LEFT JOIN acoes a
       ON a.usuario_id = mc.usuario_id
      AND a.condominio_id IS NOT DISTINCT FROM mc.condominio_id
GROUP BY c.id_condominio, c.nome_condominio;

-- ============================================================================
-- 7. Quantidade de coletas agendadas, realizadas e taxa de sucesso
-- ============================================================================
CREATE OR REPLACE VIEW vw_desempenho_coletas AS
SELECT
    c.id_condominio,
    c.nome_condominio,
    COUNT(DISTINCT ac.id_agendamento_coleta)::BIGINT AS coletas_agendadas,
    COUNT(DISTINCT vc.id_visita_coleta)::BIGINT AS visitas_programadas,
    COUNT(DISTINCT vc.id_visita_coleta) FILTER (WHERE vc.foi_realizada = TRUE)::BIGINT AS coletas_realizadas,
    ROUND(
        100.0 * COUNT(DISTINCT vc.id_visita_coleta) FILTER (WHERE vc.foi_realizada = TRUE)
        / NULLIF(COUNT(DISTINCT vc.id_visita_coleta), 0),
        2
    ) AS taxa_sucesso_percentual
FROM tb_condominios c
LEFT JOIN tb_agendamentos_coletas ac ON ac.condominio_id = c.id_condominio
LEFT JOIN tb_visitas_coletas vc ON vc.agendamento_coleta_id = ac.id_agendamento_coleta
GROUP BY c.id_condominio, c.nome_condominio;

-- ============================================================================
-- 8. Evolucao das coletas por periodo
-- ============================================================================
CREATE OR REPLACE VIEW vw_coletas_por_mes AS
SELECT
    EXTRACT(YEAR FROM COALESCE(vc.data_visita, ac.data_inicio))::INTEGER AS ano,
    EXTRACT(MONTH FROM COALESCE(vc.data_visita, ac.data_inicio))::INTEGER AS mes,
    COUNT(DISTINCT ac.id_agendamento_coleta)::BIGINT AS coletas_agendadas,
    COUNT(DISTINCT vc.id_visita_coleta)::BIGINT AS visitas_programadas,
    COUNT(DISTINCT vc.id_visita_coleta) FILTER (
        WHERE vc.foi_realizada = TRUE
    )::BIGINT AS coletas_realizadas
FROM tb_agendamentos_coletas ac
LEFT JOIN tb_visitas_coletas vc
       ON vc.agendamento_coleta_id = ac.id_agendamento_coleta
GROUP BY
    EXTRACT(YEAR FROM COALESCE(vc.data_visita, ac.data_inicio)),
    EXTRACT(MONTH FROM COALESCE(vc.data_visita, ac.data_inicio));

-- ============================================================================
-- 9. Comparacao das coletas entre tb_condominios
-- ============================================================================
CREATE OR REPLACE VIEW vw_coletas_por_condominio AS
SELECT
    c.id_condominio,
    c.nome_condominio,
    COUNT(DISTINCT ac.id_agendamento_coleta)::BIGINT AS coletas_agendadas,
    COUNT(DISTINCT vc.id_visita_coleta)::BIGINT AS visitas_programadas,
    COUNT(DISTINCT vc.id_visita_coleta) FILTER (WHERE vc.foi_realizada = TRUE)::BIGINT AS coletas_realizadas,
    ROUND(
        100.0 * COUNT(DISTINCT vc.id_visita_coleta) FILTER (WHERE vc.foi_realizada = TRUE)
        / NULLIF(COUNT(DISTINCT vc.id_visita_coleta), 0),
        2
    ) AS taxa_sucesso_percentual
FROM tb_condominios c
LEFT JOIN tb_agendamentos_coletas ac ON ac.condominio_id = c.id_condominio
LEFT JOIN tb_visitas_coletas vc ON vc.agendamento_coleta_id = ac.id_agendamento_coleta
GROUP BY c.id_condominio, c.nome_condominio;

-- ============================================================================
-- 10. Desempenho das tb_cooperativas parceiras
-- ============================================================================
CREATE OR REPLACE VIEW vw_coletas_por_cooperativa AS
SELECT
    coop.id_cooperativa,
    coop.nome_cooperativa,
    COUNT(DISTINCT ac.id_agendamento_coleta)::BIGINT AS coletas_agendadas,
    COUNT(DISTINCT vc.id_visita_coleta)::BIGINT AS visitas_programadas,
    COUNT(DISTINCT vc.id_visita_coleta) FILTER (WHERE vc.foi_realizada = TRUE)::BIGINT AS coletas_realizadas,
    ROUND(
        100.0 * COUNT(DISTINCT vc.id_visita_coleta) FILTER (WHERE vc.foi_realizada = TRUE)
        / NULLIF(COUNT(DISTINCT vc.id_visita_coleta), 0),
        2
    ) AS taxa_sucesso_percentual
FROM tb_cooperativas coop
LEFT JOIN tb_agendamentos_coletas ac ON ac.cooperativa_id = coop.id_cooperativa
LEFT JOIN tb_visitas_coletas vc ON vc.agendamento_coleta_id = ac.id_agendamento_coleta
GROUP BY coop.id_cooperativa, coop.nome_cooperativa;

-- ============================================================================
-- 11. Percentual de comparecimento das tb_cooperativas aos agendamentos
-- ============================================================================
CREATE OR REPLACE VIEW vw_taxa_comparecimento_cooperativas AS
SELECT
    coop.id_cooperativa,
    coop.nome_cooperativa,
    COUNT(DISTINCT vc.id_visita_coleta)::BIGINT AS visitas_programadas,
    COUNT(DISTINCT vc.id_visita_coleta) FILTER (WHERE vc.foi_realizada = TRUE)::BIGINT AS visitas_realizadas,
    ROUND(
        100.0 * COUNT(DISTINCT vc.id_visita_coleta) FILTER (WHERE vc.foi_realizada = TRUE)
        / NULLIF(COUNT(DISTINCT vc.id_visita_coleta), 0),
        2
    ) AS taxa_comparecimento_percentual
FROM tb_cooperativas coop
LEFT JOIN tb_agendamentos_coletas ac ON ac.cooperativa_id = coop.id_cooperativa
LEFT JOIN tb_visitas_coletas vc ON vc.agendamento_coleta_id = ac.id_agendamento_coleta
GROUP BY coop.id_cooperativa, coop.nome_cooperativa;

-- ============================================================================
-- 12. Novos tb_usuarios cadastrados por periodo (YYYY-MM)
-- ============================================================================
CREATE OR REPLACE VIEW vw_crescimento_usuarios AS
SELECT
    EXTRACT(YEAR FROM u.registro_em)::INTEGER AS ano,
    EXTRACT(MONTH FROM u.registro_em)::INTEGER AS mes,
    tu.id_tipo_usuario,
    tu.nome_tipo,
    COUNT(u.id_usuario)::BIGINT AS novos_usuarios
FROM tb_usuarios u
LEFT JOIN tb_lkp_tipos_usuarios tu ON tu.id_tipo_usuario = u.tipo_usuario_id
GROUP BY
    EXTRACT(YEAR FROM u.registro_em),
    EXTRACT(MONTH FROM u.registro_em),
    tu.id_tipo_usuario,
    tu.nome_tipo;

-- ============================================================================
-- 13. Quantidade de tb_usuarios ativos por mes
-- ============================================================================
CREATE OR REPLACE VIEW vw_usuarios_ativos_mensal AS
WITH acoes_usuarios AS (
    SELECT
        p.usuario_id,
        p.condominio_id,
        p.data_postagem AS data_acao
    FROM tb_postagens p
    UNION ALL
    SELECT
        uc.usuario_id,
        m.condominio_id,
        uc.data_conclusao AS data_acao
    FROM tb_rel_usuarios_cursos uc
    LEFT JOIN tb_moradores m ON m.usuario_id = uc.usuario_id
    WHERE uc.concluido = TRUE
      AND uc.data_conclusao IS NOT NULL
)
SELECT
    EXTRACT(YEAR  FROM au.data_acao)::INTEGER AS ano,
    EXTRACT(MONTH FROM au.data_acao)::INTEGER AS mes,
    au.condominio_id,
    c.nome_condominio,
    COUNT(DISTINCT u.id_usuario)::BIGINT AS usuarios_ativos
FROM acoes_usuarios au
JOIN tb_usuarios u
  ON u.id_usuario = au.usuario_id
 AND u.ativo = TRUE
LEFT JOIN tb_condominios c ON c.id_condominio = au.condominio_id
WHERE au.data_acao IS NOT NULL
GROUP BY
    EXTRACT(YEAR  FROM au.data_acao),
    EXTRACT(MONTH FROM au.data_acao),
    au.condominio_id,
    c.nome_condominio;

-- ============================================================================
-- 14. Quantidade de tb_moradores por condominio e torre
-- ============================================================================
CREATE OR REPLACE VIEW vw_distribuicao_moradores AS
SELECT
    c.id_condominio,
    c.nome_condominio,
    COUNT(DISTINCT m.id_morador)::BIGINT AS qtd_moradores
FROM tb_condominios c
LEFT JOIN tb_moradores m ON m.condominio_id = c.id_condominio
GROUP BY c.id_condominio, c.nome_condominio;

-- ============================================================================
-- 15. Desempenho por quiz (tentativas, aprovacao, nota media)
-- ============================================================================
CREATE OR REPLACE VIEW vw_desempenho_quizzes AS
SELECT
    q.id_quiz,
    q.titulo_quiz,
    a.id_aula,
    a.titulo_aula,
    cu.id_curso,
    cu.titulo_curso,
    q.nota_minima_aprovacao,
    q.ativo,
    COUNT(DISTINCT tq.usuario_id)::BIGINT AS usuarios_unicos,
    COUNT(tq.id_tentativa)::BIGINT AS total_tentativas,
    COUNT(tq.id_tentativa) FILTER (WHERE tq.concluido_em IS NOT NULL)::BIGINT AS tentativas_concluidas,
    COUNT(tq.id_tentativa) FILTER (WHERE tq.aprovado = TRUE)::BIGINT AS tentativas_aprovadas,
    ROUND(
        100.0 * COUNT(tq.id_tentativa) FILTER (WHERE tq.aprovado = TRUE)
        / NULLIF(COUNT(tq.id_tentativa) FILTER (WHERE tq.concluido_em IS NOT NULL), 0),
        2
    ) AS taxa_aprovacao_percentual,
    ROUND(AVG(tq.nota) FILTER (WHERE tq.concluido_em IS NOT NULL), 2) AS nota_media
FROM tb_quizzes q
JOIN tb_aulas a ON a.id_aula = q.aula_id
JOIN tb_cursos cu ON cu.id_curso = a.curso_id
LEFT JOIN tb_tentativas_quiz tq ON tq.quiz_id = q.id_quiz
GROUP BY
    q.id_quiz,
    q.titulo_quiz,
    a.id_aula,
    a.titulo_aula,
    cu.id_curso,
    cu.titulo_curso,
    q.nota_minima_aprovacao,
    q.ativo;

-- ============================================================================
-- 16. Denuncias por motivo (volume e taxa de procedencia)
-- ============================================================================
CREATE OR REPLACE VIEW vw_denuncias_por_motivo AS
SELECT
    md.id_motivo_denuncia,
    md.descricao AS motivo,
    md.ativo,
    COUNT(vp.id_voto)::BIGINT AS qtd_denuncias,
    COUNT(DISTINCT vp.postagem_id)::BIGINT AS qtd_postagens_denunciadas,
    COUNT(vp.id_voto) FILTER (WHERE svp.nome_status = 'reprovada')::BIGINT AS qtd_denuncias_procedentes,
    ROUND(
        100.0 * COUNT(vp.id_voto) FILTER (WHERE svp.nome_status = 'reprovada')
        / NULLIF(COUNT(vp.id_voto), 0),
        2
    ) AS taxa_procedencia_percentual
FROM tb_lkp_motivos_denuncia md
LEFT JOIN tb_rel_votos_postagens vp
       ON vp.motivo_denuncia_id = md.id_motivo_denuncia
LEFT JOIN tb_postagens p
       ON p.id_postagem = vp.postagem_id
LEFT JOIN tb_lkp_status_validacoes_postagens svp
       ON svp.id_status_validacao = p.status_validacao_id
GROUP BY
    md.id_motivo_denuncia,
    md.descricao,
    md.ativo;

-- ============================================================================
-- SECAO 15 - DAU (USUARIOS ATIVOS DIARIOS)
--
-- tb_atividades_diarias_usuarios : 1 linha por usuario x dia civil (America/Sao_Paulo)
--                                  em que o usuario abriu o app. A API faz UPSERT
--                                  a cada sessao (ON CONFLICT (usuario_id, data_atividade)).
-- tb_metricas_dau                : fotografia diaria consolidada (DAU/WAU/MAU,
--                                  novos, stickiness), recalculada por
--                                  sp_consolidar_metricas_dau (idempotente).
-- ============================================================================

CREATE TABLE IF NOT EXISTS tb_atividades_diarias_usuarios (
    id_atividade_diaria    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id             INTEGER      NOT NULL,
    data_atividade         DATE         NOT NULL,
    plataforma             VARCHAR(10)  NOT NULL,
    qtd_sessoes            SMALLINT     NOT NULL DEFAULT 1,
    minutos_ativos         SMALLINT     NOT NULL DEFAULT 0,
    qtd_acoes              INTEGER      NOT NULL DEFAULT 0,
    primeira_atividade_em  TIMESTAMPTZ  NOT NULL,
    ultima_atividade_em    TIMESTAMPTZ  NOT NULL,
    CONSTRAINT fk_atividades_diarias_usuario_id FOREIGN KEY (usuario_id) REFERENCES tb_usuarios (id_usuario),
    CONSTRAINT uq_atividades_diarias_usuario_data UNIQUE (usuario_id, data_atividade),
    CONSTRAINT ck_atividades_diarias_plataforma CHECK (plataforma IN ('android', 'ios', 'web')),
    CONSTRAINT ck_atividades_diarias_qtd_sessoes CHECK (qtd_sessoes > 0),
    CONSTRAINT ck_atividades_diarias_minutos CHECK (minutos_ativos >= 0),
    CONSTRAINT ck_atividades_diarias_qtd_acoes CHECK (qtd_acoes >= 0),
    CONSTRAINT ck_atividades_diarias_intervalo CHECK (ultima_atividade_em >= primeira_atividade_em)
);
COMMENT ON TABLE tb_atividades_diarias_usuarios IS 'Base do DAU: uma linha por usuario por dia com atividade no app.';
COMMENT ON COLUMN tb_atividades_diarias_usuarios.data_atividade IS 'Dia civil no fuso America/Sao_Paulo';
COMMENT ON COLUMN tb_atividades_diarias_usuarios.plataforma IS 'Plataforma predominante do dia: android | ios | web';
COMMENT ON COLUMN tb_atividades_diarias_usuarios.qtd_acoes IS 'Eventos relevantes no dia (postagens, votos, aulas, quizzes, navegacao)';

-- O UNIQUE (usuario_id, data_atividade) ja atende buscas por usuario; este
-- atende as janelas de data usadas no DAU/WAU/MAU.
CREATE INDEX IF NOT EXISTS idx_atividades_diarias_data
    ON tb_atividades_diarias_usuarios (data_atividade, usuario_id);

CREATE TABLE IF NOT EXISTS tb_metricas_dau (
    data_referencia     DATE          PRIMARY KEY,
    dau                 INTEGER       NOT NULL,
    wau                 INTEGER       NOT NULL,
    mau                 INTEGER       NOT NULL,
    novos_usuarios      INTEGER       NOT NULL,
    usuarios_retornantes INTEGER      NOT NULL,
    sessoes_total       INTEGER       NOT NULL,
    minutos_medios      DECIMAL(6,2),
    stickiness          DECIMAL(5,2),
    calculado_em        TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT ck_metricas_dau_contagens CHECK (dau >= 0 AND wau >= dau AND mau >= wau),
    CONSTRAINT ck_metricas_dau_novos CHECK (novos_usuarios + usuarios_retornantes = dau),
    CONSTRAINT ck_metricas_dau_stickiness CHECK (stickiness IS NULL OR stickiness BETWEEN 0 AND 100)
);
COMMENT ON TABLE tb_metricas_dau IS 'Agregado diario de engajamento, gerado por sp_consolidar_metricas_dau.';
COMMENT ON COLUMN tb_metricas_dau.wau IS 'Usuarios distintos ativos nos 7 dias ate data_referencia (inclusive)';
COMMENT ON COLUMN tb_metricas_dau.mau IS 'Usuarios distintos ativos nos 30 dias ate data_referencia (inclusive)';
COMMENT ON COLUMN tb_metricas_dau.novos_usuarios IS 'Usuarios cuja primeira atividade registrada e data_referencia';
COMMENT ON COLUMN tb_metricas_dau.stickiness IS 'DAU / MAU * 100';

-- ----------------------------------------------------------------------------
-- PROCEDURE 5: sp_consolidar_metricas_dau
-- Recalcula tb_metricas_dau para cada dia do intervalo. Idempotente (UPSERT):
-- o job diario da API chama com (current_date - 1, current_date - 1); cargas
-- retroativas passam o intervalo inteiro.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE sp_consolidar_metricas_dau(
    p_inicio DATE,
    p_fim    DATE DEFAULT CURRENT_DATE
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_fim < p_inicio THEN
        RAISE EXCEPTION 'Intervalo invalido: % > %', p_inicio, p_fim;
    END IF;

    INSERT INTO tb_metricas_dau (
        data_referencia, dau, wau, mau, novos_usuarios, usuarios_retornantes,
        sessoes_total, minutos_medios, stickiness, calculado_em
    )
    SELECT
        g.dia,
        j.dau,
        j.wau,
        j.mau,
        n.novos,
        j.dau - n.novos,
        j.sessoes,
        j.minutos_medios,
        ROUND(100.0 * j.dau / NULLIF(j.mau, 0), 2),
        now()
    FROM generate_series(p_inicio, p_fim, INTERVAL '1 day') AS g0(ts)
    CROSS JOIN LATERAL (SELECT g0.ts::DATE AS dia) g
    CROSS JOIN LATERAL (
        SELECT
            COUNT(DISTINCT a.usuario_id) FILTER (WHERE a.data_atividade = g.dia)::INTEGER     AS dau,
            COUNT(DISTINCT a.usuario_id) FILTER (WHERE a.data_atividade > g.dia - 7)::INTEGER AS wau,
            COUNT(DISTINCT a.usuario_id)::INTEGER                                              AS mau,
            COALESCE(SUM(a.qtd_sessoes) FILTER (WHERE a.data_atividade = g.dia), 0)::INTEGER  AS sessoes,
            ROUND(AVG(a.minutos_ativos) FILTER (WHERE a.data_atividade = g.dia), 2)           AS minutos_medios
          FROM tb_atividades_diarias_usuarios a
         WHERE a.data_atividade BETWEEN g.dia - 29 AND g.dia
    ) j
    CROSS JOIN LATERAL (
        SELECT COUNT(*)::INTEGER AS novos
          FROM tb_atividades_diarias_usuarios h
         WHERE h.data_atividade = g.dia
           AND NOT EXISTS (
                SELECT 1
                  FROM tb_atividades_diarias_usuarios x
                 WHERE x.usuario_id = h.usuario_id
                   AND x.data_atividade < g.dia
           )
    ) n
    ON CONFLICT (data_referencia) DO UPDATE
       SET dau                  = EXCLUDED.dau,
           wau                  = EXCLUDED.wau,
           mau                  = EXCLUDED.mau,
           novos_usuarios       = EXCLUDED.novos_usuarios,
           usuarios_retornantes = EXCLUDED.usuarios_retornantes,
           sessoes_total        = EXCLUDED.sessoes_total,
           minutos_medios       = EXCLUDED.minutos_medios,
           stickiness           = EXCLUDED.stickiness,
           calculado_em         = EXCLUDED.calculado_em;
END;
$$;
COMMENT ON PROCEDURE sp_consolidar_metricas_dau IS
    'Consolida DAU/WAU/MAU, novos, retornantes e stickiness em tb_metricas_dau para o intervalo informado (UPSERT).';

-- ----------------------------------------------------------------------------
-- 17. DAU por tipo de usuario (quem usa o app em cada dia)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_dau_por_tipo_usuario AS
SELECT
    a.data_atividade,
    tu.nome_tipo,
    COUNT(*)::BIGINT                   AS dau,
    SUM(a.qtd_sessoes)::BIGINT         AS sessoes,
    ROUND(AVG(a.minutos_ativos), 2)    AS minutos_medios
FROM tb_atividades_diarias_usuarios a
JOIN tb_usuarios u            ON u.id_usuario = a.usuario_id
JOIN tb_lkp_tipos_usuarios tu ON tu.id_tipo_usuario = u.tipo_usuario_id
GROUP BY a.data_atividade, tu.nome_tipo;

-- ----------------------------------------------------------------------------
-- 18. Retencao por coorte mensal de cadastro (M0, M1, M2 ...)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_retencao_coortes_mensais AS
WITH coortes AS (
    SELECT id_usuario,
           DATE_TRUNC('month', registro_em AT TIME ZONE 'America/Sao_Paulo')::DATE AS mes_coorte
      FROM tb_usuarios
),
tamanho AS (
    SELECT mes_coorte, COUNT(*)::BIGINT AS usuarios_coorte
      FROM coortes
     GROUP BY mes_coorte
),
atividade AS (
    SELECT DISTINCT
           c.mes_coorte,
           a.usuario_id,
           ((EXTRACT(YEAR FROM a.data_atividade) - EXTRACT(YEAR FROM c.mes_coorte)) * 12
             + EXTRACT(MONTH FROM a.data_atividade) - EXTRACT(MONTH FROM c.mes_coorte))::INTEGER AS mes_relativo
      FROM tb_atividades_diarias_usuarios a
      JOIN coortes c ON c.id_usuario = a.usuario_id
)
SELECT
    a.mes_coorte,
    t.usuarios_coorte,
    a.mes_relativo,
    COUNT(*)::BIGINT AS usuarios_ativos,
    ROUND(100.0 * COUNT(*) / t.usuarios_coorte, 2) AS taxa_retencao_percentual
FROM atividade a
JOIN tamanho t ON t.mes_coorte = a.mes_coorte
WHERE a.mes_relativo >= 0
GROUP BY a.mes_coorte, t.usuarios_coorte, a.mes_relativo;

COMMIT;

-- ============================================================================
-- FIM DAS VIEWS ANALÍTICAS
--
-- ============================================================================
-- FIM DO SCRIPT (46 tabelas)
-- ============================================================================