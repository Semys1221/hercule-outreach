"""Environment for AI Reply Agent Streamlit tool."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
_APP_DIR = Path(__file__).resolve().parent
_ROOT_ENV = _REPO_ROOT / ".env"
_LOCAL_ENV = _APP_DIR / ".env"

for env_path in (_ROOT_ENV, _LOCAL_ENV):
    if env_path.is_file():
        load_dotenv(env_path, override=True)

PRODUCTION_APP_URL = "https://www.hercule.dev"
WEBHOOK_PATH = "/api/webhooks/instantly/reply"
PRODUCTION_WEBHOOK_URL = f"{PRODUCTION_APP_URL}{WEBHOOK_PATH}"


def env(name: str, default: str = "") -> str:
    value = os.getenv(name, default).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1].strip()
    return value


def require_instantly_api_key() -> str:
    key = env("INSTANTLY_API_KEY")
    if not key:
        raise ValueError("INSTANTLY_API_KEY is not set")
    return key


def app_base_url() -> str:
    return env("NEXT_PUBLIC_APP_URL", PRODUCTION_APP_URL).rstrip("/")


def normalize_webhook_url(url: str) -> str:
    return url.strip().rstrip("/")


def is_valid_webhook_target_url(target_url: str) -> bool:
    return normalize_webhook_url(target_url) == normalize_webhook_url(
        PRODUCTION_WEBHOOK_URL
    )


def webhook_public_url() -> str:
    return f"{app_base_url()}{WEBHOOK_PATH}"


def webhook_url_error() -> str | None:
    base = app_base_url()
    if is_valid_webhook_target_url(webhook_public_url()):
        return None
    if "localhost" in base:
        return (
            "NEXT_PUBLIC_APP_URL pointe vers localhost. "
            f"Utilisez `{PRODUCTION_APP_URL}`."
        )
    return (
        f"NEXT_PUBLIC_APP_URL (`{base}`) ne correspond pas à la prod attendue "
        f"(`{PRODUCTION_APP_URL}`)."
    )


def webhook_secret() -> str:
    return env("INSTANTLY_BYPASS_WEBHOOK_SECRET") or env("CRON_SECRET")


def supabase_url() -> str:
    return env("SUPABASE_URL") or env("NEXT_PUBLIC_SUPABASE_URL")


def supabase_service_role_key() -> str:
    return env("SUPABASE_SERVICE_ROLE_KEY")


def grok_api_key_status() -> tuple[bool, str]:
    key = env("GROK_API_KEY") or env("XAI_API_KEY")
    if key:
        return True, ""
    if env("GROQ_API_KEY"):
        return (
            False,
            "GROQ_API_KEY détectée mais ce module utilise xAI. "
            "Ajoutez GROK_API_KEY (ou XAI_API_KEY) depuis console.x.ai dans .env, "
            "puis redémarrez Streamlit.",
        )
    return (
        False,
        "GROK_API_KEY manquante. Ajoutez-la dans .env (console.x.ai), "
        "puis redémarrez Streamlit.",
    )


def grok_api_key() -> str:
    ok, hint = grok_api_key_status()
    if not ok:
        raise ValueError(hint or "GROK_API_KEY is not set")
    return env("GROK_API_KEY") or env("XAI_API_KEY")


def grok_management_key() -> str:
    return env("XAI_MANAGEMENT_KEY") or env("XAI_MGMT_KEY") or env("GROK_MANAGEMENT_KEY")


def grok_team_id() -> str:
    # Team ID from console.x.ai URL: console.x.ai/team/<team_id>/settings
    return env("XAI_TEAM_ID") or env("GROK_TEAM_ID")


def groq_api_key() -> str:
    """Deprecated alias — use grok_api_key()."""
    return grok_api_key()


def send_window_tz() -> str:
    return "Europe/Paris"


def send_window_start_hour() -> int:
    return 8


def send_window_end_hour() -> int:
    return 17


def bulk_try_agent_concurrency() -> int:
    raw = env("BULK_TRY_AGENT_CONCURRENCY", "5")
    try:
        return max(1, min(int(raw), 16))
    except ValueError:
        return 5


def prompts_dir() -> Path:
    return _APP_DIR / "prompts"
