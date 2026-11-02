# Modelagem de Dados

## Links do GitHub: onde se encontra cada demanda

Cada link abre direto o arquivo da demanda, na branch `feat/metadata` do repositório
[md-populador-pgsql](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql).

### Demanda 1: Catálogo de Dados (design do relatório do ia-eko)

| Item | Link |
|---|---|
| Catálogo em PDF | [catalogo_dados.pdf](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/blob/feat/metadata/documentos/catalogo_dados.pdf) |
| Catálogo em HTML | [catalogo_dados.html](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/blob/feat/metadata/documentos/catalogo_dados.html) |
| Conteúdo extraído do HTML original | [dados/catalogo.json](https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/blob/feat/metadata/documentos/dados/catalogo.json) |
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

**Atenção:** os links só funcionam depois de `backup_e_recuperacao.html/.pdf` e as alterações
de `gerar_documentos.py` e do catálogo serem commitados e enviados (`push`) para
`origin/feat/metadata`. Hoje esses arquivos estão só no working tree.

## Liberação de acesso para os professores

**Pendente, e só o dono do repositório pode fazer.** O repositório fica na organização
`EcoCiente-Instituto-J-F`. Para liberar: *Settings > Collaborators and teams > Add people*
(ou tornar o repositório público). Não foi feito nesta sessão, e a lista de professores
das disciplinas não foi fornecida.

## Relatório de justificativa (review)

Revisão feita em 02/11/2026, sobre o working tree.

### O que foi verificado

| Verificação | Resultado |
|---|---|
| `python documentos/gerar_documentos.py` | Gera os dois PDFs, sem avisos do conversor |
| Páginas: catálogo / backup | 66 / 11; o número do PDF bate com o impresso pelo gerador |
| Tamanho de página | 824,9 × 637,9 pt (1100 × 850 px) em todas |
| Índice do catálogo | 102 entradas conferidas contra a página real da ficha: 0 erros |
| HTML sem JavaScript | Confirmado (0 `<script>` no documento de backup) |
| `extrair_catalogo.py` | 51 tabelas em 11 camadas; 306 colunas lidas do schema |
| `requirements.txt` e `.gitignore` | `beautifulsoup4`, `playwright` e `backups/` presentes |
| Backup/restore em PostgreSQL 16 (Docker) | Backup 0,5 s, restauração 2,0 s, 17 de 17 contagens iguais |
| Inspeção visual | Páginas do backup (todas) e do catálogo (amostra: 13–24 e 61–66) |

### Divergências entre catálogo e schema (só reportadas, não corrigidas)

8 tabelas do schema ficam fora do catálogo HTML: `tb_autenticacoes_api`, `tb_movimentacoes_pontos`,
`tb_atividades_diarias_usuarios`, `tb_metricas_dau`, `tb_recuperacoes_senha`, `tb_migracao_ids_map`,
`tb_conversas` e `tb_mensagens_conversas`. Nenhuma tabela do catálogo falta no schema.

### Decisões que merecem justificativa

1. **Colunas, nível e PII vêm de regra, não do HTML.** O catálogo original não tem colunas, PII nem
   nível de acesso. O dono escolheu "schema + nível derivado": colunas e chaves vêm do schema SQL, e
   nível e PII saem de regra fixa. Todo nível e PII leva a etiqueta DERIVADO e o documento diz que
   não é classificação oficial.
2. **Metas de backup são premissas.** RPO 24 h, RTO 1 h, frequência diária e retenção 7 + 4 levam
   PREMISSA. Só os tempos do teste levam MEDIDO.
3. **Nada afirmado sobre o provedor.** O documento não cita limites ou planos do Aiven ou Neon
   (não foram verificados) e manda conferir no console.
4. **`->` no lugar de `→`** nas FKs, porque a fonte latina embutida não tem a seta.

### Problemas encontrados

| Gravidade | Problema | Situação |
|---|---|---|
| Alta | `sql/ecociente_schema.sql` falha em banco vazio: `idx_esqueci_senha_usuario_id` (linha ~613) vem antes de `CREATE TABLE tb_recuperacoes_senha` (~2164). | Corrigido só numa cópia temporária, a pedido. **O arquivo do repositório continua quebrado.** Está documentado na página de falhas. |
| Média | A restauração parcial `restore.sh -t ... --truncar` não usa CASCADE; tabelas referenciadas por FK precisam ser listadas juntas. | Decisão de segurança, documentada. |
| Média | Tempos medidos na escala `leve`, num PostgreSQL local, sem rede. | Declarado em "O que este documento não afirma". |
| Baixa | O `.ps1` foi validado de ponta a ponta só no PowerShell 7 (contêiner). No Windows PowerShell 5.1 foi até a checagem do `pg_dump`. | Documentado em "Como medimos". |
| Baixa | Retenção: com vários dumps na mesma semana ISO, a semana já coberta por um diário pode ser repetida. | Literal do brief; ajuste de 1 linha se quiserem outra regra. |
| Baixa | Muito espaço em branco em várias fichas do catálogo (ficha pequena sozinha na página) e nas páginas 5 e 7 do backup. | Estético; nada cortado. |
| Baixa | A senha na DSN aparece na linha de comando do `pg_dump` (visível em `ps`). | Mascarada nas mensagens; a linha de comando não. |

### O que não foi revisado

- Não olhei as páginas 3–12 e 25–60 do catálogo uma a uma nesta revisão; só a amostra acima e as
  checagens automáticas (índice, tamanho, contagem).
- A revisão foi feita por Sonnet 5.5, a mesma sessão que implementou a T5. Não é uma revisão independente.

### Veredito

Entrega completa e consistente: os dois documentos geram, nada está cortado nas páginas
inspecionadas e os números do documento de backup vêm do teste real. Antes de enviar aos
professores, falta **commitar e enviar** os arquivos novos, **liberar o acesso** ao repositório e
decidir o que fazer com o índice quebrado em `sql/ecociente_schema.sql`.
