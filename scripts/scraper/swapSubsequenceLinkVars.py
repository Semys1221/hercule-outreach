#!/usr/bin/env python3
"""Swap reservation_agence_link → reservation_entreprise_link in subsequence templates."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUBSEQUENCE_DIR = _REPO_ROOT / "satellites" / "subsequence"
_SCRAPER_DIR = _REPO_ROOT / "scraper"

for path in (str(_REPO_ROOT), str(_SUBSEQUENCE_DIR), str(_SCRAPER_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

load_dotenv(_REPO_ROOT / ".env")

COMPTABLE_CAMPAIGN_ID = "5591a068-75f9-4826-8564-4dc2acc74bd4"
COMPTABLE_SUBSEQUENCE_ID = "7105ed91-f2b7-4316-96c9-76a3c374cd6e"

_REPLACEMENTS = (
    ("{{reservation_agence_link}}", "{{reservation_entreprise_link}}"),
    ("{reservation_agence_link}", "{reservation_entreprise_link}"),
    ("{{link}}", "{{reservation_entreprise_link}}"),
    ("{link}", "{reservation_entreprise_link}"),
)

_TEMPLATE_KEYS = (
    "interested_email1",
    "interested_email2",
    "interested_email3",
    "no_show_email1",
    "no_show_email2",
)


def _swap(text: str) -> str:
    result = text
    for old, new in _REPLACEMENTS:
        result = result.replace(old, new)
    return result


def swap_templates(
    campaign_id: str,
    *,
    dry_run: bool = False,
    sync_instantly: bool = True,
    subsequence_id: str = "",
) -> dict[str, Any]:
    from supabase_repo import get_client, list_templates, save_template

    client = get_client()
    rows = list_templates(campaign_id)
    updated_keys: list[str] = []

    for key in _TEMPLATE_KEYS:
        row = next((r for r in rows if str(r.get("template_key") or "") == key), None)
        if not row:
            continue
        subject = str(row.get("subject") or "")
        body = str(row.get("body_html") or "")
        if not body.strip():
            continue
        new_subject = _swap(subject)
        new_body = _swap(body)
        if new_subject == subject and new_body == body:
            continue
        updated_keys.append(key)
        if not dry_run:
            save_template(
                campaign_id,
                key,
                new_subject,
                new_body,
                sync_bootstrap_default=(key == "interested_email1"),
            )

    instantly_synced = False
    if sync_instantly and not dry_run and updated_keys and subsequence_id:
        from instantly_client import patch_subsequence_sequences
        from shared.instantly_client import get_api_key

        api_key = get_api_key()
        if api_key:
            refreshed = list_templates(campaign_id)
            emails = []
            for key in ("interested_email1", "interested_email2", "interested_email3"):
                row = next(
                    (r for r in refreshed if str(r.get("template_key") or "") == key),
                    None,
                )
                if row and str(row.get("body_html") or "").strip():
                    emails.append(
                        {
                            "subject": str(row.get("subject") or ""),
                            "body": str(row.get("body_html") or ""),
                        }
                    )
            if emails:
                patch_subsequence_sequences(
                    api_key,
                    subsequence_id,
                    emails,
                    default_delay_days=1,
                )
                instantly_synced = True

    return {
        "campaign_id": campaign_id,
        "subsequence_id": subsequence_id or None,
        "updated_keys": updated_keys,
        "instantly_synced": instantly_synced,
        "dry_run": dry_run,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Swap agence CTA to entreprise in subsequence templates")
    parser.add_argument("--campaign-id", default=COMPTABLE_CAMPAIGN_ID)
    parser.add_argument("--subsequence-id", default=COMPTABLE_SUBSEQUENCE_ID)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-instantly", action="store_true")
    args = parser.parse_args()

    result = swap_templates(
        args.campaign_id.strip(),
        dry_run=args.dry_run,
        sync_instantly=not args.no_instantly,
        subsequence_id=args.subsequence_id.strip(),
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
