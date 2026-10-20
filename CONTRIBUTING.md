# Como contribuir

Obrigado por querer contribuir com o **EcoCiente Populador PostgreSQL**! Este guia explica como preparar o ambiente, como organizar branches, commits e pull requests, e o que checar antes de enviar uma mudança.

Ao participar, você concorda com o nosso [Código de Conduta](CODE_OF_CONDUCT.md). Para vulnerabilidades, siga a [Política de Segurança](SECURITY.md) e **não** abra issue pública.

## Antes de começar

- Procure issues abertas antes de criar uma nova. Se a sua ideia for grande (por exemplo, mudar o schema ou adicionar uma etapa ao populador), abra uma issue primeiro para alinharmos o escopo.
- Uma mudança por pull request. PRs pequenas e focadas são revisadas mais rápido.

## Preparando o ambiente

Você vai precisar de **Python 3.10+** e de um **PostgreSQL 14+** (Aiven, local ou Docker). Os passos completos estão no [README](README.md). Em resumo:

```bash
git clone https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql.git
cd md-populador-pgsql
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # preencha com um banco de DESENVOLVIMENTO
psql "$ECOCIENTE_DSN" -v ON_ERROR_STOP=1 -f sql/ecociente_schema.sql
```

> [!WARNING]
> Nunca rode o populador contra um banco que tenha dados reais ou de produção. Ele faz `TRUNCATE` nas tabelas de negócio. Use um banco de desenvolvimento ou um serviço descartável.

Nunca faça commit do `.env`, de DSNs, senhas ou tokens. O arquivo já está no `.gitignore`, mas confira com `git status` antes de cada commit.

## Fluxo de contribuição

1. Faça um fork (ou, se você tem acesso de escrita, crie a branch direto no repositório).
2. Crie uma branch a partir de `main` com um prefixo que descreva o tipo da mudança:

   | Prefixo | Uso | Exemplo |
   |---|---|---|
   | `feat/` | nova funcionalidade | `feat/chat-cooperativa` |
   | `fix/` | correção de bug | `fix/torre-de-outro-condominio` |
   | `docs/` | documentação | `docs/readme-tabelas` |
   | `chore/` | manutenção, schema, configuração | `chore/ecociente-schema` |

3. Faça as mudanças, rode os testes (veja [Testes](#testes)) e confira o diff.
4. Abra a pull request para `main`.

## Mensagens de commit

Seguimos o padrão [Conventional Commits](https://www.conventionalcommits.org/pt-br/), com o tipo em minúsculas seguido de dois-pontos e uma descrição curta no imperativo:

```
feat: populate chat cooperativa x condominio
fix: torre de morador deve pertencer ao mesmo condominio
chore: ecociente schema
docs: updating readme
```

- Use a primeira linha com até ~72 caracteres.
- Se precisar de contexto, deixe uma linha em branco e explique o **porquê** no corpo do commit.
- Prefira commits pequenos e coerentes a um commit gigante que mistura assuntos.

## Padrões de código

- **Idioma:** comentários, docstrings, mensagens ao usuário e nomes de domínio ficam em **português**, como no restante do projeto (`criar_morador`, `popular_chat_cooperativas`, `tb_moradores`).
- **Estilo:** siga o estilo do arquivo que você está editando: nome de função em `snake_case`, indentação de 4 espaços e comentários com a mesma densidade do código vizinho. Não reformate linhas que não fazem parte da sua mudança.
- **Dependências:** antes de adicionar uma biblioteca, veja se a biblioteca padrão ou o que já está no `requirements.txt` resolve. Se adicionar, inclua a justificativa na PR.
- **Dados fictícios:** o populador deve continuar gerando massa em pt-BR com o `FakerBR`. Não inclua dados reais de pessoas, nem CPF, e-mail ou telefone verdadeiros.

## Alterações no schema (`sql/ecociente_schema.sql`)

Mudanças no schema costumam pedir ajustes em outros lugares. Antes de enviar a PR, confira:

- [ ] o script aplica sem erro com `ON_ERROR_STOP=1` em um PostgreSQL limpo;
- [ ] o populador (`src/utils/database.py` e `src/main.py`) preenche as novas colunas e tabelas, e não insere em colunas removidas;
- [ ] novas tabelas entram em `limpar_dados_banco` (em `database.py`) e, se forem de negócio, em `TABELAS_RESUMO` (em `main.py`);
- [ ] `src/tests/test_schema.py` tem a contagem de tabelas e colunas atualizada;
- [ ] o README reflete a contagem de tabelas, se ela mudou;
- [ ] a carga completa roda em pelo menos uma escala (`--escala leve`) sem erro.

## Testes

Os testes de autoverificação ficam em `src/tests/` e rodam a partir da pasta `src/`:

```bash
cd src
python -m tests.test_schema     # checagem de schema e de DSN
python -m tests.test_dau        # gerador de DAU
python -m tests.test_ui         # lógica do painel e do servidor da tela
```

Para validar a carga de ponta a ponta, rode o populador contra um banco de desenvolvimento:

```bash
cd src
python main.py --escala leve --force
```

Antes de abrir a PR, rode pelo menos os três testes e a carga `leve`, e inclua o resultado na descrição.

## Pull requests

- Descreva **o que** mudou e **por que**. Relacione a issue, se houver (`Closes #123`).
- Liste como você testou (comandos e escala usada).
- Atualize a documentação afetada (README, comentários de schema, este guia).
- Mantenha a PR focada. Se a revisão pedir mudanças, adicione commits novos em vez de reescrever o histórico, a menos que seja pedido.
- Você não precisa escrever a descrição do zero: o bot do repositório gera um rascunho, mas revise o conteúdo antes de considerar a PR pronta.

### Checklist

- [ ] a branch parte de `main` e tem um nome com prefixo válido;
- [ ] os commits seguem o padrão Conventional Commits;
- [ ] nenhum segredo, `.env` ou dado real foi incluído;
- [ ] os testes e a carga `leve` passam localmente;
- [ ] a documentação afetada foi atualizada.

## Licença

Ao contribuir, você concorda que sua contribuição será licenciada sob a [Licença MIT](LICENSE) do projeto.
