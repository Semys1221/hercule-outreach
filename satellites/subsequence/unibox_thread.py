"""Unibox thread fetch and WhatsApp-style HTML rendering."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Literal

from shared.instantly_client import InstantlyClient

from unibox_classify import (
    classify_sent_items,
    derive_step_from_flows,
    email_timestamp,
    extract_email_text,
    fetch_email_detail,
    flow_tag_for_text,
    is_no_show_status,
)

Direction = Literal["sent", "received"]


@dataclass
class ThreadMessage:
    id: str
    direction: Direction
    timestamp: str
    subject: str
    body_html: str
    body_plain: str
    sender_label: str
    flow_tag: str | None


def _sanitize_html(raw: str) -> str:
    cleaned = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.I | re.S)
    cleaned = re.sub(r"<style[^>]*>.*?</style>", "", cleaned, flags=re.I | re.S)
    return cleaned


def _plain_from_html(raw: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


_QUOTE_HTML_MARKERS: list[re.Pattern[str]] = [
    re.compile(r"<blockquote\b", re.I),
    re.compile(r'class=["\']gmail_quote["\']', re.I),
    re.compile(r'id=["\']divRplyFwdMsg["\']', re.I),
]

_QUOTE_TEXT_MARKERS: list[re.Pattern[str]] = [
    re.compile(r"Le\s+\d{1,2}\s+.+?\s+a\s+(?:écrit|ecrit)\s*:", re.I | re.S),
    re.compile(r"On\s+.+?\s+wrote\s*:", re.I | re.S),
    re.compile(r"-----Original Message-----", re.I),
    re.compile(r"From:\s.+?\nSent:\s", re.I | re.S),
    re.compile(r"^>+\s", re.M),
]


def strip_quoted_reply(raw: str) -> str:
    """Return only the new reply text, without quoted previous messages."""
    if not raw or not raw.strip():
        return ""

    earliest = len(raw)
    for pattern in (*_QUOTE_HTML_MARKERS, *_QUOTE_TEXT_MARKERS):
        match = pattern.search(raw)
        if match and match.start() < earliest:
            earliest = match.start()

    return raw[:earliest].rstrip() if earliest < len(raw) else raw.rstrip()


def _pick_latest_email(items: list[dict]) -> dict | None:
    if not items:
        return None

    def ts(item: dict) -> str:
        return str(item.get("timestamp_email") or item.get("timestamp_created") or "")

    return sorted(items, key=ts, reverse=True)[0]


def fetch_latest_reply(
    client: InstantlyClient,
    *,
    lead_email: str,
    campaign_id: str,
    lead_first_name: str = "",
    limit: int = 1,
) -> list[ThreadMessage]:
    """Fetch the lead's most recent received reply (no sent history)."""
    received_label = lead_first_name.strip() or lead_email
    items = client.list_emails(
        search=lead_email,
        campaign_id=campaign_id,
        email_type="received",
        latest_of_thread=True,
        limit=limit,
    )
    item = _pick_latest_email(items)
    if not item:
        return []

    email_id = str(item.get("id") or "")
    if not email_id:
        return []

    text, has_body = extract_email_text(item)
    if not has_body:
        detail = fetch_email_detail(client, email_id)
        if detail:
            text, has_body = extract_email_text(detail)

    text = strip_quoted_reply(text) if text else ""
    body_html = _sanitize_html(text) if text else ""
    body_plain = (
        _plain_from_html(body_html)
        if body_html
        else str(item.get("subject") or "")
    )

    return [
        ThreadMessage(
            id=email_id,
            direction="received",
            timestamp=email_timestamp(item),
            subject=str(item.get("subject") or ""),
            body_html=body_html,
            body_plain=body_plain,
            sender_label=received_label,
            flow_tag=None,
        )
    ]


def fetch_thread_messages(
    client: InstantlyClient,
    *,
    lead_email: str,
    campaign_id: str,
    lead_first_name: str = "",
    interest_status: int | None = None,
    limit: int = 50,
) -> list[ThreadMessage]:
    is_no_show = is_no_show_status(interest_status)
    received_label = lead_first_name.strip() or lead_email
    messages_by_id: dict[str, ThreadMessage] = {}

    for email_type in ("received", "sent"):
        items = client.list_emails(
            search=lead_email,
            campaign_id=campaign_id,
            email_type=email_type,
            limit=limit,
        )
        direction: Direction = "received" if email_type == "received" else "sent"

        for item in items:
            email_id = str(item.get("id") or "")
            if not email_id:
                continue

            text, has_body = extract_email_text(item)
            if not has_body:
                detail = fetch_email_detail(client, email_id)
                if detail:
                    text, has_body = extract_email_text(detail)

            body_html = _sanitize_html(text) if text else ""
            body_plain = _plain_from_html(body_html) if body_html else str(item.get("subject") or "")

            flow_tag = None
            if direction == "sent":
                flow_tag = flow_tag_for_text(text, is_no_show=is_no_show)

            sender = "Hercule / Béatrice" if direction == "sent" else received_label

            messages_by_id[email_id] = ThreadMessage(
                id=email_id,
                direction=direction,
                timestamp=email_timestamp(item),
                subject=str(item.get("subject") or ""),
                body_html=body_html,
                body_plain=body_plain,
                sender_label=sender,
                flow_tag=flow_tag,
            )

    return sorted(messages_by_id.values(), key=lambda m: m.timestamp or "")


def derive_step_from_thread(
    messages: list[ThreadMessage],
    *,
    interest_status: int | None,
) -> tuple[str, set[str]]:
    is_no_show = is_no_show_status(interest_status)
    sent_items = [
        {
            "id": msg.id,
            "subject": msg.subject,
            "body": {"html": msg.body_html},
            "timestamp_email": msg.timestamp,
        }
        for msg in messages
        if msg.direction == "sent"
    ]
    flows, _, _ = classify_sent_items(sent_items, is_no_show=is_no_show, client=None)
    step = derive_step_from_flows(set(flows), is_no_show=is_no_show)
    return step, {str(f) for f in flows}


def render_conversation_html(messages: list[ThreadMessage]) -> str:
    if not messages:
        return (
            '<div class="unibox-chat"><p style="color:#888;text-align:center;">'
            "Aucun message dans ce thread.</p></div>"
        )

    parts = [
        '<div class="unibox-chat" style="'
        "font-family:system-ui,sans-serif;font-size:13px;"
        "max-height:520px;overflow-y:auto;padding:8px;"
        '">',
    ]

    for msg in messages:
        is_sent = msg.direction == "sent"
        align = "flex-end" if is_sent else "flex-start"
        bg = "#dcf8c6" if is_sent else "#f0f0f0"
        border = "#b8e0a8" if is_sent else "#ddd"
        margin = "margin-left:24px;" if is_sent else "margin-right:24px;"
        badge = ""
        if msg.flow_tag:
            badge = (
                f'<span style="font-size:10px;background:#4f46e5;color:#fff;'
                f'padding:1px 6px;border-radius:8px;margin-left:6px;">'
                f"{html.escape(msg.flow_tag)}</span>"
            )

        body = html.escape(msg.body_plain or msg.subject)
        body = body.replace("\n", "<br/>")
        ts = html.escape(msg.timestamp[:16] if msg.timestamp else "")
        sender = html.escape(msg.sender_label)

        parts.append(
            f'<div style="display:flex;justify-content:{align};margin:8px 0;">'
            f'<div style="max-width:85%;background:{bg};border:1px solid {border};'
            f"border-radius:12px;padding:10px 12px;{margin}\">"
            f'<div style="font-size:11px;color:#666;margin-bottom:4px;">'
            f"{sender}{badge}</div>"
            f'<div style="line-height:1.45;color:#111;">{body}</div>'
            f'<div style="font-size:10px;color:#999;margin-top:6px;text-align:right;">'
            f"{ts}</div></div></div>"
        )

    parts.append("</div>")
    return "".join(parts)


def thread_subject(messages: list[ThreadMessage]) -> str:
    for msg in messages:
        if msg.subject.strip():
            return msg.subject.strip()
    return "(sans sujet)"
