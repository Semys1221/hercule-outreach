"""AI Reply Agent — Streamlit control panel."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st

_APP_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _APP_DIR.parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from shared.instantly_client import InstantlyClient, format_resource_label, list_all_campaigns

from agent_preview import generate_reply_preview
from config import (
    grok_api_key_status,
    prompts_dir,
    require_instantly_api_key,
    webhook_public_url,
    webhook_secret,
    webhook_url_error,
)
from grok_usage_ui import render_grok_usage_badge
from inbox import dispatch_manual_reply
from pending_table_state import invalidate_all_editors, is_reply_mode_enabled, set_reply_mode_enabled
from pending_table_ui import render_pending_table
from pending_reply_mode import render_reply_mode_view
from lead_tags import TAG_FILTER_ORDER, TAG_LABELS, build_interest_index, count_by_tag
from pending_fetch import (
    PendingReplyRow,
    dedupe_pending_rows_by_email,
    enrich_pending_rows,
    fetch_pending_emails,
    filter_rows_by_tag,
)
from pending_table_state import clear_inbound_body_cache
from onboarding import (
    STATUS_LABELS,
    activate_campaign,
    derive_onboarding_status,
    initiate_webhooks,
    merge_webhook_config,
    validate_campaign_readiness,
)
from presets import list_preset_options, load_niche_metadata, preset_label, resolve_preset_for_campaign
from editor_history import (
    record_prompt_save,
    render_reply_history_note,
    render_reply_prompt_history_tab,
)
from supabase_repo import (
    get_config,
    get_global_auto_send_enabled,
    list_inbound_messages,
    list_problem_messages,
    list_thread_messages,
    save_config,
    set_global_auto_send_enabled,
)
from unibox_thread import fetch_thread_messages, render_conversation_html

st.set_page_config(page_title="AI Reply Agent", layout="wide")
st.title("AI Reply Agent")

TARGET_TOOLTIP = (
    "Buyer = agencies applying for leads. "
    "Seller = enterprises looking for an agency."
)


@st.cache_data(ttl=300)
def _load_campaigns(_api_key: str) -> list[dict]:
    return list_all_campaigns()


def _thread_cache_key(
    campaign_id: str,
    lead_email: str,
    thread_id: str | None = None,
) -> str:
    key = f"thread_{campaign_id}_{lead_email.lower()}"
    if thread_id:
        return f"{key}_{thread_id}"
    return key


def get_cached_thread_messages(
    client: InstantlyClient,
    *,
    campaign_id: str,
    lead_email: str,
    thread_id: str | None = None,
) -> list[dict]:
    cache_key = _thread_cache_key(campaign_id, lead_email, thread_id)
    if cache_key not in st.session_state:
        st.session_state[cache_key] = fetch_thread_messages(
            client,
            lead_email=lead_email,
            campaign_id=campaign_id,
            thread_id=thread_id or None,
        )
    return st.session_state[cache_key]


def invalidate_thread_cache(
    campaign_id: str,
    lead_email: str,
    thread_id: str | None = None,
) -> None:
    st.session_state.pop(
        _thread_cache_key(campaign_id, lead_email, thread_id),
        None,
    )


_INTEREST_INDEX_TTL_S = 300


def _interest_index_keys(campaign_id: str) -> tuple[str, str]:
    return (
        f"interest_index_{campaign_id}",
        f"interest_index_ts_{campaign_id}",
    )


def invalidate_interest_index(campaign_id: str) -> None:
    data_key, ts_key = _interest_index_keys(campaign_id)
    st.session_state.pop(data_key, None)
    st.session_state.pop(ts_key, None)


def get_cached_interest_index(
    client: InstantlyClient,
    campaign_id: str,
    *,
    force_refresh: bool = False,
) -> dict[str, int | None]:
    data_key, ts_key = _interest_index_keys(campaign_id)
    if not force_refresh and data_key in st.session_state:
        cached_at = float(st.session_state.get(ts_key, 0))
        if time.time() - cached_at < _INTEREST_INDEX_TTL_S:
            return st.session_state[data_key]

    index = build_interest_index(client, campaign_id)
    st.session_state[data_key] = index
    st.session_state[ts_key] = time.time()
    return index


def prompt_path(preset_id: str, target_type: str) -> str:
    return str(prompts_dir() / f"{preset_id}_{target_type}.md")


def load_prompt_text(preset_id: str, target_type: str) -> str:
    path = Path(prompt_path(preset_id, target_type))
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _prompt_editor_key(campaign_id: str, preset_id: str, target_type: str) -> str:
    return f"prompt_editor_{campaign_id}_{preset_id}_{target_type}"


def _show_prompt_save_result(result: dict) -> None:
    st.success("Prompt enregistré (fichier prompts/).")
    if result.get("prod"):
        st.caption("Snapshot prod mis à jour — les réponses IA utilisent ce prompt.")
    else:
        reason = result.get("reason")
        if reason == "not_active":
            st.caption(
                "Prod inchangée — utilisez **Envoyer en prod** pour la première activation."
            )
        elif reason == "prompt_key_mismatch":
            st.caption(
                "Prod inchangée — niche/target ne correspond pas à la config campagne."
            )
        elif reason:
            st.caption(f"Prod inchangée ({reason}).")


def _initial_prompt_text(
    *,
    config: dict | None,
    niche_preset_id: str,
    target_type: str,
    prefer_prod_snapshot: bool,
) -> str:
    if prefer_prod_snapshot and config:
        snapshot = str(config.get("prompt_snapshot") or "").strip()
        if snapshot:
            return snapshot
    return load_prompt_text(niche_preset_id, target_type)


def render_prompt_editor(
    *,
    campaign_id: str,
    config: dict | None,
    niche_preset_id: str,
    target_type: str,
    prefer_prod_snapshot: bool = False,
    key_suffix: str = "",
) -> str:
    editor_key = _prompt_editor_key(campaign_id, niche_preset_id, target_type)
    if key_suffix:
        editor_key = f"{editor_key}_{key_suffix}"

    initial_text = _initial_prompt_text(
        config=config,
        niche_preset_id=niche_preset_id,
        target_type=target_type,
        prefer_prod_snapshot=prefer_prod_snapshot,
    )
    if editor_key not in st.session_state:
        st.session_state[editor_key] = initial_text

    file_text = load_prompt_text(niche_preset_id, target_type)
    if not file_text.strip() and not str(st.session_state.get(editor_key) or "").strip():
        st.warning(
            f"Prompt fichier absent ou vide : `{prompt_path(niche_preset_id, target_type)}`. "
            "Vous pouvez écrire ci-dessous et enregistrer."
        )

    render_reply_history_note("prompt")

    st.markdown("#### Prompt")
    prompt_text = st.text_area(
        "Corps du prompt",
        height=400,
        key=editor_key,
    )

    reload_prod_col, reload_file_col, save_col, _ = st.columns([1, 1, 1, 1])
    with reload_prod_col:
        if st.button(
            "Recharger depuis prod",
            key=f"reload_prod_prompt_{campaign_id}{key_suffix}",
            disabled=not config or not config.get("prompt_snapshot"),
        ):
            st.session_state[editor_key] = str(config.get("prompt_snapshot") or "")
            st.rerun()
    with reload_file_col:
        if st.button(
            "Recharger depuis le fichier",
            key=f"reload_file_prompt_{campaign_id}{key_suffix}",
        ):
            st.session_state[editor_key] = load_prompt_text(niche_preset_id, target_type)
            st.rerun()
    with save_col:
        if st.button("Enregistrer", key=f"save_prompt_{campaign_id}{key_suffix}"):
            try:
                result = record_prompt_save(
                    preset_id=niche_preset_id,
                    target_type=target_type,
                    text=prompt_text,
                    campaign_id=campaign_id,
                    config=config,
                    key_prefix="prompt",
                )
                _show_prompt_save_result(result)
                if config and result.get("prod"):
                    config["prompt_snapshot"] = prompt_text
            except Exception as exc:
                st.error(str(exc))

    return prompt_text


def render_active_prompt_tab(
    *,
    campaign_id: str,
    config: dict | None,
) -> None:
    if not config:
        st.warning("Aucune config campagne — complétez l'onboarding d'abord.")
        return

    niche_preset_id = str(config.get("niche_preset_id") or "")
    target_type = str(config.get("target_type") or "buyer")
    prompt_key = str(config.get("prompt_key") or f"{niche_preset_id}_{target_type}")

    st.caption(
        f"Niche: **{preset_label(niche_preset_id)}** · Target: **{target_type}** · "
        f"Clé: `{prompt_key}`"
    )
    st.caption(
        "Le snapshot prod (`prompt_snapshot`) est la source utilisée par le webhook et **Try agent**."
    )

    tab_edit, tab_history = st.tabs(["Édition", "Historique"])
    with tab_edit:
        prompt_text = render_prompt_editor(
            campaign_id=campaign_id,
            config=config,
            niche_preset_id=niche_preset_id,
            target_type=target_type,
            prefer_prod_snapshot=True,
            key_suffix="_active",
        )
    with tab_history:
        editor_key = _prompt_editor_key(campaign_id, niche_preset_id, target_type) + "_active"
        render_reply_prompt_history_tab(
            campaign_id=campaign_id,
            niche_preset_id=niche_preset_id,
            target_type=target_type,
            config=config,
            load_prompt_text=load_prompt_text,
            editor_key=editor_key,
        )

    st.divider()
    st.markdown("#### Test rapide")
    grok_ok, grok_hint = grok_api_key_status()
    if not grok_ok:
        st.error(grok_hint)
    sample_inbound = st.text_input(
        "Réponse prospect (test)",
        value="Bonjour, pouvez-vous m'en dire plus ?",
        key=f"prompt_try_inbound_{campaign_id}",
    )
    if st.button(
        "Try agent",
        key=f"prompt_try_agent_{campaign_id}",
        disabled=not grok_ok,
    ):
        if not prompt_text.strip():
            st.error("Le prompt ne peut pas être vide.")
        elif not config.get("prompt_snapshot") and not prompt_text.strip():
            st.error("Enregistrez d'abord le prompt pour mettre à jour le snapshot prod.")
        else:
            try:
                preview_config = dict(config)
                preview_config["prompt_snapshot"] = prompt_text
                preview = generate_reply_preview(
                    preview_config,
                    sample_inbound.strip() or "(empty body)",
                    "test@example.com",
                )
                if preview.get("should_reply") and preview.get("reply_text"):
                    st.success("Réponse générée (preview, non envoyée) :")
                    st.write(preview["reply_text"])
                    st.caption(f"Modèle: {preview.get('model', '—')}")
                else:
                    st.warning(preview.get("reason") or "L'IA a choisi de ne pas répondre.")
            except Exception as exc:
                st.error(str(exc))


def render_onboarding(
    *,
    instantly_client: InstantlyClient,
    campaign_id: str,
    campaign_name: str,
    config: dict | None,
    onboarding_status: str,
) -> None:
    st.subheader("Onboarding")
    st.info(STATUS_LABELS.get(onboarding_status, onboarding_status))

    preset_options = list_preset_options()
    preset_labels = list(preset_options.keys())
    expected_preset_id = resolve_preset_for_campaign(campaign_id)
    saved_preset_id = str((config or {}).get("niche_preset_id") or "")
    resolved_preset_id = expected_preset_id or saved_preset_id

    if expected_preset_id:
        st.text_input(
            "Niche config",
            value=preset_label(expected_preset_id),
            disabled=True,
            help="Niche verrouillée — cette campagne Instantly est liée à ce preset scraper.",
        )
        niche_preset_id = expected_preset_id
    else:
        niche_index = next(
            (
                i
                for i, label in enumerate(preset_labels)
                if preset_options[label] == resolved_preset_id
            ),
            0,
        )
        niche_label = st.selectbox(
            "Niche config",
            options=preset_labels,
            index=niche_index,
            key=f"niche_label_{campaign_id}",
        )
        niche_preset_id = preset_options[niche_label]

    st.caption(TARGET_TOOLTIP)
    target_options = ["buyer", "seller"]
    saved_target = str((config or {}).get("target_type") or "buyer")
    target_index = target_options.index(saved_target) if saved_target in target_options else 0
    target_type = st.radio(
        "Target type",
        options=target_options,
        index=target_index,
        format_func=lambda v: v.capitalize(),
        horizontal=True,
        key=f"target_type_{campaign_id}",
    )

    prompt_text = render_prompt_editor(
        campaign_id=campaign_id,
        config=config,
        niche_preset_id=niche_preset_id,
        target_type=target_type,
        prefer_prod_snapshot=False,
    )

    if not prompt_text.strip():
        st.error("Le prompt ne peut pas être vide pour activer la campagne.")
        return

    auto_validate_prompt = bool(
        config
        and (
            config.get("initialized_at")
            or (config.get("webhook_id") and config.get("ooo_webhook_id"))
        )
    )
    prompt_validated = st.checkbox(
        "Valider le prompt",
        value=auto_validate_prompt,
        key=f"prompt_validated_{campaign_id}",
    )

    public_url = webhook_public_url()
    url_error = webhook_url_error()
    if url_error:
        st.error(url_error)

    webhook_ready = bool(
        config
        and config.get("webhook_id")
        and config.get("ooo_webhook_id")
    )
    campaign_is_active = bool(
        config
        and validate_campaign_readiness(config, campaign_id).ready
    )

    if st.button(
        "Initier le webhook",
        disabled=not prompt_validated or bool(url_error) or campaign_is_active,
    ):
        try:
            secret = webhook_secret()
            reply_id, ooo_id = initiate_webhooks(
                instantly_client,
                campaign_id=campaign_id,
                campaign_name=campaign_name,
                target_url=public_url,
                secret=secret,
            )
            save_config(
                merge_webhook_config(
                    config,
                    {
                        "campaign_id": campaign_id,
                        "campaign_name": campaign_name,
                        "niche_preset_id": niche_preset_id,
                        "target_type": target_type,
                        "prompt_key": f"{niche_preset_id}_{target_type}",
                        "webhook_id": reply_id,
                        "ooo_webhook_id": ooo_id,
                    },
                )
            )
            st.success(
                "Webhooks `reply_received` et `lead_out_of_office` enregistrés."
            )
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    if webhook_ready or (config and config.get("webhook_id")):
        st.info(
            f"Webhook reply: `{config.get('webhook_id')}` · "
            f"OOO: `{config.get('ooo_webhook_id')}`"
        )

    if st.button(
        "Envoyer en prod",
        disabled=not prompt_validated or not webhook_ready,
    ):
        with st.spinner("Activation en cours…"):
            try:
                niche_metadata = load_niche_metadata(niche_preset_id)
                row = activate_campaign(
                    campaign_id=campaign_id,
                    campaign_name=campaign_name,
                    niche_preset_id=niche_preset_id,
                    niche_metadata=niche_metadata,
                    target_type=target_type,
                    prompt_key=f"{niche_preset_id}_{target_type}",
                    prompt_snapshot=prompt_text,
                    webhook_id=str(config.get("webhook_id") or ""),
                    ooo_webhook_id=str(config.get("ooo_webhook_id") or ""),
                )
                save_config(row)
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


def render_pending_unibox_tab(
    *,
    instantly_client: InstantlyClient,
    campaign_id: str,
    config: dict | None,
) -> None:
    cache_key = f"pending_replies_{campaign_id}"
    fetch_ok_key = f"pending_fetch_ok_{campaign_id}"
    max_leads_key = f"pending_max_leads_{campaign_id}"
    tag_filter_key = f"pending_tag_filter_{campaign_id}"
    tags_pending_key = f"tags_pending_{campaign_id}"

    auto_send_enabled = get_global_auto_send_enabled()
    pending_rows_cached = dedupe_pending_rows_by_email(st.session_state.get(cache_key, []))
    toolbar_col_fetch, toolbar_col_max, toolbar_col_auto, toolbar_col_mode = st.columns(
        [1.5, 1, 1.5, 1.2]
    )
    with toolbar_col_max:
        max_leads = st.number_input(
            "Max leads",
            min_value=10,
            max_value=500,
            value=int(st.session_state.get(max_leads_key, 200)),
            step=10,
            key=max_leads_key,
        )
    with toolbar_col_fetch:
        fetch_clicked = st.button("Fetch all pending", key=f"fetch_pending_{campaign_id}")
    with toolbar_col_auto:
        auto_enabled = st.toggle(
            "Envoi automatique (webhook)",
            value=auto_send_enabled,
            help=(
                "Activé : Grok répond et envoie immédiatement via Instantly. "
                "Désactivé : Grok rédige un brouillon ; envoi manuel depuis Pending ou Reply Mode."
            ),
            key=f"auto_send_toggle_{campaign_id}",
        )
        if auto_enabled != auto_send_enabled:
            set_global_auto_send_enabled(auto_enabled)
            st.rerun()
        if auto_enabled:
            st.caption("Auto actif")
        else:
            st.caption("Brouillon manuel")
    with toolbar_col_mode:
        if st.button(
            "Reply Mode",
            key=f"reply_mode_enter_{campaign_id}",
            disabled=not pending_rows_cached,
            help="Mode focus : messages complets et brouillons éditables.",
        ):
            set_reply_mode_enabled(campaign_id, True)
            st.rerun()

    if fetch_clicked:
        invalidate_interest_index(campaign_id)
        progress = st.progress(0.0)
        status = st.empty()

        def on_progress(page: int, max_pages: int, found: int, target: int) -> None:
            if max_pages > 0:
                progress.progress(min(page / max_pages, 1.0))
            status.caption(f"Page {page}/{max_pages} — {found}/{target} trouvés…")

        try:
            with st.spinner("Chargement Unibox…"):
                st.session_state[cache_key] = fetch_pending_emails(
                    instantly_client,
                    campaign_id,
                    max_leads=int(max_leads),
                    on_progress=on_progress,
                )
                st.session_state[fetch_ok_key] = True
                st.session_state[tags_pending_key] = True
                invalidate_all_editors(campaign_id)
                clear_inbound_body_cache(campaign_id)
            progress.empty()
            status.empty()
        except Exception as exc:
            st.session_state[fetch_ok_key] = False
            st.session_state.pop(tags_pending_key, None)
            progress.empty()
            status.empty()
            st.error(str(exc))

    if st.session_state.get(tags_pending_key) and cache_key in st.session_state:
        rows = dedupe_pending_rows_by_email(st.session_state.get(cache_key, []))
        index = get_cached_interest_index(instantly_client, campaign_id)
        st.session_state[cache_key] = enrich_pending_rows(
            instantly_client, index, campaign_id, rows
        )
        st.session_state[tags_pending_key] = False
        st.rerun()

    pending_rows = dedupe_pending_rows_by_email(st.session_state.get(cache_key, []))
    if st.session_state.get(fetch_ok_key) and cache_key in st.session_state:
        if not pending_rows:
            st.success("Aucun lead en attente de réponse.")
            return
        st.caption(f"{len(pending_rows)} lead(s) en attente de réponse.")

    if not pending_rows:
        st.info(
            "Cliquez **Fetch all pending** pour charger les réponses Unibox "
            "en attente de réponse (filtrables par tag Instantly)."
        )
        return

    tag_counts = count_by_tag(pending_rows)
    selected_tag = st.session_state.get(tag_filter_key, "all")
    filter_cols = st.columns(len(TAG_FILTER_ORDER))
    for col, tag_key in zip(filter_cols, TAG_FILTER_ORDER):
        label = TAG_LABELS[tag_key]
        count = tag_counts.get(tag_key, 0)
        with col:
            if st.button(
                f"{label} ({count})",
                key=f"tag_filter_{campaign_id}_{tag_key}",
                type="primary" if selected_tag == tag_key else "secondary",
                use_container_width=True,
            ):
                st.session_state[tag_filter_key] = tag_key
                st.rerun()

    filtered_rows = filter_rows_by_tag(pending_rows, selected_tag)
    if not filtered_rows:
        st.info(f"Aucun lead dans le filtre « {TAG_LABELS.get(selected_tag, selected_tag)} ».")
        return

    render_pending_table(
        instantly_client=instantly_client,
        campaign_id=campaign_id,
        config=config,
        filtered_rows=filtered_rows,
        pending_rows=pending_rows,
        cache_key=cache_key,
        selected_tag=selected_tag,
        get_thread_messages=get_cached_thread_messages,
        invalidate_thread_cache=invalidate_thread_cache,
    )


def render_webhook_inbox_tab(
    *,
    instantly_client: InstantlyClient,
    campaign_id: str,
) -> None:
    messages = list_inbound_messages(campaign_id)
    if not messages:
        st.info("Aucune réponse capturée pour l'instant.")
        return

    labels = [
        f"{row.get('lead_email')} · {row.get('ai_status')} · {row.get('created_at', '')[:16]}"
        for row in messages
    ]
    selected_idx = st.selectbox("Réponses", range(len(labels)), format_func=lambda i: labels[i])
    inbound = messages[selected_idx]
    lead_email = str(inbound.get("lead_email") or "")

    col_left, col_right = st.columns([1, 1])
    with col_left:
        st.markdown("#### Message entrant")
        st.write(inbound.get("body_text") or "")
        st.caption(f"Status: {inbound.get('ai_status')} — {inbound.get('ai_reason') or ''}")

    with col_right:
        st.markdown("#### Conversation Unibox")
        try:
            thread = get_cached_thread_messages(
                instantly_client,
                campaign_id=campaign_id,
                lead_email=lead_email,
            )
            st.markdown(render_conversation_html(thread), unsafe_allow_html=True)
        except Exception as exc:
            st.warning(f"Unibox indisponible : {exc}")

    stored = list_thread_messages(campaign_id, lead_email)
    outbound = [m for m in stored if m.get("direction") == "outbound"]
    if outbound:
        st.markdown("#### Réponse Hercule")
        for msg in outbound:
            st.write(msg.get("body_text") or "")


def render_inbox_tab(
    *,
    instantly_client: InstantlyClient,
    campaign_id: str,
    config: dict | None,
) -> None:
    tab_pending, tab_webhook = st.tabs(["Pending Unibox", "Webhook"])
    with tab_pending:
        render_pending_unibox_tab(
            instantly_client=instantly_client,
            campaign_id=campaign_id,
            config=config,
        )
    with tab_webhook:
        render_webhook_inbox_tab(
            instantly_client=instantly_client,
            campaign_id=campaign_id,
        )


def _problem_severity_label(status: str) -> str:
    if status == "failed":
        return "Échec"
    if status == "pending":
        return "Brouillon >24h"
    if status == "skipped_recovery":
        return "Recovery <70%"
    if status == "skipped_unsafe":
        return "Abstention IA"
    if status == "skipped_ooo":
        return "OOO"
    return status


def render_problem_tab(
    *,
    instantly_client: InstantlyClient,
    campaign_id: str,
    config: dict | None = None,
) -> None:
    problems = list_problem_messages(campaign_id)
    if not problems:
        st.success("Aucun message en attente dans Problem.")
        return

    by_severity: dict[str, list[dict]] = {}
    for row in problems:
        status = str(row.get("ai_status") or "unknown")
        by_severity.setdefault(status, []).append(row)
    summary_parts = [
        f"{_problem_severity_label(status)}: {len(rows)}"
        for status, rows in sorted(
            by_severity.items(),
            key=lambda item: {
                "failed": 0,
                "pending": 1,
                "skipped_recovery": 2,
                "skipped_unsafe": 3,
                "skipped_ooo": 4,
            }.get(item[0], 9),
        )
    ]
    st.caption(" · ".join(summary_parts))

    labels = [
        f"[{_problem_severity_label(str(row.get('ai_status') or ''))}] "
        f"{row.get('lead_email')} · {row.get('created_at', '')[:16]}"
        for row in problems
    ]
    selected_idx = st.selectbox(
        "Problem queue", range(len(labels)), format_func=lambda i: labels[i], key="problem_select"
    )
    inbound = problems[selected_idx]
    lead_email = str(inbound.get("lead_email") or "")

    st.warning(inbound.get("ai_reason") or "Réponse non traitée par l'IA")
    st.write(inbound.get("body_text") or "")

    try:
        thread = get_cached_thread_messages(
            instantly_client,
            campaign_id=campaign_id,
            lead_email=lead_email,
        )
        st.markdown(render_conversation_html(thread), unsafe_allow_html=True)
    except Exception as exc:
        st.caption(f"Unibox : {exc}")

    target_type = None
    if config:
        raw_target = str(config.get("target_type") or "").strip().lower()
        if raw_target in ("buyer", "seller"):
            target_type = raw_target

    if config and st.button("Re-run Grok (read-only)", key="problem_rerun_grok"):
        from agent_preview import generate_reply_preview
        from lead_tags import build_interest_index, interest_label, lookup_lead_interest
        from reply_gate import apply_reply_gate

        interest_index = build_interest_index(instantly_client, campaign_id)
        interest = lookup_lead_interest(
            instantly_client, campaign_id, lead_email, interest_index
        )
        preview = generate_reply_preview(
            config,
            str(inbound.get("body_text") or ""),
            lead_email,
            interest_label=interest_label(interest),
        )
        gate = apply_reply_gate(interest, preview)
        st.json(
            {
                "allow_reply": gate["allow_reply"],
                "ai_status": gate["ai_status"],
                "reason": gate["reason"],
                "recovery_confidence": preview.get("recovery_confidence"),
                "draft_preview": (preview.get("reply_text") or "")[:500],
            }
        )

    reply_text = st.text_area("Réponse manuelle", height=160, key="manual_reply")
    if st.button("Envoyer la réponse manuelle", disabled=not reply_text.strip()):
        try:
            result = dispatch_manual_reply(
                instantly_client,
                campaign_id=campaign_id,
                inbound=inbound,
                reply_text=reply_text,
                target_type=target_type,
            )
            if result["status"] == "sent":
                st.success(result["detail"])
            else:
                st.info(result["detail"])
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


try:
    api_key = require_instantly_api_key()
    instantly_client = InstantlyClient(api_key)
    campaigns = _load_campaigns(api_key)
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

selected_label = st.selectbox(
    "Campagne Instantly",
    options=list(campaign_options.keys()),
    key="global_campaign",
)
selected_campaign_id = campaign_options[selected_label]
selected_campaign_name = selected_label.split(" (")[0]
config = get_config(selected_campaign_id)
status = derive_onboarding_status(config, selected_campaign_id)
readiness = validate_campaign_readiness(config, selected_campaign_id) if config else None

grok_ok, grok_hint = grok_api_key_status()
with st.sidebar:
    header_col, _ = st.columns([3, 1])
    with header_col:
        st.subheader("Global")
    render_grok_usage_badge(grok_ok=grok_ok, key_prefix="sidebar")
    if not grok_ok:
        st.error(grok_hint)
    st.caption(f"Webhook: `{webhook_public_url()}`")

    st.subheader("Campagne")
    st.caption(f"ID: `{selected_campaign_id}`")
    if config:
        st.caption(f"Statut DB: `{config.get('status')}`")
        st.caption(f"Niche: `{config.get('niche_preset_id')}` ({config.get('target_type')})")
        st.caption(f"Prompt: `{config.get('prompt_key')}`")
        if config.get("initialized_at"):
            st.caption(f"Initialisée: `{config.get('initialized_at')}`")
        if readiness and not readiness.ready and readiness.reason:
            st.error(f"Config invalide: `{readiness.reason}`")
    else:
        st.caption("Statut DB: aucune config")

if status in ("waiting_for_replies", "paused"):
    pending_cache_key = f"pending_replies_{selected_campaign_id}"
    pending_rows_for_mode = dedupe_pending_rows_by_email(
        st.session_state.get(pending_cache_key, [])
    )
    if is_reply_mode_enabled(selected_campaign_id) and pending_rows_for_mode:
        if not config:
            st.error("Config campagne manquante — Reply Mode indisponible.")
            set_reply_mode_enabled(selected_campaign_id, False)
            st.rerun()
        else:
            render_reply_mode_view(
                instantly_client=instantly_client,
                campaign_id=selected_campaign_id,
                campaign_name=selected_campaign_name,
                config=config,
                pending_rows=pending_rows_for_mode,
                cache_key=pending_cache_key,
                invalidate_thread_cache=invalidate_thread_cache,
            )
    elif is_reply_mode_enabled(selected_campaign_id):
        set_reply_mode_enabled(selected_campaign_id, False)
        st.info("Reply Mode fermé — aucun lead en attente.")
        st.rerun()
    else:
        if status == "waiting_for_replies":
            st.success("Inbox: **waiting for replies**")
        else:
            st.warning("Campagne en pause.")
        tab_inbox, tab_prompt, tab_problem = st.tabs(["Inbox", "Prompt", "Problem"])
        with tab_inbox:
            render_inbox_tab(
                instantly_client=instantly_client,
                campaign_id=selected_campaign_id,
                config=config,
            )
        with tab_prompt:
            render_active_prompt_tab(
                campaign_id=selected_campaign_id,
                config=config,
            )
        with tab_problem:
            render_problem_tab(
                instantly_client=instantly_client,
                campaign_id=selected_campaign_id,
                config=config,
            )
else:
    render_onboarding(
        instantly_client=instantly_client,
        campaign_id=selected_campaign_id,
        campaign_name=selected_campaign_name,
        config=config,
        onboarding_status=status,
    )
