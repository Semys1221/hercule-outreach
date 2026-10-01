"""Paths for local editor history SQLite."""

from __future__ import annotations

import os
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent


def history_db_path() -> Path:
    override = os.getenv("STREAMLIT_EDITOR_HISTORY_DB", "").strip()
    if override:
        return Path(override).expanduser()
    return _PACKAGE_DIR / ".data" / "editor_history.sqlite"
