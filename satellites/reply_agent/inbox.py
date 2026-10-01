"""Manual reply dispatch from Problem tab and Pending Unibox."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from outreach_preset_ops import (
    PRESET_INACTIVE_MESSAGE,
    is_campaign_outreach_allowed,
)

from send_window import format_paris_slot, is_within_send_window, next_send_slot
from supabase_repo import (
    get_client,
    insert_inbound_message,
    insert_outbound_message,
    queue_manual_job,
    update_message_status,
)
from thread_resolve import resolve_thread
from email_format import format_reply_html
from lead_links import TargetType


def plain_text_to_html(text: str) -> str:
    """Legacy alias — prefer format_reply_html for outbound replies."""
    return format_reply_html(text)


def _build_html_body(
    reply_text: str,
    *,
    lead_email: str,
    target_type: TargetType | None = None,
) -> str:
    return format_reply_html(
        reply_text.strip(),
        lead_email=lead_email,
        target_type=target_type,
    )


def _format_subject(subject: str) -> str:
    cleaned = subject.strip() or "Re: votre message"
    if not cleaned.lower().startswith("re:"):
        return f"Re: {cleaned}"
    return cleaned


def _send_or_queue(
    instantly_client: Any,
    *,
    campaign_id: str,
    lead_email: str,
    message_id: str,
    eaccount: str,
    reply_to_uuid: str,
    subject: str,
    reply_text: str,
    html_body: str,
) -> dict[str, str]:
    payload = {
        "eaccount": eaccount,
        "reply_to_uuid": reply_to_uuid,
        "subject": subject,
        "html": html_body,
        "body_text": reply_text.strip(),
    }

    if is_within_send_window():
        instantly_client.reply_to_email(
            eaccount=eaccount,
            reply_to_uuid=reply_to_uuid,
            subject=subject,
            html=html_body,
        )
        update_message_status(message_id, "manual_replied")
        insert_outbound_message(
            {
                "campaign_id": campaign_id,
                "lead_email": lead_email.lower(),
                "direction": "outbound",
                "subject": subject,
                "body_text": reply_text.strip(),
                "email_account": eaccount,
                "ai_status": "manual_replied",
                "reply_to_uuid": reply_to_uuid,
            }
        )
        return {"status": "sent", "detail": "Réponse envoyée."}

    scheduled = next_send_slot()
    queue_manual_job(
        campaign_id=campaign_id,
        lead_email=lead_email,
        message_id=message_id,
        scheduled_for=scheduled.isoformat(),
        payload=payload,
    )
    update_message_status(
        message_id,
        "manual_queued",
        f"Programmé pour {format_paris_slot(scheduled)}",
    )
    return {
        "status": "queued",
        "detail": f"Réponse programmée : {format_paris_slot(scheduled)}",
    }


def dispatch_manual_reply(
    instantly_client: Any,
    *,
    campaign_id: str,
    inbound: dict[str, Any],
    reply_text: str,
    target_type: TargetType | None = None,
) -> dict[str, str]:
    if not is_campaign_outreach_allowed(get_client(), campaign_id):
        return {"status": "blocked", "detail": PRESET_INACTIVE_MESSAGE}

    lead_email = str(inbound.get("lead_email") or "")
    message_id = str(inbound.get("id") or "")
    eaccount = str(inbound.get("email_account") or "").strip()
    reply_to_uuid = str(
        inbound.get("reply_to_uuid") or inbound.get("instantly_email_id") or ""
    ).strip()
    subject = _format_subject(str(inbound.get("subject") or "Re: votre message"))

    if not eaccount or not reply_to_uuid:
        raise ValueError("Missing email_account or reply_to_uuid on inbound message")

    html_body = _build_html_body(
        reply_text,
        lead_email=lead_email,
        target_type=target_type,
    )
    return _send_or_queue(
        instantly_client,
        campaign_id=campaign_id,
        lead_email=lead_email,
        message_id=message_id,
        eaccount=eaccount,
        reply_to_uuid=reply_to_uuid,
        subject=subject,
        reply_text=reply_text,
        html_body=html_body,
    )


def dispatch_unibox_reply(
    instantly_client: Any,
    *,
    campaign_id: str,
    lead_email: str,
    reply_text: str,
    inbound_body: str = "",
    inbound_subject: str = "",
    instantly_email_id: str | None = None,
    target_type: TargetType | None = None,
) -> dict[str, str]:
    if not is_campaign_outreach_allowed(get_client(), campaign_id):
        return {"status": "blocked", "detail": PRESET_INACTIVE_MESSAGE}

    thread = resolve_thread(
        instantly_client,
        lead_email=lead_email,
        campaign_id=campaign_id,
    )
    if not thread:
        raise ValueError("Impossible de résoudre le thread Unibox pour ce lead")

    eaccount = thread["eaccount"]
    reply_to_uuid = thread["reply_to_uuid"]
    subject = _format_subject(inbound_subject or thread.get("subject") or "")

    message_id = insert_inbound_message(
        {
            "campaign_id": campaign_id,
            "lead_email": lead_email.lower(),
            "direction": "inbound",
            "event_type": "unibox_manual",
            "instantly_email_id": instantly_email_id,
            "subject": inbound_subject or subject,
            "body_text": inbound_body or "(pending unibox reply)",
            "email_account": eaccount,
            "ai_status": "pending",
            "reply_to_uuid": reply_to_uuid,
        }
    )

    html_body = _build_html_body(
        reply_text,
        lead_email=lead_email,
        target_type=target_type,
    )
    return _send_or_queue(
        instantly_client,
        campaign_id=campaign_id,
        lead_email=lead_email,
        message_id=message_id,
        eaccount=eaccount,
        reply_to_uuid=reply_to_uuid,
        subject=subject,
        reply_text=reply_text,
        html_body=html_body,
    )
