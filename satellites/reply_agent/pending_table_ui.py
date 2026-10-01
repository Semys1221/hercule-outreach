"""Pending Unibox table UI with bulk selection and quick actions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

from config import grok_api_key_status
from lead_links import TargetType
from pending_bulk_actions import bulk_delete, bulk_send, bulk_try_agent
from pending_fetch import PendingReplyRow, is_reply_over_24h
from pending_lead_detail import maybe_open_detail
from pending_table_state import (
    PAGE_SIZE,
    bulk_try_result_key,
    checkbox_key,
    detail_email_key,
    get_selected_emails,
    page_key,
    paginate_rows,
    pop_bulk_try_result,
    set_all_selected,
)
from supabase_repo import get_lead_replies_batch


def _target_type_from_config(config: dict | None) -> TargetType | None:
    if not config:
        return None
    value = str(config.get("target_type") or "").strip().lower()
    if value == "seller":
        return "seller"
    if value == "buyer":
        return "buyer"
    return None


def _show_bulk_result(label: str, result) -> None:
    if result.succeeded:
        st.success(f"{label}: {len(result.succeeded)} lead(s) traité(s).")
    for email, reason in result.skipped:
        st.warning(f"{email}: {reason}")
    for email, error in result.failed:
        st.error(f"{email}: {error}")


def _remove_emails_from_cache(
    cache_key: str,
    emails: set[str],
) -> list[PendingReplyRow]:
    remaining = [
        row
        for row in st.session_state.get(cache_key, [])
        if row.lead_email.lower() not in emails
    ]
    st.session_state[cache_key] = remaining
    return remaining


def render_pending_table(
    *,
    instantly_client: Any,
    campaign_id: str,
    config: dict | None,
    filtered_rows: list[PendingReplyRow],
    pending_rows: list[PendingReplyRow],
    cache_key: str,
    selected_tag: str,
    get_thread_messages: Callable[..., list[dict]],
    invalidate_thread_cache: Callable[..., None],
) -> None:
    bulk_result = pop_bulk_try_result(campaign_id)
    if bulk_result is not None:
        _show_bulk_result("Try agent", bulk_result)

    page_state_key = page_key(campaign_id, selected_tag)
    current_page = int(st.session_state.get(page_state_key, 0))
    page_rows, current_page, total_pages = paginate_rows(filtered_rows, current_page)
    st.session_state[page_state_key] = current_page
    reply_by_email = get_lead_replies_batch(
        campaign_id,
        [row.lead_email for row in page_rows],
    )

    if total_pages > 1:
        nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])
        with nav_col1:
            if st.button(
                "← Précédent",
                key=f"pending_prev_{campaign_id}_{selected_tag}",
                disabled=current_page <= 0,
            ):
                st.session_state[page_state_key] = current_page - 1
                st.rerun()
        with nav_col2:
            start = current_page * PAGE_SIZE + 1
            end = min((current_page + 1) * PAGE_SIZE, len(filtered_rows))
            st.caption(
                f"Page {current_page + 1}/{total_pages} — "
                f"leads {start}–{end} sur {len(filtered_rows)}"
            )
        with nav_col3:
            if st.button(
                "Suivant →",
                key=f"pending_next_{campaign_id}_{selected_tag}",
                disabled=current_page >= total_pages - 1,
            ):
                st.session_state[page_state_key] = current_page + 1
                st.rerun()

    sel_col1, sel_col2, _ = st.columns([1, 1, 3])
    with sel_col1:
        if st.button(
            "Tout sélectionner",
            key=f"pending_select_all_{campaign_id}_{selected_tag}",
        ):
            set_all_selected(filtered_rows, campaign_id, selected=True)
            st.rerun()
    with sel_col2:
        if st.button(
            "Tout désélectionner",
            key=f"pending_deselect_all_{campaign_id}_{selected_tag}",
        ):
            set_all_selected(filtered_rows, campaign_id, selected=False)
            st.rerun()

    header = st.columns([0.5, 2.2, 3.5, 3.0, 0.9])
    header[0].markdown("**☑**")
    header[1].markdown("**Lead email**")
    header[2].markdown("**Lead last reply**")
    header[3].markdown("**AI agent reply**")
    header[4].markdown("**See more**")

    for row in page_rows:
        email = row.lead_email
        draft = reply_by_email.get(email.lower(), "")
        cols = st.columns([0.5, 2.2, 3.5, 3.0, 0.9])
        with cols[0]:
            st.checkbox(
                "sel",
                label_visibility="collapsed",
                key=checkbox_key(campaign_id, email),
            )
        with cols[1]:
            prefix = "🔴 " if is_reply_over_24h(row.last_reply_at) else ""
            tag = f"[{row.interest_label}] " if row.interest_label else ""
            st.write(f"{prefix}{tag}{email}")
        with cols[2]:
            preview = (row.last_reply_preview or "")[:80]
            if len(row.last_reply_preview or "") > 80:
                preview += "…"
            timestamp = (row.last_reply_at or "")[:16]
            st.write(f"{preview or '—'} · {timestamp}" if preview else timestamp or "—")
        with cols[3]:
            display_draft = draft[:80] + ("…" if len(draft) > 80 else "") if draft else ""
            st.write(display_draft or "—")
        with cols[4]:
            if st.button(
                "See more",
                key=f"pending_detail_{campaign_id}_{email.lower()}",
            ):
                st.session_state[detail_email_key(campaign_id)] = email
                st.rerun()

    selected_emails = get_selected_emails(filtered_rows, campaign_id)
    if not selected_emails:
        maybe_open_detail(
            instantly_client=instantly_client,
            campaign_id=campaign_id,
            config=config,
            filtered_rows=filtered_rows,
            get_thread_messages=get_thread_messages,
        )
        return

    st.divider()
    st.markdown(f"**{len(selected_emails)}** lead(s) sélectionné(s)")

    selected_replies = get_lead_replies_batch(campaign_id, list(selected_emails))
    send_enabled = all(selected_replies.get(email.strip().lower(), "").strip() for email in selected_emails)
    grok_ok, grok_hint = grok_api_key_status()
    regenerate_existing = st.checkbox(
        "Regénérer même si brouillon",
        key=f"pending_try_regenerate_{campaign_id}_{selected_tag}",
    )
    action_cols = st.columns([1, 1, 1.5])
    with action_cols[0]:
        delete_clicked = st.button(
            "Delete",
            key=f"pending_bulk_delete_{campaign_id}_{selected_tag}",
        )
    with action_cols[1]:
        try_agent_clicked = st.button(
            "Try agent",
            key=f"pending_bulk_try_{campaign_id}_{selected_tag}",
            disabled=not config or not grok_ok,
            help=None if grok_ok else grok_hint,
        )
    with action_cols[2]:
        send_clicked = st.button(
            "Send agent reply",
            key=f"pending_bulk_send_{campaign_id}_{selected_tag}",
            disabled=not send_enabled,
        )

    if delete_clicked:
        result = bulk_delete(campaign_id, pending_rows, selected_emails)
        _remove_emails_from_cache(cache_key, set(result.succeeded))
        _show_bulk_result("Delete", result)
        st.rerun()

    if try_agent_clicked:
        if not config:
            st.error("Campagne non configurée.")
        else:
            progress = st.progress(0.0)
            status = st.empty()

            def on_try_progress(email: str, index: int, total: int) -> None:
                progress.progress(index / total)
                status.caption(f"Try agent {index}/{total} — {email}")

            result = bulk_try_agent(
                instantly_client,
                config,
                pending_rows,
                selected_emails,
                campaign_id,
                on_progress=on_try_progress,
                regenerate_existing=regenerate_existing,
            )
            progress.empty()
            status.empty()
            st.session_state[bulk_try_result_key(campaign_id)] = result
            st.rerun()

    if send_clicked:
        if not send_enabled:
            st.warning("Tous les leads sélectionnés doivent avoir un draft IA.")
        else:
            progress = st.progress(0.0)
            status = st.empty()

            def on_send_progress(email: str, index: int, total: int) -> None:
                progress.progress(index / total)
                status.caption(f"Envoi {index}/{total} — {email}")

            def on_sent(row: PendingReplyRow) -> None:
                invalidate_thread_cache(
                    campaign_id,
                    row.lead_email,
                    row.thread_id or None,
                )

            result = bulk_send(
                instantly_client,
                campaign_id,
                pending_rows,
                selected_emails,
                target_type=_target_type_from_config(config),
                on_progress=on_send_progress,
                on_sent=on_sent,
            )
            progress.empty()
            status.empty()
            _remove_emails_from_cache(cache_key, set(result.succeeded))
            _show_bulk_result("Send", result)
            st.rerun()

    maybe_open_detail(
        instantly_client=instantly_client,
        campaign_id=campaign_id,
        config=config,
        filtered_rows=filtered_rows,
        get_thread_messages=get_thread_messages,
    )
