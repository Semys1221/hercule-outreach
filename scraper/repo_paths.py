"""Repo root and satellite app paths for scraper bootstrap."""

from __future__ import annotations

import os
from pathlib import Path


def outreach_root() -> Path:
    override = os.getenv("OUTREACH_ROOT", "").strip()
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parent.parent


def subsequence_app() -> Path:
    return outreach_root() / "satellites" / "subsequence"


def reply_agent_app() -> Path:
    return outreach_root() / "satellites" / "reply_agent"


def reply_prompts_dir() -> Path:
    return reply_agent_app() / "prompts"
