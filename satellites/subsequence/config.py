"""Environment for Instantly subsequence bypass Streamlit tool."""

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
WEBHOOK_PATH = "/api/webhooks/instantly"
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
    if "henri-fridzi.homes" in base:
        return (
            "NEXT_PUBLIC_APP_URL pointe vers henri-fridzi.homes (incorrect). "
            f"Utilisez `{PRODUCTION_APP_URL}`."
        )
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


def webhook_auto_send_enabled() -> bool:
    """Webhook auto-send toggle stored in Supabase (Setup tab)."""
    from supabase_repo import get_webhook_auto_send_enabled

    return get_webhook_auto_send_enabled()


def supabase_url() -> str:
    return env("SUPABASE_URL") or env("NEXT_PUBLIC_SUPABASE_URL")


def supabase_service_role_key() -> str:
    return env("SUPABASE_SERVICE_ROLE_KEY")


def waiting_for_reply_interest_value() -> int | None:
    raw = env("INSTANTLY_WAITING_FOR_REPLY_INTEREST_VALUE")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def send_window_tz() -> str:
    return "Europe/Paris"


def send_window_start_hour() -> int:
    return 8


def send_window_end_hour() -> int:
    return 17


def no_reply_email2_delay_days() -> int:
    raw = env("INSTANTLY_NO_REPLY_EMAIL2_DELAY_DAYS", "3")
    try:
        parsed = int(raw)
        return parsed if parsed > 0 else 3
    except ValueError:
        return 3
