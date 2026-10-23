# Política de Segurança

Este projeto gera dados **fictícios** (pt-BR) e os grava em um banco PostgreSQL do EcoCiente. Ele não trata dados pessoais reais, mas lida com credenciais de banco (DSN/`.env`) e **apaga dados** (`TRUNCATE`) no banco de destino.

## Versões suportadas

| Versão | Suporte |
| --- | --- |
| `main` (mais recente) | ✅ |
| Outros branches e commits antigos | ❌ |

## Reportando uma vulnerabilidade

**Não abra issue, pull request ou discussão públicos.**

Use o relato privado do GitHub: <https://github.com/EcoCiente-Instituto-J-F/md-populador-pgsql/security/advisories/new> (aba **Security → Advisories → Report a vulnerability**).

> Mantenedores: ative o *Private vulnerability reporting* em **Settings → Code security**.

Inclua no relato:

- o impacto;
- os passos para reproduzir, com dados falsos;
- o commit testado e a configuração usada;
- uma ideia de correção, se tiver.

O que acontece depois: confirmamos o recebimento, corrigimos de forma privada e publicamos um advisory com crédito a quem reportou. Pedimos um prazo razoável para a correção antes de qualquer divulgação.

## Escopo

**Dentro do escopo**

- Segredos commitados (senha, DSN, tokens).
- Vazamento da senha do banco em logs, na tela ou em mensagens de erro.
- Injeção SQL nos scripts do populador ou da tela.
- Execução de `TRUNCATE` sem a confirmação (ou `--force`/`ECOCIENTE_ALLOW_RESET=1`) no banco de destino.
- Falhas no workflow do PR Bot (`.github/workflows/pr-bot.yml`) que exponham `GEMINI_API_KEY` ou `GITHUB_TOKEN`.

**Fora do escopo**

- Bugs sem impacto de segurança.
- Falhas em serviços de terceiros (Aiven, GitHub, Gemini).
- Dados de exemplo do próprio populador (são fictícios).
- Negação de serviço no seu próprio banco ou deploy.

## Como o projeto protege os dados

| Camada | Onde | O que faz |
| --- | --- | --- |
| Configuração | `.env` (no `.gitignore`), `.env.example` | Mantém a DSN e a senha fora do repositório. |
| Conexão | `src/utils/helpers.py` | Lê a conexão do ambiente; `target_description` descreve o destino sem a senha. |
| Confirmação | `src/main.py`, `src/ui.py` | Pede confirmação antes do `TRUNCATE`; só é pulada com `--force` ou `ECOCIENTE_ALLOW_RESET=1`. |
| Dados únicos | `src/utils/unique_generator.py` | Tokens e hashes gerados com `secrets`. |
| CI | `.github/workflows/pr-bot.yml` | Roda com código da branch base e só em PRs de branches do próprio repositório. |

## Checklist de uso seguro

- Aponte o populador **apenas** para bancos de teste/desenvolvimento.
- Nunca versione o `.env`; troque a senha da Aiven se ela vazar.
- Use `sslmode=require` na conexão.
- Use um usuário de banco com o mínimo de permissão necessário.
- Guarde `GEMINI_API_KEY` apenas em *Secrets* do GitHub.
