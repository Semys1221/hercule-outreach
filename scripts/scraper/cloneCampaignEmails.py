#!/usr/bin/env python3
"""Clone cold-email sequences from a source Instantly campaign to a target, swapping link vars."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRAPER_DIR = _REPO_ROOT / "scraper"

if str(_SCRAPER_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRAPER_DIR))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

load_dotenv(_REPO_ROOT / ".env")

BIGGY_SOURCE_CAMPAIGN_ID = "2cd03978-93b3-4462-ad88-f0fb0f35d59c"
COMPTABLE_TARGET_CAMPAIGN_ID = "5591a068-75f9-4826-8564-4dc2acc74bd4"

_LINK_REPLACEMENTS = (
    ("{{reservation_agence_link}}", "{{reservation_entreprise_link}}"),
    ("{reservation_agence_link}", "{reservation_entreprise_link}"),
    ("{{link}}", "{{reservation_entreprise_link}}"),
    ("{link}", "{reservation_entreprise_link}"),
)


def _swap_booking_link(text: str) -> str:
    result = text
    for old, new in _LINK_REPLACEMENTS:
        result = result.replace(old, new)
    return result


def _extract_campaign_emails(campaign: dict[str, Any]) -> list[dict[str, str]]:
    sequences = campaign.get("sequences") or []
    if not sequences or not isinstance(sequences, list):
        return []
    steps = sequences[0].get("steps") if isinstance(sequences[0], dict) else []
    if not isinstance(steps, list):
        return []

    emails: list[dict[str, str]] = []
    for step in steps:
        if not isinstance(step, dict) or step.get("type") != "email":
            continue
        variants = step.get("variants") or []
        if not variants or not isinstance(variants[0], dict):
            continue
        subject = str(variants[0].get("subject") or "").strip()
        body = str(variants[0].get("body") or "").strip()
        if subject and body:
            emails.append({"subject": subject, "body": body})
    return emails


def clone_campaign_emails(
    *,
    source_campaign_id: str,
    target_campaign_id: str,
    api_key: str,
    dry_run: bool = False,
    force: bool = False,
    default_delay_days: int = 3,
) -> dict[str, Any]:
    from instantly_client import (
        campaign_has_sequence_emails,
        get_campaign,
        patch_campaign_sequences,
    )

    if not force and campaign_has_sequence_emails(api_key, target_campaign_id, min_steps=2):
        return {
            "skipped": True,
            "reason": "target already has 2+ email steps",
            "target_campaign_id": target_campaign_id,
        }

    source = get_campaign(api_key, source_campaign_id)
    raw_emails = _extract_campaign_emails(source)
    if len(raw_emails) < 2:
        raise RuntimeError(
            f"Source campaign {source_campaign_id} has fewer than 2 email steps "
            f"(found {len(raw_emails)})"
        )

    cloned = [
        {
            "subject": _swap_booking_link(email["subject"]),
            "body": _swap_booking_link(email["body"]),
        }
        for email in raw_emails[:2]
    ]

    if dry_run:
        return {
            "dry_run": True,
            "source_campaign_id": source_campaign_id,
            "target_campaign_id": target_campaign_id,
            "emails": [
                {"subject": e["subject"], "body_preview": e["body"][:120]}
                for e in cloned
            ],
        }

    patch_campaign_sequences(
        api_key,
        target_campaign_id,
        cloned,
        default_delay_days=default_delay_days,
    )
    return {
        "skipped": False,
        "source_campaign_id": source_campaign_id,
        "target_campaign_id": target_campaign_id,
        "steps_patched": len(cloned),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Clone Instantly cold emails with entreprise CTA")
    parser.add_argument(
        "--source",
        default=BIGGY_SOURCE_CAMPAIGN_ID,
        help="Source campaign UUID (default: Biggy Agency)",
    )
    parser.add_argument(
        "--target",
        default=COMPTABLE_TARGET_CAMPAIGN_ID,
        help="Target campaign UUID (default: comptable)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Patch even if target already has 2 email steps",
    )
    args = parser.parse_args()

    api_key = os.getenv("INSTANTLY_API_KEY", "").strip()
    if not api_key and not args.dry_run:
        print("INSTANTLY_API_KEY is required", file=sys.stderr)
        sys.exit(1)

    result = clone_campaign_emails(
        source_campaign_id=args.source.strip(),
        target_campaign_id=args.target.strip(),
        api_key=api_key,
        dry_run=args.dry_run,
        force=args.force,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
