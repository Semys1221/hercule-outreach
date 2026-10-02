"""Scrape page layout — launch form + live progress + history."""

from __future__ import annotations

import streamlit as st

from bootstrap.ui_helpers import scrape_preset_selector
from bootstrap.ui_tab_scrape import render_scrape_tab


def render_scrape_page() -> None:
    st.title("Lead Engine — Scrape")
    st.caption(
        "Choisissez un preset, saisissez les mots-clés de recherche, "
        "la liste Instantly de destination et le volume, puis lancez le flux n8n."
    )
    preset_id = scrape_preset_selector()
    render_scrape_tab(preset_id)
