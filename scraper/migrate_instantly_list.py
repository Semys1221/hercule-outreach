"""Migrate an Instantly lead list to Supabase temporary_leads."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable

from instantly_client import (
    count_leads_in_list,
    paginate_list_leads,
    purge_leads_from_list,
)
from supabase_leads_repo import export_list_leads_to_supabase


def migrate_instantly_list(
    api_key: str,
    list_id: str,
    *,
    dry_run: bool = True,
    log_cb: Callable[[str], None] | None = None,
    report_path: str | None = None,
) -> dict[str, Any]:
    def _log(msg: str) -> None:
        if log_cb:
            log_cb(msg)

    started = time.time()
    list_id = list_id.strip()
    instantly_before = count_leads_in_list(api_key, list_id)
    _log(f"Instantly list {list_id}: {instantly_before} lead(s).")

    leads = paginate_list_leads(
        api_key,
        list_id,
        on_progress=lambda n: _log(f"  fetched {n} lead(s)..."),
    )
    _log(f"Fetched {len(leads)} lead record(s) from Instantly.")

    export_stats = export_list_leads_to_supabase(
        leads,
        list_id,
        dry_run=dry_run,
        log_cb=log_cb,
    )

    purge_deleted = 0
    instantly_after = instantly_before
    if not dry_run:
        if export_stats["exportable"] == 0 and instantly_before > 0:
            raise RuntimeError(
                f"No exportable leads ({export_stats['skipped']} skipped) — aborting purge."
            )
        if export_stats["supabase_total"] < export_stats["exportable"]:
            raise RuntimeError(
                "Supabase count lower than exportable rows — aborting purge."
            )
        _log(f"Purging Instantly list {list_id}...")
        purge_deleted = purge_leads_from_list(api_key, list_id, log_cb=log_cb)
        instantly_after = count_leads_in_list(api_key, list_id)
        _log(f"Instantly list after purge: {instantly_after} lead(s).")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "list_id": list_id,
        "dry_run": dry_run,
        "instantly_before": instantly_before,
        "instantly_fetched": len(leads),
        "instantly_after": instantly_after,
        "purge_deleted": purge_deleted,
        "duration_s": round(time.time() - started, 2),
        **export_stats,
    }

    if report_path:
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        _log(f"Report → {report_path}")

    return report
