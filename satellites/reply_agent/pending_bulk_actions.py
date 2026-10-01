"""Bulk actions for Pending Unibox table (no Streamlit UI)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Literal

from agent_preview import generate_reply_preview
from config import bulk_try_agent_concurrency
from inbox import dispatch_unibox_reply
from lead_links import TargetType
from lead_tags import INTERESTED_STATUS, NOT_INTERESTED_STATUS
from reply_gate import apply_reply_gate
from pending_fetch import PendingReplyRow, resolve_inbound_body
from pending_table_state import clear_checkbox
from shared.instantly_client import InstantlyClient
from supabase_repo import add_to_blocklist, get_lead_reply, upsert_lead_reply


@dataclass
class BulkActionResult:
    succeeded: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class _LeadTryOutcome:
    email: str
    kind: Literal["succeeded", "failed", "skipped"]
    detail: str = ""


def _rows_by_email(rows: list[PendingReplyRow]) -> dict[str, PendingReplyRow]:
    return {row.lead_email.lower(): row for row in rows}


def _process_one_lead(
    *,
    campaign_id: str,
    config: dict[str, Any],
    row: PendingReplyRow,
    api_key: str,
    regenerate_existing: bool,
    interested_only: bool,
) -> _LeadTryOutcome:
    normalized = row.lead_email.strip().lower()
    if interested_only and row.interest_status != INTERESTED_STATUS:
        return _LeadTryOutcome(normalized, "skipped", "Lead non tagué Interested")

    if row.interest_status == NOT_INTERESTED_STATUS:
        return _LeadTryOutcome(
            normalized,
            "skipped",
            "Lead marqué Not interested dans Instantly",
        )

    if not regenerate_existing:
        existing = get_lead_reply(campaign_id, normalized).strip()
        if existing:
            return _LeadTryOutcome(normalized, "skipped", "Brouillon déjà présent")

    client = InstantlyClient(api_key)
    try:
        inbound_body = resolve_inbound_body(client, row)
        preview = generate_reply_preview(
            config,
            inbound_body,
            row.lead_email,
            interest_label=row.interest_label,
        )
        gate = apply_reply_gate(row.interest_status, preview)
        if gate["allow_reply"] and preview.get("reply_text"):
            upsert_lead_reply(
                campaign_id,
                normalized,
                str(preview["reply_text"]),
            )
            return _LeadTryOutcome(normalized, "succeeded")
        reason = gate["reason"] or str(
            preview.get("reason") or "L'IA a choisi de ne pas répondre."
        )
        return _LeadTryOutcome(normalized, "skipped", reason)
    except Exception as exc:
        return _LeadTryOutcome(normalized, "failed", str(exc))


def bulk_delete(
    campaign_id: str,
    rows: list[PendingReplyRow],
    emails: set[str],
) -> BulkActionResult:
    result = BulkActionResult()
    by_email = _rows_by_email(rows)

    for email in sorted(emails):
        normalized = email.strip().lower()
        if normalized not in by_email:
            result.skipped.append((normalized, "lead introuvable"))
            continue
        try:
            add_to_blocklist(campaign_id, normalized)
            clear_checkbox(campaign_id, normalized)
            result.succeeded.append(normalized)
        except Exception as exc:
            result.failed.append((normalized, str(exc)))

    return result


def bulk_try_agent(
    instantly_client: Any,
    config: dict[str, Any],
    rows: list[PendingReplyRow],
    emails: set[str],
    campaign_id: str,
    *,
    on_progress: Callable[[str, int, int], None] | None = None,
    regenerate_existing: bool = False,
    interested_only: bool = True,
) -> BulkActionResult:
    api_key = str(getattr(instantly_client, "api_key", "") or "").strip()
    if not api_key:
        raise ValueError("Instantly API key is missing on client")

    result = BulkActionResult()
    by_email = _rows_by_email(rows)
    ordered_emails = sorted(emails)
    total = len(ordered_emails)
    work: list[tuple[str, PendingReplyRow]] = []

    for email in ordered_emails:
        normalized = email.strip().lower()
        row = by_email.get(normalized)
        if row is None:
            result.skipped.append((normalized, "lead introuvable"))
            continue
        work.append((normalized, row))

    if not work:
        return result

    result_lock = threading.Lock()
    completed = 0
    progress_lock = threading.Lock()
    max_workers = min(bulk_try_agent_concurrency(), len(work))

    def _record_progress(email: str) -> None:
        nonlocal completed
        if not on_progress:
            return
        with progress_lock:
            completed += 1
            current = completed
        on_progress(email, current, total)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _process_one_lead,
                campaign_id=campaign_id,
                config=config,
                row=row,
                api_key=api_key,
                regenerate_existing=regenerate_existing,
                interested_only=interested_only,
            ): email
            for email, row in work
        }
        for future in as_completed(futures):
            outcome = future.result()
            with result_lock:
                if outcome.kind == "succeeded":
                    result.succeeded.append(outcome.email)
                elif outcome.kind == "skipped":
                    result.skipped.append((outcome.email, outcome.detail))
                else:
                    result.failed.append((outcome.email, outcome.detail))
            _record_progress(outcome.email)

    return result


def bulk_send(
    instantly_client: Any,
    campaign_id: str,
    rows: list[PendingReplyRow],
    emails: set[str],
    *,
    target_type: TargetType | None = None,
    on_progress: Callable[[str, int, int], None] | None = None,
    on_sent: Callable[[PendingReplyRow], None] | None = None,
) -> BulkActionResult:
    result = BulkActionResult()
    by_email = _rows_by_email(rows)
    total = len(emails)

    for index, email in enumerate(sorted(emails), start=1):
        normalized = email.strip().lower()
        if on_progress:
            on_progress(normalized, index, total)

        row = by_email.get(normalized)
        if row is None:
            result.skipped.append((normalized, "lead introuvable"))
            continue

        draft = get_lead_reply(campaign_id, normalized).strip()
        if not draft:
            result.skipped.append((normalized, "pas de draft IA"))
            continue

        try:
            dispatch_unibox_reply(
                instantly_client,
                campaign_id=campaign_id,
                lead_email=row.lead_email,
                reply_text=draft,
                inbound_body=row.last_reply_preview,
                inbound_subject=row.last_reply_subject,
                instantly_email_id=row.last_reply_id or None,
                target_type=target_type,
            )
            if on_sent:
                on_sent(row)
            clear_checkbox(campaign_id, normalized)
            result.succeeded.append(normalized)
        except Exception as exc:
            result.failed.append((normalized, str(exc)))

    return result
