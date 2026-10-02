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
    start_worker,
    stop_worker,
    vps_configured,
    worker_status,
)
from config_loader import load_config
from scrape_metrics import heartbeat_age_seconds
from scrape_state import detect_recoverable_run, is_instantly_push_mode, target_mode
from core_logic import output_paths


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


def _render_worker_controls(
    preset_id: str,
    *,
    at_target: bool,
    mode: str,
    has_instantly: bool,
    vps: dict[str, Any] | None = None,
) -> None:
    if not vps_configured():
        st.subheader("Lancer un scrape")
        st.caption(
            "Les scrapes s'exécutent **uniquement sur le VPS** (worker systemd, "
            "souvent déclenché via n8n). Configurez `VPS_HOST` et `VPS_USER` dans `.env` "
            "pour démarrer le worker et lire l'historique — pas d'exécution locale."
        )
        if st.button("Actualiser", key="scrape_refresh"):
            st.rerun()
        return

    _, _, _, heartbeat, _ = load_panel_state(preset_id)
    vps = vps or worker_status()
    status_label = _worker_state_label(heartbeat, bool(vps.get("active")))

    st.subheader("Lancer un scrape")
    st.caption(
        f"État worker : **{status_label}**. "
        "Démarrage via **Démarrer worker VPS** (`start_worker` → systemd sur le VPS). "
        "Si votre flux passe par n8n, le webhook/workflow n8n reste l'autre entrée."
    )

    ctrl1, ctrl2, ctrl3 = st.columns(3)
    continue_btn = ctrl1.button(
        "Démarrer worker VPS",
        type="primary",
        disabled=at_target or (is_instantly_push_mode(mode) and not has_instantly),
        key="scrape_continue_worker",
    )
    pause_btn = ctrl2.button("Arrêter worker VPS", key="scrape_pause_worker")
    refresh_btn = ctrl3.button("Actualiser", key="scrape_refresh")

    if continue_btn:
        ok, message = start_worker(preset_id)
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
            "Scraping **VPS uniquement** (n8n + worker systemd). "
            "Ajoutez `VPS_HOST` / `VPS_USER` pour lire l'historique scrape à distance."
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

    if vps_configured():
        if st.button("Actualiser", key="scrape_refresh_no_preset"):
            st.rerun()


def render_scrape_tab(preset_id: str) -> None:
    if not preset_id:
        _render_scrape_without_preset()
        return

    config = load_config(preset_id, require_keys=False)
    paths = output_paths(preset_id)
    recovery = detect_recoverable_run(config, paths.csv, state_path=paths.scrape_state)
    target = int(config.get("TARGET_LEADS", 0))
    mode = target_mode(config)
    has_instantly = bool(config.get("INSTANTLY_API_KEY") and config.get("INSTANTLY_LIST_ID"))
    at_target = recovery.headline_progress >= target > 0

    vps_probe = worker_status() if vps_configured() else None
    if not vps_configured():
        st.info(
            "Scraping **VPS uniquement** (n8n + worker systemd). "
            "Ajoutez `VPS_HOST` / `VPS_USER` pour lire l'historique et démarrer le worker."
        )
    elif vps_probe and not vps_probe.get("reachable", True):
        st.warning(
            "Connexion VPS impossible — "
            f"{format_vps_connection_warning(vps_probe.get('detail', ''))}."
        )
    else:
        st.caption(
            f"VPS {os.getenv('VPS_HOST', '')} — données sous "
            f"`HERCULE_DATA_ROOT` (scrape_state, scrape.log, heartbeat)."
        )

    _status_and_history_panel(preset_id)
    _render_worker_controls(
        preset_id,
        at_target=at_target,
        mode=mode,
        has_instantly=has_instantly,
        vps=vps_probe,
    )
