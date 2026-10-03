"""Typer CLI for preset bootstrap."""

from __future__ import annotations

import typer

from bootstrap.discovery import discover_presets, invalidate_preset_cache
from bootstrap.validators import validate_preset_runtime

app = typer.Typer(
    help="Bootstrap scraper preset configurations interactively.",
    no_args_is_help=True,
)


@app.command("create")
def create_cmd() -> None:
    """Open Streamlit UI to create a new preset (tab 1 Config → Create new)."""
    typer.secho(
        "Use the Streamlit onboarding UI: pnpm streamlit-scraper → tab 1 Config → Create new.",
        fg=typer.colors.CYAN,
    )
    raise typer.Exit(code=0)


@app.command("list")
def list_cmd() -> None:
    """List discovered presets."""
    presets = discover_presets(use_cache=True)
    if not presets:
        typer.secho("No presets found.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=0)

    typer.echo(f"{'ID':<28} {'LABEL':<40} {'TARGET':>8}  LIST_ID")
    typer.echo("-" * 100)
    for meta in presets.values():
        config = meta.loader()
        typer.echo(
            f"{meta.preset_id:<28} {meta.label:<40} "
            f"{int(config.get('TARGET_LEADS', 0)):>8,}  "
            f"{config.get('INSTANTLY_LIST_ID', '')}"
        )


@app.command("validate")
def validate_cmd(
    preset_id: str = typer.Argument(
        "",
        help="Preset to validate (default: all presets)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Also run pipeline dry-run (query count check)",
    ),
) -> None:
    """Validate preset schema and loadability."""
    presets = discover_presets(use_cache=True)
    targets = [preset_id] if preset_id else sorted(presets.keys())

    if preset_id and preset_id not in presets:
        typer.secho(f"Unknown preset {preset_id!r}.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    failed = False
    for pid in targets:
        result = validate_preset_runtime(pid, dry_run=dry_run)
        if result.ok and not result.warnings:
            typer.secho(f"OK  {pid}", fg=typer.colors.GREEN)
        elif result.ok:
            typer.secho(f"OK  {pid} (with warnings)", fg=typer.colors.YELLOW)
            for warn in result.warnings:
                typer.echo(f"    warn: {warn}")
        else:
            failed = True
            typer.secho(f"FAIL {pid}", fg=typer.colors.RED)
            for err in result.errors:
                typer.echo(f"    error: {err}")
            for warn in result.warnings:
                typer.echo(f"    warn: {warn}")

    if failed:
        raise typer.Exit(code=1)


@app.command("provision-instantly")
def provision_instantly_cmd(
    preset_id: str = typer.Argument(
        "",
        help="Preset to provision (default: all sub-niche configs/)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be created without calling Instantly",
    ),
    with_subsequence: bool = typer.Option(
        False,
        "--with-subsequence",
        help="After provisioning, bootstrap E1/E2/E3 bypass + reply prompts",
    ),
) -> None:
    """Create or reuse Instantly list + draft campaign for niche presets."""
    import os

    from bootstrap.campaign_layers import bootstrap_campaign_layers
    from bootstrap.provision import provision_preset, provision_targets
    from config_loader import load_config

    try:
        targets = provision_targets(preset_id)
    except KeyError:
        typer.secho(f"Unknown preset {preset_id!r}.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if not targets:
        typer.secho("No presets in configs/ to provision.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=0)

    api_key = ""
    if not dry_run:
        sample = load_config(targets[0], require_keys=False)
        api_key = str(sample.get("INSTANTLY_API_KEY") or os.getenv("INSTANTLY_API_KEY") or "").strip()
        if not api_key:
            typer.secho("INSTANTLY_API_KEY is required (set it in repo .env).", fg=typer.colors.RED)
            raise typer.Exit(code=1)

    failed = False
    for pid in targets:
        try:
            result = provision_preset(
                pid,
                api_key=api_key,
                dry_run=dry_run,
            )
        except Exception as exc:
            failed = True
            typer.secho(f"FAIL {pid}: {exc}", fg=typer.colors.RED)
            continue

        status = "SKIP" if result.get("skipped") else ("DRY" if dry_run else "OK")
        color = typer.colors.YELLOW if status != "OK" else typer.colors.GREEN
        subseq = result.get("subsequence_id") or "(none)"
        typer.secho(
            f"{status} {pid} — {result['name']} "
            f"list={result.get('list_id') or '(pending)'} "
            f"campaign={result.get('campaign_id') or '(pending)'} "
            f"subsequence={subseq}",
            fg=color,
        )

        campaign_id = str(result.get("campaign_id") or "").strip()
        if with_subsequence and campaign_id and not dry_run and not result.get("skipped"):
            try:
                layer = bootstrap_campaign_layers(pid, campaign_id=campaign_id, api_key=api_key)
                seeded = (layer.get("bypass") or {}).get("seeded_templates") or []
                cloned = (layer.get("bypass") or {}).get("cloned_templates") or []
                prompts = layer.get("prompt_paths") or []
                if seeded:
                    typer.echo(f"    bypass seeded: {', '.join(seeded)}")
                elif cloned:
                    typer.echo(f"    bypass cloned: {', '.join(cloned)}")
                if prompts:
                    typer.echo(f"    reply prompts: {len(prompts)} file(s)")
            except Exception as exc:
                failed = True
                typer.secho(f"    bootstrap layers FAIL: {exc}", fg=typer.colors.RED)

    if failed:
        raise typer.Exit(code=1)


@app.command("onboard-subsequence")
def onboard_subsequence_cmd(
    preset_id: str = typer.Argument(
        "",
        help="Preset to onboard (default: all sub-niche configs/)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be onboarded without calling APIs",
    ),
    clone_from: str = typer.Option(
        "",
        "--clone-from",
        help="Source campaign UUID for template clone (default: Biggy Agency)",
    ),
) -> None:
    """Onboard Supabase subsequence config + webhook for existing campaigns."""
    from bootstrap.provision import onboard_subsequence_preset, provision_targets

    try:
        targets = provision_targets(preset_id)
    except KeyError:
        typer.secho(f"Unknown preset {preset_id!r}.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if not targets:
        typer.secho("No sub-niche configs/ presets to onboard.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=0)

    failed = False
    api_key = ""
    if not dry_run:
        import os

        from config_loader import load_config

        sample = load_config(targets[0], require_keys=False)
        api_key = str(
            sample.get("INSTANTLY_API_KEY") or os.getenv("INSTANTLY_API_KEY") or ""
        ).strip()
        if not api_key:
            typer.secho("INSTANTLY_API_KEY is required (set it in repo .env).", fg=typer.colors.RED)
            raise typer.Exit(code=1)

    for pid in targets:
        try:
            result = onboard_subsequence_preset(
                pid,
                api_key=api_key,
                clone_from=clone_from,
                dry_run=dry_run,
                log_cb=lambda msg: typer.echo(f"    {msg}"),
            )
        except Exception as exc:
            failed = True
            typer.secho(f"FAIL {pid}: {exc}", fg=typer.colors.RED)
            continue

        status = "DRY" if dry_run else "OK"
        cloned = result.get("cloned_templates") or []
        clone_note = f" templates={len(cloned)}" if cloned else ""
        typer.secho(
            f"{status} {pid} — {result['name']} "
            f"campaign={result.get('campaign_id')}{clone_note}",
            fg=typer.colors.GREEN if status == "OK" else typer.colors.YELLOW,
        )

    if failed:
        raise typer.Exit(code=1)


@app.command("cleanup-empty-instantly")
def cleanup_empty_instantly_cmd(
    execute: bool = typer.Option(
        False,
        "--execute",
        help="Actually delete resources (default is dry-run)",
    ),
) -> None:
    """Delete workspace Instantly lists/campaigns with 0 leads; force-delete services_fm."""
    import os

    import config_loader  # noqa: F401 — loads repo .env via side effect

    from bootstrap.cleanup import cleanup_empty_instantly

    api_key = os.getenv("INSTANTLY_API_KEY", "").strip()
    if not api_key:
        typer.secho("INSTANTLY_API_KEY is required (set it in repo .env).", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    result = cleanup_empty_instantly(api_key, dry_run=not execute)
    mode = "EXEC" if execute else "DRY"

    typer.echo(f"\n--- {mode} lists ({len(result['lists_to_delete'])}) ---")
    for row in result["lists_to_delete"]:
        typer.echo(f"  [{row['reason']}] {row['name']} ({row['id']})")

    typer.echo(f"\n--- {mode} campaigns ({len(result['campaigns_to_delete'])}) ---")
    for row in result["campaigns_to_delete"]:
        typer.echo(f"  [{row['reason']}] {row['name']} ({row['id']})")

    if execute:
        typer.secho(
            f"\nDeleted {len(result['deleted_lists'])} list(s), "
            f"{len(result['deleted_campaigns'])} campaign(s).",
            fg=typer.colors.GREEN,
        )
    else:
        typer.secho("\nDry-run only. Pass --execute to delete.", fg=typer.colors.YELLOW)


@app.command("cleanup-instantly")
def cleanup_instantly_cmd(
    execute: bool = typer.Option(
        False,
        "--execute",
        help="Actually delete resources (default is dry-run)",
    ),
) -> None:
    """Deprecated alias — use cleanup-empty-instantly."""
    cleanup_empty_instantly_cmd(execute=execute)


@app.command("reload")
def reload_cmd() -> None:
    """Clear preset discovery cache (after manual config edits)."""
    invalidate_preset_cache()
    from config_loader import invalidate_preset_registry

    invalidate_preset_registry()
    typer.secho("Preset cache cleared.", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()
