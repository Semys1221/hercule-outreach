"""Unibox thread fetch for AI Reply Agent."""

from __future__ import annotations

import html
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

_APP_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _APP_DIR.parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.instantly_client import InstantlyClient


def strip_quoted_reply(raw: str) -> str:
    if not raw or not raw.strip():
        return ""
    patterns = [
        re.compile(r"<blockquote\b", re.I),
        re.compile(r"Le\s+\d{1,2}\s+.+?\s+a\s+(?:écrit|ecrit)\s*:", re.I | re.S),
        re.compile(r"On\s+.+?\s+wrote\s*:", re.I | re.S),
        re.compile(r"^>+\s", re.M),
    ]
    earliest = len(raw)
    for pattern in patterns:
        match = pattern.search(raw)
        if match and match.start() < earliest:
            earliest = match.start()
    return raw[:earliest].rstrip() if earliest < len(raw) else raw.rstrip()


def _plain_from_html(raw: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_body_text(
    client: InstantlyClient,
    item: dict[str, Any],
    *,
    _fetch_detail: bool = True,
) -> str:
    body = item.get("body")
    body_html = ""
    body_text = ""
    if isinstance(body, dict):
        body_html = str(body.get("html") or "")
        body_text = str(body.get("text") or "")
    else:
        body_html = str(item.get("body_html") or "")
        body_text = str(item.get("body_text") or "")

    if not body_text and not body_html:
        preview = str(item.get("content_preview") or "")
        if preview:
            return strip_quoted_reply(preview)

    if not body_text and body_html:
        body_text = _plain_from_html(body_html)

    if not body_text and _fetch_detail:
        email_id = str(item.get("id") or "")
        if email_id:
            detail = client.get_email(email_id)
            if detail:
                return _extract_body_text(client, detail, _fetch_detail=False)

    return strip_quoted_reply(body_text)


def _items_to_messages(
    client: InstantlyClient,
    items: list[dict[str, Any]],
    *,
    direction: str,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for item in items:
        messages.append(
            {
                "id": str(item.get("id") or ""),
                "direction": direction,
                "timestamp": str(
                    item.get("timestamp_email") or item.get("timestamp_created") or ""
                ),
                "subject": str(item.get("subject") or ""),
                "body": _extract_body_text(client, item),
            }
        )
    return messages


def _fetch_by_thread_id(
    client: InstantlyClient,
    *,
    thread_id: str,
    campaign_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    items = client.list_emails(
        search=f"thread:{thread_id}",
        campaign_id=campaign_id,
        limit=limit,
        preview_only=False,
    )
    messages: list[dict[str, Any]] = []
    for item in items:
        ue_type = item.get("ue_type")
        direction = "received" if ue_type == 2 else "sent"
        messages.append(
            {
                "id": str(item.get("id") or ""),
                "direction": direction,
                "timestamp": str(
                    item.get("timestamp_email") or item.get("timestamp_created") or ""
                ),
                "subject": str(item.get("subject") or ""),
                "body": _extract_body_text(client, item),
            }
        )
    messages.sort(key=lambda m: m.get("timestamp") or "")
    return messages


def fetch_thread_messages(
    client: InstantlyClient,
    *,
    lead_email: str,
    campaign_id: str,
    thread_id: str | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    if thread_id:
        return _fetch_by_thread_id(
            client,
            thread_id=thread_id,
            campaign_id=campaign_id,
            limit=limit,
        )

    def fetch_sent() -> list[dict[str, Any]]:
        items = client.list_emails(
            search=lead_email,
            campaign_id=campaign_id,
            email_type="sent",
            limit=limit,
            preview_only=False,
        )
        return _items_to_messages(client, items, direction="sent")

    def fetch_received() -> list[dict[str, Any]]:
        items = client.list_emails(
            search=lead_email,
            campaign_id=campaign_id,
            email_type="received",
            limit=limit,
            preview_only=False,
        )
        return _items_to_messages(client, items, direction="received")

    with ThreadPoolExecutor(max_workers=2) as executor:
        sent_future = executor.submit(fetch_sent)
        received_future = executor.submit(fetch_received)
        messages = sent_future.result() + received_future.result()

    messages.sort(key=lambda m: m.get("timestamp") or "")
    return messages


def render_conversation_html(messages: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for msg in messages:
        direction = msg.get("direction")
        label = "Hercule / Béatrice" if direction == "sent" else "Prospect"
        align = "right" if direction == "sent" else "left"
        body = html.escape(str(msg.get("body") or ""))
        blocks.append(
            f'<div style="text-align:{align};margin:8px 0;">'
            f'<div style="display:inline-block;max-width:85%;padding:10px 14px;'
            f'border-radius:12px;background:#FFFFFF;border:1px solid #e5e5e5;">'
            f'<div style="font-size:11px;color:#000;margin-bottom:4px;">{html.escape(label)}</div>'
            f'<div style="white-space:pre-wrap;font-size:14px;color:#000;">{body}</div>'
            f"</div></div>"
        )
    return "".join(blocks)
