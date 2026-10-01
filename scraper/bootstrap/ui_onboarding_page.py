"""Onboarding page layout (tabs 1–6)."""

from __future__ import annotations

import streamlit as st

from bootstrap.ui_helpers import preset_selector, render_status_badges, status_for_active
from bootstrap.ui_tab_campaign import render_campaign_tab
from bootstrap.ui_tab_config import render_config_tab
from bootstrap.ui_tab_emails import render_emails_tab
from bootstrap.ui_tab_list import render_list_tab
from bootstrap.ui_tab_reply import render_reply_tab
from bootstrap.ui_tab_subsequence import render_subsequence_tab


def render_onboarding_page() -> None:
    st.title("Lead Engine — Onboarding")
    preset_id = preset_selector()

    status = status_for_active(preset_id)
    render_status_badges(status)

    tab_config, tab_list, tab_campaign, tab_emails, tab_subseq, tab_reply = st.tabs(
        [
            "1 Config",
            "2 Liste",
            "3 Campagne",
            "4 2 emails",
            "5 E1–E3",
            "6 Prompt buyer",
        ]
    )

    with tab_config:
        preset_id = render_config_tab(preset_id)

    with tab_list:
        render_list_tab(preset_id)

    with tab_campaign:
        render_campaign_tab(preset_id)

    with tab_emails:
        render_emails_tab(preset_id)

    with tab_subseq:
        render_subsequence_tab(preset_id)

    with tab_reply:
        render_reply_tab(preset_id)
