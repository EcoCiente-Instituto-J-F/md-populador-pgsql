#!/usr/bin/env bash
# Backup do banco EcoCiente (pg_dump -Fc + schema.sql) com retenção diária/semanal.
#
# Variáveis de ambiente:
#   ECOCIENTE_DSN                  DSN do banco (ou linha ECOCIENTE_DSN= do .env na raiz)
#   ECOCIENTE_BACKUP_DIR           pasta de saída (padrão: <raiz>/backups)
#   ECOCIENTE_RETENCAO_DIARIOS     backups mais novos mantidos (padrão: 7)
#   ECOCIENTE_RETENCAO_SEMANAIS    semanas ISO adicionais mantidas (padrão: 4)
#   PG_BIN                         pasta com pg_dump/pg_restore/psql (padrão: PATH)
#
# Uso: scripts/backup/backup.sh [-h|--help]
set -euo pipefail

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 0
fi

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# ---------- conexão ----------
DSN="${ECOCIENTE_DSN:-}"
if [ -z "$DSN" ] && [ -f "$RAIZ/.env" ]; then
  # lê só a linha ECOCIENTE_DSN= (sem executar o .env)
  DSN="$(grep -E '^[[:space:]]*ECOCIENTE_DSN=' "$RAIZ/.env" | tail -n 1 | sed -E 's/^[[:space:]]*ECOCIENTE_DSN=//' | tr -d '\r' || true)"
  DSN="${DSN%\"}"; DSN="${DSN#\"}"; DSN="${DSN%\'}"; DSN="${DSN#\'}"
fi
if [ -z "$DSN" ]; then
  echo "ERRO: defina ECOCIENTE_DSN (veja .env.example)" >&2
  exit 1
fi
mascarar() { printf '%s' "$1" | sed -E 's#(://[^:/@]*):[^/]*@#\1:***@#; s#(password=)[^[:space:]]+#\1***#g'; }

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
PG_DUMP="$(achar_bin pg_dump)" || exit 1

# ---------- tempo ----------
agora() { if [ -n "${EPOCHREALTIME:-}" ]; then printf '%s' "${EPOCHREALTIME/,/.}"; else date +%s; fi; }
dif() { awk -v a="$1" -v b="$2" 'BEGIN { printf "%.1f", b - a }'; }
mb() { awk -v b="$(wc -c < "$1" | tr -d ' ')" 'BEGIN { printf "%.1f", b / 1048576 }'; }

# ---------- saída ----------
DIR="${ECOCIENTE_BACKUP_DIR:-$RAIZ/backups}"
N_DIA="${ECOCIENTE_RETENCAO_DIARIOS:-7}"
N_SEM="${ECOCIENTE_RETENCAO_SEMANAIS:-4}"
case "$N_DIA$N_SEM" in *[!0-9]*|"") echo "ERRO: retenção deve ser número inteiro (ECOCIENTE_RETENCAO_DIARIOS >= 1, ECOCIENTE_RETENCAO_SEMANAIS >= 0)" >&2; exit 1;; esac
if [ "$N_DIA" -lt 1 ]; then echo "ERRO: ECOCIENTE_RETENCAO_DIARIOS deve ser >= 1 (a retenção nunca pode apagar o backup recém-criado)" >&2; exit 1; fi
mkdir -p "$DIR"

CARIMBO="$(date +%Y%m%d_%H%M%S)"
while [ -e "$DIR/ecociente_$CARIMBO.dump" ]; do sleep 1; CARIMBO="$(date +%Y%m%d_%H%M%S)"; done
DUMP="$DIR/ecociente_$CARIMBO.dump"
SCHEMA="$DIR/ecociente_$CARIMBO.schema.sql"
trap 'rm -f "$DUMP.parcial" "$SCHEMA.parcial"; exit 130' INT TERM

echo "Banco: $(mascarar "$DSN")"
T0="$(agora)"

# grava em .parcial e só renomeia se o pg_dump terminar com código 0
executar() { # $1=destino final; resto = argumentos do pg_dump
  local final="$1"; shift
  local parcial="$final.parcial" cod=0
  "$PG_DUMP" "$@" --no-owner --no-privileges -f "$parcial" "$DSN" || cod=$?
  if [ "$cod" -ne 0 ]; then
    rm -f "$parcial"
    echo "ERRO: pg_dump falhou (código $cod). Nenhum backup novo foi gravado." >&2
    return "$cod"
  fi
  if ! mv "$parcial" "$final"; then
    rm -f "$parcial"
    echo "ERRO: não foi possível gravar $final. Nenhum backup novo foi gravado." >&2
    return 1
  fi
}

executar "$DUMP" -Fc || { rm -f "$DUMP.parcial" "$SCHEMA.parcial"; exit 1; }
executar "$SCHEMA" --schema-only || { rm -f "$DUMP" "$SCHEMA.parcial"; exit 1; }
T1="$(agora)"

echo "ok: ${DUMP#"$RAIZ"/} ($(mb "$DUMP") MB) em $(dif "$T0" "$T1") s"
echo "ok: ${SCHEMA#"$RAIZ"/} ($(mb "$SCHEMA") MB)"

# ---------- retenção (só após sucesso) ----------
semana_iso() { # $1=AAAAMMDD -> AAAA-SS (ano-semana ISO)
  date -d "${1:0:4}-${1:4:2}-${1:6:2}" +%G-%V 2>/dev/null \
    || date -j -f %Y%m%d "$1" +%G-%V
}

mapfile -t TODOS < <(ls -1 "$DIR" | grep -E '^ecociente_[0-9]{8}_[0-9]{6}\.dump$' | sort -r)
manter=(); apagar=(); semanas_vistas=()
i=0
for f in "${TODOS[@]}"; do
  i=$((i + 1))
  if [ "$i" -le "$N_DIA" ]; then manter+=("$f"); continue; fi
  sem="$(semana_iso "${f:10:8}")"
  achou=0
  for s in ${semanas_vistas[@]+"${semanas_vistas[@]}"}; do [ "$s" = "$sem" ] && achou=1; done
  if [ "$achou" -eq 0 ] && [ "${#semanas_vistas[@]}" -lt "$N_SEM" ]; then
    semanas_vistas+=("$sem"); manter+=("$f")
  else
    apagar+=("$f")
  fi
done

echo "Retenção (diários=$N_DIA, semanais=$N_SEM):"
for f in ${manter[@]+"${manter[@]}"}; do echo "  mantido: $f"; done
for f in ${apagar[@]+"${apagar[@]}"}; do
  rm -f "$DIR/$f" "$DIR/${f%.dump}.schema.sql"
  echo "  apagado: $f (e ${f%.dump}.schema.sql)"
done
