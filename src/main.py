"""
main.py
================================================================================
EcoCiente - Massa de Dados (Carga Inicial)
================================================================================
Popula o schema PostgreSQL do EcoCiente (modelagem lógica atual, implementada
em ecociente_schema.sql) com dados fictícios em pt_BR, usando a classe
FakerBR (faker_br.py), através das funções de utils/database.py.

PRÉ-REQUISITO (rodar antes deste script):
    ecociente_schema.sql — DDL de todas as tabelas do DBML, FKs, CHECKs,
    as functions fn_pontos_disponiveis_postagem / fn_calcular_trust_score,
    as procedures sp_processar_voto_postagem / sp_atualizar_trust_score, e
    as triggers de auditoria (tb_postagens / tb_agendamentos_coletas /
    tb_rel_usuarios_condominios).

    O schema atual NÃO tem mais sp_confirmar_passagem_cooperativa nem
    trigger de recorrência automática — este script reflete isso:
    confirmar_visita() faz UPDATE direto, e possui_recorrencia é setado no
    próprio INSERT de tb_agendamentos_coletas.

A conexão é obtida via utils.helpers.get_connection(), que já devolve a
conexão em autocommit=True. Isso simplifica o tratamento de erro: cada
INSERT/UPDATE já fica persistido imediatamente, sem depender de um COMMIT
manual ao final do script — por isso, em caso de exceção, o bloco de
tratamento chama limpar_dados_banco(cur) para descartar o que já tiver sido
gravado nesta execução.

Colunas de moderação/confiança que o schema atual exige (NOT NULL sem
default) e que este script preenche:
    - tb_rel_usuarios_condominios: trust_score (calculado via
      fn_calcular_trust_score do próprio banco), postagens_validadas_sem_
      contestacao, denuncias_realizadas, denuncias_procedentes.
    - tb_postagens: hash_foto (único), capturada_em, saldo_confianca.

Lookups de moderação semeados por este script (não vêm prontos no DDL):
    tb_lkp_niveis_confianca, tb_lkp_status_validacoes_postagens,
    tb_lkp_tipos_votos_postagens, tb_lkp_motivos_denuncia.
    (tb_lkp_tipos_eventos_auditados e tb_lkp_tipos_operacoes_auditoria já
    vêm semeadas pelo próprio ecociente_schema.sql — não precisam ser
    populadas aqui.)

    - Síndicos: criar_usuario → criar_subtipo_sindico → retorna id_sindico
      (usado como FK em tb_condominios.sindico_id, não o usuario_id direto).
    - Usuários Comuns: criar_usuario → criar_subtipo_usuario_comum.
    - criar_condominio recebe sindico_id (tb_sindicos.id_sindico), não o
      usuario_id direto.
    - criar_cooperativa não recebe nome externo; retorna (cooperativa_id, nome).
    - tb_unidades.condominio_id é NOT NULL sempre — mesmo unidades ligadas
      a uma torre (torre_id) também precisam do condominio_id preenchido.

Instalação:
    pip install psycopg2-binary --break-system-packages

Uso:
    python main.py
    (configure utils.helpers.DB_CONFIG ou exporte ECOCIENTE_DSN /
     ECOCIENTE_DB_HOST / ECOCIENTE_DB_PORT / ECOCIENTE_DB_NAME /
     ECOCIENTE_DB_USER / ECOCIENTE_DB_PASSWORD / ECOCIENTE_DB_SSLMODE)
================================================================================
"""

import sys

from utils.helpers import get_connection

try:
    import psycopg2  # noqa: F401  (checagem antecipada de dependência instalada)
except ImportError:
    print("Este script requer psycopg2. Instale com:")
    print("    pip install psycopg2-binary --break-system-packages")
    sys.exit(1)

from utils.database import (
    # config / volumetria (fonte única: utils/database.py, evita duplicação
    # e divergência de constantes entre os dois módulos)
    SEED,
    N_CONDOMINIOS_RESIDENCIAL,
    N_CONDOMINIOS_COMERCIAL,
    N_COOPERATIVAS,
    N_USUARIOS_COMUM,
    TORRES_POR_RESIDENCIAL,
    UNIDADES_POR_TORRE,
    UNIDADES_POR_COMERCIAL,
    CHANCE_UNIDADE_OCUPADA,
    PONTOS_COLETA_POR_COOPERATIVA,
    POSTAGENS_POR_OCUPANTE,
    NOTIFICACOES_POR_USUARIO,
    AGENDAMENTOS_POR_CONDOMINIO,
    VISITAS_POR_AGENDAMENTO,
    # instâncias compartilhadas de FakerBR/Random (mesmo SEED, um único
    # stream de aleatoriedade entre database.py e main.py)
    fk,
    rng,
    # funções de geração de massa
    popular_tipos_usuarios,
    popular_tipos_condominios,
    popular_tipos_avisos,
    popular_dias_semana,
    popular_categorias_residuos,
    popular_status_agendamentos,
    popular_niveis_confianca,
    popular_status_validacoes_postagens,
    popular_tipos_votos_postagens,
    popular_motivos_denuncia,
    criar_usuario,
    criar_subtipo_sindico,
    criar_subtipo_usuario_comum,
    criar_condominio,
    criar_torre,
    criar_unidade,
    criar_morador,
    criar_vinculo_condominio,
    criar_aviso,
    criar_cooperativa,
    criar_ponto_coleta,
    vincular_categorias_cooperativa,
    vincular_categorias_ponto_coleta,
    popular_cursos_e_aulas,
    criar_postagem,
    criar_agendamento,
    criar_recorrencia,
    criar_visita,
    confirmar_visita,
    criar_avaliacao_visita,
    matricular_usuario_em_aulas,
    criar_notificacoes_usuario,
    limpar_dados_banco,
)


# ==============================================================================
# ORQUESTRAÇÃO PRINCIPAL
# ==============================================================================

def main():
    print("=" * 78)
    print("EcoCiente - Carga inicial de massa de dados (FakerBR)")
    print("=" * 78)

    conn = get_connection()
    cur = conn.cursor()
    print("\n[1/9] Tabelas de domínio / lookup...")
    try:
        tipos_usuario = popular_tipos_usuarios(cur)
        tipos_condominio = popular_tipos_condominios(cur)
        tipos_aviso = popular_tipos_avisos(cur)
        dias_semana = popular_dias_semana(cur)
        status_agendamento = popular_status_agendamentos(cur)
        categorias = popular_categorias_residuos(cur)
        categorias_reciclaveis = [cid for nome, cid in categorias.items() if nome != "Rejeito"]

        # Lookups de moderação/confiança — precisam existir ANTES de
        # qualquer INSERT em tb_rel_usuarios_condominios/tb_postagens, pois
        # ambas dependem do id 1 (morador_comum / aprovada) via DEFAULT ou
        # FK explícita.
        popular_niveis_confianca(cur)
        popular_status_validacoes_postagens(cur)
        popular_tipos_votos_postagens(cur)
        popular_motivos_denuncia(cur)

        print("[2/9] Cursos e aulas (apenas os 2 cursos do domínio)...")
        cursos_ids, aulas_por_curso = popular_cursos_e_aulas(cur)

        print("[3/9] Usuários comuns...")
        usuarios_comuns = []
        for _ in range(N_USUARIOS_COMUM):
            uid, _ = criar_usuario(cur, tipos_usuario["Usuário Comum"])
            criar_subtipo_usuario_comum(cur, uid)
            usuarios_comuns.append(uid)

        print("[4/9] Cooperativas + pontos de coleta...")
        cooperativas = []  # (cooperativa_id, nome, usuario_id)
        for _ in range(N_COOPERATIVAS):
            u_coop, _ = criar_usuario(cur, tipos_usuario["Cooperativa"])
            coop_id, coop_nome = criar_cooperativa(cur, u_coop)
            vincular_categorias_cooperativa(cur, coop_id, categorias_reciclaveis)
            for _ in range(rng.randint(*PONTOS_COLETA_POR_COOPERATIVA)):
                ponto_id = criar_ponto_coleta(cur, coop_id, coop_nome)
                vincular_categorias_ponto_coleta(cur, ponto_id, categorias_reciclaveis)
            cooperativas.append((coop_id, coop_nome, u_coop))

        print("[5/9] Condomínios residenciais + torres + unidades + moradores...")
        # ocupantes: lista de dicts com usuario_id, condominio_id, morador_id,
        # sindico_usuario_id (usuarios.id_usuario) e sindico_id (sindicos.id_sindico)
        ocupantes = []
        condominios_residenciais = []
        for i in range(N_CONDOMINIOS_RESIDENCIAL):
            sindico_usuario_id, sindico_nome = criar_usuario(cur, tipos_usuario["Síndico Residencial"])
            sindico_id = criar_subtipo_sindico(cur, sindico_usuario_id)

            nome_condominio = f"Condomínio {fk.street_name()}"
            condominio_id = criar_condominio(
                cur, tipos_condominio["Residencial"], sindico_id, nome_condominio, comercial=False
            )
            condominios_residenciais.append(condominio_id)

            for t in range(rng.randint(*TORRES_POR_RESIDENCIAL)):
                torre_id = criar_torre(cur, condominio_id, f"Torre {chr(65 + t)}")
                for u in range(rng.randint(*UNIDADES_POR_TORRE)):
                    numero = f"{rng.randint(1, 20)}{str(u + 1).zfill(2)}"
                    # tb_unidades.condominio_id é NOT NULL sempre: mesmo
                    # unidade vinculada a uma torre precisa do condominio_id.
                    unidade_id = criar_unidade(
                        cur, numero, "residencial",
                        torre_id=torre_id, condominio_id=condominio_id,
                    )
                    if fk.boolean(CHANCE_UNIDADE_OCUPADA):
                        tipo_ocupante = tipos_usuario["Morador Residencial"]
                        uid, _ = criar_usuario(cur, tipo_ocupante)
                        morador_id = criar_morador(cur, uid, unidade_id)
                        criar_vinculo_condominio(cur, uid, condominio_id, aprovado_por_usuario_id=sindico_usuario_id)
                        ocupantes.append({
                            "usuario_id": uid,
                            "condominio_id": condominio_id,
                            "torre_id": torre_id,
                            "morador_id": morador_id,
                            "sindico_usuario_id": sindico_usuario_id,
                            "sindico_id": sindico_id,
                        })

            # avisos do síndico: criado_por_usuario_id aponta para tb_usuarios diretamente
            for _ in range(rng.randint(2, 5)):
                criar_aviso(cur, condominio_id, sindico_usuario_id, fk.random_element(list(tipos_aviso.values())))

        print("[6/9] Condomínios comerciais + unidades + usuários comerciais...")
        condominios_comerciais = []

        for i in range(N_CONDOMINIOS_COMERCIAL):
            sindico_usuario_id, _ = criar_usuario(cur, tipos_usuario["Síndico Comercial"])
            sindico_id = criar_subtipo_sindico(cur, sindico_usuario_id)

            nome_condominio = f"Edifício Comercial {fk.street_name()}"
            condominio_id = criar_condominio(
                cur, tipos_condominio["Comercial"], sindico_id, nome_condominio, comercial=True
            )
            condominios_comerciais.append(condominio_id)

            for u in range(rng.randint(*UNIDADES_POR_COMERCIAL)):
                numero = f"Sala {100 + u}"
                unidade_id = criar_unidade(cur, numero, "comercial", condominio_id=condominio_id)
                if fk.boolean(CHANCE_UNIDADE_OCUPADA):
                    uid, _ = criar_usuario(cur, tipos_usuario["Usuário Comercial"])
                    morador_id = criar_morador(cur, uid, unidade_id)
                    criar_vinculo_condominio(cur, uid, condominio_id, aprovado_por_usuario_id=sindico_usuario_id)
                    ocupantes.append({
                        "usuario_id": uid,
                        "condominio_id": condominio_id,
                        "torre_id": None,
                        "morador_id": morador_id,
                        "sindico_usuario_id": sindico_usuario_id,
                        "sindico_id": sindico_id,
                    })

            for _ in range(rng.randint(1, 3)):
                criar_aviso(cur, condominio_id, sindico_usuario_id, fk.random_element(list(tipos_aviso.values())))

        todos_condominios = condominios_residenciais + condominios_comerciais

        print(f"      -> {len(ocupantes)} ocupantes (moradores/usuários comerciais) gerados.")

        print("[7/9] Postagens de descarte...")
        # Todo INSERT dispara trg_auditoria_postagens, que grava automaticamente
        # em tb_log_auditoria + tb_log_auditoria_postagens.
        qtd_postagens = 0
        for ocupante in ocupantes:
            for _ in range(rng.randint(*POSTAGENS_POR_OCUPANTE)):
                categoria_id = fk.random_element(categorias_reciclaveis)
                data_postagem = fk.date_time_between(90, 0)
                criar_postagem(
                    cur, ocupante["usuario_id"], ocupante["condominio_id"],
                    categoria_id, data_postagem, torre_id=ocupante.get("torre_id"),
                )
                qtd_postagens += 1

        print(f"      -> {qtd_postagens} postagens criadas.")

        print("[8/9] Agendamentos, recorrências, visitas e avaliações...")
        qtd_visitas_confirmadas = qtd_visitas_recusadas = qtd_visitas_futuras = 0
        qtd_avaliacoes = 0
        for condominio_id in todos_condominios:
            coop_id, _, _ = fk.random_element(cooperativas)
            for _ in range(rng.randint(*AGENDAMENTOS_POR_CONDOMINIO)):
                recorrente = fk.boolean(70)
                status_id = fk.random_element(list(status_agendamento.values()))
                agendamento_id = criar_agendamento(cur, condominio_id, coop_id, status_id, recorrente)

                if recorrente:
                    for dia_id in fk.random_elements(list(dias_semana.values()), length=rng.randint(1, 2), unique=True):
                        criar_recorrencia(cur, agendamento_id, dia_id)

                for _ in range(rng.randint(*VISITAS_POR_AGENDAMENTO)):
                    no_passado = fk.boolean(70)
                    data_visita = fk.date_time_between(120, 1) if no_passado else fk.date_time_future(60)
                    visita_id = criar_visita(cur, agendamento_id, data_visita)

                    if no_passado:
                        confirmou = fk.boolean(80)
                        obs = None if confirmou else fk.sentence(8)
                        confirmar_visita(cur, visita_id, confirmou, obs)
                        if confirmou:
                            qtd_visitas_confirmadas += 1
                        else:
                            qtd_visitas_recusadas += 1

                        if fk.boolean(70):
                            # avaliador é o síndico como usuário (tb_usuarios.id_usuario)
                            sindico_da_visita = next(
                                (o["sindico_usuario_id"] for o in ocupantes if o["condominio_id"] == condominio_id), None
                            )
                            if sindico_da_visita:
                                criar_avaliacao_visita(cur, visita_id, sindico_da_visita)
                                qtd_avaliacoes += 1
                    else:
                        qtd_visitas_futuras += 1  # fica com houve_confirmacao = FALSE (pendente)

        print(f"      -> visitas: {qtd_visitas_confirmadas} confirmadas | {qtd_visitas_recusadas} recusadas | "
            f"{qtd_visitas_futuras} futuras (pendentes) | {qtd_avaliacoes} avaliações")

        print("[9/9] Matrículas em cursos e notificações...")
        todos_usuarios_ensino = usuarios_comuns + [o["usuario_id"] for o in ocupantes]
        for usuario_id in todos_usuarios_ensino:
            cursos_escolhidos = fk.random_elements(list(aulas_por_curso.keys()), length=rng.randint(1, 2), unique=True)
            for titulo_curso in cursos_escolhidos:
                matricular_usuario_em_aulas(cur, usuario_id, aulas_por_curso[titulo_curso])

        todos_usuarios_para_notificar = set(
            usuarios_comuns
            + [o["usuario_id"] for o in ocupantes]
            + [o["sindico_usuario_id"] for o in ocupantes]
            + [c[2] for c in cooperativas]
        )
        for usuario_id in todos_usuarios_para_notificar:
            criar_notificacoes_usuario(cur, usuario_id, rng.randint(*NOTIFICACOES_POR_USUARIO))

        print("\n" + "=" * 78)
        print("Carga concluída. Resumo de linhas por tabela:")
        print("=" * 78)
        tabelas = [
            "tb_lkp_tipos_usuarios", "tb_usuarios", "tb_telefones", "tb_notificacoes",
            "tb_lkp_tipos_condominios", "tb_condominios", "tb_sindicos", "tb_usuarios_comuns",
            "tb_moradores", "tb_torres", "tb_unidades",
            "tb_enderecos", "tb_rel_usuarios_condominios", "tb_pontos_coletas", "tb_cooperativas",
            "tb_lkp_categorias_residuos", "tb_rel_cooperativas_categorias_materiais",
            "tb_rel_pontos_coletas_categorias",
            "tb_lkp_niveis_confianca", "tb_lkp_status_validacoes_postagens",
            "tb_lkp_tipos_votos_postagens", "tb_lkp_motivos_denuncia",
            "tb_postagens", "tb_rel_votos_postagens",
            "tb_lkp_tipos_avisos", "tb_avisos", "tb_lkp_status_agendamentos",
            "tb_agendamentos_coletas", "tb_visitas_coletas", "tb_avaliacoes_visitas_coletas",
            "tb_lkp_dias_semanas", "tb_rel_recorrencias_agendamentos", "tb_cursos", "tb_aulas",
            "tb_quizzes", "tb_perguntas_quiz", "tb_alternativas_quiz",
            "tb_tentativas_quiz", "tb_rel_respostas_tentativas_quiz",
            "tb_rel_usuarios_cursos",
            "tb_lkp_tipos_eventos_auditados", "tb_lkp_tipos_operacoes_auditoria", "tb_log_auditoria",
            "tb_log_auditoria_postagens", "tb_log_auditoria_agendamentos_coletas",
            "tb_log_auditoria_usuarios_condominios",
        ]
        for tabela in tabelas:
            cur.execute(f"SELECT COUNT(*) FROM {tabela}")
            print(f"  {tabela:38s} {cur.fetchone()[0]:>6d}")

        print("\nObs.: tb_log_auditoria foi populada 100% automaticamente pelas triggers")
        print("(trg_auditoria_postagens / trg_auditoria_agendamentos_coletas / trg_auditoria_usuarios_condominios)")
        print("a cada INSERT/UPDATE feito neste script -- nenhuma linha foi inserida nela manualmente.")
        print("\nObs.: tb_rel_votos_postagens e as tabelas de quiz (tb_quizzes/tb_perguntas_quiz/")
        print("tb_alternativas_quiz/tb_tentativas_quiz/tb_rel_respostas_tentativas_quiz) ainda não")
        print("são geradas por este populador -- por isso aparecem com 0 linhas acima.")
    except Exception as e:
        print("\n[ERRO]", e)
        # Se a conexão/cursor morreu no meio do erro original (ex.: o
        # servidor derrubou a conexão), tentar limpar com esse mesmo `cur`
        # só gera um segundo erro em cascata (InterfaceError: cursor already
        # closed) que mascara a causa real. Nesse caso, abre-se uma conexão
        # NOVA só para a limpeza.
        try:
            limpar_dados_banco(cur)
        except Exception as cleanup_error:
            print("[AVISO] Não foi possível limpar usando a conexão original "
                  f"({cleanup_error}). Tentando com uma nova conexão...")
            try:
                conn2 = get_connection()
                cur2 = conn2.cursor()
                limpar_dados_banco(cur2)
                cur2.close()
                conn2.close()
            except Exception as cleanup_error2:
                print("[AVISO] Limpeza automática falhou mesmo com nova conexão "
                      f"({cleanup_error2}).")
                print("        Rode manualmente um TRUNCATE nas tabelas de negócio "
                      "antes da próxima execução, ou reexecute este script assim "
                      "que a conexão com o banco estiver estável novamente.")
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass n


if __name__ == "__main__":
    main()