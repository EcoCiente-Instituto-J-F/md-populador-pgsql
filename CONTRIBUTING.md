# Contribuindo com o Populador PostgreSQL do EcoCiente

Ao participar, você concorda em seguir o [Código de Conduta](CODE_OF_CONDUCT.md). Para reportar um problema de segurança, **não** abra uma issue — siga o [SECURITY.md](SECURITY.md).

## Idioma

Código, comentários, mensagens de commit, issues e PRs são escritos em **português do Brasil**.

## Configurando o ambiente

Você precisa de Python 3.10+ e de um PostgreSQL 14+ de **teste** (um Postgres local ou a Aiven Free Tier).

```bash
git clone https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql.git
cd md-populador-pgsql
python3 -m venv .venv && source .venv/bin/activate   # Windows: py -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                                  # Windows: copy .env.example .env
psql "$ECOCIENTE_DSN" -v ON_ERROR_STOP=1 -f sql/ecociente_schema.sql
```

Preencha o `.env` com os dados do seu banco de teste. O `.env` está no `.gitignore`: nunca o versione.

## Testando sua mudança

O repositório ainda não tem um workflow de CI que rode os testes. Rode os self-checks a partir da pasta `src/`:

```bash
cd src
python -m tests.test_dau
python -m tests.test_schema
python -m tests.test_ui
```

Se sua mudança mexe na carga, rode também o populador em um banco de teste:

```bash
python main.py --escala leve --force
```

Regras para os testes:

- Toda mudança de comportamento vem com um teste que falha sem ela.
- Os testes não usam rede, API paga nem dados de produção.

> [!WARNING]
> Cada execução do populador faz `TRUNCATE … RESTART IDENTITY CASCADE` nas tabelas de negócio. Confira o banco de destino antes de rodar.

## Regras do projeto

- Nenhum segredo no repositório (senhas, DSN, tokens). Use o `.env`.
- Nenhum dado pessoal real em testes ou exemplos. Os dados são fictícios, gerados por `src/utils/faker_br.py`.
- A conexão é configurada em um só lugar: `src/utils/helpers.py`. Se criar uma variável de ambiente nova, atualize o `.env.example`.
- Dados únicos (CPF, e-mail, hash de foto, token) vêm de `src/utils/unique_generator.py`, para evitar colisões.
- O populador não recalcula em Python o que o banco já faz: use as *procedures* e *triggers* do schema.
- Mudou o schema? Atualize `sql/ecociente_schema.sql` (e `sql/migracao_dau.sql`, se for o caso do DAU).
- Nenhuma dependência nova sem discussão prévia em uma issue.

## Pull requests

1. Crie um branch a partir da `main` (ex.: `feat/minha-mudanca`).
2. Faça commits focados, com prefixos: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`.
3. Abra o PR para a `main`. O **EcoCiente PR Bot** (`.github/workflows/pr-bot.yml`) gera a descrição automaticamente nos PRs de branches do próprio repositório.
4. Um mantenedor revisa o PR antes do merge.

## Reportando bugs e propondo funcionalidades

Abra uma issue descrevendo o que aconteceu (ou o que você propõe), os passos para reproduzir, a escala e a `--seed` usadas e a versão do Python e do PostgreSQL. Não inclua senhas nem a DSN do seu banco.
