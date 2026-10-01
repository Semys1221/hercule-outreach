"""Resolve Instantly Unibox thread anchors for manual replies."""

from __future__ import annotations

import time
from typing import Any

from shared.instantly_client import InstantlyClient


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
