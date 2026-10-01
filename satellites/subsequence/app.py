"""Instantly subsequence — Streamlit operations dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

_APP_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _APP_DIR.parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from config import (
    env,
    is_valid_webhook_target_url,
    require_instantly_api_key,
    webhook_auto_send_enabled,
    webhook_public_url,
    webhook_secret,
    webhook_url_error,
)
from onboarding import (
    copy_is_complete,
    derive_onboarding_status,
    e1_copy_is_ready,
    explain_webhook_miss,
    find_campaign_webhook,
    initialize_campaign,
    is_webhook_active,
)
from send_queue import (
    DEFAULT_FLOW_BY_STEP,
    PIPELINE_STEPS,
    SENDABLE_FLOWS,
    Flow,
    PipelineStep,
    dispatch_bulk,
    dispatch_conversation_reply,
    fetch_pipeline_leads,
    format_last_reply_label,
    leads_for_step,
    move_pipeline_leads,
    render_template_html,
    suggest_flow_for_lead,
)
from send_window import format_paris_slot, is_within_send_window, next_send_slot
from unibox_classify import derive_step_from_flows, is_no_show_status
from unibox_thread import (
    fetch_latest_reply,
    render_conversation_html,
    thread_subject,
)
from shared.instantly_client import InstantlyClient, format_resource_label, list_all_campaigns
from editor_history import (
    render_subsequence_history_note,
    render_subsequence_history_tab,
    save_template_with_history,
)
from supabase_repo import (
    fetch_analytics,
    get_config,
    list_templates,
    set_campaign_pipeline_auto_advance_enabled,
    set_campaign_webhook_auto_send_enabled,
    sync_webhook_id,
)

st.set_page_config(page_title="Streamlit Subsequence", layout="wide")
st.title("Streamlit Subsequence")
st.caption("CRM étapes 0–4 → Unibox reply → E1 webhook auto (+2 min), E2/E3/step_4 via cron 15 min.")

FLOW_LABELS: dict[Flow, str] = {
    "interested_email1": "Email 1 — Précisions + candidature (webhook auto ou manuel)",
    "interested_email2": "Email 2 — Relance contrat annuel",
    "interested_email3": "Email 3 — Clôture",
}

STEP_LABELS: dict[PipelineStep, str] = {
    "step_0": "Étape 0 — En attente E1",
    "step_1": "Étape 1 — E1 envoyé",
    "step_2": "Étape 2 — E2 envoyé",
    "step_3": "Étape 3 — E3 envoyé",
    "step_4": "Étape 4 — Clôturé (Not Interested)",
    "replies_to_handle": "Réponses à traiter",
}

TEMPLATE_KEYS = (
    "interested_email1",
    "interested_email2",
    "interested_email3",
)

STATUS_LABELS = {
    "not_initialized": "Non initialisé",
    "copy_incomplete": "Copy incomplet",
    "webhook_incomplete": "Webhook manquant",
    "ready": "Prêt",
}

URGENT_BLINK_CSS = """
<style>
@keyframes subseq-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
.subseq-urgent {
  animation: subseq-blink 1.2s ease-in-out infinite;
  color: #c0392b;
  font-weight: 600;
}
</style>
"""


def _inject_urgent_css() -> None:
    if st.session_state.get("_subseq_urgent_css"):
        return
    st.markdown(URGENT_BLINK_CSS, unsafe_allow_html=True)
    st.session_state["_subseq_urgent_css"] = True


def _step_radio_label(step: PipelineStep, all_queue: list | None) -> str:
    base = STEP_LABELS[step]
    if step != "replies_to_handle" or not all_queue:
        return base.split(" — ")[0] if step != "replies_to_handle" else base
    replies = leads_for_step(all_queue, "replies_to_handle")
    urgent_count = sum(1 for row in replies if row.awaiting_reply_over_24h)
    short = base.split(" — ")[0]
    if urgent_count:
        return f"{short} ({len(replies)} · {urgent_count} urgents)"
    if replies:
        return f"{short} ({len(replies)})"
    return short


def _queue_to_dataframe(queue: list) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Envoyer": row.envoyer,
                "Alerte": "🔴 24h+" if row.awaiting_reply_over_24h else "—",
                "Email": row.email,
                "Prénom": row.first_name,
                "Statut": row.interest_label,
                "Étape": STEP_LABELS[row.step],
                "Répondu depuis envoi Hercule": "Oui" if row.replied_since_last_send else "Non",
                "Dernière réponse prospect": format_last_reply_label(row.last_reply_at),
                "Lien OK": "Non" if row.missing_reservation_link else "Oui",
                "Emails déjà envoyés": ", ".join(row.sent_flows) if row.sent_flows else "—",
                "Dernier envoi Hercule": row.last_sent_at or "—",
            }
            for row in queue
        ]
    )


def _template_field_keys(key_prefix: str, campaign_id: str, key: str) -> tuple[str, str]:
    return (
        f"{key_prefix}_sub_{campaign_id}_{key}",
        f"{key_prefix}_body_{campaign_id}_{key}",
    )


def _clear_template_session_keys(campaign_id: str, template_key: str | None = None) -> None:
    for prefix in ("setup", "templates"):
        if template_key:
            for field_key in _template_field_keys(prefix, campaign_id, template_key):
                st.session_state.pop(field_key, None)
        else:
            for key in TEMPLATE_KEYS:
                for field_key in _template_field_keys(prefix, campaign_id, key):
                    st.session_state.pop(field_key, None)


def _show_template_save_result(result: dict) -> None:
    st.success("Modèle enregistré (DB + prod Instantly).")
    code_sync = result.get("code_sync") or {}
    if code_sync.get("default_templates"):
        st.caption("Default bootstrap E1 synchronisé (default_templates.py).")
    elif code_sync.get("errors"):
        st.warning(
            "DB OK — sync bootstrap partielle : "
            + "; ".join(str(err) for err in code_sync["errors"])
        )


def _render_sequence_form(campaign_id: str, templates: list[dict], *, key_prefix: str) -> None:
    template_map = {t["template_key"]: t for t in templates}
    edited: list[dict[str, str]] = []

    render_subsequence_history_note(key_prefix)

    if st.button("Recharger les modèles", key=f"{key_prefix}_reload_{campaign_id}"):
        _clear_template_session_keys(campaign_id)
        st.rerun()

    for key in TEMPLATE_KEYS:
        row = template_map.get(key, {"subject": "", "body_html": ""})
        st.markdown(f"**{FLOW_LABELS.get(key, key)}**")
        sub_key, body_key = _template_field_keys(key_prefix, campaign_id, key)
        if sub_key not in st.session_state:
            st.session_state[sub_key] = row.get("subject", "")
        if body_key not in st.session_state:
            st.session_state[body_key] = row.get("body_html", "")
        subject = st.text_input(f"Subject ({key})", key=sub_key)
        body = st.text_area(f"Body HTML ({key})", height=160, key=body_key)
        sync_bootstrap = False
        if key == "interested_email1":
            sync_bootstrap = st.checkbox(
                "Mettre à jour le default bootstrap (nouvelles campagnes)",
                value=False,
                key=f"{key_prefix}_sync_bootstrap_{campaign_id}_{key}",
            )
        save_col, _ = st.columns([1, 3])
        with save_col:
            if st.button("Enregistrer", key=f"{key_prefix}_save_{campaign_id}_{key}"):
                result = save_template_with_history(
                    campaign_id,
                    key,
                    subject,
                    body,
                    sync_bootstrap_default=sync_bootstrap,
                    key_prefix=key_prefix,
                )
                _clear_template_session_keys(campaign_id, key)
                st.session_state[sub_key] = subject
                st.session_state[body_key] = body
                _show_template_save_result(result)
                st.rerun()
        edited.append(
            {
                "template_key": key,
                "subject": subject,
                "body_html": body,
                "sync_bootstrap_default": sync_bootstrap,
            }
        )

    if st.button(
        "Enregistrer tous les modèles",
        type="primary",
        key=f"{key_prefix}_save_all_{campaign_id}",
    ):
        for item in edited:
            save_template_with_history(
                campaign_id,
                item["template_key"],
                item["subject"],
                item["body_html"],
                sync_bootstrap_default=item.get("sync_bootstrap_default", False),
                key_prefix=key_prefix,
            )
        _clear_template_session_keys(campaign_id)
        st.success("Tous les modèles enregistrés (DB + prod Instantly).")
        st.rerun()

    st.caption(
        "Variables: {{reservation_link}}, {{first_name}}, "
        "{{last_name}}, {{company_name}}. Sujet E1 = fil de réponse ; E2/E3 = fil ou sujet modèle si renseigné. "
        "`reservation_link` n’est exigé à l’envoi que s’il apparaît dans le HTML."
    )


def _render_conversation_panel(
    *,
    campaign_id: str,
    queue: list,
    selected_emails: set[str],
    step: PipelineStep,
    cache_key: str,
    send_enabled: bool,
) -> None:
    _inject_urgent_css()
    st.subheader("Conversation Unibox")
    if not queue:
        st.caption("Aucun lead dans cette étape.")
        return

    def _lead_option_label(row) -> str:
        prefix = "🔴 " if row.awaiting_reply_over_24h else ""
        name = f"{row.first_name} — {row.email}" if row.first_name else row.email
        return f"{prefix}{name}"

    email_options = [row.email for row in queue]
    default_email = email_options[0]
    if len(selected_emails) == 1:
        default_email = next(iter(selected_emails))

    default_index = email_options.index(default_email) if default_email in email_options else 0
    conv_email = st.selectbox(
        "Lead",
        options=email_options,
        index=default_index,
        format_func=lambda e: next(
            (_lead_option_label(r) for r in queue if r.email == e),
            e,
        ),
        key=f"conv_lead_{step}_{campaign_id}",
    )

    lead_row = next((r for r in queue if r.email == conv_email), None)
    if not lead_row:
        return

    if lead_row.awaiting_reply_over_24h:
        st.markdown(
            '<p class="subseq-urgent">Dernière réponse prospect il y a 24h+ — réponse Hercule en attente.</p>',
            unsafe_allow_html=True,
        )

    load_key = f"thread_{campaign_id}_{conv_email}"
    loaded_for_key = f"thread_loaded_for_{campaign_id}_{step}"

    reload_col, _ = st.columns([1, 3])
    with reload_col:
        force_reload = st.button("Recharger", key=f"reload_conv_{step}_{conv_email}")

    should_load = force_reload or st.session_state.get(loaded_for_key) != conv_email
    if should_load:
        try:
            with st.spinner("Chargement…"):
                client = InstantlyClient(require_instantly_api_key())
                messages = fetch_latest_reply(
                    client,
                    lead_email=conv_email,
                    campaign_id=campaign_id,
                    lead_first_name=lead_row.first_name,
                )
                st.session_state[load_key] = messages
                st.session_state[loaded_for_key] = conv_email
        except Exception as exc:
            st.error(str(exc))

    if load_key not in st.session_state:
        st.info("Chargement de la conversation…")
        return

    messages = st.session_state[load_key]
    interest_status = lead_row.raw.get("lt_interest_status")
    is_no_show = is_no_show_status(
        int(interest_status) if interest_status is not None else None
    )
    detected_flows = set(lead_row.sent_flows)
    derived_step = derive_step_from_flows(detected_flows, is_no_show=is_no_show)

    if messages:
        st.caption(f"**Sujet :** {thread_subject(messages)}")
    st.caption(
        f"**CRM :** {STEP_LABELS[lead_row.step]} · "
        f"**Détecté :** {STEP_LABELS.get(derived_step, derived_step)} "  # type: ignore[arg-type]
        f"({', '.join(sorted(detected_flows)) or '—'})"
    )

    if lead_row.step != derived_step and lead_row.step != "replies_to_handle":
        st.warning(
            f"Écart CRM vs Unibox : étape dashboard **{STEP_LABELS[lead_row.step]}**, "
            f"fingerprints → **{STEP_LABELS.get(derived_step, derived_step)}**."  # type: ignore[arg-type]
        )

    if messages:
        st.markdown(render_conversation_html(messages), unsafe_allow_html=True)
    else:
        st.info("Aucune réponse reçue pour ce lead.")

    st.divider()
    st.subheader("Répondre")

    suggested_flow = suggest_flow_for_lead(lead_row)
    if suggested_flow is None:
        st.caption("Aucun email séquence suggéré pour ce lead — déplacez-le vers une autre étape.")
        return

    flow_labels = [FLOW_LABELS[f] for f in SENDABLE_FLOWS]
    default_flow_index = SENDABLE_FLOWS.index(suggested_flow)
    chosen_flow_label = st.selectbox(
        "Email à envoyer",
        options=flow_labels,
        index=default_flow_index,
        key=f"conv_flow_{campaign_id}_{step}_{conv_email}",
    )
    conv_flow: Flow = SENDABLE_FLOWS[flow_labels.index(chosen_flow_label)]

    body_state_key = f"conv_body_{campaign_id}_{conv_email}_{conv_flow}"
    template_seed_key = f"conv_body_seed_{campaign_id}_{conv_email}_{conv_flow}"
    if template_seed_key not in st.session_state:
        try:
            st.session_state[body_state_key] = render_template_html(
                conv_flow,
                lead_row.raw,
                campaign_id=campaign_id,
            )
            st.session_state[template_seed_key] = True
        except Exception as exc:
            st.error(f"Impossible de charger le template : {exc}")
            return

    body_html = st.text_area(
        "Corps HTML (éditable)",
        height=180,
        key=body_state_key,
    )

    with st.expander("Aperçu rendu", expanded=False):
        st.markdown(body_html or "", unsafe_allow_html=True)

    dry_conv = st.checkbox(
        "Mode test (dry run)",
        value=True,
        key=f"dry_conv_{campaign_id}_{step}",
        help="Aucun email Instantly ni event Supabase en mode test.",
    )

    send_disabled = not send_enabled or not str(body_html or "").strip()
    if st.button(
        "Envoyer la réponse",
        key=f"send_conv_{campaign_id}_{step}_{conv_email}",
        disabled=send_disabled,
    ):
        try:
            client = InstantlyClient(require_instantly_api_key())
            result = dispatch_conversation_reply(
                client,
                flow=conv_flow,
                campaign_id=campaign_id,
                lead=lead_row.raw,
                body_html=body_html,
                dry_run=dry_conv,
            )
        except Exception as exc:
            st.error(str(exc))
            return

        if result.get("skipped"):
            st.warning(f"Déjà traité : {result.get('skipped')}")
        elif dry_run:
            if result.get("would_send_now"):
                st.info("Mode test : envoi **immédiat** si vous décochez le dry run.")
            elif result.get("would_schedule"):
                slot = result.get("scheduled_label") or format_paris_slot(next_send_slot())
                st.info(f"Mode test : programmé pour **{slot}**.")
        elif result.get("scheduled"):
            slot = result.get("scheduled_label") or format_paris_slot(next_send_slot())
            st.toast(f"Réponse programmée pour {slot}", icon="🕐")
            st.success(f"Réponse programmée pour **{slot}**.")
            st.session_state.pop(cache_key, None)
            st.session_state.pop(load_key, None)
            st.session_state.pop(loaded_for_key, None)
        elif result.get("ok"):
            st.toast("Réponse envoyée", icon="✅")
            st.success("Réponse envoyée via Unibox.")
            st.session_state.pop(cache_key, None)
            st.session_state.pop(load_key, None)
            st.session_state.pop(loaded_for_key, None)
            for key in list(st.session_state.keys()):
                if str(key).startswith(f"conv_body_{campaign_id}_{conv_email}_"):
                    st.session_state.pop(key, None)
                if str(key).startswith(f"conv_body_seed_{campaign_id}_{conv_email}_"):
                    st.session_state.pop(key, None)
        else:
            st.error(result.get("error", "Échec d'envoi"))


def _render_pipeline_panel(campaign_id: str, *, send_enabled: bool = True) -> None:
    _inject_urgent_css()
    window_open = is_within_send_window()
    next_slot = next_send_slot()
    next_slot_label = format_paris_slot(next_slot)
    if window_open:
        st.success("Fenêtre d'envoi : lun–ven, 8h–17h (Paris) — **Ouverte**")
    else:
        st.warning(
            "Fenêtre d'envoi : lun–ven, 8h–17h (Paris) — **Fermée**  \n"
            f"Prochain créneau : **{next_slot_label}**"
        )

    if not send_enabled:
        st.warning("Remplissez l'email 1 dans Setup ou Templates avant d'envoyer.")

    cache_key = f"pipeline_{campaign_id}"
    all_queue_cached = st.session_state.get(cache_key)

    step = st.radio(
        "Étape CRM",
        options=PIPELINE_STEPS,
        format_func=lambda s: _step_radio_label(s, all_queue_cached),
        horizontal=True,
        key="envois_step",
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        max_leads = st.number_input(
            "Max leads Instantly",
            min_value=1,
            max_value=500,
            value=100,
            key="max_pipeline",
        )
    with col2:
        dry_run = st.checkbox(
            "Mode test (dry run)",
            value=True,
            key="dry_pipeline",
            help=(
                "En mode test : le bouton Envoyer affiche uniquement combien de leads "
                "seraient traités — aucun email Instantly, aucun event Supabase, "
                "aucun changement d'étape. Décochez pour l'envoi réel."
            ),
        )
    with col3:
        default_flow = DEFAULT_FLOW_BY_STEP[step]
        if default_flow:
            flow_labels = [FLOW_LABELS[f] for f in SENDABLE_FLOWS]
            default_index = SENDABLE_FLOWS.index(default_flow)
            chosen_flow_label = st.selectbox(
                "Email to send",
                options=flow_labels,
                index=default_index,
                key="flow_pipeline",
            )
            flow: Flow | None = SENDABLE_FLOWS[flow_labels.index(chosen_flow_label)]
        else:
            st.caption("Pas d'envoi auto depuis cette étape — déplacez le lead d'abord.")
            flow = None
    with col4:
        refresh = st.button("Fetch Interested + sync CRM", key="fetch_pipeline")

    if dry_run:
        st.caption(
            "Mode test actif — le bouton Envoyer n'enverra rien. "
            "Utilisez Aperçu email pour lire le contenu."
        )

    show_preview = st.checkbox("Aperçu email", value=False, key="preview_pipeline")
    if show_preview and flow:
        preview_lead = None
        cache_key = f"pipeline_{campaign_id}"
        cached_queue = st.session_state.get(cache_key)
        if cached_queue:
            preview_options = ["Variables par défaut"] + [row.email for row in cached_queue]
            preview_choice = st.selectbox(
                "Aperçu avec le lead",
                options=preview_options,
                key="preview_lead_pipeline",
            )
            if preview_choice != "Variables par défaut":
                match = next((row for row in cached_queue if row.email == preview_choice), None)
                if match:
                    preview_lead = match.raw
        try:
            html = render_template_html(flow, preview_lead, campaign_id=campaign_id)
            with st.expander(f"Aperçu — {FLOW_LABELS[flow]}", expanded=True):
                st.markdown(html, unsafe_allow_html=True)
        except Exception as exc:
            st.error(f"Impossible de charger l'aperçu : {exc}")

    cache_key = f"pipeline_{campaign_id}"
    fetch_meta_key = "fetch_meta_pipeline"
    editor_key = f"editor_pipeline_{campaign_id}_{step}"
    current_meta = (campaign_id, int(max_leads))

    if st.session_state.get(fetch_meta_key) != current_meta:
        st.session_state.pop(cache_key, None)
        st.session_state[fetch_meta_key] = current_meta

    if refresh:
        progress_bar = st.progress(0.0)
        status_text = st.empty()
        try:
            client = InstantlyClient(require_instantly_api_key())

            def on_progress(current: int, total: int, message: str) -> None:
                progress_bar.progress(min(current / max(total, 1), 1.0))
                status_text.caption(message)

            st.session_state[cache_key] = fetch_pipeline_leads(
                campaign_id=campaign_id,
                max_leads=int(max_leads),
                client=client,
                on_progress=on_progress,
            )
            for key in list(st.session_state.keys()):
                if str(key).startswith(f"editor_pipeline_{campaign_id}_"):
                    st.session_state.pop(key, None)
            progress_bar.empty()
            status_text.empty()
        except Exception as exc:
            progress_bar.empty()
            status_text.empty()
            st.error(str(exc))
            return

    all_queue = st.session_state.get(cache_key)
    if all_queue is None:
        st.info("Cliquez sur **Fetch Interested + sync CRM** pour charger les leads.")
        return

    queue = leads_for_step(all_queue, step)
    counts = {s: len(leads_for_step(all_queue, s)) for s in PIPELINE_STEPS}
    st.caption(
        " · ".join(f"{STEP_LABELS[s].split(' — ')[0]}: {counts[s]}" for s in PIPELINE_STEPS)
    )
    st.caption(f"{len(queue)} lead(s) dans **{STEP_LABELS[step]}**")

    if not queue:
        st.warning("Aucun lead dans cette étape.")
        return

    urgent_leads = [row for row in queue if row.awaiting_reply_over_24h]
    if step == "replies_to_handle" and urgent_leads:
        urgent_items = ", ".join(
            f"{row.first_name or row.email} ({row.email})" for row in urgent_leads
        )
        st.markdown(
            f'<p class="subseq-urgent"><strong>{len(urgent_leads)} lead(s) sans réponse depuis 24h+</strong>'
            f" — {urgent_items}</p>",
            unsafe_allow_html=True,
        )

    missing_links = sum(1 for row in queue if row.missing_reservation_link)
    if missing_links:
        st.warning(f"{missing_links} lead(s) missing `reservation_agence_link` — they will fail on send.")

    if editor_key not in st.session_state:
        st.session_state[editor_key] = _queue_to_dataframe(queue)

    left_col, right_col = st.columns([3, 2])

    with left_col:
        sel_col1, sel_col2, move_col, _ = st.columns([1, 1, 2, 1])
        with sel_col1:
            if st.button("Tout sélectionner", key=f"select_all_{step}"):
                df_all = st.session_state[editor_key].copy()
                df_all["Envoyer"] = True
                st.session_state[editor_key] = df_all
                st.rerun()
        with sel_col2:
            if st.button("Tout désélectionner", key=f"deselect_all_{step}"):
                df_none = st.session_state[editor_key].copy()
                df_none["Envoyer"] = False
                st.session_state[editor_key] = df_none
                st.rerun()
        with move_col:
            target_step = st.selectbox(
                "Déplacer les cochés vers",
                options=["—"] + list(PIPELINE_STEPS),
                format_func=lambda s: "—" if s == "—" else STEP_LABELS[s],
                key=f"move_target_{step}",
            )

        edited = st.data_editor(
            st.session_state[editor_key],
            column_config={
                "Envoyer": st.column_config.CheckboxColumn("Envoyer", default=True),
            },
            disabled=[
                "Alerte",
                "Email",
                "Prénom",
                "Statut",
                "Étape",
                "Répondu depuis envoi Hercule",
                "Dernière réponse prospect",
                "Lien OK",
                "Emails déjà envoyés",
                "Dernier envoi Hercule",
            ],
            hide_index=True,
            use_container_width=True,
            key=f"data_editor_{step}_{campaign_id}",
        )
        st.session_state[editor_key] = edited

        selected_emails = {
            str(row["Email"]).strip().lower()
            for _, row in edited.iterrows()
            if row["Envoyer"]
        }
        selected_count = len(selected_emails)
        if flow:
            st.write(f"**{selected_count}** lead(s) selected → **{FLOW_LABELS[flow]}**")
            if selected_count > 0:
                if window_open:
                    st.caption(f"{selected_count} lead(s) → envoi **immédiat**")
                else:
                    st.caption(
                        f"{selected_count} lead(s) → programmés pour **{next_slot_label}**"
                    )
        else:
            st.write(f"**{selected_count}** lead(s) selected")

        if st.button("Déplacer les leads cochés", key=f"move_{step}"):
            if target_step == "—" or not selected_emails:
                st.warning("Cochez des leads et choisissez une étape cible.")
            else:
                move_pipeline_leads(campaign_id, list(selected_emails), target_step)
                for row in all_queue:
                    if row.email in selected_emails:
                        row.step = target_step
                st.session_state[cache_key] = all_queue
                st.success(f"{selected_count} lead(s) déplacé(s) vers {STEP_LABELS[target_step]}.")
                st.rerun()

        send_clicked = st.button(
            "Envoyer aux leads cochés",
            key=f"send_{step}",
            disabled=not send_enabled or not flow,
        )
        if flow and send_clicked:
            selected_leads = [row.raw for row in queue if row.email in selected_emails]

            if dry_run:
                preview = dispatch_bulk(
                    campaign_id=campaign_id,
                    flow=flow,
                    leads=selected_leads,
                    dry_run=True,
                )
                if window_open:
                    st.info(
                        f"Mode test : **{preview.sent}** lead(s) seraient envoyés "
                        f"**maintenant**, **{preview.scheduled}** programmé(s), "
                        f"**{preview.skipped}** ignoré(s)."
                    )
                else:
                    slot_text = preview.scheduled_slot_label or next_slot_label
                    st.info(
                        f"Mode test : **{preview.scheduled}** lead(s) seraient "
                        f"programmés pour **{slot_text}**, "
                        f"**{preview.skipped}** ignoré(s)."
                    )
            else:
                log_box = st.empty()
                logs: list[str] = []
                progress = st.progress(0.0)

                def on_progress(email: str) -> None:
                    logs.append(email)
                    log_box.text("\n".join(logs[-12:]))
                    progress.progress(min(len(logs) / max(len(selected_leads), 1), 1.0))

                with st.spinner("Sending…"):
                    result = dispatch_bulk(
                        campaign_id=campaign_id,
                        flow=flow,
                        leads=selected_leads,
                        dry_run=False,
                        on_progress=on_progress,
                    )

                if result.sent > 0:
                    st.toast(f"{result.sent} email(s) envoyé(s) maintenant", icon="✅")
                if result.scheduled > 0:
                    slot_text = result.scheduled_slot_label or next_slot_label
                    st.toast(
                        f"{result.scheduled} email(s) programmé(s) pour {slot_text}",
                        icon="🕐",
                    )

                st.session_state.pop(cache_key, None)
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Envoyés", result.sent)
                m2.metric("Programmés", result.scheduled)
                m3.metric("Ignorés", result.skipped)
                m4.metric("Échecs", result.failed)
                if result.errors:
                    st.error("\n".join(result.errors[:10]))

    with right_col:
        _render_conversation_panel(
            campaign_id=campaign_id,
            queue=queue,
            selected_emails=selected_emails,
            step=step,
            cache_key=cache_key,
            send_enabled=send_enabled,
        )


try:
    api_key = require_instantly_api_key()
    instantly_client = InstantlyClient(api_key)
    campaigns = list_all_campaigns()
except ValueError as exc:
    st.error(str(exc))
    st.stop()

campaign_options = {
    format_resource_label(c.get("name"), str(c.get("id") or "")): str(c.get("id") or "")
    for c in campaigns
    if c.get("id")
}

if not campaign_options:
    st.warning("No Instantly campaigns found.")
    st.stop()

default_campaign = env("INSTANTLY_BYPASS_CAMPAIGN_ID")
default_label = next(
    (label for label, cid in campaign_options.items() if cid == default_campaign),
    next(iter(campaign_options.keys()), ""),
)
selected_label = st.selectbox(
    "Campagne Instantly",
    options=list(campaign_options.keys()),
    index=list(campaign_options.keys()).index(default_label)
    if default_label in campaign_options
    else 0,
    key="global_campaign",
)
selected_campaign_id = campaign_options[selected_label]
selected_campaign_name = selected_label.split(" (")[0]
selected_config = get_config(selected_campaign_id)
templates = list_templates(selected_campaign_id)
public_url = webhook_public_url()
webhooks = instantly_client.list_webhooks()
matched_webhook = find_campaign_webhook(
    webhooks,
    campaign_id=selected_campaign_id,
    target_url=public_url,
)
existing_webhook = find_campaign_webhook(
    webhooks,
    campaign_id=selected_campaign_id,
    target_url=public_url,
    require_active=False,
)
inactive_webhook = (
    existing_webhook
    if existing_webhook and not is_webhook_active(existing_webhook)
    else None
)
if matched_webhook and selected_config:
    live_webhook_id = str(matched_webhook.get("id") or "")
    stored_webhook_id = str(selected_config.get("webhook_id") or "")
    if live_webhook_id and live_webhook_id != stored_webhook_id:
        sync_webhook_id(selected_campaign_id, live_webhook_id)
        selected_config = get_config(selected_campaign_id)
onboarding_status = derive_onboarding_status(
    has_config=selected_config is not None,
    has_webhook=matched_webhook is not None,
    copy_complete=copy_is_complete(templates),
)
webhook_miss_reason = (
    explain_webhook_miss(
        webhooks,
        campaign_id=selected_campaign_id,
        target_url=public_url,
    )
    if onboarding_status == "webhook_incomplete"
    else None
)
url_error = webhook_url_error()

status_col, action_col = st.columns([3, 1])
with status_col:
    if onboarding_status == "ready":
        st.success(f"Statut : **{STATUS_LABELS[onboarding_status]}**")
    elif onboarding_status == "copy_incomplete":
        st.info(f"Statut : **{STATUS_LABELS[onboarding_status]}** — remplissez Email 1, 2 et 3.")
    else:
        st.warning(f"Statut : **{STATUS_LABELS[onboarding_status]}**")
    if webhook_miss_reason:
        st.caption(webhook_miss_reason)

if url_error:
    st.error(url_error)

global_webhook_on = webhook_auto_send_enabled()
if not global_webhook_on:
    st.error(
        "Kill-switch global webhook : **en pause** (`instantly_bypass_settings`). "
        "Aucun E1 auto ne part, quelle que soit la campagne."
    )

with action_col:
    can_init = (
        onboarding_status in {"not_initialized", "webhook_incomplete"}
        and is_valid_webhook_target_url(public_url)
    )
    init_label = "Réactiver le webhook" if inactive_webhook else "Initialiser"
    if st.button(init_label, disabled=not can_init, key="init_campaign"):
        try:
            initialize_campaign(
                instantly_client,
                campaign_id=selected_campaign_id,
                campaign_name=selected_campaign_name,
                target_url=public_url,
                secret=webhook_secret(),
            )
            if inactive_webhook:
                st.success("Webhook Instantly réactivé (headers + resume).")
            else:
                st.success("Campagne initialisée (config, templates, webhook).")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

TAB_WORKFLOW, TAB_SETUP, TAB_TEMPLATES, TAB_ENVOIS, TAB_ANALYTICS = st.tabs(
    ["Workflow", "Setup", "Templates", "Envois", "Analytics"]
)

with TAB_WORKFLOW:
    st.subheader("CRM pipeline")
    campaign_webhook_on = bool(
        selected_config and selected_config.get("webhook_auto_send_enabled", True)
    )
    if onboarding_status == "webhook_incomplete":
        if inactive_webhook:
            error_at = str(inactive_webhook.get("timestamp_error") or "").strip()
            since = f" (coupé le {error_at})" if error_at else ""
            st.error(
                f"Webhook Instantly inactif{since} — aucun E1 auto ne partira. "
                "Cliquez **Réactiver le webhook**."
            )
        else:
            st.error(
                "Webhook Instantly manquant — aucun E1 auto ne partira. "
                "Cliquez **Initialiser** (après correction de l'URL si nécessaire)."
            )
    elif not global_webhook_on:
        st.warning("Kill-switch global en pause — voir le bandeau en haut de page.")
    elif not campaign_webhook_on:
        st.warning("Webhook auto-send (cette campagne) : **En pause**. Activez-le dans Setup.")
    elif onboarding_status == "ready":
        st.success("Webhook auto-send (cette campagne) : **Actif**")
    elif selected_config:
        st.info(
            "Webhook auto-send activé en config, mais la campagne n'est pas encore prête "
            "(copy ou webhook incomplet)."
        )
    st.markdown(
        """
1. **Étape 0** — lead Interested, pas encore d'email de suivi Hercule. Webhook `lead_interested` + envoi E1 (ou envoi manuel).
2. **Étape 1** — E1 précisions envoyé. Prochain envoi : E2 confirmation.
3. **Étape 2** — E2 envoyé. Prochain envoi : E3 clôture → Instantly **Not Interested (-1)**.
4. **Étape 3** — séquence terminée.
5. **Réponses à traiter** — le lead a répondu en étape 1, 2 ou 3 (détection Unibox au Fetch). Déplacement manuel possible.
6. Le tag Instantly **Interested** ne change qu'à l'envoi de E3. L'étape CRM est la seule source de vérité.
        """
    )
    st.info(f"Production webhook URL: `{public_url}`")

with TAB_SETUP:
    st.subheader("Onboarding")
    if onboarding_status == "not_initialized":
        st.markdown(
            "Cette campagne Instantly n’a pas encore de config Hercule. "
            "**Initialiser** crée la ligne config, des templates E1–E3 vides, "
            "et enregistre le webhook `lead_interested`."
        )
    elif onboarding_status == "copy_incomplete":
        st.markdown("Config présente — remplissez Email 1, 2 et 3 ci-dessous.")
    elif onboarding_status == "webhook_incomplete":
        if inactive_webhook:
            st.markdown(
                "Config présente mais le webhook Instantly est **inactif** "
                "(échecs de livraison). Cliquez **Réactiver le webhook**."
            )
        else:
            st.markdown(
                "Config présente mais webhook Instantly manquant — cliquez **Initialiser**."
            )
        if webhook_miss_reason:
            st.warning(webhook_miss_reason)
    else:
        st.markdown("Campagne prête. Vous pouvez encore éditer le copy ou mettre le webhook en pause.")

    if selected_config:
        st.divider()
        st.subheader("Webhook auto-send (cette campagne)")
        campaign_enabled = bool(selected_config.get("webhook_auto_send_enabled", True))
        if onboarding_status == "webhook_incomplete":
            if inactive_webhook:
                st.error(
                    "Auto-send configuré, mais webhook Instantly inactif — E1 auto impossible."
                )
            else:
                st.error(
                    "Auto-send configuré, mais webhook Instantly absent — E1 auto impossible."
                )
        elif campaign_enabled:
            st.success("Auto-send webhook: **Actif**")
        else:
            st.warning("Auto-send webhook: **En pause**")
        toggle_col1, toggle_col2 = st.columns(2)
        with toggle_col1:
            if st.button(
                "Activer le webhook auto-send",
                disabled=campaign_enabled,
                key="webhook_enable",
            ):
                set_campaign_webhook_auto_send_enabled(selected_campaign_id, True)
                st.rerun()
        with toggle_col2:
            if st.button(
                "Mettre en pause",
                disabled=not campaign_enabled,
                key="webhook_pause",
            ):
                set_campaign_webhook_auto_send_enabled(selected_campaign_id, False)
                st.rerun()
        st.caption(
            "Ce réglage est **par campagne**. Le kill-switch global reste dans "
            "`instantly_bypass_settings` (pause d’urgence toutes campagnes)."
        )

        st.subheader("Pipeline auto-advance (cette campagne)")
        pipeline_enabled = bool(
            selected_config.get("pipeline_auto_advance_enabled", True)
        )
        if pipeline_enabled:
            st.success("Auto-advance cron: **Actif** (E2 +24h, E3 +48h, clôture +48h)")
        else:
            st.warning("Auto-advance cron: **En pause**")
        pipeline_col1, pipeline_col2 = st.columns(2)
        with pipeline_col1:
            if st.button(
                "Activer l'auto-advance",
                disabled=pipeline_enabled,
                key="pipeline_enable",
            ):
                set_campaign_pipeline_auto_advance_enabled(selected_campaign_id, True)
                st.rerun()
        with pipeline_col2:
            if st.button(
                "Mettre en pause",
                disabled=not pipeline_enabled,
                key="pipeline_pause",
            ):
                set_campaign_pipeline_auto_advance_enabled(selected_campaign_id, False)
                st.rerun()
        st.caption(
            "Cron `/api/cron/instantly-bypass-pipeline` toutes les 15 min "
            "(cron-job.org). Respecte la fenêtre d'envoi 8h–17h pour E2/E3."
        )

        st.code(public_url)
        if url_error:
            st.error(url_error)

        st.divider()
        st.subheader("Séquences emails")
        _render_sequence_form(selected_campaign_id, templates, key_prefix="setup")

    st.divider()
    st.subheader("Webhooks Instantly")
    if webhooks:
        st.dataframe(
            [
                {
                    "id": w.get("id"),
                    "name": w.get("name"),
                    "event_type": w.get("event_type"),
                    "campaign": w.get("campaign") or w.get("campaign_id"),
                    "url": w.get("target_hook_url"),
                    "status": w.get("status"),
                    "timestamp_error": w.get("timestamp_error"),
                }
                for w in webhooks
            ],
            use_container_width=True,
        )
    else:
        st.caption("No webhooks registered.")

    to_delete = st.selectbox(
        "Delete webhook",
        options=["—"] + [str(w.get("id")) for w in webhooks if w.get("id")],
    )
    if st.button("Delete selected webhook", disabled=to_delete == "—"):
        instantly_client.delete_webhook(to_delete)
        st.success("Webhook deleted.")
        st.rerun()

with TAB_TEMPLATES:
    st.subheader("Email templates")
    if not selected_config:
        st.warning("Initialisez la campagne dans Setup avant d’éditer les templates.")
    else:
        tab_edit, tab_history = st.tabs(["Édition", "Historique"])
        with tab_edit:
            _render_sequence_form(selected_campaign_id, templates, key_prefix="templates")
        with tab_history:
            render_subsequence_history_tab(
                selected_campaign_id,
                templates,
                key_prefix="templates",
            )

with TAB_ENVOIS:
    st.subheader("Envois")
    if not selected_config:
        st.warning("Initialisez cette campagne (bouton **Initialiser**) avant d’ouvrir le CRM.")
    else:
        _render_pipeline_panel(
            selected_campaign_id,
            send_enabled=e1_copy_is_ready(templates),
        )

with TAB_ANALYTICS:
    st.subheader("Live analytics")
    try:
        stats = fetch_analytics(selected_campaign_id)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    c1, c2, c3 = st.columns(3)
    c1.metric("Instant emails sent", stats["total_sent"])
    c2.metric(
        "Avg latency (ms)",
        stats["avg_latency_ms"] if stats["avg_latency_ms"] is not None else "—",
    )
    c3.metric("Failed events", stats["failed_count"])

    if stats["recent_errors"]:
        st.subheader("Recent errors")
        st.dataframe(stats["recent_errors"], use_container_width=True)
    else:
        st.caption("No failed events for this campaign.")
