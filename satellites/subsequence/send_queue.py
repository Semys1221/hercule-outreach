"""Dashboard send queues — CRM pipeline fetch, Unibox reply sends."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Literal
from zoneinfo import ZoneInfo

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from outreach_preset_ops import is_campaign_outreach_allowed, outreach_blocked_result

from shared.instantly_client import (
    FILTER_LEAD_INTERESTED,
    InstantlyClient,
    get_api_key,
    lead_custom_var,
)

from supabase_repo import (
    get_last_send_at,
    has_pending_job,
    has_sent_event,
    insert_bypass_job,
    list_pipeline_for_campaign,
    list_sent_flows,
    list_templates,
    record_event,
    upsert_pipeline_step,
)
from config import send_window_tz
from reply_subject import resolve_bypass_reply_subject
from send_window import format_paris_slot, is_within_send_window, next_send_slot
from unibox_classify import (
    email_timestamp,
    extract_email_text,
    is_hercule_email,
    match_flows,
)

PipelineStep = Literal["step_0", "step_1", "step_2", "step_3", "step_4", "replies_to_handle"]
Flow = Literal["interested_email1", "interested_email2", "interested_email3"]

INTERESTED_STATUS = 1
NO_SHOW_STATUS = -4
NOT_INTERESTED_STATUS = -1
EMAIL_SEND_DELAY_S = 3.2

PIPELINE_STEPS: list[PipelineStep] = [
    "step_0",
    "step_1",
    "step_2",
    "step_3",
    "step_4",
    "replies_to_handle",
]

REPLY_MOVE_STEPS: set[PipelineStep] = {"step_1", "step_2", "step_3"}

STEP_AFTER_FLOW: dict[Flow, PipelineStep] = {
    "interested_email1": "step_1",
    "interested_email2": "step_2",
    "interested_email3": "step_3",
}

DEFAULT_FLOW_BY_STEP: dict[PipelineStep, Flow | None] = {
    "step_0": "interested_email1",
    "step_1": "interested_email2",
    "step_2": "interested_email3",
    "step_3": None,
    "step_4": None,
    "replies_to_handle": None,
}

SENDABLE_FLOWS: list[Flow] = [
    "interested_email1",
    "interested_email2",
    "interested_email3",
]

EMAIL_SIGNATURE = (
    "Béatrice Meyer<br/>hercule.dev Courtage contrat BNC/BIC<br/>"
    '<a href="https://hercule.dev">hercule.dev</a>'
)
RESERVATION_LINK_PLACEHOLDER = "{{reservation_link}}"
RESERVATION_AGENCE_PLACEHOLDER = "{{reservation_agence_link}}"
RESERVATION_ENTREPRISE_PLACEHOLDER = "{{reservation_entreprise_link}}"
RESERVATION_CIF_PLACEHOLDER = "{{reservation_cif_link}}"
RESERVATION_COMPTABLE_PLACEHOLDER = "{{reservation_comptable_link}}"
RESERVATION_JUM_PLACEHOLDER = "{{reservation_jum_link}}"
RESERVATION_CARTE_T_PLACEHOLDER = "{{reservation_carte_t_link}}"
SLOT_PLACEHOLDERS = ("{{slot_1}}", "{{slot_2}}")

KNOWN_CAMPAIGN_CALENDLY_EVENT: dict[str, str] = {
    "5591a068-75f9-4826-8564-4dc2acc74bd4": "comptable",
    "e3bdb573-fe9f-437d-bd96-4ceb52869dd4": "cif",
    "8c3aee0c-5eeb-4c5c-9a6a-a9c79b4b936c": "entreprise",
    "93c2e56f-4088-4495-94da-7891153e3947": "agence",
}


def template_requires_reservation_link(body_html: str) -> bool:
    text = body_html or ""
    if RESERVATION_LINK_PLACEHOLDER in text:
        return True
    return (
        RESERVATION_AGENCE_PLACEHOLDER in text
        or RESERVATION_ENTREPRISE_PLACEHOLDER in text
        or RESERVATION_CIF_PLACEHOLDER in text
        or RESERVATION_COMPTABLE_PLACEHOLDER in text
        or RESERVATION_JUM_PLACEHOLDER in text
        or RESERVATION_CARTE_T_PLACEHOLDER in text
        or "{{conference_link}}" in text
    )


def campaign_requires_reservation_link(campaign_id: str) -> bool:
    for row in list_templates(campaign_id):
        if template_requires_reservation_link(str(row.get("body_html") or "")):
            return True
    return False

PREVIEW_LEAD: dict[str, Any] = {
    "first_name": "Jean",
    "last_name": "Dupont",
    "payload": {
        "reservation_link": "https://www.hercule.dev/reservation/preview",
    },
}


def idempotency_key(flow: str, campaign_id: str, lead_email: str) -> str:
    return f"{flow}:{campaign_id}:{lead_email.strip().lower()}"


def _pick_latest_email(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not items:
        return None

    def ts(item: dict[str, Any]) -> str:
        return str(item.get("timestamp_email") or item.get("timestamp_created") or "")

    return sorted(items, key=ts, reverse=True)[0]


def _pick_earliest_email(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not items:
        return None

    def ts(item: dict[str, Any]) -> str:
        return str(item.get("timestamp_email") or item.get("timestamp_created") or "")

    return sorted(items, key=ts)[0]


def _resolve_initial_eaccount(
    client: InstantlyClient,
    *,
    lead_email: str,
    campaign_id: str,
    fallback_eaccount: str | None = None,
) -> str | None:
    sent_items = client.list_emails(
        search=lead_email,
        campaign_id=campaign_id,
        email_type="sent",
        limit=50,
    )
    earliest = _pick_earliest_email(sent_items)
    if earliest and earliest.get("eaccount"):
        return str(earliest["eaccount"])
    if fallback_eaccount and fallback_eaccount.strip():
        return fallback_eaccount.strip()
    return None


def _resolve_reply_anchor(
    client: InstantlyClient,
    *,
    lead_email: str,
    campaign_id: str,
) -> dict[str, str] | None:
    for attempt in range(3):
        for email_type in ("received", "sent"):
            items = client.list_emails(
                search=lead_email,
                campaign_id=campaign_id,
                email_type=email_type,
                latest_of_thread=True,
                limit=10,
            )
            pick = _pick_latest_email(items)
            if pick and pick.get("id"):
                return {
                    "reply_to_uuid": str(pick["id"]),
                    "subject": str(pick.get("subject") or ""),
                }
        if attempt < 2:
            time.sleep(3)

    items = client.list_emails(search=lead_email, campaign_id=campaign_id, limit=5)
    pick = _pick_latest_email(items)
    if pick and pick.get("id"):
        return {
            "reply_to_uuid": str(pick["id"]),
            "subject": str(pick.get("subject") or ""),
        }
    return None


def resolve_thread(
    client: InstantlyClient,
    *,
    lead_email: str,
    campaign_id: str,
    fallback_eaccount: str | None = None,
) -> dict[str, str] | None:
    reply = _resolve_reply_anchor(
        client,
        lead_email=lead_email,
        campaign_id=campaign_id,
    )
    if not reply:
        return None

    eaccount = _resolve_initial_eaccount(
        client,
        lead_email=lead_email,
        campaign_id=campaign_id,
        fallback_eaccount=fallback_eaccount,
    )
    if not eaccount:
        return None

    return {
        "reply_to_uuid": reply["reply_to_uuid"],
        "eaccount": eaccount,
        "subject": reply["subject"],
    }


def lead_has_replied_since(
    client: InstantlyClient,
    lead_email: str,
    since_iso: str,
) -> bool:
    received = client.list_emails(
        search=lead_email,
        email_type="received",
        limit=20,
    )
    for item in received:
        ts = item.get("timestamp_email") or item.get("timestamp_created")
        if ts and str(ts) > since_iso:
            return True
    return False


def get_last_received_at(
    client: InstantlyClient,
    lead_email: str,
    campaign_id: str,
) -> str | None:
    items = client.list_emails(
        search=lead_email,
        campaign_id=campaign_id,
        email_type="received",
        latest_of_thread=True,
        limit=10,
    )
    if not isinstance(items, list) or not items:
        return None
    pick = _pick_latest_email(items)
    if not pick:
        return None
    ts = email_timestamp(pick)
    return ts or None


def _parse_iso_datetime(value: str) -> datetime | None:
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def is_awaiting_reply_over_24h(
    last_received_at: str | None,
    last_sent_at: str | None,
) -> bool:
    received_dt = _parse_iso_datetime(last_received_at or "")
    if received_dt is None:
        return False
    if datetime.now(timezone.utc) - received_dt < timedelta(hours=24):
        return False
    if not last_sent_at:
        return True
    sent_dt = _parse_iso_datetime(last_sent_at)
    if sent_dt is None:
        return True
    return sent_dt < received_dt


def format_last_reply_label(last_reply_at: str | None) -> str:
    if not last_reply_at:
        return "—"
    parsed = _parse_iso_datetime(last_reply_at)
    if parsed is None:
        return last_reply_at[:16]
    return format_paris_slot(parsed)


def _render_template(body_html: str, vars_map: dict[str, str]) -> str:
    out_body = body_html
    for key, value in vars_map.items():
        out_body = out_body.replace(f"{{{{{key}}}}}", value)
    return out_body.replace("{{accountSignature}}", EMAIL_SIGNATURE)


def _template_requires_slots(body_html: str) -> bool:
    text = body_html or ""
    return any(placeholder in text for placeholder in SLOT_PLACEHOLDERS)


def _campaign_calendly_event(campaign_id: str) -> str | None:
    known = KNOWN_CAMPAIGN_CALENDLY_EVENT.get(campaign_id.strip())
    if known:
        return known

    try:
        from supabase_repo import get_client

        resp = (
            get_client()
            .table("outreach_campaigns")
            .select("niche")
            .eq("campaign_id", campaign_id)
            .maybe_single()
            .execute()
        )
        niche = str((resp.data or {}).get("niche") or "").strip()
        if niche in {"agence", "comptable", "entreprise", "cif"}:
            return niche
    except Exception:
        return None
    return None


def _build_slot_vars_from_labels(labels: list[str]) -> dict[str, str]:
    slot_1 = labels[0].strip() if labels else ""
    slot_2 = labels[1].strip() if len(labels) > 1 else ""
    if slot_1 and not slot_2:
        slot_2 = "un autre créneau"
    return {"slot_1": slot_1, "slot_2": slot_2}


def _resolve_slot_vars(campaign_id: str, body_html: str) -> dict[str, str]:
    empty = {"slot_1": "", "slot_2": ""}
    if not _template_requires_slots(body_html):
        return empty

    event = _campaign_calendly_event(campaign_id)
    if not event:
        return empty

    try:
        import requests

        from config import app_base_url

        response = requests.get(
            f"{app_base_url()}/api/calendly/next-slots",
            params={"event": event, "count": 2},
            timeout=30,
        )
        data = response.json()
        if not response.ok or not data.get("ok"):
            return empty
        slots = data.get("slots") or []
        labels = [
            str(slot.get("label") or "").strip()
            for slot in slots
            if isinstance(slot, dict) and str(slot.get("label") or "").strip()
        ]
        return _build_slot_vars_from_labels(labels)
    except Exception:
        return empty


def _template_vars(
    lead: dict[str, Any],
    *,
    body_html: str = "",
    campaign_id: str = "",
) -> dict[str, str]:
    payload = lead.get("payload") if isinstance(lead.get("payload"), dict) else {}
    reservation_link = lead_custom_var(lead, "reservation_link") or ""
    reservation_agence_link = lead_custom_var(lead, "reservation_agence_link") or reservation_link
    reservation_entreprise_link = (
        lead_custom_var(lead, "reservation_entreprise_link") or reservation_link
    )
    reservation_cif_link = lead_custom_var(lead, "reservation_cif_link") or reservation_link
    reservation_comptable_link = (
        lead_custom_var(lead, "reservation_comptable_link") or reservation_link
    )
    reservation_jum_link = lead_custom_var(lead, "reservation_jum_link") or reservation_link
    reservation_carte_t_link = (
        lead_custom_var(lead, "reservation_carte_t_link") or reservation_link
    )
    if not reservation_link:
        reservation_link = (
            reservation_carte_t_link
            or reservation_jum_link
            or reservation_entreprise_link
            or reservation_cif_link
            or reservation_comptable_link
            or reservation_agence_link
        )
    first = str(
        lead.get("first_name") or payload.get("firstName") or payload.get("first_name") or ""
    )
    company = str(
        lead.get("company_name") or payload.get("companyName") or payload.get("company_name") or ""
    )
    vars_map = {
        "first_name": first,
        "last_name": str(lead.get("last_name") or payload.get("lastName") or ""),
        "company_name": company,
        "reservation_link": reservation_link,
        "reservation_agence_link": reservation_agence_link,
        "reservation_entreprise_link": reservation_entreprise_link,
        "reservation_cif_link": reservation_cif_link,
        "reservation_comptable_link": reservation_comptable_link,
        "reservation_jum_link": reservation_jum_link,
        "reservation_carte_t_link": reservation_carte_t_link,
    }
    if body_html and campaign_id:
        vars_map.update(_resolve_slot_vars(campaign_id, body_html))
    return vars_map


def _load_template(campaign_id: str, template_key: str) -> dict[str, str]:
    from supabase_repo import get_client

    resp = (
        get_client()
        .table("instantly_bypass_templates")
        .select("subject, body_html")
        .eq("campaign_id", campaign_id)
        .eq("template_key", template_key)
        .maybe_single()
        .execute()
    )
    row = resp.data if resp else None
    if not row:
        raise RuntimeError(f"Template not found: {template_key} for campaign {campaign_id}")
    return {"subject": row["subject"], "body_html": row["body_html"]}


def _interest_label(lead: dict[str, Any]) -> str:
    status = lead.get("lt_interest_status")
    if status == INTERESTED_STATUS:
        return "Intéressé"
    if status == NO_SHOW_STATUS:
        return "No Show"
    if status == NOT_INTERESTED_STATUS:
        return "Plus intéressé"
    if status is None:
        return "—"
    return str(status)


def _read_any_reservation_link(lead: dict[str, Any]) -> str:
    for key in (
        "reservation_link",
        "reservation_carte_t_link",
        "reservation_jum_link",
        "reservation_entreprise_link",
        "reservation_cif_link",
        "reservation_comptable_link",
        "reservation_agence_link",
        "conference_link",
    ):
        value = lead_custom_var(lead, key)
        if value:
            return value
    return ""


def _missing_reservation_link(lead: dict[str, Any], body_html: str = "") -> bool:
    text = body_html or ""
    if RESERVATION_LINK_PLACEHOLDER in text:
        return not _read_any_reservation_link(lead)
    checks = (
        (RESERVATION_AGENCE_PLACEHOLDER, "reservation_agence_link"),
        (RESERVATION_ENTREPRISE_PLACEHOLDER, "reservation_entreprise_link"),
        (RESERVATION_CIF_PLACEHOLDER, "reservation_cif_link"),
        (RESERVATION_COMPTABLE_PLACEHOLDER, "reservation_comptable_link"),
        (RESERVATION_JUM_PLACEHOLDER, "reservation_jum_link"),
        (RESERVATION_CARTE_T_PLACEHOLDER, "reservation_carte_t_link"),
    )
    for placeholder, key in checks:
        if placeholder in text and not lead_custom_var(lead, key):
            if _read_any_reservation_link(lead):
                continue
            return True
    return False


def _coerce_step(value: str | None) -> PipelineStep:
    if value in PIPELINE_STEPS:
        return value  # type: ignore[return-value]
    return "step_0"


def move_pipeline_leads(campaign_id: str, emails: list[str], step: PipelineStep) -> None:
    for email in emails:
        upsert_pipeline_step(campaign_id, email, step)


def _paris_day_start_utc(now: datetime | None = None) -> datetime:
    paris = ZoneInfo(send_window_tz())
    utc_now = now or datetime.now(timezone.utc)
    paris_now = utc_now.astimezone(paris)
    paris_start = datetime(
        paris_now.year,
        paris_now.month,
        paris_now.day,
        tzinfo=paris,
    )
    return paris_start.astimezone(timezone.utc)


def was_hercule_sent_today(
    campaign_id: str,
    lead_email: str,
    client: InstantlyClient,
) -> tuple[bool, str | None]:
    """Return whether a Hercule email was sent today (Paris calendar day)."""
    day_start_iso = _paris_day_start_utc().isoformat()

    last_event = get_last_send_at(campaign_id, lead_email)
    if last_event and last_event >= day_start_iso:
        return True, last_event

    sent_items = client.list_emails(
        search=lead_email,
        campaign_id=campaign_id,
        email_type="sent",
        limit=50,
    )
    latest = ""
    for item in sent_items:
        text, _ = extract_email_text(item)
        if not is_hercule_email(text):
            continue
        ts = email_timestamp(item)
        if ts >= day_start_iso and ts > latest:
            latest = ts

    if latest:
        return True, latest
    return False, last_event


@dataclass
class QueueLead:
    lead_id: str
    email: str
    first_name: str
    interest_label: str
    last_sent_at: str | None
    replied_since_last_send: bool
    missing_reservation_link: bool
    sent_flows: list[str]
    step: PipelineStep
    envoyer: bool
    last_reply_at: str | None = None
    awaiting_reply_over_24h: bool = False
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


def suggest_flow_for_lead(lead: QueueLead) -> Flow | None:
    if lead.step == "replies_to_handle":
        sent = set(lead.sent_flows)
        if "interested_email3" in sent:
            return None
        if "interested_email2" in sent:
            return "interested_email3"
        if "interested_email1" in sent:
            return "interested_email2"
        return "interested_email1"
    return DEFAULT_FLOW_BY_STEP.get(lead.step)


@dataclass
class BulkSendResult:
    sent: int = 0
    scheduled: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    scheduled_slot_label: str | None = None


def render_template_html(
    template_key: str,
    lead: dict[str, Any] | None = None,
    *,
    campaign_id: str = "",
) -> str:
    template = _load_template(campaign_id, template_key)
    body_html = template["body_html"]
    vars_map = _template_vars(
        lead or PREVIEW_LEAD,
        body_html=body_html,
        campaign_id=campaign_id,
    )
    return _render_template(body_html, vars_map)


def fetch_pipeline_leads(
    *,
    campaign_id: str,
    max_leads: int = 500,
    client: InstantlyClient | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> list[QueueLead]:
    api_key = get_api_key()
    if not api_key:
        raise ValueError("INSTANTLY_API_KEY is not set")
    instantly = client or InstantlyClient(api_key)

    if on_progress:
        on_progress(0, 1, "Chargement des leads Instantly…")

    raw_leads = instantly.list_leads_by_interest_filter(
        campaign_id=campaign_id,
        interest_filter=FILTER_LEAD_INTERESTED,
        max_leads=max_leads,
    )
    requires_link = campaign_requires_reservation_link(campaign_id)
    instantly_by_email: dict[str, dict[str, Any]] = {}
    for lead in raw_leads:
        email = str(lead.get("email") or "").strip().lower()
        if email:
            instantly_by_email[email] = lead

    pipeline_rows = list_pipeline_for_campaign(campaign_id)
    step_by_email: dict[str, PipelineStep] = {
        str(row["lead_email"]).strip().lower(): _coerce_step(str(row.get("step") or ""))
        for row in pipeline_rows
        if row.get("lead_email")
    }

    for email in instantly_by_email:
        if email not in step_by_email:
            upsert_pipeline_step(campaign_id, email, "step_0")
            step_by_email[email] = "step_0"

    all_emails = sorted(set(instantly_by_email) | set(step_by_email))
    total = len(all_emails)
    rows: list[QueueLead] = []

    for index, lead_email in enumerate(all_emails, start=1):
        if on_progress:
            on_progress(
                index,
                total,
                f"{index}/{total} — {lead_email} — sync CRM / Unibox…",
            )

        lead = instantly_by_email.get(lead_email) or {
            "id": "",
            "email": lead_email,
            "first_name": "",
            "payload": {},
        }
        step = step_by_email.get(lead_email, "step_0")
        last_sent_at = get_last_send_at(campaign_id, lead_email)
        replied_since_last_send = False
        if last_sent_at and step in REPLY_MOVE_STEPS:
            replied_since_last_send = lead_has_replied_since(instantly, lead_email, last_sent_at)
            time.sleep(0.15)
            if replied_since_last_send:
                upsert_pipeline_step(campaign_id, lead_email, "replies_to_handle")
                step = "replies_to_handle"

        sent_flows = list_sent_flows(campaign_id, lead_email)
        last_reply_at: str | None = None
        awaiting_reply_over_24h = False
        if step == "replies_to_handle" or replied_since_last_send:
            last_reply_at = get_last_received_at(instantly, lead_email, campaign_id)
            time.sleep(0.15)
            awaiting_reply_over_24h = is_awaiting_reply_over_24h(last_reply_at, last_sent_at)

        rows.append(
            QueueLead(
                lead_id=str(lead.get("id") or ""),
                email=lead_email,
                first_name=str(lead.get("first_name") or ""),
                interest_label=_interest_label(lead),
                last_sent_at=last_sent_at,
                replied_since_last_send=replied_since_last_send,
                missing_reservation_link=requires_link
                and not (
                    bool(lead_custom_var(lead, "reservation_agence_link"))
                    or bool(lead_custom_var(lead, "reservation_entreprise_link"))
                ),
                sent_flows=sent_flows,
                step=step,
                envoyer=not replied_since_last_send,
                last_reply_at=last_reply_at,
                awaiting_reply_over_24h=awaiting_reply_over_24h,
                raw=lead,
            )
        )

    if on_progress:
        on_progress(total, total, f"{total} lead(s) chargé(s).")

    return rows


def leads_for_step(queue: list[QueueLead], step: PipelineStep) -> list[QueueLead]:
    return [row for row in queue if row.step == step]


def _execute_send(
    client: InstantlyClient,
    *,
    flow: Flow,
    campaign_id: str,
    lead: dict[str, Any],
    lead_email: str,
    lead_id: str,
    idem: str,
    started: datetime,
    html_override: str | None = None,
) -> dict[str, Any]:
    template = _load_template(campaign_id, flow)

    thread = resolve_thread(
        client,
        lead_email=lead_email,
        campaign_id=campaign_id,
        fallback_eaccount=lead_custom_var(lead, "email_account"),
    )
    if not thread:
        record_event(
            {
                "idempotency_key": idem,
                "flow": flow,
                "campaign_id": campaign_id,
                "lead_email": lead_email,
                "lead_id": lead_id or None,
                "status": "failed",
                "error_message": "Could not resolve Unibox thread",
            }
        )
        return {"ok": False, "error": "thread_not_found", "lead_email": lead_email}

    body_html = template["body_html"]
    source_html = html_override if html_override is not None else body_html
    vars_map = _template_vars(lead, body_html=source_html, campaign_id=campaign_id)
    html = _render_template(source_html, vars_map)
    subject = resolve_bypass_reply_subject(
        flow=flow,
        thread_subject=thread.get("subject"),
        template_subject=template.get("subject"),
    )

    client.reply_to_email(
        eaccount=thread["eaccount"],
        reply_to_uuid=thread["reply_to_uuid"],
        subject=subject,
        html=html,
    )

    dispatched = datetime.now(timezone.utc)
    latency_ms = int((dispatched - started).total_seconds() * 1000)

    next_step = STEP_AFTER_FLOW.get(flow)
    if next_step:
        upsert_pipeline_step(campaign_id, lead_email, next_step)

    record_event(
        {
            "idempotency_key": idem,
            "flow": flow,
            "campaign_id": campaign_id,
            "lead_email": lead_email,
            "lead_id": lead_id or None,
            "dispatched_at": dispatched.isoformat(),
            "latency_ms": latency_ms,
            "status": "sent",
            "reply_to_uuid": thread["reply_to_uuid"],
        }
    )
    return {"ok": True, "lead_email": lead_email, "latency_ms": latency_ms}


def dispatch_one(
    client: InstantlyClient,
    *,
    flow: Flow,
    campaign_id: str,
    lead: dict[str, Any],
    dry_run: bool = False,
    force_immediate: bool = False,
) -> dict[str, Any]:
    if not is_campaign_outreach_allowed(get_client(), campaign_id):
        return outreach_blocked_result(campaign_id)

    lead_email = str(lead.get("email") or "").strip().lower()
    lead_id = str(lead.get("id") or "")
    if not lead_email:
        return {"ok": False, "error": "missing_lead_email"}

    idem = idempotency_key(flow, campaign_id, lead_email)
    if has_sent_event(idem):
        return {"ok": True, "skipped": "already_sent"}

    if has_pending_job(idem):
        return {"ok": True, "skipped": "already_scheduled"}

    try:
        template = _load_template(campaign_id, flow)
    except RuntimeError:
        record_event(
            {
                "idempotency_key": idem,
                "flow": flow,
                "campaign_id": campaign_id,
                "lead_email": lead_email,
                "lead_id": lead_id or None,
                "status": "failed",
                "error_message": f"Empty or missing template {flow}",
            }
        )
        return {"ok": False, "error": "template_empty", "lead_email": lead_email}

    if not str(template.get("body_html") or "").strip():
        record_event(
            {
                "idempotency_key": idem,
                "flow": flow,
                "campaign_id": campaign_id,
                "lead_email": lead_email,
                "lead_id": lead_id or None,
                "status": "failed",
                "error_message": f"Empty template {flow}",
            }
        )
        return {"ok": False, "error": "template_empty", "lead_email": lead_email}

    if template_requires_reservation_link(template["body_html"]) and _missing_reservation_link(
        lead, template["body_html"]
    ):
        record_event(
            {
                "idempotency_key": idem,
                "flow": flow,
                "campaign_id": campaign_id,
                "lead_email": lead_email,
                "lead_id": lead_id or None,
                "status": "failed",
                "error_message": "Missing reservation link on lead",
            }
        )
        return {"ok": False, "error": "missing_reservation_link", "lead_email": lead_email}

    if dry_run:
        result: dict[str, Any] = {"ok": True, "dry_run": True, "lead_email": lead_email}
        if force_immediate or is_within_send_window():
            result["would_send_now"] = True
        else:
            slot = next_send_slot()
            result["would_schedule"] = True
            result["scheduled_label"] = format_paris_slot(slot)
        return result

    if not force_immediate and not is_within_send_window():
        slot = next_send_slot()
        insert_bypass_job(
            idempotency_key=idem,
            campaign_id=campaign_id,
            lead_email=lead_email,
            flow=flow,
            scheduled_for=slot,
            payload={"lead_id": lead_id, "lead": lead},
        )
        label = format_paris_slot(slot)
        return {
            "ok": True,
            "scheduled": True,
            "scheduled_for": slot.isoformat(),
            "scheduled_label": label,
            "lead_email": lead_email,
        }

    started = datetime.now(timezone.utc)

    try:
        return _execute_send(
            client,
            flow=flow,
            campaign_id=campaign_id,
            lead=lead,
            lead_email=lead_email,
            lead_id=lead_id,
            idem=idem,
            started=started,
        )
    except Exception as exc:
        record_event(
            {
                "idempotency_key": idem,
                "flow": flow,
                "campaign_id": campaign_id,
                "lead_email": lead_email,
                "lead_id": lead_id or None,
                "status": "failed",
                "error_message": str(exc),
            }
        )
        return {"ok": False, "error": str(exc), "lead_email": lead_email}


def dispatch_conversation_reply(
    client: InstantlyClient,
    *,
    flow: Flow,
    campaign_id: str,
    lead: dict[str, Any],
    body_html: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not is_campaign_outreach_allowed(get_client(), campaign_id):
        return outreach_blocked_result(campaign_id)

    lead_email = str(lead.get("email") or "").strip().lower()
    lead_id = str(lead.get("id") or "")
    if not lead_email:
        return {"ok": False, "error": "missing_lead_email"}

    idem = idempotency_key(flow, campaign_id, lead_email)
    if has_sent_event(idem):
        return {"ok": True, "skipped": "already_sent"}

    if has_pending_job(idem):
        return {"ok": True, "skipped": "already_scheduled"}

    if not str(body_html or "").strip():
        return {"ok": False, "error": "empty_body", "lead_email": lead_email}

    try:
        _load_template(campaign_id, flow)
    except RuntimeError:
        return {"ok": False, "error": "template_empty", "lead_email": lead_email}

    if template_requires_reservation_link(body_html) and _missing_reservation_link(
        lead, body_html
    ):
        return {"ok": False, "error": "missing_reservation_link", "lead_email": lead_email}

    if dry_run:
        result: dict[str, Any] = {"ok": True, "dry_run": True, "lead_email": lead_email}
        if is_within_send_window():
            result["would_send_now"] = True
        else:
            slot = next_send_slot()
            result["would_schedule"] = True
            result["scheduled_label"] = format_paris_slot(slot)
        return result

    if not is_within_send_window():
        slot = next_send_slot()
        insert_bypass_job(
            idempotency_key=idem,
            campaign_id=campaign_id,
            lead_email=lead_email,
            flow=flow,
            scheduled_for=slot,
            payload={"lead_id": lead_id, "lead": lead, "body_html": body_html},
        )
        label = format_paris_slot(slot)
        return {
            "ok": True,
            "scheduled": True,
            "scheduled_for": slot.isoformat(),
            "scheduled_label": label,
            "lead_email": lead_email,
        }

    started = datetime.now(timezone.utc)
    try:
        return _execute_send(
            client,
            flow=flow,
            campaign_id=campaign_id,
            lead=lead,
            lead_email=lead_email,
            lead_id=lead_id,
            idem=idem,
            started=started,
            html_override=body_html,
        )
    except Exception as exc:
        record_event(
            {
                "idempotency_key": idem,
                "flow": flow,
                "campaign_id": campaign_id,
                "lead_email": lead_email,
                "lead_id": lead_id or None,
                "status": "failed",
                "error_message": str(exc),
            }
        )
        return {"ok": False, "error": str(exc), "lead_email": lead_email}


def thread_already_has_e1(
    client: InstantlyClient,
    *,
    lead_email: str,
    campaign_id: str,
) -> bool:
    """True when a Hercule E1 (comptable fingerprint) is already in the Unibox thread."""
    sent_items = client.list_emails(
        search=lead_email,
        campaign_id=campaign_id,
        email_type="sent",
        limit=50,
    )
    for item in sent_items:
        text, _ = extract_email_text(item)
        if "interested_email1" in match_flows(text, allowed_flows=["interested_email1"]):
            return True
    return False


def dispatch_bulk(
    *,
    campaign_id: str,
    flow: Flow,
    leads: list[dict[str, Any]],
    dry_run: bool = False,
    force_immediate: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> BulkSendResult:
    api_key = get_api_key()
    if not api_key:
        raise ValueError("INSTANTLY_API_KEY is not set")

    client = InstantlyClient(api_key)
    result = BulkSendResult()

    for lead in leads:
        lead_email = str(lead.get("email") or "")
        if on_progress:
            on_progress(lead_email)

        dispatch_result = dispatch_one(
            client,
            flow=flow,
            campaign_id=campaign_id,
            lead=lead,
            dry_run=dry_run,
            force_immediate=force_immediate,
        )

        if dispatch_result.get("skipped"):
            result.skipped += 1
        elif dispatch_result.get("scheduled") or dispatch_result.get("would_schedule"):
            result.scheduled += 1
            label = dispatch_result.get("scheduled_label")
            if label and not result.scheduled_slot_label:
                result.scheduled_slot_label = label
        elif dispatch_result.get("ok"):
            result.sent += 1
        else:
            result.failed += 1
            result.errors.append(f"{lead_email}: {dispatch_result.get('error', 'unknown')}")

        if not dry_run:
            time.sleep(EMAIL_SEND_DELAY_S)

    return result
