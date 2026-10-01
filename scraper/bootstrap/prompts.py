"""Interactive wizard for creating scraper presets."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import typer

from bootstrap.discovery import discover_presets, invalidate_preset_cache, preset_config_path
from bootstrap.template import render_preset_config
from bootstrap.validators import (
    parse_instantly_uuid,
    parse_keyword_list,
    validate_preset_id,
    validate_preset_runtime,
)

TUNING_KEYS = (
    "INSTANTLY_PUSH_EVERY",
    "ENRICH_ENABLED",
    "ENRICH_BATCH_SIZE",
    "ENRICH_CONCURRENCY",
    "ENRICH_TIMEOUT_MS",
    "OUTSCRAPER_BATCH_SIZE",
    "OUTSCRAPER_CONCURRENCY",
    "OUTSCRAPER_LIMIT_PER_QUERY",
    "OUTSCRAPER_POLL_INITIAL_S",
    "OUTSCRAPER_POLL_INTERVAL_S",
    "OUTSCRAPER_POLL_SLOW_S",
    "OUTSCRAPER_POLL_TIMEOUT_S",
    "OUTSCRAPER_TOTAL_LIMIT_BUFFER",
    "EXCLUDE_DOMAINS",
    "PAPPERS_ENABLED",
    "PAPPERS_MIN_EMPLOYEES",
    "PAPPERS_MIN_SCORE",
    "PAPPERS_SCORING_ENABLED",
    "PAPPERS_ON_UNKNOWN",
    "PAPPERS_CONCURRENCY",
    "PAPPERS_NAF_PREFIXES",
    "SIRENE_INDEX_ENABLED",
    "SIRENE_INDEX_PATH",
    "REGISTRY_DEEP_ENRICH",
    "REJECT_HOLDINGS",
    "NICHE_METADATA",
)


@dataclass
class CreatePresetInput:
    preset_id: str
    label: str
    list_id: str
    campaign_id: str
    target_leads: int
    copy_from: str
    keywords: list[str]
    expansion_keywords: list[str]
    enrich_included: list[str]
    enrich_hard_excluded: list[str]
    enrich_soft_excluded: list[str]
    service_default: str
    service_rules: list[dict[str, Any]]


def _read_multiline_keywords(prompt: str) -> list[str]:
    typer.echo(prompt)
    typer.echo("(Enter keywords separated by commas, or one per line. Empty line to finish.)")
    lines: list[str] = []
    while True:
        line = typer.prompt(">", default="", show_default=False)
        if not line.strip():
            break
        lines.append(line)
    return parse_keyword_list("\n".join(lines))


def _load_tuning_from_preset(copy_from: str) -> dict[str, Any]:
    from config_loader import load_config

    source = load_config(copy_from, require_keys=False)
    tuning: dict[str, Any] = {}
    for key in TUNING_KEYS:
        if key in source:
            tuning[key] = source[key]
    return tuning


def _default_tuning() -> dict[str, Any]:
    return {
        "INSTANTLY_PUSH_EVERY": 100,
        "ENRICH_ENABLED": False,
        "ENRICH_BATCH_SIZE": 50,
        "ENRICH_CONCURRENCY": 20,
        "ENRICH_TIMEOUT_MS": 10000,
        "OUTSCRAPER_BATCH_SIZE": 200,
        "OUTSCRAPER_CONCURRENCY": 6,
        "OUTSCRAPER_LIMIT_PER_QUERY": 30,
        "OUTSCRAPER_POLL_INITIAL_S": 45,
        "OUTSCRAPER_POLL_INTERVAL_S": 5,
        "OUTSCRAPER_POLL_SLOW_S": 10,
        "OUTSCRAPER_POLL_TIMEOUT_S": 600,
        "OUTSCRAPER_TOTAL_LIMIT_BUFFER": 8,
        "EXCLUDE_DOMAINS": [
            "duckduckgo.com",
            "google.com",
            "google.fr",
            "facebook.com",
            "instagram.com",
            "linkedin.com",
            "youtube.com",
            "pinterest.com",
            "tiktok.com",
            "societe.com",
            "pagesjaunes.fr",
        ],
        "PAPPERS_ENABLED": False,
        "PAPPERS_MIN_EMPLOYEES": 3,
        "PAPPERS_MIN_SCORE": 55,
        "PAPPERS_SCORING_ENABLED": True,
        "PAPPERS_ON_UNKNOWN": "reject",
        "PAPPERS_CONCURRENCY": 50,
        "PAPPERS_NAF_PREFIXES": [],
        "SIRENE_INDEX_ENABLED": True,
        "SIRENE_INDEX_PATH": "data/sirene.db",
        "REGISTRY_DEEP_ENRICH": False,
        "REJECT_HOLDINGS": True,
        "NICHE_METADATA": {
            "angle": "",
            "valeur_client": "",
            "effectif_cible": "10+ salariés",
        },
    }


def run_create_wizard() -> CreatePresetInput:
    existing = discover_presets(use_cache=True)

    raw_id = typer.prompt("Preset ID (snake_case, e.g. conseillers_financiers)")
    try:
        preset_id = validate_preset_id(raw_id)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if preset_id in existing:
        raise typer.BadParameter(f"Preset {preset_id!r} already exists.")

    label = typer.prompt("UI label", default=preset_id.replace("_", " ").title() + " (France)").strip()
    if not label:
        raise typer.BadParameter("Label cannot be empty.")

    list_raw = typer.prompt("Instantly list ID or contacts URL")
    try:
        list_id = parse_instantly_uuid(list_raw, kind="list ID")
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    campaign_raw = typer.prompt("Instantly campaign ID or URL (optional)", default="")
    campaign_id = ""
    if campaign_raw.strip():
        try:
            campaign_id = parse_instantly_uuid(campaign_raw, kind="campaign ID")
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc

    target_leads = typer.prompt("Target Instantly pushed leads", default=5000, type=int)
    if target_leads <= 0:
        raise typer.BadParameter("Target leads must be positive.")

    copy_from = ""
    if existing:
        choices = ", ".join(sorted(existing.keys()))
        copy_from = typer.prompt(
            f"Copy Outscraper/enrich tuning from preset (optional)",
            default="biggy_agency" if "biggy_agency" in existing else "",
        ).strip()
        if copy_from and copy_from not in existing:
            raise typer.BadParameter(f"Unknown preset {copy_from!r}. Available: {choices}")

    typer.echo("\n--- Outscraper keywords (pass 0) ---")
    keywords = _read_multiline_keywords("Enter scrape keywords:")
    if not keywords:
        raise typer.BadParameter("At least one scrape keyword is required.")

    typer.echo("\n--- Expansion keywords (pass 1) ---")
    expansion_keywords = _read_multiline_keywords("Enter expansion keywords (optional):")

    typer.echo("\n--- Website enrich: included keywords ---")
    enrich_included = _read_multiline_keywords("Keywords that must appear on the website:")
    if not enrich_included:
        raise typer.BadParameter("At least one enrich included keyword is required.")

    typer.echo("\n--- Website enrich: hard excluded ---")
    enrich_hard = _read_multiline_keywords("Hard exclusions (optional):")

    typer.echo("\n--- Website enrich: soft excluded ---")
    enrich_soft = _read_multiline_keywords("Soft exclusions (optional):")

    service_default = "Marketing Digital"
    service_rules: list[dict[str, Any]] = []
    if copy_from:
        from config_loader import load_config

        source = load_config(copy_from, require_keys=False)
        service_default = str(source.get("SERVICE_DEFAULT") or service_default)
        service_rules = [
            dict(rule)
            for rule in (source.get("SERVICE_RULES") or [])
            if isinstance(rule, dict)
        ]
    else:
        service_default = typer.prompt("Default Service label", default=service_default).strip()
        if not service_default:
            raise typer.BadParameter("SERVICE_DEFAULT cannot be empty.")

    return CreatePresetInput(
        preset_id=preset_id,
        label=label,
        list_id=list_id,
        campaign_id=campaign_id,
        target_leads=target_leads,
        copy_from=copy_from,
        keywords=keywords,
        expansion_keywords=expansion_keywords,
        enrich_included=enrich_included,
        enrich_hard_excluded=enrich_hard,
        enrich_soft_excluded=enrich_soft,
        service_default=service_default,
        service_rules=service_rules,
    )


def write_preset_file(data: CreatePresetInput) -> str:
    if data.copy_from:
        tuning = _load_tuning_from_preset(data.copy_from)
    else:
        tuning = _default_tuning()

    content = render_preset_config(
        preset_id=data.preset_id,
        label=data.label,
        list_id=data.list_id,
        campaign_id=data.campaign_id,
        target_leads=data.target_leads,
        keywords=data.keywords,
        expansion_keywords=data.expansion_keywords,
        enrich_included=data.enrich_included,
        enrich_hard_excluded=data.enrich_hard_excluded,
        enrich_soft_excluded=data.enrich_soft_excluded,
        service_default=data.service_default,
        service_rules=data.service_rules,
        tuning=tuning,
    )

    path = preset_config_path(data.preset_id)
    if os.path.isfile(path):
        raise typer.BadParameter(f"Config file already exists: {path}")

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    invalidate_preset_cache()
    from config_loader import invalidate_preset_registry

    invalidate_preset_registry()
    return path


def confirm_and_create(data: CreatePresetInput) -> str:
    typer.echo("\n--- Summary ---")
    typer.echo(f"  Preset ID:     {data.preset_id}")
    typer.echo(f"  Label:         {data.label}")
    typer.echo(f"  List ID:       {data.list_id}")
    typer.echo(f"  Campaign ID:   {data.campaign_id or '(none)'}")
    typer.echo(f"  Target leads:  {data.target_leads:,}")
    typer.echo(f"  Copy tuning:   {data.copy_from or '(defaults)'}")
    typer.echo(f"  Keywords:      {len(data.keywords)} pass-0, {len(data.expansion_keywords)} expansion")
    typer.echo(
        f"  Enrich:        {len(data.enrich_included)} included, "
        f"{len(data.enrich_hard_excluded)} hard, {len(data.enrich_soft_excluded)} soft"
    )
    typer.echo(f"  Service:       default={data.service_default!r}, {len(data.service_rules)} rule(s)")
    typer.echo(f"  Output file:   {preset_config_path(data.preset_id)}")

    if not typer.confirm("Create this preset?", default=True):
        raise typer.Abort()

    path = write_preset_file(data)
    typer.secho(f"Created {path}", fg=typer.colors.GREEN)

    try:
        import sys
        from pathlib import Path

        from repo_paths import reply_agent_app

        reply_agent_dir = reply_agent_app()
        if str(reply_agent_dir) not in sys.path:
            sys.path.insert(0, str(reply_agent_dir))
        from prompt_scaffold import scaffold_ai_reply_prompts

        prompt_paths = scaffold_ai_reply_prompts(data.preset_id, data.label)
        for prompt_path in prompt_paths:
            typer.secho(f"Created AI prompt {prompt_path}", fg=typer.colors.GREEN)
    except Exception as exc:
        typer.secho(
            f"Warning: could not scaffold AI reply prompts: {exc}",
            fg=typer.colors.YELLOW,
        )

    result = validate_preset_runtime(data.preset_id, dry_run=True)
    if result.ok:
        typer.secho("Validation passed.", fg=typer.colors.GREEN)
    else:
        for err in result.errors:
            typer.secho(f"  ERROR: {err}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.echo("\nNext steps:")
    typer.echo(f"  python main.py dry-run --preset {data.preset_id}")
    typer.echo(f"  python main.py scrape --preset {data.preset_id} --target {data.target_leads} --push-instantly")
    return path
