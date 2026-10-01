"""Fetch pending Unibox replies awaiting Hercule response."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from shared.instantly_client import InstantlyClient, PAGE_SIZE

from lead_tags import (
    interest_label,
    lookup_lead_interest,
    tag_key_for_status,
)
from supabase_repo import list_blocklist, list_client_emails
from unibox_thread import strip_quoted_reply

# Instantly ue_type: 2 = Received (latest message awaiting our reply).
_UE_TYPE_RECEIVED = 2
_MAX_PAGES = 5

ProgressCallback = Callable[[int, int, int, int], None]


@dataclass(frozen=True)
class PendingReplyRow:
    lead_email: str
    last_reply_at: str
    last_reply_subject: str
    last_reply_preview: str
    last_reply_id: str
    thread_id: str = ""
    interest_status: int | None = None
    interest_label: str = "Lead"


def _read_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _lead_email_from_item(item: dict[str, Any]) -> str:
    email = _read_str(item.get("lead"))
    if not email:
        email = _read_str(item.get("from_address_email"))
    if not email:
        email = _read_str(item.get("to_address_email_list"))
    return email.lower()


def _email_timestamp(item: dict[str, Any]) -> str:
    return _read_str(item.get("timestamp_email") or item.get("timestamp_created"))


def _plain_from_html(raw: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_received_latest(item: dict[str, Any]) -> bool:
    ue_type = item.get("ue_type")
    if ue_type is not None:
        try:
            return int(ue_type) == _UE_TYPE_RECEIVED
        except (TypeError, ValueError):
            pass
    return str(item.get("email_type") or "").lower() == "received"


def extract_email_body(item: dict[str, Any]) -> str:
    body = item.get("body")
    body_html = ""
    body_text = ""
    if isinstance(body, dict):
        body_html = _read_str(body.get("html"))
        body_text = _read_str(body.get("text"))
    else:
        body_html = _read_str(item.get("body_html"))
        body_text = _read_str(item.get("body_text"))
    if not body_text and body_html:
        body_text = _plain_from_html(body_html)
    return strip_quoted_reply(body_text)


def _preview_from_item(item: dict[str, Any]) -> str:
    preview = _read_str(item.get("content_preview"))
    if not preview:
        preview = extract_email_body(item)
    return preview[:160] + ("…" if len(preview) > 160 else "")


def is_awaiting_our_reply(
    client: InstantlyClient,
    *,
    lead_email: str,
    campaign_id: str,
) -> bool:
    items = client.list_emails(
        search=lead_email,
        campaign_id=campaign_id,
        latest_of_thread=True,
        limit=1,
        preview_only=True,
    )
    if not items:
        return False
    return _is_received_latest(items[0])


def is_reply_over_24h(last_reply_at: str) -> bool:
    raw = last_reply_at.strip()
    if not raw:
        return False
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return datetime.now(timezone.utc) - parsed >= timedelta(hours=24)


def _row_recency_key(row: PendingReplyRow) -> tuple[str, str]:
    return (row.last_reply_at, row.last_reply_id)


def dedupe_pending_rows_by_email(rows: list[PendingReplyRow]) -> list[PendingReplyRow]:
    """Keep one row per lead email (most recent reply wins)."""
    by_email: dict[str, PendingReplyRow] = {}
    for row in rows:
        key = row.lead_email.lower()
        existing = by_email.get(key)
        if existing is None or _row_recency_key(row) > _row_recency_key(existing):
            by_email[key] = row
    return sorted(by_email.values(), key=_row_recency_key, reverse=True)


def fetch_pending_emails(
    client: InstantlyClient,
    campaign_id: str,
    *,
    max_leads: int = 200,
    on_progress: ProgressCallback | None = None,
) -> list[PendingReplyRow]:
    """Fetch pending threads from Instantly (emails only, no tag enrichment)."""
    pending: list[PendingReplyRow] = []
    starting_after: str | None = None
    campaign = campaign_id.strip()
    page_index = 0

    while len(pending) < max_leads and page_index < _MAX_PAGES:
        page_index += 1
        params = [
            f"campaign_id={campaign}",
            "latest_of_thread=true",
            f"limit={PAGE_SIZE}",
            "sort_order=desc",
            "preview_only=true",
        ]
        if starting_after:
            params.append(f"starting_after={starting_after}")

        try:
            page = client._fetch(f"/emails?{'&'.join(params)}", method="GET")
        except RuntimeError:
            break

        page_items = page.get("items") or [] if isinstance(page, dict) else []
        if not page_items:
            break

        for item in page_items:
            if not _is_received_latest(item):
                continue
            lead_email = _lead_email_from_item(item)
            if not lead_email or "@" not in lead_email:
                continue
            pending.append(
                PendingReplyRow(
                    lead_email=lead_email,
                    last_reply_at=_email_timestamp(item),
                    last_reply_subject=_read_str(item.get("subject")),
                    last_reply_preview=_preview_from_item(item),
                    last_reply_id=_read_str(item.get("id")),
                    thread_id=_read_str(item.get("thread_id")),
                )
            )
            if len(pending) >= max_leads:
                break

        if on_progress:
            on_progress(page_index, _MAX_PAGES, len(pending), max_leads)

        if len(pending) >= max_leads:
            break

        next_cursor = page.get("next_starting_after") if isinstance(page, dict) else None
        if not next_cursor:
            next_cursor = page_items[-1].get("id")
        if not next_cursor or len(page_items) < PAGE_SIZE:
            break
        starting_after = str(next_cursor)

    return dedupe_pending_rows_by_email(pending)


def enrich_pending_rows(
    client: InstantlyClient,
    interest_index: dict[str, int | None],
    campaign_id: str,
    rows: list[PendingReplyRow],
) -> list[PendingReplyRow]:
    """Apply blocklist, paying clients, and Instantly interest tags."""
    blocklist = list_blocklist(campaign_id)
    client_emails = list_client_emails()
    filtered = [
        row
        for row in rows
        if row.lead_email.lower() not in blocklist
        and row.lead_email.lower() not in client_emails
    ]
    if not filtered:
        return []

    enriched: list[PendingReplyRow] = []
    for row in filtered:
        status = lookup_lead_interest(
            client, campaign_id, row.lead_email, interest_index
        )
        enriched.append(
            PendingReplyRow(
                lead_email=row.lead_email,
                last_reply_at=row.last_reply_at,
                last_reply_subject=row.last_reply_subject,
                last_reply_preview=row.last_reply_preview,
                last_reply_id=row.last_reply_id,
                thread_id=row.thread_id,
                interest_status=status,
                interest_label=interest_label(status),
            )
        )
    return enriched


def fetch_pending_replies(
    client: InstantlyClient,
    campaign_id: str,
    *,
    max_leads: int = 200,
    on_progress: ProgressCallback | None = None,
    interest_index: dict[str, int | None] | None = None,
) -> list[PendingReplyRow]:
    """Fetch pending emails and enrich with tags (single-phase convenience wrapper)."""
    rows = fetch_pending_emails(
        client,
        campaign_id,
        max_leads=max_leads,
        on_progress=on_progress,
    )
    if interest_index is None:
        return rows
    return enrich_pending_rows(client, interest_index, campaign_id, rows)


def resolve_inbound_body(
    client: InstantlyClient,
    row: PendingReplyRow,
) -> str:
    """Full inbound text for Groq (fetch email by id when available)."""
    if row.last_reply_id:
        item = client.get_email(row.last_reply_id)
        if item:
            body = extract_email_body(item)
            if body.strip():
                return body
    preview = (row.last_reply_preview or "").strip()
    if preview.endswith("…"):
        preview = preview[:-1].strip()
    return preview or "(empty body)"


def filter_rows_by_tag(
    rows: list[PendingReplyRow],
    tag_key: str,
) -> list[PendingReplyRow]:
    if tag_key == "all":
        return rows
    return [
        row
        for row in rows
        if tag_key_for_status(row.interest_status) == tag_key
    ]
