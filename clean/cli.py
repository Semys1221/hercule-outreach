"""Headless CLI for MyEmailVerifier cleaning pipeline (Render / cron)."""

from __future__ import annotations

import os
import sys
from typing import Optional

import pandas as pd
import typer

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_LIB_DIR)
for path in (_REPO_ROOT, _LIB_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from bulk_verifier import fetch_mev_credits  # noqa: E402
from shared.mev_export import (  # noqa: E402
    audit_emails,
    extract_emails_from_dataframe,
    write_mev_csv,
)
from checkpoint import list_checkpoints  # noqa: E402
from core_logic import get_api_key  # noqa: E402
from instantly_client import (  # noqa: E402
    fetch_leads_from_list,
    leads_to_dataframe,
)
from paths import data_dir  # noqa: E402
from pipeline import (  # noqa: E402
    RUN_MODE_CUSTOM,
    RUN_MODE_DRY,
    RUN_MODE_FULL,
    RUN_MODE_TEST_50,
    run_cleaning_pipeline,
)

app = typer.Typer(help="Email cleaner CLI — MyEmailVerifier bulk verify + Instantly push")

_MODE_MAP = {
    "dry_run": RUN_MODE_DRY,
    "test_50": RUN_MODE_TEST_50,
    "full": RUN_MODE_FULL,
    "custom": RUN_MODE_CUSTOM,
}


def _log(msg: str) -> None:
    typer.echo(f"[LOG] {msg}")


def _on_progress(message: str, fraction: float) -> None:
    pct = int(min(max(fraction, 0.0), 1.0) * 100)
    typer.echo(f"[{pct:3d}%] {message}")


def _parse_allowed_statuses(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _resolve_run_mode(mode: str) -> str:
    key = mode.strip().lower()
    if key not in _MODE_MAP:
        raise typer.BadParameter(
            f"Unknown mode {mode!r}. Choose from: {', '.join(_MODE_MAP)}"
        )
    return _MODE_MAP[key]


@app.command()
def credits() -> None:
    """Print remaining MyEmailVerifier credits (smoke test)."""
    if not get_api_key():
        raise typer.BadParameter("MYEMAILVERIFIER_API_KEY is missing")
    balance = fetch_mev_credits()
    if balance is None:
        typer.secho("Could not read MEV credits.", fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.secho(f"MyEmailVerifier credits: {balance}", fg=typer.colors.GREEN)


@app.command("checkpoints")
def checkpoints_cmd() -> None:
    """List resumable verification jobs on disk."""
    items = list_checkpoints()
    if not items:
        typer.echo("No checkpoints found.")
        return
    for item in items:
        total = item.get("total_target")
        suffix = f"/{total}" if total else ""
        updated = item.get("updated_at") or "unknown"
        typer.echo(
            f"{item['prefix']} — {item['verified_count']}{suffix} verified "
            f"(updated {updated})"
        )


@app.command("export-mev")
def export_mev(
    list_id: str = typer.Option(..., "--list-id", help="Instantly source list UUID"),
    output: str = typer.Option(
        "mev_emails.csv",
        "--output",
        "-o",
        help="Output path for single-column MEV CSV",
    ),
) -> None:
    """Export Instantly list emails as a MyEmailVerifier-ready CSV (header: email)."""
    _log(f"Downloading leads from Instantly list {list_id}...")
    leads = fetch_leads_from_list(
        list_id,
        on_progress=lambda n: _log(f"Downloaded {n} leads"),
    )
    df = leads_to_dataframe(leads)
    emails = extract_emails_from_dataframe(df)
    if not emails:
        raise typer.BadParameter("No valid emails found in list")

    count = write_mev_csv(emails, output)
    typer.secho(
        f"Wrote {count} email(s) to {output}",
        fg=typer.colors.GREEN,
    )
    typer.echo("Upload this file to MyEmailVerifier — do not use Instantly UI export.")


@app.command("audit-list")
def audit_list(
    list_id: str = typer.Option(..., "--list-id", help="Instantly source list UUID"),
) -> None:
    """Report valid vs invalid email addresses in an Instantly list."""
    _log(f"Downloading leads from Instantly list {list_id}...")
    leads = fetch_leads_from_list(
        list_id,
        on_progress=lambda n: _log(f"Downloaded {n} leads"),
    )
    df = leads_to_dataframe(leads)
    stats = audit_emails(df.get("email", pd.Series(dtype=str)).tolist())
    typer.echo(f"Total rows: {stats['total']}")
    typer.echo(f"Valid emails: {stats['valid']}")
    typer.echo(f"Invalid/missing: {stats['invalid']}")
    if stats["invalid"]:
        typer.secho(
            "Some leads have invalid email fields — fix in Instantly before MEV upload.",
            fg=typer.colors.YELLOW,
        )


@app.command()
def run(
    list_id: str = typer.Option(..., "--list-id", help="Instantly source list UUID"),
    campaign_id: Optional[str] = typer.Option(
        None,
        "--campaign-id",
        help="Destination Instantly campaign UUID",
    ),
    mode: str = typer.Option(
        "test_50",
        "--mode",
        help="dry_run | test_50 | full | custom",
    ),
    resume_prefix: Optional[str] = typer.Option(
        None,
        "--resume-prefix",
        help="Artifact prefix to resume from checkpoint (skips quick verify)",
    ),
    allowed_statuses: str = typer.Option(
        "Valid,Catch All",
        "--allowed-statuses",
        help="Comma-separated MEV statuses to keep",
    ),
    skip_push: bool = typer.Option(
        False,
        "--skip-push",
        help="Verify only — do not push to Instantly campaign",
    ),
    refresh_list: bool = typer.Option(
        False,
        "--refresh-list",
        help="Re-download leads from Instantly even when resuming",
    ),
    custom_limit: Optional[int] = typer.Option(
        None,
        "--custom-limit",
        help="Row limit when --mode custom",
    ),
) -> None:
    """Fetch Instantly list → quick verify → MEV bulk → optional campaign push."""
    run_mode = _resolve_run_mode(mode)
    statuses = _parse_allowed_statuses(allowed_statuses)
    destination = None if skip_push else campaign_id

    if run_mode != RUN_MODE_DRY and not get_api_key():
        raise typer.BadParameter("MYEMAILVERIFIER_API_KEY is missing")

    if destination is None and not skip_push and run_mode != RUN_MODE_DRY:
        raise typer.BadParameter(
            "Provide --campaign-id or pass --skip-push for verify-only runs"
        )

    if run_mode == RUN_MODE_FULL:
        typer.secho(
            "Full Clean: source list will be purged on Instantly after download.",
            fg=typer.colors.YELLOW,
        )

    source_df: pd.DataFrame
    email_column: str | None = None
    skip_quick = False

    if resume_prefix and not refresh_list:
        quick_clean_path = os.path.join(data_dir(), f"{resume_prefix}_quick_clean.csv")
        if not os.path.isfile(quick_clean_path):
            raise typer.BadParameter(f"Resume artifact not found: {quick_clean_path}")
        source_df = pd.read_csv(quick_clean_path)
        skip_quick = True
        email_column = "email" if "email" in source_df.columns else source_df.columns[0]
        _log(f"Resuming from {quick_clean_path} ({len(source_df)} rows)")
    else:
        _log(f"Downloading leads from Instantly list {list_id}...")
        leads = fetch_leads_from_list(list_id, on_progress=lambda n: _log(f"Downloaded {n} leads"))
        source_df = leads_to_dataframe(leads)
        _log(f"Downloaded {len(source_df)} leads")

    result = run_cleaning_pipeline(
        source_df=source_df,
        run_mode=run_mode,
        custom_limit=custom_limit,
        allowed_statuses=statuses,
        destination_campaign_id=destination,
        source_list_id=list_id,
        purge_source=(run_mode == RUN_MODE_FULL),
        email_column=email_column,
        on_progress=_on_progress,
        resume_prefix=resume_prefix,
        skip_quick_verify=skip_quick,
    )

    typer.secho(
        f"Done — {result.final_clean_count} clean / {result.rejected_count} rejected "
        f"({result.credits_used} MEV credits)",
        fg=typer.colors.GREEN,
    )
    if result.credits_before is not None and result.credits_remaining is not None:
        typer.echo(
            f"Credits: {result.credits_before} → {result.credits_remaining}"
        )
    if not skip_push and destination:
        typer.echo(
            f"Instantly push: {result.push_pushed} pushed, "
            f"{result.push_skipped_duplicate} skipped duplicate"
        )
    for label, path in result.artifact_paths.items():
        typer.echo(f"  {label}: {path}")


if __name__ == "__main__":
    app()
