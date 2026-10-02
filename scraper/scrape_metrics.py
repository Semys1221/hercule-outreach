"""Worker heartbeat / cron tail helpers for Scrape UI (read-only)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any


def heartbeat_path(out_dir: str) -> str:
    return os.path.join(out_dir, "worker_heartbeat.json")


def cron_events_path(out_dir: str) -> str:
    return os.path.join(out_dir, "cron_events.jsonl")


def load_worker_heartbeat(out_dir: str) -> dict[str, Any] | None:
    path = heartbeat_path(out_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def tail_cron_events(out_dir: str, *, max_lines: int = 10) -> list[dict[str, Any]]:
    path = cron_events_path(out_dir)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return []
    events: list[dict[str, Any]] = []
    for line in lines[-max_lines:]:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                events.append(item)
        except json.JSONDecodeError:
            continue
    return events


def heartbeat_age_seconds(heartbeat: dict[str, Any] | None) -> float | None:
    if not heartbeat:
        return None
    raw = str(heartbeat.get("last_seen") or "").strip()
    if not raw:
        return None
    try:
        seen = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        return max((datetime.now(timezone.utc) - seen).total_seconds(), 0.0)
    except ValueError:
        return None
