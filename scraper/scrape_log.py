"""Persistent scrape log on disk (survives Streamlit reruns)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Callable


def scrape_log_path(out_dir: str) -> str:
    return os.path.join(out_dir, "scrape.log")


def append_scrape_log(out_dir: str, message: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    path = scrape_log_path(out_dir)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{stamp}] {message}\n"
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line)


def make_file_log_cb(out_dir: str, *, also: Callable[[str], None] | None = None) -> Callable[[str], None]:
    def _log(message: str) -> None:
        append_scrape_log(out_dir, message)
        if also:
            also(message)

    return _log


def tail_scrape_log(out_dir: str, *, max_lines: int = 80) -> str:
    path = scrape_log_path(out_dir)
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return ""
    return "".join(lines[-max_lines:])
