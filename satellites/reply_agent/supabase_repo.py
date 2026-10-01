"""Supabase access for AI Reply Agent Streamlit tool."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from supabase import Client, create_client

from config import supabase_service_role_key, supabase_url


@lru_cache(maxsize=1)
def get_client() -> Client:
    url = supabase_url()
    key = supabase_service_role_key()
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    return create_client(url, key)


OUTREACH_CAMPAIGNS_TABLE = "outreach_campaigns"
APP_SETTINGS_TABLE = "app_settings"
AI_REPLY_SETTINGS_KEY = "ai_reply_agent"


def _legacy_reply_config(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "campaign_id": row.get("campaign_id"),
        "campaign_name": row.get("campaign_name"),
        "niche_preset_id": row.get("niche_preset_id"),
        "niche_metadata": row.get("niche_metadata") or {},
        "target_type": row.get("target_type"),
        "prompt_key": row.get("prompt_key"),
        "prompt_snapshot": row.get("prompt_snapshot") or "",
        "webhook_id": row.get("reply_webhook_id"),
        "ooo_webhook_id": row.get("ooo_webhook_id"),
        "max_sentences": row.get("reply_max_sentences"),
        "status": row.get("reply_status"),
        "initialized_at": row.get("reply_initialized_at"),
        "updated_at": row.get("updated_at"),
    }


def _outreach_reply_patch(row: dict[str, Any]) -> dict[str, Any]:
    patch: dict[str, Any] = {
        "campaign_id": row.get("campaign_id"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    for src, dest in (
        ("campaign_name", "campaign_name"),
        ("niche_preset_id", "niche_preset_id"),
        ("niche_metadata", "niche_metadata"),
        ("target_type", "target_type"),
        ("prompt_key", "prompt_key"),
        ("prompt_snapshot", "prompt_snapshot"),
        ("webhook_id", "reply_webhook_id"),
        ("ooo_webhook_id", "ooo_webhook_id"),
        ("max_sentences", "reply_max_sentences"),
        ("status", "reply_status"),
        ("initialized_at", "reply_initialized_at"),
    ):
        if src in row:
            patch[dest] = row.get(src)
    return patch


def get_global_auto_send_enabled() -> bool:
    resp = (
        get_client()
        .table(APP_SETTINGS_TABLE)
        .select("value")
        .eq("key", AI_REPLY_SETTINGS_KEY)
        .maybe_single()
        .execute()
    )
    if not resp or not resp.data:
        return True
    value = resp.data.get("value") or {}
    if isinstance(value, dict):
        return bool(value.get("webhook_auto_send_enabled", True))
    return True


def set_global_auto_send_enabled(enabled: bool) -> None:
    now = datetime.now(timezone.utc).isoformat()
    client = get_client()
    existing = (
        client.table(APP_SETTINGS_TABLE)
        .select("value")
        .eq("key", AI_REPLY_SETTINGS_KEY)
        .maybe_single()
        .execute()
    )
    value = dict((existing.data or {}).get("value") or {})
    value["webhook_auto_send_enabled"] = enabled
    client.table(APP_SETTINGS_TABLE).upsert(
        {"key": AI_REPLY_SETTINGS_KEY, "value": value, "updated_at": now},
        on_conflict="key",
    ).execute()


def list_reply_configs(
    *,
    statuses: tuple[str, ...] = ("waiting_for_replies", "paused"),
) -> list[dict[str, Any]]:
    """Reply-agent rows from outreach_campaigns (legacy-shaped dicts)."""
    resp = (
        get_client()
        .table(OUTREACH_CAMPAIGNS_TABLE)
        .select("*")
        .in_("reply_status", list(statuses))
        .execute()
    )
    rows: list[dict[str, Any]] = []
    for raw in resp.data or []:
        if not isinstance(raw, dict):
            continue
        if not str(raw.get("niche_preset_id") or "").strip():
            continue
        rows.append(_legacy_reply_config(raw))
    return rows


def get_config(campaign_id: str) -> dict[str, Any] | None:
    resp = (
        get_client()
        .table(OUTREACH_CAMPAIGNS_TABLE)
        .select("*")
        .eq("campaign_id", campaign_id)
        .maybe_single()
        .execute()
    )
    if not resp or not resp.data or not isinstance(resp.data, dict):
        return None
    return _legacy_reply_config(resp.data)


def save_config(row: dict[str, Any]) -> None:
    payload = _outreach_reply_patch(dict(row))
    get_client().table(OUTREACH_CAMPAIGNS_TABLE).upsert(
        payload, on_conflict="campaign_id"
    ).execute()


def list_inbound_messages(campaign_id: str, limit: int = 200) -> list[dict[str, Any]]:
    resp = (
        get_client()
        .table("ai_reply_agent_messages")
        .select("*")
        .eq("campaign_id", campaign_id)
        .eq("direction", "inbound")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return resp.data or []


_PROBLEM_STATUSES = (
    "failed",
    "skipped_unsafe",
    "skipped_recovery",
    "skipped_ooo",
    "pending",
)
_PROBLEM_SEVERITY = {
    "failed": 0,
    "pending": 1,
    "skipped_recovery": 2,
    "skipped_unsafe": 3,
    "skipped_ooo": 4,
}


def _is_stale_pending(row: dict[str, Any], stale_hours: int = 24) -> bool:
    if str(row.get("ai_status") or "") != "pending":
        return False
    created = str(row.get("created_at") or "").strip()
    if not created:
        return False
    if created.endswith("Z"):
        created = f"{created[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(created)
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return datetime.now(timezone.utc) - parsed >= timedelta(hours=stale_hours)


def list_problem_messages(campaign_id: str, limit: int = 200) -> list[dict[str, Any]]:
    """Inbound rows needing ops attention: failures, stale drafts, abstentions, OOO."""
    resp = (
        get_client()
        .table("ai_reply_agent_messages")
        .select("*")
        .eq("campaign_id", campaign_id)
        .eq("direction", "inbound")
        .in_("ai_status", list(_PROBLEM_STATUSES))
        .order("created_at", desc=True)
        .limit(limit * 2)
        .execute()
    )
    rows = resp.data or []
    filtered = [
        row
        for row in rows
        if str(row.get("ai_status") or "") != "pending"
        or _is_stale_pending(row)
    ]
    filtered.sort(
        key=lambda row: (
            _PROBLEM_SEVERITY.get(str(row.get("ai_status") or ""), 9),
            str(row.get("created_at") or ""),
        ),
        reverse=True,
    )
    return filtered[:limit]


def list_thread_messages(
    campaign_id: str, lead_email: str
) -> list[dict[str, Any]]:
    resp = (
        get_client()
        .table("ai_reply_agent_messages")
        .select("*")
        .eq("campaign_id", campaign_id)
        .eq("lead_email", lead_email.lower())
        .order("created_at", desc=False)
        .execute()
    )
    return resp.data or []


def update_message_status(
    message_id: str,
    ai_status: str,
    ai_reason: str | None = None,
    *,
    groq_model: str | None = None,
    recovery_confidence: int | None = None,
    groq_cost_usd_ticks: int | None = None,
) -> None:
    patch: dict[str, Any] = {
        "ai_status": ai_status,
        "ai_reason": ai_reason,
    }
    if groq_model is not None:
        patch["groq_model"] = groq_model
    if recovery_confidence is not None:
        patch["recovery_confidence"] = max(0, min(100, int(recovery_confidence)))
    if groq_cost_usd_ticks is not None:
        patch["groq_cost_usd_ticks"] = groq_cost_usd_ticks
    get_client().table("ai_reply_agent_messages").update(patch).eq("id", message_id).execute()


def insert_outbound_message(row: dict[str, Any]) -> None:
    get_client().table("ai_reply_agent_messages").insert(row).execute()


def queue_manual_job(
    *,
    campaign_id: str,
    lead_email: str,
    message_id: str,
    scheduled_for: str,
    payload: dict[str, Any],
) -> None:
    idempotency_key = f"manual:{message_id}:{scheduled_for}"
    get_client().table("ai_reply_agent_jobs").insert(
        {
            "idempotency_key": idempotency_key,
            "campaign_id": campaign_id,
            "lead_email": lead_email.lower(),
            "message_id": message_id,
            "scheduled_for": scheduled_for,
            "status": "pending",
            "payload": payload,
        }
    ).execute()


def list_client_emails() -> set[str]:
    resp = get_client().table("clients").select("email").execute()
    rows = resp.data or []
    return {
        str(row.get("email") or "").strip().lower()
        for row in rows
        if row.get("email")
    }


def list_blocklist(campaign_id: str) -> set[str]:
    resp = (
        get_client()
        .table("ai_reply_agent_blocklist")
        .select("lead_email")
        .eq("campaign_id", campaign_id)
        .execute()
    )
    rows = resp.data or []
    return {str(row.get("lead_email") or "").strip().lower() for row in rows if row.get("lead_email")}


def add_to_blocklist(
    campaign_id: str,
    lead_email: str,
    *,
    reason: str = "dismissed",
) -> None:
    get_client().table("ai_reply_agent_blocklist").upsert(
        {
            "campaign_id": campaign_id,
            "lead_email": lead_email.strip().lower(),
            "reason": reason,
            "blocked_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="campaign_id,lead_email",
    ).execute()


def is_blocklisted(campaign_id: str, lead_email: str) -> bool:
    resp = (
        get_client()
        .table("ai_reply_agent_blocklist")
        .select("id")
        .eq("campaign_id", campaign_id)
        .eq("lead_email", lead_email.strip().lower())
        .maybe_single()
        .execute()
    )
    return bool(resp and resp.data)


def get_lead_reply(campaign_id: str, lead_email: str) -> str:
    resp = (
        get_client()
        .table("ai_reply_agent_leads")
        .select("ai_reply_agent_1")
        .eq("campaign_id", campaign_id)
        .eq("lead_email", lead_email.strip().lower())
        .maybe_single()
        .execute()
    )
    if not resp or not resp.data:
        return ""
    text = resp.data.get("ai_reply_agent_1")
    return str(text).strip() if text else ""


def upsert_lead_reply(campaign_id: str, lead_email: str, reply_text: str) -> None:
    normalized = lead_email.strip().lower()
    trimmed = (reply_text or "").strip()
    if not trimmed:
        raise ValueError("reply_text must be non-empty")
    get_client().table("ai_reply_agent_leads").upsert(
        {
            "campaign_id": campaign_id,
            "lead_email": normalized,
            "ai_reply_agent_1": trimmed,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="campaign_id,lead_email",
    ).execute()


def get_lead_replies_batch(
    campaign_id: str,
    lead_emails: list[str],
) -> dict[str, str]:
    normalized = sorted({email.strip().lower() for email in lead_emails if email.strip()})
    if not normalized:
        return {}
    resp = (
        get_client()
        .table("ai_reply_agent_leads")
        .select("lead_email, ai_reply_agent_1")
        .eq("campaign_id", campaign_id)
        .in_("lead_email", normalized)
        .execute()
    )
    result: dict[str, str] = {}
    for row in resp.data or []:
        email = str(row.get("lead_email") or "").strip().lower()
        text = row.get("ai_reply_agent_1")
        if email and text and str(text).strip():
            result[email] = str(text).strip()
    return result


def insert_inbound_message(row: dict[str, Any]) -> str:
    client = get_client()
    campaign_id = str(row.get("campaign_id") or "")
    lead_email = str(row.get("lead_email") or "").lower()
    instantly_email_id = row.get("instantly_email_id")

    if instantly_email_id:
        existing = (
            client.table("ai_reply_agent_messages")
            .select("id")
            .eq("campaign_id", campaign_id)
            .eq("lead_email", lead_email)
            .eq("instantly_email_id", instantly_email_id)
            .maybe_single()
            .execute()
        )
        if existing and existing.data:
            return str(existing.data["id"])

    resp = client.table("ai_reply_agent_messages").insert(row).select("id").execute()
    if not resp or not resp.data:
        raise RuntimeError("Failed to insert inbound message")
    inserted = resp.data[0] if isinstance(resp.data, list) else resp.data
    return str(inserted["id"])
