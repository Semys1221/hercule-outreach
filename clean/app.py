import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

_APP_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _APP_DIR.parent
for path in (_REPO_ROOT, _APP_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from shared.mev_export import extract_emails_from_dataframe, mev_csv_bytes

from checkpoint import list_checkpoints, partial_verified_path
from paths import data_dir
from core_logic import get_api_key
from instantly_client import (
    count_leads_in_campaign,
    count_leads_in_list,
    fetch_leads_from_list,
    format_resource_label,
    get_api_key as get_instantly_api_key,
    list_all_campaigns,
    list_all_lead_lists,
    leads_to_dataframe,
)
from pipeline import (
    RUN_MODE_CUSTOM,
    RUN_MODE_DRY,
    RUN_MODE_FULL,
    RUN_MODE_TEST_50,
    estimate_credits,
    estimate_minutes,
    run_cleaning_pipeline,
)

st.set_page_config(page_title="Email CSV Cleaner", layout="wide")
st.title("📧 Email Cleaner & Instantly Pipeline")
st.caption(
    "Quick local pre-filter → MyEmailVerifier → purge source list (Full Clean) "
    "→ push to Instantly campaign (workspace duplicate check always on)."
)

if "funnel_step" not in st.session_state:
    st.session_state.funnel_step = 1
if "list_validated" not in st.session_state:
    st.session_state.list_validated = False
if "campaign_validated" not in st.session_state:
    st.session_state.campaign_validated = False
if "pipeline_result" not in st.session_state:
    st.session_state.pipeline_result = None


def _step_indicator(current: int) -> None:
    labels = [
        "1. Source list",
        "2. Campaign",
        "3. Run config",
        "4. Execute",
        "5. Results",
    ]
    cols = st.columns(5)
    for idx, (col, label) in enumerate(zip(cols, labels), start=1):
        with col:
            if idx == current:
                st.markdown(f"**→ {label}**")
            elif idx < current:
                st.markdown(f"✅ {label}")
            else:
                st.markdown(label)


def _status_count(result, status: str) -> int:
    return int(result.status_counts.get(status, 0))


def _render_validation_screen(result, *, show_push: bool) -> None:
    st.success("Cleaning complete — review your results below.")

    st.write("#### MyEmailVerifier results")
    v1, v2, v3, v4 = st.columns(4)
    v1.metric("Valid", _status_count(result, "Valid"))
    v2.metric("Catch All", _status_count(result, "Catch All"))
    v3.metric("Invalid", _status_count(result, "Invalid"))
    v4.metric("Final clean", result.final_clean_count)

    unknown_count = _status_count(result, "Unknown")
    if unknown_count:
        st.caption(f"Also includes {unknown_count} Unknown status lead(s).")

    c1, c2 = st.columns(2)
    c1.metric("Credits used", result.credits_used)
    if result.credits_remaining is not None:
        c2.metric("Credits remaining", result.credits_remaining)
    elif result.run_mode == "dry_run":
        c2.metric("Credits remaining", "— (dry run)")
    else:
        c2.metric("Credits remaining", "Unavailable")

    if (
        result.credits_before is not None
        and result.credits_remaining is not None
        and result.credits_used
    ):
        st.caption(
            f"Balance before run: {result.credits_before} → after run: "
            f"{result.credits_remaining}"
        )

    st.write("#### Pipeline summary")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Raw rows", result.raw_count)
    m2.metric("After quick verify", result.quick_clean_count)
    m3.metric("MEV checked", result.verified_count)
    m4.metric("Rejected by MEV", result.rejected_count)

    with st.expander("Quick verify rejections"):
        q1, q2, q3 = st.columns(3)
        q1.metric("Bad format", result.quick_stats.get("format_errors", 0))
        q2.metric("Garbage domain", result.quick_stats.get("garbage_domains", 0))
        q3.metric("Dead DNS", result.quick_stats.get("dns_errors", 0))

    if show_push and result.push_attempted:
        st.info(
            f"Pushed {result.push_pushed} leads to campaign "
            f"({result.push_batches} batch(es))."
        )
        if result.push_skipped_duplicate:
            st.info(
                f"Skipped {result.push_skipped_duplicate} duplicate(s) "
                f"(already in workspace)."
            )

    if show_push and result.mark_attempted:
        st.info(
            f"Marked {result.mark_patched} lead(s) with Instantly custom variable "
            f"`cleaned=valid` ({result.mark_failed} failed, "
            f"{result.mark_skipped_no_lead} without resolvable lead id)."
        )

    if result.purged_count:
        st.warning(
            f"Purged {result.purged_count} lead(s) from the source Instantly list "
            f"(backup saved in raw CSV artifact)."
        )

    st.caption(
        "Final clean leads include `cleaned=valid` (CSV column and Instantly custom variable on push)."
    )

    st.write("#### Clean data preview")
    st.dataframe(result.final_clean_df.head(10))

    if not result.final_clean_df.empty:
        csv = result.final_clean_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download cleaned CSV",
            data=csv,
            file_name="cleaned_emails.csv",
            mime="text/csv",
        )

    if not result.rejected_df.empty:
        with st.expander(f"View {len(result.rejected_df)} rejected emails"):
            st.dataframe(
                result.rejected_df[[result.email_column, "Verification_Status"]].head(50)
            )

    with st.expander("Saved artifact paths"):
        for label, path in result.artifact_paths.items():
            st.text(f"{label}: {path}")

    if st.button(
        "Clean another list",
        type="primary",
        key=f"clean_another_{'instantly' if show_push else 'csv'}",
    ):
        if show_push:
            _reset_funnel()
        else:
            st.session_state.csv_pipeline_result = None
            st.rerun()


def _reset_funnel() -> None:
    for key in (
        "funnel_step",
        "list_validated",
        "campaign_validated",
        "list_id",
        "list_name",
        "list_count",
        "campaign_id",
        "campaign_name",
        "campaign_count",
        "allowed_statuses",
        "run_mode",
        "custom_limit",
        "pipeline_result",
        "csv_pipeline_result",
    ):
        st.session_state.pop(key, None)
    st.session_state.funnel_step = 1
    st.session_state.list_validated = False
    st.session_state.campaign_validated = False
    st.session_state.pipeline_result = None
    st.session_state.csv_pipeline_result = None
    st.rerun()


def _render_resume_panel(*, show_push: bool) -> None:
    checkpoints = list_checkpoints()
    if not checkpoints:
        return

    st.divider()
    st.subheader("Resume interrupted job")
    st.caption(
        "Verified emails are saved in checkpoints. Resume only verifies the remaining "
        "addresses (no duplicate MEV credits for emails already checked)."
    )

    options = {}
    for item in checkpoints:
        total = item.get("total_target")
        suffix = f"/{total}" if total else ""
        label = f"{item['prefix']} — {item['verified_count']}{suffix} verified"
        options[label] = item
    selected_label = st.selectbox("Interrupted job", list(options.keys()))
    selected = options[selected_label]

    quick_clean_path = os.path.join(data_dir(), f"{selected['prefix']}_quick_clean.csv")
    source_artifact = selected.get("source_artifact") or quick_clean_path
    if not os.path.isfile(source_artifact):
        st.warning(f"Source list not found: `{source_artifact}`")
        return

    resume_df = pd.read_csv(source_artifact)
    partial_path = partial_verified_path(selected["prefix"])
    if os.path.isfile(partial_path):
        partial_df = pd.read_csv(partial_path)
        clean_partial = partial_df[
            partial_df.get("Verification_Status", pd.Series(dtype=str)).isin(
                ["Valid", "Catch All"]
            )
        ]
        if not clean_partial.empty:
            st.info(
                f"{len(clean_partial)} clean lead(s) already saved in partial results "
                f"(safe even if the job stops again)."
            )
            csv = clean_partial.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download partial clean leads now",
                data=csv,
                file_name=f"{selected['prefix']}_partial_clean.csv",
                mime="text/csv",
            )

    allowed_statuses = st.multiselect(
        "Include these statuses",
        options=["Valid", "Catch All", "Unknown"],
        default=["Valid", "Catch All"],
        key=f"resume_statuses_{selected['prefix']}",
    )
    run_mode = st.selectbox(
        "Run mode",
        options=[RUN_MODE_FULL, RUN_MODE_TEST_50, RUN_MODE_DRY],
        format_func=lambda value: {
            RUN_MODE_FULL: "Full list (verify remaining only)",
            RUN_MODE_TEST_50: "Test next 50 rows",
            RUN_MODE_DRY: "Dry run",
        }[value],
        key=f"resume_mode_{selected['prefix']}",
    )

    if st.button("Resume verification", type="primary", key=f"resume_btn_{selected['prefix']}"):
        if run_mode != RUN_MODE_DRY and not get_api_key():
            st.error("MYEMAILVERIFIER_API_KEY is missing.")
            return

        progress_bar = st.progress(0)
        status_text = st.empty()
        log_expander = st.expander("Resume log", expanded=True)
        log_lines: list[str] = []

        def on_progress(message: str, fraction: float) -> None:
            progress_bar.progress(min(max(fraction, 0.0), 1.0))
            status_text.text(message)
            log_lines.append(message)
            with log_expander:
                st.text("\n".join(log_lines[-30:]))

        email_col = "email" if "email" in resume_df.columns else resume_df.columns[0]
        try:
            result = run_cleaning_pipeline(
                source_df=resume_df,
                run_mode=run_mode,
                custom_limit=None,
                allowed_statuses=allowed_statuses,
                destination_campaign_id=st.session_state.get("campaign_id")
                if show_push
                else None,
                source_list_id=None,
                purge_source=False,
                email_column=email_col,
                on_progress=on_progress,
                resume_prefix=selected["prefix"],
                skip_quick_verify=True,
            )
            _render_validation_screen(result, show_push=show_push)
            st.session_state.pipeline_result = result
            if show_push:
                st.session_state.funnel_step = 5
                st.rerun()
        except Exception as exc:
            st.error(f"Resume failed: {exc}")


@st.cache_data(ttl=300, show_spinner=False)
def _cached_lead_lists() -> list[dict]:
    items = list_all_lead_lists()
    return sorted(
        [
            {
                "id": item.get("id", ""),
                "name": (item.get("name") or "").strip() or "(unnamed)",
            }
            for item in items
            if item.get("id")
        ],
        key=lambda item: item["name"].lower(),
    )


@st.cache_data(ttl=300, show_spinner=False)
def _cached_campaigns() -> list[dict]:
    items = list_all_campaigns()
    return sorted(
        [
            {
                "id": item.get("id", ""),
                "name": (item.get("name") or "").strip() or "(unnamed)",
            }
            for item in items
            if item.get("id")
        ],
        key=lambda item: item["name"].lower(),
    )


def _resource_labels(resources: list[dict]) -> list[str]:
    name_counts: dict[str, int] = {}
    for resource in resources:
        name = resource["name"]
        name_counts[name] = name_counts.get(name, 0) + 1

    labels: list[str] = []
    for resource in resources:
        name = resource["name"]
        if name_counts[name] > 1:
            labels.append(f"{name} ({resource['id']})")
        else:
            labels.append(format_resource_label(name, resource["id"]))
    return labels


def _select_instantly_resource(
    *,
    resources: list[dict],
    label: str,
    key: str,
    current_id: str | None = None,
) -> dict | None:
    if not resources:
        st.warning(f"No {label.lower()} found in your Instantly workspace.")
        return None

    labels = _resource_labels(resources)
    default_index = 0
    if current_id:
        for index, resource in enumerate(resources):
            if resource["id"] == current_id:
                default_index = index
                break

    selected_index = st.selectbox(
        label,
        options=range(len(resources)),
        format_func=lambda index: labels[index],
        index=default_index,
        key=key,
    )
    return resources[selected_index]


def _run_mode_radio(*, key_prefix: str = "default") -> tuple[str, int | None]:
    choice = st.radio(
        "Processing mode",
        (
            "Dry Run (0 credits, no push)",
            "Test Mode (first 50 leads)",
            "Full Clean (entire list)",
            "Custom limit",
        ),
        key=f"{key_prefix}_run_mode_choice",
    )
    custom_limit: int | None = None
    if choice.startswith("Dry"):
        return RUN_MODE_DRY, None
    if choice.startswith("Test"):
        return RUN_MODE_TEST_50, None
    if choice.startswith("Full"):
        return RUN_MODE_FULL, None
    custom_limit = st.number_input(
        "Number of leads to verify",
        min_value=1,
        value=100,
        step=1,
        key=f"{key_prefix}_custom_limit_input",
    )
    return RUN_MODE_CUSTOM, int(custom_limit)


tab_instantly, tab_csv = st.tabs(["Instantly Pipeline", "CSV Upload"])

with tab_instantly:
    _step_indicator(st.session_state.funnel_step)

    if not get_instantly_api_key():
        st.error(
            "Set INSTANTLY_API_KEY in the repo root `.env` or "
            "`clean/.env` before using the Instantly pipeline."
        )

    step = st.session_state.funnel_step

    if step == 1:
        st.subheader("Step 1 — Source Instantly list")

        refresh_col, _ = st.columns([1, 3])
        with refresh_col:
            if st.button("Refresh lists", key="refresh_lists"):
                _cached_lead_lists.clear()
                st.rerun()

        try:
            lead_lists = _cached_lead_lists()
        except Exception as exc:
            st.error(f"Could not load Instantly lists: {exc}")
            lead_lists = []

        selected_list = _select_instantly_resource(
            resources=lead_lists,
            label="Select source list",
            key="source_list_select",
            current_id=st.session_state.get("list_id"),
        )

        if selected_list:
            st.caption(f"List ID: `{selected_list['id']}`")
            st.caption(
                "For manual MyEmailVerifier upload, use **Download for MEV** below — "
                "do not export from the Instantly UI (wrong column layout)."
            )
            if st.button("Prepare MEV download", key="prepare_mev_download"):
                with st.spinner("Fetching emails from Instantly..."):
                    leads = fetch_leads_from_list(selected_list["id"])
                    emails = extract_emails_from_dataframe(leads_to_dataframe(leads))
                    st.session_state.mev_download_bytes = mev_csv_bytes(emails)
                    st.session_state.mev_download_count = len(emails)
                    st.session_state.mev_download_name = (
                        f"mev_{selected_list['id'][:8]}.csv"
                    )
            if st.session_state.get("mev_download_bytes"):
                st.download_button(
                    label=(
                        f"Download for MEV "
                        f"({st.session_state.get('mev_download_count', 0)} emails)"
                    ),
                    data=st.session_state.mev_download_bytes,
                    file_name=st.session_state.get(
                        "mev_download_name", "mev_emails.csv"
                    ),
                    mime="text/csv",
                    key="download_mev_csv",
                )

        if st.button(
            "Validate list",
            type="primary",
            disabled=selected_list is None,
        ):
            try:
                count = count_leads_in_list(selected_list["id"])
                st.session_state.list_id = selected_list["id"]
                st.session_state.list_name = selected_list["name"]
                st.session_state.list_count = count
                st.session_state.list_validated = True
                st.session_state.funnel_step = 2
                st.rerun()
            except Exception as exc:
                st.error(f"Could not validate list: {exc}")

        if st.session_state.list_validated:
            st.info(
                f"List **{st.session_state.get('list_name')}** — "
                f"{st.session_state.get('list_count', 0)} leads"
            )

    elif step == 2:
        st.subheader("Step 2 — Destination campaign")
        if st.session_state.list_validated:
            st.info(
                f"Source: **{st.session_state.get('list_name')}** "
                f"({st.session_state.get('list_count', 0)} leads)"
            )

        refresh_col, _ = st.columns([1, 3])
        with refresh_col:
            if st.button("Refresh campaigns", key="refresh_campaigns"):
                _cached_campaigns.clear()
                st.rerun()

        try:
            campaigns = _cached_campaigns()
        except Exception as exc:
            st.error(f"Could not load Instantly campaigns: {exc}")
            campaigns = []

        selected_campaign = _select_instantly_resource(
            resources=campaigns,
            label="Select destination campaign",
            key="destination_campaign_select",
            current_id=st.session_state.get("campaign_id"),
        )

        if selected_campaign:
            st.caption(f"Campaign ID: `{selected_campaign['id']}`")

        col_back, col_validate = st.columns(2)
        with col_back:
            if st.button("← Back to list"):
                st.session_state.funnel_step = 1
                st.rerun()
        with col_validate:
            validate_clicked = st.button(
                "Validate campaign",
                type="primary",
                disabled=selected_campaign is None,
            )

        if validate_clicked and selected_campaign:
            try:
                count = count_leads_in_campaign(selected_campaign["id"])
                st.session_state.campaign_id = selected_campaign["id"]
                st.session_state.campaign_name = selected_campaign["name"]
                st.session_state.campaign_count = count
                st.session_state.campaign_validated = True
                st.session_state.funnel_step = 3
                st.rerun()
            except Exception as exc:
                st.error(f"Could not validate campaign: {exc}")

    elif step == 3:
        st.subheader("Step 3 — Run configuration")
        st.info(
            f"Source list: **{st.session_state.get('list_name')}** "
            f"({st.session_state.get('list_count', 0)} leads)"
        )
        st.info(
            f"Destination campaign: **{st.session_state.get('campaign_name')}** "
            f"({st.session_state.get('campaign_count', 0)} leads)"
        )

        allowed_statuses = st.multiselect(
            "Include these MyEmailVerifier statuses",
            options=["Valid", "Catch All", "Unknown"],
            default=["Valid", "Catch All"],
        )
        run_mode, custom_limit = _run_mode_radio(key_prefix="instantly")

        preview_count = st.session_state.get("list_count", 0)
        if run_mode == RUN_MODE_TEST_50:
            preview_count = min(50, preview_count)
        elif run_mode == RUN_MODE_CUSTOM and custom_limit:
            preview_count = min(custom_limit, preview_count)

        st.caption(
            "MEV receives a single-column `email` CSV automatically during the pipeline."
        )

        if run_mode != RUN_MODE_DRY and not get_api_key():
            st.error(
                "Set MYEMAILVERIFIER_API_KEY in `.env` before running real verification."
            )
        elif run_mode != RUN_MODE_DRY:
            credits = estimate_credits(preview_count, run_mode)
            minutes = estimate_minutes(preview_count, run_mode)
            st.info(
                f"Estimated: ~{credits} credits, ~{minutes} min via MEV bulk API "
                f"(after quick verify reduces the set)."
            )
            if run_mode == RUN_MODE_FULL:
                st.warning(
                    "Full Clean will permanently remove all leads from the source "
                    "Instantly list after download (local raw.csv backup). "
                    "Clean leads are then pushed to the destination campaign."
                )

        col_back, col_next = st.columns(2)
        with col_back:
            if st.button("← Back to campaign"):
                st.session_state.funnel_step = 2
                st.rerun()
        with col_next:
            if st.button("Continue to execute →", type="primary"):
                st.session_state.allowed_statuses = allowed_statuses
                st.session_state.run_mode = run_mode
                st.session_state.custom_limit = custom_limit
                st.session_state.funnel_step = 4
                st.rerun()

    elif step == 5:
        st.subheader("Step 5 — Results")
        result = st.session_state.get("pipeline_result")
        if result is None:
            st.warning("No results found. Start a new cleaning run.")
            if st.button("Go to source list"):
                st.session_state.funnel_step = 1
                st.rerun()
        else:
            _render_validation_screen(result, show_push=True)

    elif step == 4:
        st.subheader("Step 4 — Execute pipeline")
        run_mode = st.session_state.get("run_mode", RUN_MODE_DRY)
        custom_limit = st.session_state.get("custom_limit")
        allowed_statuses = st.session_state.get("allowed_statuses", ["Valid", "Catch All"])

        st.markdown(
            f"- **List:** {st.session_state.get('list_name')} "
            f"(`{st.session_state.get('list_id')}`) — "
            f"{st.session_state.get('list_count', 0)} leads\n"
            f"- **Campaign:** {st.session_state.get('campaign_name')} "
            f"(`{st.session_state.get('campaign_id')}`) — "
            f"{st.session_state.get('campaign_count', 0)} leads\n"
            f"- **Mode:** {run_mode}"
            + (f" (limit {custom_limit})" if run_mode == RUN_MODE_CUSTOM else "")
            + f"\n- **Allowed statuses:** {', '.join(allowed_statuses)}"
        )

        if run_mode == RUN_MODE_FULL:
            st.warning(
                "Full Clean: the source list will be emptied on Instantly after "
                "download (backup in local raw.csv). This cannot be undone on Instantly."
            )

        col_back, col_run = st.columns(2)
        with col_back:
            if st.button("← Back to config"):
                st.session_state.funnel_step = 3
                st.rerun()

        with col_run:
            run_clicked = st.button("Run pipeline", type="primary")

        if run_clicked:
            if run_mode != RUN_MODE_DRY and not get_api_key():
                st.error("Cannot start: MYEMAILVERIFIER_API_KEY is missing.")
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()
                log_expander = st.expander("Live log", expanded=True)
                log_lines: list[str] = []

                def on_progress(message: str, fraction: float) -> None:
                    progress_bar.progress(min(max(fraction, 0.0), 1.0))
                    status_text.text(message)
                    log_lines.append(message)
                    with log_expander:
                        st.text("\n".join(log_lines[-30:]))

                try:
                    on_progress("Downloading leads from Instantly list...", 0.02)
                    leads = fetch_leads_from_list(
                        st.session_state.list_id,
                        on_progress=lambda n: on_progress(
                            f"Downloaded {n} leads...",
                            0.02 + min(n / max(st.session_state.list_count, 1), 1) * 0.03,
                        ),
                    )
                    source_df = leads_to_dataframe(leads)
                    on_progress(f"Downloaded {len(source_df)} leads.", 0.05)

                    result = run_cleaning_pipeline(
                        source_df=source_df,
                        run_mode=run_mode,
                        custom_limit=custom_limit,
                        allowed_statuses=allowed_statuses,
                        destination_campaign_id=st.session_state.campaign_id,
                        source_list_id=st.session_state.list_id,
                        purge_source=(run_mode == RUN_MODE_FULL),
                        on_progress=on_progress,
                    )
                    st.session_state.pipeline_result = result
                    st.session_state.funnel_step = 5
                    st.rerun()
                except Exception as exc:
                    st.error(f"Pipeline failed: {exc}")

with tab_csv:
    st.subheader("CSV Upload")

    if st.session_state.get("csv_pipeline_result") is not None:
        _render_validation_screen(st.session_state.csv_pipeline_result, show_push=False)
    else:
        st.write("Upload a CSV for quick verify + MyEmailVerifier cleaning (no Instantly push).")

        uploaded_file = st.file_uploader("Upload your CSV file", type=["csv"])

        if uploaded_file is not None:
            df = pd.read_csv(uploaded_file)

            st.write("### Data Preview")
            st.dataframe(df.head(3))

            email_column = st.selectbox(
                "Which column contains the email addresses?",
                df.columns,
            )

            allowed_statuses = st.multiselect(
                "Which email statuses should be included in the cleaned file?",
                options=["Valid", "Catch All", "Unknown"],
                default=["Valid", "Catch All"],
                key="csv_allowed_statuses",
            )

            run_mode, custom_limit = _run_mode_radio(key_prefix="csv")

            if run_mode == RUN_MODE_TEST_50:
                preview_rows = min(50, len(df))
            elif run_mode == RUN_MODE_CUSTOM and custom_limit:
                preview_rows = min(custom_limit, len(df))
            else:
                preview_rows = len(df)

            if run_mode != RUN_MODE_DRY:
                if not get_api_key():
                    st.error(
                        "Set MYEMAILVERIFIER_API_KEY in `.env` before running real verification."
                    )
                else:
                    st.info(
                        f"Estimated: ~{estimate_credits(preview_rows, run_mode)} credits, "
                        f"~{estimate_minutes(preview_rows, run_mode)} min via MEV bulk API."
                    )

            if st.button("Start Cleaning", type="primary"):
                if run_mode != RUN_MODE_DRY and not get_api_key():
                    st.error("Cannot start: MYEMAILVERIFIER_API_KEY is missing.")
                else:
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    log_expander = st.expander("Live verification log", expanded=False)
                    log_lines: list[str] = []

                    def on_progress(message: str, fraction: float) -> None:
                        progress_bar.progress(min(max(fraction, 0.0), 1.0))
                        status_text.text(message)
                        log_lines.append(message)
                        with log_expander:
                            st.text("\n".join(log_lines[-20:]))

                    try:
                        result = run_cleaning_pipeline(
                            source_df=df,
                            run_mode=run_mode,
                            custom_limit=custom_limit,
                            allowed_statuses=allowed_statuses,
                            destination_campaign_id=None,
                            email_column=email_column,
                            on_progress=on_progress,
                        )
                        st.session_state.csv_pipeline_result = result
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Cleaning failed: {exc}")
