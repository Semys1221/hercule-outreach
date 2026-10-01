"""Session-state helpers and DataFrame mapping for Pending Unibox table."""

from __future__ import annotations

import streamlit as st

import pandas as pd

from pending_fetch import PendingReplyRow, is_reply_over_24h

PAGE_SIZE = 25
REPLY_MODE_PAGE_SIZE = 6
_DEFAULT_SENTENCE_COUNT = 2
_MIN_SENTENCE_COUNT = 1
_MAX_SENTENCE_COUNT = 10
_PREVIEW_TRUNCATE = 80
_REPLY_TRUNCATE = 80


def reply_mode_key(campaign_id: str) -> str:
    return f"reply_mode_enabled_{campaign_id}"


def reply_mode_exit_confirm_key(campaign_id: str) -> str:
    return f"reply_mode_exit_confirm_{campaign_id}"


def inbound_body_key(campaign_id: str, lead_email: str) -> str:
    return f"inbound_body_{campaign_id}_{lead_email.lower()}"


def is_reply_mode_enabled(campaign_id: str) -> bool:
    return bool(st.session_state.get(reply_mode_key(campaign_id), False))


def set_reply_mode_enabled(campaign_id: str, enabled: bool) -> None:
    st.session_state[reply_mode_key(campaign_id)] = enabled
    if not enabled:
        st.session_state.pop(reply_mode_exit_confirm_key(campaign_id), None)


def clear_inbound_body_cache(campaign_id: str, lead_email: str | None = None) -> None:
    if lead_email:
        st.session_state.pop(inbound_body_key(campaign_id, lead_email), None)
        return
    prefix = f"inbound_body_{campaign_id}_"
    for key in list(st.session_state.keys()):
        if isinstance(key, str) and key.startswith(prefix):
            st.session_state.pop(key, None)


def is_draft_dirty(campaign_id: str, lead_email: str, db_draft: str) -> bool:
    session_val = str(
        st.session_state.get(reply_draft_key(campaign_id, lead_email), "") or ""
    ).strip()
    return session_val != (db_draft or "").strip()


def page_has_unsaved_drafts(
    campaign_id: str,
    rows: list[PendingReplyRow],
    db_drafts: dict[str, str],
) -> bool:
    for row in rows:
        email = row.lead_email.lower()
        if is_draft_dirty(campaign_id, row.lead_email, db_drafts.get(email, "")):
            return True
    return False


def bulk_try_result_key(campaign_id: str) -> str:
    return f"bulk_try_result_{campaign_id}"


def pop_bulk_try_result(campaign_id: str):
    key = bulk_try_result_key(campaign_id)
    result = st.session_state.get(key)
    if result is not None:
        st.session_state.pop(key, None)
    return result


def reply_draft_key(campaign_id: str, lead_email: str) -> str:
    return f"pending_reply_text_{campaign_id}_{lead_email.lower()}"


def draft_pending_key(campaign_id: str, lead_email: str) -> str:
    return f"pending_reply_pending_{campaign_id}_{lead_email.lower()}"


def sentence_count_key(campaign_id: str, lead_email: str) -> str:
    return f"reply_mode_sentence_count_{campaign_id}_{lead_email.lower()}"


def custom_ai_open_key(campaign_id: str, lead_email: str) -> str:
    return f"reply_mode_custom_ai_open_{campaign_id}_{lead_email.lower()}"


def custom_directive_key(campaign_id: str, lead_email: str) -> str:
    return f"reply_mode_custom_directive_{campaign_id}_{lead_email.lower()}"


def get_sentence_count(campaign_id: str, lead_email: str) -> int:
    key = sentence_count_key(campaign_id, lead_email)
    raw = st.session_state.get(key, _DEFAULT_SENTENCE_COUNT)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = _DEFAULT_SENTENCE_COUNT
    return max(_MIN_SENTENCE_COUNT, min(_MAX_SENTENCE_COUNT, value))


def set_sentence_count(campaign_id: str, lead_email: str, count: int) -> None:
    clamped = max(_MIN_SENTENCE_COUNT, min(_MAX_SENTENCE_COUNT, count))
    st.session_state[sentence_count_key(campaign_id, lead_email)] = clamped


def get_custom_ai_open(campaign_id: str, lead_email: str) -> bool:
    return bool(st.session_state.get(custom_ai_open_key(campaign_id, lead_email), False))


def set_custom_ai_open(campaign_id: str, lead_email: str, open_: bool) -> None:
    st.session_state[custom_ai_open_key(campaign_id, lead_email)] = open_


def get_custom_directive(campaign_id: str, lead_email: str) -> str:
    return str(st.session_state.get(custom_directive_key(campaign_id, lead_email), "") or "")


def editor_df_key(campaign_id: str, tag: str) -> str:
    return f"pending_editor_df_{campaign_id}_{tag}"


def detail_email_key(campaign_id: str) -> str:
    return f"pending_detail_email_{campaign_id}"


def selected_key(campaign_id: str, tag: str) -> str:
    return f"pending_selected_{campaign_id}_{tag}"


def page_key(campaign_id: str, tag: str) -> str:
    return f"pending_page_{campaign_id}_{tag}"


def checkbox_key(campaign_id: str, lead_email: str) -> str:
    return f"pending_cb_{campaign_id}_{lead_email.lower()}"


def get_draft(campaign_id: str, lead_email: str) -> str:
    return str(st.session_state.get(reply_draft_key(campaign_id, lead_email), "") or "")


def set_draft(campaign_id: str, lead_email: str, text: str) -> None:
    """Set draft before the text_area widget is rendered (initial seed only)."""
    st.session_state[reply_draft_key(campaign_id, lead_email)] = text


def queue_draft_update(campaign_id: str, lead_email: str, text: str) -> None:
    """Queue a draft update for the next rerun (safe after widget render)."""
    st.session_state[draft_pending_key(campaign_id, lead_email)] = text


def apply_pending_draft(campaign_id: str, lead_email: str) -> bool:
    """Apply queued draft before rendering the text_area widget."""
    pending_key = draft_pending_key(campaign_id, lead_email)
    pending = st.session_state.pop(pending_key, None)
    if pending is None:
        return False
    st.session_state[reply_draft_key(campaign_id, lead_email)] = str(pending)
    return True


def ensure_draft(campaign_id: str, lead_email: str, default: str = "") -> None:
    """Initialize draft in session state before widget render."""
    if apply_pending_draft(campaign_id, lead_email):
        return
    draft_key = reply_draft_key(campaign_id, lead_email)
    if draft_key not in st.session_state:
        st.session_state[draft_key] = default


def clear_draft(campaign_id: str, lead_email: str) -> None:
    st.session_state.pop(reply_draft_key(campaign_id, lead_email), None)


def clear_checkbox(campaign_id: str, lead_email: str) -> None:
    st.session_state.pop(checkbox_key(campaign_id, lead_email), None)


def _truncate(text: str, limit: int) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def _format_last_reply(row: PendingReplyRow) -> str:
    preview = _truncate(row.last_reply_preview, _PREVIEW_TRUNCATE)
    timestamp = (row.last_reply_at or "")[:16]
    if preview and timestamp:
        return f"{preview} · {timestamp}"
    return preview or timestamp or "—"


def _format_email_cell(row: PendingReplyRow) -> str:
    prefix = "🔴 " if is_reply_over_24h(row.last_reply_at) else ""
    tag = f"[{row.interest_label}] " if row.interest_label else ""
    return f"{prefix}{tag}{row.lead_email}"


def rows_to_dataframe(rows: list[PendingReplyRow], campaign_id: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Selected": False,
                "Lead email": _format_email_cell(row),
                "Lead last reply": _format_last_reply(row),
                "AI agent reply": _truncate(
                    get_draft(campaign_id, row.lead_email), _REPLY_TRUNCATE
                ),
                "_email_key": row.lead_email.lower(),
            }
            for row in rows
        ]
    )


def sync_drafts_from_session(df: pd.DataFrame, campaign_id: str) -> pd.DataFrame:
    if df.empty:
        return df
    updated = df.copy()
    for index, row in updated.iterrows():
        email = str(row["_email_key"])
        updated.at[index, "AI agent reply"] = _truncate(
            get_draft(campaign_id, email), _REPLY_TRUNCATE
        )
    return updated


def selected_emails_from_df(df: pd.DataFrame) -> set[str]:
    if df.empty:
        return set()
    return {
        str(row["_email_key"]).strip().lower()
        for _, row in df.iterrows()
        if bool(row.get("Selected"))
    }


def get_selected_emails(
    rows: list[PendingReplyRow],
    campaign_id: str,
) -> set[str]:
    return {
        row.lead_email.lower()
        for row in rows
        if st.session_state.get(checkbox_key(campaign_id, row.lead_email), False)
    }


def set_all_selected(
    rows: list[PendingReplyRow],
    campaign_id: str,
    *,
    selected: bool,
) -> None:
    for row in rows:
        st.session_state[checkbox_key(campaign_id, row.lead_email)] = selected


def invalidate_editor(campaign_id: str, tag: str) -> None:
    st.session_state.pop(editor_df_key(campaign_id, tag), None)


def invalidate_all_editors(campaign_id: str) -> None:
    prefix = f"pending_editor_df_{campaign_id}_"
    for key in list(st.session_state.keys()):
        if isinstance(key, str) and key.startswith(prefix):
            st.session_state.pop(key, None)


def row_by_email(
    rows: list[PendingReplyRow],
    lead_email: str,
) -> PendingReplyRow | None:
    target = lead_email.strip().lower()
    for row in rows:
        if row.lead_email.lower() == target:
            return row
    return None


def paginate_rows(
    rows: list[PendingReplyRow],
    page: int,
    *,
    page_size: int = PAGE_SIZE,
) -> tuple[list[PendingReplyRow], int, int]:
    total = len(rows)
    if total == 0:
        return [], 0, 1
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    return rows[start : start + page_size], page, total_pages
