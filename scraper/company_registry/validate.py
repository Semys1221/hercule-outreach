"""Batch validation with SIREN deduplication."""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from typing import Any, Callable

import httpx

from company_registry.config import USER_AGENT, pappers_settings
from company_registry.gate import CompanyGate, build_validator
from company_registry.models import GateVerdict, LegacyVerdict
from company_registry.siret_extract import resolve_identifiers

_LIB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP_DIR = os.path.dirname(_LIB_DIR)
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)
from outreach_data import scraper_output_base  # noqa: E402


def _registry_cache_policy_hash(config: dict[str, Any]) -> str:
    """Short hash so cache invalidates when gate policy changes."""
    parts = [
        str(config.get("PAPPERS_ON_UNKNOWN") or "reject"),
        str(config.get("PAPPERS_MIN_EMPLOYEES", 3)),
        str(config.get("PAPPERS_MAX_EMPLOYEES") or ""),
        str(config.get("PAPPERS_MIN_SCORE", 55)),
        str(config.get("PAPPERS_FAST_MODE", False)),
        str(config.get("PAPPERS_SCORING_ENABLED", True)),
        "|".join(sorted(str(p) for p in (config.get("PAPPERS_NAF_PREFIXES") or []))),
    ]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:12]


def _cache_path_for_config(config: dict[str, Any]) -> str:
    preset = str(config.get("PRESET_ID") or config.get("_preset_id") or "default")
    policy = _registry_cache_policy_hash(config)
    return os.path.join(scraper_output_base(), preset, f"siret_cache_{policy}.json")


def _dedup_groups(rows: list[dict[str, str]]) -> dict[str, list[int]]:
    groups: dict[str, list[int]] = {}
    for idx, row in enumerate(rows):
        site_text = row.get("_website_text") or row.get("_html_text") or ""
        siret, siren, _ = resolve_identifiers(row, site_text)
        company = (row.get("Company") or "").strip().lower()
        city = (row.get("City") or "").strip().lower()
        if siret:
            key = f"id:{siret}"
        elif siren:
            key = f"id:{siren}"
        else:
            key = f"name:{company}|{city}"
        groups.setdefault(key, []).append(idx)
    return groups


async def validate_leads(
    rows: list[dict[str, str]],
    config: dict[str, Any],
    *,
    log_cb: Callable[[str], None] | None = None,
    client: httpx.AsyncClient | None = None,
    validator: CompanyGate | None = None,
    deep_enrich: bool = False,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    settings = pappers_settings(config)
    if not settings["enabled"]:
        return rows, []
    if not rows:
        return [], []

    cache_path = _cache_path_for_config(config)
    gate = validator or build_validator(config, cache_path=cache_path)
    if deep_enrich:
        gate.config.deep_enrich = True

    if log_cb:
        log_cb(
            f"SIRET enrich — {len(rows)} lead(s), min effectif {settings['min_employees']}, "
            f"min score {settings.get('min_score', 55)}, concurrency {settings['concurrency']}"
        )

    semaphore = asyncio.Semaphore(settings["concurrency"])
    groups = _dedup_groups(rows)
    group_verdicts: dict[str, GateVerdict] = {}
    own_client = client is None

    async def _resolve_group(key: str, indices: list[int]) -> None:
        representative = rows[indices[0]]
        async with semaphore:
            verdict = await gate.validate_lead(representative, active_client)
        group_verdicts[key] = verdict

    limits = httpx.Limits(max_connections=80, max_keepalive_connections=40)

    async def _run(active_client: httpx.AsyncClient) -> list[tuple[dict[str, str], GateVerdict]]:
        await asyncio.gather(
            *[_resolve_group(key, indices) for key, indices in groups.items()]
        )
        results: list[tuple[dict[str, str], GateVerdict]] = []
        for key, indices in groups.items():
            verdict = group_verdicts[key]
            for idx in indices:
                results.append((rows[idx], verdict))
        return results

    if own_client:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings["timeout_s"]),
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
            limits=limits,
        ) as active_client:
            results = await _run(active_client)
    else:
        results = await _run(client)

    gate.flush_cache()

    valid: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    for row, verdict in results:
        cleaned = {k: v for k, v in row.items() if not str(k).startswith("_")}
        legacy = verdict.as_legacy()
        enriched = {**cleaned, **legacy.as_lead_fields()}
        if verdict.accepted:
            valid.append(enriched)
        else:
            enriched["Statut_Lead"] = "Non Valide"
            enriched["Enrich_Reason"] = verdict.reason
            rejected.append(enriched)

    if log_cb:
        log_cb(f"SIRET enrich done — {len(valid)} valid, {len(rejected)} rejected")

    # Pass 2: deep enrich unknown effectif rejections when configured
    if config.get("REGISTRY_DEEP_ENRICH") and rejected:
        retry_rows = [
            row for row in rejected
            if row.get("Enrich_Reason") == "REJECT_UNKNOWN_EFFECTIF"
        ]
        if retry_rows:
            if log_cb:
                log_cb(f"Deep enrich pass — retrying {len(retry_rows)} unknown-effectif lead(s)")
            retry_valid, still_rejected = await validate_leads(
                retry_rows,
                config,
                log_cb=log_cb,
                client=client,
                validator=gate,
                deep_enrich=True,
            )
            rejected = [r for r in rejected if r not in retry_rows] + still_rejected
            valid.extend(retry_valid)

    return valid, rejected
