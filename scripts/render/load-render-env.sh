#!/usr/bin/env bash
# Load Render credentials from repo .env and verify workspace (hercule, not lontis).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ENV_FILE="${RENDER_ENV_FILE:-$ROOT/.env}"
EXPECTED_NAME="${RENDER_WORKSPACE_NAME:-hercule}"

if [ ! -f "$ENV_FILE" ]; then
  echo "[load-render-env] Missing $ENV_FILE" >&2
  exit 1
fi

eval "$(python3 - "$ENV_FILE" <<'PY'
import shlex
import sys
from pathlib import Path

path = Path(sys.argv[1])
values = {}
for raw in path.read_text().splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1]
    values[key] = value

for key in ("RENDER_API_KEY", "RENDER_WORKSPACE_ID", "RENDER_WORKSPACE_NAME"):
    if key in values and values[key]:
        print(f"export {key}={shlex.quote(values[key])}")
PY
)"

if [ -z "${RENDER_API_KEY:-}" ]; then
  echo "[load-render-env] RENDER_API_KEY is missing in $ENV_FILE" >&2
  exit 1
fi

if ! command -v render >/dev/null 2>&1; then
  echo "[load-render-env] render CLI not found (brew install render)" >&2
  exit 1
fi

workspaces_json="$(render workspaces -o json 2>/dev/null || true)"
if [ -z "$workspaces_json" ]; then
  echo "[load-render-env] Could not list Render workspaces (check RENDER_API_KEY)" >&2
  exit 1
fi

resolved="$(python3 - "$workspaces_json" "$EXPECTED_NAME" "${RENDER_WORKSPACE_ID:-}" <<'PY'
import json
import sys

workspaces = json.loads(sys.argv[1])
expected_name = sys.argv[2].strip().lower()
expected_id = sys.argv[3].strip()

if not workspaces:
    print("error=No workspaces returned for this API key")
    raise SystemExit(0)

match = None
if expected_id:
    for ws in workspaces:
        if ws.get("id") == expected_id:
            match = ws
            break

if match is None:
    for ws in workspaces:
        if str(ws.get("name", "")).lower() == expected_name:
            match = ws
            break

if match is None:
    names = ", ".join(f"{ws.get('name')} ({ws.get('id')})" for ws in workspaces)
    print(f"error=Expected workspace '{expected_name}' not found. Available: {names}")
    raise SystemExit(0)

print(
    "name=" + str(match.get("name", "")) + "\n"
    + "id=" + str(match.get("id", "")) + "\n"
    + "email=" + str(match.get("email", ""))
)
PY
)"

if grep -q '^error=' <<<"$resolved"; then
  echo "[load-render-env] $(echo "$resolved" | sed -n 's/^error=//p')" >&2
  exit 1
fi

WS_NAME="$(echo "$resolved" | sed -n 's/^name=//p')"
WS_ID="$(echo "$resolved" | sed -n 's/^id=//p')"
WS_EMAIL="$(echo "$resolved" | sed -n 's/^email=//p')"

export RENDER_WORKSPACE_ID="${RENDER_WORKSPACE_ID:-$WS_ID}"
export RENDER_WORKSPACE_NAME="${RENDER_WORKSPACE_NAME:-$WS_NAME}"

if [ "$(echo "$WS_NAME" | tr '[:upper:]' '[:lower:]')" = "lontis" ]; then
  echo "[load-render-env] Wrong workspace: lontis. Use contact@hercule.dev API key." >&2
  exit 1
fi

render workspace set "$RENDER_WORKSPACE_ID" --confirm -o text >/dev/null 2>&1 || true

echo "[load-render-env] workspace=$WS_NAME id=$WS_ID email=$WS_EMAIL"
