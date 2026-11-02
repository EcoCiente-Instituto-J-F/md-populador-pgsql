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
arquivo e o trecho do repositório onde a decisão está, para quem for conferir.

Ambiente: PostgreSQL 14+. O sistema aceita **Neon e Aiven** (a conexão é uma DSN PostgreSQL comum); a referência de dimensionamento é o **Neon, plano free, limite de 1 GB**. O schema tem **59 tabelas**
(50 em [`sql/ecociente_schema.sql`](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/blob/feat/metadata/sql/ecociente_schema.sql)
e 9 do Data Mart em [`sql/ecociente_datamart.sql`](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/blob/feat/metadata/sql/ecociente_datamart.sql)).
Os dois arquivos foram aplicados, na ordem, num PostgreSQL 16 vazio, sem erro.

### Decisão de base: o provedor (Neon free, 1 GB)

| | |
|---|---|
| **Decisão** | Todo o projeto é dimensionado para caber em 1 GB e para não depender de recursos que o plano free pode não ter. |
| **Por quê** | O limite de 1 GB é fixo. O populador tem três escalas: `leve` (~25 MB), `medio` (~55 MB) e `pesado` (~145 MB), medidas pelo próprio `--help` de `src/main.py`. A `pesado` usa cerca de 15% do limite, então há folga de sobra para o log de auditoria e o DAU crescerem. |
| **Alternativa descartada** | Depender dos backups e da recuperação a um ponto no tempo do provedor. |
| **Por que esta é a melhor** | O que o plano free cobre é algo que o console do Neon confirma e que pode mudar; um dump lógico (`pg_dump -Fc`) de 1,5 MB na escala leve é independente do plano, do serviço e da conta. O banco inteiro cabe em um arquivo pequeno, então manter o dump fora do servidor custa quase nada. |

O documento de backup trata RPO, RTO, frequência e retenção como **premissas** e só os tempos do teste como **medidos**. Nenhum limite do Neon além do 1 GB informado pela equipe é afirmado; o que o plano free cobre deve ser conferido no console.

### 1. Modelagem de Dados

**1.1 Banco normalizado até a 3FN (com lookups).**

- *Feito:* tabelas de domínio `tb_lkp_*` (tipos de usuário, status de agendamento, categorias de resíduo, motivos de denúncia etc.) e tabelas de relação `tb_rel_*` (votos, usuários×condomínios, usuários×cursos). Atributos que se repetiam ou dependiam só de outro atributo viraram tabela (por exemplo `tb_enderecos`, `tb_telefones`).
- *Por quê:* cada fato fica em um só lugar, então alterar o nome de um status ou de uma categoria é um `UPDATE` de uma linha, sem anomalia de atualização.
- *Descartado:* colunas de texto livre ou `ENUM` para status e tipos.
- *Por que a melhor:* lookup tem integridade por FK, aceita novos valores sem `ALTER TYPE` e pode ter atributos próprios (por exemplo `limite_pontos_diario` da categoria). Não foi preciso ir à 4FN/5FN: as tabelas `tb_rel_*` já são o resultado das dependências N:N, e a 5FN só se justifica quando há dependência de junção que não existe aqui.

**1.2 PKs, FKs e cardinalidades.**

- *Feito:* PKs `GENERATED ALWAYS AS IDENTITY`, FKs nomeadas `fk_<tabela>_<coluna>`, `UNIQUE` e `CHECK` nomeados. 1:1 nos subtipos de usuário, 1:N nas hierarquias (condomínio, torre, morador), N:N nas tabelas `tb_rel_*`.
- *Por quê:* nomes previsíveis facilitam mensagens de erro e o catálogo; `IDENTITY` é o padrão do PostgreSQL moderno e impede inserir um id à mão por engano.
- *Descartado:* `SERIAL` e PKs naturais.
- *Por que a melhor:* `SERIAL` é um atalho legado e tem donos de sequência confusos; chaves naturais (e-mail, CPF) mudam e são PII, então não devem ser chave de ligação.

**1.3 Massa de dados (500+ registros verossímeis).**

- *Feito:* o populador (`src/main.py`) gera dados fictícios em pt-BR com 12 meses de histórico. Mesmo na escala `leve` o teste mediu 435 usuários, 1.595 postagens, 8.591 votos e 16.020 linhas de auditoria, muito acima de 500.
- *Por quê:* volume e padrões (sazonalidade, coortes, abandono) tornam as views de BI e o `EXPLAIN ANALYZE` significativos.
- *Descartado:* carga manual por `INSERT` e dados aleatórios sem estrutura.
- *Por que a melhor:* os dados passam pelas procedures e triggers do próprio banco, então testam as regras de verdade, e as escalas permitem escolher o volume conforme o 1 GB.

**1.4 Subtipos de usuário por FK (e não por `INHERITS`).**

- *Feito:* `tb_usuarios` guarda os dados comuns de toda pessoa (nome, e-mail, senha, tipo) e os subtipos `tb_sindicos`, `tb_moradores` e `tb_cooperativas` guardam o que é específico de cada papel. Cada subtipo aponta para `tb_usuarios` por uma FK.
- *Por quê:* muitas tabelas do sistema referenciam o usuário por FK (postagens, votos, notificações, DAU, tentativas de quiz, entre outras). No `INHERITS` do PostgreSQL, uma FK que aponta para a tabela-mãe só enxerga as linhas gravadas na própria mãe, e **não** as das filhas. Com os subtipos em `INHERITS`, o usuário gravado na filha não poderia ser referenciado por essas FKs.
- *Descartado:* `INHERITS (tb_usuarios)` nos três subtipos.
- *Por que a melhor:* mantém a integridade referencial inteira (PK, FK e `UNIQUE` valem em toda a hierarquia), que é a razão de ser do banco relacional. O `INHERITS` foi usado onde essa perda não pesa, na auditoria (seção 6), que só recebe escrita e não é referenciada por nenhuma outra tabela. Escolher o mecanismo conforme o risco, e não aplicar o mesmo em tudo, foi a decisão mais segura.

### 2. Engenharia de Dados e ETL

**2.1 Integração RPA em outro repositório.**

- *Feito:* este repositório só contém o que o banco precisa para receber a migração: a tabela `tb_migracao_ids_map` (`entidade`, `legacy_id`, `novo_id`, PK composta). O RPA em si fica no repositório **`md-rpa-integration`**.
- *Por quê:* o RPA tem ciclo de vida, dependências e credenciais próprias (conexão com o banco legado). O banco e o robô evoluem em ritmos diferentes.
- *Descartado:* misturar o código do RPA no repositório do banco.
- *Por que a melhor:* o contrato entre os dois é pequeno e explícito: o mapa legado → novo torna a carga **idempotente** (rodar de novo não duplica) e resolve as FKs das entidades dependentes. O documento de backup também descreve o RPA como falha prevista (carga transacional, reconciliação).

**2.2 Camada de BI: Data Mart em Star Schema.**

- *Feito:* 7 dimensões (`dim_tempo`, `dim_usuario`, `dim_condominio`, `dim_cooperativa`, `dim_categoria_residuo`, `dim_status_postagem`, `dim_status_agendamento`) e 2 fatos (`fato_postagens`, `fato_coletas`), com chaves substitutas (`sk_*`) e grão documentado em cada `COMMENT`. A carga é a procedure `sp_carga_datamart()`.
- *Por quê:* BI faz agregações por tempo, condomínio, categoria e cooperativa; o star schema entrega isso com poucos joins.
- *Descartado:* Snowflake, e views direto sobre o OLTP.
- *Por que a melhor:* o snowflake normaliza as dimensões e acrescenta joins sem ganho, e as dimensões aqui são pequenas. Views só sobre o OLTP competem com a carga transacional e não guardam histórico.

**2.3 CTEs e Window Functions.**

- *Feito:* a `dim_tempo` é gerada com **CTE recursiva** (`WITH RECURSIVE`, em `ecociente_datamart.sql`); as 19 views analíticas de `ecociente_schema.sql` e as 4 do Data Mart usam CTEs para organizar a transformação em etapas. As window functions estão nas 4 views `vw_bi_*` do Data Mart: `RANK()`/`DENSE_RANK()` (ranking de condomínios por mês), `SUM() OVER` (total acumulado de postagens por usuário), `LAG()` (evolução mensal das coletas) e `AVG() OVER` com janela de 7 dias (média móvel do DAU).
- *Por quê:* a lógica de transformação fica legível em etapas, e os cálculos analíticos não exigem subconsultas aninhadas.
- *Por que a melhor:* CTEs e window functions são o jeito idiomático do PostgreSQL e o planejador as otimiza bem; a alternativa de calcular em Python tiraria a regra do banco.

### 3. Objetos Lógicos e Otimização

**3.1 Functions e Procedures (mínimo 2 e 2).**

- *Feito:* functions `fn_pontos_disponiveis_postagem` e `fn_calcular_trust_score`; procedures `sp_processar_voto_postagem`, `sp_encerrar_janela_postagem`, `sp_decidir_postagem_analise`, `sp_atualizar_trust_score` e `sp_consolidar_metricas_dau`.
- *Por quê:* pontuação, voto e moderação são regras críticas que precisam ser atômicas e idênticas para qualquer cliente (API, populador, RPA).
- *Descartado:* regra na aplicação.
- *Por que a melhor:* no banco, a regra roda dentro da mesma transação do dado e vale para todos os clientes; function para cálculo sem efeito colateral, procedure para o que escreve e controla transação.

**3.2 Triggers de auditoria (NEW, OLD, TG_OP, CURRENT_USER; mínimo 2 tabelas).**

- *Feito:* três tabelas auditadas: `tb_postagens`, `tb_agendamentos_coletas` e `tb_usuarios_condominios`, por `fn_trg_auditoria_*` e `trg_auditoria_*`, gravando o antes e o depois, a operação e o usuário (`executado_por DEFAULT CURRENT_USER`).
- *Por quê:* são as tabelas em que um conflito (conteúdo moderado, coleta, vínculo de confiança) precisa de rastro.
- *Por que a melhor:* trigger audita qualquer caminho de escrita, inclusive acesso direto ao banco; auditoria na aplicação perderia esse caso.

**3.3 EXPLAIN ANALYZE e índices.**

- *Feito:* quatro casos em `ecociente_schema.sql` (fila de moderação, histórico de denúncias, auditoria por período e indicadores por condomínio), cada um com "antes" e "depois" e o índice proposto (33 `CREATE INDEX` no total, entre eles os parciais, como `idx_postagens_pendentes_moderacao`).
- *Por quê:* índice só vale se o plano mudar de `Seq Scan` para `Index Scan`.
- *Descartado:* indexar toda FK por reflexo.
- *Por que a melhor:* no Neon free, com 1 GB, cada índice ocupa espaço e custa escrita; o índice parcial indexa só as linhas que a consulta usa.

### 4. Governança de Dados

**4.1 Catálogo de Dados (a "tabela técnica de metadados").**

- *Feito:* o catálogo é o PDF [`catalogo_dados.pdf`](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/blob/feat/metadata/documentos/catalogo_dados.pdf), gerado de `dados/catalogo.json` e do schema. Ele descreve cada tabela, suas colunas, regras de negócio e nível de acesso (PUBLICO, INTERNO, RESTRITO e CONFIDENCIAL), mais o mapa de PII.
- *Por quê:* a equipe definiu que o catálogo em PDF é a entrega de metadados.
- *Descartado:* um segundo catálogo dentro do banco.
- *Por que a melhor:* uma só fonte da verdade, regerada por `python documentos/gerar_documentos.py`, evita que um catálogo em tabela e um em documento divirjam. As descrições de coluna vêm do próprio `COMMENT ON COLUMN` do schema, então o catálogo acompanha o banco.
- *Limite assumido:* nível de acesso e PII são **derivados por regra fixa** (permissões do catálogo e nome da coluna), com a etiqueta DERIVADO; não são uma classificação oficial.

**4.2 Backup e Recuperação.**

- *Feito:* [`backup_e_recuperacao.pdf`](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/blob/feat/metadata/documentos/backup_e_recuperacao.pdf) e os scripts em [`scripts/backup`](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/tree/feat/metadata/scripts/backup) (`backup.sh`/`.ps1`, `restore.sh`/`.ps1`). Dump `-Fc` diário, `--schema-only` a cada mudança, retenção 7 diários + 4 semanais, restauração do banco inteiro ou de uma tabela, conferência por contagem.
- *Medido:* backup 0,5 s, restauração 2,0 s e 17 de 17 contagens iguais (escala leve, PostgreSQL 16 em Docker).
- *Por quê:* o Neon free tem 1 GB e a equipe precisa de um caminho de recuperação que não dependa do plano.
- *Descartado:* depender só dos recursos do provedor, e `pg_dumpall`.
- *Por que a melhor:* o formato `-Fc` é compacto e permite restaurar uma tabela com `pg_restore -t`; o dump é portátil entre provedores e versões. Cada script recusa restaurar por cima de `ECOCIENTE_DSN` sem confirmação explícita.

### 5. Monitoramento: DAU no banco

- *Feito:* `tb_atividades_diarias_usuarios` (uma linha por usuário por dia, `UNIQUE (usuario_id, data_atividade)`, a API faz `UPSERT` a cada sessão) e `tb_metricas_dau` (DAU, WAU, MAU, novos, retornantes e stickiness). A `sp_consolidar_metricas_dau` recalcula o intervalo de forma idempotente. As views `vw_dau_por_tipo_usuario` e `vw_retencao_coortes_mensais` consomem os dados.
- *Por quê:* DAU precisa ser registrado de forma barata a cada sessão e consolidado uma vez por dia.
- *Descartado:* contar DAU com `COUNT(DISTINCT)` direto sobre as tabelas de negócio.
- *Por que a melhor:* a tabela diária mantém o custo de escrita baixo e uma linha por usuário/dia, o que importa no limite de 1 GB, e o `CHECK` (`wau >= dau`, `mau >= wau`) barra métricas incoerentes.
- *Limite assumido:* o agendamento diário da consolidação é feito pela API (`current_date - 1`), não por um job dentro do Postgres.

### 6. Estruturas Avançadas

- **CTE recursiva:** usada na `dim_tempo`, onde faz sentido porque a série de datas é, por natureza, gerada passo a passo. *Melhor que* `generate_series` ou uma tabela estática? A CTE recursiva demonstra a técnica pedida e gera apenas o intervalo necessário.
- **Herança de tabelas com `INHERITS`:** a auditoria usa o recurso nativo do PostgreSQL. `tb_log_auditoria` é a tabela-mãe (id, tipo de evento, tipo de operação, quem executou, quando) e `tb_log_auditoria_postagens`, `tb_log_auditoria_agendamentos_coletas` e `tb_log_auditoria_usuarios_condominios` são as filhas, cada uma declarada com `INHERITS (tb_log_auditoria)` e com as colunas do seu assunto.
  - *Como funciona:* as filhas recebem as colunas, o `NOT NULL`, o `CHECK` e o `DEFAULT` da mãe. A mãe fica vazia; um `SELECT` em `tb_log_auditoria` lê as linhas de todas as filhas, e `tableoid::regclass` diz de qual tabela veio cada linha. Cada trigger grava uma única linha na filha, sem a etapa antiga de gravar na mãe e depois na filha.
  - *O que o `INHERITS` não herda e como foi tratado:* a identidade (`GENERATED ... AS IDENTITY`), a PK, as FKs, o `UNIQUE` e os índices. A mãe usa uma sequence compartilhada (`seq_log_auditoria`), então o `id_auditoria` é único entre todas as filhas; cada filha declara de novo a sua PK, as FKs e o índice por `executado_em`. Foi testado: 16.497 linhas lidas pela mãe (15.788 + 85 + 624), 0 linhas só na mãe e ids sem repetição.
  - *Alternativa descartada:* modelar a herança por FK 1:1 (Class Table Inheritance, como antes). O professor pediu herança de tabelas, e `INHERITS` é o mecanismo do próprio PostgreSQL para isso.
  - *Por que a melhor aqui:* a perda de PK e FK entre mãe e filha quase não pesa na auditoria, porque o log só recebe escrita e nenhuma outra tabela referencia `tb_log_auditoria`. A consulta por período (caso 3 do `EXPLAIN`) passou a usar os índices de cada filha (`Append` sobre `Bitmap Index Scan`).
  - *Por que os subtipos de usuário não usam `INHERITS`:* ver a decisão 1.4.

### O que foi verificado

| Verificação | Resultado |
|---|---|
| `sql/ecociente_schema.sql` e `ecociente_datamart.sql` num PostgreSQL 16 vazio | Aplicam sem erro (`ON_ERROR_STOP`): **59 tabelas** e o índice `idx_esqueci_senha_usuario_id` no lugar |
| `python documentos/gerar_documentos.py` | Gera os dois PDFs, sem avisos do conversor |
| Populador `--escala leve --force` com a auditoria em `INHERITS` | Roda sem erro; triggers gravam nas filhas; a mãe lê 16.497 linhas e `ONLY` na mãe lê 0 |
| Páginas: catálogo / backup | 66 / 11; o número do PDF bate com o gerador |
| Tamanho de página | 824,9 × 637,9 pt (1100 × 850 px) |
| Índice do catálogo | 102 entradas conferidas contra a página real: 0 erros |
| Backup e restauração (Docker, PostgreSQL 16) | 0,5 s e 2,0 s; 17 de 17 contagens iguais |

### Tabelas do schema fora do catálogo (só reportadas)

8 tabelas do schema ficam fora do catálogo: `tb_autenticacoes_api`, `tb_movimentacoes_pontos`,
`tb_atividades_diarias_usuarios`, `tb_metricas_dau`, `tb_recuperacoes_senha`, `tb_migracao_ids_map`,
`tb_conversas` e `tb_mensagens_conversas`. Nenhuma tabela do catálogo falta no schema.

### Limites declarados

| Gravidade | Limite | Situação |
|---|---|---|
| Média | Nível de acesso e PII do catálogo são **derivados**, não uma classificação oficial. | Declarado no catálogo (etiqueta DERIVADO). |
| Média | Tempos de backup e restauração foram medidos na escala `leve`, num PostgreSQL local, sem rede. Contra o Neon entram latência e o tamanho real. | Declarado em "O que este documento não afirma". |
| Média | O que o plano free do Neon cobre além de 1 GB (recuperação, suspensão por inatividade) não foi verificado. | A conferir no console; o documento não afirma nada disso. |
| Baixa | `restore.sh -t ... --truncar` não usa `CASCADE`; tabelas referenciadas por FK precisam ser listadas juntas. | Escolha de segurança, documentada. |
| Baixa | O `.ps1` foi validado de ponta a ponta no PowerShell 7 (contêiner). No Windows PowerShell 5.1 foi até a checagem do `pg_dump`. | Documentado em "Como medimos". |
| Média | As observações do catálogo (`dados/catalogo.json`) das 3 tabelas filhas de auditoria ainda citam o vínculo 1:1 por `auditoria_id`, anterior à herança com `INHERITS`; a tabela de colunas da mesma ficha já mostra o schema atual. | Texto do catálogo não alterado; o schema é a fonte das colunas. |
| Baixa | README e `main.py` citam Aiven. | Mantidos: o sistema aceita Neon e Aiven, pois a conexão é uma DSN PostgreSQL comum. |
| Baixa | A senha da DSN aparece na linha de comando do `pg_dump` (visível em `ps`). | Mascarada nas mensagens; a linha de comando não. |
