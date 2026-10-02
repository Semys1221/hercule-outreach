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


SCRAPE_RUN_CONTEXT_KEY = "scrape_run_context"


def store_scrape_run_context(
    preset_id: str,
    *,
    keyword: str,
    instantly_list_id: str,
    instantly_list_name: str,
    target_leads: int,
) -> None:
    """Persist launch parameters for the live « Suivi en cours » panel."""
    st.session_state[SCRAPE_RUN_CONTEXT_KEY] = {
        "preset_id": preset_id,
        "keyword": keyword.strip(),
        "instantly_list_id": instantly_list_id.strip(),
        "instantly_list_name": (instantly_list_name or "").strip(),
        "target_leads": int(target_leads),
    }


def resolve_instantly_list_name(list_id: str) -> str:
    list_id = list_id.strip()
    if not list_id:
        return ""
    try:
        for item in cached_instantly_lead_lists():
            if item["id"] == list_id:
                return item["name"]
    except Exception:
        return ""
    return ""


def format_instantly_list_line(list_id: str, list_name: str) -> str:
    if not list_id:
        return "—"
    name = (list_name or "").strip() or "(liste inconnue)"
    return format_resource_label(name, list_id)


def _coerce_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def merge_scrape_run_display(
    preset_id: str,
    state: dict[str, Any] | None,
    config: dict[str, Any] | None = None,
    *,
    session_ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge UI session launch context with VPS scrape_state run metadata."""
    ctx = session_ctx
    if ctx is None:
        raw = st.session_state.get(SCRAPE_RUN_CONTEXT_KEY)
        ctx = raw if isinstance(raw, dict) else {}
    session_ctx = ctx
    if (
        session_ctx.get("preset_id")
        and preset_id
        and session_ctx.get("preset_id") != preset_id
    ):
        session_ctx = {}

    keyword = ""
    list_id = ""
    list_name = ""
    target_leads: int | None = None

    if state:
        keyword = str(
            state.get("keyword")
            or state.get("keywords")
            or state.get("run_keyword")
            or state.get("niche_keyword")
            or ""
        ).strip()
        list_id = str(
            state.get("instantly_list_id")
            or state.get("INSTANTLY_LIST_ID")
            or ""
        ).strip()
        list_name = str(state.get("instantly_list_name") or "").strip()
        target_leads = _coerce_positive_int(state.get("target_leads") or state.get("target"))

    if session_ctx:
        keyword = str(session_ctx.get("keyword") or keyword).strip()
        list_id = str(session_ctx.get("instantly_list_id") or list_id).strip()
        list_name = str(session_ctx.get("instantly_list_name") or list_name).strip()
        ctx_target = _coerce_positive_int(session_ctx.get("target_leads"))
        if ctx_target is not None:
            target_leads = ctx_target

    if list_id and not list_name:
        list_name = resolve_instantly_list_name(list_id)

    if not keyword and config:
        keyword = default_keyword_from_config(config)

    if target_leads is None and config:
        target_leads = default_target_leads(config)

    return {
        "keyword": keyword,
        "instantly_list_id": list_id,
        "instantly_list_name": list_name,
        "target_leads": target_leads,
    }


def render_scrape_run_context_banner(
    display: dict[str, Any],
    *,
    running: bool,
) -> None:
    """Prominent niche / Instantly list / volume lines for « Suivi en cours »."""
    keyword = str(display.get("keyword") or "").strip()
    list_id = str(display.get("instantly_list_id") or "").strip()
    list_name = str(display.get("instantly_list_name") or "").strip()
    target_leads = display.get("target_leads")

    if not running and not keyword and not list_id:
        return

    parts: list[str] = []
    if running and not keyword:
        parts.append("**Niche en cours :** *(en attente de métadonnées VPS)*")
    elif keyword:
        parts.append(f"**Niche en cours :** {keyword}")
    if list_id or list_name:
        parts.append(
            f"**Liste Instantly :** {format_instantly_list_line(list_id, list_name)}"
        )
    if target_leads is not None and int(target_leads) > 0:
        parts.append(f"**Volume cible :** {int(target_leads):,} leads")

    if not parts:
        return

    st.info("\n\n".join(parts))


def load_adhoc_scrape_form_defaults() -> tuple[str, int, None]:
    """Defaults for the preset-free launch form."""
    from bootstrap.vps_control import resolve_scrape_default_preset_id

    preset_id = resolve_scrape_default_preset_id()
    presets = discover_presets(use_cache=True)
    if preset_id in presets:
        keyword, target, _ = load_scrape_form_defaults(preset_id)
        return keyword, target, None
    return "", 5000, None
