"""Full-app Reply Mode — consecutive draft editing with full inbound messages."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

from inbox import dispatch_unibox_reply
from lead_links import TargetType
from lead_tags import TAG_FILTER_ORDER, TAG_LABELS, count_by_tag
from pending_bulk_actions import bulk_send
from pending_fetch import PendingReplyRow, filter_rows_by_tag, resolve_inbound_body
from pending_table_state import (
    REPLY_MODE_PAGE_SIZE,
    apply_pending_draft,
    clear_inbound_body_cache,
    draft_pending_key,
    inbound_body_key,
    is_draft_dirty,
    page_has_unsaved_drafts,
    page_key,
    paginate_rows,
    queue_draft_update,
    reply_draft_key,
    reply_mode_exit_confirm_key,
    set_reply_mode_enabled,
)
from reply_mode_ui import (
    render_custom_ai_panel,
)
from grok_usage_ui import render_grok_usage_badge
from config import grok_api_key_status
from supabase_repo import get_global_auto_send_enabled, get_lead_replies_batch, upsert_lead_reply


def _target_type_from_config(config: dict[str, Any]) -> TargetType | None:
    value = str(config.get("target_type") or "").strip().lower()
    if value == "seller":
        return "seller"
    if value == "buyer":
        return "buyer"
    return None


def _resolve_cached_inbound_body(
    instantly_client: Any,
    campaign_id: str,
    row: PendingReplyRow,
) -> str:
    cache_key = inbound_body_key(campaign_id, row.lead_email)
    cached = st.session_state.get(cache_key)
    if isinstance(cached, str) and cached.strip():
        return cached
    body = resolve_inbound_body(instantly_client, row)
    st.session_state[cache_key] = body
    return body


def _seed_drafts(campaign_id: str, rows: list[PendingReplyRow], db_drafts: dict[str, str]) -> None:
    for row in rows:
        draft_key = reply_draft_key(campaign_id, row.lead_email)
        if draft_key in st.session_state:
            continue
        if draft_pending_key(campaign_id, row.lead_email) in st.session_state:
            continue
        st.session_state[draft_key] = db_drafts.get(row.lead_email.lower(), "")


def _save_draft(campaign_id: str, lead_email: str) -> None:
    draft_key = reply_draft_key(campaign_id, lead_email)
    draft_text = str(st.session_state.get(draft_key, "") or "").strip()
    if not draft_text:
        raise ValueError("Le brouillon ne peut pas être vide.")
    upsert_lead_reply(campaign_id, lead_email, draft_text)


def _save_page_drafts(
    campaign_id: str,
    rows: list[PendingReplyRow],
) -> list[str]:
    saved: list[str] = []
    for row in rows:
        draft_key = reply_draft_key(campaign_id, row.lead_email)
        draft_text = str(st.session_state.get(draft_key, "") or "").strip()
        if not draft_text:
            continue
        upsert_lead_reply(campaign_id, row.lead_email, draft_text)
        saved.append(row.lead_email.lower())
    return saved


def _remove_emails_from_cache(cache_key: str, emails: set[str]) -> None:
    remaining = [
        row
        for row in st.session_state.get(cache_key, [])
        if row.lead_email.lower() not in emails
    ]
    st.session_state[cache_key] = remaining


@st.fragment
def _render_reply_mode_lead_card(
    *,
    instantly_client: Any,
    campaign_id: str,
    cache_key: str,
    config: dict[str, Any],
    row: PendingReplyRow,
    inbound_body: str,
    db_draft: str,
    target_type: TargetType | None,
    invalidate_thread_cache: Callable[..., None],
) -> None:
    email_key = row.lead_email.lower()
    draft_key = reply_draft_key(campaign_id, row.lead_email)

    with st.container(border=True):
        header = (
            f"**{row.lead_email}** · [{row.interest_label}] · "
            f"{(row.last_reply_at or '')[:16]}"
        )
        if row.last_reply_subject:
            header += f" · {row.last_reply_subject}"
        st.markdown(header)

        col_in, col_draft = st.columns(2)
        with col_in:
            st.markdown("**Message prospect**")
            st.text_area(
                "Message prospect",
                value=inbound_body or "(vide)",
                height=200,
                key=f"reply_mode_inbound_{campaign_id}_{email_key}",
                label_visibility="collapsed",
                disabled=True,
            )
        with col_draft:
            st.markdown("**Brouillon IA**")
            if apply_pending_draft(campaign_id, row.lead_email):
                st.success("Brouillon mis à jour.")
            st.text_area(
                "Brouillon IA",
                height=200,
                key=draft_key,
                label_visibility="collapsed",
            )
            draft_text = str(st.session_state.get(draft_key, "") or "").strip()
            has_draft = bool(draft_text)
            dirty = is_draft_dirty(campaign_id, row.lead_email, db_draft)
            if not has_draft:
                st.caption("Pas de brouillon — utilisez Try agent en mode normal.")
            elif dirty:
                st.caption("non enregistré")

            render_custom_ai_panel(
                campaign_id=campaign_id,
                lead_email=row.lead_email,
                config=config,
                inbound_body=inbound_body,
                interest_label=row.interest_label,
                on_generated=lambda text, lead_email=row.lead_email: queue_draft_update(
                    campaign_id, lead_email, text
                ),
            )

            action_col1, action_col2 = st.columns(2)
            with action_col1:
                if st.button(
                    "Enregistrer",
                    key=f"reply_mode_save_{campaign_id}_{email_key}",
                    disabled=not has_draft,
                ):
                    try:
                        _save_draft(campaign_id, row.lead_email)
                        st.success("Brouillon enregistré.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
            with action_col2:
                if st.button(
                    "Envoyer",
                    key=f"reply_mode_send_{campaign_id}_{email_key}",
                    disabled=not has_draft,
                ):
                    try:
                        if dirty:
                            _save_draft(campaign_id, row.lead_email)
                        draft_text = str(st.session_state.get(draft_key, "") or "").strip()
                        result = dispatch_unibox_reply(
                            instantly_client,
                            campaign_id=campaign_id,
                            lead_email=row.lead_email,
                            reply_text=draft_text,
                            inbound_body=inbound_body,
                            inbound_subject=row.last_reply_subject,
                            instantly_email_id=row.last_reply_id or None,
                            target_type=target_type,
                        )
                        clear_inbound_body_cache(campaign_id, row.lead_email)
                        invalidate_thread_cache(
                            campaign_id,
                            row.lead_email,
                            row.thread_id or None,
                        )
                        _remove_emails_from_cache(cache_key, {email_key})
                        if result["status"] == "sent":
                            st.success(result["detail"])
                        else:
                            st.info(result["detail"])
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))


def _render_exit_bar(
    *,
    campaign_id: str,
    campaign_name: str,
    page_rows: list[PendingReplyRow],
    db_drafts: dict[str, str],
) -> bool:
    """Render exit controls. Returns True if caller should st.rerun()."""
    confirm_key = reply_mode_exit_confirm_key(campaign_id)
    has_unsaved = page_has_unsaved_drafts(campaign_id, page_rows, db_drafts)

    exit_col, info_col, quota_col = st.columns([1.2, 3.2, 1.2])
    with exit_col:
        if st.button("← Quitter Reply Mode", key=f"reply_mode_exit_{campaign_id}"):
            if has_unsaved:
                st.session_state[confirm_key] = True
                st.rerun()
            set_reply_mode_enabled(campaign_id, False)
            st.rerun()

    with info_col:
        auto_on = get_global_auto_send_enabled()
        auto_label = "Auto: ON" if auto_on else "Auto: OFF (brouillon manuel)"
        st.caption(
            f"**Reply Mode** · Campagne: {campaign_name} · "
            f"{auto_label}"
        )

    with quota_col:
        grok_ok, _ = grok_api_key_status()
        render_grok_usage_badge(grok_ok=grok_ok, key_prefix=f"reply_mode_{campaign_id}")

    if not st.session_state.get(confirm_key):
        return False

    st.warning("Des brouillons non enregistrés sont présents sur cette page.")
    confirm_col1, confirm_col2, _ = st.columns([1, 1, 3])
    with confirm_col1:
        if st.button("Enregistrer et quitter", key=f"reply_mode_save_exit_{campaign_id}"):
            _save_page_drafts(campaign_id, page_rows)
            set_reply_mode_enabled(campaign_id, False)
            st.session_state.pop(confirm_key, None)
            st.rerun()
    with confirm_col2:
        if st.button("Quitter sans enregistrer", key=f"reply_mode_discard_exit_{campaign_id}"):
            set_reply_mode_enabled(campaign_id, False)
            st.session_state.pop(confirm_key, None)
            st.rerun()
    return True


def render_reply_mode_view(
    *,
    instantly_client: Any,
    campaign_id: str,
    campaign_name: str,
    config: dict[str, Any],
    pending_rows: list[PendingReplyRow],
    cache_key: str,
    invalidate_thread_cache: Callable[..., None],
) -> None:
    tag_filter_key = f"pending_tag_filter_{campaign_id}"
    selected_tag = st.session_state.get(tag_filter_key, "all")
    filtered_rows = filter_rows_by_tag(pending_rows, selected_tag)

    if not filtered_rows:
        st.info(f"Aucun lead dans le filtre « {TAG_LABELS.get(selected_tag, selected_tag)} ».")
        if st.button("← Quitter Reply Mode", key=f"reply_mode_empty_exit_{campaign_id}"):
            set_reply_mode_enabled(campaign_id, False)
            st.rerun()
        return

    tag_counts = count_by_tag(pending_rows)
    filter_cols = st.columns(len(TAG_FILTER_ORDER))
    for col, tag_key in zip(filter_cols, TAG_FILTER_ORDER):
        label = TAG_LABELS[tag_key]
        count = tag_counts.get(tag_key, 0)
        with col:
            if st.button(
                f"{label} ({count})",
                key=f"reply_mode_tag_{campaign_id}_{tag_key}",
                type="primary" if selected_tag == tag_key else "secondary",
                use_container_width=True,
            ):
                st.session_state[tag_filter_key] = tag_key
                st.rerun()

    page_state_key = page_key(campaign_id, selected_tag)
    current_page = int(st.session_state.get(page_state_key, 0))
    page_rows, current_page, total_pages = paginate_rows(
        filtered_rows,
        current_page,
        page_size=REPLY_MODE_PAGE_SIZE,
    )
    st.session_state[page_state_key] = current_page

    db_drafts = get_lead_replies_batch(
        campaign_id,
        [row.lead_email for row in page_rows],
    )
    _seed_drafts(campaign_id, page_rows, db_drafts)

    if _render_exit_bar(
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        page_rows=page_rows,
        db_drafts=db_drafts,
    ):
        return

    st.caption(
        f"{len(filtered_rows)} lead(s) · filtre « {TAG_LABELS.get(selected_tag, selected_tag)} »"
    )

    with st.spinner("Chargement des messages…"):
        inbound_by_email = {
            row.lead_email.lower(): _resolve_cached_inbound_body(
                instantly_client, campaign_id, row
            )
            for row in page_rows
        }

    target_type = _target_type_from_config(config)

    for row in page_rows:
        email_key = row.lead_email.lower()
        _render_reply_mode_lead_card(
            instantly_client=instantly_client,
            campaign_id=campaign_id,
            cache_key=cache_key,
            config=config,
            row=row,
            inbound_body=inbound_by_email.get(email_key, ""),
            db_draft=db_drafts.get(email_key, ""),
            target_type=target_type,
            invalidate_thread_cache=invalidate_thread_cache,
        )

    nav_col1, nav_col2, nav_col3, bulk_col1, bulk_col2 = st.columns([1, 2, 1, 1, 1])
    with nav_col1:
        if st.button(
            "← Page",
            key=f"reply_mode_prev_{campaign_id}_{selected_tag}",
            disabled=current_page <= 0,
        ):
            st.session_state[page_state_key] = current_page - 1
            st.rerun()
    with nav_col2:
        start = current_page * REPLY_MODE_PAGE_SIZE + 1
        end = min((current_page + 1) * REPLY_MODE_PAGE_SIZE, len(filtered_rows))
        st.caption(f"Page {current_page + 1}/{total_pages} — leads {start}–{end}")
    with nav_col3:
        if st.button(
            "Page →",
            key=f"reply_mode_next_{campaign_id}_{selected_tag}",
            disabled=current_page >= total_pages - 1,
        ):
            st.session_state[page_state_key] = current_page + 1
            st.rerun()
    with bulk_col1:
        if st.button("Enregistrer la page", key=f"reply_mode_save_page_{campaign_id}"):
            saved = _save_page_drafts(campaign_id, page_rows)
            if saved:
                st.success(f"{len(saved)} brouillon(s) enregistré(s).")
            else:
                st.info("Aucun brouillon à enregistrer sur cette page.")
            st.rerun()
    with bulk_col2:
        page_emails = {row.lead_email.lower() for row in page_rows}
        page_drafts_ok = all(
            str(st.session_state.get(reply_draft_key(campaign_id, row.lead_email), "") or "").strip()
            for row in page_rows
        )
        send_page_key = f"reply_mode_send_page_confirm_{campaign_id}"

        def _send_page() -> None:
            _save_page_drafts(campaign_id, page_rows)
            progress = st.progress(0.0)
            status = st.empty()

            def on_send_progress(email: str, index: int, total: int) -> None:
                progress.progress(index / total)
                status.caption(f"Envoi {index}/{total} — {email}")

            def on_sent(sent_row: PendingReplyRow) -> None:
                clear_inbound_body_cache(campaign_id, sent_row.lead_email)
                invalidate_thread_cache(
                    campaign_id,
                    sent_row.lead_email,
                    sent_row.thread_id or None,
                )

            result = bulk_send(
                instantly_client,
                campaign_id,
                pending_rows,
                page_emails,
                target_type=target_type,
                on_progress=on_send_progress,
                on_sent=on_sent,
            )
            progress.empty()
            status.empty()
            st.session_state.pop(send_page_key, None)
            _remove_emails_from_cache(cache_key, set(result.succeeded))
            if result.succeeded:
                st.success(f"Envoi: {len(result.succeeded)} lead(s) traité(s).")
            for email, reason in result.skipped:
                st.warning(f"{email}: {reason}")
            for email, error in result.failed:
                st.error(f"{email}: {error}")
            st.rerun()

        if st.session_state.get(send_page_key):
            st.warning("Confirmez l'envoi de tous les brouillons de cette page.")
            if st.button(
                "Confirmer l'envoi",
                key=f"reply_mode_send_page_ok_{campaign_id}",
            ):
                _send_page()
        elif st.button(
            "Envoyer la page",
            key=f"reply_mode_send_page_{campaign_id}",
            disabled=not page_drafts_ok or not page_emails,
        ):
            if len(page_rows) > 1:
                st.session_state[send_page_key] = True
                st.rerun()
            _send_page()
