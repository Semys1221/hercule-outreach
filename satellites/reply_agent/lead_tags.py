"""Instantly lead interest tags for Pending Unibox filtering."""

from __future__ import annotations

from typing import Any

from shared.instantly_client import (
    FILTER_LEAD_INTERESTED,
    FILTER_LEAD_NOT_INTERESTED,
    FILTER_LEAD_NO_SHOW,
    InstantlyClient,
)

INTERESTED_STATUS = 1
NOT_INTERESTED_STATUS = -1
NO_SHOW_STATUS = -4

TAG_ALL = "all"
TAG_INTERESTED = "interested"
TAG_NOT_INTERESTED = "not_interested"
TAG_NO_SHOW = "no_show"
TAG_LEAD = "lead"

TAG_LABELS: dict[str, str] = {
    TAG_ALL: "All",
    TAG_INTERESTED: "Interested",
    TAG_NOT_INTERESTED: "Not interested",
    TAG_NO_SHOW: "No show",
    TAG_LEAD: "Lead",
}

TAG_FILTER_ORDER = [
    TAG_ALL,
    TAG_INTERESTED,
    TAG_NOT_INTERESTED,
    TAG_NO_SHOW,
    TAG_LEAD,
]


def tag_key_for_status(status: int | None) -> str:
    if status == INTERESTED_STATUS:
        return TAG_INTERESTED
    if status == NOT_INTERESTED_STATUS:
        return TAG_NOT_INTERESTED
    if status == NO_SHOW_STATUS:
        return TAG_NO_SHOW
    return TAG_LEAD


def interest_label(status: int | None) -> str:
    return TAG_LABELS[tag_key_for_status(status)]


def _read_interest_status(lead: dict[str, Any]) -> int | None:
    raw = lead.get("lt_interest_status")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _email_from_lead(lead: dict[str, Any]) -> str:
    return str(lead.get("email") or "").strip().lower()


def build_interest_index(
    client: InstantlyClient,
    campaign_id: str,
) -> dict[str, int | None]:
    """Map lead email -> lt_interest_status from bulk Instantly filters."""
    index: dict[str, int | None] = {}

    for interest_filter, status in (
        (FILTER_LEAD_INTERESTED, INTERESTED_STATUS),
        (FILTER_LEAD_NOT_INTERESTED, NOT_INTERESTED_STATUS),
        (FILTER_LEAD_NO_SHOW, NO_SHOW_STATUS),
    ):
        leads = client.list_leads_by_interest_filter(
            campaign_id=campaign_id,
            interest_filter=interest_filter,
            max_leads=1000,
        )
        for lead in leads:
            email = _email_from_lead(lead)
            if email:
                index[email] = status

    return index


def lookup_lead_interest_from_index(
    index: dict[str, int | None],
    lead_email: str,
) -> int | None:
    """Index-only lookup; missing emails default to Lead tag (None)."""
    return index.get(lead_email.strip().lower())


def lookup_lead_interest(
    client: InstantlyClient,
    campaign_id: str,
    lead_email: str,
    index: dict[str, int | None],
) -> int | None:
    normalized = lead_email.strip().lower()
    if normalized in index:
        return index[normalized]

    lead = client.find_lead_by_email_in_campaign(campaign_id, normalized)
    if not lead:
        index[normalized] = None
        return None

    status = _read_interest_status(lead)
    index[normalized] = status
    return status


def count_by_tag(rows: list[Any]) -> dict[str, int]:
    counts = {key: 0 for key in TAG_FILTER_ORDER if key != TAG_ALL}
    for row in rows:
        tag = tag_key_for_status(getattr(row, "interest_status", None))
        counts[tag] = counts.get(tag, 0) + 1
    counts[TAG_ALL] = len(rows)
    return counts
