"""
main.py

Carga inicial de massa de dados do EcoCiente. Popula o schema PostgreSQL
(sql/ecociente_schema.sql) com dados fictícios em pt_BR via FakerBR
(faker_br.py) e as funções de utils/database.py.

Pré-requisito: rodar sql/ecociente_schema.sql antes.

Instalação:
    pip install -r requirements.txt

Uso:
    python src/main.py [--seed N] [--escala leve|medio|pesado] [--force]
    (configure o .env com ECOCIENTE_DSN ou ECOCIENTE_DB_HOST / ECOCIENTE_DB_PORT /
     ECOCIENTE_DB_NAME / ECOCIENTE_DB_USER / ECOCIENTE_DB_PASSWORD / ECOCIENTE_DB_SSLMODE)

    --seed N    usa N em vez do SEED fixo de utils/database.py (massa diferente a cada valor).
    --escala    multiplica a quantidade de condomínios/cooperativas/usuários
                (leve 0.3 | medio 1 | pesado 3). Padrão: medio (~55 MB).
    --force     pula a confirmação antes de apagar os dados existentes
                (mesmo efeito de exportar ECOCIENTE_ALLOW_RESET=1).
"""

import argparse
import os
import sys
import time
from collections import defaultdict
from datetime import timedelta

from utils.helpers import get_connection, target_description

try:
    import psycopg2  # noqa: F401  (checagem antecipada de dependência instalada)
except ImportError:
    print("Este script requer psycopg2. Instale com:")
    print("    pip install psycopg2-binary --break-system-packages")
    sys.exit(1)

from utils import database as db
from utils.database import (
    AGORA,
    AGENDAMENTOS_POR_CONDOMINIO,
    DIAS_HISTORICO,
    MORADORES_POR_TORRE,
    PONTOS_COLETA_POR_COOPERATIVA,
    TORRES_POR_RESIDENCIAL,
    USUARIOS,
    USUARIOS_POR_COMERCIAL,
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
    gerar_postagens,
    encerrar_janelas_postagens,
    registrar_ledger_pontos,
    criar_agendamento,
    criar_recorrencia,
    criar_visita,
    criar_avaliacao_visita,
    simular_trilhas,
    popular_notificacoes,
    popular_autenticacoes_api,
    popular_atividades_diarias,
    limpar_dados_banco,
)

ESCALAS = {"leve": 0.3, "medio": 1.0, "pesado": 3.0}

TABELAS_RESUMO = [
    "tb_lkp_tipos_usuarios", "tb_usuarios", "tb_telefones", "tb_notificacoes",
    "tb_autenticacoes_api",
    "tb_lkp_tipos_condominios", "tb_condominios", "tb_sindicos",
    "tb_moradores", "tb_torres",
    "tb_enderecos", "tb_rel_usuarios_condominios", "tb_pontos_coletas", "tb_cooperativas",
    "tb_lkp_categorias_residuos", "tb_rel_cooperativas_categorias_materiais",
    "tb_rel_pontos_coletas_categorias",
    "tb_lkp_niveis_confianca", "tb_lkp_status_validacoes_postagens",
    "tb_lkp_tipos_votos_postagens", "tb_lkp_motivos_denuncia",
    "tb_postagens", "tb_rel_votos_postagens", "tb_movimentacoes_pontos",
    "tb_lkp_status_agendamentos",
    "tb_agendamentos_coletas", "tb_visitas_coletas", "tb_avaliacoes_visitas_coletas",
    "tb_lkp_dias_semanas", "tb_rel_recorrencias_agendamentos", "tb_cursos", "tb_aulas",
    "tb_quizzes", "tb_perguntas_quiz", "tb_alternativas_quiz",
    "tb_tentativas_quiz", "tb_rel_respostas_tentativas_quiz",
    "tb_rel_usuarios_cursos",
    "tb_lkp_tipos_eventos_auditados", "tb_lkp_tipos_operacoes_auditoria", "tb_log_auditoria",
    "tb_log_auditoria_postagens", "tb_log_auditoria_agendamentos_coletas",
    "tb_log_auditoria_usuarios_condominios",
    "tb_atividades_diarias_usuarios", "tb_metricas_dau",
]


# ==============================================================================
# ORQUESTRAÇÃO PRINCIPAL
# ==============================================================================

def parse_args():
    parser = argparse.ArgumentParser(description="Carga inicial de massa de dados do EcoCiente.")
    parser.add_argument("--seed", type=int, default=None,
                        help="Seed do gerador aleatório (padrão: SEED fixo de utils/database.py).")
    parser.add_argument("--escala", choices=ESCALAS, default="medio",
                        help="Volume da massa: leve (~25 MB), medio (~55 MB), pesado (~145 MB).")
    parser.add_argument("--force", action="store_true",
                        help="Pula a confirmação antes de apagar os dados existentes.")
    return parser.parse_args()


def confirmar_limpeza(force):
    """
    O script apaga TODOS os dados de negócio antes de popular de novo --
    essa confirmação evita rodar isso sem querer contra o banco errado.
    Pulada com --force ou ECOCIENTE_ALLOW_RESET=1 (útil em CI/automação).
    """
    if force or os.environ.get("ECOCIENTE_ALLOW_RESET") == "1":
        return True
    alvo = target_description()
    print(f"\n[ATENÇÃO] Isso vai APAGAR todos os dados de negócio em: {alvo}")
    try:
        resposta = input("Digite 'sim' para confirmar: ").strip().lower()
    except EOFError:
        resposta = ""
    return resposta == "sim"


def escalar(n, fator):
    return max(1, round(n * fator))


def main():
    args = parse_args()
    seed = db.SEED if args.seed is None else args.seed
    fk.reseed(seed)
    rng.seed(seed)
    fator = ESCALAS[args.escala]

    print("=" * 78)
    print(f"EcoCiente - Carga inicial de massa de dados (seed={seed}, escala={args.escala})")
    print("=" * 78)

    conn = get_connection()
    cur = conn.cursor()

    if not confirmar_limpeza(args.force):
        print("Operação cancelada -- nenhuma alteração foi feita.")
        cur.close()
        conn.close()
        return

    # Toda execução parte de um estado limpo -- evita duplicar codigo_acesso,
    # emails, hash_foto etc. entre uma rodada e outra do script.
    limpar_dados_banco(cur)
    t0 = time.time()

    try:
        print("\n[1/10] Tabelas de domínio / lookup...")
        tipos_usuario = popular_tipos_usuarios(cur)
        tipos_condominio = popular_tipos_condominios(cur)
        dias_semana = popular_dias_semana(cur)
        status_agendamento = popular_status_agendamentos(cur)
        categorias = popular_categorias_residuos(cur)
        categorias_reciclaveis = [cid for nome, cid in categorias.items() if nome != "Rejeito"]

        niveis = popular_niveis_confianca(cur)
        status_validacoes = popular_status_validacoes_postagens(cur)
        popular_tipos_votos_postagens(cur)
        motivos_denuncia_ids = list(popular_motivos_denuncia(cur).values())

        print("[2/10] Cursos, aulas e quizzes (trilha real)...")
        cursos_ids, aulas_por_curso = popular_cursos_e_aulas(cur)
        quizzes_por_aula = popular_quizzes(cur, cursos_ids, aulas_por_curso)

        print("[3/10] Usuários comuns...")
        usuarios_comuns = [
            criar_usuario(cur, tipos_usuario["Usuário Comum"])[0]
            for _ in range(escalar(db.N_USUARIOS_COMUM, fator))
        ]
        for _ in range(2):
            criar_usuario(cur, tipos_usuario["Administrador"], perfil="power", pioneiro=True)

        print("[4/10] Cooperativas + pontos de coleta...")
        cooperativas = []  # (cooperativa_id, nome, usuario_id, qualidade)
        for _ in range(escalar(db.N_COOPERATIVAS, fator)):
            u_coop, _ = criar_usuario(cur, tipos_usuario["Cooperativa"], perfil="power", pioneiro=True)
            coop_id, coop_nome, qualidade = criar_cooperativa(cur, u_coop)
            vincular_categorias_cooperativa(cur, coop_id, categorias_reciclaveis)
            for _ in range(rng.randint(*PONTOS_COLETA_POR_COOPERATIVA)):
                ponto_id = criar_ponto_coleta(cur, coop_id, coop_nome)
                vincular_categorias_ponto_coleta(cur, ponto_id, categorias_reciclaveis)
            cooperativas.append((coop_id, coop_nome, u_coop, qualidade))

        ocupantes = []  # dicts com usuario_id, condominio_id, torre_id, sindico_usuario_id
        votantes_por_condominio = defaultdict(list)  # vínculo aprovado e ativo, por condomínio
        sindico_por_condominio = {}

        def novo_condominio(tipo, comercial):
            tipo_sindico = "Síndico Comercial" if comercial else "Síndico Residencial"
            sindico_uid, _ = criar_usuario(cur, tipos_usuario[tipo_sindico],
                                           perfil="power", comercial=comercial, pioneiro=True)
            sindico_id = criar_subtipo_sindico(cur, sindico_uid)
            nome = fk.edificio_comercial_name() if comercial else fk.condominio_name()
            condominio_id = criar_condominio(cur, tipos_condominio[tipo], sindico_id, nome, comercial=comercial)
            # síndico também vota, com peso 3 (nível "sindico")
            criar_vinculo_condominio(cur, sindico_uid, condominio_id,
                                     nivel_confianca_id=niveis["sindico"], aprovado=True)
            votantes_por_condominio[condominio_id].append(sindico_uid)
            sindico_por_condominio[condominio_id] = sindico_uid
            return condominio_id, sindico_uid

        def novo_ocupante(tipo_usuario, condominio_id, sindico_uid, torre_id, comercial):
            desde = USUARIOS[sindico_uid]["inicio"]
            uid, _ = criar_usuario(cur, tipos_usuario[tipo_usuario], desde=desde, comercial=comercial)
            criar_morador(cur, uid, condominio_id)
            _, pode_votar = criar_vinculo_condominio(cur, uid, condominio_id,
                                                     aprovado_por_usuario_id=sindico_uid)
            if pode_votar:
                votantes_por_condominio[condominio_id].append(uid)
            ocupantes.append({"usuario_id": uid, "condominio_id": condominio_id,
                              "torre_id": torre_id, "sindico_usuario_id": sindico_uid})

        print("[5/10] Condomínios residenciais + torres + moradores...")
        for _ in range(escalar(db.N_CONDOMINIOS_RESIDENCIAL, fator)):
            condominio_id, sindico_uid = novo_condominio("Residencial", comercial=False)
            for t in range(rng.randint(*TORRES_POR_RESIDENCIAL)):
                torre_id = criar_torre(cur, condominio_id, f"Torre {chr(65 + t)}")
                for _ in range(rng.randint(*MORADORES_POR_TORRE)):
                    novo_ocupante("Morador Residencial", condominio_id, sindico_uid, torre_id, False)

        print("[6/10] Condomínios comerciais + usuários comerciais...")
        for _ in range(escalar(db.N_CONDOMINIOS_COMERCIAL, fator)):
            condominio_id, sindico_uid = novo_condominio("Comercial", comercial=True)
            for _ in range(rng.randint(*USUARIOS_POR_COMERCIAL)):
                novo_ocupante("Usuário Comercial", condominio_id, sindico_uid, None, True)

        print(f"      -> {len(USUARIOS)} usuários, {len(ocupantes)} ocupantes, "
              f"{len(sindico_por_condominio)} condomínios.")

        print("[7/10] Postagens, votos (sp_processar_voto_postagem) e encerramento das janelas...")
        qtd_postagens, qtd_votos = gerar_postagens(
            cur, ocupantes, votantes_por_condominio, categorias,
            status_validacoes["em_analise"], motivos_denuncia_ids,
        )
        encerrar_janelas_postagens(cur, seed)
        recalcular_trust_scores(cur)
        print(f"      -> {qtd_postagens} postagens, {qtd_votos} votos; trust_score recalculado.")

        print("[8/10] Agendamentos, recorrências, visitas e avaliações...")
        qtd_visitas = 0
        for condominio_id, sindico_uid in sindico_por_condominio.items():
            parceiras = rng.sample(cooperativas, min(2, len(cooperativas)))
            for _ in range(rng.randint(*AGENDAMENTOS_POR_CONDOMINIO)):
                coop_id, _, _, qualidade = rng.choice(parceiras)
                data_inicio = AGORA + timedelta(days=rng.uniform(-DIAS_HISTORICO, 45))
                futuro = data_inicio > AGORA
                if futuro:
                    status = "Confirmado" if fk.boolean(55) else "Agendado"
                else:
                    status = rng.choices(["Realizado", "Cancelado", "Recusado"],
                                         weights=[qualidade * 100, 12, (1 - qualidade) * 40])[0]
                recorrente = fk.boolean(65)
                agendamento_id = criar_agendamento(cur, condominio_id, coop_id, status_agendamento,
                                                   data_inicio, status, recorrente)
                if recorrente:
                    for dia_id in rng.sample(list(dias_semana.values()), rng.randint(1, 2)):
                        criar_recorrencia(cur, agendamento_id, dia_id)

                passo = 7 if recorrente else 14
                for i in range(rng.randint(*VISITAS_POR_AGENDAMENTO) if recorrente else 1):
                    data_visita = data_inicio + timedelta(days=passo * i, hours=rng.randint(0, 2))
                    qtd_visitas += 1
                    if data_visita > AGORA:
                        criar_visita(cur, agendamento_id, data_visita)
                        continue
                    realizada = status == "Realizado" and fk.boolean(round(qualidade * 100))
                    visita_id = criar_visita(
                        cur, agendamento_id, data_visita,
                        foi_realizada=realizada, houve_confirmacao=True,
                        confirmado_em=data_visita + timedelta(minutes=rng.randint(10, 240)),
                        observacao=None if realizada else rng.choice([
                            "Cooperativa não compareceu.", "Caminhão quebrado, reagendar.",
                            "Portaria não liberou a entrada.", "Pouco material separado.",
                        ]),
                    )
                    if fk.boolean(70):
                        criar_avaliacao_visita(cur, visita_id, sindico_uid, qualidade,
                                               realizada, data_visita)
        print(f"      -> {qtd_visitas} visitas.")

        print("[9/10] Trilhas de ensino, quizzes, ledger de pontos, notificações e tokens...")
        usuarios_ensino = usuarios_comuns + [o["usuario_id"] for o in ocupantes]
        ocupante_por_usuario = {o["usuario_id"]: o for o in ocupantes}
        qtd_matriculas, qtd_tentativas = simular_trilhas(
            cur, usuarios_ensino, ocupante_por_usuario, aulas_por_curso, quizzes_por_aula
        )
        registrar_ledger_pontos(cur, seed)
        qtd_notificacoes = popular_notificacoes(cur, list(USUARIOS))
        qtd_tokens = popular_autenticacoes_api(cur, list(USUARIOS))
        print(f"      -> {qtd_matriculas} matrículas, {qtd_tentativas} tentativas de quiz, "
              f"{qtd_notificacoes} notificações, {qtd_tokens} tokens.")

        print("[10/10] Atividade diária (DAU) + sp_consolidar_metricas_dau...")
        qtd_dau = popular_atividades_diarias(cur)
        print(f"      -> {qtd_dau} linhas de atividade diária.")

        print("\n" + "=" * 78)
        print(f"Carga concluída em {time.time() - t0:.0f}s. Resumo de linhas por tabela:")
        print("=" * 78)
        for tabela in TABELAS_RESUMO:
            cur.execute(f"SELECT COUNT(*) FROM {tabela}")
            print(f"  {tabela:40s} {cur.fetchone()[0]:>8d}")

        cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
        print(f"\nTamanho do banco: {cur.fetchone()[0]} (Aiven free tier: 1 GB de disco)")

        print("\nObs.: tb_log_auditoria foi populada 100% pelas triggers de auditoria;")
        print("votos, encerramento de janelas, decisões manuais e trust_score passaram")
        print("pelas procedures do próprio banco, não por recálculo em Python.")
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
        sys.exit(1)
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
