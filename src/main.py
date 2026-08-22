"""
main.py

Carga inicial de massa de dados do EcoCiente. Popula o schema PostgreSQL
(ecociente_schema_ajustado.sql) com dados fictícios em pt_BR via FakerBR
(faker_br.py) e as funções de utils/database.py.

Pré-requisito: rodar ecociente_schema_ajustado.sql antes.

Instalação:
    pip install psycopg2-binary --break-system-packages

Uso:
    python main.py
    (configure utils.helpers.DB_CONFIG ou exporte ECOCIENTE_DSN /
     ECOCIENTE_DB_HOST / ECOCIENTE_DB_PORT / ECOCIENTE_DB_NAME /
     ECOCIENTE_DB_USER / ECOCIENTE_DB_PASSWORD / ECOCIENTE_DB_SSLMODE)
"""

import sys
from collections import defaultdict

from utils.helpers import get_connection

try:
    import psycopg2  # noqa: F401  (checagem antecipada de dependência instalada)
except ImportError:
    print("Este script requer psycopg2. Instale com:")
    print("    pip install psycopg2-binary --break-system-packages")
    sys.exit(1)

from utils.database import (
    N_CONDOMINIOS_RESIDENCIAL,
    N_CONDOMINIOS_COMERCIAL,
    N_COOPERATIVAS,
    N_USUARIOS_COMUM,
    TORRES_POR_RESIDENCIAL,
    MORADORES_POR_TORRE,
    USUARIOS_POR_COMERCIAL,
    PONTOS_COLETA_POR_COOPERATIVA,
    POSTAGENS_POR_OCUPANTE,
    NOTIFICACOES_POR_USUARIO,
    AGENDAMENTOS_POR_CONDOMINIO,
    VISITAS_POR_AGENDAMENTO,
    fk,
    rng,
    popular_tipos_usuarios,
    popular_tipos_condominios,
    popular_dias_semana,
    popular_categorias_residuos,
    popular_status_agendamentos,
    popular_niveis_confianca,
    popular_status_validacoes_postagens,
    popular_tipos_votos_postagens,
    popular_motivos_denuncia,
    criar_usuario,
    criar_subtipo_sindico,
    criar_condominio,
    criar_torre,
    criar_morador,
    criar_vinculo_condominio,
    recalcular_trust_scores,
    criar_cooperativa,
    criar_ponto_coleta,
    vincular_categorias_cooperativa,
    vincular_categorias_ponto_coleta,
    popular_cursos_e_aulas,
    popular_quizzes,
    criar_postagem,
    simular_votos_postagem,
    criar_agendamento,
    criar_recorrencia,
    criar_visita,
    confirmar_visita,
    criar_avaliacao_visita,
    matricular_usuario_em_aulas,
    simular_tentativa_quiz,
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
        dias_semana = popular_dias_semana(cur)
        status_agendamento = popular_status_agendamentos(cur)
        categorias = popular_categorias_residuos(cur)
        categorias_reciclaveis = [cid for nome, cid in categorias.items() if nome != "Rejeito"]

        popular_niveis_confianca(cur)
        popular_status_validacoes_postagens(cur)
        popular_tipos_votos_postagens(cur)
        motivos_denuncia = popular_motivos_denuncia(cur)
        motivos_denuncia_ids = list(motivos_denuncia.values())

        print("[2/9] Cursos, aulas e quizzes...")
        cursos_ids, aulas_por_curso = popular_cursos_e_aulas(cur)
        quizzes_por_aula = popular_quizzes(cur, cursos_ids, aulas_por_curso)

        print("[3/9] Usuários comuns...")
        usuarios_comuns = []
        for _ in range(N_USUARIOS_COMUM):
            uid, _ = criar_usuario(cur, tipos_usuario["Usuário Comum"])
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

        ocupantes = []  # dicts com usuario_id, condominio_id, torre_id, morador_id, sindico_id etc.
        votantes_por_condominio = defaultdict(list)  # usuario_ids com vínculo aprovado, por condomínio

        print("[5/9] Condomínios residenciais + torres + moradores...")
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
                for _ in range(rng.randint(*MORADORES_POR_TORRE)):
                    uid, _ = criar_usuario(cur, tipos_usuario["Morador Residencial"])
                    morador_id = criar_morador(cur, uid, condominio_id)
                    _, aprovado = criar_vinculo_condominio(
                        cur, uid, condominio_id, aprovado_por_usuario_id=sindico_usuario_id
                    )
                    if aprovado:
                        votantes_por_condominio[condominio_id].append(uid)
                    ocupantes.append({
                        "usuario_id": uid,
                        "condominio_id": condominio_id,
                        "torre_id": torre_id,
                        "morador_id": morador_id,
                        "sindico_usuario_id": sindico_usuario_id,
                        "sindico_id": sindico_id,
                    })

        print("[6/9] Condomínios comerciais + moradores/usuários comerciais...")
        condominios_comerciais = []

        for i in range(N_CONDOMINIOS_COMERCIAL):
            sindico_usuario_id, _ = criar_usuario(cur, tipos_usuario["Síndico Comercial"])
            sindico_id = criar_subtipo_sindico(cur, sindico_usuario_id)

            nome_condominio = f"Edifício Comercial {fk.street_name()}"
            condominio_id = criar_condominio(
                cur, tipos_condominio["Comercial"], sindico_id, nome_condominio, comercial=True
            )
            condominios_comerciais.append(condominio_id)

            for _ in range(rng.randint(*USUARIOS_POR_COMERCIAL)):
                uid, _ = criar_usuario(cur, tipos_usuario["Usuário Comercial"])
                morador_id = criar_morador(cur, uid, condominio_id)
                _, aprovado = criar_vinculo_condominio(
                    cur, uid, condominio_id, aprovado_por_usuario_id=sindico_usuario_id
                )
                if aprovado:
                    votantes_por_condominio[condominio_id].append(uid)
                ocupantes.append({
                    "usuario_id": uid,
                    "condominio_id": condominio_id,
                    "torre_id": None,
                    "morador_id": morador_id,
                    "sindico_usuario_id": sindico_usuario_id,
                    "sindico_id": sindico_id,
                })

        todos_condominios = condominios_residenciais + condominios_comerciais
        ocupante_por_usuario = {o["usuario_id"]: o for o in ocupantes}

        print(f"      -> {len(ocupantes)} ocupantes (moradores/usuários comerciais) gerados.")

        print("[7/9] Postagens de descarte + votos de moderação...")
        qtd_postagens = 0
        for ocupante in ocupantes:
            votantes_condominio = votantes_por_condominio.get(ocupante["condominio_id"], [])
            for _ in range(rng.randint(*POSTAGENS_POR_OCUPANTE)):
                categoria_id = fk.random_element(categorias_reciclaveis)
                data_postagem = fk.date_time_between(90, 0)
                postagem_id = criar_postagem(
                    cur, ocupante["usuario_id"], ocupante["condominio_id"],
                    categoria_id, data_postagem, torre_id=ocupante.get("torre_id"),
                )
                simular_votos_postagem(
                    cur, postagem_id, ocupante["usuario_id"],
                    votantes_condominio, motivos_denuncia_ids,
                )
                qtd_postagens += 1

        print(f"      -> {qtd_postagens} postagens criadas.")

        print("[8/9] Agendamentos, recorrências, visitas, avaliações e trust score...")
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
                            sindico_da_visita = next(
                                (o["sindico_usuario_id"] for o in ocupantes if o["condominio_id"] == condominio_id), None
                            )
                            if sindico_da_visita:
                                criar_avaliacao_visita(cur, visita_id, sindico_da_visita)
                                qtd_avaliacoes += 1
                    else:
                        qtd_visitas_futuras += 1

        print(f"      -> visitas: {qtd_visitas_confirmadas} confirmadas | {qtd_visitas_recusadas} recusadas | "
            f"{qtd_visitas_futuras} futuras (pendentes) | {qtd_avaliacoes} avaliações")

        recalcular_trust_scores(cur)
        print("      -> trust_score recalculado via sp_atualizar_trust_score para todos os vínculos.")

        print("[9/9] Matrículas em cursos, tentativas de quiz e notificações...")
        todos_usuarios_ensino = usuarios_comuns + [o["usuario_id"] for o in ocupantes]
        for usuario_id in todos_usuarios_ensino:
            ocupante = ocupante_por_usuario.get(usuario_id)
            condominio_id = ocupante["condominio_id"] if ocupante else None
            torre_id = ocupante["torre_id"] if ocupante else None

            cursos_escolhidos = fk.random_elements(list(aulas_por_curso.keys()), length=rng.randint(1, 2), unique=True)
            for titulo_curso in cursos_escolhidos:
                aulas_concluidas = matricular_usuario_em_aulas(cur, usuario_id, aulas_por_curso[titulo_curso])
                for aula_id in aulas_concluidas:
                    if fk.boolean(70):
                        simular_tentativa_quiz(
                            cur, usuario_id, quizzes_por_aula[aula_id],
                            condominio_id=condominio_id, torre_id=torre_id,
                        )

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
            "tb_lkp_tipos_condominios", "tb_condominios", "tb_sindicos",
            "tb_moradores", "tb_torres",
            "tb_enderecos", "tb_rel_usuarios_condominios", "tb_pontos_coletas", "tb_cooperativas",
            "tb_lkp_categorias_residuos", "tb_rel_cooperativas_categorias_materiais",
            "tb_rel_pontos_coletas_categorias",
            "tb_lkp_niveis_confianca", "tb_lkp_status_validacoes_postagens",
            "tb_lkp_tipos_votos_postagens", "tb_lkp_motivos_denuncia",
            "tb_postagens", "tb_rel_votos_postagens",
            "tb_lkp_status_agendamentos",
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
        print("\nObs.: tb_rel_votos_postagens foi populada via sp_processar_voto_postagem, e o")
        print("trust_score final de tb_rel_usuarios_condominios via sp_atualizar_trust_score --")
        print("ambas as procedures do próprio banco, não recálculo em Python.")
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
            pass


if __name__ == "__main__":
    main()
