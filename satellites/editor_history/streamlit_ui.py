"""Shared Streamlit UI for editor version history."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db import DOMAIN_REPLY_PROMPT, DOMAIN_SUBSEQUENCE, ensure_seeded_from_current, list_versions, promote_version

PARIS = ZoneInfo("Europe/Paris")

SUBSEQUENCE_ITEM_LABELS = {
    "interested_email1": "Email 1",
    "interested_email2": "Email 2",
    "interested_email3": "Email 3",
}

REPLY_ITEM_LABELS = {
    "buyer": "Buyer",
    "seller": "Seller",
}


def _format_paris(iso: str | None) -> str:
    if not iso:
        return "—"
    normalized = str(iso).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return iso
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(PARIS).strftime("%d/%m/%Y %H:%M")


def _excerpt(text: str, max_len: int = 80) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1] + "…"


def render_version_history_panel(
    *,
    domain: str,
    niche_key: str,
    campaign_id: str,
    item_keys: tuple[str, ...],
    item_labels: dict[str, str],
    get_current_content: Callable[[str], tuple[str, str | None]],
    on_promote: Callable[[dict[str, Any]], None],
    on_load_draft: Callable[[str, str, str | None], None],
    key_prefix: str,
) -> None:
    st.caption(
        f"Historique local (SQLite) · niche `{niche_key}` · "
        "Promouvoir repousse la version vers la prod ; **Charger** remplit l’éditeur sans enregistrer."
    )

    item_key = st.selectbox(
        "Modèle",
        options=item_keys,
        format_func=lambda k: item_labels.get(k, k),
        key=f"{key_prefix}_history_item",
    )

    subject_current, body_current = get_current_content(item_key)
    ensure_seeded_from_current(
        domain=domain,
        niche_key=niche_key,
        item_key=item_key,
        body_text=body_current,
        campaign_id=campaign_id,
        subject=subject_current,
    )

    seed_col, _ = st.columns([1, 3])
    with seed_col:
        if st.button("Importer l’état prod actuel", key=f"{key_prefix}_history_seed_{item_key}"):
            from db import insert_version

            insert_version(
                domain=domain,
                niche_key=niche_key,
                item_key=item_key,
                body_text=body_current,
                campaign_id=campaign_id,
                subject=subject_current,
                label="Snapshot prod manuel",
            )
            st.success("Version importée.")
            st.rerun()

    versions = list_versions(
        domain=domain,
        niche_key=niche_key,
        item_key=item_key,
        limit=50,
    )
    if not versions:
        st.info("Aucune version enregistrée pour ce modèle.")
        return

    df = pd.DataFrame(
        [
            {
                "id": v["id"],
                "Date (Paris)": _format_paris(v.get("created_at")),
                "Note": v.get("label") or "—",
                "Extrait": _excerpt(v.get("body_text") or ""),
                "Active": "Oui" if v.get("is_active") else "—",
            }
            for v in versions
        ]
    )
    st.dataframe(df, use_container_width=True, hide_index=True)

    version_ids = [v["id"] for v in versions]
    selected_id = st.selectbox(
        "Version",
        options=version_ids,
        format_func=lambda vid: f"#{vid} — {_format_paris(next(v['created_at'] for v in versions if v['id'] == vid))}",
        key=f"{key_prefix}_history_pick_{item_key}",
    )
    selected = next(v for v in versions if v["id"] == selected_id)

    act1, act2, _ = st.columns([1, 1, 2])
    with act1:
        if st.button("Promouvoir", type="primary", key=f"{key_prefix}_promote_{item_key}"):
            try:
                promote_version(selected_id, push_to_prod=on_promote)
                st.success(f"Version #{selected_id} promue (prod mise à jour).")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    with act2:
        if st.button("Charger dans l’éditeur", key=f"{key_prefix}_load_{item_key}"):
            on_load_draft(
                item_key,
                selected.get("body_text") or "",
                selected.get("subject"),
            )
            st.success("Contenu chargé dans l’éditeur — enregistrez pour créer une nouvelle version.")
            st.rerun()

    with st.expander("Aperçu complet"):
        if domain == DOMAIN_SUBSEQUENCE and selected.get("subject"):
            st.text_input("Objet (archive)", value=selected.get("subject") or "", disabled=True)
        st.text_area(
            "Contenu",
            value=selected.get("body_text") or "",
            height=240,
            disabled=True,
            key=f"{key_prefix}_preview_{selected_id}",
        )


def version_note_session_key(key_prefix: str) -> str:
    return f"{key_prefix}_version_note"


def read_version_note(key_prefix: str) -> str | None:
    raw = str(st.session_state.get(version_note_session_key(key_prefix)) or "").strip()
    return raw or None


def render_version_note_field(key_prefix: str) -> None:
    st.text_input(
        "Note de version (optionnelle, appliquée au prochain enregistrement)",
        key=version_note_session_key(key_prefix),
    )
