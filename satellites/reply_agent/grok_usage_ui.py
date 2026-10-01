"""Streamlit UI for Grok API usage badge."""

from __future__ import annotations

import streamlit as st

from grok_usage import fetch_grok_usage, format_usage_label, usage_severity


@st.cache_data(ttl=60, show_spinner=False)
def _cached_fetch_grok_usage():
    return fetch_grok_usage()


def clear_grok_usage_cache() -> None:
    _cached_fetch_grok_usage.clear()


def get_cached_grok_usage_snapshot():
    return _cached_fetch_grok_usage()


def render_grok_usage_badge(*, grok_ok: bool, key_prefix: str = "global") -> None:
    if not grok_ok:
        return

    label_col, refresh_col = st.columns([5, 1])
    with refresh_col:
        if st.button("↻", key=f"grok_usage_refresh_{key_prefix}", help="Rafraîchir le quota Grok"):
            clear_grok_usage_cache()
            st.rerun()

    snapshot = _cached_fetch_grok_usage()
    label = format_usage_label(snapshot)
    severity = usage_severity(snapshot)

    with label_col:
        if severity == "critical":
            st.error(label)
        elif severity == "warn":
            st.warning(label)
        else:
            st.caption(label)

        if snapshot.period_end:
            st.caption(f"Reset · {snapshot.period_end[:10]}")
        if snapshot.error and snapshot.remaining_percent is None and snapshot.remaining_usd is None:
            st.caption(snapshot.error)
