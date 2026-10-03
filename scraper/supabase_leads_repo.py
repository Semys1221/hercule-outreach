"""Supabase persistence for migrated Instantly leads."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Callable

from supabase import Client, create_client

TABLE_NAME = "temporary_leads"
UPSERT_BATCH_SIZE = 500


def _env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1].strip()
    return value


@lru_cache(maxsize=1)
def get_client() -> Client:
    url = _env("SUPABASE_URL") or _env("NEXT_PUBLIC_SUPABASE_URL")
    key = _env("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    return create_client(url, key)


def count_temporary_leads(source_list_id: str) -> int:
    client = get_client()
    resp = (
        client.table(TABLE_NAME)
        .select("id", count="exact")
        .eq("source_list_id", source_list_id.strip())
        .execute()
    )
    return int(resp.count or 0)


def upsert_temporary_leads(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    client = get_client()
    written = 0
    for start in range(0, len(rows), UPSERT_BATCH_SIZE):
        batch = rows[start : start + UPSERT_BATCH_SIZE]
        client.table(TABLE_NAME).upsert(
            batch,
            on_conflict="email,source_list_id",
        ).execute()
        written += len(batch)
    return written


def export_list_leads_to_supabase(
    leads: list[dict[str, Any]],
    list_id: str,
    *,
    dry_run: bool = True,
    log_cb: Callable[[str], None] | None = None,
) -> dict[str, int]:
    from instantly_client import lead_item_to_row

    def _log(msg: str) -> None:
        if log_cb:
            log_cb(msg)

    rows: list[dict[str, Any]] = []
    skipped = 0
    for item in leads:
        row = lead_item_to_row(item, list_id)
        if row is None:
            skipped += 1
            continue
        rows.append(row)

    if dry_run:
        _log(f"Dry-run — {len(rows)} lead(s) would be upserted ({skipped} skipped without email).")
        return {
            "instantly_total": len(leads),
            "exportable": len(rows),
            "skipped": skipped,
            "upserted": 0,
            "supabase_total": count_temporary_leads(list_id) if rows else 0,
        }

    upserted = upsert_temporary_leads(rows)
    supabase_total = count_temporary_leads(list_id)
    _log(f"Upserted {upserted} lead(s) to {TABLE_NAME} (Supabase total: {supabase_total}).")
    return {
        "instantly_total": len(leads),
        "exportable": len(rows),
        "skipped": skipped,
        "upserted": upserted,
        "supabase_total": supabase_total,
    }
