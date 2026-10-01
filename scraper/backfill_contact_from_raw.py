"""Backfill Phone / Rating / ReviewsCount from outscraper_raw.jsonl into CSV leads."""

from __future__ import annotations

import csv
import json
import os
from typing import Any, Callable

from core_logic import (
    _CSV_COLUMNS,
    _extract_email,
    _outscraper_phone,
    _outscraper_rating,
    _outscraper_reviews,
)
from outreach_data import scraper_output_base

CONTACT_COLUMNS = ("Phone", "Rating", "ReviewsCount")


def contact_fields_from_business(business: dict[str, Any]) -> dict[str, str]:
    return {
        "Phone": _outscraper_phone(business),
        "Rating": _outscraper_rating(business),
        "ReviewsCount": _outscraper_reviews(business),
    }


def build_contact_index_from_raw(
    jsonl_path: str,
) -> dict[str, dict[str, str]]:
    """Map normalized email -> best contact fields seen in raw Outscraper rows."""
    index: dict[str, dict[str, str]] = {}

    if not os.path.isfile(jsonl_path):
        return index

    with open(jsonl_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                business = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(business, dict):
                continue

            email = (_extract_email(business) or "").strip().lower()
            if not email:
                continue

            fields = contact_fields_from_business(business)
            existing = index.get(email)
            if existing is None:
                index[email] = fields
                continue

            for column in CONTACT_COLUMNS:
                if fields.get(column) and not existing.get(column):
                    existing[column] = fields[column]

    return index


def backfill_preset_contacts(
    preset_id: str,
    *,
    data_root: str | None = None,
    dry_run: bool = False,
    log_cb: Callable[[str], None] | None = None,
) -> dict[str, int]:
    def _log(msg: str) -> None:
        if log_cb:
            log_cb(msg)

    base = data_root or scraper_output_base()
    out_dir = os.path.join(base, preset_id)
    csv_path = os.path.join(out_dir, "outscraper_leads.csv")
    jsonl_path = os.path.join(out_dir, "outscraper_raw.jsonl")

    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    contact_index = build_contact_index_from_raw(jsonl_path)
    _log(f"{preset_id}: {len(contact_index)} email(s) with raw contact data")

    with open(csv_path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    stats = {"rows": len(rows), "phone_updated": 0, "rating_updated": 0, "reviews_updated": 0}

    for row in rows:
        email = (row.get("Email") or "").strip().lower()
        contact = contact_index.get(email)
        if not contact:
            continue
        for column in CONTACT_COLUMNS:
            value = (contact.get(column) or "").strip()
            if not value:
                continue
            if not (row.get(column) or "").strip():
                row[column] = value
                if column == "Phone":
                    stats["phone_updated"] += 1
                elif column == "Rating":
                    stats["rating_updated"] += 1
                else:
                    stats["reviews_updated"] += 1

    if dry_run:
        _log(
            f"{preset_id} dry-run — would update phone={stats['phone_updated']}, "
            f"rating={stats['rating_updated']}, reviews={stats['reviews_updated']}"
        )
        return stats

    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: (row.get(column) or "") for column in _CSV_COLUMNS})

    _log(
        f"{preset_id} updated — phone={stats['phone_updated']}, "
        f"rating={stats['rating_updated']}, reviews={stats['reviews_updated']}"
    )
    return stats


def backfill_contacts(
    preset_ids: list[str],
    *,
    data_root: str | None = None,
    dry_run: bool = False,
    log_cb: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    totals = {
        "presets": preset_ids,
        "dry_run": dry_run,
        "phone_updated": 0,
        "rating_updated": 0,
        "reviews_updated": 0,
        "by_preset": {},
    }
    for preset_id in preset_ids:
        stats = backfill_preset_contacts(
            preset_id,
            data_root=data_root,
            dry_run=dry_run,
            log_cb=log_cb,
        )
        totals["by_preset"][preset_id] = stats
        totals["phone_updated"] += stats["phone_updated"]
        totals["rating_updated"] += stats["rating_updated"]
        totals["reviews_updated"] += stats["reviews_updated"]
    return totals
