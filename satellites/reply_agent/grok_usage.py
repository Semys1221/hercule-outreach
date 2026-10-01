"""Fetch and parse xAI Grok API quota / billing usage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import requests

from config import grok_api_key, grok_management_key, grok_team_id

XAI_API_BASE = "https://api.x.ai/v1"
XAI_MGMT_BASE = "https://management-api.x.ai/v1"
XAI_MGMT_AUTH_BASE = "https://management-api.x.ai"
_REQUEST_TIMEOUT = 15


@dataclass(frozen=True)
class GrokUsageSnapshot:
    remaining_percent: float | None
    remaining_usd: float | None
    period_end: str | None
    source: str
    error: str | None = None


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _object_cents(value: Any) -> int | None:
    if not isinstance(value, dict):
        return None
    raw = value.get("val")
    if raw is None:
        return None
    try:
        return int(str(raw).strip())
    except ValueError:
        return None


def _clamp_percent(value: float) -> float:
    return max(0.0, min(100.0, value))


def _remaining_from_used_percent(used_percent: float) -> float:
    return _clamp_percent(100.0 - used_percent)


def parse_billing_credits(payload: dict[str, Any]) -> GrokUsageSnapshot:
    config = payload.get("config")
    if not isinstance(config, dict):
        return GrokUsageSnapshot(
            remaining_percent=None,
            remaining_usd=None,
            period_end=None,
            source="billing_credits",
            error="Réponse billing sans config.",
        )

    period_end: str | None = None
    current_period = config.get("currentPeriod")
    if isinstance(current_period, dict):
        end = current_period.get("end")
        if isinstance(end, str) and end.strip():
            period_end = end.strip()
    if not period_end:
        fallback_end = config.get("billingPeriodEnd")
        if isinstance(fallback_end, str) and fallback_end.strip():
            period_end = fallback_end.strip()

    credit_usage = config.get("creditUsagePercent")
    if isinstance(credit_usage, (int, float)):
        remaining_percent = _remaining_from_used_percent(float(credit_usage))
        prepaid_cents = _object_cents(config.get("prepaidBalance"))
        remaining_usd = (-prepaid_cents / 100.0) if prepaid_cents is not None else None
        return GrokUsageSnapshot(
            remaining_percent=remaining_percent,
            remaining_usd=remaining_usd,
            period_end=period_end,
            source="billing_credits",
        )

    used_cents = _object_cents(config.get("used"))
    limit_cents = _object_cents(config.get("monthlyLimit"))
    if used_cents is not None and limit_cents and limit_cents > 0:
        used_pct = (used_cents / limit_cents) * 100.0
        return GrokUsageSnapshot(
            remaining_percent=_remaining_from_used_percent(used_pct),
            remaining_usd=None,
            period_end=period_end,
            source="billing_credits_legacy",
        )

    prepaid_cents = _object_cents(config.get("prepaidBalance"))
    if prepaid_cents is not None:
        remaining_usd = max(0.0, -prepaid_cents / 100.0)
        return GrokUsageSnapshot(
            remaining_percent=None,
            remaining_usd=remaining_usd,
            period_end=period_end,
            source="billing_credits_prepaid",
        )

    return GrokUsageSnapshot(
        remaining_percent=None,
        remaining_usd=None,
        period_end=period_end,
        source="billing_credits",
        error="Champs quota absents de la réponse billing.",
    )


def parse_prepaid_balance(payload: dict[str, Any]) -> GrokUsageSnapshot:
    total_cents = _object_cents(payload.get("total"))
    if total_cents is None:
        return GrokUsageSnapshot(
            remaining_percent=None,
            remaining_usd=None,
            period_end=None,
            source="management_prepaid",
            error="Solde prepaid illisible.",
        )

    remaining_usd = max(0.0, -total_cents / 100.0)
    purchase_total_cents = 0
    changes = payload.get("changes")
    if isinstance(changes, list):
        for change in changes:
            if not isinstance(change, dict):
                continue
            if str(change.get("changeOrigin") or "").upper() != "PURCHASE":
                continue
            amount_cents = _object_cents(change.get("amount"))
            if amount_cents is not None and amount_cents < 0:
                purchase_total_cents += abs(amount_cents)

    remaining_percent: float | None = None
    if purchase_total_cents > 0:
        remaining_percent = _clamp_percent((remaining_usd / (purchase_total_cents / 100.0)) * 100.0)

    return GrokUsageSnapshot(
        remaining_percent=remaining_percent,
        remaining_usd=remaining_usd,
        period_end=None,
        source="management_prepaid",
    )


def _fetch_json(url: str, api_key: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        response = requests.get(
            url,
            headers=_auth_headers(api_key),
            timeout=_REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        return None, str(exc)

    if not response.ok:
        return None, f"HTTP {response.status_code}"

    try:
        data = response.json()
    except ValueError:
        return None, "JSON invalide"

    if not isinstance(data, dict):
        return None, "Réponse inattendue"
    return data, None


def _fetch_billing_credits(inference_key: str) -> GrokUsageSnapshot:
    data, error = _fetch_json(f"{XAI_API_BASE}/billing?format=credits", inference_key)
    if error or data is None:
        return GrokUsageSnapshot(
            remaining_percent=None,
            remaining_usd=None,
            period_end=None,
            source="billing_credits",
            error=error or "Billing indisponible",
        )
    snapshot = parse_billing_credits(data)
    if snapshot.error:
        return snapshot
    if snapshot.remaining_percent is not None or snapshot.remaining_usd is not None:
        return snapshot
    return GrokUsageSnapshot(
        remaining_percent=None,
        remaining_usd=None,
        period_end=snapshot.period_end,
        source=snapshot.source,
        error=snapshot.error or "Quota non disponible via billing.",
    )


def _extract_team_id(payload: dict[str, Any]) -> str | None:
    for key in ("teamId", "team_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def parse_management_key_validation(payload: dict[str, Any]) -> str | None:
    scope = str(payload.get("scope") or "").upper()
    if scope == "SCOPE_TEAM":
        scope_id = payload.get("scopeId")
        if isinstance(scope_id, str) and scope_id.strip():
            return scope_id.strip()
    return _extract_team_id(payload)


def _fetch_team_id_from_management(management_key: str) -> tuple[str | None, str | None]:
    data, error = _fetch_json(
        f"{XAI_MGMT_AUTH_BASE}/auth/management-keys/validation",
        management_key,
    )
    if error or data is None:
        return None, error
    team_id = parse_management_key_validation(data)
    if team_id:
        return team_id, None
    return None, "team_id absent (validation management)"


def _fetch_team_id_from_inference(inference_key: str) -> tuple[str | None, str | None]:
    for path in ("/me", "/api-key"):
        data, error = _fetch_json(f"{XAI_API_BASE}{path}", inference_key)
        if error or data is None:
            continue
        team_id = _extract_team_id(data)
        if team_id:
            return team_id, None
    return None, "team_id absent"


def _resolve_team_id(management_key: str, inference_key: str) -> tuple[str | None, str | None]:
    env_team_id = grok_team_id()
    if env_team_id:
        return env_team_id, None

    if management_key:
        team_id, error = _fetch_team_id_from_management(management_key)
        if team_id:
            return team_id, None
        management_error = error
    else:
        management_error = None

    team_id, inference_error = _fetch_team_id_from_inference(inference_key)
    if team_id:
        return team_id, None

    errors = [err for err in (management_error, inference_error) if err]
    return None, "; ".join(errors) if errors else "team_id introuvable"


def _fetch_management_prepaid(management_key: str, inference_key: str) -> GrokUsageSnapshot:
    team_id, team_error = _resolve_team_id(management_key, inference_key)
    if not team_id:
        return GrokUsageSnapshot(
            remaining_percent=None,
            remaining_usd=None,
            period_end=None,
            source="management_prepaid",
            error=team_error or "team_id introuvable",
        )

    url = f"{XAI_MGMT_BASE}/billing/teams/{team_id}/prepaid/balance"
    data, error = _fetch_json(url, management_key)
    if error or data is None:
        return GrokUsageSnapshot(
            remaining_percent=None,
            remaining_usd=None,
            period_end=None,
            source="management_prepaid",
            error=error or "Management billing indisponible",
        )
    return parse_prepaid_balance(data)


def fetch_grok_usage() -> GrokUsageSnapshot:
    inference_key = grok_api_key()
    billing = _fetch_billing_credits(inference_key)
    if billing.remaining_percent is not None or billing.remaining_usd is not None:
        return billing

    management_key = grok_management_key()
    if not management_key:
        return billing

    prepaid = _fetch_management_prepaid(management_key, inference_key)
    if prepaid.remaining_percent is not None or prepaid.remaining_usd is not None:
        return prepaid

    if billing.error and prepaid.error:
        return GrokUsageSnapshot(
            remaining_percent=None,
            remaining_usd=None,
            period_end=None,
            source="unavailable",
            error=f"{billing.error}; {prepaid.error}",
        )
    return prepaid if prepaid.error else billing


def format_usage_label(snapshot: GrokUsageSnapshot) -> str:
    if snapshot.remaining_percent is not None:
        rounded = int(snapshot.remaining_percent) if snapshot.remaining_percent.is_integer() else round(
            snapshot.remaining_percent, 1
        )
        return f"Grok · {rounded}% restant"
    if snapshot.remaining_usd is not None:
        return f"Grok · ${snapshot.remaining_usd:.2f} restants"
    if snapshot.error:
        return "Grok · quota indisponible"
    return "Grok · quota indisponible"


def usage_severity(snapshot: GrokUsageSnapshot) -> Literal["ok", "warn", "critical"]:
    if snapshot.remaining_percent is not None:
        if snapshot.remaining_percent <= 0:
            return "critical"
        if snapshot.remaining_percent < 15:
            return "warn"
        return "ok"
    if snapshot.remaining_usd is not None:
        if snapshot.remaining_usd <= 0:
            return "critical"
        return "ok"
    return "warn"
