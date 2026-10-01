"""Persist and resume MEV verification progress across interruptions."""

from __future__ import annotations

import ast
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

from bulk_verifier import normalize_status
from paths import data_dir

CHECKPOINT_SUFFIX = "_checkpoint.json"
PARTIAL_VERIFIED_SUFFIX = "_verified_partial.csv"
LEGACY_LOG_PATTERN = re.compile(
    r"Raw API Response for ([^:]+):\s*(\{.*\})\s*$"
)


def checkpoint_path(prefix: str) -> str:
    return os.path.join(data_dir(), f"{prefix}{CHECKPOINT_SUFFIX}")


def partial_verified_path(prefix: str) -> str:
    return os.path.join(data_dir(), f"{prefix}{PARTIAL_VERIFIED_SUFFIX}")


def save_checkpoint(
    prefix: str,
    status_map: dict[str, str],
    *,
    total_target: int | None = None,
    source_artifact: str | None = None,
) -> str:
    os.makedirs(data_dir(), exist_ok=True)
    path = checkpoint_path(prefix)
    payload = {
        "artifact_prefix": prefix,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total_target": total_target,
        "source_artifact": source_artifact,
        "verified_count": len(status_map),
        "status_map": status_map,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    return path


def load_checkpoint(prefix: str) -> tuple[dict[str, str], dict[str, Any]] | None:
    path = checkpoint_path(prefix)
    if not os.path.isfile(path):
        return None

    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)

    status_map = payload.get("status_map") or {}
    normalized = {
        str(email).strip().lower(): normalize_status(status)
        for email, status in status_map.items()
        if str(email).strip()
    }
    return normalized, payload


def list_checkpoints() -> list[dict[str, Any]]:
    if not os.path.isdir(data_dir()):
        return []

    checkpoints: list[dict[str, Any]] = []
    for name in os.listdir(data_dir()):
        if not name.endswith(CHECKPOINT_SUFFIX):
            continue
        prefix = name[: -len(CHECKPOINT_SUFFIX)]
        loaded = load_checkpoint(prefix)
        if not loaded:
            continue
        status_map, payload = loaded
        checkpoints.append(
            {
                "prefix": prefix,
                "path": checkpoint_path(prefix),
                "verified_count": len(status_map),
                "total_target": payload.get("total_target"),
                "updated_at": payload.get("updated_at"),
                "source_artifact": payload.get("source_artifact"),
            }
        )

    checkpoints.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return checkpoints


def parse_legacy_terminal_log(text: str) -> dict[str, str]:
    """Recover statuses printed by the old single-email client."""
    status_map: dict[str, str] = {}
    for line in text.splitlines():
        match = LEGACY_LOG_PATTERN.search(line.strip())
        if not match:
            continue
        email = match.group(1).strip().lower()
        try:
            payload = ast.literal_eval(match.group(2))
        except (SyntaxError, ValueError):
            continue
        status = payload.get("Status") if isinstance(payload, dict) else None
        if email and status:
            status_map[email] = normalize_status(status)
    return status_map


def recover_checkpoint_from_log(
    log_path: str,
    prefix: str,
    *,
    total_target: int | None = None,
    source_artifact: str | None = None,
) -> tuple[str, dict[str, str]]:
    with open(log_path, encoding="utf-8", errors="replace") as handle:
        status_map = parse_legacy_terminal_log(handle.read())

    path = save_checkpoint(
        prefix,
        status_map,
        total_target=total_target,
        source_artifact=source_artifact,
    )
    return path, status_map


def save_partial_verified_csv(
    prefix: str,
    df,
    email_column: str,
    status_map: dict[str, str],
) -> str:
    """Write rows with known verification status so clean leads are not lost."""
    import pandas as pd

    working = df.copy()
    working["Verification_Status"] = working[email_column].apply(
        lambda value: status_map.get(str(value).strip().lower(), "")
    )
    known = working[working["Verification_Status"].astype(str).str.len() > 0].copy()
    path = partial_verified_path(prefix)
    known.to_csv(path, index=False)
    return path
