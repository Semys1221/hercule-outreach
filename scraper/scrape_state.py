"""Scrape run state helpers for Streamlit UI (read-only)."""

from __future__ import annotations

import json
import os
from typing import Any

STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_INCOMPLETE = "incomplete"

CHECKPOINT_PUSH_MODES = frozenset({"instantly_pushed", "instantly_pushed_run"})
LIVE_LIST_TARGET_MODES = frozenset({"instantly_pushed"})
VALID_TARGET_MODES = frozenset({"csv_saved", "instantly_pushed", "instantly_pushed_run"})


def target_mode(config: dict) -> str:
    return str(config.get("TARGET_MODE") or "csv_saved").strip()


def target_uses_live_list(mode: str) -> bool:
    return mode in LIVE_LIST_TARGET_MODES


def target_uses_checkpoint_push(mode: str) -> bool:
    return mode in CHECKPOINT_PUSH_MODES


def is_instantly_push_mode(mode: str) -> bool:
    return mode in CHECKPOINT_PUSH_MODES


def target_progress_value(
    mode: str,
    *,
    instantly_pushed: int = 0,
    leads_saved: int = 0,
    instantly_live: int | None = None,
) -> int:
    if mode in CHECKPOINT_PUSH_MODES:
        if target_uses_live_list(mode) and instantly_live is not None:
            return instantly_live
        return instantly_pushed
    return leads_saved


def load_scrape_state(state_path: str) -> dict[str, Any] | None:
    if not os.path.isfile(state_path):
        return None
    try:
        with open(state_path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def ui_target_progress(
    config: dict,
    state: dict[str, Any] | None,
    *,
    instantly_live: int | None = None,
) -> tuple[int, int, bool]:
    """Return (progress, target, at_target) from manifest config + scrape_state."""
    target = int(config.get("TARGET_LEADS", 0))
    mode = target_mode(config)
    leads_saved = int(state.get("leads_saved", 0)) if state else 0
    instantly_pushed = int(state.get("instantly_pushed", 0)) if state else 0
    progress = target_progress_value(
        mode,
        instantly_pushed=instantly_pushed,
        leads_saved=leads_saved,
        instantly_live=instantly_live,
    )
    at_target = progress >= target > 0
    return progress, target, at_target
