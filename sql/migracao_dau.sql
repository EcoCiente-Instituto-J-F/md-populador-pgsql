-- ============================================================================
-- ECOCIENTE | MIGRACAO: DAU
-- Para bancos que ja tem o schema aplicado. Mesmo conteudo da SECAO 15 de
-- ecociente_schema.sql; idempotente (IF NOT EXISTS / OR REPLACE).
-- ============================================================================

BEGIN;

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
