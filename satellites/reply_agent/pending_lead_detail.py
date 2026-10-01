"""Lead detail dialog for Pending Unibox (See more)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

from pending_fetch import PendingReplyRow, is_reply_over_24h
from pending_table_state import detail_email_key, ensure_draft, reply_draft_key
from supabase_repo import get_lead_reply, upsert_lead_reply
from unibox_thread import render_conversation_html


def _config_summary(config: dict[str, Any] | None) -> str:
    if not config:
        return "Campagne non configurée."
    niche = config.get("niche_preset_id") or "—"
    target = config.get("target_type") or "—"
    status = config.get("status") or "—"
    snapshot = str(config.get("prompt_snapshot") or "").strip()
    excerpt = snapshot[:300] + ("…" if len(snapshot) > 300 else "")
    return (
        f"**Niche:** {niche} · **Target:** {target} · **Status:** {status}\n\n"
        f"**Prompt (extrait):**\n\n{excerpt or '—'}"
    )


@st.fragment
def _render_lead_draft_editor(campaign_id: str, row: PendingReplyRow) -> None:
    st.markdown("#### Draft IA")
    draft_key = reply_draft_key(campaign_id, row.lead_email)
    ensure_draft(campaign_id, row.lead_email, get_lead_reply(campaign_id, row.lead_email))
    st.text_area(
        "Réponse agent",
        height=160,
        key=draft_key,
    )

    save_col, close_col = st.columns(2)
    with save_col:
        if st.button("Sauvegarder draft", key=f"save_detail_{campaign_id}_{row.lead_email}"):
            draft_text = str(st.session_state.get(draft_key, "") or "").strip()
            if not draft_text:
                st.warning("Le draft ne peut pas être vide.")
            else:
                upsert_lead_reply(campaign_id, row.lead_email, draft_text)
                st.success("Draft enregistré.")
    with close_col:
        if st.button("Fermer", key=f"close_detail_{campaign_id}_{row.lead_email}"):
            st.session_state.pop(detail_email_key(campaign_id), None)
            st.rerun()


@st.dialog("Lead detail", width="large")
def show_lead_detail(
    *,
    instantly_client: Any,
    campaign_id: str,
    config: dict | None,
    row: PendingReplyRow,
    get_thread_messages: Callable[..., list[dict]],
) -> None:
    st.markdown(f"### {row.lead_email}")
    if is_reply_over_24h(row.last_reply_at):
        st.warning("En attente depuis plus de 24h.")
    st.caption(
        f"Sujet: {row.last_reply_subject or '—'} · "
        f"Tag: {row.interest_label} · "
        f"Dernière réponse: {(row.last_reply_at or '')[:16]}"
    )

    col_left, col_right = st.columns([1, 1])
    with col_left:
        st.markdown("#### Dernière réponse prospect")
        st.write(row.last_reply_preview or "(vide)")
        st.markdown("#### Configuration actuelle")
        st.markdown(_config_summary(config))

    with col_right:
        st.markdown("#### Conversation Unibox")
        try:
            thread = get_thread_messages(
                instantly_client,
                campaign_id=campaign_id,
                lead_email=row.lead_email,
                thread_id=row.thread_id or None,
            )
            st.markdown(render_conversation_html(thread), unsafe_allow_html=True)
        except Exception as exc:
            st.warning(f"Unibox indisponible : {exc}")

    _render_lead_draft_editor(campaign_id, row)


def maybe_open_detail(
    *,
    instantly_client: Any,
    campaign_id: str,
    config: dict | None,
    filtered_rows: list[PendingReplyRow],
    get_thread_messages: Callable[..., list[dict]],
) -> None:
    detail_email = st.session_state.get(detail_email_key(campaign_id))
    if not detail_email:
        return
    row = next(
        (item for item in filtered_rows if item.lead_email.lower() == str(detail_email).lower()),
        None,
    )
    if row is None:
        st.session_state.pop(detail_email_key(campaign_id), None)
        return
    show_lead_detail(
        instantly_client=instantly_client,
        campaign_id=campaign_id,
        config=config,
        row=row,
        get_thread_messages=get_thread_messages,
    )
