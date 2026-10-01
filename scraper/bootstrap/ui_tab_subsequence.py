"""Tab 5 — E1/E2/E3 bypass templates (Supabase + webhook, no Instantly subsequence)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from bootstrap.campaign_layers import load_bypass_templates_for_ui
from bootstrap.onboarding_state import save_onboarding_state
from bootstrap.ui_helpers import get_api_key, load_preset_config
from instantly_client import instantly_resource_name
from repo_paths import subsequence_app

_SUBSEQUENCE_APP = subsequence_app()


def _prefill_subsequence_fields(campaign_id: str) -> None:
    cache_key = f"sub_prefill_{campaign_id}"
    if st.session_state.get(cache_key):
        return

    templates = load_bypass_templates_for_ui(campaign_id)
    for ui_key in ("e1", "e2", "e3"):
        row = templates.get(ui_key) or {}
        subject = str(row.get("subject") or "").strip()
        body = str(row.get("body") or "").strip()
        if subject:
            st.session_state[f"sub_{ui_key}_subject"] = subject
        if body:
            st.session_state[f"sub_{ui_key}_body"] = body

    st.session_state[cache_key] = True


def _save_supabase_templates(campaign_id: str, campaign_name: str, emails: list[dict[str, str]]) -> None:
    if not _SUBSEQUENCE_APP.is_dir():
        raise RuntimeError("streamlit_subsequence app not found")

    from bootstrap.app_imports import load_app_module
    from shared.instantly_client import InstantlyClient, get_api_key as shared_get_key

    sub_config = load_app_module(_SUBSEQUENCE_APP, "config")
    sub_onboarding = load_app_module(_SUBSEQUENCE_APP, "onboarding")
    sub_repo = load_app_module(_SUBSEQUENCE_APP, "supabase_repo")

    url_error = sub_config.webhook_url_error()
    if url_error:
        raise RuntimeError(f"Webhook URL invalide : {url_error}")

    secret = sub_config.webhook_secret()
    if not secret:
        raise RuntimeError("INSTANTLY_BYPASS_WEBHOOK_SECRET / CRON_SECRET manquant")

    api_key = shared_get_key()
    client = InstantlyClient(api_key)
    target_url = sub_config.webhook_public_url()
    sub_onboarding.initialize_campaign(
        client,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        target_url=target_url,
        secret=secret,
    )

    keys = ("interested_email1", "interested_email2", "interested_email3")
    for key, email in zip(keys, emails):
        sub_repo.save_template(
            campaign_id,
            key,
            email["subject"],
            email["body"],
            sync_bootstrap_default=(key == "interested_email1"),
        )


def render_subsequence_tab(preset_id: str) -> None:
    st.subheader("5 — E1 / E2 / E3 (subsequence)")
    if not preset_id:
        st.warning("Sélectionnez ou créez une config (onglet 1).")
        return

    config = load_preset_config(preset_id)
    campaign_id = str(config.get("INSTANTLY_CAMPAIGN_ID") or "").strip()
    if not campaign_id:
        st.warning("Liez d'abord une campagne (onglet 3).")
        return

    _prefill_subsequence_fields(campaign_id)

    label = str(config.get("PRESET_LABEL") or preset_id)
    sub_name = instantly_resource_name(f"{label} — Interested")

    api_key = get_api_key()
    if not api_key:
        st.error("INSTANTLY_API_KEY manquant dans le .env")
        return

    st.caption(
        "Rédigez E1, E2, E3 à la main. Enregistrement → Supabase + webhook bypass "
        "(pas de subsequence Instantly — évite le double envoi E1)."
    )

    for idx, key in enumerate(("e1", "e2", "e3"), start=1):
        st.markdown(f"**Email {idx}**")
        st.text_input(f"E{idx} sujet", key=f"sub_{key}_subject")
        st.text_area(f"E{idx} corps HTML", height=160, key=f"sub_{key}_body")

    if st.button("Enregistrer E1–E3", type="primary", key="sub_save"):
        emails = []
        for key in ("e1", "e2", "e3"):
            subject = str(st.session_state.get(f"sub_{key}_subject") or "").strip()
            body = str(st.session_state.get(f"sub_{key}_body") or "").strip()
            if not subject or not body:
                st.error(f"E{key[-1]} : sujet et corps requis.")
                return
            emails.append({"subject": subject, "body": body})

        try:
            _save_supabase_templates(campaign_id, sub_name, emails)
        except Exception as exc:
            st.error(f"Enregistrement Supabase / webhook : {exc}")
            return

        st.success("Templates bypass E1–E3 + webhook enregistrés (sans subsequence Instantly).")
        save_onboarding_state(preset_id, {"subsequence_saved": True})
        st.session_state.pop(f"sub_prefill_{campaign_id}", None)
        st.rerun()
