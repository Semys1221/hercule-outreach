"""Preset schema validation and Instantly URL parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.I,
)

INSTANTLY_LIST_STEP_HINT = (
    "Step 1 — link the Instantly lead list in onboarding tab « 2 Liste » "
    "(Instantly app → Contacts → listId in the URL) or set "
    "`configs/<preset>_config.py` / `INSTANTLY_LIST_ID_<PRESET>` env override."
)
PRESET_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")

REQUIRED_CONFIG_KEYS = (
    "INSTANTLY_LIST_ID",
    "TARGET_LEADS",
    "TARGET_MODE",
    "SERVICE_DEFAULT",
    "SERVICE_RULES",
    "KEYWORDS",
    "LOCATIONS",
    "EXPANSION_KEYWORDS",
    "EXPANSION_LOCATIONS",
    "ENRICH_ENABLED",
    "ENRICH_INCLUDED_KEYWORDS",
    "ENRICH_HARD_EXCLUDED_KEYWORDS",
    "ENRICH_SOFT_EXCLUDED_KEYWORDS",
    "EXCLUDE_DOMAINS",
    "OUTSCRAPER_BATCH_SIZE",
    "OUTSCRAPER_CONCURRENCY",
    "OUTSCRAPER_LIMIT_PER_QUERY",
)

REQUIRED_LIST_KEYS = (
    "KEYWORDS",
    "LOCATIONS",
    "EXPANSION_KEYWORDS",
    "EXPANSION_LOCATIONS",
    "ENRICH_INCLUDED_KEYWORDS",
    "ENRICH_HARD_EXCLUDED_KEYWORDS",
    "ENRICH_SOFT_EXCLUDED_KEYWORDS",
    "EXCLUDE_DOMAINS",
)


@dataclass
class ValidationResult:
    preset_id: str
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.ok = False
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


def require_instantly_list_for_scrape_push(
    config: dict[str, Any],
    *,
    preset_id: str = "",
) -> str:
    """Fail fast when scrape/push has no valid Instantly list target."""
    list_id = str(config.get("INSTANTLY_LIST_ID") or "").strip()
    preset_hint = f" (preset `{preset_id}`)" if preset_id else ""
    if not list_id:
        raise ValueError(
            f"INSTANTLY_LIST_ID is required before scrape/push{preset_hint}. "
            f"{INSTANTLY_LIST_STEP_HINT}"
        )
    if not UUID_RE.fullmatch(list_id):
        raise ValueError(
            f"INSTANTLY_LIST_ID must be a UUID{preset_hint}: {list_id!r}. "
            f"{INSTANTLY_LIST_STEP_HINT}"
        )
    api_key = str(config.get("INSTANTLY_API_KEY") or "").strip()
    if not api_key:
        raise ValueError(
            f"INSTANTLY_API_KEY is required for scrape/push{preset_hint} (repo `.env`). "
            f"{INSTANTLY_LIST_STEP_HINT}"
        )
    return list_id


def parse_instantly_uuid(value: str, *, kind: str = "id") -> str:
    """Extract UUID from raw ID or Instantly app URL."""
    raw = value.strip()
    if not raw:
        return ""

    match = UUID_RE.search(raw)
    if not match:
        raise ValueError(f"Invalid Instantly {kind}: no UUID found in {raw!r}")
    return match.group(0).lower()


def validate_preset_id(preset_id: str) -> str:
    normalized = preset_id.strip().lower().replace("-", "_").replace(" ", "_")
    if not PRESET_ID_RE.match(normalized):
        raise ValueError(
            "Preset ID must be snake_case (lowercase letters, digits, underscores; "
            "must start with a letter)."
        )
    return normalized


def parse_keyword_list(raw: str) -> list[str]:
    if not raw.strip():
        return []
    parts: list[str] = []
    for line in raw.replace(";", ",").splitlines():
        for item in line.split(","):
            kw = item.strip()
            if kw:
                parts.append(kw)
    return parts


def validate_config_schema(config: dict[str, Any], *, preset_id: str) -> ValidationResult:
    result = ValidationResult(preset_id=preset_id, ok=True)

    for key in REQUIRED_CONFIG_KEYS:
        if key not in config:
            result.add_error(f"CONFIG missing key: {key}")

    for key in REQUIRED_LIST_KEYS:
        value = config.get(key)
        if value is not None and not isinstance(value, list):
            result.add_error(f"CONFIG[{key!r}] must be a list")
        elif isinstance(value, list) and len(value) == 0:
            result.add_warning(f"CONFIG[{key!r}] is empty")

    list_id = str(config.get("INSTANTLY_LIST_ID", "")).strip()
    if list_id and not UUID_RE.fullmatch(list_id):
        result.add_error(f"INSTANTLY_LIST_ID is not a valid UUID: {list_id!r}")
    elif not list_id:
        result.add_warning(
            "INSTANTLY_LIST_ID is empty — complete onboarding tab « 2 Liste » before scrape/push"
        )

    campaign_id = str(config.get("INSTANTLY_CAMPAIGN_ID", "")).strip()
    if campaign_id and not UUID_RE.fullmatch(campaign_id):
        result.add_error(f"INSTANTLY_CAMPAIGN_ID is not a valid UUID: {campaign_id!r}")

    subsequence_id = str(config.get("INSTANTLY_SUBSEQUENCE_ID", "")).strip()
    if subsequence_id and not UUID_RE.fullmatch(subsequence_id):
        result.add_error(f"INSTANTLY_SUBSEQUENCE_ID is not a valid UUID: {subsequence_id!r}")

    niche_group = str(config.get("NICHE_GROUP") or "").strip()
    if niche_group and not PRESET_ID_RE.match(niche_group):
        result.add_error(f"NICHE_GROUP must be snake_case: {niche_group!r}")

    target = config.get("TARGET_LEADS")
    if target is not None and int(target) <= 0:
        result.add_error("TARGET_LEADS must be positive")

    mode = str(config.get("TARGET_MODE") or "csv_saved").strip()
    if config.get("TARGET_MODE") is not None:
        from scrape_state import VALID_TARGET_MODES

        if mode not in VALID_TARGET_MODES:
            result.add_error(
                f"TARGET_MODE must be one of {sorted(VALID_TARGET_MODES)}: {mode!r}"
            )

    service_default = config.get("SERVICE_DEFAULT")
    if service_default is not None and not str(service_default).strip():
        result.add_error("SERVICE_DEFAULT must be a non-empty string")

    service_rules = config.get("SERVICE_RULES")
    if service_rules is not None:
        if not isinstance(service_rules, list):
            result.add_error("CONFIG['SERVICE_RULES'] must be a list")
        else:
            for idx, rule in enumerate(service_rules):
                if not isinstance(rule, dict):
                    result.add_error(f"SERVICE_RULES[{idx}] must be a dict")
                    continue
                if not str(rule.get("label") or "").strip():
                    result.add_error(f"SERVICE_RULES[{idx}] missing non-empty 'label'")
                keywords = rule.get("keywords")
                if keywords is None or not isinstance(keywords, list):
                    result.add_error(f"SERVICE_RULES[{idx}] missing 'keywords' list")

    if "PAPPERS_ENABLED" in config and not isinstance(config.get("PAPPERS_ENABLED"), bool):
        result.add_error("PAPPERS_ENABLED must be a bool")

    min_emp = config.get("PAPPERS_MIN_EMPLOYEES")
    if min_emp is not None:
        try:
            if int(min_emp) < 0:
                result.add_error("PAPPERS_MIN_EMPLOYEES must be >= 0")
        except (TypeError, ValueError):
            result.add_error("PAPPERS_MIN_EMPLOYEES must be an integer")

    on_unknown = str(config.get("PAPPERS_ON_UNKNOWN") or "reject").strip().lower()
    if config.get("PAPPERS_ON_UNKNOWN") is not None and on_unknown not in ("reject", "accept"):
        result.add_error("PAPPERS_ON_UNKNOWN must be 'reject' or 'accept'")

    naf = config.get("PAPPERS_NAF_PREFIXES")
    if naf is not None and not isinstance(naf, list):
        result.add_error("PAPPERS_NAF_PREFIXES must be a list")

    min_score = config.get("PAPPERS_MIN_SCORE")
    if min_score is not None:
        try:
            if int(min_score) < 0:
                result.add_error("PAPPERS_MIN_SCORE must be >= 0")
        except (TypeError, ValueError):
            result.add_error("PAPPERS_MIN_SCORE must be an integer")

    if "PAPPERS_SCORING_ENABLED" in config and not isinstance(
        config.get("PAPPERS_SCORING_ENABLED"), bool
    ):
        result.add_error("PAPPERS_SCORING_ENABLED must be a bool")

    if "SIRENE_INDEX_ENABLED" in config and not isinstance(
        config.get("SIRENE_INDEX_ENABLED"), bool
    ):
        result.add_error("SIRENE_INDEX_ENABLED must be a bool")

    if "REGISTRY_DEEP_ENRICH" in config and not isinstance(
        config.get("REGISTRY_DEEP_ENRICH"), bool
    ):
        result.add_error("REGISTRY_DEEP_ENRICH must be a bool")

    if "REJECT_HOLDINGS" in config and not isinstance(config.get("REJECT_HOLDINGS"), bool):
        result.add_error("REJECT_HOLDINGS must be a bool")

    if "TAXONOMY_GATE_ENABLED" in config and not isinstance(
        config.get("TAXONOMY_GATE_ENABLED"), bool
    ):
        result.add_error("TAXONOMY_GATE_ENABLED must be a bool")

    taxonomy_keywords = config.get("TAXONOMY_INCLUDED_KEYWORDS")
    if taxonomy_keywords is not None and not isinstance(taxonomy_keywords, list):
        result.add_error("TAXONOMY_INCLUDED_KEYWORDS must be a list")
    if config.get("TAXONOMY_GATE_ENABLED") and not (
        isinstance(taxonomy_keywords, list) and taxonomy_keywords
    ):
        result.add_error(
            "TAXONOMY_INCLUDED_KEYWORDS must be a non-empty list when TAXONOMY_GATE_ENABLED"
        )

    metadata = config.get("NICHE_METADATA")
    if metadata is not None and not isinstance(metadata, dict):
        result.add_error("NICHE_METADATA must be a dict")

    return result


def validate_preset_runtime(preset_id: str, *, dry_run: bool = False) -> ValidationResult:
    from config_loader import load_config
    from scrape_state import build_config_fingerprint

    result = ValidationResult(preset_id=preset_id, ok=True)

    try:
        config = load_config(preset_id, require_keys=False)
    except SystemExit as exc:
        result.add_error(str(exc))
        return result
    except Exception as exc:
        result.add_error(f"load_config failed: {exc}")
        return result

    schema = validate_config_schema(config, preset_id=preset_id)
    result.errors.extend(schema.errors)
    result.warnings.extend(schema.warnings)
    if not schema.ok:
        result.ok = False

    try:
        build_config_fingerprint(config)
    except Exception as exc:
        result.add_error(f"build_config_fingerprint failed: {exc}")

    if dry_run:
        try:
            import asyncio
            from core_logic import run_scraper_pipeline

            summary: dict[str, Any] = {}

            def _log(_: str) -> None:
                pass

            summary = asyncio.run(
                run_scraper_pipeline(
                    config,
                    log_cb=_log,
                    progress_cb=lambda _: None,
                    metric_cb=lambda *_: None,
                    dry_run=True,
                    preset=preset_id,
                )
            )
            if int(summary.get("queries_total", 0)) <= 0:
                result.add_warning("dry-run produced zero queries")
        except Exception as exc:
            result.add_error(f"dry-run failed: {exc}")

    return result
