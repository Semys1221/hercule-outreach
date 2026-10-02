"""Streamlit scraper — scrape machine (VPS / n8n)."""

from __future__ import annotations

import streamlit as st

from bootstrap.ui_common import init_session_state
from bootstrap.ui_scrape_page import render_scrape_page

st.set_page_config(page_title="Lead Engine — Scrape", page_icon="⚡", layout="wide")

init_session_state()
render_scrape_page()
