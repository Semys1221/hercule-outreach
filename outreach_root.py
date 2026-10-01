"""Resolve hercule-outreach repo root for env loading and satellite paths."""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent


def outreach_root() -> Path:
    override = os.getenv("OUTREACH_ROOT", "").strip()
    if override:
        return Path(override).resolve()
    return _REPO_ROOT


def ensure_repo_on_path() -> Path:
    root = outreach_root()
    root_str = str(root)
    if root_str not in os.sys.path:
        os.sys.path.insert(0, root_str)
    return root
