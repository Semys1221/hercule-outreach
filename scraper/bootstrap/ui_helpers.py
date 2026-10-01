"""Shared helpers for Streamlit onboarding tabs."""

from __future__ import annotations

import os
from typing import Any

import streamlit as st

from bootstrap.discovery import PresetMeta, discover_presets, invalidate_preset_cache
from bootstrap.onboarding_state import OnboardingStatus, onboarding_complete, onboarding_status
from config_loader import invalidate_preset_registry, load_config

_onboarding_pg: Any = None
_scrape_pg: Any = None


def register_navigation_pages(onboarding_pg: Any, scrape_pg: Any) -> None:
    global _onboarding_pg, _scrape_pg
    _onboarding_pg = onboarding_pg
    _scrape_pg = scrape_pg


def get_api_key() -> str:
    return os.getenv("INSTANTLY_API_KEY", "").strip()


def get_outscraper_key() -> str:
    return os.getenv("OUTSCRAPER_API_KEY", "").strip()


def preset_selector() -> str:
    presets = discover_presets(use_cache=True)
    options = ["— select preset —"] + sorted(presets.keys())
    labels = {pid: presets[pid].label for pid in presets}
    if "active_preset_id" not in st.session_state:
        st.session_state.active_preset_id = ""

    def _fmt(pid: str) -> str:
        if pid == "— select preset —":
            return pid
        return f"{labels.get(pid, pid)} ({pid})"

    current = st.session_state.active_preset_id
    index = options.index(current) if current in options else 0
    selected = st.selectbox("Preset actif", options, index=index, format_func=_fmt)
    if selected != "— select preset —":
        st.session_state.active_preset_id = selected
        return selected
    st.session_state.active_preset_id = ""
    return ""


def list_ready_presets() -> dict[str, PresetMeta]:
    presets = discover_presets(use_cache=True)
    return {pid: meta for pid, meta in presets.items() if onboarding_complete(pid)}


def scrape_preset_selector() -> str:
    ready = list_ready_presets()
    if not ready:
        st.info(
            "Aucun preset prêt. Terminez l'onboarding (onglets 1 à 6) pour activer le scraping."
        )
        st.session_state.scrape_preset_id = ""
        return ""

    options = sorted(ready.keys())
    labels = {pid: ready[pid].label for pid in ready}

    if "scrape_preset_id" not in st.session_state:
        st.session_state.scrape_preset_id = ""

    query_preset = st.query_params.get("preset", "")
    if query_preset in ready and st.session_state.scrape_preset_id != query_preset:
        st.session_state.scrape_preset_id = query_preset

    current = st.session_state.scrape_preset_id
    index = options.index(current) if current in options else 0
    selected = st.selectbox(
        "Preset scrape",
        options,
        index=index,
        format_func=lambda pid: f"{labels.get(pid, pid)} ({pid})",
        key="scrape_preset_selectbox",
    )
    st.session_state.scrape_preset_id = selected
    return selected


def navigate_to_onboarding_page() -> None:
    if _onboarding_pg is None:
        raise RuntimeError("Navigation pages not registered — call register_navigation_pages in app.py")
    st.switch_page(_onboarding_pg)


def render_status_badges(status: OnboardingStatus, *, include_scrape: bool = False) -> None:
    items = [
        ("Config", status.config_saved),
        ("Liste", status.list_linked),
        ("Campagne", status.campaign_linked),
        ("2 emails", status.campaign_emails_saved),
        ("E1–E3", status.subsequence_saved),
        ("Prompt buyer", status.buyer_prompt_saved),
    ]
    if include_scrape:
        items.append(("Scrape", status.complete))
    cols = st.columns(len(items))
    for col, (label, ok) in zip(cols, items):
        with col:
            st.caption(f"{'✅' if ok else '⬜'} {label}")


def reload_presets() -> None:
    invalidate_preset_cache()
    invalidate_preset_registry()


def load_preset_config(preset_id: str) -> dict[str, Any]:
    return load_config(preset_id, require_keys=False)


def status_for_active(preset_id: str) -> OnboardingStatus:
    if not preset_id:
        return OnboardingStatus(
            preset_id="",
            config_saved=False,
            list_linked=False,
            campaign_linked=False,
            campaign_emails_saved=False,
            subsequence_saved=False,
            buyer_prompt_saved=False,
        )
    return onboarding_status(preset_id)
