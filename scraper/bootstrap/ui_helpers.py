"""Shared helpers for Streamlit scrape UI."""

from __future__ import annotations

import os

import streamlit as st

from bootstrap.discovery import discover_presets, invalidate_preset_cache
from config_loader import invalidate_preset_registry, load_config


def get_api_key() -> str:
    return os.getenv("INSTANTLY_API_KEY", "").strip()


def scrape_preset_selector() -> str:
    presets = discover_presets(use_cache=True)
    if not presets:
        st.info("Aucun preset trouvé dans `scraper/presets.yaml`.")
        st.session_state.scrape_preset_id = ""
        return ""

    options = sorted(presets.keys())
    labels = {pid: presets[pid].label for pid in presets}

    if "scrape_preset_id" not in st.session_state:
        st.session_state.scrape_preset_id = ""

    query_preset = st.query_params.get("preset", "")
    if query_preset in presets and st.session_state.scrape_preset_id != query_preset:
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


def reload_presets() -> None:
    invalidate_preset_cache()
    invalidate_preset_registry()
