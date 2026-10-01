"""Scrape page layout (always accessible)."""

from __future__ import annotations

import streamlit as st

from bootstrap.ui_common import add_log
from bootstrap.ui_helpers import navigate_to_onboarding_page, scrape_preset_selector
from bootstrap.ui_tab_scrape import render_scrape_tab


def render_scrape_page() -> None:
    header_main, header_back = st.columns([5, 1])
    with header_main:
        st.title("Lead Engine — Scrape")
    with header_back:
        st.markdown("<div style='margin-top: 1.75rem;'></div>", unsafe_allow_html=True)
        if st.button("Onboarding", use_container_width=True, key="scrape_back_onboarding"):
            navigate_to_onboarding_page()

    preset_id = scrape_preset_selector()
    render_scrape_tab(preset_id, add_log)
