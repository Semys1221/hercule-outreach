"""Backfill Instantly custom_variables (segmentation columns) for existing leads."""

from __future__ import annotations

import asyncio
import csv
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from company_registry.config import USER_AGENT, pappers_settings
from company_registry.gate import CompanyGate, build_validator
from company_registry.models import CompanyRecord, GateVerdict
from company_registry.segmentation import enrich_lead_segmentation
from config_loader import load_config
from core_logic import output_paths
from instantly_client import (
    ANALYTICS_CUSTOM_VAR_KEYS,
    CSV_COLUMNS,
    _normalize_email,
    _read_email,
    custom_variables_fully_provisioned,
    paginate_campaign_leads,
    paginate_list_leads,
    patch_body_from_row,
    patch_lead,
)
from outreach_data import scraper_output_base

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STATE_PATH = os.path.join(_LIB_DIR, "output", "backfill_reception_state.json")
DEFAULT_REPORT_PATH = os.path.join(_LIB_DIR, "output", "backfill_reception_report.json")


def paths_for_scope(scope: dict[str, str]) -> tuple[str, str]:
    """Return (state_path, report_path) for a list or campaign scope."""
    if "list_id" in scope:
        scope_id = scope["list_id"].strip()
        prefix = "backfill_list"
    elif "campaign" in scope:
        scope_id = scope["campaign"].strip()
        prefix = "backfill_campaign"
    else:
        raise ValueError("scope must include list_id or campaign")
    safe_id = scope_id.replace("/", "_")
    state_path = os.path.join(_LIB_DIR, "output", f"{prefix}_{safe_id}_state.json")
    report_path = os.path.join(_LIB_DIR, "output", f"{prefix}_{safe_id}_report.json")
    return state_path, report_path


def scope_label(scope: dict[str, str]) -> str:
    if "list_id" in scope:
        return f"list {scope['list_id'].strip()}"
    if "campaign" in scope:
        return f"campaign {scope['campaign'].strip()}"
    return "unknown scope"


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _row_completeness(row: dict[str, Any]) -> int:
    return sum(1 for value in row.values() if _safe_str(value))


def _cache_path_for_preset(preset_id: str, data_root: str | None = None) -> str:
    base = data_root or scraper_output_base()
    return os.path.join(base, preset_id, "siret_cache.json")


def load_csv_index(
    preset_ids: list[str],
    *,
    data_root: str | None = None,
) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """Merge preset CSV rows by email; prefer the most complete duplicate."""
    base = data_root or scraper_output_base()
    index: dict[str, dict[str, str]] = {}
    email_preset: dict[str, str] = {}

    for preset_id in preset_ids:
        csv_path = os.path.join(base, preset_id, "outscraper_leads.csv")
        if not os.path.isfile(csv_path):
            continue
        with open(csv_path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for raw in reader:
                email = _normalize_email(_safe_str(raw.get("Email")))
                if not email:
                    continue
                row = {_safe_str(key): _safe_str(value) for key, value in raw.items()}
                row["Email"] = email
                existing = index.get(email)
                if existing is None or _row_completeness(row) > _row_completeness(existing):
                    index[email] = row
                    email_preset[email] = preset_id

    return index, email_preset


def csv_row_to_company_record(row: dict[str, Any]) -> CompanyRecord:
    effectif_raw = _safe_str(row.get("Effectif"))
    tranche = _safe_str(row.get("TrancheEffectif"))
    effectif_min: int | None = None
    if effectif_raw:
        try:
            effectif_min = int(effectif_raw.split()[0])
        except ValueError:
            effectif_min = None

    nb_etab_raw = _safe_str(row.get("NbEtablissements"))
    nb_etablissements = 0
    if nb_etab_raw:
        try:
            nb_etablissements = int(nb_etab_raw)
        except ValueError:
            nb_etablissements = 0

    ei_raw = _safe_str(row.get("EstEntrepreneurIndividuel")).lower()
    est_ei = ei_raw in {"oui", "true", "1", "yes"}

    return CompanyRecord(
        siren=_safe_str(row.get("Siren")),
        siret=_safe_str(row.get("Siret")),
        tranche_effectif=tranche,
        effectif_min=effectif_min,
        effectif_label=effectif_raw,
        chiffre_affaires=_safe_str(row.get("ChiffreAffaires")),
        annee_creation=_safe_str(row.get("AnneeCreation")),
        code_naf=_safe_str(row.get("Naf")),
        forme_juridique=_safe_str(row.get("FormeJuridique")),
        denomination=_safe_str(row.get("Company")),
        commune=_safe_str(row.get("City")),
        source=_safe_str(row.get("RegistrySource")),
        dirigeant_prenom=_safe_str(row.get("DirigeantPrenom")),
        dirigeant_nom=_safe_str(row.get("DirigeantNom")),
        dirigeant_qualite=_safe_str(row.get("DirigeantQualite")),
        resultat_net=_safe_str(row.get("ResultatNet")),
        est_entrepreneur_individuel=est_ei,
        categorie_entreprise=_safe_str(row.get("CategorieEntreprise")),
        nb_etablissements=nb_etablissements,
    )


def instantly_lead_to_csv_row(item: dict[str, Any]) -> dict[str, str]:
    email = _read_email(item)
    custom_vars = item.get("custom_variables")
    if not isinstance(custom_vars, dict):
        payload = item.get("payload")
        custom_vars = payload if isinstance(payload, dict) else {}

    return {
        "Email": email,
        "Company": _safe_str(item.get("company_name")),
        "Website": _safe_str(item.get("website")),
        "Phone": _safe_str(item.get("phone") or custom_vars.get("phone")),
        "City": _safe_str(custom_vars.get("city")),
        "Service": _safe_str(custom_vars.get("service")),
        "Niche": _safe_str(custom_vars.get("niche")),
        "Subniche": _safe_str(custom_vars.get("subniche")),
        "Type": _safe_str(custom_vars.get("type")),
        "Category": _safe_str(custom_vars.get("category")),
        "Subtypes": _safe_str(custom_vars.get("subtypes")),
        "Siret": _safe_str(custom_vars.get("siret")),
        "Siren": _safe_str(custom_vars.get("siren")),
        "Effectif": _safe_str(custom_vars.get("effectif")),
        "TrancheEffectif": _safe_str(custom_vars.get("tranche_effectif")),
        "Naf": _safe_str(custom_vars.get("naf")),
        "FormeJuridique": _safe_str(custom_vars.get("forme_juridique")),
        "AnneeCreation": _safe_str(custom_vars.get("annee_creation")),
        "ChiffreAffaires": _safe_str(custom_vars.get("chiffre_affaires")),
        "TailleEntreprise": _safe_str(custom_vars.get("taille_entreprise")),
        "LeadScore": _safe_str(custom_vars.get("lead_score")),
        "Phone": _safe_str(custom_vars.get("phone") or item.get("phone")),
        "Rating": _safe_str(custom_vars.get("rating")),
        "ReviewsCount": _safe_str(custom_vars.get("reviews_count")),
        "DirigeantPrenom": _safe_str(custom_vars.get("dirigeant_prenom")),
        "DirigeantNom": _safe_str(custom_vars.get("dirigeant_nom")),
        "DirigeantQualite": _safe_str(custom_vars.get("dirigeant_qualite")),
        "ResultatNet": _safe_str(custom_vars.get("resultat_net")),
        "EstEntrepreneurIndividuel": _safe_str(custom_vars.get("est_entrepreneur_individuel")),
        "CategorieEntreprise": _safe_str(custom_vars.get("categorie_entreprise")),
        "NbEtablissements": _safe_str(custom_vars.get("nb_etablissements")),
        "AngleIr": _safe_str(custom_vars.get("angle_ir")),
        "AngleCharges": _safe_str(custom_vars.get("angle_charges")),
        "AngleFraisKm": _safe_str(custom_vars.get("angle_frais_km")),
        "AngleCotisations": _safe_str(custom_vars.get("angle_cotisations")),
        "EconomieEstimee": _safe_str(custom_vars.get("economie_estimee")),
        "DejaExpertComptable": _safe_str(custom_vars.get("deja_expert_comptable")),
        "OutilComptaDetecte": _safe_str(custom_vars.get("outil_compta_detecte")),
    }


def build_enriched_row(csv_row: dict[str, Any], verdict: GateVerdict) -> dict[str, str]:
    cleaned = {
        key: _safe_str(value)
        for key, value in csv_row.items()
        if not str(key).startswith("_")
    }
    registry_fields = verdict.as_lead_fields()
    merged = {**cleaned, **registry_fields}
    for key, value in cleaned.items():
        if value and not merged.get(key):
            merged[key] = value
    merged.update(enrich_lead_segmentation(verdict.company, csv_row))
    merged["Email"] = _normalize_email(merged.get("Email", ""))
    return merged


def should_skip_lead(
    custom_variables: dict[str, Any] | None,
    *,
    force: bool = False,
    keys: tuple[str, ...] = ANALYTICS_CUSTOM_VAR_KEYS,
) -> bool:
    if force:
        return False
    return custom_variables_fully_provisioned(custom_variables, keys=keys)


async def enrich_row_from_registry(
    row: dict[str, str],
    gate: CompanyGate,
    client: httpx.AsyncClient,
) -> GateVerdict:
    return await gate.validate_lead(row, client)


def _load_checkpoint(path: str) -> set[str]:
    if not os.path.isfile(path):
        return set()
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    processed = data.get("processed_emails") or []
    return {_normalize_email(str(email)) for email in processed if email}


def _save_checkpoint(path: str, processed_emails: set[str], meta: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "processed_emails": sorted(processed_emails),
        **meta,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def update_preset_csvs(
    preset_ids: list[str],
    enriched_by_email: dict[str, dict[str, str]],
    *,
    data_root: str | None = None,
    log_cb: Callable[[str], None] | None = None,
) -> int:
    if not enriched_by_email:
        return 0

    base = data_root or scraper_output_base()
    updated_rows = 0

    for preset_id in preset_ids:
        csv_path = os.path.join(base, preset_id, "outscraper_leads.csv")
        if not os.path.isfile(csv_path):
            continue

        with open(csv_path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)

        changed = False
        for row in rows:
            email = _normalize_email(_safe_str(row.get("Email")))
            enriched = enriched_by_email.get(email)
            if not enriched:
                continue
            for column in CSV_COLUMNS:
                value = enriched.get(column, "")
                if value:
                    row[column] = value
            changed = True
            updated_rows += 1

        if not changed:
            continue

        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        with open(csv_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({column: _safe_str(row.get(column)) for column in CSV_COLUMNS})

        if log_cb:
            log_cb(f"Updated CSV → {csv_path}")

    return updated_rows

async def backfill_leads(
    api_key: str,
    scope: dict[str, str],
    preset_ids: list[str],
    *,
    dry_run: bool = True,
    force: bool = False,
    limit: int = 0,
    concurrency: int = 25,
    registry_concurrency: int = 50,
    data_root: str | None = None,
    state_path: str | None = None,
    report_path: str | None = None,
    log_cb: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    def _log(msg: str) -> None:
        if log_cb:
            log_cb(msg)

    started = time.time()
    scope = {key: value.strip() for key, value in scope.items() if value and str(value).strip()}
    if "list_id" not in scope and "campaign" not in scope:
        raise ValueError("scope must include list_id or campaign")

    preset_ids = [preset.strip() for preset in preset_ids if preset.strip()]
    if not preset_ids:
        raise ValueError("At least one preset id is required")

    default_state, default_report = paths_for_scope(scope)
    state_path = state_path or default_state
    report_path = report_path or default_report

    primary_preset = preset_ids[0]
    config = load_config(primary_preset)
    settings = pappers_settings(config)
    if not settings["enabled"]:
        raise RuntimeError(f"Registry enrichment disabled for preset {primary_preset}")

    csv_index, email_preset = load_csv_index(preset_ids, data_root=data_root)
    _log(f"CSV index: {len(csv_index)} email(s) from {', '.join(preset_ids)}")

    processed_emails = _load_checkpoint(state_path)
    if processed_emails:
        _log(f"Checkpoint: {len(processed_emails)} email(s) already processed")

    gates: dict[str, CompanyGate] = {}
    for preset_id in preset_ids:
        cache_path = _cache_path_for_preset(preset_id, data_root)
        preset_config = load_config(preset_id)
        gates[preset_id] = build_validator(preset_config, cache_path=cache_path)

    on_progress = lambda count: _log(f"  fetched {count} Instantly lead(s)...")
    if "list_id" in scope:
        leads = paginate_list_leads(api_key, scope["list_id"], on_progress=on_progress)
    else:
        leads = paginate_campaign_leads(api_key, scope["campaign"], on_progress=on_progress)
    _log(f"Instantly {scope_label(scope)}: {len(leads)} lead(s)")

    patch_sem = asyncio.Semaphore(max(concurrency, 1))
    registry_sem = asyncio.Semaphore(max(registry_concurrency, 1))
    limits = httpx.Limits(max_connections=80, max_keepalive_connections=40)

    stats = {
        "patched": 0,
        "skipped": 0,
        "dry_run_count": 0,
        "failed": 0,
        "no_csv_match": 0,
        "sample_patches": [],
    }
    enriched_by_email: dict[str, dict[str, str]] = {}
    errors: list[dict[str, str]] = []

    async def _process_lead(
        item: dict[str, Any],
        client: httpx.AsyncClient,
    ) -> None:
        email = _read_email(item)
        lead_id = str(item.get("id") or "").strip()
        if not email or not lead_id:
            return
        if email in processed_emails:
            stats["skipped"] += 1
            return

        custom_vars = item.get("custom_variables")
        if not isinstance(custom_vars, dict):
            payload = item.get("payload")
            custom_vars = payload if isinstance(payload, dict) else {}

        if should_skip_lead(custom_vars, force=force):
            stats["skipped"] += 1
            processed_emails.add(email)
            return

        csv_row = csv_index.get(email)
        if csv_row is None:
            csv_row = instantly_lead_to_csv_row(item)
            stats["no_csv_match"] += 1
        else:
            csv_row = dict(csv_row)

        preset_for_row = email_preset.get(email, primary_preset)
        gate = gates[preset_for_row]

        async with registry_sem:
            verdict = await enrich_row_from_registry(csv_row, gate, client)

        enriched = build_enriched_row(csv_row, verdict)
        enriched_by_email[email] = enriched
        patch_body = patch_body_from_row(enriched)

        if dry_run:
            stats["dry_run_count"] += 1
            if len(stats["sample_patches"]) < 5:
                stats["sample_patches"].append(
                    {"email": email, "lead_id": lead_id, "patch_body": patch_body}
                )
            return

        try:
            async with patch_sem:
                await asyncio.to_thread(patch_lead, api_key, lead_id, patch_body)
            stats["patched"] += 1
            processed_emails.add(email)
        except Exception as exc:  # noqa: BLE001
            stats["failed"] += 1
            errors.append({"email": email, "lead_id": lead_id, "error": str(exc)})

    candidates = leads[:limit] if limit > 0 else leads

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(settings["timeout_s"]),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
        limits=limits,
    ) as client:
        await asyncio.gather(*[_process_lead(item, client) for item in candidates])

    for gate in gates.values():
        gate.flush_cache()

    csv_updated = 0
    if not dry_run and enriched_by_email:
        csv_updated = update_preset_csvs(
            preset_ids,
            enriched_by_email,
            data_root=data_root,
            log_cb=_log,
        )

    if not dry_run:
        _save_checkpoint(
            state_path,
            processed_emails,
            {
                "scope": scope,
                "dry_run": dry_run,
                "force": force,
                "patched": stats["patched"],
                "skipped": stats["skipped"],
                "failed": stats["failed"],
            },
        )

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scope": scope,
        "preset_ids": preset_ids,
        "dry_run": dry_run,
        "force": force,
        "limit": limit,
        "concurrency": concurrency,
        "instantly_total": len(leads),
        "processed": len(candidates),
        "csv_index_size": len(csv_index),
        "csv_rows_updated": csv_updated,
        "duration_s": round(time.time() - started, 2),
        "errors": errors[:50],
        **stats,
    }

    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    _log(f"Report → {report_path}")

    return report


async def backfill_list(
    api_key: str,
    list_id: str,
    preset_ids: list[str],
    **kwargs: Any,
) -> dict[str, Any]:
    return await backfill_leads(
        api_key,
        {"list_id": list_id.strip()},
        preset_ids,
        **kwargs,
    )


async def backfill_campaign(
    api_key: str,
    campaign_id: str,
    preset_ids: list[str],
    **kwargs: Any,
) -> dict[str, Any]:
    return await backfill_leads(
        api_key,
        {"campaign": campaign_id.strip()},
        preset_ids,
        **kwargs,
    )
