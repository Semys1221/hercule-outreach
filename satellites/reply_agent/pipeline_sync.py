"""Sync instantly_bypass_pipeline step from sent event flows."""

from __future__ import annotations

from datetime import datetime, timezone

from supabase_repo import get_client

PipelineStep = str


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


def derive_step_from_flows(flows: set[str]) -> PipelineStep:
    if "interested_email3" in flows or "no_show_email2" in flows:
        return "step_3"
    if "interested_email2" in flows:
        return "step_2"
    if "interested_email1" in flows or "no_show_email1" in flows:
        return "step_1"
    return "step_0"


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
    return str(resp.data.get("step") or "") or None


def _upsert_pipeline_step(campaign_id: str, lead_email: str, step: str) -> None:
    get_client().table("instantly_bypass_pipeline").upsert(
        {
            "campaign_id": campaign_id,
            "lead_email": lead_email.strip().lower(),
            "step": step,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="campaign_id,lead_email",
    ).execute()


def sync_pipeline_step_from_sent_flows(campaign_id: str, lead_email: str) -> str:
    current = get_pipeline_step(campaign_id, lead_email)
    if current in ("step_4", "replies_to_handle"):
        return current or "step_0"
    flows = set(list_sent_flows(campaign_id, lead_email))
    step = derive_step_from_flows(flows)
    _upsert_pipeline_step(campaign_id, lead_email, step)
    return step
