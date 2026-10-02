"""Shared helpers for Streamlit scrape UI."""

from __future__ import annotations

import sys
from typing import Any

import streamlit as st

from bootstrap.discovery import discover_presets, invalidate_preset_cache
from config_loader import invalidate_preset_registry, load_config
from repo_paths import outreach_root

_ROOT = str(outreach_root())
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from shared.instantly_client import (  # noqa: E402
    format_resource_label,
    get_api_key,
    list_all_lead_lists,
)


def get_instantly_api_key() -> str:
    return get_api_key().strip()


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


def default_keyword_from_config(config: dict[str, Any]) -> str:
    raw = config.get("KEYWORDS")
    if isinstance(raw, list) and raw:
        return ", ".join(str(item).strip() for item in raw if str(item).strip())
    label = str(config.get("SUBNICHE_LABEL") or config.get("NICHE_GROUP_LABEL") or "").strip()
    return label


def default_target_leads(config: dict[str, Any]) -> int:
    try:
        return max(int(config.get("TARGET_LEADS") or 0), 1)
    except (TypeError, ValueError):
        return 5000


@st.cache_data(ttl=300, show_spinner=False)
def cached_instantly_lead_lists() -> list[dict[str, str]]:
    items = list_all_lead_lists()
    return sorted(
        [
            {
                "id": str(item.get("id", "")),
                "name": (item.get("name") or "").strip() or "(sans nom)",
            }
            for item in items
            if item.get("id")
        ],
        key=lambda item: item["name"].lower(),
    )


def _resource_labels(resources: list[dict[str, str]]) -> list[str]:
    name_counts: dict[str, int] = {}
    for resource in resources:
        name = resource["name"]
        name_counts[name] = name_counts.get(name, 0) + 1

    labels: list[str] = []
    for resource in resources:
        name = resource["name"]
        if name_counts[name] > 1:
            labels.append(f"{name} ({resource['id']})")
        else:
            labels.append(format_resource_label(name, resource["id"]))
    return labels


def select_instantly_lead_list(
    *,
    label: str,
    key: str,
    current_id: str | None = None,
) -> dict[str, str] | None:
    refresh_col, _ = st.columns([1, 3])
    with refresh_col:
        if st.button("Actualiser les listes", key=f"{key}_refresh"):
            cached_instantly_lead_lists.clear()
            st.rerun()

    if not get_instantly_api_key():
        st.warning(
            "Définissez `INSTANTLY_API_KEY` dans le `.env` du repo pour charger les listes Instantly."
        )
        return None

    try:
        lead_lists = cached_instantly_lead_lists()
    except Exception as exc:
        st.error(f"Impossible de charger les listes Instantly : {exc}")
        return None

    if not lead_lists:
        st.warning("Aucune liste Instantly trouvée dans l'espace de travail.")
        return None

    labels = _resource_labels(lead_lists)
    default_index = 0
    if current_id:
        for index, resource in enumerate(lead_lists):
            if resource["id"] == current_id:
                default_index = index
                break

    selected_index = st.selectbox(
        label,
        options=range(len(lead_lists)),
        format_func=lambda index: labels[index],
        index=default_index,
        key=key,
    )
    return lead_lists[selected_index]


def load_scrape_form_defaults(preset_id: str) -> tuple[str, int, str | None]:
    """Return (keyword_default, target_leads_default, config_list_id)."""
    config = load_config(preset_id, require_keys=False)
    keyword = default_keyword_from_config(config)
    target = default_target_leads(config)
    list_id = str(config.get("INSTANTLY_LIST_ID") or "").strip() or None
    return keyword, target, list_id
