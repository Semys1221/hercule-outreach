#!/usr/bin/env python3
"""Remove pure CAC (commissaire aux comptes) leads from the Comptable Instantly campaign + list."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRAPER_DIR = _REPO_ROOT / "scraper"

for path in (str(_REPO_ROOT), str(_SCRAPER_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

load_dotenv(_REPO_ROOT / ".env")

COMPTABLE_CAMPAIGN_ID = "5591a068-75f9-4826-8564-4dc2acc74bd4"
COMPTABLE_LIST_ID = "edfd3090-6306-4f71-bd83-01192b06666c"


def _lead_summary(lead: dict[str, Any]) -> dict[str, str]:
    payload = lead.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}
    return {
        "id": str(lead.get("id") or ""),
        "email": str(lead.get("email") or payload.get("email") or ""),
        "company": str(
            lead.get("company_name")
            or payload.get("companyName")
            or ""
        ),
        "type": str(payload.get("type") or ""),
        "category": str(payload.get("category") or ""),
        "subtypes": str(payload.get("subtypes") or ""),
    }


def _collect_cac_leads(
    campaign_id: str,
    list_id: str,
) -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
    from audit_filter import is_instantly_lead_cac_only
    from shared.instantly_client import (
        fetch_leads_from_campaign,
        fetch_leads_from_list,
    )

    sources: dict[str, set[str]] = {"campaign": set(), "list": set(), "both": set()}
    by_id: dict[str, dict[str, Any]] = {}

    print("Fetching campaign leads...")
    campaign_leads = fetch_leads_from_campaign(campaign_id, max_leads=None)
    print(f"  {len(campaign_leads)} lead(s) in campaign")

    print("Fetching list leads...")
    list_leads = fetch_leads_from_list(list_id, max_leads=None)
    print(f"  {len(list_leads)} lead(s) in list")

    campaign_ids = {str(lead.get("id")) for lead in campaign_leads if lead.get("id")}
    list_ids = {str(lead.get("id")) for lead in list_leads if lead.get("id")}

    for lead in campaign_leads + list_leads:
        lead_id = str(lead.get("id") or "")
        if not lead_id:
            continue
        by_id.setdefault(lead_id, lead)

    cac_leads: list[dict[str, Any]] = []
    for lead_id, lead in by_id.items():
        if not is_instantly_lead_cac_only(lead):
            continue
        in_campaign = lead_id in campaign_ids
        in_list = lead_id in list_ids
        if in_campaign:
            sources["campaign"].add(lead_id)
        if in_list:
            sources["list"].add(lead_id)
        if in_campaign and in_list:
            sources["both"].add(lead_id)
        cac_leads.append(lead)

    return cac_leads, sources


def _print_report(cac_leads: list[dict[str, Any]], sources: dict[str, set[str]]) -> None:
    print()
    print(f"Pure CAC leads to remove: {len(cac_leads)}")
    print(f"  in campaign: {len(sources['campaign'])}")
    print(f"  in list: {len(sources['list'])}")
    print(f"  in both: {len(sources['both'])}")
    print()
    print("Sample (up to 10):")
    for lead in cac_leads[:10]:
        row = _lead_summary(lead)
        print(
            f"  - {row['email']} | {row['company']} | "
            f"type={row['type']} | category={row['category']}"
        )


def _delete_leads_by_ids(lead_ids: list[str], *, campaign_id: str) -> int:
    from shared.instantly_client import InstantlyClient, get_api_key

    client = InstantlyClient(get_api_key())
    deleted = 0
    batch_size = 100
    for index in range(0, len(lead_ids), batch_size):
        batch = lead_ids[index : index + batch_size]
        client._fetch(
            "/leads",
            method="DELETE",
            body={"campaign_id": campaign_id, "ids": batch},
        )
        deleted += len(batch)
        print(f"  deleted {deleted}/{len(lead_ids)}")
        if index + batch_size < len(lead_ids):
            time.sleep(0.5)
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove pure CAC leads from Comptable Instantly campaign + list",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Delete matching leads (default: dry-run preview only)",
    )
    parser.add_argument("--campaign-id", default=COMPTABLE_CAMPAIGN_ID)
    parser.add_argument("--list-id", default=COMPTABLE_LIST_ID)
    args = parser.parse_args()

    dry_run = not args.execute
    cac_leads, sources = _collect_cac_leads(args.campaign_id, args.list_id)
    _print_report(cac_leads, sources)

    if not cac_leads:
        print("\nNothing to remove.")
        return 0

    if dry_run:
        print("\nDry-run only — pass --execute to delete.")
        return 0

    lead_ids = [str(lead.get("id")) for lead in cac_leads if lead.get("id")]
    print(f"\nDeleting {len(lead_ids)} lead(s)...")
    deleted = _delete_leads_by_ids(lead_ids, campaign_id=args.campaign_id)
    print(f"Deleted {deleted} lead(s).")

    print("\nVerifying...")
    remaining, _ = _collect_cac_leads(args.campaign_id, args.list_id)
    if remaining:
        print(f"WARNING: {len(remaining)} pure CAC lead(s) still remain.")
        return 1

    print("OK — no pure CAC leads remain in campaign or list.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
