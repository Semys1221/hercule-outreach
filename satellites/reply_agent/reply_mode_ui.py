"""Reply Mode UI helpers — selectable read-only text, sentence toggle, Custom AI panel."""

from __future__ import annotations

import html
from collections.abc import Callable
from typing import Any

import streamlit as st

from grok_usage import usage_severity
from grok_usage_ui import get_cached_grok_usage_snapshot
from pending_table_state import (
    custom_directive_key,
    get_custom_ai_open,
    get_custom_directive,
    get_sentence_count,
    set_custom_ai_open,
    set_sentence_count,
)


def render_selectable_readonly(text: str, *, height_px: int = 200) -> None:
    """Render read-only text that users can select and copy."""
    escaped = html.escape(text or "(vide)")
    st.markdown(
        f"""
        <div style="
            height: {height_px}px;
            overflow-y: auto;
            padding: 0.75rem;
            border: 1px solid rgba(49, 51, 63, 0.2);
            border-radius: 0.5rem;
            background-color: rgba(240, 242, 246, 0.5);
            white-space: pre-wrap;
            word-wrap: break-word;
            user-select: text;
            -webkit-user-select: text;
            font-family: 'Source Sans Pro', sans-serif;
            font-size: 0.875rem;
            line-height: 1.6;
            color: rgb(49, 51, 63);
        ">{escaped}</div>
        """,
        unsafe_allow_html=True,
    )


def render_sentence_count_toggle(
    campaign_id: str,
    lead_email: str,
) -> int:
    """Render − / count / + controls. Returns current sentence count (1–10)."""
    email_key = lead_email.lower()
    count = get_sentence_count(campaign_id, lead_email)

    label_col, minus_col, count_col, plus_col = st.columns([2, 0.6, 0.6, 0.6])
    with label_col:
        st.caption("Phrases")
    with minus_col:
        if st.button(
            "−",
            key=f"reply_mode_sent_minus_{campaign_id}_{email_key}",
            disabled=count <= 1,
        ):
            set_sentence_count(campaign_id, lead_email, count - 1)
            st.rerun()
    with count_col:
        st.markdown(f"**{count}**")
    with plus_col:
        if st.button(
            "+",
            key=f"reply_mode_sent_plus_{campaign_id}_{email_key}",
            disabled=count >= 10,
        ):
            set_sentence_count(campaign_id, lead_email, count + 1)
            st.rerun()

    return get_sentence_count(campaign_id, lead_email)


def render_custom_ai_panel(
    *,
    campaign_id: str,
    lead_email: str,
    config: dict[str, Any],
    inbound_body: str,
    on_generated: Callable[[str], None],
    interest_label: str | None = None,
) -> None:
    """Toggle Custom AI panel and run Grok regeneration on demand."""
    from agent_preview import generate_reply_preview

    email_key = lead_email.lower()
    open_key = f"reply_mode_custom_ai_toggle_{campaign_id}_{email_key}"
    directive_input_key = custom_directive_key(campaign_id, lead_email)
    generate_key = f"reply_mode_custom_ai_generate_{campaign_id}_{email_key}"

    is_open = get_custom_ai_open(campaign_id, lead_email)

    if st.button(
        "Custom AI",
        key=open_key,
        type="secondary" if not is_open else "primary",
    ):
        set_custom_ai_open(campaign_id, lead_email, not is_open)
        st.rerun()

    if not is_open:
        return

    render_sentence_count_toggle(campaign_id, lead_email)

    quota_snapshot = get_cached_grok_usage_snapshot()
    if usage_severity(quota_snapshot) in ("warn", "critical"):
        st.caption("Quota Grok bas — évitez les regénérations inutiles.")

    if directive_input_key not in st.session_state:
        st.session_state[directive_input_key] = get_custom_directive(campaign_id, lead_email)

    directive = st.text_area(
        "Directive custom",
        height=80,
        key=directive_input_key,
        placeholder="Ex. : insiste sur la gratuité entreprise, ton plus direct…",
        label_visibility="collapsed",
    )

    if st.button("Générer", key=generate_key, type="primary"):
        sentence_count = get_sentence_count(campaign_id, lead_email)
        trimmed_directive = str(directive or "").strip()
        with st.spinner("Génération IA…"):
            try:
                preview = generate_reply_preview(
                    config,
                    inbound_body,
                    lead_email,
                    custom_directive=trimmed_directive or None,
                    max_sentences=sentence_count,
                    interest_label=interest_label,
                )
            except Exception as exc:
                st.error(str(exc))
                return

        if preview.get("should_reply") and preview.get("reply_text"):
            on_generated(str(preview["reply_text"]))
            st.rerun()
        else:
            reason = str(preview.get("reason") or "L'IA a choisi de ne pas répondre.")
            st.warning(reason)
