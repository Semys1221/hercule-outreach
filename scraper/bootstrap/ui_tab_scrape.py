"""Tab — Scrape operations panel (VPS worker + live metrics)."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pandas as pd
import streamlit as st

from bootstrap.discovery import discover_presets
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
    remote_csv_lead_count,
    start_worker,
    stop_worker,
    vps_configured,
    worker_status,
)
from config_loader import load_config
from core_logic import clear_local_leads, output_paths
from scrape_metrics import fetch_instantly_live, heartbeat_age_seconds
from scrape_state import (
    detect_recoverable_run,
    is_instantly_push_mode,
    target_mode,
    target_progress_value,
)


def _count_pappers_rejects(audit_path: str) -> int:
    if not audit_path or not os.path.isfile(audit_path):
        return 0
    try:
        df = pd.read_csv(audit_path)
        if df.empty or "Enrich_Reason" not in df.columns:
            return 0
        return int(df["Enrich_Reason"].astype(str).str.startswith("REJECT_").sum())
    except (OSError, pd.errors.EmptyDataError, ValueError):
        return 0


def _format_age(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{int(seconds)}s ago"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    return f"{int(seconds // 3600)}h ago"


def _worker_state_label(heartbeat: dict | None, vps_active: bool) -> str:
    age = heartbeat_age_seconds(heartbeat)
    if vps_active:
        return "Worker VPS actif"
    if age is not None and age < 900:
        return "Heartbeat actif"
    if age is not None:
        return "En pause (heartbeat expiré)"
    return "Inactif"


def _parse_log_totals(log_text: str) -> tuple[int | None, int | None]:
    """Parse last enrich totals line from scrape.log tail."""
    if not log_text:
        return None, None
    import re

    enriched: int | None = None
    rejected: int | None = None
    for line in reversed(log_text.splitlines()):
        match = re.search(
            r"totals:\s*(\d+)\s*valid\s*/\s*(\d+)\s*rejected",
            line,
            flags=re.IGNORECASE,
        )
        if match:
            enriched = int(match.group(1))
            rejected = int(match.group(2))
            break
    return enriched, rejected


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


@st.fragment(run_every=5)
def _live_panel(
    preset_id: str,
    config: dict,
    paths,
    recovery,
    target: int,
    mode: str,
) -> None:
    state, log_text, out_dir, heartbeat, cron_events = load_panel_state(preset_id)
    instantly_live = fetch_instantly_live(config)
    checkpoint_pushed = int(state.get("instantly_pushed", 0)) if state else 0
    state_scraped = int(state.get("leads_saved", 0)) if state else 0
    remote_scraped = remote_csv_lead_count(preset_id) if vps_configured() else None
    scraped = max(state_scraped, remote_scraped or 0)
    enriched = int(state.get("leads_enriched_valid", 0)) if state else 0
    rejected = int(state.get("leads_enriched_rejected", 0)) if state else 0
    log_enriched, log_rejected = _parse_log_totals(log_text)
    if log_enriched is not None and log_enriched > enriched:
        enriched = log_enriched
    if log_rejected is not None and log_rejected > rejected:
        rejected = log_rejected
    inflight = len(state.get("inflight_tasks") or []) if state else 0
    query_pass = int(state.get("query_pass", 0)) if state else 0
    batches_total = int(state.get("batches_total", 0)) if state else 0
    last_batch = int(state.get("last_completed_batch_index", -1)) if state else -1

    headline = target_progress_value(
        mode,
        instantly_pushed=checkpoint_pushed,
        leads_saved=scraped,
        instantly_live=instantly_live,
    )
    progress = min(headline / target, 1.0) if target > 0 else 0.0

    vps = worker_status()
    status_label = _worker_state_label(heartbeat, bool(vps.get("active")))

    if status_label == "En pause (heartbeat expiré)":
        st.error(
            f"Worker en pause — dernier heartbeat "
            f"{_format_age(heartbeat_age_seconds(heartbeat))}"
        )
    elif status_label == "Worker VPS actif":
        st.success(f"Worker VPS actif ({vps.get('host', '')})")
    elif status_label == "Heartbeat actif":
        st.info(f"Heartbeat {_format_age(heartbeat_age_seconds(heartbeat))}")

    st.progress(progress, text=f"Progrès {headline:,} / {target:,} ({mode})")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Instantly (live)", f"{instantly_live:,}" if instantly_live is not None else "—")
    c2.metric("This run (checkpoint)", f"{checkpoint_pushed:,}")
    c3.metric("Scraped CSV", f"{scraped:,}")
    c4.metric("Enriched valid", f"{enriched:,}")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Enrich rejected", f"{rejected:,}")
    c6.metric("Outscraper in-flight", inflight)
    c7.metric("Query pass", query_pass + 1)
    c8.metric(
        "Batches",
        f"{max(last_batch + 1, 0)}/{batches_total}" if batches_total else "—",
    )

    if config.get("PAPPERS_ENABLED"):
        st.caption(f"Pappers rejected: {_count_pappers_rejects(paths.enrich_audit):,}")

    if recovery and recovery.message:
        st.caption(recovery.message)

    if log_text:
        st.code(log_text, language="shell")

    if cron_events:
        with st.expander("Cron heal events"):
            for event in reversed(cron_events[-5:]):
                st.write(
                    f"{event.get('ts', '')} — {event.get('action', '')} "
                    f"live {event.get('live_before', '?')} → {event.get('live_after', '?')}"
                )


def _mask_uuid(value: str) -> str:
    value = str(value or "").strip()
    if len(value) < 12:
        return value or "—"
    return f"{value[:8]}…{value[-4:]}"


def _render_config_summary(config: dict[str, Any], preset_id: str) -> None:
    presets = discover_presets(use_cache=True)
    label = presets[preset_id].label if preset_id in presets else preset_id
    keywords = config.get("KEYWORDS") or []
    keyword_preview = ", ".join(keywords[:5])
    if len(keywords) > 5:
        keyword_preview += f" (+{len(keywords) - 5})"

    with st.expander("Config preset (lecture seule)", expanded=False):
        c1, c2 = st.columns(2)
        c1.markdown(f"**Label** — {label}")
        c1.markdown(f"**Preset ID** — `{preset_id}`")
        c1.markdown(f"**SERVICE_DEFAULT** — {config.get('SERVICE_DEFAULT', '—')}")
        c2.markdown(f"**TARGET_LEADS** — {int(config.get('TARGET_LEADS', 0) or 0):,}")
        c2.markdown(f"**TARGET_MODE** — `{config.get('TARGET_MODE', '—')}`")
        c2.markdown(
            f"**Instantly list** — `{_mask_uuid(config.get('INSTANTLY_LIST_ID', ''))}`"
        )
        c2.markdown(
            f"**Instantly campaign** — `{_mask_uuid(config.get('INSTANTLY_CAMPAIGN_ID', ''))}`"
        )

        st.caption(f"KEYWORDS — {keyword_preview or '—'}")

        keys = st.columns(2)
        outscraper_ok = bool(config.get("OUTSCRAPER_API_KEY"))
        instantly_ok = bool(config.get("INSTANTLY_API_KEY"))
        keys[0].caption(f"{'✅' if outscraper_ok else '⬜'} OUTSCRAPER_API_KEY")
        keys[1].caption(f"{'✅' if instantly_ok else '⬜'} INSTANTLY_API_KEY")


def _render_worker_controls(
    preset_id: str,
    *,
    at_target: bool,
    mode: str,
    has_instantly: bool,
    vps: dict[str, Any] | None = None,
) -> None:
    if not vps_configured():
        st.caption(
            "Les scrapes s'exécutent **uniquement sur le VPS** (worker systemd, "
            "déclenché via n8n). Configurez `VPS_HOST` et `VPS_USER` dans `.env` "
            "pour suivre l'état à distance — pas de worker local."
        )
        if st.button("Actualiser", key="scrape_refresh"):
            st.rerun()
        return

    _, _, _, heartbeat, _ = load_panel_state(preset_id)
    vps = vps or worker_status()
    status_label = _worker_state_label(heartbeat, bool(vps.get("active")))

    st.subheader("Contrôles VPS")
    st.caption(
        f"État worker : **{status_label}**. "
        "Les runs sont orchestrés sur le VPS (n8n → systemd) — pas d'exécution locale."
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
    st.caption(
        "Les contrôles worker, métriques live et historique **par preset** "
        "apparaissent une fois l'onboarding terminé (onglets 1 à 6)."
    )
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
        st.caption(
            "Historique agrégé depuis **n8n** (aucun preset onboarding prêt pour scrape.log VPS)."
        )
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)
    else:
        st.info(
            "**Aucun preset prêt** — pas d'historique scrape.log / checkpoint VPS. "
            "Configurez n8n ou terminez l'onboarding pour voir les runs."
        )
        if n8n_err:
            st.warning(f"n8n — {n8n_err}")
    _render_n8n_executions(expanded=not table_rows)

    if vps_configured():
        if st.button("Actualiser", key="scrape_refresh_no_preset"):
            st.rerun()


def render_scrape_tab(preset_id: str, add_log) -> None:
    st.subheader("Scrape — operations panel")

    if not preset_id:
        _render_scrape_without_preset()
        return

    config = load_config(preset_id, require_keys=False)
    paths = output_paths(preset_id)
    list_id = str(config.get("INSTANTLY_LIST_ID") or "").strip()
    if not list_id:
        st.error(
            "Étape 1 — aucune liste Instantly (`INSTANTLY_LIST_ID`). "
            "Liez la liste dans **Onboarding → onglet 2 Liste** (listId dans l’URL Instantly Contacts) "
            "avant de lancer un scrape/push."
        )
    recovery = detect_recoverable_run(config, paths.csv, state_path=paths.scrape_state)
    target = int(config.get("TARGET_LEADS", 0))
    mode = target_mode(config)
    has_instantly = bool(config.get("INSTANTLY_API_KEY") and config.get("INSTANTLY_LIST_ID"))
    instantly_live = fetch_instantly_live(config)
    at_target = recovery.headline_progress >= target > 0

    vps_probe = worker_status() if vps_configured() else None
    if not vps_configured():
        st.info(
            "Scraping **VPS uniquement** (n8n + worker systemd). "
            "Ajoutez `VPS_HOST` / `VPS_USER` pour lire l'historique et le statut à distance."
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
    _live_panel(preset_id, config, paths, recovery, target, mode)

    _render_worker_controls(
        preset_id,
        at_target=at_target,
        mode=mode,
        has_instantly=has_instantly,
        vps=vps_probe,
    )

    _render_config_summary(config, preset_id)

    if vps_configured():
        st.caption(
            "Push Instantly automatique sur le VPS (worker-loop). "
            "Pas de push CSV depuis cette interface."
        )
        with st.expander("Zone sensible — effacer le checkpoint VPS"):
            st.warning(
                "Supprime le CSV et scrape_state.json **sur le VPS** (SSH). "
                "**Ne supprime pas** les leads déjà dans Instantly."
            )
            confirm = st.checkbox(
                "Je confirme la suppression du checkpoint VPS",
                key="scrape_wipe_confirm",
            )
            wipe_btn = st.button("Effacer checkpoint VPS", disabled=not confirm, key="scrape_wipe")
            if wipe_btn:
                with st.spinner("Suppression du checkpoint…"):
                    result = asyncio.run(
                        clear_local_leads(
                            cancel_remote=bool(config.get("OUTSCRAPER_API_KEY")),
                            api_key=config.get("OUTSCRAPER_API_KEY", ""),
                            log_cb=add_log,
                            preset=preset_id,
                        )
                    )
                st.success(
                    f"Checkpoint effacé — {result['leads_removed']} ligne(s) retirées du CSV. "
                    f"Instantly live : {instantly_live if instantly_live is not None else '?'}"
                )
                st.rerun()

