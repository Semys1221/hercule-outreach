"""Tab 1 — Config bootstrap (create / select preset file)."""

from __future__ import annotations

from typing import Any

import streamlit as st

from bootstrap.discovery import discover_presets, preset_config_path
from bootstrap.form_defaults import default_tuning
from bootstrap.template import render_preset_config
from bootstrap.ui_helpers import reload_presets, status_for_active
from bootstrap.validators import parse_keyword_list, validate_preset_id


def _parse_lines(text: str) -> list[str]:
    return parse_keyword_list(text)


def _service_rules_editor() -> list[dict[str, Any]]:
    st.caption("Service rules — une ligne par règle : `Label | mot1, mot2`")
    raw = st.text_area(
        "SERVICE_RULES",
        height=120,
        placeholder="Facility management | facility management, multiservices",
        key="cfg_service_rules",
    )
    rules: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if "|" not in line:
            continue
        label, kws = line.split("|", 1)
        label = label.strip()
        keywords = _parse_lines(kws)
        if label and keywords:
            rules.append({"label": label, "keywords": keywords})
    return rules


def render_config_tab(preset_id: str) -> str:
    st.subheader("1 — Config")
    status = status_for_active(preset_id)
    if preset_id:
        st.caption(f"Statut : {'✅ fichier config' if status.config_saved else '⬜ manquant'}")

    mode = st.radio(
        "Mode",
        ["Select existing", "Create new"],
        horizontal=True,
        key="cfg_mode",
    )

    if mode == "Select existing":
        presets = discover_presets(use_cache=True)
        if not presets:
            st.info("Aucun preset. Passez en **Create new**.")
            return preset_id
        ids = sorted(presets.keys())
        pick = st.selectbox(
            "Preset",
            ids,
            index=ids.index(preset_id) if preset_id in ids else 0,
            format_func=lambda pid: f"{presets[pid].label} ({pid})",
            key="cfg_select_preset",
        )
        if st.button("Utiliser ce preset", key="cfg_use_preset"):
            st.session_state.active_preset_id = pick
            st.rerun()
        return pick

    st.markdown("**Create new** — remplissez tous les champs métier, puis **Save**.")
    preset_id_input = st.text_input("Preset ID (snake_case)", key="cfg_preset_id")
    label = st.text_input("Label", key="cfg_label")
    service_default = st.text_input("SERVICE_DEFAULT", key="cfg_service_default")

    keywords = st.text_area("KEYWORDS (une par ligne ou virgules)", key="cfg_keywords")
    expansion_keywords = st.text_area("EXPANSION_KEYWORDS", key="cfg_expansion_kw")
    enrich_included = st.text_area("ENRICH_INCLUDED_KEYWORDS", key="cfg_enrich_in")
    enrich_hard = st.text_area("ENRICH_HARD_EXCLUDED_KEYWORDS", key="cfg_enrich_hard")
    enrich_soft = st.text_area("ENRICH_SOFT_EXCLUDED_KEYWORDS", key="cfg_enrich_soft")
    naf_prefixes = st.text_area("PAPPERS_NAF_PREFIXES (optionnel)", key="cfg_naf")

    angle = st.text_input("NICHE_METADATA — angle", key="cfg_angle")
    valeur = st.text_input("NICHE_METADATA — valeur_client", key="cfg_valeur")
    effectif = st.text_input("NICHE_METADATA — effectif_cible", key="cfg_effectif")

    service_rules = _service_rules_editor()
    tuning = default_tuning()
    tuning["NICHE_METADATA"] = {
        "angle": angle.strip(),
        "valeur_client": valeur.strip(),
        "effectif_cible": effectif.strip(),
    }
    tuning["PAPPERS_NAF_PREFIXES"] = _parse_lines(naf_prefixes)

    if st.button("Save config", type="primary", key="cfg_save"):
        try:
            pid = validate_preset_id(preset_id_input)
        except ValueError as exc:
            st.error(str(exc))
            return preset_id

        if not label.strip():
            st.error("Label requis.")
            return preset_id
        if not service_default.strip():
            st.error("SERVICE_DEFAULT requis.")
            return preset_id

        kw = _parse_lines(keywords)
        exp_kw = _parse_lines(expansion_keywords)
        if not kw or not exp_kw:
            st.error("KEYWORDS et EXPANSION_KEYWORDS requis.")
            return preset_id
        if not _parse_lines(enrich_included):
            st.error("ENRICH_INCLUDED_KEYWORDS requis.")
            return preset_id

        path = preset_config_path(pid)
        content = render_preset_config(
            preset_id=pid,
            label=label.strip(),
            list_id="",
            campaign_id="",
            subsequence_id="",
            target_leads=int(tuning.get("TARGET_LEADS", 5000)),
            keywords=kw,
            expansion_keywords=exp_kw,
            enrich_included=_parse_lines(enrich_included),
            enrich_hard_excluded=_parse_lines(enrich_hard),
            enrich_soft_excluded=_parse_lines(enrich_soft),
            service_default=service_default.strip(),
            service_rules=service_rules,
            tuning=tuning,
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        reload_presets()
        st.session_state.active_preset_id = pid
        st.success(f"Config sauvegardée : `{path}`")
        st.rerun()

    return preset_id
