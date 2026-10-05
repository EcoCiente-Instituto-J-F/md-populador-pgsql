# ♻️ EcoCiente — Populador PostgreSQL

![GitHub repo size](https://img.shields.io/github/repo-size/EcoCiente-Instituto-J-F/md-populador-pgsql?style=for-the-badge)
![GitHub language count](https://img.shields.io/github/languages/count/EcoCiente-Instituto-J-F/md-populador-pgsql?style=for-the-badge)
![GitHub top language](https://img.shields.io/github/languages/top/EcoCiente-Instituto-J-F/md-populador-pgsql?style=for-the-badge)
![GitHub last commit](https://img.shields.io/github/last-commit/EcoCiente-Instituto-J-F/md-populador-pgsql?style=for-the-badge)
![GitHub license](https://img.shields.io/github/license/EcoCiente-Instituto-J-F/md-populador-pgsql?style=for-the-badge)

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14+-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![Aiven](https://img.shields.io/badge/Aiven-Free%20Tier-FF3554?style=for-the-badge)

> Gera uma massa de dados fictícia (pt-BR) para todas as 46 tabelas do banco do **EcoCiente**, com 12 meses de histórico e padrões realistas o bastante para análise (crescimento, sazonalidade, coortes, churn, correlações). Os dados passam pelas *procedures* e *triggers* do próprio banco, nada é recalculado em Python. Também traz a nova gestão de **DAU (usuários ativos diários)**.

### Ajustes e melhorias

O projeto ainda está em desenvolvimento e as próximas atualizações serão voltadas para as seguintes tarefas:

- [x] Schema versionado em `sql/ecociente_schema.sql`, com correção dos CHECKs de `tb_autenticacoes_api`
- [x] Tabelas de DAU (`tb_atividades_diarias_usuarios`, `tb_metricas_dau`) + `sp_consolidar_metricas_dau` + 2 views
- [x] Moderação no fluxo novo: votos → janela de 24h → `sp_encerrar_janela_postagem` → decisão manual
- [x] Ledger de pontos (`tb_movimentacoes_pontos`) com CRÉDITO, ESTORNO, RESTAURAÇÃO e teto diário
- [x] Perfis de engajamento, abandono, sazonalidade e campanha para análises com sinal real
- [x] Carga em lote (`execute_values` + loops no servidor), pensada para a latência do Aiven
- [x] Escalas `leve` / `medio` / `pesado`
- [ ] Datar `tb_log_auditoria.executado_em` com a data do evento (hoje todas as linhas ficam com a data da carga)
- [ ] Casar cooperativa e condomínio pela cidade (hoje a parceria é sorteada)
- [ ] Oscilações múltiplas de pontuação (mais de um ESTORNO/RESTAURAÇÃO por postagem)

## 💻 Pré-requisitos

Antes de começar, verifique se você atendeu aos seguintes requisitos:

- Você tem o **Python 3.10+** instalado (o código usa `zoneinfo`).
- Você tem um **PostgreSQL 14+**. Pode ser o serviço gratuito da [Aiven](https://aiven.io/free-postgresql-database) ou um Postgres local.
- Você tem o cliente `psql` (ou DBeaver, pgAdmin etc.) para aplicar o schema.
- Funciona em Windows, Linux e macOS.

## 🗄️ Criando o schema

O populador **não cria tabelas**, então rode o schema uma vez antes:

```bash
psql "postgres://avnadmin:SENHA@SEU-SERVICO.aivencloud.com:PORTA/defaultdb?sslmode=require" \
     -v ON_ERROR_STOP=1 -f sql/ecociente_schema.sql
```

O script roda inteiro dentro de um `BEGIN … COMMIT`: se algo falhar, nada fica pela metade.

**O banco já tem o schema?** Nesse caso, aplique só a parte nova do DAU. O arquivo é idempotente, então pode ser rodado de novo sem problema:

```bash
psql "$ECOCIENTE_DSN" -v ON_ERROR_STOP=1 -f sql/migracao_dau.sql
```

O populador também precisa de `tb_movimentacoes_pontos` e `tb_autenticacoes_api`. Se o seu banco é anterior a essas tabelas, recrie-o com `sql/ecociente_schema.sql`.

> [!NOTE]
> A versão anterior do schema não subia: os CHECKs de `tb_autenticacoes_api` citavam `token_type` e `expires_in`, mas as colunas se chamam `tipo_token` e `expira_em`. O erro desfazia o script inteiro. Isso já está corrigido em `sql/ecociente_schema.sql`.

## 🚀 Instalando o Populador

Para instalar o Populador, siga estas etapas:

Linux e macOS:

```bash
git clone https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql.git
cd md-populador-pgsql
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # e preencha com os dados da Aiven
```

Windows (PowerShell):

```powershell
git clone https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql.git
cd md-populador-pgsql
py -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # e preencha com os dados da Aiven
```

No `.env`, use **ou** `ECOCIENTE_DSN` (a *Service URI* da Aiven) **ou** as variáveis separadas `ECOCIENTE_DB_*`. Se as duas formas estiverem preenchidas, vale a DSN.

## ☕ Usando o Populador

Para usar o Populador, rode a partir da pasta `src/`:

```bash
cd src
python main.py                      # escala "medio", seed 42, pede confirmação
python main.py --escala leve        # carga rápida para desenvolvimento
python main.py --seed 7 --force     # outra massa, sem confirmação
python -m tests.test_dau            # self-check do gerador de DAU
python -m tests.test_schema         # self-check da checagem de schema
python -m tests.test_ui             # self-check dos cálculos do painel da tela
```

| Opção | O que faz |
|---|---|
| `--escala leve\|medio\|pesado` | Multiplica condomínios, cooperativas e usuários por 0.3 / 1 / 3. Padrão: `medio`. |
| `--seed N` | Troca a semente. A mesma seed gera sempre a mesma massa (exceto tokens e hashes, que usam `secrets`). |
| `--force` | Pula a confirmação antes de apagar os dados. O mesmo vale para `ECOCIENTE_ALLOW_RESET=1`. |

> [!WARNING]
> Cada execução faz `TRUNCATE … RESTART IDENTITY CASCADE` em **todas as tabelas de negócio** antes de popular. Só as `tb_lkp_*` são mantidas. Confira o banco de destino antes de confirmar.

Se a carga falhar no meio, o script limpa o banco (se preciso, abrindo uma nova conexão) e sai com código `1`.

## 🖥️ Usando pela tela

Quem preferir não usar a linha de comando pode abrir a tela (tkinter, já vem com o Python):

```bash
cd src
python ui.py
```

Nela você escolhe o tamanho da massa (leve, médio ou pesado) e a seed, e acompanha a carga pela barra de progresso e pelo log na aba **Andamento**. Antes de apagar qualquer coisa, a tela mostra o banco de destino, testa a conexão e confere se as colunas do banco batem com `sql/ecociente_schema.sql`.

Quando a carga termina, a aba **Resultado** mostra um painel só com números da inserção, sem métricas de negócio:

- linhas inseridas, tabelas populadas (e quais ficaram vazias), duração, linhas por segundo e tamanho do banco;
- as dez tabelas com mais linhas;
- o tempo gasto em cada uma das dez etapas;
- todas as tabelas `tb_*` do banco, com linhas, participação no total e espaço em disco. Clique no título de uma coluna para ordenar.

"Ler o banco agora" monta o mesmo painel a partir do que já está no banco, sem rodar carga (nesse caso não há tempos).

As cores, fontes e espaçamentos da tela ficam no bloco `DESIGN SYSTEM` no topo de `src/ui.py`.

Se a checagem acusar `tb_autenticacoes_api.expira_em`, o banco foi criado com os nomes antigos (`id`, `expirado_em`). Corrija com:

```bash
psql "$ECOCIENTE_DSN" -v ON_ERROR_STOP=1 -f sql/corrige_autenticacoes_api.sql
```

## 📦 O que é gerado

Números medidos em PostgreSQL 16 com `--seed 42`:

| Escala | Usuários | Condomínios | Postagens | Votos | Linhas de DAU | Tamanho do banco | Tempo (local) |
|---|---:|---:|---:|---:|---:|---:|---:|
| `leve` | ~400 | 7 | ~1,4 mil | ~7,7 mil | ~20 mil | ~25 MB | ~6 s |
| `medio` | ~1.300 | 25 | ~4,6 mil | ~24,6 mil | ~65 mil | ~55 MB | ~20 s |
| `pesado` | ~4.300 | 75 | ~14 mil | ~75 mil | ~196 mil | ~145 MB | ~55 s |

A escala `medio` também gera ~12,8 mil notificações, ~8,2 mil matrículas em aulas, ~410 tentativas de quiz, ~5,5 mil movimentações de pontos, ~2,7 mil tokens de API, ~660 visitas de coleta e ~46 mil registros de auditoria (via triggers). O conteúdo educacional é o real da trilha: 40 cursos, 238 aulas, 20 quizzes, 246 perguntas e 840 alternativas.

> [!TIP]
> Contra a Aiven, o tempo depende da latência (cerca de 5 mil *round trips* na escala `medio`). Conte com alguns minutos. Os volumes grandes (postagens, votos, DAU, matrículas, notificações) vão em lote, e as procedures rodam em loops `DO $$ … $$` no próprio servidor.

## 🧠 Como os dados foram modelados

A ideia é que qualquer gráfico mostre um padrão, e não ruído uniforme:

| Sinal | Como aparece nos dados |
|---|---|
| **Perfis de engajamento** | Cada usuário recebe um perfil: `power` 10%, `regular` 35%, `casual` 35% ou `churn` 20%. O perfil define ao mesmo tempo quantas postagens faz, quantos cursos segue, quanto acerta nos quizzes, quanto vota e quantos dias abre o app. |
| **Crescimento** | Os cadastros se concentram nos meses recentes. Síndicos, cooperativas e admins são "pioneiros" e entram nos primeiros meses. |
| **Abandono / retenção** | Cada perfil tem uma chance de abandonar o app, e a atividade decai até parar. O resultado são curvas de coorte com M1 ≈ 95%, M3 ≈ 75% e M6 ≈ 60–70%. |
| **Sazonalidade semanal** | Condomínios residenciais têm mais uso no fim de semana. Os comerciais, bem menos. |
| **Campanha** | Semana do Meio Ambiente (1–7 de junho): DAU e postagens sobem cerca de 45%. É uma anomalia proposital para detectar. |
| **Categorias** | Condomínios residenciais descartam mais plástico e orgânico, os comerciais mais papel e eletrônico. Cada categoria tem sua taxa de aprovação: Orgânico ~69%, Rejeito ~44%, Vidro ~90%. |
| **Moderação** | Os votos são ponderados pelo nível de confiança (síndico = 3). Resultado final: cerca de 80% aprovadas, 15% reprovadas e 4% em análise. As postagens das últimas 24h continuam abertas, como uma fila de moderação real. |
| **Triagem automática** | `triagem_automatica_aprovada` concorda com a decisão final em ~84% dos casos, com confiança mais baixa quando erra. Dá para montar uma matriz de confusão contra a decisão da comunidade. |
| **Trust score** | Vem de `sp_atualizar_trust_score`. Alguns usuários `power` passam de 200 e são promovidos a `pessoa_confiavel` (6 na escala `medio`). |
| **Pontos** | Há CRÉDITO por postagem (respeitando o teto diário, já que rajadas de descarte no mesmo dia estouram o limite), ESTORNO nas reprovadas, RESTAURAÇÃO quando a postagem se recupera e CRÉDITO na 1ª aprovação de cada quiz. Cerca de 10% dos eventos das últimas 48h ficam pendentes de sincronizar com o Redis, alguns com erro registrado. |
| **Cooperativas** | Cada cooperativa tem uma "qualidade" oculta que move ao mesmo tempo a taxa de comparecimento e a nota das avaliações. As duas métricas se correlacionam. |
| **Ensino** | O usuário avança aula a aula e abandona o curso quando não conclui uma delas, o que forma um funil de conclusão. Quem reprova no quiz tenta de novo em ~55% dos casos, e ~5% das tentativas ficam abandonadas no meio. |

## 📈 DAU — Usuários ativos diários

```mermaid
flowchart LR
    A[App / API] -- "UPSERT a cada sessão" --> B[(tb_atividades_diarias_usuarios<br/>1 linha por usuário × dia)]
    B -- "CALL sp_consolidar_metricas_dau(ontem, ontem)<br/>job diário" --> C[(tb_metricas_dau<br/>DAU · WAU · MAU · novos · stickiness)]
    B --> D[vw_dau_por_tipo_usuario]
    B --> E[vw_retencao_coortes_mensais]
```

**`tb_atividades_diarias_usuarios`**: guarda uma linha por usuário por dia civil (fuso `America/Sao_Paulo`), com `plataforma` (android/ios/web), `qtd_sessoes`, `minutos_ativos`, `qtd_acoes` e o primeiro e último acesso do dia. `UNIQUE (usuario_id, data_atividade)` garante uma linha por dia. A API pode registrar a sessão assim:

```sql
INSERT INTO tb_atividades_diarias_usuarios
       (usuario_id, data_atividade, plataforma, qtd_sessoes, minutos_ativos, qtd_acoes,
        primeira_atividade_em, ultima_atividade_em)
VALUES ($1, (now() AT TIME ZONE 'America/Sao_Paulo')::date, $2, 1, $3, $4, now(), now())
ON CONFLICT (usuario_id, data_atividade) DO UPDATE
   SET qtd_sessoes         = tb_atividades_diarias_usuarios.qtd_sessoes + 1,
       minutos_ativos      = tb_atividades_diarias_usuarios.minutos_ativos + EXCLUDED.minutos_ativos,
       qtd_acoes           = tb_atividades_diarias_usuarios.qtd_acoes + EXCLUDED.qtd_acoes,
       ultima_atividade_em = EXCLUDED.ultima_atividade_em;
```

**`tb_metricas_dau`**: guarda uma fotografia por dia com `dau`, `wau` (7 dias), `mau` (30 dias), `novos_usuarios` (primeiro dia de atividade), `usuarios_retornantes`, `sessoes_total`, `minutos_medios` e `stickiness` (DAU/MAU %). CHECKs garantem que `dau ≤ wau ≤ mau` e que `novos + retornantes = dau`.

**`sp_consolidar_metricas_dau(p_inicio, p_fim)`**: é idempotente (faz UPSERT). O job diário chama `CALL sp_consolidar_metricas_dau(current_date - 1, current_date - 1);`, e reprocessar um período inteiro também é seguro.

O populador gera a atividade de acordo com os eventos reais: todo dia com postagem, voto, aula, quiz ou avaliação feita pelo usuário conta como dia ativo, assim como o dia do cadastro.

## 🔎 Consultas prontas

Todas foram testadas na massa `medio`. Também estão disponíveis as 16 views analíticas do schema (`vw_desempenho_condominio`, `vw_desempenho_quizzes`, `vw_denuncias_por_motivo`...).

<details>
<summary><b>DAU, WAU, MAU e stickiness com média móvel de 7 dias</b></summary>

```sql
SELECT data_referencia, dau, wau, mau, stickiness,
       ROUND(AVG(dau) OVER (ORDER BY data_referencia ROWS 6 PRECEDING), 1) AS dau_media_7d
  FROM tb_metricas_dau
 ORDER BY data_referencia;
```
</details>

<details>
<summary><b>DAU médio por dia da semana</b></summary>

```sql
SELECT TO_CHAR(data_referencia, 'ID-Dy') AS dia_semana, ROUND(AVG(dau), 1) AS dau_medio
  FROM tb_metricas_dau
 WHERE data_referencia >= CURRENT_DATE - 90
 GROUP BY 1 ORDER BY 1;
```
</details>

<details>
<summary><b>Retenção por coorte (M1, M3, M6)</b></summary>

```sql
SELECT mes_coorte, usuarios_coorte,
       MAX(taxa_retencao_percentual) FILTER (WHERE mes_relativo = 1) AS m1,
       MAX(taxa_retencao_percentual) FILTER (WHERE mes_relativo = 3) AS m3,
       MAX(taxa_retencao_percentual) FILTER (WHERE mes_relativo = 6) AS m6
  FROM vw_retencao_coortes_mensais
 GROUP BY 1, 2 ORDER BY 1;
```
</details>

<details>
<summary><b>DAU por tipo de usuário (últimos 30 dias)</b></summary>

```sql
SELECT nome_tipo, ROUND(AVG(dau), 1) AS dau_medio, ROUND(AVG(minutos_medios), 1) AS minutos
  FROM vw_dau_por_tipo_usuario
 WHERE data_atividade >= CURRENT_DATE - 30
 GROUP BY 1 ORDER BY 2 DESC;
```
</details>

<details>
<summary><b>Ranking de condomínios pelo saldo do ledger de pontos</b></summary>

```sql
SELECT c.nome_condominio,
       SUM(CASE m.tipo_movimentacao WHEN 'ESTORNO' THEN -m.pontos ELSE m.pontos END) AS pontos
  FROM tb_movimentacoes_pontos m
  JOIN tb_condominios c ON c.id_condominio = m.condominio_id
 GROUP BY 1 ORDER BY 2 DESC LIMIT 10;
```
</details>

<details>
<summary><b>Teto diário: postagens sem crédito por categoria</b></summary>

```sql
SELECT cr.nome_categoria, cr.limite_pontos_diario AS teto,
       COUNT(p.id_postagem) AS postagens, COUNT(m.id_movimentacao) AS creditadas
  FROM tb_postagens p
  JOIN tb_lkp_categorias_residuos cr ON cr.id_categoria = p.categoria_id
  LEFT JOIN tb_movimentacoes_pontos m
         ON m.postagem_id = p.id_postagem AND m.tipo_movimentacao = 'CREDITO'
 GROUP BY 1, 2 ORDER BY 1;
```
</details>

<details>
<summary><b>Triagem automática × decisão da comunidade (matriz de confusão)</b></summary>

```sql
SELECT p.triagem_automatica_aprovada AS triagem_aprovou, s.nome_status AS decisao_final, COUNT(*)
  FROM tb_postagens p
  JOIN tb_lkp_status_validacoes_postagens s ON s.id_status_validacao = p.status_validacao_id
 WHERE p.resolvido_em IS NOT NULL
 GROUP BY 1, 2 ORDER BY 1, 2;
```
</details>

<details>
<summary><b>Cooperativas: comparecimento × nota média</b></summary>

```sql
SELECT t.nome_cooperativa, t.taxa_comparecimento_percentual, ROUND(AVG(a.nota), 2) AS nota_media
  FROM vw_taxa_comparecimento_cooperativas t
  JOIN tb_agendamentos_coletas ag       ON ag.cooperativa_id = t.id_cooperativa
  JOIN tb_visitas_coletas v             ON v.agendamento_coleta_id = ag.id_agendamento_coleta
  JOIN tb_avaliacoes_visitas_coletas a  ON a.visita_coleta_id = v.id_visita_coleta
 GROUP BY 1, 2 ORDER BY 2 DESC;
```
</details>

<details>
<summary><b>Funil de conclusão de um curso (aula a aula)</b></summary>

```sql
SELECT c.titulo_curso, a.ordem, COUNT(*) AS matriculas, COUNT(*) FILTER (WHERE uc.concluido) AS concluidas
  FROM tb_rel_usuarios_cursos uc
  JOIN tb_aulas a  ON a.id_aula = uc.aula_id
  JOIN tb_cursos c ON c.id_curso = a.curso_id
 WHERE c.titulo_curso = 'Cidades Sustentáveis'
 GROUP BY 1, 2 ORDER BY 2;
```
</details>

<details>
<summary><b>Fila de moderação aberta por condomínio</b></summary>

```sql
SELECT c.nome_condominio, COUNT(*) AS abertas, MIN(p.data_limite_analise) AS vence_primeiro
  FROM tb_postagens p
  JOIN tb_condominios c ON c.id_condominio = p.condominio_id
 WHERE p.resolvido_em IS NULL
 GROUP BY 1 ORDER BY 2 DESC;
```
</details>

## ☁️ Notas sobre o Aiven Free Tier

- O plano tem **1 GB de disco**. A escala `medio` usa cerca de 55 MB, e mesmo a `pesado` (~145 MB) cabe com folga. O resumo final da carga imprime `pg_database_size`.
- Use `sslmode=require` (já vem na *Service URI*). O banco padrão se chama `defaultdb`.
- O populador usa **uma** conexão só, então não esbarra no limite de conexões do plano.
- Serviços gratuitos são desligados após um período sem uso. Se a conexão falhar, religue o serviço no console da Aiven.

## 🗂️ Estrutura do projeto

```
.
├── sql/
│   ├── ecociente_schema.sql        # DDL completo: 46 tabelas, functions, procedures, triggers, views
│   ├── migracao_dau.sql            # só o DAU, para bancos que já têm o schema
│   └── corrige_autenticacoes_api.sql   # renomeia id/expirado_em para os nomes do schema
├── src/
│   ├── main.py                     # orquestra a carga (10 etapas) e imprime o resumo
│   ├── ui.py                       # tela: escala, seed, checagem do banco, progresso e painel da inserção
│   ├── assets/logo_branca.png      # logo usada na tela
│   ├── tests/test_dau.py           # self-check do gerador de DAU
│   ├── tests/test_schema.py        # self-check da checagem de schema
│   ├── tests/test_ui.py            # self-check dos cálculos do painel
│   └── utils/
│       ├── database.py             # volumetria, perfis, geração e inserts
│       ├── faker_br.py             # gerador de nomes, endereços, CPFs etc. em pt-BR (sem dependência)
│       ├── helpers.py              # conexão (.env) e helpers de SQL
│       ├── unique_generator.py     # CPF, e-mail, hash de foto e token sem colisão
│       └── data/curriculo_ecociente.json   # trilha real de cursos, aulas e quizzes
├── .env.example
└── requirements.txt
```

## 📫 Contribuindo para o Populador

Para contribuir com o Populador, siga estas etapas:

1. Bifurque este repositório.
2. Crie um branch: `git checkout -b <nome_branch>`.
3. Faça suas alterações e confirme-as: `git commit -m '<mensagem_commit>'`
4. Envie para o branch original: `git push origin <nome_branch>`
5. Crie a solicitação de pull. O **EcoCiente PR Bot** (`.github/workflows/pr-bot.yml`) gera a descrição automaticamente.

Antes de abrir o PR, rode o schema e o populador em um banco de teste (`--escala leve`) e também `python -m tests.test_dau`.

Como alternativa, consulte a documentação do GitHub em [como criar uma solicitação pull](https://help.github.com/en/github/collaborating-with-issues-and-pull-requests/creating-a-pull-request).

## 🤝 Colaboradores

Agradecemos às seguintes pessoas que contribuíram para este projeto:

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/shinitihm" title="shinitihm">
        <img src="https://github.com/shinitihm.png" width="100px;" alt="Foto de shinitihm no GitHub"/><br>
        <sub><b>shinitihm</b></sub>
      </a>
    </td>
    <td align="center">
      <sub><b>Anna Luisa</b></sub>
    </td>
    <td align="center">
      <sub><b>Julio Menezes</b></sub>
    </td>
    <td align="center">
      <a href="https://github.com/VDG419" title="VDG419">
        <img src="https://github.com/VDG419.png" width="100px;" alt="Foto de VDG419 no GitHub"/><br>
        <sub><b>VDG419</b></sub>
      </a>
    </td>
  </tr>
</table>

## 📝 Licença

Esse projeto está sob licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.
