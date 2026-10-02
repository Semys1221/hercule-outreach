"""Scrape dashboard — launch form, live progress, VPS history."""

from __future__ import annotations

import os
from typing import Any

import pandas as pd
import streamlit as st

from bootstrap.n8n_read import (
    executions_to_display_rows,
    fetch_recent_executions,
    n8n_configured,
)
from bootstrap.scrape_run_history import (
    detect_scrape_running,
    history_to_dataframe_rows,
    merge_n8n_into_history,
    merge_run_history,
)
from bootstrap.ui_helpers import (
    load_adhoc_scrape_form_defaults,
    merge_scrape_run_display,
    render_scrape_run_context_banner,
    select_instantly_lead_list,
    store_scrape_run_context,
)
from bootstrap.vps_control import (
    format_vps_connection_warning,
    load_panel_state,
    n8n_scrape_webhook_configured,
    resolve_scrape_default_preset_id,
    resolve_scrape_tracking_preset_id,
    stop_worker,
    trigger_n8n_scrape,
    vps_configured,
    worker_status,
)
from config_loader import load_config
from paths import output_paths
from scrape_state import load_scrape_state, ui_target_progress


def _progress_ratio(progress: int, target: int) -> float:
    if target <= 0:
        return 0.0
    return min(max(progress / target, 0.0), 1.0)


@st.fragment(run_every=15)
def _live_progress_and_history_panel(tracking_preset_id: str) -> None:
    config = load_config(tracking_preset_id, require_keys=False)
    paths = output_paths(tracking_preset_id)
    state, log_text, _, heartbeat, cron_events = load_panel_state(
        tracking_preset_id,
        max_log_lines=400,
        max_cron_lines=40,
    )
    if state is None:
        state = load_scrape_state(paths.scrape_state)

    vps = worker_status() if vps_configured() else None
    running, _code, running_label = detect_scrape_running(
        tracking_preset_id,
        state=state,
        heartbeat=heartbeat,
        vps=vps,
    )

    run_display = merge_scrape_run_display(tracking_preset_id, state, config)
    progress, target, at_target = ui_target_progress(config, state)
    merged_target = run_display.get("target_leads")
    if isinstance(merged_target, int) and merged_target > 0:
        target = merged_target
        at_target = progress >= target
    leads_saved = int(state.get("leads_saved", 0)) if state else 0
    instantly_pushed = int(state.get("instantly_pushed", 0)) if state else 0

    st.subheader("Suivi en cours")
    st.caption("Actualisation automatique toutes les 15 secondes.")

    if running:
        st.success(f"**Scrape en cours** — {running_label}")
    elif at_target:
        st.info(f"**Objectif atteint** — {progress}/{target}")
    else:
        st.info(f"**Inactif** — {running_label}")

    render_scrape_run_context_banner(run_display, running=running)

    st.progress(_progress_ratio(progress, target), text=f"{progress:,} / {target:,} leads")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Progression", f"{progress:,}")
    m2.metric("Objectif", f"{target:,}")
    m3.metric("Leads enregistrés", f"{leads_saved:,}")
    m4.metric("Poussés Instantly", f"{instantly_pushed:,}")

    if log_text.strip():
        with st.expander("Journal scrape (extrait)", expanded=running):
            st.code(log_text[-12000:], language="shell")

    st.subheader("État & historique")
    vps_rows: list[dict[str, Any]] = []
    if vps_configured() or state or log_text.strip():
        vps_rows = merge_run_history(
            None,
            state=state,
            log_text=log_text,
            cron_events=cron_events,
        )
    n8n_executions: list[dict] = []
    if n8n_configured():
        n8n_executions, _n8n_err = fetch_recent_executions(limit=25)
    history = merge_n8n_into_history(
        vps_rows,
        n8n_executions,
        preset_id=None,
    )
    table_rows = history_to_dataframe_rows(history)
    if table_rows:
        st.caption("Historique agrégé **n8n** + **VPS**.")
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)
    else:
        st.caption(
            "Aucune exécution enregistrée (scrape.log / scrape_state sur le VPS ou exécutions n8n)."
        )

    _render_n8n_executions(expanded=not table_rows)


def _render_n8n_executions(*, expanded: bool = False) -> None:
    if not n8n_configured():
        st.caption(
            "Historique n8n — définissez `N8N_API_KEY` et `N8N_BASE_URL` "
            "(ou `VPS_HOST` / `VPS_USER` pour lire n8n sur le VPS via SSH)."
        )
        return

    executions, err = fetch_recent_executions(limit=12)
    if err:
        st.warning(f"n8n — {err}")
    elif not executions:
        st.caption("n8n — aucune exécution récente.")
    else:
        with st.expander("Exécutions n8n (lecture seule)", expanded=expanded):
            st.dataframe(
                pd.DataFrame(executions_to_display_rows(executions)),
                use_container_width=True,
                hide_index=True,
            )


def _render_launch_controls() -> None:
    st.subheader("Lancer un scrape")

    n8n_ready = n8n_scrape_webhook_configured()
    if n8n_ready:
        st.caption(
            "Déclenchement via **webhook n8n** (`N8N_SCRAPE_WEBHOOK_URL`). "
            "Preset VPS implicite : `SCRAPE_DEFAULT_PRESET` / `N8N_DEFAULT_PRESET` ou `_adhoc`."
        )
    elif not vps_configured():
        st.caption("Configurez `N8N_SCRAPE_WEBHOOK_URL` pour lancer un scrape.")

    keyword_default, target_default, _config_list_id = load_adhoc_scrape_form_defaults()

    keyword = st.text_input(
        "Mots-clés de niche (recherche)",
        value=keyword_default,
        help="Termes Outscraper / Google Maps pour cette campagne.",
        key="scrape_keyword_adhoc",
    )

    selected_list = select_instantly_lead_list(
        label="Liste Instantly de destination",
        key="scrape_instantly_list_adhoc",
        current_id=None,
    )

    target_leads = st.number_input(
        "Volume cible (leads)",
        min_value=1,
        value=target_default,
        step=100,
        help="Nombre de leads visés pour cette exécution.",
        key="scrape_volume_adhoc",
    )

    missing_list = not (selected_list and selected_list.get("id"))
    missing_keyword = not keyword.strip()

    disabled_launch = missing_list or missing_keyword or not n8n_ready
    if missing_keyword and n8n_ready:
        st.caption("Saisissez au moins un mot-clé de recherche.")
    if missing_list and n8n_ready:
        st.caption("Sélectionnez une liste Instantly.")

    ctrl1, ctrl2, ctrl3 = st.columns(3)
    n8n_btn = ctrl1.button(
        "Lancer le scrape",
        type="primary",
        disabled=disabled_launch,
        key="scrape_trigger_n8n",
    )
    pause_btn = ctrl2.button(
        "Arrêter worker VPS",
        disabled=not vps_configured(),
        key="scrape_pause_worker",
    )
    refresh_btn = ctrl3.button("Actualiser", key="scrape_refresh")

    if n8n_btn:
        list_id = str(selected_list["id"]) if selected_list else ""
        ok, message = trigger_n8n_scrape(
            keyword=keyword,
            instantly_list_id=list_id,
            target_leads=int(target_leads),
        )
        if ok:
            store_scrape_run_context(
                resolve_scrape_default_preset_id(),
                keyword=keyword,
                instantly_list_id=list_id,
                instantly_list_name=str(selected_list.get("name", "")) if selected_list else "",
                target_leads=int(target_leads),
            )
            st.success(message)
        else:
            st.error(message)
        st.rerun()

    if pause_btn:
        ok, message = stop_worker()
        if ok:
            st.success(message)
        else:
            st.warning(message)
        st.rerun()

    if refresh_btn:
        st.rerun()


def render_scrape_tab() -> None:
    vps_probe = worker_status() if vps_configured() else None
    if not vps_configured() and not n8n_scrape_webhook_configured():
        st.info(
            "Scraping **VPS / n8n**. "
            "Ajoutez `VPS_HOST` / `VPS_USER` pour l'historique ou `N8N_SCRAPE_WEBHOOK_URL` pour lancer."
        )
    elif vps_probe and not vps_probe.get("reachable", True):
        st.warning(
            "Connexion VPS impossible — "
            f"{format_vps_connection_warning(vps_probe.get('detail', ''))}."
        )
    elif vps_configured():
        st.caption(
            f"VPS {os.getenv('VPS_HOST', '')} — données sous "
            f"`HERCULE_DATA_ROOT` (scrape_state, scrape.log, heartbeat)."
        )

    _render_launch_controls()
    tracking_preset = resolve_scrape_tracking_preset_id()
    _live_progress_and_history_panel(tracking_preset)
