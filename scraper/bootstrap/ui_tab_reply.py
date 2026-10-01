"""Tab 6 — Buyer reply agent prompt."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from bootstrap.app_imports import load_app_module
from bootstrap.campaign_layers import bootstrap_reply_prompt_layer
from bootstrap.ui_helpers import load_preset_config, status_for_active
from repo_paths import reply_agent_app

_REPLY_APP = reply_agent_app()


def _load_existing_prompt(preset_id: str) -> str:
    path = _REPLY_APP / "prompts" / f"{preset_id}_buyer.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def render_reply_tab(preset_id: str) -> None:
    st.subheader("6 — Prompt reply agent (buyer)")
    if not preset_id:
        st.warning("Sélectionnez ou créez une config (onglet 1).")
        return

    config = load_preset_config(preset_id)
    campaign_id = str(config.get("INSTANTLY_CAMPAIGN_ID") or "").strip()
    label = str(config.get("PRESET_LABEL") or preset_id)

    if not _load_existing_prompt(preset_id).strip():
        try:
            written = bootstrap_reply_prompt_layer(preset_id, label=label)
            if written:
                st.info(f"Prompts reply agent générés : {', '.join(Path(p).name for p in written)}")
        except Exception as exc:
            st.caption(f"Scaffold prompts : {exc}")

    existing = _load_existing_prompt(preset_id)
    if existing.strip():
        st.success("Prompt buyer existant.")

    prompt_text = st.text_area(
        "Prompt buyer (markdown)",
        value=existing,
        height=400,
        key="reply_buyer_prompt",
    )

    if st.button("Enregistrer le prompt buyer", type="primary", key="reply_save"):
        if not prompt_text.strip():
            st.error("Le prompt ne peut pas être vide.")
            return

        reply_dir = str(_REPLY_APP)
        prompt_store = load_app_module(reply_dir, "prompt_store")

        reply_config = None
        if campaign_id:
            try:
                supabase_repo = load_app_module(reply_dir, "supabase_repo")
                reply_config = supabase_repo.get_config(campaign_id)
            except Exception:
                reply_config = None

        result = prompt_store.save_prompt(
            preset_id,
            "buyer",
            prompt_text.strip(),
            campaign_id=campaign_id or None,
            config=reply_config,
            push_prod=bool(campaign_id and reply_config),
        )
        if result.get("prod"):
            st.success("Prompt enregistré (fichier + Supabase).")
        else:
            st.success("Prompt enregistré (fichier).")
            if result.get("reason"):
                reason = str(result["reason"])
                st.caption(f"Supabase : {reason}")
                if reason in {"no_config", "not_active"} and campaign_id:
                    st.caption(
                        "Activez le reply agent en prod avec "
                        "`pnpm activate-reply-agents --preset "
                        f"{preset_id}` après validation du prompt."
                    )

        status = status_for_active(preset_id)
        if status.complete:
            st.caption("Preset prêt — ouvrez **Scrape** dans la barre latérale.")
        else:
            missing = status.missing()
            if missing:
                st.caption(f"Onboarding restant : {', '.join(missing)}")
