"""Persist AI reply prompts to disk and Supabase prod snapshot."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from config import prompts_dir
from supabase_repo import save_config


def prompt_file_path(preset_id: str, target_type: str) -> Path:
    return prompts_dir() / f"{preset_id}_{target_type}.md"


def write_prompt_file(preset_id: str, target_type: str, text: str) -> None:
    path = prompt_file_path(preset_id, target_type)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def can_push_prompt_to_prod(
    config: dict[str, Any] | None,
    campaign_id: str,
    preset_id: str,
    target_type: str,
) -> tuple[bool, str | None]:
    if not config:
        return False, "no_config"

    expected_key = f"{preset_id}_{target_type}"
    if str(config.get("prompt_key") or "") != expected_key:
        return False, "prompt_key_mismatch"

    status = str(config.get("status") or "")
    if status not in ("waiting_for_replies", "paused"):
        return False, "not_active"

    if not config.get("initialized_at"):
        return False, "missing_initialized_at"

    return True, None


def save_prompt(
    preset_id: str,
    target_type: str,
    text: str,
    *,
    campaign_id: str | None = None,
    config: dict[str, Any] | None = None,
    push_prod: bool = True,
) -> dict[str, Any]:
    write_prompt_file(preset_id, target_type, text)

    prod = False
    reason: str | None = None
    if push_prod and campaign_id and config:
        can_push, reason = can_push_prompt_to_prod(
            config,
            campaign_id,
            preset_id,
            target_type,
        )
        if can_push:
            row = dict(config)
            row["prompt_snapshot"] = text
            save_config(row)
            prod = True
    elif push_prod and not campaign_id:
        reason = "no_campaign"

    return {"file": True, "prod": prod, "reason": reason}
