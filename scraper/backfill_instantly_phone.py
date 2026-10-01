"""PATCH phone numbers onto existing Instantly leads from local CSV index."""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable

from backfill_instantly_columns import load_csv_index
from config_loader import load_config
from instantly_client import _normalize_email, _read_email, paginate_list_leads, patch_lead

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STATE_PATH = os.path.join(_LIB_DIR, "output", "backfill_reception_phone_state.json")
DEFAULT_REPORT_PATH = os.path.join(_LIB_DIR, "output", "backfill_reception_phone_report.json")
RECEPTION_LIST_ID = "5fa7d7e3-07fc-4ba6-8ce6-0b4e55780884"


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def patch_phone_body(phone: str) -> dict[str, Any]:
    phone = _safe_str(phone)
    return {
        "phone": phone,
        "custom_variables": {"phone": phone},
    }


def _lead_has_phone(item: dict[str, Any]) -> bool:
    if _safe_str(item.get("phone")):
        return True
    custom_vars = item.get("custom_variables")
    if not isinstance(custom_vars, dict):
        payload = item.get("payload")
        custom_vars = payload if isinstance(payload, dict) else {}
    return bool(_safe_str(custom_vars.get("phone")))


def _load_checkpoint(path: str) -> set[str]:
    if not os.path.isfile(path):
        return set()
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return {_normalize_email(str(email)) for email in (data.get("processed_emails") or []) if email}


def _save_checkpoint(path: str, processed_emails: set[str], meta: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "processed_emails": sorted(processed_emails),
        **meta,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


async def backfill_phone_list(
    api_key: str,
    list_id: str,
    preset_ids: list[str],
    *,
    dry_run: bool = False,
    force: bool = False,
    limit: int = 0,
    concurrency: int = 25,
    data_root: str | None = None,
    state_path: str = DEFAULT_STATE_PATH,
    report_path: str = DEFAULT_REPORT_PATH,
    log_cb: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    def _log(msg: str) -> None:
        if log_cb:
            log_cb(msg)

    started = time.time()
    list_id = list_id.strip()
    preset_ids = [preset.strip() for preset in preset_ids if preset.strip()]
    if not preset_ids:
        raise ValueError("At least one preset id is required")

    csv_index, _ = load_csv_index(preset_ids, data_root=data_root)
    phones_by_email = {
        email: _safe_str(row.get("Phone"))
        for email, row in csv_index.items()
        if _safe_str(row.get("Phone"))
    }
    _log(f"CSV phone index: {len(phones_by_email)} email(s) with Phone")

    processed_emails = _load_checkpoint(state_path)
    if processed_emails:
        _log(f"Checkpoint: {len(processed_emails)} email(s) already processed")

    leads = paginate_list_leads(
        api_key,
        list_id,
        on_progress=lambda count: _log(f"  fetched {count} Instantly lead(s)..."),
    )
    _log(f"Instantly list {list_id}: {len(leads)} lead(s)")

    stats = {
        "patched": 0,
        "skipped": 0,
        "dry_run_count": 0,
        "failed": 0,
        "no_csv_phone": 0,
        "already_has_phone": 0,
        "sample_patches": [],
    }
    errors: list[dict[str, str]] = []
    patch_sem = asyncio.Semaphore(max(concurrency, 1))

    async def _process_lead(item: dict[str, Any]) -> None:
        email = _read_email(item)
        lead_id = str(item.get("id") or "").strip()
        if not email or not lead_id:
            return
        if email in processed_emails:
            stats["skipped"] += 1
            return

        phone = phones_by_email.get(email)
        if not phone:
            stats["no_csv_phone"] += 1
            return

        if not force and _lead_has_phone(item):
            stats["already_has_phone"] += 1
            processed_emails.add(email)
            return

        body = patch_phone_body(phone)
        if dry_run:
            stats["dry_run_count"] += 1
            if len(stats["sample_patches"]) < 5:
                stats["sample_patches"].append(
                    {"email": email, "lead_id": lead_id, "patch_body": body}
                )
            return

        try:
            async with patch_sem:
                await asyncio.to_thread(patch_lead, api_key, lead_id, body)
            stats["patched"] += 1
            processed_emails.add(email)
        except Exception as exc:  # noqa: BLE001
            stats["failed"] += 1
            errors.append({"email": email, "lead_id": lead_id, "error": str(exc)})

    candidates = leads[:limit] if limit > 0 else leads
    await asyncio.gather(*[_process_lead(item) for item in candidates])

    if not dry_run:
        _save_checkpoint(
            state_path,
            processed_emails,
            {
                "list_id": list_id,
                "patched": stats["patched"],
                "skipped": stats["skipped"],
                "failed": stats["failed"],
            },
        )

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "list_id": list_id,
        "preset_ids": preset_ids,
        "dry_run": dry_run,
        "force": force,
        "limit": limit,
        "concurrency": concurrency,
        "instantly_total": len(leads),
        "processed": len(candidates),
        "csv_phones": len(phones_by_email),
        "duration_s": round(time.time() - started, 2),
        "errors": errors[:50],
        **stats,
    }

    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    _log(f"Report → {report_path}")
    return report


def default_reception_report_paths() -> tuple[str, str]:
    return DEFAULT_STATE_PATH, DEFAULT_REPORT_PATH
