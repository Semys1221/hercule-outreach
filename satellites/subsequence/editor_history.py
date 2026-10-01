"""Subsequence template version history (local SQLite)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import streamlit as st

_APP_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _APP_DIR.parents[2]
_HISTORY_DIR = _REPO_ROOT / "satellites" / "editor_history"
_REPLY_AGENT_DIR = _REPO_ROOT / "satellites" / "reply_agent"

for path in (_HISTORY_DIR, _REPLY_AGENT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from db import DOMAIN_SUBSEQUENCE, insert_version, resolve_niche_key  # noqa: E402
from streamlit_ui import (  # noqa: E402
    SUBSEQUENCE_ITEM_LABELS,
    read_version_note,
    render_version_history_panel,
    render_version_note_field,
    version_note_session_key,
)
from supabase_repo import save_template  # noqa: E402

TEMPLATE_KEYS = (
    "interested_email1",
    "interested_email2",
    "interested_email3",
)


def _resolve_preset_id(campaign_id: str) -> str | None:
    try:
        from presets import resolve_preset_for_campaign

        return resolve_preset_for_campaign(campaign_id)
    except Exception:
        return None


def niche_key_for_campaign(campaign_id: str) -> str:
    return resolve_niche_key(campaign_id, _resolve_preset_id(campaign_id))


def save_template_with_history(
    campaign_id: str,
    template_key: str,
    subject: str,
    body_html: str,
    *,
    sync_bootstrap_default: bool = False,
    version_label: str | None = None,
    key_prefix: str = "templates",
) -> dict[str, Any]:
    result = save_template(
        campaign_id,
        template_key,
        subject,
        body_html,
        sync_bootstrap_default=sync_bootstrap_default,
    )
    niche = niche_key_for_campaign(campaign_id)
    note = version_label or read_version_note(key_prefix)
    insert_version(
        domain=DOMAIN_SUBSEQUENCE,
        niche_key=niche,
        item_key=template_key,
        body_text=body_html,
        campaign_id=campaign_id,
        subject=subject,
        label=note,
    )
    st.session_state.pop(version_note_session_key(key_prefix), None)
    return result


def render_subsequence_history_tab(
    campaign_id: str,
    templates: list[dict[str, Any]],
    *,
    key_prefix: str = "templates",
) -> None:
    niche = niche_key_for_campaign(campaign_id)
    template_map = {t["template_key"]: t for t in templates}

    def get_current_content(item_key: str) -> tuple[str, str | None]:
        row = template_map.get(item_key, {})
        return str(row.get("subject") or ""), str(row.get("body_html") or "")

    def on_promote(row: dict[str, Any]) -> None:
        save_template(
            campaign_id,
            str(row["item_key"]),
            str(row.get("subject") or ""),
            str(row.get("body_text") or ""),
            sync_bootstrap_default=False,
        )

    def on_load_draft(item_key: str, body: str, subject: str | None) -> None:
        sub_key = f"{key_prefix}_sub_{campaign_id}_{item_key}"
        body_key = f"{key_prefix}_body_{campaign_id}_{item_key}"
        st.session_state[sub_key] = subject or ""
        st.session_state[body_key] = body

    render_version_history_panel(
        domain=DOMAIN_SUBSEQUENCE,
        niche_key=niche,
        campaign_id=campaign_id,
        item_keys=TEMPLATE_KEYS,
        item_labels=SUBSEQUENCE_ITEM_LABELS,
        get_current_content=get_current_content,
        on_promote=on_promote,
        on_load_draft=on_load_draft,
        key_prefix=f"{key_prefix}_hist_{campaign_id}",
    )


def render_subsequence_history_note(key_prefix: str) -> None:
    render_version_note_field(key_prefix)
