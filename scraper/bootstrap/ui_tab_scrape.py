"""Scrape dashboard — VPS history table + launch controls."""

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
from bootstrap.vps_control import (
    format_vps_connection_warning,
    load_panel_state,
    n8n_scrape_webhook_configured,
    stop_worker,
    trigger_n8n_scrape,
    vps_configured,
    worker_status,
)
from config_loader import load_config
from paths import output_paths
from scrape_metrics import heartbeat_age_seconds
from scrape_state import is_instantly_push_mode, load_scrape_state, target_mode, ui_target_progress


def _worker_state_label(heartbeat: dict | None, vps_active: bool) -> str:
    age = heartbeat_age_seconds(heartbeat)
    if vps_active:
        return "Worker VPS actif"
    if age is not None and age < 900:
        return "Heartbeat actif"
    if age is not None:
        return "En pause (heartbeat expiré)"
    return "Inactif"


@st.fragment(run_every=15)
def _status_and_history_panel(preset_id: str) -> None:
    state, log_text, _, heartbeat, cron_events = load_panel_state(
        preset_id,
        max_log_lines=400,
        max_cron_lines=40,
    )
    vps = worker_status() if vps_configured() else None
    running, _code, running_label = detect_scrape_running(
        preset_id,
        state=state,
        heartbeat=heartbeat,
        vps=vps,
    )

    st.subheader("État & historique")
    if running:
        st.success(f"**Scrape en cours** — {running_label}")
    else:
        st.info(f"**Aucun scrape en cours** — {running_label}")

    history = merge_run_history(
        preset_id,
        state=state,
        log_text=log_text,
        cron_events=cron_events,
    )
    n8n_executions: list[dict] = []
    if n8n_configured():
        n8n_executions, _n8n_err = fetch_recent_executions(limit=20)
    history = merge_n8n_into_history(
        history,
        n8n_executions,
        preset_id=preset_id,
    )
    table_rows = history_to_dataframe_rows(history)
    if table_rows:
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)
    else:
        st.caption(
            "Aucune exécution enregistrée pour ce preset "
            "(scrape.log / scrape_state.json sur le VPS)."
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


def _render_launch_controls(
    preset_id: str,
    *,
    at_target: bool,
    mode: str,
    has_instantly: bool,
    vps: dict[str, Any] | None = None,
) -> None:
    st.subheader("Lancer un scrape")

    n8n_ready = n8n_scrape_webhook_configured()
    if n8n_ready:
        st.caption(
            "Entrée recommandée : **webhook n8n** (`N8N_SCRAPE_WEBHOOK_URL`). "
            "Le worker VPS peut être arrêté manuellement si besoin."
        )
    elif vps_configured():
        st.caption(
            "Configurez `N8N_SCRAPE_WEBHOOK_URL` pour déclencher le flux n8n. "
            "L'historique VPS reste disponible via SSH."
        )
    else:
        st.caption(
            "Configurez `N8N_SCRAPE_WEBHOOK_URL` et/ou `VPS_HOST` + `VPS_USER` "
            "pour lancer ou suivre les scrapes."
        )

    _, _, _, heartbeat, _ = load_panel_state(preset_id)
    vps = vps or (worker_status() if vps_configured() else None)
    status_label = _worker_state_label(heartbeat, bool(vps and vps.get("active")))

    if vps_configured():
        st.caption(f"État worker VPS : **{status_label}**.")

    disabled_launch = at_target or (is_instantly_push_mode(mode) and not has_instantly)

    ctrl1, ctrl2, ctrl3 = st.columns(3)
    n8n_btn = ctrl1.button(
        "Lancer via n8n",
        type="primary",
        disabled=disabled_launch or not n8n_ready,
        key="scrape_trigger_n8n",
    )
    pause_btn = ctrl2.button(
        "Arrêter worker VPS",
        disabled=not vps_configured(),
        key="scrape_pause_worker",
    )
    refresh_btn = ctrl3.button("Actualiser", key="scrape_refresh")

    if n8n_btn:
        ok, message = trigger_n8n_scrape(preset_id)
        if ok:
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


def _render_scrape_without_preset() -> None:
    vps_probe = worker_status() if vps_configured() else None
    if not vps_configured():
        st.info(
            "Scraping **VPS / n8n**. "
            "Ajoutez `VPS_HOST` / `VPS_USER` pour l'historique scrape à distance "
            "ou `N8N_SCRAPE_WEBHOOK_URL` pour lancer."
        )
    elif vps_probe and not vps_probe.get("reachable", True):
        st.warning(
            "Connexion VPS impossible — "
            f"{format_vps_connection_warning(vps_probe.get('detail', ''))}."
        )

    st.subheader("État & historique")
    table_rows: list[dict[str, str]] = []
    n8n_err: str | None = None
    if n8n_configured():
        executions, n8n_err = fetch_recent_executions(limit=25)
        if executions:
            history = merge_n8n_into_history([], executions, preset_id=None)
            table_rows = history_to_dataframe_rows(history)
    if table_rows:
        st.caption("Historique agrégé depuis **n8n** (sélectionnez un preset pour le détail VPS).")
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)
    else:
        st.info(
            "Aucun historique — configurez le VPS et/ou n8n, ou choisissez un preset."
        )
        if n8n_err:
            st.warning(f"n8n — {n8n_err}")
    _render_n8n_executions(expanded=not table_rows)

    if vps_configured() or n8n_scrape_webhook_configured():
        if st.button("Actualiser", key="scrape_refresh_no_preset"):
            st.rerun()


def render_scrape_tab(preset_id: str) -> None:
    if not preset_id:
        _render_scrape_without_preset()
        return

    config = load_config(preset_id, require_keys=False)
    paths = output_paths(preset_id)
    state, _, _, _, _ = load_panel_state(preset_id, max_log_lines=1, max_cron_lines=1)
    if state is None:
        state = load_scrape_state(paths.scrape_state)
    _progress, _target, at_target = ui_target_progress(config, state)
    mode = target_mode(config)
    has_instantly = bool(config.get("INSTANTLY_API_KEY") and config.get("INSTANTLY_LIST_ID"))

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

    _status_and_history_panel(preset_id)
    _render_launch_controls(
        preset_id,
        at_target=at_target,
        mode=mode,
        has_instantly=has_instantly,
        vps=vps_probe,
    )
