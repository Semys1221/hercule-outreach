"""Tab 4 — Two cold-email steps on the Instantly campaign."""

from __future__ import annotations

import streamlit as st

from bootstrap.onboarding_state import load_onboarding_state, save_onboarding_state
from bootstrap.ui_helpers import get_api_key, load_preset_config
from instantly_client import patch_campaign_sequences


def render_emails_tab(preset_id: str) -> None:
    st.subheader("4 — 2 emails campagne")
    if not preset_id:
        st.warning("Sélectionnez ou créez une config (onglet 1).")
        return

    config = load_preset_config(preset_id)
    campaign_id = str(config.get("INSTANTLY_CAMPAIGN_ID") or "").strip()
    if not campaign_id:
        st.warning("Liez d'abord une campagne (onglet 3).")
        return

    state = load_onboarding_state(preset_id)
    if state.get("campaign_emails_saved"):
        st.success("2 emails campagne enregistrés.")

    api_key = get_api_key()
    if not api_key:
        st.error("INSTANTLY_API_KEY manquant dans le .env")
        return

    st.caption("Rédigez les 2 emails à la main (sujet + corps HTML).")

    e1_subject = st.text_input("Email 1 — sujet", key="camp_e1_sub")
    e1_body = st.text_area("Email 1 — corps HTML", height=200, key="camp_e1_body")
    e2_subject = st.text_input("Email 2 — sujet", key="camp_e2_sub")
    e2_body = st.text_area("Email 2 — corps HTML", height=200, key="camp_e2_body")

    if st.button("Enregistrer les 2 emails", type="primary", key="camp_emails_save"):
        emails = [
            {"subject": e1_subject.strip(), "body": e1_body.strip()},
            {"subject": e2_subject.strip(), "body": e2_body.strip()},
        ]
        try:
            patch_campaign_sequences(api_key, campaign_id, emails, default_delay_days=3)
        except (ValueError, RuntimeError) as exc:
            st.error(str(exc))
            return
        save_onboarding_state(
            preset_id,
            {
                "campaign_emails_saved": True,
                "campaign_email_subjects": [e1_subject.strip(), e2_subject.strip()],
            },
        )
        st.success("Séquence campagne mise à jour (draft).")
        st.rerun()
