# Política de Segurança

Obrigado por ajudar a manter o **EcoCiente Populador PostgreSQL** seguro.

## Versões suportadas

Só a branch `main` recebe correções de segurança. Se você encontrou um problema em outra branch, reporte-o mesmo assim, mas a correção será feita sobre `main`.

## Como reportar uma vulnerabilidade

**Não abra uma issue pública** para vulnerabilidades. Isso expõe o problema antes de existir correção.

Use um dos canais abaixo, nesta ordem de preferência:

1. **Relatório privado no GitHub:** aba **Security → Report a vulnerability** deste repositório.
2. **E-mail aos mantenedores:** `[E-MAIL DE SEGURANÇA A DEFINIR]`.

Inclua, sempre que possível:

- descrição do problema e o impacto que você imagina;
- passos para reproduzir (ou um trecho de código / comando mínimo);
- versão afetada (commit ou data do último commit da `main`);
- sugestão de correção, se tiver.

**Não inclua credenciais reais** (senhas, DSN do Aiven, tokens da API do Gemini ou do GitHub) no relato. Se precisar mostrar um segredo exposto, troque uma parte dele por `***`.

## O que esperar

- Vamos confirmar o recebimento e avaliar o relato assim que possível.
- Mantemos você informado sobre o andamento da correção.
- Pedimos que não divulgue o problema publicamente até que exista uma correção ou que tenhamos combinado um prazo.
- Se o relato for aceito, o crédito será dado no histórico do projeto, a menos que você prefira permanecer anônimo.

Relatos sobre o comportamento esperado do projeto (por exemplo, o populador apagar dados ao rodar em um banco que você apontou sem querer) não são vulnerabilidades, mas são bem-vindos como issue comum. Veja a seção de notas abaixo.

## Escopo

**Dentro do escopo:**

- código em `src/` (incluindo a tela local `src/ui.py` e o servidor HTTP dela);
- scripts em `scripts/pr-bot/` e o workflow `.github/workflows/pr-bot.yml`;
- scripts SQL em `sql/` (por exemplo, funções, procedures ou triggers que permitam burlar regras de negócio ou de acesso);
- vazamento de segredos pelo código, logs ou CI.

**Fora do escopo:**

- credenciais que cada pessoa mantém no próprio `.env` local;
- problemas de configuração do serviço de banco (Aiven, PostgreSQL local) que não vêm do código deste repositório;
- dados fictícios gerados pelo populador.

## Notas de segurança do projeto

Este projeto gera **massa de teste**. Algumas escolhas são deliberadas para facilitar a reprodução e não devem ser usadas em produção:

- **Senhas de teste são previsíveis.** `gerar_senha_segura` monta a senha a partir do e-mail. Os hashes em `hash_senha` também não são bcrypt de verdade (são derivados de SHA-256). Nunca use esses usuários em um ambiente real nem com dados de pessoas reais.
- **O populador apaga dados.** Cada execução faz `TRUNCATE … CASCADE` em todas as tabelas de negócio do banco apontado por `ECOCIENTE_DSN` (ou pelas variáveis `ECOCIENTE_DB_*`). Confira o destino antes de confirmar. `ECOCIENTE_ALLOW_RESET=1` e `--force` pulam essa confirmação, então use-os só em CI ou em bancos descartáveis.
- **Segredos ficam fora do repositório.** O `.env` está no `.gitignore`. Use `.env.example` como modelo e nunca faça commit de DSNs, senhas ou tokens.
- **A tela local escuta só em `127.0.0.1:8766`.** Não a exponha em rede (proxy, túnel ou bind em `0.0.0.0`) sem antes revisar o servidor.
- **O bot de PR só roda para branches do próprio repositório.** O workflow não recebe `GEMINI_API_KEY` em PRs vindas de forks, de propósito. Não altere essa condição para liberar segredos a código de terceiros.

## Divulgação coordenada

Pedimos que você siga a divulgação coordenada: nos dê tempo razoável para corrigir antes de tornar o problema público. Em troca, nos comprometemos a não tomar medidas contra quem reportar de boa-fé e a atuar com transparência sobre a correção.
