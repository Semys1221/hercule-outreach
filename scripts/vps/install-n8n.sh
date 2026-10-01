#!/usr/bin/env bash
# Install n8n Community + Postgres on the Hercule VPS (localhost bind).
#
# Usage (on VPS, as root):
#   sudo bash lib/backend/scripts/vps/install-n8n.sh
#
# Access from Mac:
#   ssh -L 5678:127.0.0.1:5678 root@201.18.210.83
#   open http://127.0.0.1:5678
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
REPO_ROOT="${VPS_REPO_ROOT:-$ROOT}"
N8N_DIR="$REPO_ROOT/lib/backend/scripts/n8n"
CRED_DIR="/root/.hercule"
ENV_FILE="$N8N_DIR/.env"
ENC_FILE="$CRED_DIR/n8n-encryption-key"
PG_FILE="$CRED_DIR/n8n-postgres-password"
BASIC_FILE="$CRED_DIR/n8n-basic-auth-password"
BASIC_USER="${N8N_BASIC_AUTH_USER:-admin}"

rand_hex() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    head -c 32 /dev/urandom | xxd -p -c 64
  fi
}

rand_pass() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 24 | tr -d '/+=' | head -c 24
  else
    head -c 32 /dev/urandom | base64 | tr -d '/+=' | head -c 24
  fi
}

echo "[install-n8n] repo=$REPO_ROOT"

if [ "$(id -u)" -ne 0 ]; then
  echo "[install-n8n] must run as root (sudo)" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "[install-n8n] Docker not found. Install Docker Engine first:" >&2
  echo "  https://docs.docker.com/engine/install/" >&2
  exit 1
fi

COMPOSE=(docker compose)
if ! docker compose version >/dev/null 2>&1; then
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE=(docker-compose)
  else
    echo "[install-n8n] docker compose plugin missing" >&2
    exit 1
  fi
fi

mkdir -p "$CRED_DIR"
chmod 700 "$CRED_DIR"

if [ ! -f "$ENC_FILE" ]; then
  rand_hex > "$ENC_FILE"
  chmod 600 "$ENC_FILE"
  echo "[install-n8n] generated encryption key → $ENC_FILE"
else
  echo "[install-n8n] reusing encryption key at $ENC_FILE"
fi

if [ ! -f "$PG_FILE" ]; then
  rand_pass > "$PG_FILE"
  chmod 600 "$PG_FILE"
  echo "[install-n8n] generated postgres password → $PG_FILE"
else
  echo "[install-n8n] reusing postgres password at $PG_FILE"
fi

if [ ! -f "$BASIC_FILE" ]; then
  rand_pass > "$BASIC_FILE"
  chmod 600 "$BASIC_FILE"
  echo "[install-n8n] generated basic auth password → $BASIC_FILE"
else
  echo "[install-n8n] reusing basic auth password at $BASIC_FILE"
fi

ENC_KEY="$(tr -d '\n' < "$ENC_FILE")"
PG_PASS="$(tr -d '\n' < "$PG_FILE")"
BASIC_PASS="$(tr -d '\n' < "$BASIC_FILE")"

WEBHOOK_URL="${WEBHOOK_URL:-http://127.0.0.1:5678/}"
N8N_HOST="${N8N_HOST:-localhost}"
N8N_PROTOCOL="${N8N_PROTOCOL:-http}"

if [ -f "$ENV_FILE" ]; then
  echo "[install-n8n] preserving existing $ENV_FILE (update WEBHOOK_URL manually for public webhooks)"
  # Ensure required keys exist without overwriting user edits
  grep -q '^N8N_ENCRYPTION_KEY=' "$ENV_FILE" || echo "N8N_ENCRYPTION_KEY=$ENC_KEY" >> "$ENV_FILE"
else
  cat > "$ENV_FILE" <<EOF
POSTGRES_USER=n8n
POSTGRES_PASSWORD=${PG_PASS}
POSTGRES_DB=n8n

N8N_ENCRYPTION_KEY=${ENC_KEY}

N8N_VERSION=1.82.1
N8N_BIND=127.0.0.1
N8N_PORT=5678
N8N_HOST=${N8N_HOST}
N8N_PROTOCOL=${N8N_PROTOCOL}
WEBHOOK_URL=${WEBHOOK_URL}

TZ=Europe/Paris
N8N_DIAGNOSTICS_ENABLED=false

N8N_BASIC_AUTH_ACTIVE=true
N8N_BASIC_AUTH_USER=${BASIC_USER}
N8N_BASIC_AUTH_PASSWORD=${BASIC_PASS}
EOF
  chmod 600 "$ENV_FILE"
  echo "[install-n8n] wrote $ENV_FILE"
fi

cd "$N8N_DIR"
"${COMPOSE[@]}" up -d

echo ""
echo "[install-n8n] stack up."
echo "  UI        http://127.0.0.1:5678  (localhost on VPS)"
echo "  Basic user  ${BASIC_USER}"
echo "  Basic pass  cat $BASIC_FILE"
echo ""
echo "From your Mac:"
echo "  ssh -L 5678:127.0.0.1:5678 root@201.18.210.83"
echo "  open http://127.0.0.1:5678"
echo ""
echo "Public webhooks: set WEBHOOK_URL in $ENV_FILE then docker compose up -d"
