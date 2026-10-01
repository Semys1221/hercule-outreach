"""Supabase access for Instantly bypass Streamlit tool."""

from __future__ import annotations

from functools import lru_cache
from typing import Any
from datetime import datetime, timezone

from supabase import Client, create_client

from config import supabase_service_role_key, supabase_url
from default_templates import DEFAULT_E1_BODY_HTML


@lru_cache(maxsize=1)
def get_client() -> Client:
    url = supabase_url()
    key = supabase_service_role_key()
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    return create_client(url, key)


INTERESTED_TEMPLATE_KEYS = (
    "interested_email1",
    "interested_email2",
    "interested_email3",
)

BIGGY_TEMPLATE_SOURCE = "2cd03978-93b3-4462-ad88-f0fb0f35d59c"
CLONE_TEMPLATE_KEYS = (
    "interested_email1",
    "interested_email2",
    "interested_email3",
    "no_show_email1",
    "no_show_email2",
)


def clone_templates(
    source_campaign_id: str,
    target_campaign_id: str,
    *,
    keys: tuple[str, ...] = CLONE_TEMPLATE_KEYS,
    overwrite_blank_only: bool = True,
) -> list[str]:
    """Copy subject + body_html per template_key from source to target campaign."""
    source_rows = {
        str(row.get("template_key") or ""): row
        for row in list_templates(source_campaign_id)
    }
    target_rows = {
        str(row.get("template_key") or ""): row
        for row in list_templates(target_campaign_id)
    }
    client = get_client()
    cloned: list[str] = []
    now = datetime.now(timezone.utc).isoformat()

    for key in keys:
        source = source_rows.get(key)
        if not source:
            continue
        subject = str(source.get("subject") or "")
        body_html = str(source.get("body_html") or "")
        if not body_html.strip():
            continue

        if overwrite_blank_only:
            existing = target_rows.get(key)
            if existing and str(existing.get("body_html") or "").strip():
                continue

        client.table("instantly_bypass_templates").upsert(
            {
                "campaign_id": target_campaign_id,
                "template_key": key,
                "subject": subject,
                "body_html": body_html,
                "updated_at": now,
            },
            on_conflict="campaign_id,template_key",
        ).execute()
        cloned.append(key)

    return cloned


def list_templates(campaign_id: str) -> list[dict[str, Any]]:
    resp = (
        get_client()
        .table("instantly_bypass_templates")
        .select("campaign_id, template_key, subject, body_html, updated_at")
        .eq("campaign_id", campaign_id)
        .order("template_key")
        .execute()
    )
    return resp.data or []


def save_template(
    campaign_id: str,
    template_key: str,
    subject: str,
    body_html: str,
    *,
    sync_bootstrap_default: bool = False,
) -> dict[str, Any]:
    get_client().table("instantly_bypass_templates").upsert(
        {
            "campaign_id": campaign_id,
            "template_key": template_key,
            "subject": subject,
            "body_html": body_html,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="campaign_id,template_key",
    ).execute()

    code_sync: dict[str, Any] = {"default_templates": False, "errors": []}
    if sync_bootstrap_default and template_key == "interested_email1":
        try:
            from template_code_sync import sync_e1_bootstrap_default

            sync_e1_bootstrap_default(body_html)
            code_sync["default_templates"] = True
        except Exception as exc:
            code_sync["errors"].append(str(exc))

    return {
        "db": True,
        "template_key": template_key,
        "code_sync": code_sync,
    }


def seed_empty_templates(
    campaign_id: str,
    keys: tuple[str, ...] = INTERESTED_TEMPLATE_KEYS,
) -> None:
    existing = {str(row.get("template_key") or "") for row in list_templates(campaign_id)}
    client = get_client()
    for key in keys:
        if key in existing:
            continue
        body_html = DEFAULT_E1_BODY_HTML if key == "interested_email1" else ""
        client.table("instantly_bypass_templates").insert(
            {
                "campaign_id": campaign_id,
                "template_key": key,
                "subject": "",
                "body_html": body_html,
            }
        ).execute()


OUTREACH_CAMPAIGNS_TABLE = "outreach_campaigns"


def _legacy_bypass_config(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "campaign_id": row.get("campaign_id"),
        "campaign_name": row.get("campaign_name"),
        "interested_subsequence_id": row.get("interested_subsequence_id"),
        "no_reply_subsequence_id": row.get("no_reply_subsequence_id"),
        "waiting_for_reply_interest_value": row.get("waiting_for_reply_interest_value"),
        "webhook_id": row.get("bypass_webhook_id"),
        "webhook_auto_send_enabled": row.get("bypass_webhook_auto_send_enabled", True),
        "pipeline_auto_advance_enabled": row.get("bypass_pipeline_auto_advance_enabled"),
        "initialized_at": row.get("bypass_initialized_at"),
        "e1_webhook_delay_ms": row.get("bypass_e1_webhook_delay_ms"),
        "updated_at": row.get("updated_at"),
    }


def _outreach_bypass_patch(row: dict[str, Any]) -> dict[str, Any]:
    patch: dict[str, Any] = {
        "campaign_id": row.get("campaign_id"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if "campaign_name" in row:
        patch["campaign_name"] = row.get("campaign_name")
    if "interested_subsequence_id" in row:
        patch["interested_subsequence_id"] = row.get("interested_subsequence_id")
    if "no_reply_subsequence_id" in row:
        patch["no_reply_subsequence_id"] = row.get("no_reply_subsequence_id")
    if "waiting_for_reply_interest_value" in row:
        patch["waiting_for_reply_interest_value"] = row.get(
            "waiting_for_reply_interest_value"
        )
    if "webhook_id" in row:
        patch["bypass_webhook_id"] = row.get("webhook_id")
    if "webhook_auto_send_enabled" in row:
        patch["bypass_webhook_auto_send_enabled"] = row.get("webhook_auto_send_enabled")
    if "pipeline_auto_advance_enabled" in row:
        patch["bypass_pipeline_auto_advance_enabled"] = row.get(
            "pipeline_auto_advance_enabled"
        )
    if "initialized_at" in row:
        patch["bypass_initialized_at"] = row.get("initialized_at")
    if "e1_webhook_delay_ms" in row:
        patch["bypass_e1_webhook_delay_ms"] = row.get("e1_webhook_delay_ms")
    return patch


def list_configs() -> list[dict[str, Any]]:
    resp = (
        get_client()
        .table(OUTREACH_CAMPAIGNS_TABLE)
        .select("*")
        .order("campaign_name")
        .execute()
    )
    return [_legacy_bypass_config(row) for row in (resp.data or [])]


def get_config(campaign_id: str) -> dict[str, Any] | None:
    resp = (
        get_client()
        .table(OUTREACH_CAMPAIGNS_TABLE)
        .select("*")
        .eq("campaign_id", campaign_id)
        .maybe_single()
        .execute()
    )
    if not resp or not resp.data:
        return None
    return _legacy_bypass_config(resp.data)


def save_config(row: dict[str, Any]) -> None:
    payload = _outreach_bypass_patch(row)
    get_client().table(OUTREACH_CAMPAIGNS_TABLE).upsert(
        payload,
        on_conflict="campaign_id",
    ).execute()


def sync_webhook_id(campaign_id: str, webhook_id: str) -> None:
    save_config(
        {
            "campaign_id": campaign_id,
            "webhook_id": webhook_id,
        }
    )


def set_campaign_webhook_auto_send_enabled(campaign_id: str, enabled: bool) -> None:
    save_config(
        {
            "campaign_id": campaign_id,
            "webhook_auto_send_enabled": enabled,
        }
    )


def set_campaign_pipeline_auto_advance_enabled(campaign_id: str, enabled: bool) -> None:
    save_config(
        {
            "campaign_id": campaign_id,
            "pipeline_auto_advance_enabled": enabled,
        }
    )


def has_sent_event(idempotency_key: str) -> bool:
    resp = (
        get_client()
        .table("instantly_bypass_events")
        .select("id")
        .eq("idempotency_key", idempotency_key)
        .eq("status", "sent")
        .maybe_single()
        .execute()
    )
    return bool(resp and resp.data)


def record_event(row: dict[str, Any]) -> None:
    get_client().table("instantly_bypass_events").upsert(
        row,
        on_conflict="idempotency_key",
    ).execute()


def get_last_send_at(campaign_id: str, lead_email: str) -> str | None:
    resp = (
        get_client()
        .table("instantly_bypass_events")
        .select("dispatched_at")
        .eq("campaign_id", campaign_id)
        .eq("lead_email", lead_email.strip().lower())
        .eq("status", "sent")
        .order("dispatched_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if not rows:
        return None
    return rows[0].get("dispatched_at")


def list_sent_flows(campaign_id: str, lead_email: str) -> list[str]:
    resp = (
        get_client()
        .table("instantly_bypass_events")
        .select("flow")
        .eq("campaign_id", campaign_id)
        .eq("lead_email", lead_email.strip().lower())
        .eq("status", "sent")
        .execute()
    )
    return [str(row["flow"]) for row in (resp.data or []) if row.get("flow")]


def get_event_sent_at(campaign_id: str, lead_email: str, flow: str) -> str | None:
    resp = (
        get_client()
        .table("instantly_bypass_events")
        .select("dispatched_at")
        .eq("campaign_id", campaign_id)
        .eq("lead_email", lead_email.strip().lower())
        .eq("flow", flow)
        .eq("status", "sent")
        .maybe_single()
        .execute()
    )
    if not resp or not resp.data:
        return None
    return resp.data.get("dispatched_at")


def get_webhook_auto_send_enabled() -> bool:
    resp = (
        get_client()
        .table("app_settings")
        .select("value")
        .eq("key", "instantly_bypass")
        .maybe_single()
        .execute()
    )
    if not resp or not resp.data:
        return False
    value = resp.data.get("value") or {}
    if isinstance(value, dict):
        return bool(value.get("webhook_auto_send_enabled", False))
    return False


def set_webhook_auto_send_enabled(enabled: bool) -> None:
    now = datetime.now(timezone.utc).isoformat()
    client = get_client()
    existing = (
        client.table("app_settings")
        .select("value")
        .eq("key", "instantly_bypass")
        .maybe_single()
        .execute()
    )
    value = dict((existing.data or {}).get("value") or {})
    value["webhook_auto_send_enabled"] = enabled
    client.table("app_settings").upsert(
        {"key": "instantly_bypass", "value": value, "updated_at": now},
        on_conflict="key",
    ).execute()


def get_pipeline_step(campaign_id: str, lead_email: str) -> str | None:
    resp = (
        get_client()
        .table("instantly_bypass_pipeline")
        .select("step")
        .eq("campaign_id", campaign_id)
        .eq("lead_email", lead_email.strip().lower())
        .maybe_single()
        .execute()
    )
    if not resp or not resp.data:
        return None
    step = resp.data.get("step")
    return str(step) if step else None


def upsert_pipeline_step(campaign_id: str, lead_email: str, step: str) -> None:
    get_client().table("instantly_bypass_pipeline").upsert(
        {
            "campaign_id": campaign_id,
            "lead_email": lead_email.strip().lower(),
            "step": step,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="campaign_id,lead_email",
    ).execute()


def list_pipeline_for_campaign(campaign_id: str) -> list[dict[str, Any]]:
    resp = (
        get_client()
        .table("instantly_bypass_pipeline")
        .select("campaign_id, lead_email, step, updated_at")
        .eq("campaign_id", campaign_id)
        .execute()
    )
    return resp.data or []


def has_pending_job(idempotency_key: str) -> bool:
    resp = (
        get_client()
        .table("instantly_bypass_jobs")
        .select("id")
        .eq("idempotency_key", idempotency_key)
        .eq("status", "pending")
        .maybe_single()
        .execute()
    )
    return bool(resp and resp.data)


def insert_bypass_job(
    *,
    idempotency_key: str,
    campaign_id: str,
    lead_email: str,
    flow: str,
    scheduled_for: datetime,
    payload: dict[str, Any],
) -> None:
    get_client().table("instantly_bypass_jobs").upsert(
        {
            "idempotency_key": idempotency_key,
            "campaign_id": campaign_id,
            "lead_email": lead_email.strip().lower(),
            "template_key": flow,
            "scheduled_for": scheduled_for.astimezone(timezone.utc).isoformat(),
            "status": "pending",
            "payload": payload,
        },
        on_conflict="idempotency_key",
    ).execute()


def list_due_bypass_jobs(limit: int = 50) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    resp = (
        get_client()
        .table("instantly_bypass_jobs")
        .select("*")
        .eq("status", "pending")
        .lte("scheduled_for", now)
        .order("scheduled_for")
        .limit(limit)
        .execute()
    )
    return resp.data or []


def mark_bypass_job_sent(job_id: str) -> None:
    get_client().table("instantly_bypass_jobs").update(
        {
            "status": "sent",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", job_id).eq("status", "pending").execute()


def mark_bypass_job_failed(job_id: str, error_message: str) -> None:
    get_client().table("instantly_bypass_jobs").update(
        {
            "status": "failed",
            "error_message": error_message[:2000],
        }
    ).eq("id", job_id).eq("status", "pending").execute()


def reschedule_bypass_job(job_id: str, scheduled_for: datetime) -> None:
    get_client().table("instantly_bypass_jobs").update(
        {
            "scheduled_for": scheduled_for.astimezone(timezone.utc).isoformat(),
        }
    ).eq("id", job_id).eq("status", "pending").execute()


def fetch_analytics(campaign_id: str | None = None) -> dict[str, Any]:
    client = get_client()
    sent_q = (
        client.table("instantly_bypass_events")
        .select("latency_ms")
        .eq("status", "sent")
    )
    failed_q = (
        client.table("instantly_bypass_events")
        .select("id", count="exact")
        .eq("status", "failed")
    )
    errors_q = (
        client.table("instantly_bypass_events")
        .select("lead_email, campaign_id, error_message, created_at")
        .eq("status", "failed")
        .order("created_at", desc=True)
        .limit(20)
    )
    if campaign_id:
        sent_q = sent_q.eq("campaign_id", campaign_id)
        failed_q = failed_q.eq("campaign_id", campaign_id)
        errors_q = errors_q.eq("campaign_id", campaign_id)
    sent = sent_q.execute()
    rows = sent.data or []
    latencies = [r["latency_ms"] for r in rows if isinstance(r.get("latency_ms"), int)]
    failed = failed_q.execute()
    errors = errors_q.execute()
    return {
        "total_sent": len(rows),
        "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
        "failed_count": failed.count or 0,
        "recent_errors": errors.data or [],
    }
