"""Streamlit scraper — scrape machine (always accessible)."""

from __future__ import annotations

import streamlit as st

from bootstrap.ui_common import add_log, init_session_state
from bootstrap.ui_helpers import scrape_preset_selector
from bootstrap.ui_tab_scrape import render_scrape_tab

st.set_page_config(page_title="Streamlit Scraper — Scrape", page_icon="⚡", layout="wide")

init_session_state()

st.title("Lead Engine — Scrape")

preset_id = scrape_preset_selector()
render_scrape_tab(preset_id, add_log)
