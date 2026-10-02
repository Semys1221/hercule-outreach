"""Scrape page layout — launch form + live progress + history."""

from __future__ import annotations

import streamlit as st

from bootstrap.ui_tab_scrape import render_scrape_tab


def render_scrape_page() -> None:
    st.title("Lead Engine — Scrape")
    st.caption(
        "Saisissez les mots-clés de recherche, la liste Instantly de destination "
        "et le volume cible, puis lancez le flux n8n."
    )
    render_scrape_tab()
