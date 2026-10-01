"""Bootstrap E1/E2/E3 bypass + reply-agent prompts when a campaign is linked."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from bootstrap.discovery import discover_presets
from bootstrap.ui_helpers import load_preset_config
from instantly_client import instantly_name_from_config
from repo_paths import reply_agent_app, subsequence_app

_SUBSEQUENCE_APP = subsequence_app()
_REPLY_APP = reply_agent_app()

_TEMPLATE_KEY_TO_UI = {
    "interested_email1": "e1",
    "interested_email2": "e2",
    "interested_email3": "e3",
}


def _load_subsequence_module(module_name: str):
    from bootstrap.app_imports import load_app_module

    return load_app_module(_SUBSEQUENCE_APP, module_name)


def resolve_niche_template_bodies(preset_id: str) -> dict[str, str] | None:
    """Return coded E1–E3 bodies for known niches, else None (clone from reference campaign)."""
    default_templates = _load_subsequence_module("default_templates")
    pid = preset_id.lower()
    if pid == "avocats" or pid.startswith("avocats_"):
        return dict(default_templates.AVOCAT_AFFAIRES_TEMPLATE_BODIES)
    if pid == "agences_immobilieres" or pid.startswith("agences_immobilieres_"):
        return dict(default_templates.AGENCES_IMMOBILIERES_TEMPLATE_BODIES)
    if "comptable" in pid:
        return dict(default_templates.COMPTABLE_TEMPLATE_BODIES)
    if any(
        token in pid
        for token in (
            "jum",
            "medecin",
            "dentiste",
            "kine",
            "architecte",
            "veterinaire",
        )
    ):
        return dict(default_templates.JUM_TEMPLATE_BODIES)
    if any(token in pid for token in ("conseiller", "patrimoine", "cif")):
        return dict(default_templates.CIF_TEMPLATE_BODIES)
    if "agence" in pid and "web" in pid:
        return dict(default_templates.AGENCE_WEB_2_TEMPLATE_BODIES)
    return None


def resolve_clone_source_campaign(preset_id: str) -> str:
    """Pick a reference campaign UUID for template cloning."""
    sub_repo = _load_subsequence_module("supabase_repo")
    biggy_source = sub_repo.BIGGY_TEMPLATE_SOURCE

    presets = discover_presets(use_cache=True)
    meta = presets.get(preset_id)
    if meta:
        siblings = [
            other
            for other in presets.values()
            if other.niche_group == meta.niche_group and other.preset_id != preset_id
        ]
        for sibling in sorted(siblings, key=lambda row: row.preset_id):
            config = sibling.loader()
            campaign_id = str(config.get("INSTANTLY_CAMPAIGN_ID") or "").strip()
            if campaign_id:
                return campaign_id
    return biggy_source


def bootstrap_bypass_layer(
    preset_id: str,
    *,
    campaign_id: str,
    campaign_name: str | None = None,
    api_key: str = "",
    clone_from: str = "",
    log_cb: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Initialize bypass config, webhook, and E1–E3 templates for a campaign."""
    if not _SUBSEQUENCE_APP.is_dir():
        raise RuntimeError("streamlit_subsequence app not found")

    from bootstrap.app_imports import load_app_module
    from bootstrap.provision import _onboard_subsequence_app

    config = load_preset_config(preset_id)
    label = str(config.get("PRESET_LABEL") or preset_id)
    short = instantly_name_from_config(config, label)
    name = campaign_name or f"{short} — Interested"

    niche_bodies = resolve_niche_template_bodies(preset_id)
    source = clone_from or ("" if niche_bodies else resolve_clone_source_campaign(preset_id))

    result = _onboard_subsequence_app(
        campaign_id=campaign_id,
        campaign_name=name,
        api_key=api_key,
        clone_from=source if not niche_bodies else "",
        log_cb=log_cb,
    )
    if result is None:
        raise RuntimeError("Bypass bootstrap failed — check webhook secret and INSTANTLY_API_KEY")

    seeded: list[str] = []
    if niche_bodies:
        sub_repo = _load_subsequence_module("supabase_repo")
        existing_rows = {
            str(row.get("template_key") or ""): row
            for row in sub_repo.list_templates(campaign_id)
        }
        for key, body_html in niche_bodies.items():
            existing = existing_rows.get(key) or {}
            if str(existing.get("body_html") or "").strip():
                continue
            sub_repo.save_template(
                campaign_id,
                key,
                str(existing.get("subject") or ""),
                body_html,
                sync_bootstrap_default=(key == "interested_email1"),
            )
            seeded.append(key)

    cloned = list(result.get("cloned_templates") or [])
    if seeded:
        result["seeded_templates"] = seeded
    elif cloned:
        result["cloned_templates"] = cloned

    return result


def bootstrap_reply_prompt_layer(preset_id: str, *, label: str = "") -> list[str]:
    """Scaffold buyer/seller prompt files when missing."""
    if not _REPLY_APP.is_dir():
        raise RuntimeError("streamlit_reply_agent app not found")

    from bootstrap.app_imports import load_app_module

    config = load_preset_config(preset_id)
    prompt_label = label or str(config.get("PRESET_LABEL") or preset_id)
    scaffold = load_app_module(_REPLY_APP, "prompt_scaffold")
    written = scaffold.scaffold_ai_reply_prompts(preset_id, prompt_label)

    return written


def load_bypass_templates_for_ui(campaign_id: str) -> dict[str, dict[str, str]]:
    """Load E1–E3 subject/body from Supabase for Streamlit prefill."""
    if not campaign_id or not _SUBSEQUENCE_APP.is_dir():
        return {}

    from bootstrap.app_imports import load_app_module

    sub_repo = load_app_module(_SUBSEQUENCE_APP, "supabase_repo")
    rows = sub_repo.list_templates(campaign_id)
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        key = str(row.get("template_key") or "")
        ui_key = _TEMPLATE_KEY_TO_UI.get(key)
        if not ui_key:
            continue
        out[ui_key] = {
            "subject": str(row.get("subject") or ""),
            "body": str(row.get("body_html") or ""),
        }
    return out


def bootstrap_campaign_layers(
    preset_id: str,
    *,
    campaign_id: str,
    api_key: str = "",
    log_cb: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run bypass + reply prompt bootstrap after campaign link/create."""
    config = load_preset_config(preset_id)
    label = str(config.get("PRESET_LABEL") or preset_id)
    bypass = bootstrap_bypass_layer(
        preset_id,
        campaign_id=campaign_id,
        api_key=api_key,
        log_cb=log_cb,
    )
    prompts = bootstrap_reply_prompt_layer(preset_id, label=label)
    summary = {
        "preset_id": preset_id,
        "campaign_id": campaign_id,
        "bypass": bypass,
        "prompt_paths": prompts,
    }
    return summary
