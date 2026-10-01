"""Shared Streamlit session helpers for onboarding and scrape pages."""

from __future__ import annotations

import streamlit as st


def init_session_state() -> None:
    if "logs" not in st.session_state:
        st.session_state.logs = []
    if "last_instantly_pushed" not in st.session_state:
        st.session_state.last_instantly_pushed = 0
    if "last_enriched_valid" not in st.session_state:
        st.session_state.last_enriched_valid = 0


def add_log(msg: str) -> None:
    try:
        if "logs" not in st.session_state:
            st.session_state.logs = []
        st.session_state.logs.append(msg)
        if len(st.session_state.logs) > 30:
            st.session_state.logs.pop(0)
        container = st.session_state.get("log_container")
        if container is not None:
            container.code("\n".join(st.session_state.logs), language="shell")
    except Exception:
        return
