"""Tab 2 — Instantly lead list."""

from __future__ import annotations

import streamlit as st

from bootstrap.provision import write_instantly_ids
from bootstrap.ui_helpers import get_api_key, load_preset_config, reload_presets
from instantly_client import ensure_lead_list, instantly_resource_name, list_all_lead_lists


def render_list_tab(preset_id: str) -> None:
    st.subheader("2 — Liste Instantly")
    st.caption(
        "Obligatoire avant scrape/push (onglet Scrape et worker-loop). "
        "Copiez le **listId** depuis Instantly → Contacts (URL) ou sélectionnez une liste existante."
    )
    if not preset_id:
        st.warning("Sélectionnez ou créez une config (onglet 1).")
        return

    config = load_preset_config(preset_id)
    current = str(config.get("INSTANTLY_LIST_ID") or "").strip()
    if current:
        st.success(f"Liste liée : `{current}`")
    else:
        st.info("Aucune liste liée.")

    api_key = get_api_key()
    if not api_key:
        st.error("INSTANTLY_API_KEY manquant dans le .env")
        return

    mode = st.radio("Liste", ["Select existing", "Create new"], horizontal=True, key="list_mode")
    lists = list_all_lead_lists(api_key)

    if mode == "Select existing":
        if not lists:
            st.warning("Aucune liste dans le workspace.")
            return
        options = {str(x["id"]): str(x.get("name") or x["id"]) for x in lists}
        pick = st.selectbox(
            "Choisir une liste",
            list(options.keys()),
            format_func=lambda i: options[i],
            key="list_pick",
        )
        if st.button("Lier cette liste", key="list_link"):
            from bootstrap.discovery import preset_config_path

            campaign_id = str(config.get("INSTANTLY_CAMPAIGN_ID") or "").strip()
            subseq = str(config.get("INSTANTLY_SUBSEQUENCE_ID") or "").strip()
            write_instantly_ids(
                preset_config_path(preset_id),
                list_id=pick,
                campaign_id=campaign_id,
                subsequence_id=subseq,
            )
            reload_presets()
            st.success("Liste liée.")
            st.rerun()
    else:
        name = st.text_input("Nom de la nouvelle liste", key="list_new_name")
        if st.button("Créer et lier", key="list_create"):
            if not name.strip():
                st.error("Nom requis.")
                return
            created = ensure_lead_list(api_key, instantly_resource_name(name.strip()))
            list_id = str(created.get("id") or "")
            from bootstrap.discovery import preset_config_path

            campaign_id = str(config.get("INSTANTLY_CAMPAIGN_ID") or "").strip()
            subseq = str(config.get("INSTANTLY_SUBSEQUENCE_ID") or "").strip()
            write_instantly_ids(
                preset_config_path(preset_id),
                list_id=list_id,
                campaign_id=campaign_id,
                subsequence_id=subseq,
            )
            reload_presets()
            st.success(f"Liste créée : {list_id}")
            st.rerun()
