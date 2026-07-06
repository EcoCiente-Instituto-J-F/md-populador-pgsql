"""
main.py
================================================================================
EcoCiente - Massa de Dados (Carga Inicial)
================================================================================
Popula o schema PostgreSQL do EcoCiente (modelagem lógica v2 + objetos lógicos
de otimização: functions, procedures, triggers de auditoria) com dados
fictícios em pt_BR, usando a classe FakerBR (faker_br.py).

PRÉ-REQUISITOS (rodar antes deste script, na ordem):
    1. DDL do modelo lógico (CREATE TABLE de todas as tabelas do DBML).
    2. ecociente_objetos_logicos_otimizacao.sql
       (cria regras_pontuacao, avaliacoes_visitas_coletas, auditoria_log,
        functions, procedures e triggers).

Este script SEMPRE prefere usar as functions/procedures/triggers já criadas
em vez de simular a regra de negócio em Python, para a massa de dados nascer
100% consistente com o que a aplicação real faria:
    - Moderação de postagem  -> CALL sp_validar_postagem(...)
    - Confirmação de visita  -> CALL sp_confirmar_passagem_cooperativa(...)
    - pontuacao_acumulada    -> atualizado pela trigger trg_atualizar_pontuacao_morador
    - possui_recorrencia     -> atualizado pela trigger trg_atualizar_recorrencia_*
    - pontuação por conclusão de aula -> trigger trg_pontuar_conclusao_curso
    - auditoria_log          -> alimentada automaticamente pelas triggers de
                                  auditoria em postagens / agendamentos_coletas /
                                  usuarios_condominios (não inserimos nela na mão)

A conexão é mantida em autocommit=True. Isso é proposital: as procedures
sp_validar_postagem e sp_confirmar_passagem_cooperativa fazem COMMIT dentro
do próprio corpo PL/pgSQL (procedure top-level), o que só é seguro fora de
um bloco de transação aberto manualmente pelo client.

Mudanças v2 (class table inheritance):
    - Síndicos: criar_usuario → criar_subtipo_sindico → retorna id_sindico
      (usado como FK em condominios.sindico_id, não mais o usuario_id direto).
    - Usuários Comuns: criar_usuario → criar_subtipo_usuario_comum.
    - criar_condominio: parâmetro renomeado de sindico_usuario_id → sindico_id,
      que agora recebe o id_sindico da tabela sindicos.
    - criar_cooperativa: não recebe mais coop_nome como parâmetro externo;
      retorna (cooperativa_id, nome) diretamente.

Instalação:
    pip install psycopg2-binary --break-system-packages

Uso:
    python main.py
    (edite utils.helpers.DB_CONFIG abaixo ou exporte a variável de ambiente ECOCIENTE_DSN)
================================================================================
"""

import os
import sys
import random
from datetime import timedelta

from utils.helpers import get_connection, fetch_id, call_procedure
from utils.database import (
    popular_tipos_usuarios,
    popular_tipos_condominios,
    popular_tipos_avisos,
    popular_dias_semana,
    popular_categorias_residuos,
    popular_status_agendamentos,
    popular_regras_pontuacao,
    criar_endereco,
    criar_usuario,
    criar_subtipo_sindico,          # [NOVO v2] subtipo síndico
    criar_subtipo_usuario_comum,    # [NOVO v2] subtipo usuário comum
    criar_condominio,
    criar_torre,
    criar_unidade,
    criar_morador,
    criar_vinculo_condominio,
    criar_aviso,
    criar_ponto_coleta,
    vincular_categorias_cooperativa,
    vincular_categorias_ponto_coleta,
    popular_cursos_e_aulas,
    criar_postagem,
    validar_postagem,
    criar_bonus_pontuacao,
    criar_agendamento,
    criar_recorrencia,
    criar_visita,
    confirmar_visita,
    criar_avaliacao_visita,
    matricular_usuario_em_aulas,
    criar_notificacoes_usuario,
    criar_cooperativa,
    limpar_dados_banco,
)

try:
    import psycopg2
except ImportError:
    print("Este script requer psycopg2. Instale com:")
    print(" \033[034m   pip install psycopg2-binary --break-system-packages\033[0m")
    sys.exit(1)

from utils.faker_br import FakerBR
from utils.database import SEED

fk = FakerBR(seed=SEED)
rng = random.Random(SEED)

# VOLUMETRIA
N_CONDOMINIOS_RESIDENCIAL = 4
N_CONDOMINIOS_COMERCIAL = 2
N_COOPERATIVAS = 3
N_USUARIOS_COMUM = 12

TORRES_POR_RESIDENCIAL = (2, 3)          # (min, max) torres por condomínio residencial
UNIDADES_POR_TORRE = (4, 8)              # (min, max) unidades por torre
UNIDADES_POR_COMERCIAL = (5, 10)         # unidades diretas (sem torre) em condomínio comercial
CHANCE_UNIDADE_OCUPADA = 80              # % de chance da unidade ter morador/ocupante

PONTOS_COLETA_POR_COOPERATIVA = (2, 3)
POSTAGENS_POR_OCUPANTE = (0, 6)
NOTIFICACOES_POR_USUARIO = (2, 5)
AGENDAMENTOS_POR_CONDOMINIO = (1, 2)
VISITAS_POR_AGENDAMENTO = (2, 5)


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
        popular_regras_pontuacao(cur)
        categorias_reciclaveis = [cid for nome, cid in categorias.items() if nome != "Rejeito"]

        print("[2/9] Cursos e aulas (apenas os 2 cursos do domínio)...")
        cursos_ids, aulas_por_curso = popular_cursos_e_aulas(cur)
        todas_aulas = [aid for lst in aulas_por_curso.values() for aid in lst]

        print("[3/9] Usuários comuns...")
        usuarios_comuns = []
        for _ in range(N_USUARIOS_COMUM):
            # [v2] criar_usuario → criar_subtipo_usuario_comum
            uid, _ = criar_usuario(cur, tipos_usuario["Usuário Comum"])
            criar_subtipo_usuario_comum(cur, uid)
            usuarios_comuns.append(uid)

        print("[4/9] Cooperativas + pontos de coleta...")
        cooperativas = []  # (cooperativa_id, nome, usuario_id)
        for _ in range(N_COOPERATIVAS):
            u_coop, _ = criar_usuario(cur, tipos_usuario["Cooperativa"])
            # [v2] criar_cooperativa não recebe mais nome externo; retorna (id, nome)
            coop_id, coop_nome = criar_cooperativa(cur, u_coop)
            vincular_categorias_cooperativa(cur, coop_id, categorias_reciclaveis)
            for _ in range(rng.randint(*PONTOS_COLETA_POR_COOPERATIVA)):
                ponto_id = criar_ponto_coleta(cur, coop_id, coop_nome)
                vincular_categorias_ponto_coleta(cur, ponto_id, categorias_reciclaveis)
            cooperativas.append((coop_id, coop_nome, u_coop))

        print("[5/9] Condomínios residenciais + torres + unidades + moradores...")
        # [v2] ocupantes agora carrega sindico_id (id_sindico) além de sindico_usuario_id
        ocupantes = []  # lista de dicts: usuario_id, condominio_id, morador_id,
                        #                 sindico_usuario_id, sindico_id
        condominios_residenciais = []
        for i in range(N_CONDOMINIOS_RESIDENCIAL):
            sindico_usuario_id, sindico_nome = criar_usuario(cur, tipos_usuario["Síndico Residencial"])
            # [v2] registra o subtipo e obtém id_sindico para usar como FK em condominios
            sindico_id = criar_subtipo_sindico(cur, sindico_usuario_id)

            nome_condominio = f"Condomínio {fk.street_name()}"
            # [v2] criar_condominio recebe sindico_id (sindicos.id_sindico)
            condominio_id = criar_condominio(
                cur, tipos_condominio["Residencial"], sindico_id, nome_condominio, comercial=False
            )
            condominios_residenciais.append(condominio_id)

            for t in range(rng.randint(*TORRES_POR_RESIDENCIAL)):
                torre_id = criar_torre(cur, condominio_id, f"Torre {chr(65 + t)}")
                for u in range(rng.randint(*UNIDADES_POR_TORRE)):
                    numero = f"{rng.randint(1, 20)}{str(u + 1).zfill(2)}"
                    unidade_id = criar_unidade(cur, numero, "residencial", torre_id=torre_id)
                    if fk.boolean(CHANCE_UNIDADE_OCUPADA):
                        tipo_ocupante = tipos_usuario["Morador Residencial"]
                        uid, _ = criar_usuario(cur, tipo_ocupante)
                        morador_id = criar_morador(cur, uid, unidade_id)
                        # aprovado_por_usuario_id ainda referencia usuarios.id_usuario
                        criar_vinculo_condominio(cur, uid, condominio_id, aprovado_por_usuario_id=sindico_usuario_id)
                        ocupantes.append({
                            "usuario_id": uid,
                            "condominio_id": condominio_id,
                            "morador_id": morador_id,
                            "sindico_usuario_id": sindico_usuario_id,  # para avisos / vínculos
                            "sindico_id": sindico_id,                   # FK de condominios [v2]
                        })

            # avisos do síndico — criado_por_usuario_id aponta para usuarios diretamente
            for _ in range(rng.randint(2, 5)):
                criar_aviso(cur, condominio_id, sindico_usuario_id, fk.random_element(list(tipos_aviso.values())))

        print("[6/9] Condomínios comerciais + unidades + usuários comerciais...")
        condominios_comerciais = []

        for i in range(N_CONDOMINIOS_COMERCIAL):
            sindico_usuario_id, _ = criar_usuario(cur, tipos_usuario["Síndico Comercial"])
            # [v2] subtipo síndico → id_sindico para FK em condominios
            sindico_id = criar_subtipo_sindico(cur, sindico_usuario_id)

            nome_condominio = f"Edifício Comercial {fk.street_name()}"
            # [v2] criar_condominio recebe sindico_id (sindicos.id_sindico)
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
                        "morador_id": morador_id,
                        "sindico_usuario_id": sindico_usuario_id,
                        "sindico_id": sindico_id,
                    })

            for _ in range(rng.randint(1, 3)):
                criar_aviso(cur, condominio_id, sindico_usuario_id, fk.random_element(list(tipos_aviso.values())))

        todos_condominios = condominios_residenciais + condominios_comerciais

        print(f"      -> {len(ocupantes)} ocupantes (moradores/usuários comerciais) gerados.")

        print("[7/9] Postagens de descarte (validadas via sp_validar_postagem)...")
        qtd_aprovadas = qtd_rejeitadas = qtd_pendentes = 0
        for ocupante in ocupantes:
            qtd_postagens = rng.randint(*POSTAGENS_POR_OCUPANTE)
            for _ in range(qtd_postagens):
                categoria_id = fk.random_element(categorias_reciclaveis)
                data_postagem = fk.date_time_between(90, 0)
                postagem_id = criar_postagem(cur, ocupante["usuario_id"], ocupante["condominio_id"], categoria_id, data_postagem)

                sorteio = rng.random()
                if sorteio < 0.60:
                    # validado_por_usuario_id → usuarios.id_usuario do síndico
                    validar_postagem(cur, postagem_id, "A", ocupante["sindico_usuario_id"])
                    qtd_aprovadas += 1
                elif sorteio < 0.85:
                    validar_postagem(cur, postagem_id, "R", ocupante["sindico_usuario_id"])
                    qtd_rejeitadas += 1
                else:
                    qtd_pendentes += 1  # fica como 'P', simula fila de moderação real

            # bônus ocasional do síndico
            if fk.boolean(15):
                criar_bonus_pontuacao(cur, ocupante["usuario_id"], ocupante["condominio_id"], ocupante["sindico_usuario_id"])

        print(f"      -> postagens: {qtd_aprovadas} aprovadas | {qtd_rejeitadas} rejeitadas | {qtd_pendentes} pendentes")

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
                            # avaliador é o síndico como usuário (usuarios.id_usuario)
                            sindico_da_visita = next(
                                (o["sindico_usuario_id"] for o in ocupantes if o["condominio_id"] == condominio_id), None
                            )
                            if sindico_da_visita:
                                criar_avaliacao_visita(cur, visita_id, sindico_da_visita)
                                qtd_avaliacoes += 1
                    else:
                        qtd_visitas_futuras += 1  # fica com houve_confirmacao = NULL (pendente)

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
            + [o["sindico_usuario_id"] for o in ocupantes]  # [v2] chave renomeada
            + [c[2] for c in cooperativas]
        )
        for usuario_id in todos_usuarios_para_notificar:
            criar_notificacoes_usuario(cur, usuario_id, rng.randint(*NOTIFICACOES_POR_USUARIO))

        print("\n" + "=" * 78)
        print("Carga concluída. Resumo de linhas por tabela:")
        print("=" * 78)
        tabelas = [
            "tipos_usuarios", "usuarios", "telefones", "notificacoes",
            "tipos_condominios", "condominios", "sindicos", "usuarios_comuns",  # [NOVO v2]
            "moradores", "torres", "unidades",
            "enderecos", "usuarios_condominios", "pontos_coletas", "cooperativas",
            "categorias_residuos", "cooperativas_categorias_materiais",
            "pontos_coletas_categorias", "postagens", "historico_pontuacao",
            "regras_pontuacao", "tipos_avisos", "avisos", "status_agendamentos",
            "agendamentos_coletas", "visitas_coletas", "avaliacoes_visitas_coletas",
            "dias_semanas", "recorrencias_agendamentos", "cursos", "aulas",
            "usuarios_cursos", "auditoria_log",
        ]
        for tabela in tabelas:
            cur.execute(f"SELECT COUNT(*) FROM {tabela}")
            print(f"  {tabela:38s} {cur.fetchone()[0]:>6d}")

        print("\nObs.: auditoria_log foi populada 100% automaticamente pelas triggers")
        print("(trg_auditoria_postagens / trg_auditoria_agendamentos_coletas / trg_auditoria_usuarios_condominios)")
        print("a cada INSERT/UPDATE feito neste script -- nenhuma linha foi inserida nela manualmente.")
    except Exception as e:
        print("\n[ERRO]", e)
        limpar_dados_banco(cur)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()