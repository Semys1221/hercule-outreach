"""Reply agent prompt version history (local SQLite)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import streamlit as st

_APP_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _APP_DIR.parents[2]
_HISTORY_DIR = _REPO_ROOT / "satellites" / "editor_history"

if str(_HISTORY_DIR) not in sys.path:
    sys.path.insert(0, str(_HISTORY_DIR))

from db import DOMAIN_REPLY_PROMPT, insert_version  # noqa: E402
from prompt_store import save_prompt  # noqa: E402
from streamlit_ui import (  # noqa: E402
    REPLY_ITEM_LABELS,
    read_version_note,
    render_version_history_panel,
    render_version_note_field,
    version_note_session_key,
)

REPLY_ITEM_KEYS = ("buyer", "seller")


def record_prompt_save(
    *,
    preset_id: str,
    target_type: str,
    text: str,
    campaign_id: str | None,
    config: dict[str, Any] | None,
    push_prod: bool = True,
    version_label: str | None = None,
    key_prefix: str = "prompt",
) -> dict[str, Any]:
    result = save_prompt(
        preset_id,
        target_type,
        text,
        campaign_id=campaign_id,
        config=config,
        push_prod=push_prod,
    )
    note = version_label or read_version_note(key_prefix)
    insert_version(
        domain=DOMAIN_REPLY_PROMPT,
        niche_key=preset_id,
        item_key=target_type,
        body_text=text,
        campaign_id=campaign_id,
        label=note,
    )
    st.session_state.pop(version_note_session_key(key_prefix), None)
    return result


def render_reply_prompt_history_tab(
    *,
    campaign_id: str,
    niche_preset_id: str,
    target_type: str,
    config: dict[str, Any] | None,
    load_prompt_text: Any,
    editor_key: str,
    key_prefix: str = "prompt",
) -> None:
    def get_current_content(item_key: str) -> tuple[str, str | None]:
        if item_key != target_type:
            body = load_prompt_text(niche_preset_id, item_key)
            return None, body
        if config and str(config.get("prompt_snapshot") or "").strip():
            return None, str(config.get("prompt_snapshot"))
        return None, load_prompt_text(niche_preset_id, item_key)

    def on_promote(row: dict[str, Any]) -> None:
        save_prompt(
            niche_preset_id,
            str(row["item_key"]),
            str(row.get("body_text") or ""),
            campaign_id=campaign_id,
            config=config,
        )

    def on_load_draft(item_key: str, body: str, _subject: str | None) -> None:
        if item_key == target_type:
            st.session_state[editor_key] = body

    render_version_history_panel(
        domain=DOMAIN_REPLY_PROMPT,
        niche_key=niche_preset_id,
        campaign_id=campaign_id,
        item_keys=REPLY_ITEM_KEYS,
        item_labels=REPLY_ITEM_LABELS,
        get_current_content=get_current_content,
        on_promote=on_promote,
        on_load_draft=on_load_draft,
        key_prefix=f"{key_prefix}_hist_{campaign_id}_{niche_preset_id}",
    )


def render_reply_history_note(key_prefix: str) -> None:
    render_version_note_field(key_prefix)
