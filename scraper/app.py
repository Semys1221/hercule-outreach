"""Streamlit scraper — explicit multipage navigation."""

from __future__ import annotations

import streamlit as st

from bootstrap.ui_common import init_session_state
from bootstrap.ui_helpers import register_navigation_pages
from bootstrap.ui_onboarding_page import render_onboarding_page
from bootstrap.ui_scrape_page import render_scrape_page

st.set_page_config(page_title="Streamlit Scraper", page_icon="⚡", layout="wide")

init_session_state()

onboarding_pg = st.Page(
    render_onboarding_page,
    title="Onboarding",
    icon="📋",
    default=True,
)
scrape_pg = st.Page(render_scrape_page, title="Scrape", icon="⚡")

register_navigation_pages(onboarding_pg, scrape_pg)
st.navigation([onboarding_pg, scrape_pg]).run()
