"""Upsert scraped leads into Supabase prospect_pool (SaaS autonomous).

Usage:
  python -m app.streamlit_scraper.pool_filler \\
    --csv path/to/outscraper_leads.csv \\
    --niche restaurant \\
    --preset restaurants_independants

Requires env: NEXT_PUBLIC_SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path
from typing import Any

try:
    from supabase import create_client
except ImportError:  # pragma: no cover
    create_client = None  # type: ignore[assignment]

VALID_NICHES = ("restaurant", "sante", "btp")
BATCH_SIZE = 200


def _normalize_email(raw: str) -> str:
    return (raw or "").strip().lower()


def _load_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader)


def _pick_email(row: dict[str, str]) -> str:
    for key in ("email", "Email", "emails", "contact_email"):
        value = row.get(key) or ""
        if "@" in value:
            # Outscraper sometimes returns semicolon-separated emails
            return _normalize_email(value.split(";")[0].split(",")[0])
    return ""


def _pick_company(row: dict[str, str]) -> str | None:
    for key in ("name", "company_name", "business_name", "title"):
        value = (row.get(key) or "").strip()
        if value:
            return value
    return None


def upsert_prospects(
    *,
    csv_path: Path,
    niche: str,
    preset: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    if niche not in VALID_NICHES:
        raise SystemExit(f"Invalid niche {niche!r}; expected one of {VALID_NICHES}")

    rows = _load_rows(csv_path)
    payloads: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        email = _pick_email(row)
        if not email or email in seen:
            continue
        seen.add(email)
        payloads.append(
            {
                "email": email,
                "niche": niche,
                "source_preset": preset,
                "company_name": _pick_company(row),
                "status": "available",
            }
        )

    if dry_run or not payloads:
        return {
            "read": len(rows),
            "unique": len(payloads),
            "upserted": 0,
            "dry_run": dry_run,
        }

    if create_client is None:
        raise SystemExit("supabase package required: pip install supabase")

    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise SystemExit("NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")

    sb = create_client(url, key)
    upserted = 0
    for i in range(0, len(payloads), BATCH_SIZE):
        chunk = payloads[i : i + BATCH_SIZE]
        # Only insert new emails — ignore conflicts (already in pool)
        result = (
            sb.table("prospect_pool")
            .upsert(chunk, on_conflict="email,niche", ignore_duplicates=True)
            .execute()
        )
        upserted += len(result.data or chunk)

    return {
        "read": len(rows),
        "unique": len(payloads),
        "upserted": upserted,
        "dry_run": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--niche", required=True, choices=VALID_NICHES)
    parser.add_argument("--preset", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.csv.exists():
        print(f"CSV not found: {args.csv}", file=sys.stderr)
        return 1

    stats = upsert_prospects(
        csv_path=args.csv,
        niche=args.niche,
        preset=args.preset,
        dry_run=args.dry_run,
    )
    print(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
