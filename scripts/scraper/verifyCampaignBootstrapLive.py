#!/usr/bin/env python3
"""Live bootstrap audit + mock-lead pipeline flow for scraper campaigns."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import requests
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_DIR = _REPO_ROOT / "lib" / "backend"
_SCRAPER_DIR = _BACKEND_DIR / "streamlit_scraper"
_CLEAN_DIR = _REPO_ROOT / "lib" / "backend" / "streamlit_clean"
_CRM_DIR = _REPO_ROOT / ".no_crm"
_SUBSEQUENCE_DIR = _REPO_ROOT / "satellites" / "subsequence"
_REPLY_DIR = _REPO_ROOT / "lib" / "backend" / "streamlit_reply_agent"
_PROMPTS_DIR = _REPLY_DIR / "prompts"
_OUTPUT_DIR = _SCRAPER_DIR / "output"
_REPORT_PATH = _OUTPUT_DIR / "bootstrap_audit_report.json"

for path in (str(_BACKEND_DIR), str(_REPO_ROOT), str(_SCRAPER_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

load_dotenv(_REPO_ROOT / ".env")
load_dotenv(_CRM_DIR / ".env", override=True)

import importlib.util


def _load_app_module(app_dir: Path, module_name: str):
    module_path = app_dir / f"{module_name}.py"
    app_path = str(app_dir)
    saved_path = sys.path[:]
    saved_modules = {
        name: sys.modules[name]
        for name in ("config", "supabase_repo", "onboarding", "pipeline")
        if name in sys.modules
    }
    for name in saved_modules:
        del sys.modules[name]
    repo_root = str(_REPO_ROOT)
    filtered_path = [p for p in saved_path if os.path.abspath(p) != os.path.abspath(repo_root)]
    sys.path = [app_path] + filtered_path
    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {module_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path = saved_path
        for name, module in saved_modules.items():
            sys.modules[name] = module

from bootstrap.discovery import discover_presets  # noqa: E402
from config_loader import load_config  # noqa: E402
from shared.instantly_client import (  # noqa: E402
    InstantlyClient,
    fetch_leads_from_campaign,
    fetch_leads_from_list,
    get_api_key,
    lead_custom_var,
)

CANONICAL_INSTANTLY_KEYS = (
    "reservation_agence_link",
    "reservation_entreprise_link",
    "confirmation_agence_link",
    "reservation_cif_link",
    "statut",
)

MOCK_COMPANIES: list[tuple[str, str, str]] = [
    ("Cabinet Martin & Associés", "Sophie", "Martin"),
    ("Expertise Dupont SARL", "Jean", "Dupont"),
    ("Fiduciaire Lefèvre", "Marie", "Lefèvre"),
    ("Comptabilité Bernard", "Pierre", "Bernard"),
    ("Audit Moreau Partners", "Claire", "Moreau"),
]

AuditStatus = Literal["OK", "WARN", "FAIL", "DEPRECATED"]

DEPRECATED_PRESETS = frozenset({"comptables", "conseillers_financiers"})
ORPHAN_REPLY_AGENT_CAMPAIGN_ID = "fd0175d2-1d13-4616-b1b8-cc498b41e65d"


@dataclass
class LayerResult:
    ok: bool
    status: AuditStatus
    detail: str = ""


@dataclass
class PresetAudit:
    preset_id: str
    label: str
    niche_group: str
    list_id: str = ""
    campaign_id: str = ""
    subsequence_id: str = ""
    overall: AuditStatus = "FAIL"
    layers: dict[str, LayerResult] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class FlowStageTiming:
    stage: str
    elapsed_s: float
    detail: str = ""
    ok: bool = True


@dataclass
class FlowPilotResult:
    preset_id: str
    campaign_id: str
    list_id: str
    lead_emails: list[str]
    stages: list[FlowStageTiming] = field(default_factory=list)
    ok: bool = False
    errors: list[str] = field(default_factory=list)


def _uuid(value: Any) -> str:
    return str(value or "").strip()


def _status_from_layers(layers: dict[str, LayerResult]) -> AuditStatus:
    if any(layer.status == "FAIL" for layer in layers.values()):
        return "FAIL"
    if any(layer.status == "WARN" for layer in layers.values()):
        return "WARN"
    return "OK"


def _resolve_prompt_paths(preset_id: str, target_type: str = "buyer") -> tuple[Path, Path]:
    buyer = _PROMPTS_DIR / f"{preset_id}_{target_type}.md"
    seller = _PROMPTS_DIR / f"{preset_id}_seller.md"
    return buyer, seller


def _check_links_tables() -> LayerResult:
    try:
        crm_repo = _load_app_module(_CRM_DIR, "supabase_repo")
        client = crm_repo.get_client()
        for table in ("agence", "entreprise"):
            resp = client.table(table).select("id").limit(1).execute()
            if resp.data is None:
                return LayerResult(
                    False,
                    "FAIL",
                    f"Table `{table}` query returned no data handle",
                )
        return LayerResult(True, "OK", "agence + entreprise reachable")
    except Exception as exc:
        return LayerResult(False, "FAIL", f"Supabase links tables: {exc}")


def _check_instantly_resource(
    client: InstantlyClient,
    *,
    kind: str,
    resource_id: str,
) -> LayerResult:
    if not resource_id:
        return LayerResult(False, "FAIL", f"Missing {kind} id")
    try:
        if kind == "list":
            data = client.get_lead_list(resource_id)
        elif kind == "campaign":
            data = client.get_campaign(resource_id)
        elif kind == "subsequence":
            data = client._fetch(f"/subsequences/{resource_id}", method="GET")
        else:
            return LayerResult(False, "FAIL", f"Unknown resource kind {kind}")
        name = str(data.get("name") or data.get("label") or resource_id)
        return LayerResult(True, "OK", f"{kind} exists ({name})")
    except Exception as exc:
        return LayerResult(False, "FAIL", f"Instantly {kind} {resource_id}: {exc}")


def _check_bypass_layer(
    client: InstantlyClient,
    *,
    campaign_id: str,
) -> LayerResult:
    subseq_config = _load_app_module(_SUBSEQUENCE_DIR, "config")
    subseq_repo = _load_app_module(_SUBSEQUENCE_DIR, "supabase_repo")
    subseq_onboarding = _load_app_module(_SUBSEQUENCE_DIR, "onboarding")

    config_row = subseq_repo.get_config(campaign_id)
    templates = subseq_repo.list_templates(campaign_id) if config_row else []
    webhooks = client.list_webhooks()
    target_url = subseq_config.webhook_public_url()
    has_webhook = bool(
        subseq_onboarding.find_campaign_webhook(
            webhooks,
            campaign_id=campaign_id,
            target_url=target_url,
            require_active=True,
        )
    )
    e1_ready = subseq_onboarding.e1_copy_is_ready(templates)
    status = subseq_onboarding.derive_onboarding_status(
        has_config=bool(config_row),
        has_webhook=has_webhook,
        copy_complete=e1_ready,
    )

    if status == "ready":
        return LayerResult(True, "OK", "Bypass bootstrap ready (E1 + webhook)")
    if status == "copy_incomplete" and config_row and has_webhook and e1_ready:
        return LayerResult(
            True,
            "OK",
            "Bypass live — E1 seeded, E2/E3 editable",
        )
    if not config_row:
        return LayerResult(False, "FAIL", "instantly_bypass_config missing")
    if not e1_ready:
        return LayerResult(False, "FAIL", "interested_email1 template empty")
    if not has_webhook:
        secret = subseq_config.webhook_secret()
        hint = "register lead_interested webhook" if secret else "missing webhook secret"
        return LayerResult(False, "FAIL", f"No active lead_interested webhook ({hint})")
    return LayerResult(False, "WARN", f"Bypass status: {status}")


def _check_reply_agent_layer(campaign_id: str, preset_id: str) -> LayerResult:
    reply_onboarding = _load_app_module(_REPLY_DIR, "onboarding")
    reply_repo = _load_app_module(_REPLY_DIR, "supabase_repo")

    config_row = reply_repo.get_config(campaign_id)
    if not config_row:
        return LayerResult(
            False,
            "WARN",
            "ai_reply_agent_config missing — activate in streamlit_reply_agent",
        )

    readiness = reply_onboarding.validate_campaign_readiness(config_row, campaign_id)
    status = reply_onboarding.derive_onboarding_status(config_row, campaign_id)
    niche = str(config_row.get("niche_preset_id") or "")
    if readiness.ready:
        return LayerResult(True, "OK", f"Reply agent live ({status})")
    if niche and niche != preset_id:
        return LayerResult(
            False,
            "WARN",
            f"Reply agent configured for `{niche}` not `{preset_id}` ({readiness.reason})",
        )
    return LayerResult(
        False,
        "WARN",
        f"Reply agent not fully live ({readiness.reason or status})",
    )


def audit_preset(
    preset_id: str,
    meta: Any,
    *,
    client: InstantlyClient,
    links_tables: LayerResult,
) -> PresetAudit:
    config = load_config(preset_id, require_keys=False)
    list_id = _uuid(config.get("INSTANTLY_LIST_ID"))
    campaign_id = _uuid(config.get("INSTANTLY_CAMPAIGN_ID"))
    subsequence_id = _uuid(config.get("INSTANTLY_SUBSEQUENCE_ID"))

    audit = PresetAudit(
        preset_id=preset_id,
        label=meta.label,
        niche_group=meta.niche_group,
        list_id=list_id,
        campaign_id=campaign_id,
        subsequence_id=subsequence_id,
    )

    if preset_id in DEPRECATED_PRESETS:
        audit.layers["deprecated"] = LayerResult(
            True,
            "OK",
            "Legacy preset — Instantly campaign stale, excluded from bootstrap",
        )
        audit.overall = "DEPRECATED"
        return audit

    if not list_id or not campaign_id:
        audit.layers["config"] = LayerResult(
            False,
            "FAIL",
            "INSTANTLY_LIST_ID and/or INSTANTLY_CAMPAIGN_ID missing",
        )
    else:
        audit.layers["config"] = LayerResult(True, "OK", "List + campaign ids present")

    audit.layers["instantly_list"] = _check_instantly_resource(
        client, kind="list", resource_id=list_id
    )
    audit.layers["instantly_campaign"] = _check_instantly_resource(
        client, kind="campaign", resource_id=campaign_id
    )

    audit.layers["bypass"] = _check_bypass_layer(
        client,
        campaign_id=campaign_id,
    )
    if subsequence_id:
        audit.warnings.append(
            "INSTANTLY_SUBSEQUENCE_ID still set — remove Instantly subsequence to avoid duplicate E1"
        )

    buyer_path, seller_path = _resolve_prompt_paths(preset_id)
    if buyer_path.is_file() and seller_path.is_file():
        audit.layers["reply_prompts"] = LayerResult(
            True,
            "OK",
            f"Prompts: {buyer_path.name}, {seller_path.name}",
        )
    else:
        audit.layers["reply_prompts"] = LayerResult(
            False,
            "FAIL",
            f"Missing per-preset prompts ({buyer_path.name}, {seller_path.name})",
        )

    if campaign_id:
        audit.layers["reply_agent"] = _check_reply_agent_layer(campaign_id, preset_id)
    else:
        audit.layers["reply_agent"] = LayerResult(
            False,
            "FAIL",
            "Cannot check reply agent without campaign id",
        )

    audit.layers["links_tables"] = links_tables

    for layer in audit.layers.values():
        if layer.status == "WARN":
            audit.warnings.append(layer.detail)
        if layer.status == "FAIL":
            audit.errors.append(layer.detail)

    audit.overall = _status_from_layers(audit.layers)
    return audit


def run_audit_all() -> dict[str, Any]:
    api_key = get_api_key()
    if not api_key:
        raise SystemExit("INSTANTLY_API_KEY is required")

    client = InstantlyClient(api_key)
    links_tables = _check_links_tables()
    presets = discover_presets(use_cache=True)

    results: list[PresetAudit] = []
    for preset_id in sorted(presets.keys()):
        results.append(
            audit_preset(preset_id, presets[preset_id], client=client, links_tables=links_tables)
        )

    summary = {
        "OK": sum(1 for row in results if row.overall == "OK"),
        "WARN": sum(1 for row in results if row.overall == "WARN"),
        "FAIL": sum(1 for row in results if row.overall == "FAIL"),
        "DEPRECATED": sum(1 for row in results if row.overall == "DEPRECATED"),
    }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "preset_count": len(results),
        "summary": summary,
        "presets": [
            {
                **asdict(row),
                "layers": {name: asdict(layer) for name, layer in row.layers.items()},
            }
            for row in results
        ],
    }

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\nBootstrap audit — {len(results)} presets")
    print(f"  OK: {summary['OK']}  WARN: {summary['WARN']}  FAIL: {summary['FAIL']}  DEPRECATED: {summary['DEPRECATED']}")
    print(f"  Report: {_REPORT_PATH}\n")
    print(f"{'PRESET':<28} {'STATUS':<6} {'CAMPAIGN_ID':<38} NOTES")
    print("-" * 110)
    for row in results:
        notes = row.errors[0] if row.errors else (row.warnings[0] if row.warnings else "")
        print(
            f"{row.preset_id:<28} {row.overall:<6} "
            f"{row.campaign_id[:36]:<38} {notes[:40]}"
        )

    if summary["FAIL"]:
        return report
    return report


def _push_leads_to_list(
    client: InstantlyClient,
    list_id: str,
    leads: list[dict[str, Any]],
) -> dict[str, int]:
    if not leads:
        return {"pushed": 0, "skipped_duplicate": 0, "failed": 0}
    data = client._fetch(
        "/leads/add",
        method="POST",
        body={
            "list_id": list_id.strip(),
            "leads": leads,
            "skip_if_in_campaign": True,
            "skip_if_in_list": False,
        },
    )
    if not isinstance(data, dict):
        return {"pushed": 0, "skipped_duplicate": 0, "failed": len(leads)}
    pushed = int(data.get("leads_uploaded") or 0)
    skipped = int(data.get("skipped_count") or 0)
    failed = max(len(leads) - pushed - skipped, 0)
    return {"pushed": pushed, "skipped_duplicate": skipped, "failed": failed}


def _push_leads_to_campaign_direct(
    client: InstantlyClient,
    campaign_id: str,
    leads: list[dict[str, Any]],
) -> dict[str, int]:
    if not leads:
        return {"pushed": 0, "skipped_duplicate": 0, "failed": 0}
    data = client._fetch(
        "/leads/add",
        method="POST",
        body={
            "campaign_id": campaign_id.strip(),
            "leads": leads,
            "skip_if_in_workspace": False,
        },
    )
    if not isinstance(data, dict):
        return {"pushed": 0, "skipped_duplicate": 0, "failed": len(leads)}
    pushed = int(data.get("leads_uploaded") or 0)
    skipped = int(data.get("skipped_count") or 0)
    failed = max(len(leads) - pushed - skipped, 0)
    return {"pushed": pushed, "skipped_duplicate": skipped, "failed": failed}


def _purge_mock_leads_from_list(
    client: InstantlyClient,
    list_id: str,
    emails: list[str],
) -> int:
    removed = 0
    targets = {email.strip().lower() for email in emails}
    list_leads = fetch_leads_from_list(list_id, max_leads=500)
    for lead in list_leads:
        email = str(lead.get("email") or "").strip().lower()
        lead_id = lead.get("id")
        if email in targets and lead_id:
            try:
                client._fetch(f"/leads/{lead_id}", method="DELETE")
                removed += 1
            except Exception:
                pass
    return removed


def _build_mock_leads(run_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    leads: list[dict[str, Any]] = []
    emails: list[str] = []
    for index, (company, first_name, last_name) in enumerate(MOCK_COMPANIES):
        email = f"pipe.smoke.{run_id}.{index}@gmail.com"
        emails.append(email)
        leads.append(
            {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "company_name": company,
            }
        )
    return leads, emails


def _lead_has_canonical_vars(lead: dict[str, Any]) -> bool:
    return all(lead_custom_var(lead, key) for key in CANONICAL_INSTANTLY_KEYS)


def _lead_custom_variables(lead: dict[str, Any]) -> dict[str, Any]:
    return InstantlyClient.lead_custom_variables(lead)


def _cleanup_test_leads(
    *,
    client: InstantlyClient,
    campaign_id: str,
    list_id: str,
    emails: list[str],
) -> None:
    crm_repo = _load_app_module(_CRM_DIR, "supabase_repo")
    sb = crm_repo.get_client()
    for email in emails:
        normalized = crm_repo.normalize_email(email)
        for table in ("agence", "entreprise"):
            sb.table(table).delete().eq("email", normalized).execute()

        lead = client.find_lead_by_email_in_campaign(campaign_id, normalized)
        if lead and lead.get("id"):
            try:
                client._fetch(f"/leads/{lead['id']}", method="DELETE")
            except Exception:
                pass

        list_leads = fetch_leads_from_list(list_id, max_leads=500)
        for list_lead in list_leads:
            list_email = str(list_lead.get("email") or "").strip().lower()
            if list_email == normalized and list_lead.get("id"):
                try:
                    client._fetch(f"/leads/{list_lead['id']}", method="DELETE")
                except Exception:
                    pass


def _post_interested_webhook(
    *,
    campaign_id: str,
    lead_email: str,
) -> tuple[int, str]:
    subseq_config = _load_app_module(_SUBSEQUENCE_DIR, "config")
    base = os.getenv("WEBHOOK_BASE_URL", "").strip() or subseq_config.app_base_url().rstrip("/")
    secret = subseq_config.webhook_secret()
    url = f"{base}/api/webhooks/instantly"
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "lead_interested",
        "workspace": "00000000-0000-0000-0000-000000000001",
        "campaign_id": campaign_id,
        "campaign_name": "Pipeline smoke",
        "lead_email": lead_email,
        "email_account": "sender@hercule.dev",
        "first_name": "Smoke",
    }
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    return response.status_code, response.text[:500]


def run_flow_pilot(
    preset_id: str,
    *,
    cleanup: bool = True,
) -> FlowPilotResult:
    api_key = get_api_key()
    if not api_key:
        raise SystemExit("INSTANTLY_API_KEY is required")

    config = load_config(preset_id, require_keys=False)
    list_id = _uuid(config.get("INSTANTLY_LIST_ID"))
    campaign_id = _uuid(config.get("INSTANTLY_CAMPAIGN_ID"))
    if not list_id or not campaign_id:
        raise SystemExit(f"Preset {preset_id} missing list or campaign id")

    client = InstantlyClient(api_key)
    run_id = uuid.uuid4().hex[:8]
    mock_leads, emails = _build_mock_leads(run_id)
    result = FlowPilotResult(
        preset_id=preset_id,
        campaign_id=campaign_id,
        list_id=list_id,
        lead_emails=emails,
    )

    def record(stage: str, started: float, detail: str, ok: bool = True) -> None:
        elapsed = time.monotonic() - started
        result.stages.append(
            FlowStageTiming(stage=stage, elapsed_s=round(elapsed, 2), detail=detail, ok=ok)
        )
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] {stage}: {elapsed:.2f}s — {detail}")

    print(f"\nFlow pilot — preset={preset_id} run_id={run_id}")

    t0 = time.monotonic()
    push_stats = _push_leads_to_list(client, list_id, mock_leads)
    detail = (
        f"pushed={push_stats['pushed']} skipped={push_stats['skipped_duplicate']} "
        f"failed={push_stats['failed']}"
    )
    ok = push_stats["pushed"] + push_stats["skipped_duplicate"] >= len(mock_leads)
    record("list_push", t0, detail, ok=ok)
    if not ok:
        result.errors.append(f"List push incomplete: {detail}")

    t0 = time.monotonic()
    fetched = fetch_leads_from_list(list_id, max_leads=200)
    fetched_emails = {
        str(lead.get("email") or "").strip().lower() for lead in fetched
    }
    found = sum(1 for email in emails if email.lower() in fetched_emails)
    record("list_fetch", t0, f"found {found}/{len(emails)} mock leads in list", ok=found >= len(emails))

    t0 = time.monotonic()
    removed = _purge_mock_leads_from_list(client, list_id, emails)
    record(
        "list_purge",
        t0,
        f"removed {removed}/{len(emails)} mock leads from list (mirrors Full Clean)",
        ok=True,
    )

    campaign_leads = [
        {
            "email": lead["email"],
            "first_name": lead.get("first_name"),
            "last_name": lead.get("last_name"),
            "company_name": lead.get("company_name"),
        }
        for lead in mock_leads
    ]

    t0 = time.monotonic()
    push_campaign = _push_leads_to_campaign_direct(client, campaign_id, campaign_leads)
    detail = (
        f"pushed={push_campaign['pushed']} skipped={push_campaign['skipped_duplicate']} "
        f"failed={push_campaign['failed']}"
    )
    ok = push_campaign["pushed"] + push_campaign["skipped_duplicate"] >= len(mock_leads)
    record("clean_to_campaign", t0, detail, ok=ok)

    t0 = time.monotonic()
    time.sleep(2)
    selected = fetch_leads_from_campaign(campaign_id, max_leads=500)
    selected = [
        lead
        for lead in selected
        if str(lead.get("email") or "").strip().lower() in {e.lower() for e in emails}
    ]
    if len(selected) < len(mock_leads):
        result.errors.append(
            f"Only {len(selected)}/{len(mock_leads)} leads found in campaign before provision"
        )

    crm_pipeline = _load_app_module(_CRM_DIR, "pipeline")
    crm_repo = _load_app_module(_CRM_DIR, "supabase_repo")

    provision = crm_pipeline.provision_from_instantly_leads(
        category="agence",
        campaign_id=campaign_id,
        selected_leads=selected,
        instantly=client,
        supabase=crm_repo.get_client(),
        patch_instantly=True,
    )
    detail = (
        f"created={provision.created} updated={provision.updated} "
        f"patched={provision.patched} failed={provision.failed}"
    )
    ok = (provision.created + provision.updated) >= len(mock_leads) and provision.patched >= len(
        mock_leads
    )
    record("links_provision", t0, detail, ok=ok)
    if provision.errors:
        result.errors.extend(provision.errors[:5])

    t0 = time.monotonic()
    vars_ok = 0
    for email in emails:
        lead = client.find_lead_by_email_in_campaign(campaign_id, email)
        if not lead:
            continue
        lead_id = str(lead.get("id") or "")
        if lead_id:
            try:
                lead = client.get_lead(lead_id)
            except Exception:
                pass
        if _lead_has_canonical_vars(lead):
            vars_ok += 1
    record(
        "instantly_vars",
        t0,
        f"{vars_ok}/{len(emails)} leads have canonical custom_variables",
        ok=vars_ok >= len(emails),
    )

    t0 = time.monotonic()
    sb_ok = 0
    sb_client = crm_repo.get_client()
    for email in emails:
        if crm_repo.find_by_email(sb_client, email):
            sb_ok += 1
    record(
        "supabase_rows",
        t0,
        f"{sb_ok}/{len(emails)} emails found in agence/entreprise",
        ok=sb_ok >= len(emails),
    )

    t0 = time.monotonic()
    status_code, body = _post_interested_webhook(
        campaign_id=campaign_id,
        lead_email=emails[0],
    )
    webhook_ok = status_code < 500
    record(
        "subsequence_webhook",
        t0,
        f"HTTP {status_code}: {body[:120]}",
        ok=webhook_ok,
    )

    t0 = time.monotonic()
    reply_layer = _check_reply_agent_layer(campaign_id, preset_id)
    record("reply_agent", t0, reply_layer.detail, ok=reply_layer.status != "FAIL")

    list_fetch_s = next((s.elapsed_s for s in result.stages if s.stage == "list_fetch"), 0)
    list_push_s = next((s.elapsed_s for s in result.stages if s.stage == "list_push"), 0)
    links_s = next((s.elapsed_s for s in result.stages if s.stage == "links_provision"), 0)
    if list_push_s + list_fetch_s > 30:
        result.errors.append(
            f"List push+fetch slow: {list_push_s + list_fetch_s:.1f}s > 30s threshold"
        )
    if links_s > 60:
        result.errors.append(f"Links provision slow: {links_s:.1f}s > 60s threshold")

    core_stages = {
        "list_push",
        "list_fetch",
        "clean_to_campaign",
        "links_provision",
        "supabase_rows",
        "instantly_vars",
    }
    result.ok = not result.errors and all(
        stage.ok for stage in result.stages if stage.stage in core_stages
    )

    if cleanup:
        print("  Cleaning up test leads…")
        _cleanup_test_leads(
            client=client,
            campaign_id=campaign_id,
            list_id=list_id,
            emails=emails,
        )

    print(
        f"\nFlow pilot {'PASSED' if result.ok else 'FAILED'} "
        f"— {len(result.errors)} error(s)"
    )
    for err in result.errors:
        print(f"  - {err}")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Campaign bootstrap live verification")
    parser.add_argument(
        "--audit-all",
        action="store_true",
        help="Audit all scraper presets (Instantly + Supabase bootstrap)",
    )
    parser.add_argument(
        "--flow-pilot",
        action="store_true",
        help="Run mock-lead pipeline flow on one preset",
    )
    parser.add_argument(
        "--preset",
        default="expertise_comptable",
        help="Preset for --flow-pilot (default: expertise_comptable)",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        default=True,
        help="Remove mock leads after flow pilot (default: true)",
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_false",
        dest="cleanup",
        help="Keep mock leads after flow pilot",
    )
    args = parser.parse_args()

    if not args.audit_all and not args.flow_pilot:
        parser.error("Specify --audit-all and/or --flow-pilot")

    exit_code = 0

    if args.audit_all:
        report = run_audit_all()
        if report["summary"]["FAIL"]:
            exit_code = 1

    if args.flow_pilot:
        flow = run_flow_pilot(args.preset, cleanup=args.cleanup)
        if not flow.ok:
            exit_code = 1

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
