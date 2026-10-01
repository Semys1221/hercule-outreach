#!/usr/bin/env bash
# Run MyEmailVerifier clean pipeline headlessly (Render / local).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=/dev/null
if [ -z "${RENDER:-}" ] && [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi
export PYTHONPATH="${PYTHONPATH:-$ROOT:$ROOT/clean}"
export HERCULE_DATA_ROOT="${HERCULE_DATA_ROOT:-/var/data}"

cd "$ROOT/clean"

LIST_ID="${CLEAN_LIST_ID:?CLEAN_LIST_ID is required}"
MODE="${CLEAN_MODE:-test_50}"

args=(run --list-id "$LIST_ID" --mode "$MODE")
if [ -n "${CLEAN_CAMPAIGN_ID:-}" ]; then
  args+=(--campaign-id "$CLEAN_CAMPAIGN_ID")
fi
if [ "${CLEAN_SKIP_PUSH:-0}" = "1" ]; then
  args+=(--skip-push)
fi
if [ -n "${CLEAN_RESUME_PREFIX:-}" ]; then
  args+=(--resume-prefix "$CLEAN_RESUME_PREFIX")
fi
if [ -n "${CLEAN_ALLOWED_STATUSES:-}" ]; then
  args+=(--allowed-statuses "$CLEAN_ALLOWED_STATUSES")
fi

echo "[run-clean] list=$LIST_ID mode=$MODE"
python cli.py "${args[@]}"
