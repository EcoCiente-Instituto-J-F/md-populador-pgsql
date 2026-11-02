# Modelagem de Dados

## Links do GitHub: onde se encontra cada demanda

Cada link abre direto o arquivo da demanda, na branch `feat/metadata` do repositório
[md-populador-pgsql](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql).

### Demanda 1: Catálogo de Dados (design do relatório do ia-eko)

| Item | Link |
|---|---|
| Catálogo em PDF | [catalogo_dados.pdf](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/blob/feat/metadata/documentos/catalogo_dados.pdf) |
| Catálogo em HTML | [catalogo_dados.html](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/blob/feat/metadata/documentos/catalogo_dados.html) |
| Conteúdo do catálogo (dados) | [dados/catalogo.json](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/blob/feat/metadata/documentos/dados/catalogo.json) |
| Extração e divergências contra o schema | [extrair_catalogo.py](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/blob/feat/metadata/documentos/extrair_catalogo.py) |
| Gerador dos dois documentos | [gerar_documentos.py](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/blob/feat/metadata/documentos/gerar_documentos.py) |
| Design (CSS, arte, paginação) | [documentos/design](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/tree/feat/metadata/documentos/design) |

### Demanda 2: Backup e Recuperação

| Item | Link |
|---|---|
| Documento em PDF | [backup_e_recuperacao.pdf](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/blob/feat/metadata/documentos/backup_e_recuperacao.pdf) |
| Documento em HTML | [backup_e_recuperacao.html](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/blob/feat/metadata/documentos/backup_e_recuperacao.html) |
| Scripts de backup e restauração | [scripts/backup](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/tree/feat/metadata/scripts/backup) |
| Tempos medidos no teste | [dados/medicoes_backup.json](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/blob/feat/metadata/documentos/dados/medicoes_backup.json) |

**Atenção:** as correções desta revisão (índice em `sql/ecociente_schema.sql`, texto do Neon em
`gerar_documentos.py` e os PDFs regerados) só aparecem nos links depois do commit e do `push` para
`origin/feat/metadata`.

## Liberação de acesso para os professores

**Pendente, e só o dono do repositório pode fazer.** O repositório fica na organização
`EcoCiente-Instituto-J-F`. Para liberar: *Settings > Collaborators and teams > Add people*
(ou tornar o repositório público). Não foi feito nesta sessão, e a lista de professores
das disciplinas não foi fornecida.

## Relatório de justificativa

Este relatório fica no próprio repositório. Cada decisão segue o mesmo formato: **o que foi feito**,
**por que**, **a alternativa descartada** e **por que esta foi a melhor**. As referências apontam para o
arquivo e o trecho do repositório onde a decisão está, para quem for conferir. Os apêndices A a D foram
**gerados a partir do banco real** (schema e Data Mart aplicados num PostgreSQL 16 vazio), então os números
não dependem de contagem manual.

Ambiente: PostgreSQL 14+. O sistema aceita **Neon e Aiven** (a conexão é uma DSN PostgreSQL comum); a referência de
dimensionamento é o **Neon, plano free, limite de 1 GB**. O schema tem **59 tabelas**
(50 em [`sql/ecociente_schema.sql`](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/blob/feat/metadata/sql/ecociente_schema.sql)
e 9 do Data Mart em [`sql/ecociente_datamart.sql`](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/blob/feat/metadata/sql/ecociente_datamart.sql)),
95 chaves estrangeiras, 37 regras `CHECK`, 36 restrições `UNIQUE`, 9 funções, 6 procedures e 6 triggers
em 5 tabelas.

### Decisão de base: o provedor (Neon free, 1 GB)

| | |
|---|---|
| **Decisão** | Todo o projeto é dimensionado para caber em 1 GB e para não depender de recursos que o plano free pode não ter. |
| **Por quê** | O limite de 1 GB é fixo. O populador tem três escalas: `leve` (~25 MB), `medio` (~55 MB) e `pesado` (~145 MB), medidas pelo próprio `--help` de `src/main.py`. A `pesado` usa cerca de 15% do limite, então há folga de sobra para o log de auditoria e o DAU crescerem. |
| **Alternativa descartada** | Depender dos backups e da recuperação a um ponto no tempo do provedor. |
| **Por que esta é a melhor** | O que o plano free cobre é algo que o console do Neon confirma e que pode mudar; um dump lógico (`pg_dump -Fc`) de 1,5 MB na escala leve é independente do plano, do serviço e da conta. O banco inteiro cabe em um arquivo pequeno, então manter o dump fora do servidor custa quase nada. |

O documento de backup trata RPO, RTO, frequência e retenção como **premissas** e só os tempos do teste como **medidos**. Nenhum limite do Neon além do 1 GB informado pela equipe é afirmado; o que o plano free cobre deve ser conferido no console.

### 1. Modelagem de Dados

#### 1.1 Normalização: até a 3FN, com desvios documentados

**1FN (valores atômicos, sem grupos repetidos).**
- *Feito:* o endereço é quebrado em colunas (`cep`, `estado`, `cidade`, `bairro`, `logradouro`, `numero`, `complemento`) na própria `tb_enderecos`; os telefones de um usuário ficam em linhas de `tb_telefones` (e não em colunas `telefone1`, `telefone2`); as categorias de resíduo que uma cooperativa ou um ponto de coleta aceita ficam em `tb_rel_cooperativas_categorias_materiais` e `tb_rel_pontos_coletas_categorias` (e não em uma lista dentro de uma coluna); os dias da semana de uma recorrência ficam em `tb_rel_recorrencias_agendamentos`; cada resposta de quiz é uma linha de `tb_rel_respostas_tentativas_quiz`.
- *Por quê:* uma coluna com lista ("seg,qua,sex") impede `JOIN`, `UNIQUE` e FK sobre cada valor.
- *Descartado:* colunas multivaloradas e `ARRAY`/JSON para esses casos.
- *Por que a melhor:* com uma linha por valor, o banco garante integridade (FK para o dia da semana ou para a categoria) e impede repetição (`UNIQUE (agendamento_coleta_id, dia_semana_id)`), o que um array não faz.

**2FN (nenhum atributo depende de parte da chave).**
- *Feito:* quase todas as tabelas têm PK simples (`IDENTITY`), então não existe dependência parcial. As tabelas associativas (`tb_rel_*`) têm um `UNIQUE` sobre o par natural (por exemplo `(usuario_id, condominio_id)`) e os atributos que carregam (`trust_score`, `aprovado`, `peso_aplicado`...) dependem do par inteiro. A única PK composta é a de `tb_migracao_ids_map` (`entidade`, `legacy_id`), e `novo_id` e `migrado_em` dependem das duas colunas juntas.
- *Por que a melhor:* PK substituta simples mantém as FKs de uma coluna só, e o `UNIQUE` no par natural preserva a regra de negócio ("um voto por usuário por postagem").

**3FN (nenhum atributo depende de outro atributo não-chave).**
- *Feito:* tudo que é uma descrição repetida virou tabela de domínio: tipo de usuário, tipo de condomínio, status de agendamento, status de validação de postagem, categoria de resíduo, nível de confiança, tipo de voto, motivo de denúncia, dia da semana, tipo de evento e de operação de auditoria (as 11 tabelas `tb_lkp_*`). O endereço fica numa tabela só, referenciada por usuário, condomínio, cooperativa e ponto de coleta. O nome de uma categoria existe em um lugar só.
- *Por quê:* alterar o nome de um status ou de uma categoria é um `UPDATE` de uma linha, sem anomalia de atualização.
- *Descartado:* colunas de texto livre ou `ENUM` para status e tipos.
- *Por que a melhor:* o lookup tem integridade por FK, aceita novos valores sem `ALTER TYPE` e pode ter atributos próprios (por exemplo `limite_pontos_diario` e `pontos_base` da categoria, `peso_voto` do nível de confiança).

**Por que não foi preciso 4FN nem 5FN.** As relações N:N foram todas decompostas em tabelas associativas binárias (`tb_rel_*`), cada uma guardando uma única relação independente. Não há uma relação ternária que só se reconstrua pela junção de três projeções, que é o caso em que a 5FN exige decomposição, nem fatos multivalorados independentes dentro de uma mesma tabela, que é o caso da 4FN. Cooperativa×categoria e ponto de coleta×categoria, por exemplo, são duas relações binárias separadas, e não uma ternária cooperativa×ponto×categoria.

**Desvios conscientes da 3FN (desnormalização intencional).** Cada um tem um motivo e um responsável por mantê-lo correto:

| Coluna(s) | Por que existe | Quem mantém |
|---|---|---|
| `tb_rel_votos_postagens.peso_aplicado` | Snapshot do peso do voto no momento em que foi dado. O histórico não pode mudar quando o nível de confiança do usuário muda depois. | `sp_processar_voto_postagem` |
| `tb_tentativas_quiz.condominio_id`, `torre_id` | Snapshot do condomínio e da torre do usuário na conclusão do quiz. Os pontos pertencem ao ciclo em que foram ganhos, mesmo se o usuário mudar de condomínio. | API, na conclusão |
| `tb_rel_usuarios_condominios.trust_score`, `nivel_confianca_id`, `postagens_validadas_sem_contestacao`, `denuncias_realizadas`, `denuncias_procedentes`, `taxa_acerto_denuncias` | Contadores derivados de `tb_postagens` e `tb_rel_votos_postagens`. Guardá-los evita varrer todas as postagens a cada voto. | `sp_atualizar_trust_score` (usa `fn_calcular_trust_score`); a taxa de acerto é recalculada pela aplicação |
| `tb_postagens.saldo_confianca` | Soma ponderada dos votos, guardada para decidir aprovação sem somar os votos a cada consulta. | `sp_processar_voto_postagem` |
| `tb_agendamentos_coletas.possui_recorrencia` | Cache de "existe algum dia em `tb_rel_recorrencias_agendamentos`". | Aplicação (não há trigger; é um ponto de atenção declarado) |
| `tb_conversas.ultima_mensagem_em` | Ordena a caixa de entrada sem varrer as mensagens. | Trigger `trg_validar_mensagem_conversa`, com `GREATEST` |
| `tb_movimentacoes_pontos.redis_sincronizado`, `redis_sincronizado_em`, `tentativas_sync_redis`, `ultimo_erro_redis`; `condominio_id`, `torre_id` | Controle operacional da projeção no Redis e snapshot do ciclo de pontos. O PostgreSQL é a fonte oficial e o Redis é reconstruível. | API |
| Todo o Data Mart (`dim_*`, `fato_*`) | Desnormalizado por definição: o star schema troca normalização por leitura rápida e simples para BI. É um schema derivado do OLTP e não recebe escrita direta. | `sp_carga_datamart()` |

#### 1.2 Chaves, relacionamentos e cardinalidades

- *Feito:* PKs `GENERATED ALWAYS AS IDENTITY`; FKs nomeadas `fk_<tabela>_<coluna>`; `UNIQUE` e `CHECK` nomeados (`uq_*`, `ck_*`). **1:1** entre usuário e cada subtipo (`UNIQUE (usuario_id)` em `tb_sindicos`, `tb_moradores` e `tb_cooperativas`), entre quiz e aula, e entre visita e avaliação. **1:N** nas hierarquias: condomínio → torre → morador, curso → aula, quiz → pergunta → alternativa. **N:N** nas tabelas `tb_rel_*`.
- *Por quê:* nomes previsíveis facilitam mensagens de erro e o catálogo; `IDENTITY` é o padrão do PostgreSQL moderno e impede inserir um id à mão por engano.
- *Descartado:* `SERIAL` e PKs naturais.
- *Por que a melhor:* `SERIAL` é um atalho legado e tem donos de sequência confusos; chaves naturais (e-mail, CPF) mudam e são PII, então não devem ser a chave de ligação.

**FK composta que garante a torre do mesmo condomínio.** `tb_moradores` tem `FOREIGN KEY (torre_id, condominio_id) REFERENCES tb_torres (id_torre, condominio_id)`, e `tb_torres` declara `UNIQUE (id_torre, condominio_id)` só para ser o alvo dessa FK. Assim um morador nunca aponta para a torre de outro condomínio, e `torre_id` continua opcional (condomínio sem torres).

**Exclusão é bloqueada, não em cascata.** Nenhuma FK usa `ON DELETE CASCADE`: o padrão (`NO ACTION`) impede apagar uma linha que ainda é referenciada. A saída normal é a desativação lógica (`ativo = FALSE`, presente em usuário, condomínio, telefone e ponto de coleta, entre outras). `ON UPDATE CASCADE` aparece em 5 FKs da cadeia de votos e de quiz (voto → postagem; quiz → aula; pergunta → quiz; alternativa → pergunta; resposta → tentativa), onde o id pai pode ser reatribuído e os filhos acompanham.
- *Descartado:* `ON DELETE CASCADE`.
- *Por que a melhor:* os dados de pontuação, votos e auditoria têm valor histórico e de compliance; apagar um condomínio em cascata levaria junto postagens, votos e pontos. O bloqueio obriga uma decisão consciente.

#### 1.3 Massa de dados (500+ registros verossímeis)

- *Feito:* o populador (`src/main.py`) gera dados fictícios em pt-BR com 12 meses de histórico. Mesmo na escala `leve` o teste mediu 435 usuários, 1.595 postagens, 8.591 votos e 16.020 linhas de auditoria, muito acima de 500.
- *Por quê:* volume e padrões (sazonalidade, coortes, abandono) tornam as views de BI e o `EXPLAIN ANALYZE` significativos.
- *Descartado:* carga manual por `INSERT` e dados aleatórios sem estrutura.
- *Por que a melhor:* os dados passam pelas procedures e triggers do próprio banco, então testam as regras de verdade, e as escalas permitem escolher o volume conforme o 1 GB.

#### 1.4 Subtipos de usuário por FK (e não por `INHERITS`)

- *Feito:* `tb_usuarios` guarda os dados comuns de toda pessoa (nome, e-mail, senha, tipo) e os subtipos `tb_sindicos`, `tb_moradores` e `tb_cooperativas` guardam o que é específico de cada papel. Cada subtipo aponta para `tb_usuarios` por uma FK com `UNIQUE (usuario_id)`.
- *Por quê:* muitas tabelas do sistema referenciam o usuário por FK (postagens, votos, notificações, DAU, tentativas de quiz, entre outras). No `INHERITS` do PostgreSQL, uma FK que aponta para a tabela-mãe só enxerga as linhas gravadas na própria mãe, e **não** as das filhas. Com os subtipos em `INHERITS`, o usuário gravado na filha não poderia ser referenciado por essas FKs.
- *Descartado:* `INHERITS (tb_usuarios)` nos três subtipos.
- *Por que a melhor:* mantém a integridade referencial inteira (PK, FK e `UNIQUE` valem em toda a hierarquia), que é a razão de ser do banco relacional. O `INHERITS` foi usado onde essa perda não pesa, na auditoria (seção 6), que só recebe escrita e não é referenciada por nenhuma outra tabela. Escolher o mecanismo conforme o risco, e não aplicar o mesmo em tudo, foi a decisão mais segura.

### 2. Engenharia de Dados e ETL

**2.1 Integração RPA em outro repositório.**
- *Feito:* este repositório só contém o que o banco precisa para receber a migração: a tabela `tb_migracao_ids_map` (`entidade`, `legacy_id`, `novo_id`, PK composta). O RPA em si fica no repositório **`md-rpa-integration`**.
- *Por quê:* o RPA tem ciclo de vida, dependências e credenciais próprias (conexão com o banco legado). O banco e o robô evoluem em ritmos diferentes.
- *Descartado:* misturar o código do RPA no repositório do banco.
- *Por que a melhor:* o contrato entre os dois é pequeno e explícito: o mapa legado → novo torna a carga **idempotente** (rodar de novo não duplica) e resolve as FKs das entidades dependentes. A PK composta `(entidade, legacy_id)` impede migrar duas vezes o mesmo registro. `novo_id` **não tem FK de propósito**, porque aponta para tabelas diferentes conforme a entidade. O índice de busca reversa `(entidade, novo_id)` **não é único**, porque vários registros legados podem convergir para o mesmo id novo (deduplicação). O documento de backup também descreve o RPA como falha prevista (carga transacional, reconciliação).

**2.2 Camada de BI: Data Mart em Star Schema.**
- *Feito:* 7 dimensões (`dim_tempo`, `dim_usuario`, `dim_condominio`, `dim_cooperativa`, `dim_categoria_residuo`, `dim_status_postagem`, `dim_status_agendamento`) e 2 fatos (`fato_postagens`, `fato_coletas`), com chaves substitutas (`sk_*`), a chave de negócio original em `UNIQUE` (`id_usuario`, `id_condominio`...) e o grão documentado em cada `COMMENT`. A carga é a procedure `sp_carga_datamart()`.
- *Por quê:* BI faz agregações por tempo, condomínio, categoria e cooperativa; o star schema entrega isso com poucos joins.
- *Descartado:* Snowflake, e views direto sobre o OLTP.
- *Por que a melhor:* o snowflake normaliza as dimensões e acrescenta joins sem ganho, e as dimensões aqui são pequenas. Views só sobre o OLTP competem com a carga transacional e não guardam histórico. A chave substituta isola o BI de mudanças de id no OLTP, e a chave de negócio `UNIQUE` torna a carga repetível.

**2.3 CTEs e Window Functions.**
- *Feito:* a `dim_tempo` é gerada com **CTE recursiva** (`WITH RECURSIVE`, em `ecociente_datamart.sql`); as 19 views analíticas de `ecociente_schema.sql` e as 4 do Data Mart usam CTEs para organizar a transformação em etapas. As window functions estão nas 4 views `vw_bi_*` do Data Mart: `RANK()`/`DENSE_RANK()` (ranking de condomínios por mês), `SUM() OVER` (total acumulado de postagens por usuário), `LAG()` (evolução mensal das coletas) e `AVG() OVER` com janela de 7 dias (média móvel do DAU).
- *Por quê:* a lógica de transformação fica legível em etapas, e os cálculos analíticos não exigem subconsultas aninhadas.
- *Por que a melhor:* CTEs e window functions são o jeito idiomático do PostgreSQL e o planejador as otimiza bem; a alternativa de calcular em Python tiraria a regra do banco.

### 3. Objetos Lógicos e Otimização

**3.1 Functions e Procedures (mínimo 2 e 2).**
- *Feito:* 3 functions de regra de negócio (`fn_pontos_disponiveis_postagem`, `fn_calcular_trust_score`, `fn_usuario_representa_lado`) e 5 procedures (`sp_processar_voto_postagem`, `sp_encerrar_janela_postagem`, `sp_decidir_postagem_analise`, `sp_atualizar_trust_score`, `sp_consolidar_metricas_dau`), além de `sp_carga_datamart`. As regras estão descritas na seção 7.
- *Por quê:* pontuação, voto e moderação são regras críticas que precisam ser atômicas e idênticas para qualquer cliente (API, populador, RPA).
- *Descartado:* regra na aplicação.
- *Por que a melhor:* no banco, a regra roda dentro da mesma transação do dado e vale para todos os clientes; function para cálculo sem efeito colateral (`fn_calcular_trust_score` é `IMMUTABLE`, `fn_usuario_representa_lado` é `STABLE`), procedure para o que escreve e controla transação.

**3.2 Triggers de auditoria (NEW, OLD, TG_OP, CURRENT_USER; mínimo 2 tabelas).**
- *Feito:* três tabelas auditadas: `tb_postagens`, `tb_agendamentos_coletas` e `tb_rel_usuarios_condominios`, por `fn_trg_auditoria_*` e `trg_auditoria_*` (`AFTER INSERT OR UPDATE OR DELETE`, uma linha por linha afetada), gravando o antes (`OLD`) e o depois (`NEW`), a operação (`TG_OP`) e o usuário (`executado_por DEFAULT CURRENT_USER`).
- *Por quê:* são as tabelas em que um conflito (conteúdo moderado, coleta, vínculo de confiança) precisa de rastro.
- *Por que a melhor:* trigger audita qualquer caminho de escrita, inclusive acesso direto ao banco; auditoria na aplicação perderia esse caso. `AFTER` garante que só se audita o que de fato foi gravado.

**3.3 Triggers de regra de negócio (além da auditoria).** Três triggers `BEFORE` impedem dados inválidos que um `CHECK` não alcança, porque olham outras linhas ou outras tabelas: `trg_validar_partes_agendamento`, `trg_validar_mensagem_conversa` e `trg_validar_referencia_movimentacao_pontos`. Ver a seção 7.
- *Descartado:* validar só na API.
- *Por que a melhor:* um `CHECK` só enxerga a própria linha. Regras como "quem aceita é o lado oposto de quem pediu" dependem de consultar `tb_sindicos`, `tb_condominios` e `tb_cooperativas`; a trigger garante a regra mesmo para escrita direta no banco.

**3.4 EXPLAIN ANALYZE e índices.**
- *Feito:* quatro casos em `ecociente_schema.sql` (fila de moderação, histórico de denúncias, auditoria por período e indicadores por condomínio), cada um com "antes" e "depois" e o índice proposto (134 índices no banco, entre eles os parciais, como `idx_postagens_pendentes_moderacao`, que indexa só as postagens ainda não resolvidas, e `idx_mensagens_conversas_nao_lidas`, só as mensagens não lidas).
- *Por quê:* índice só vale se o plano mudar de `Seq Scan` para `Index Scan`.
- *Descartado:* indexar toda FK por reflexo.
- *Por que a melhor:* no Neon free, com 1 GB, cada índice ocupa espaço e custa escrita; o índice parcial indexa só as linhas que a consulta usa. Na auditoria, o índice por `executado_em` é criado em cada filha, e o plano da consulta pela tabela-mãe passou a usar um `Append` sobre `Bitmap Index Scan` nas filhas.

### 4. Governança de Dados

**4.1 Catálogo de Dados (a "tabela técnica de metadados").**
- *Feito:* o catálogo é o PDF [`catalogo_dados.pdf`](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/blob/feat/metadata/documentos/catalogo_dados.pdf), gerado de `dados/catalogo.json` e do schema. Ele cobre as **59 tabelas em 13 camadas** e descreve cada tabela, suas colunas, regras de negócio e nível de acesso (PUBLICO, INTERNO, RESTRITO e CONFIDENCIAL), mais o mapa de PII.
- *Por quê:* a equipe definiu que o catálogo em PDF é a entrega de metadados.
- *Descartado:* um segundo catálogo dentro do banco.
- *Por que a melhor:* uma só fonte da verdade, regerada por `python documentos/gerar_documentos.py`, evita que um catálogo em tabela e um em documento divirjam. As descrições de coluna vêm do próprio `COMMENT ON COLUMN` do schema, então o catálogo acompanha o banco.
- *Limite assumido:* nível de acesso e PII são **derivados por regra fixa** (permissões do catálogo e nome da coluna), com a etiqueta DERIVADO; não são uma classificação oficial.

**4.2 As 8 tabelas incluídas no catálogo.** O catálogo cobria 51 das 59 tabelas; foram incluídas as 8 que faltavam, cada uma em uma camada que combina com o seu papel:

| Tabela | Camada | Para que serve |
|---|---|---|
| `tb_autenticacoes_api` | Usuários | Tokens de acesso da API (token único, tipo `Bearer`, validade). |
| `tb_recuperacoes_senha` | Usuários | Pedidos de recuperação de senha (guarda só o hash do token). |
| `tb_conversas` | Contato e Comunicação | Canal de chat entre síndico e cooperativa, uma conversa por par condomínio × cooperativa. |
| `tb_mensagens_conversas` | Contato e Comunicação | Mensagens desse chat. |
| `tb_movimentacoes_pontos` | Moderação e Confiança | Ledger oficial de pontos (crédito, estorno, restauração). |
| `tb_atividades_diarias_usuarios` | Monitoramento (DAU), camada nova | Uma linha por usuário por dia de atividade. |
| `tb_metricas_dau` | Monitoramento (DAU), camada nova | DAU, WAU, MAU e stickiness por dia. |
| `tb_migracao_ids_map` | Migração (RPA), camada nova | Mapa de ids legado → novo para o RPA. |

As **permissões por perfil dessas 8 tabelas são uma proposta** derivada do comportamento do código (quem escreve, via qual objeto do banco): tokens, recuperação de senha, DAU e migração ficam só com o Sistema e o DBA; chat e pontos têm acesso restrito por dono. Isso as deixa como CONFIDENCIAL (tokens, senha, DAU, migração) ou RESTRITO (chat, pontos). A equipe deve confirmar essas permissões.

**4.3 Backup e Recuperação.**
- *Feito:* [`backup_e_recuperacao.pdf`](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/blob/feat/metadata/documentos/backup_e_recuperacao.pdf) e os scripts em [`scripts/backup`](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/tree/feat/metadata/scripts/backup) (`backup.sh`/`.ps1`, `restore.sh`/`.ps1`). Dump `-Fc` diário, `--schema-only` a cada mudança, retenção 7 diários + 4 semanais, restauração do banco inteiro ou de uma tabela, conferência por contagem.
- *Medido:* backup 0,5 s, restauração 2,0 s e 17 de 17 contagens iguais (escala leve, PostgreSQL 16 em Docker). Restaurar um banco com a auditoria em `INHERITS` preserva a herança (16.497 linhas e 3 filhas no banco restaurado).
- *Por quê:* o Neon free tem 1 GB e a equipe precisa de um caminho de recuperação que não dependa do plano.
- *Descartado:* depender só dos recursos do provedor, e `pg_dumpall`.
- *Por que a melhor:* o formato `-Fc` é compacto e permite restaurar uma tabela com `pg_restore -t`; o dump é portátil entre provedores e versões. Cada script recusa restaurar por cima de `ECOCIENTE_DSN` sem confirmação explícita.

### 5. Monitoramento: DAU no banco

- *Feito:* `tb_atividades_diarias_usuarios` (uma linha por usuário por dia, `UNIQUE (usuario_id, data_atividade)`, a API faz `UPSERT` a cada sessão) e `tb_metricas_dau` (DAU, WAU, MAU, novos, retornantes e stickiness). A `sp_consolidar_metricas_dau` recalcula o intervalo de forma idempotente. As views `vw_dau_por_tipo_usuario` e `vw_retencao_coortes_mensais` consomem os dados.
- *Por quê:* DAU precisa ser registrado de forma barata a cada sessão e consolidado uma vez por dia.
- *Descartado:* contar DAU com `COUNT(DISTINCT)` direto sobre as tabelas de negócio.
- *Por que a melhor:* a tabela diária mantém o custo de escrita baixo e uma linha por usuário/dia, o que importa no limite de 1 GB, e os `CHECK` (`wau >= dau`, `mau >= wau`, `novos + retornantes = dau`) barram métricas incoerentes. O índice `(data_atividade, usuario_id)` atende as janelas de 7 e 30 dias de WAU e MAU.
- *Limite assumido:* o agendamento diário da consolidação é feito pela API (`current_date - 1`), não por um job dentro do Postgres.

### 6. Estruturas Avançadas

- **CTE recursiva:** usada na `dim_tempo`, onde faz sentido porque a série de datas é, por natureza, gerada passo a passo. A CTE recursiva demonstra a técnica pedida e gera apenas o intervalo necessário.
- **Herança de tabelas com `INHERITS`:** a auditoria usa o recurso nativo do PostgreSQL. `tb_log_auditoria` é a tabela-mãe (id, tipo de evento, tipo de operação, quem executou, quando) e `tb_log_auditoria_postagens`, `tb_log_auditoria_agendamentos_coletas` e `tb_log_auditoria_usuarios_condominios` são as filhas, cada uma declarada com `INHERITS (tb_log_auditoria)` e com as colunas do seu assunto.
  - *Como funciona:* as filhas recebem as colunas, o `NOT NULL`, o `CHECK` e o `DEFAULT` da mãe. A mãe fica vazia; um `SELECT` em `tb_log_auditoria` lê as linhas de todas as filhas, e `tableoid::regclass` diz de qual tabela veio cada linha. Cada trigger grava uma única linha na filha, sem a etapa antiga de gravar na mãe e depois na filha.
  - *O que o `INHERITS` não herda e como foi tratado:* a identidade (`GENERATED ... AS IDENTITY`), a PK, as FKs, o `UNIQUE` e os índices. A mãe usa uma sequence compartilhada (`seq_log_auditoria`), então o `id_auditoria` é único entre todas as filhas; cada filha declara de novo a sua PK, as FKs e o índice por `executado_em`. Foi testado: 16.497 linhas lidas pela mãe (15.788 + 85 + 624), 0 linhas só na mãe e ids sem repetição.
  - *Alternativa descartada:* modelar a herança por FK 1:1 (Class Table Inheritance, como antes). O professor pediu herança de tabelas, e `INHERITS` é o mecanismo do próprio PostgreSQL para isso.
  - *Por que a melhor aqui:* a perda de PK e FK entre mãe e filha quase não pesa na auditoria, porque o log só recebe escrita e nenhuma outra tabela referencia `tb_log_auditoria`. A consulta por período (caso 3 do `EXPLAIN`) passou a usar os índices de cada filha (`Append` sobre `Bitmap Index Scan`).
  - *Por que os subtipos de usuário não usam `INHERITS`:* ver a decisão 1.4.

### 7. Regras de negócio e constraints

#### 7.1 Como as regras foram distribuídas

As regras foram postas na camada mais simples que consegue garanti-las, e só subiram para a seguinte quando a anterior não bastava:

| Camada | Garante | Exemplo |
|---|---|---|
| Tipo e `NOT NULL` | Formato e obrigatoriedade | `email_usuario` e `senha_hash` obrigatórios; `estado CHAR(2)` |
| `CHECK` | Regra sobre a própria linha | `pontos > 0`; `lida_em >= enviada_em`; `nota BETWEEN 1 AND 5` |
| `UNIQUE` e índice único parcial | Unicidade, inclusive condicional | um voto por usuário por postagem; um crédito inicial por postagem |
| `FOREIGN KEY` | Existência do registro referenciado | toda postagem tem usuário, condomínio e categoria |
| Trigger `BEFORE` | Regra que olha outras linhas ou tabelas | quem aceita um agendamento; quem pode escrever numa conversa |
| Procedure | Regra com vários passos e transação | votar, encerrar a janela, decidir, recalcular a confiança |

*Por que a melhor:* quanto mais simples a ferramenta, mais barata de executar e mais fácil de entender; a trigger e a procedure ficam para o que não cabe em declaração. O Apêndice B lista todas as regras `CHECK` e `UNIQUE`, e o Apêndice D lista as functions, procedures e triggers.

#### 7.2 Agendamento de coleta: quem pede não pode aceitar

Um agendamento tem um **solicitante** (`solicitado_por_usuario_id`) e um **lado de origem** (`origem_solicitacao`, `CONDOMINIO` ou `COOPERATIVA`). A regra é: **quem solicita não pode aceitar nem recusar o próprio pedido; a outra parte é que responde.**

- **Se o condomínio pediu** (origem `CONDOMINIO`, quem pede é o síndico), só a **cooperativa** responde.
- **Se a cooperativa pediu** (origem `COOPERATIVA`), só o **síndico** do condomínio responde.
- O banco garante isso na trigger `trg_validar_partes_agendamento` (`BEFORE INSERT OR UPDATE`), que usa a function `fn_usuario_representa_lado`: (1) o solicitante precisa realmente representar o lado de `origem_solicitacao` (síndico atual do condomínio, ou o usuário da cooperativa) e (2) quem responde (`respondido_por_usuario_id`) precisa representar o lado **oposto**. Caso contrário, a operação falha com `RAISE EXCEPTION`.
- Dois `CHECK` completam: `origem_solicitacao` só aceita `CONDOMINIO` ou `COOPERATIVA`, e `respondido_por_usuario_id` e `respondido_em` são preenchidos **juntos** ou ficam os dois nulos (não existe resposta sem data nem data sem responsável).
- O fluxo de status usa os valores `Agendado` (pendente), `Confirmado` (aceito), `Recusado`, `Realizado` e `Cancelado` (`tb_lkp_status_agendamentos`, inseridos de forma idempotente). As transições de status (quem marca realizada ou cancelada) ficam na API; a regra de quem **responde** fica no banco.

*Por que a melhor:* separação de funções. Se o mesmo lado pudesse pedir e aceitar, bastaria um usuário para "fechar um acordo" sozinho. Como a regra depende de consultar outras tabelas (qual é o síndico atual, qual usuário é da cooperativa), um `CHECK` não alcança, e a trigger garante a regra até para escrita direta no banco. Reutilizar `fn_usuario_representa_lado` no agendamento e no chat evita duas definições de "quem fala por quem". Os valores nulos de `solicitado_por_usuario_id` só existiriam em linhas legadas não migradas, e a coluna é `NOT NULL` no schema atual.

#### 7.3 Chat entre síndico e cooperativa

`tb_conversas` guarda um canal por par condomínio × cooperativa, e `tb_mensagens_conversas` guarda as mensagens.
- `UNIQUE (condominio_id, cooperativa_id)`: nunca há duas conversas para o mesmo par.
- A trigger `trg_validar_mensagem_conversa` (`BEFORE INSERT`) exige que: a conversa exista e esteja **ativa**; o remetente realmente represente o lado informado em `remetente_tipo` (mesma `fn_usuario_representa_lado`); a conversa seja **iniciada pela cooperativa** (a primeira mensagem não pode ser do condomínio); e atualiza `ultima_mensagem_em` com `GREATEST` (uma mensagem com data antiga, de carga histórica, não faz o relógio voltar).
- A trigger trava a linha da conversa (`FOR UPDATE`) para duas mensagens simultâneas não furarem a regra "a cooperativa inicia".
- `CHECK`s: `remetente_tipo` só `COOPERATIVA` ou `CONDOMINIO`; o conteúdo, sem os espaços das pontas, tem de 1 a 2000 caracteres; `lida_em` nunca é anterior a `enviada_em`.
- Índices: histórico paginado `(conversa_id, enviada_em DESC)`, contador de não lidas (parcial, só `lida_em IS NULL`) e caixa de entrada por cooperativa e por condomínio.

*Por que a melhor:* a regra "a cooperativa inicia, depois o síndico responde" espelha o processo real (a cooperativa procura o condomínio). Validar no banco e não só na API garante que nenhum cliente consiga criar uma conversa "de dentro" do condomínio.

#### 7.4 Ledger de pontos

`tb_movimentacoes_pontos` é o registro oficial e imutável da pontuação; o Redis é só uma projeção que pode ser reconstruída por ela.
- `pontos > 0` sempre; o **sentido** vem de `tipo_movimentacao`: `CREDITO` soma, `ESTORNO` subtrai, `RESTAURACAO` soma de novo o mesmo crédito.
- **Origem consistente (`CHECK`):** um movimento vem de uma `POSTAGEM` (exige `postagem_id` e `categoria_id`, e não tem `tentativa_quiz_id`) ou de um `QUIZ` (exige `tentativa_quiz_id`, sem postagem nem categoria). Nunca os dois, nunca nenhum.
- **Referência consistente (`CHECK`):** `CREDITO` não aponta para outro movimento; `ESTORNO` e `RESTAURACAO` precisam apontar para o crédito original. A trigger `trg_validar_referencia_movimentacao_pontos` confere o que o `CHECK` não vê: que o referenciado é um `CREDITO` da mesma origem, do mesmo usuário e do mesmo valor.
- **Um crédito inicial por origem:** índices únicos parciais `uq_mov_pontos_credito_postagem` e `uq_mov_pontos_credito_quiz`. Estornos e restaurações podem repetir enquanto a moderação oscila.
- **Idempotência:** `idempotency_key` é `UNIQUE`; se a API repetir a chamada, os pontos não duplicam.
- **Projeção no Redis:** `redis_sincronizado = TRUE` exige a data em `redis_sincronizado_em` (`CHECK`), e `tentativas_sync_redis >= 0`.
- **Teto diário** por categoria: `fn_pontos_disponiveis_postagem` calcula o saldo líquido do ledger (`CREDITO + RESTAURACAO - ESTORNO`) usando a data da **postagem**, para uma restauração posterior não consumir o teto do dia da restauração.

*Por que a melhor:* um ledger só de inserções (como um livro-caixa) dá auditoria completa e permite reconstruir o saldo; guardar apenas o saldo perderia o histórico e impediria corrigir a projeção do Redis.

#### 7.5 Moderação comunitária e confiança

- `tb_rel_votos_postagens`: `UNIQUE (postagem_id, usuario_id)` (um voto por usuário por postagem) e `peso_aplicado > 0`.
- `sp_processar_voto_postagem` rejeita voto em tipo inválido; exige `motivo_denuncia_id` nas denúncias e proíbe nas aprovações; rejeita voto em postagem já encerrada ou fora da **janela comunitária de 24 h** (`data_limite_analise`); e exige que o votante tenha **vínculo aprovado e ativo** com o condomínio da postagem. Cruzar o saldo −5 não encerra a postagem: marca a pontuação como inativa e a reconciliação como pendente, e se o saldo voltar a `>= 0` dentro das 24 h a pontuação volta a ficar ativa e a API registra a RESTAURAÇÃO.
- `sp_encerrar_janela_postagem` aplica a regra definitiva: saldo `>= 0` → aprovada; de −1 a −4 → em análise; `<= −5` → reprovada. Só roda depois de a janela fechar.
- `sp_decidir_postagem_analise` registra a decisão manual de uma postagem que terminou em análise; a autorização do síndico/admin fica na API.
- `fn_calcular_trust_score`: +2 por postagem validada sem contestação, +5 por denúncia procedente, mais metade da taxa de acerto das denúncias (0 a 50), com teto de 1000. `sp_atualizar_trust_score` recalcula os contadores e promove o usuário a "pessoa confiável" ao passar do limiar.
- `tb_rel_usuarios_condominios`: contadores não negativos e `denuncias_procedentes <= denuncias_realizadas`; taxa de acerto entre 0 e 100.
- `tb_postagens`: `capturada_em <= data_postagem` (a foto não pode ser mais nova que a postagem), `hash_foto` único (a mesma foto não vale duas vezes) e confiança da triagem automática entre 0 e 100.

*Por que a melhor:* o peso do voto pelo nível de confiança e a janela de 24 h reduzem fraude e dão tempo à comunidade; o `UNIQUE (postagem_id, usuario_id)` e o `hash_foto` único fecham as duas fraudes mais óbvias (votar duas vezes e repostar a mesma foto).

#### 7.6 Educação, categorias, DAU e autenticação

- **Quiz:** `nota_minima_aprovacao` e `nota` entre 0 e 100; `pontos_recompensa > 0`; um quiz por aula (`UNIQUE (aula_id)`); `ordem` única dentro do curso e do quiz; uma resposta por pergunta por tentativa; um progresso por usuário e aula.
- **Categorias de resíduo:** `pontos_base > 0` e `limite_pontos_diario` nulo ou `>= 0`; níveis de confiança com `peso_voto > 0`.
- **Avaliação de coleta:** nota de 1 a 5 e uma avaliação por visita.
- **DAU:** as regras da seção 5.
- **Autenticação:** token único; tipo sempre `Bearer`; validade `> 0`; recuperação de senha com `token_hash` único.

#### 7.7 Dados sensíveis

`senha_hash` guarda só o hash; `token_hash` da recuperação de senha também. O CPF é `UNIQUE`. O **e-mail do usuário não tem `UNIQUE`** no schema atual: é um ponto de atenção declarado (ver Limites).

### O que foi verificado

| Verificação | Resultado |
|---|---|
| `sql/ecociente_schema.sql` e `ecociente_datamart.sql` num PostgreSQL 16 vazio | Aplicam sem erro (`ON_ERROR_STOP`): **59 tabelas** e o índice `idx_esqueci_senha_usuario_id` no lugar |
| Populador `--escala leve --force` com a auditoria em `INHERITS` | Roda sem erro; triggers gravam nas filhas; a mãe lê 16.497 linhas e `ONLY` na mãe lê 0 |
| `python documentos/gerar_documentos.py` | Gera os dois PDFs, sem avisos do conversor |
| Páginas: catálogo / backup | 79 / 11; o número do PDF bate com o gerador |
| Tamanho de página | 824,9 × 637,9 pt (1100 × 850 px) |
| Catálogo | 59 tabelas em 13 camadas; todas as tabelas do schema estão no catálogo e nenhuma tabela do catálogo falta no schema |
| Backup e restauração (Docker, PostgreSQL 16) | 0,5 s e 2,0 s; 17 de 17 contagens iguais |

### Limites declarados

| Gravidade | Limite | Situação |
|---|---|---|
| Média | Nível de acesso e PII do catálogo são **derivados**, não uma classificação oficial. | Declarado no catálogo (etiqueta DERIVADO). |
| Média | As permissões das 8 tabelas incluídas no catálogo são **propostas** a partir do comportamento do código. | A equipe deve confirmar. |
| Média | Tempos de backup e restauração foram medidos na escala `leve`, num PostgreSQL local, sem rede. Contra o Neon entram latência e o tamanho real. | Declarado em "O que este documento não afirma". |
| Média | O que o plano free do Neon cobre além de 1 GB (recuperação, suspensão por inatividade) não foi verificado. | A conferir no console; o documento não afirma nada disso. |
| Média | O e-mail de `tb_usuarios` não tem `UNIQUE`: dois usuários podem ter o mesmo e-mail. | Ponto de atenção; decidir se deve ser único. |
| Baixa | `possui_recorrencia` em `tb_agendamentos_coletas` não é mantida por trigger; quem grava é a aplicação. | Declarado em 1.1. |
| Baixa | `restore.sh -t ... --truncar` não usa `CASCADE`; tabelas referenciadas por FK precisam ser listadas juntas. | Escolha de segurança, documentada. |
| Baixa | O `.ps1` foi validado de ponta a ponta no PowerShell 7 (contêiner). No Windows PowerShell 5.1 foi até a checagem do `pg_dump`. | Documentado em "Como medimos". |
| Baixa | README e `main.py` citam Aiven. | Mantidos: o sistema aceita Neon e Aiven, pois a conexão é uma DSN PostgreSQL comum. |
| Baixa | A senha da DSN aparece na linha de comando do `pg_dump` (visível em `ps`). | Mascarada nas mensagens; a linha de comando não. |

### Resolvido nesta revisão

- **Índice do schema.** `sql/ecociente_schema.sql` falhava em banco vazio, porque `idx_esqueci_senha_usuario_id` vinha antes do `CREATE TABLE tb_recuperacoes_senha`. O índice foi movido para logo depois da tabela, e o schema aplica direto.
- **Auditoria com `INHERITS`.** Troca do modelo por FK 1:1 pela herança nativa, validada com o populador, o backup e a restauração.
- **Catálogo completo.** As 8 tabelas que faltavam entraram, com as regras de agendamento e de chat.
- **Textos do catálogo defasados.** As observações das 3 filhas de auditoria passaram a descrever a herança com `INHERITS`, e duas regras que falavam em exclusão "em cascata" (condomínio e curso) foram corrigidas, porque o schema não usa `ON DELETE CASCADE`.

### Veredito

Entrega completa: modelagem, ETL, objetos lógicos, governança, DAU e estruturas avançadas estão no banco e documentados, o catálogo cobre todas as tabelas e o schema aplica num banco vazio. Falta commitar e enviar os arquivos novos e liberar o acesso aos professores.

## Apêndice A. Resumo por tabela (gerado do banco)

PK = chave primária; UQ = restrições `UNIQUE`; CK = regras `CHECK`; FK = chaves estrangeiras; TRG = triggers; IDX = índices (inclui o da PK e os dos `UNIQUE`). Os valores vêm do catálogo do PostgreSQL.

| Tabela | PK | UQ | CK | FK | TRG | IDX |
|---|---|---|---|---|---|---|
| `dim_categoria_residuo` | `(sk_categoria)` | 1 | 0 | 0 | 0 | 2 |
| `dim_condominio` | `(sk_condominio)` | 1 | 0 | 0 | 0 | 2 |
| `dim_cooperativa` | `(sk_cooperativa)` | 1 | 0 | 0 | 0 | 2 |
| `dim_status_agendamento` | `(sk_status_agendamento)` | 1 | 0 | 0 | 0 | 2 |
| `dim_status_postagem` | `(sk_status_postagem)` | 2 | 0 | 0 | 0 | 3 |
| `dim_tempo` | `(sk_tempo)` | 1 | 0 | 0 | 0 | 2 |
| `dim_usuario` | `(sk_usuario)` | 1 | 0 | 0 | 0 | 2 |
| `fato_coletas` | `(sk_fato_coleta)` | 1 | 0 | 4 | 0 | 5 |
| `fato_postagens` | `(sk_fato_postagem)` | 1 | 0 | 5 | 0 | 6 |
| `tb_agendamentos_coletas` | `(id_agendamento_coleta)` | 0 | 3 | 5 | 2 | 3 |
| `tb_alternativas_quiz` | `(id_alternativa)` | 0 | 0 | 1 | 0 | 1 |
| `tb_atividades_diarias_usuarios` | `(id_atividade_diaria)` | 1 | 5 | 1 | 0 | 3 |
| `tb_aulas` | `(id_aula)` | 1 | 0 | 1 | 0 | 2 |
| `tb_autenticacoes_api` | `(id_autenticao_api)` | 1 | 2 | 1 | 0 | 2 |
| `tb_avaliacoes_visitas_coletas` | `(id_avaliacao)` | 1 | 1 | 2 | 0 | 2 |
| `tb_condominios` | `(id_condominio)` | 1 | 0 | 3 | 0 | 2 |
| `tb_conversas` | `(id_conversa)` | 1 | 0 | 2 | 0 | 4 |
| `tb_cooperativas` | `(id_cooperativa)` | 2 | 0 | 2 | 0 | 3 |
| `tb_cursos` | `(id_curso)` | 0 | 0 | 0 | 0 | 1 |
| `tb_enderecos` | `(id_endereco)` | 0 | 0 | 0 | 0 | 1 |
| `tb_lkp_categorias_residuos` | `(id_categoria)` | 0 | 2 | 0 | 0 | 1 |
| `tb_lkp_dias_semanas` | `(id_dia_semana)` | 0 | 0 | 0 | 0 | 1 |
| `tb_lkp_motivos_denuncia` | `(id_motivo_denuncia)` | 0 | 0 | 0 | 0 | 1 |
| `tb_lkp_niveis_confianca` | `(id_nivel_confianca)` | 0 | 1 | 0 | 0 | 1 |
| `tb_lkp_status_agendamentos` | `(id_status)` | 1 | 0 | 0 | 0 | 2 |
| `tb_lkp_status_validacoes_postagens` | `(id_status_validacao)` | 0 | 0 | 0 | 0 | 1 |
| `tb_lkp_tipos_condominios` | `(id_tipo_condominio)` | 0 | 0 | 0 | 0 | 1 |
| `tb_lkp_tipos_eventos_auditados` | `(id_tipo_evento_auditado)` | 0 | 0 | 0 | 0 | 1 |
| `tb_lkp_tipos_operacoes_auditoria` | `(id_tipo_operacao)` | 0 | 0 | 0 | 0 | 1 |
| `tb_lkp_tipos_usuarios` | `(id_tipo_usuario)` | 0 | 0 | 0 | 0 | 1 |
| `tb_lkp_tipos_votos_postagens` | `(id_tipo_voto)` | 0 | 0 | 0 | 0 | 1 |
| `tb_log_auditoria` | `(id_auditoria)` | 0 | 0 | 2 | 0 | 1 |
| `tb_log_auditoria_agendamentos_coletas` | `(id_auditoria)` | 0 | 0 | 5 | 0 | 2 |
| `tb_log_auditoria_postagens` | `(id_auditoria)` | 0 | 0 | 5 | 0 | 2 |
| `tb_log_auditoria_usuarios_condominios` | `(id_auditoria)` | 0 | 0 | 3 | 0 | 2 |
| `tb_mensagens_conversas` | `(id_mensagem)` | 0 | 3 | 2 | 1 | 3 |
| `tb_metricas_dau` | `(data_referencia)` | 0 | 3 | 0 | 0 | 1 |
| `tb_migracao_ids_map` | `(entidade, legacy_id)` | 0 | 0 | 0 | 0 | 2 |
| `tb_moradores` | `(id_morador)` | 1 | 0 | 3 | 0 | 4 |
| `tb_movimentacoes_pontos` | `(id_movimentacao)` | 1 | 7 | 7 | 1 | 10 |
| `tb_notificacoes` | `(id_notificacao)` | 0 | 0 | 1 | 0 | 1 |
| `tb_perguntas_quiz` | `(id_pergunta)` | 1 | 0 | 1 | 0 | 2 |
| `tb_pontos_coletas` | `(id_ponto_coleta)` | 0 | 0 | 2 | 0 | 1 |
| `tb_postagens` | `(id_postagem)` | 1 | 2 | 5 | 1 | 6 |
| `tb_quizzes` | `(id_quiz)` | 1 | 2 | 2 | 0 | 2 |
| `tb_recuperacoes_senha` | `(id_esqueci_senha)` | 1 | 0 | 1 | 0 | 3 |
| `tb_rel_cooperativas_categorias_materiais` | `(id_cooperativa_categoria)` | 1 | 0 | 2 | 0 | 2 |
| `tb_rel_pontos_coletas_categorias` | `(id_ponto_coleta_categoria)` | 1 | 0 | 2 | 0 | 2 |
| `tb_rel_recorrencias_agendamentos` | `(id_recorrencia_agendamento)` | 1 | 0 | 2 | 0 | 2 |
| `tb_rel_respostas_tentativas_quiz` | `(id_resposta)` | 1 | 0 | 3 | 0 | 2 |
| `tb_rel_usuarios_condominios` | `(id_usuario_condominio)` | 1 | 4 | 4 | 1 | 2 |
| `tb_rel_usuarios_cursos` | `(id_usuario_curso)` | 1 | 0 | 2 | 0 | 2 |
| `tb_rel_votos_postagens` | `(id_voto)` | 1 | 1 | 4 | 0 | 3 |
| `tb_sindicos` | `(id_sindico)` | 1 | 0 | 1 | 0 | 2 |
| `tb_telefones` | `(id_telefone)` | 0 | 0 | 1 | 0 | 1 |
| `tb_tentativas_quiz` | `(id_tentativa)` | 0 | 1 | 4 | 0 | 5 |
| `tb_torres` | `(id_torre)` | 2 | 0 | 1 | 0 | 3 |
| `tb_usuarios` | `(id_usuario)` | 1 | 0 | 2 | 0 | 2 |
| `tb_visitas_coletas` | `(id_visita_coleta)` | 0 | 0 | 1 | 0 | 2 |
| **Total (59 tabelas)** | | **36** | **37** | **95** | **6** | **134** |

## Apêndice B. Todas as regras CHECK e UNIQUE, em português

Cada linha é uma constraint real do banco (nome técnico à esquerda). As chaves de negócio `UNIQUE` das 9 tabelas do Data Mart ficam agrupadas no fim.

| Tabela | Constraint | Tipo | Regra |
|---|---|---|---|
| `tb_agendamentos_coletas` | `ck_agendamentos_coletas_datas` | CHECK | O fim da coleta, quando existe, não pode ser antes do início. |
| `tb_agendamentos_coletas` | `ck_agendamentos_coletas_origem_solicitacao` | CHECK | Quem abriu o pedido é o CONDOMINIO ou a COOPERATIVA, e só. |
| `tb_agendamentos_coletas` | `ck_agendamentos_coletas_resposta` | CHECK | Responsável e data da resposta são preenchidos juntos ou ficam os dois nulos. |
| `tb_atividades_diarias_usuarios` | `ck_atividades_diarias_intervalo` | CHECK | A última atividade do dia não pode ser anterior à primeira. |
| `tb_atividades_diarias_usuarios` | `ck_atividades_diarias_minutos` | CHECK | Minutos ativos não podem ser negativos. |
| `tb_atividades_diarias_usuarios` | `ck_atividades_diarias_plataforma` | CHECK | A plataforma é android, ios ou web. |
| `tb_atividades_diarias_usuarios` | `ck_atividades_diarias_qtd_acoes` | CHECK | A quantidade de ações não pode ser negativa. |
| `tb_atividades_diarias_usuarios` | `ck_atividades_diarias_qtd_sessoes` | CHECK | Se existe a linha do dia, houve pelo menos uma sessão. |
| `tb_atividades_diarias_usuarios` | `uq_atividades_diarias_usuario_data` | UNIQUE | Uma linha por usuário por dia (base do DAU e do UPSERT). |
| `tb_aulas` | `aulas_index_4` | UNIQUE | A ordem de uma aula é única dentro do curso. |
| `tb_autenticacoes_api` | `ck_autenticao_api_expira_em` | CHECK | A validade do token tem de ser positiva. |
| `tb_autenticacoes_api` | `ck_autenticao_api_token_type` | CHECK | O tipo do token é sempre Bearer. |
| `tb_autenticacoes_api` | `uq_autenticao_api_token` | UNIQUE | Dois usuários nunca compartilham o mesmo token. |
| `tb_avaliacoes_visitas_coletas` | `ck_avaliacoes_visitas_coletas_nota` | CHECK | A nota da avaliação vai de 1 a 5. |
| `tb_avaliacoes_visitas_coletas` | `uq_avaliacoes_visitas_coletas_visita_coleta_id` | UNIQUE | Cada visita recebe no máximo uma avaliação. |
| `tb_condominios` | `uq_condominios_endereco_id` | UNIQUE | Dois condomínios não dividem o mesmo endereço. |
| `tb_conversas` | `uq_conversas_condominio_cooperativa` | UNIQUE | Só uma conversa por par condomínio × cooperativa. |
| `tb_cooperativas` | `uq_cooperativas_endereco_id` | UNIQUE | Duas cooperativas não dividem o mesmo endereço. |
| `tb_cooperativas` | `uq_cooperativas_usuario_id` | UNIQUE | Um usuário representa no máximo uma cooperativa. |
| `tb_lkp_categorias_residuos` | `ck_categorias_residuos_limite_pontos_diario` | CHECK | O teto diário de pontos, se existe, não é negativo. |
| `tb_lkp_categorias_residuos` | `ck_categorias_residuos_pontos_base` | CHECK | Toda categoria vale pontos positivos. |
| `tb_lkp_niveis_confianca` | `ck_niveis_confianca_peso_voto` | CHECK | O peso do voto de um nível de confiança é positivo. |
| `tb_lkp_status_agendamentos` | `uq_lkp_status_agendamentos_nome_status` | UNIQUE | Não existem dois status de agendamento com o mesmo nome. |
| `tb_mensagens_conversas` | `ck_mensagens_conversas_conteudo` | CHECK | A mensagem tem de 1 a 2000 caracteres, sem contar os espaços das pontas. |
| `tb_mensagens_conversas` | `ck_mensagens_conversas_lida_em` | CHECK | A mensagem não pode ser lida antes de ser enviada. |
| `tb_mensagens_conversas` | `ck_mensagens_conversas_remetente_tipo` | CHECK | O remetente fala como COOPERATIVA ou como CONDOMINIO. |
| `tb_metricas_dau` | `ck_metricas_dau_contagens` | CHECK | O DAU nunca passa do WAU, e o WAU nunca passa do MAU. |
| `tb_metricas_dau` | `ck_metricas_dau_novos` | CHECK | Novos + retornantes dá exatamente o DAU do dia. |
| `tb_metricas_dau` | `ck_metricas_dau_stickiness` | CHECK | A stickiness é um percentual, de 0 a 100. |
| `tb_moradores` | `uq_moradores_usuario_id` | UNIQUE | Um usuário só vira morador uma vez. |
| `tb_movimentacoes_pontos` | `ck_mov_pontos_origem_consistente` | CHECK | O movimento vem de uma POSTAGEM (com postagem e categoria) ou de um QUIZ (com tentativa), nunca dos dois. |
| `tb_movimentacoes_pontos` | `ck_mov_pontos_origem_tipo` | CHECK | A origem do movimento é POSTAGEM ou QUIZ. |
| `tb_movimentacoes_pontos` | `ck_mov_pontos_pontos_positivo` | CHECK | Os pontos de um movimento são sempre positivos; o sentido vem do tipo. |
| `tb_movimentacoes_pontos` | `ck_mov_pontos_referencia_consistente` | CHECK | CRÉDITO não referencia outro movimento; ESTORNO e RESTAURAÇÃO precisam referenciar o crédito original. |
| `tb_movimentacoes_pontos` | `ck_mov_pontos_sync_timestamp` | CHECK | Marcado como sincronizado com o Redis, a data da sincronização é obrigatória. |
| `tb_movimentacoes_pontos` | `ck_mov_pontos_tentativas_sync` | CHECK | As tentativas de sincronização com o Redis não podem ser negativas. |
| `tb_movimentacoes_pontos` | `ck_mov_pontos_tipo_movimentacao` | CHECK | O tipo é CREDITO, ESTORNO ou RESTAURACAO. |
| `tb_movimentacoes_pontos` | `uq_mov_pontos_idempotency_key` | UNIQUE | Repetir a chamada da API (mesma chave) não duplica o movimento. |
| `tb_perguntas_quiz` | `perguntas_quiz_index_12` | UNIQUE | A ordem de uma pergunta é única dentro do quiz. |
| `tb_postagens` | `ck_postagens_capturada_em` | CHECK | A foto não pode ter sido capturada depois de a postagem ser feita. |
| `tb_postagens` | `ck_postagens_triagem_confianca` | CHECK | A confiança da triagem automática, se existe, vai de 0 a 100. |
| `tb_postagens` | `uq_postagens_hash_foto` | UNIQUE | A mesma foto não vale duas postagens. |
| `tb_quizzes` | `ck_quizzes_nota_minima_aprovacao` | CHECK | A nota mínima de aprovação vai de 0 a 100. |
| `tb_quizzes` | `ck_quizzes_pontos_recompensa` | CHECK | A recompensa de um quiz é positiva. |
| `tb_quizzes` | `uq_quizzes_aula_id` | UNIQUE | Cada aula tem no máximo um quiz. |
| `tb_recuperacoes_senha` | `uq_esqueci_senha_token_hash` | UNIQUE | Dois pedidos de recuperação nunca têm o mesmo token. |
| `tb_rel_cooperativas_categorias_materiais` | `cooperativas_categorias_materiais_index_1` | UNIQUE | Uma cooperativa não repete a mesma categoria. |
| `tb_rel_pontos_coletas_categorias` | `pontos_coletas_categorias_index_2` | UNIQUE | Um ponto de coleta não repete a mesma categoria. |
| `tb_rel_recorrencias_agendamentos` | `recorrencias_agendamentos_index_3` | UNIQUE | Um agendamento não repete o mesmo dia da semana. |
| `tb_rel_respostas_tentativas_quiz` | `respostas_tentativas_quiz_index_13` | UNIQUE | Uma pergunta é respondida uma vez por tentativa. |
| `tb_rel_usuarios_condominios` | `ck_usuarios_condominios_denuncias_procedentes` | CHECK | As denúncias procedentes não passam das denúncias realizadas. |
| `tb_rel_usuarios_condominios` | `ck_usuarios_condominios_denuncias_realizadas` | CHECK | As denúncias realizadas não podem ser negativas. |
| `tb_rel_usuarios_condominios` | `ck_usuarios_condominios_postagens_validadas` | CHECK | As postagens validadas sem contestação não podem ser negativas. |
| `tb_rel_usuarios_condominios` | `ck_usuarios_condominios_taxa_acerto_denuncias` | CHECK | A taxa de acerto é um percentual, de 0 a 100. |
| `tb_rel_usuarios_condominios` | `usuarios_condominios_index_5` | UNIQUE | Um usuário tem um só vínculo com cada condomínio. |
| `tb_rel_usuarios_cursos` | `usuarios_cursos_index_6` | UNIQUE | Um usuário tem um só progresso por aula. |
| `tb_rel_votos_postagens` | `ck_votos_postagens_peso_aplicado` | CHECK | O peso aplicado ao voto é positivo. |
| `tb_rel_votos_postagens` | `votos_postagens_index_7` | UNIQUE | Um usuário vota uma única vez em cada postagem. |
| `tb_sindicos` | `uq_sindicos_usuario_id` | UNIQUE | Um usuário só vira síndico uma vez. |
| `tb_tentativas_quiz` | `ck_tentativas_quiz_nota` | CHECK | A nota da tentativa, se existe, vai de 0 a 100. |
| `tb_torres` | `torres_index_0` | UNIQUE | O nome da torre é único dentro do condomínio. |
| `tb_torres` | `uq_torres_id_condominio` | UNIQUE | Par (torre, condomínio) único: é o alvo da FK composta de tb_moradores, que garante a torre do mesmo condomínio. |
| `tb_usuarios` | `uq_usuarios_cpf` | UNIQUE | Dois usuários não têm o mesmo CPF. |

**Data Mart.** Chave de negócio da dimensão/fato (id do OLTP): torna a carga repetível e evita duplicar linhas.

| Tabela | Constraint | Colunas |
|---|---|---|
| `dim_categoria_residuo` | `dim_categoria_residuo_id_categoria_key` | `(id_categoria)` |
| `dim_condominio` | `dim_condominio_id_condominio_key` | `(id_condominio)` |
| `dim_cooperativa` | `dim_cooperativa_id_cooperativa_key` | `(id_cooperativa)` |
| `dim_status_agendamento` | `dim_status_agendamento_id_status_key` | `(id_status)` |
| `dim_status_postagem` | `dim_status_postagem_codigo_key` | `(codigo)` |
| `dim_status_postagem` | `dim_status_postagem_id_status_validacao_key` | `(id_status_validacao)` |
| `dim_tempo` | `dim_tempo_data_completa_key` | `(data_completa)` |
| `dim_usuario` | `dim_usuario_id_usuario_key` | `(id_usuario)` |
| `fato_coletas` | `fato_coletas_id_visita_coleta_key` | `(id_visita_coleta)` |
| `fato_postagens` | `fato_postagens_id_postagem_key` | `(id_postagem)` |

## Apêndice C. Chaves estrangeiras por tabela (gerado do banco)

Nenhuma FK usa `ON DELETE CASCADE`: apagar uma linha referenciada é bloqueado. `ON UPDATE CASCADE` aparece nas FKs marcadas com (UC).

| Tabela | Coluna(s) → tabela referenciada |
|---|---|
| `fato_coletas` | `sk_condominio` → `dim_condominio`<br>`sk_cooperativa` → `dim_cooperativa`<br>`sk_status_agendamento` → `dim_status_agendamento`<br>`sk_tempo` → `dim_tempo` |
| `fato_postagens` | `sk_categoria` → `dim_categoria_residuo`<br>`sk_condominio` → `dim_condominio`<br>`sk_status_postagem` → `dim_status_postagem`<br>`sk_tempo` → `dim_tempo`<br>`sk_usuario` → `dim_usuario` |
| `tb_agendamentos_coletas` | `condominio_id` → `tb_condominios`<br>`cooperativa_id` → `tb_cooperativas`<br>`respondido_por_usuario_id` → `tb_usuarios`<br>`solicitado_por_usuario_id` → `tb_usuarios`<br>`status_agendamento_id` → `tb_lkp_status_agendamentos` |
| `tb_alternativas_quiz` | `pergunta_id` → `tb_perguntas_quiz` (UC) |
| `tb_atividades_diarias_usuarios` | `usuario_id` → `tb_usuarios` |
| `tb_aulas` | `curso_id` → `tb_cursos` |
| `tb_autenticacoes_api` | `usuario_id` → `tb_usuarios` |
| `tb_avaliacoes_visitas_coletas` | `usuario_avaliador_id` → `tb_usuarios`<br>`visita_coleta_id` → `tb_visitas_coletas` |
| `tb_condominios` | `endereco_id` → `tb_enderecos`<br>`sindico_id` → `tb_sindicos`<br>`tipo_condominio_id` → `tb_lkp_tipos_condominios` |
| `tb_conversas` | `condominio_id` → `tb_condominios`<br>`cooperativa_id` → `tb_cooperativas` |
| `tb_cooperativas` | `endereco_id` → `tb_enderecos`<br>`usuario_id` → `tb_usuarios` |
| `tb_log_auditoria` | `tipo_evento_auditado_id` → `tb_lkp_tipos_eventos_auditados`<br>`tipo_operacao_id` → `tb_lkp_tipos_operacoes_auditoria` |
| `tb_log_auditoria_agendamentos_coletas` | `agendamento_coleta_id` → `tb_agendamentos_coletas`<br>`status_anterior_id` → `tb_lkp_status_agendamentos`<br>`status_novo_id` → `tb_lkp_status_agendamentos`<br>`tipo_evento_auditado_id` → `tb_lkp_tipos_eventos_auditados`<br>`tipo_operacao_id` → `tb_lkp_tipos_operacoes_auditoria` |
| `tb_log_auditoria_postagens` | `postagem_id` → `tb_postagens`<br>`status_validacao_anterior_id` → `tb_lkp_status_validacoes_postagens`<br>`status_validacao_novo_id` → `tb_lkp_status_validacoes_postagens`<br>`tipo_evento_auditado_id` → `tb_lkp_tipos_eventos_auditados`<br>`tipo_operacao_id` → `tb_lkp_tipos_operacoes_auditoria` |
| `tb_log_auditoria_usuarios_condominios` | `tipo_evento_auditado_id` → `tb_lkp_tipos_eventos_auditados`<br>`tipo_operacao_id` → `tb_lkp_tipos_operacoes_auditoria`<br>`usuario_condominio_id` → `tb_rel_usuarios_condominios` |
| `tb_mensagens_conversas` | `conversa_id` → `tb_conversas`<br>`remetente_usuario_id` → `tb_usuarios` |
| `tb_moradores` | `condominio_id` → `tb_condominios`<br>`torre_id,condominio_id` → `tb_torres`<br>`usuario_id` → `tb_usuarios` |
| `tb_movimentacoes_pontos` | `categoria_id` → `tb_lkp_categorias_residuos`<br>`condominio_id` → `tb_condominios`<br>`movimentacao_referencia_id` → `tb_movimentacoes_pontos`<br>`postagem_id` → `tb_postagens`<br>`tentativa_quiz_id` → `tb_tentativas_quiz`<br>`torre_id` → `tb_torres`<br>`usuario_id` → `tb_usuarios` |
| `tb_notificacoes` | `usuario_id` → `tb_usuarios` |
| `tb_perguntas_quiz` | `quiz_id` → `tb_quizzes` (UC) |
| `tb_pontos_coletas` | `cooperativa_id` → `tb_cooperativas`<br>`endereco_id` → `tb_enderecos` |
| `tb_postagens` | `categoria_id` → `tb_lkp_categorias_residuos`<br>`condominio_id` → `tb_condominios`<br>`status_validacao_id` → `tb_lkp_status_validacoes_postagens`<br>`torre_id` → `tb_torres`<br>`usuario_id` → `tb_usuarios` |
| `tb_quizzes` | `aula_id` → `tb_aulas` (UC)<br>`curso_id` → `tb_cursos` |
| `tb_recuperacoes_senha` | `usuario_id` → `tb_usuarios` |
| `tb_rel_cooperativas_categorias_materiais` | `categoria_residuo_id` → `tb_lkp_categorias_residuos`<br>`cooperativa_id` → `tb_cooperativas` |
| `tb_rel_pontos_coletas_categorias` | `categoria_residuo_id` → `tb_lkp_categorias_residuos`<br>`ponto_coleta_id` → `tb_pontos_coletas` |
| `tb_rel_recorrencias_agendamentos` | `agendamento_coleta_id` → `tb_agendamentos_coletas`<br>`dia_semana_id` → `tb_lkp_dias_semanas` |
| `tb_rel_respostas_tentativas_quiz` | `alternativa_escolhida_id` → `tb_alternativas_quiz`<br>`pergunta_id` → `tb_perguntas_quiz`<br>`tentativa_id` → `tb_tentativas_quiz` (UC) |
| `tb_rel_usuarios_condominios` | `aprovado_por_usuario_id` → `tb_usuarios`<br>`condominio_id` → `tb_condominios`<br>`nivel_confianca_id` → `tb_lkp_niveis_confianca`<br>`usuario_id` → `tb_usuarios` |
| `tb_rel_usuarios_cursos` | `aula_id` → `tb_aulas`<br>`usuario_id` → `tb_usuarios` |
| `tb_rel_votos_postagens` | `motivo_denuncia_id` → `tb_lkp_motivos_denuncia`<br>`postagem_id` → `tb_postagens` (UC)<br>`tipo_voto_id` → `tb_lkp_tipos_votos_postagens`<br>`usuario_id` → `tb_usuarios` |
| `tb_sindicos` | `usuario_id` → `tb_usuarios` |
| `tb_telefones` | `usuario_id` → `tb_usuarios` |
| `tb_tentativas_quiz` | `condominio_id` → `tb_condominios`<br>`quiz_id` → `tb_quizzes`<br>`torre_id` → `tb_torres`<br>`usuario_id` → `tb_usuarios` |
| `tb_torres` | `condominio_id` → `tb_condominios` |
| `tb_usuarios` | `endereco_id` → `tb_enderecos`<br>`tipo_usuario_id` → `tb_lkp_tipos_usuarios` |
| `tb_visitas_coletas` | `agendamento_coleta_id` → `tb_agendamentos_coletas` |

## Apêndice D. Functions, procedures e triggers (gerado do banco)

| Objeto | Tipo | O que faz |
|---|---|---|
| `fn_calcular_trust_score` | function | Fórmula do trust_score (+2 por postagem validada, +5 por denúncia procedente, mais metade da taxa de acerto, teto 1000). IMMUTABLE. |
| `fn_pontos_disponiveis_postagem` | function | Pontos que uma postagem ainda pode render, respeitando o teto diário da categoria, pelo saldo líquido do ledger. |
| `fn_trg_auditoria_agendamentos_coletas` | function | Função da trigger de auditoria de tb_agendamentos_coletas. |
| `fn_trg_auditoria_postagens` | function | Função da trigger de auditoria de tb_postagens (grava OLD, NEW, TG_OP e CURRENT_USER na filha). |
| `fn_trg_auditoria_usuarios_condominios` | function | Função da trigger de auditoria de tb_rel_usuarios_condominios. |
| `fn_trg_validar_mensagem_conversa` | function | Valida remetente × lado, exige que a cooperativa inicie a conversa e atualiza ultima_mensagem_em. |
| `fn_trg_validar_partes_agendamento` | function | Garante que o solicitante representa o lado de origem e que quem responde é o lado oposto. |
| `fn_usuario_representa_lado` | function | TRUE se o usuário fala em nome do lado CONDOMINIO (síndico atual) ou COOPERATIVA. Reutilizada no agendamento e no chat. STABLE. |
| `fn_validar_referencia_movimentacao_pontos` | function | Garante que ESTORNO/RESTAURAÇÃO referencia um CRÉDITO da mesma origem, usuário e valor. |
| `sp_atualizar_trust_score` | procedure | Recalcula os contadores de confiança do usuário no condomínio e o promove a pessoa confiável. |
| `sp_carga_datamart` | procedure | ETL full-refresh do Data Mart (dimensões e fatos) a partir do OLTP. |
| `sp_consolidar_metricas_dau` | procedure | Consolida DAU/WAU/MAU, novos, retornantes e stickiness (UPSERT idempotente). |
| `sp_decidir_postagem_analise` | procedure | Decisão manual de uma postagem que terminou em análise. |
| `sp_encerrar_janela_postagem` | procedure | Fecha a janela comunitária de 24 h: saldo >= 0 aprova; −1 a −4 vai para análise; <= −5 reprova. |
| `sp_processar_voto_postagem` | procedure | Registra o voto ponderado dentro da janela comunitária, com as validações de vínculo, prazo e denúncia. |

| Trigger | Tabela | Quando | Eventos |
|---|---|---|---|
| `trg_auditoria_agendamentos_coletas` | `tb_agendamentos_coletas` | AFTER | INSERT, UPDATE, DELETE |
| `trg_auditoria_postagens` | `tb_postagens` | AFTER | INSERT, UPDATE, DELETE |
| `trg_auditoria_usuarios_condominios` | `tb_rel_usuarios_condominios` | AFTER | INSERT, UPDATE, DELETE |
| `trg_validar_mensagem_conversa` | `tb_mensagens_conversas` | BEFORE | INSERT |
| `trg_validar_partes_agendamento` | `tb_agendamentos_coletas` | BEFORE | INSERT, UPDATE |
| `trg_validar_referencia_movimentacao_pontos` | `tb_movimentacoes_pontos` | BEFORE | INSERT, UPDATE |

