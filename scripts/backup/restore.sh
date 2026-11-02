#!/usr/bin/env bash
# Restaura um backup (.dump, formato custom) do banco EcoCiente.
set -euo pipefail

uso() {
  cat <<'AJUDA'
Uso: restore.sh [-t tabela]... [--truncar] [--comparar] <arquivo.dump> [dsn_destino]

  <arquivo.dump>   backup gerado por backup.sh
  <dsn_destino>    banco de destino (ou variável ECOCIENTE_RESTORE_DSN)
  -t, --tabela T   restaura só a tabela T (repetível; --data-only)
  --truncar        com -t: esvazia (TRUNCATE) as tabelas antes de restaurar
  --comparar       depois de restaurar, compara as contagens com a origem
                   (ECOCIENTE_DSN); sai com código 1 se alguma divergir
  -h, --help       esta ajuda

Variáveis de ambiente:
  ECOCIENTE_DSN          origem (usada por --comparar e para proteger contra
                         restaurar em cima do banco de produção); lida do .env
                         da raiz se não estiver no ambiente
  ECOCIENTE_RESTORE_DSN  destino alternativo ao argumento
  ECOCIENTE_ALLOW_RESET  =1 permite destino igual a ECOCIENTE_DSN
  PG_BIN                 pasta com pg_dump/pg_restore/psql (padrão: PATH)

Banco inteiro: pg_restore --clean --if-exists --no-owner --no-privileges
--exit-on-error. Apaga e recria os objetos do destino.

Tabela isolada (-t): usa --data-only. Sem --truncar, linhas já existentes
podem colidir com a chave primária. Para recuperar uma exclusão acidental com
segurança, o caminho recomendado é restaurar o dump INTEIRO num banco novo e
copiar de lá as linhas que faltam.

Exemplos:
  restore.sh --comparar backups/ecociente_20260101_120000.dump postgres://u:s@h:5432/ecociente_teste
  ECOCIENTE_RESTORE_DSN=postgres://u:s@h:5432/novo restore.sh backups/ecociente_x.dump
  restore.sh -t tb_cursos --truncar backups/ecociente_x.dump postgres://u:s@h:5432/ecociente_teste
AJUDA
}

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TABELAS=(); TRUNCAR=0; COMPARAR=0; POS=()
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) uso; exit 0;;
    -t|--tabela) [ $# -ge 2 ] || { echo "ERRO: $1 exige o nome da tabela" >&2; exit 2; }; TABELAS+=("$2"); shift 2;;
    --truncar) TRUNCAR=1; shift;;
    --comparar) COMPARAR=1; shift;;
    --) shift; while [ $# -gt 0 ]; do POS+=("$1"); shift; done;;
    -*) echo "ERRO: opção desconhecida: $1 (veja --help)" >&2; exit 2;;
    *) POS+=("$1"); shift;;
  esac
done
ARQUIVO="${POS[0]:-}"
DESTINO="${POS[1]:-${ECOCIENTE_RESTORE_DSN:-}}"
[ -n "$ARQUIVO" ] || { echo "ERRO: informe o arquivo .dump (veja --help)" >&2; exit 2; }
[ -f "$ARQUIVO" ] || { echo "ERRO: arquivo não encontrado: $ARQUIVO" >&2; exit 1; }
[ -n "$DESTINO" ] || { echo "ERRO: informe o destino (argumento <dsn_destino> ou ECOCIENTE_RESTORE_DSN)" >&2; exit 2; }
if [ "$TRUNCAR" -eq 1 ] && [ "${#TABELAS[@]}" -eq 0 ]; then
  echo "ERRO: --truncar só vale junto com -t" >&2; exit 2
fi
for t in ${TABELAS[@]+"${TABELAS[@]}"}; do
  case "$t" in ""|[0-9]*|*[!a-z0-9_]*) echo "ERRO: nome de tabela inválido: $t" >&2; exit 2;; esac
done

# ---------- conexão de origem ----------
DSN="${ECOCIENTE_DSN:-}"
if [ -z "$DSN" ] && [ -f "$RAIZ/.env" ]; then
  DSN="$(grep -E '^[[:space:]]*ECOCIENTE_DSN=' "$RAIZ/.env" | tail -n 1 | sed -E 's/^[[:space:]]*ECOCIENTE_DSN=//' | tr -d '\r' || true)"
  DSN="${DSN%\"}"; DSN="${DSN#\"}"; DSN="${DSN%\'}"; DSN="${DSN#\'}"
fi
if [ -z "$DSN" ] && [ "$COMPARAR" -eq 1 ]; then
  echo "ERRO: defina ECOCIENTE_DSN (veja .env.example)" >&2; exit 1
fi
mascarar() { printf '%s' "$1" | sed -E 's#(://[^:/@]*):[^/]*@#\1:***@#; s#(password=)[^[:space:]]+#\1***#g'; }

if [ -n "$DSN" ] && [ "$DESTINO" = "$DSN" ] && [ "${ECOCIENTE_ALLOW_RESET:-}" != "1" ]; then
  echo "ERRO: o destino é igual a ECOCIENTE_DSN ($(mascarar "$DESTINO")). Recusado para não sobrescrever a origem; defina ECOCIENTE_ALLOW_RESET=1 se for isso mesmo." >&2
  exit 1
fi

# ---------- binários ----------
achar_bin() {
  local nome="$1" c
  if [ -n "${PG_BIN:-}" ]; then
    for c in "$PG_BIN/$nome" "$PG_BIN/$nome.exe"; do
      if [ -x "$c" ]; then printf '%s' "$c"; return 0; fi
    done
  elif command -v "$nome" >/dev/null 2>&1; then
    command -v "$nome"; return 0
  fi
  echo "ERRO: '$nome' não encontrado${PG_BIN:+ em PG_BIN=$PG_BIN}. Instale o cliente PostgreSQL (versão >= à do servidor; a Aiven usa PG 16+) ou aponte PG_BIN." >&2
  return 1
}
PG_RESTORE="$(achar_bin pg_restore)" || exit 1
PSQL="$(achar_bin psql)" || exit 1

agora() { if [ -n "${EPOCHREALTIME:-}" ]; then printf '%s' "${EPOCHREALTIME/,/.}"; else date +%s; fi; }
dif() { awk -v a="$1" -v b="$2" 'BEGIN { printf "%.1f", b - a }'; }

PRINCIPAIS=(tb_usuarios tb_condominios tb_moradores tb_cooperativas tb_postagens tb_rel_votos_postagens
  tb_agendamentos_coletas tb_visitas_coletas tb_cursos tb_aulas tb_quizzes tb_tentativas_quiz
  tb_movimentacoes_pontos tb_notificacoes tb_log_auditoria fato_postagens fato_coletas)

existe() { # $1=dsn $2=tabela -> 0 se existe
  local r
  r="$("$PSQL" -X -qtA -d "$1" -c "SELECT to_regclass('public.$2') IS NOT NULL" 2>/dev/null)" || return 2
  [ "$r" = "t" ]
}
contar() { # $1=dsn $2=tabela -> contagem ou '-' se a tabela não existe
  if existe "$1" "$2"; then
    "$PSQL" -X -qtA -d "$1" -c "SELECT count(*) FROM public.$2"
  else
    printf '%s' "-"
  fi
}

echo "Arquivo: $ARQUIVO"
echo "Destino: $(mascarar "$DESTINO")"

# o destino tem de aceitar conexão
"$PSQL" -X -qtA -d "$DESTINO" -c "SELECT 1" >/dev/null || { echo "ERRO: não foi possível conectar ao destino." >&2; exit 1; }

T0="$(agora)"
if [ "${#TABELAS[@]}" -eq 0 ]; then
  cod=0
  "$PG_RESTORE" --clean --if-exists --no-owner --no-privileges --exit-on-error -d "$DESTINO" "$ARQUIVO" || cod=$?
  [ "$cod" -eq 0 ] || { echo "ERRO: pg_restore falhou (código $cod)." >&2; exit 1; }
else
  lista=""
  for t in "${TABELAS[@]}"; do
    existe "$DESTINO" "$t" || { echo "ERRO: a tabela $t não existe no destino. Crie o schema antes (ou restaure o dump inteiro num banco novo)." >&2; exit 1; }
    lista="${lista:+$lista, }public.$t"
  done
  if [ "$TRUNCAR" -eq 1 ]; then
    echo "Esvaziando: $lista"
    "$PSQL" -X -q -v ON_ERROR_STOP=1 -d "$DESTINO" -c "TRUNCATE TABLE $lista" \
      || { echo "ERRO: TRUNCATE falhou (chaves estrangeiras de outras tabelas?). Nada foi restaurado." >&2; exit 1; }
  else
    echo "AVISO: sem --truncar; linhas já existentes podem colidir com a chave primária."
  fi
  args=()
  for t in "${TABELAS[@]}"; do args+=(-t "$t"); done
  cod=0
  "$PG_RESTORE" --data-only --no-owner --no-privileges --exit-on-error "${args[@]}" -d "$DESTINO" "$ARQUIVO" || cod=$?
  [ "$cod" -eq 0 ] || { echo "ERRO: pg_restore falhou (código $cod)." >&2; exit 1; }
fi
T1="$(agora)"
echo "Restauração concluída em $(dif "$T0" "$T1") s"

# ---------- contagens ----------
DIVERGE=0
if [ "$COMPARAR" -eq 1 ]; then
  printf '%-28s %12s %12s\n' tabela origem restaurado
else
  printf '%-28s %12s\n' tabela linhas
fi
for t in "${PRINCIPAIS[@]}"; do
  dest="$(contar "$DESTINO" "$t")"
  if [ "$COMPARAR" -eq 1 ]; then
    orig="$(contar "$DSN" "$t")"
    marca=""
    if [ "$orig" != "$dest" ]; then marca="  <-- DIVERGE"; DIVERGE=1; fi
    printf '%-28s %12s %12s%s\n' "$t" "$orig" "$dest" "$marca"
  else
    [ "$dest" = "-" ] || printf '%-28s %12s\n' "$t" "$dest"
  fi
done

if [ "$COMPARAR" -eq 1 ]; then
  if [ "$DIVERGE" -eq 0 ]; then echo "Contagens iguais."; else echo "ERRO: contagens divergentes." >&2; exit 1; fi
fi
