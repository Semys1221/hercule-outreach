"""Instantly workspace cleanup — empty lists/campaigns and forced deletes."""

from __future__ import annotations

from typing import Any

from instantly_client import (
    delete_campaign,
    delete_lead_list,
    has_leads_in_campaign,
    has_leads_in_list,
    list_all_campaigns,
    list_all_lead_lists,
)

# services_fm — always delete even when leads > 0
FORCE_DELETE_LIST_IDS = frozenset({"29119a30-89fb-457c-a723-583a7ddc98bd"})
FORCE_DELETE_CAMPAIGN_IDS = frozenset({"795ece57-2304-4629-ade3-4e1af7fc6c66"})


def cleanup_empty_instantly(
    api_key: str,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Delete workspace lists/campaigns with 0 leads; force-delete services_fm."""
    lists = list_all_lead_lists(api_key)
    campaigns = list_all_campaigns(api_key)

    to_delete_lists: list[dict[str, str]] = []
    to_delete_campaigns: list[dict[str, str]] = []

    for item in lists:
        list_id = str(item.get("id") or "").strip()
        if not list_id:
            continue
        name = str(item.get("name") or list_id)
        if list_id in FORCE_DELETE_LIST_IDS:
            to_delete_lists.append({"id": list_id, "name": name, "reason": "force services_fm"})
            continue
        if not has_leads_in_list(api_key, list_id):
            to_delete_lists.append({"id": list_id, "name": name, "reason": "0 leads"})

    for item in campaigns:
        campaign_id = str(item.get("id") or "").strip()
        if not campaign_id:
            continue
        name = str(item.get("name") or campaign_id)
        if campaign_id in FORCE_DELETE_CAMPAIGN_IDS:
            to_delete_campaigns.append(
                {"id": campaign_id, "name": name, "reason": "force services_fm"}
            )
            continue
        if not has_leads_in_campaign(api_key, campaign_id):
            to_delete_campaigns.append({"id": campaign_id, "name": name, "reason": "0 leads"})

    deleted_lists: list[str] = []
    deleted_campaigns: list[str] = []

    if not dry_run:
        # Campaigns first (may reference lists)
        for row in to_delete_campaigns:
            delete_campaign(api_key, row["id"])
            deleted_campaigns.append(row["id"])
        for row in to_delete_lists:
            delete_lead_list(api_key, row["id"])
            deleted_lists.append(row["id"])

    return {
        "dry_run": dry_run,
        "lists_to_delete": to_delete_lists,
        "campaigns_to_delete": to_delete_campaigns,
        "deleted_lists": deleted_lists,
        "deleted_campaigns": deleted_campaigns,
    }
