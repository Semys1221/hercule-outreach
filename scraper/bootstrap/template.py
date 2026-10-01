"""Generate preset config Python files."""

from __future__ import annotations

from typing import Any


def _format_string_list(items: list[str], indent: int = 8) -> str:
    if not items:
        return "[]"
    pad = " " * indent
    close_pad = " " * max(0, indent - 4)
    escaped = []
    for item in items:
        escaped.append(f'{pad}"{item.replace(chr(34), chr(92) + chr(34))}",')
    return "[\n" + "\n".join(escaped) + f"\n{close_pad}]"


def _config_var_name(preset_id: str) -> str:
    return f"{preset_id.upper()}_CONFIG"


def _format_niche_metadata(meta: dict[str, Any] | None, indent: int = 8) -> str:
    data = meta or {}
    pad = " " * indent
    close_pad = " " * max(0, indent - 4)
    angle = str(data.get("angle") or "").replace('"', '\\"')
    valeur = str(data.get("valeur_client") or "").replace('"', '\\"')
    effectif = str(data.get("effectif_cible") or "").replace('"', '\\"')
    return (
        "{\n"
        f'{pad}"angle": "{angle}",\n'
        f'{pad}"valeur_client": "{valeur}",\n'
        f'{pad}"effectif_cible": "{effectif}",\n'
        f"{close_pad}}}"
    )


def _format_service_rules(rules: list[dict[str, Any]], indent: int = 8) -> str:
    if not rules:
        return "[]"
    pad = " " * indent
    inner_pad = " " * (indent + 4)
    close_pad = " " * max(0, indent - 4)
    lines: list[str] = ["["]
    for rule in rules:
        label = str(rule.get("label") or "").replace('"', '\\"')
        keywords = _format_string_list(list(rule.get("keywords") or []), indent=indent + 8)
        lines.append(f"{pad}{{'label': \"{label}\", 'keywords': {keywords}}},")
    lines.append(f"{close_pad}]")
    return "\n".join(lines)


def render_preset_config(
    *,
    preset_id: str,
    label: str,
    list_id: str,
    campaign_id: str,
    subsequence_id: str = "",
    niche_group: str = "",
    niche_group_label: str = "",
    subniche_label: str = "",
    target_leads: int,
    keywords: list[str],
    expansion_keywords: list[str],
    enrich_included: list[str],
    enrich_hard_excluded: list[str],
    enrich_soft_excluded: list[str],
    service_default: str,
    service_rules: list[dict[str, Any]],
    tuning: dict[str, Any],
) -> str:
    var_name = _config_var_name(preset_id)

    list_block = f'_LIST_ID = "{list_id}"' if list_id else '_LIST_ID = ""'
    list_ref = "_LIST_ID"
    campaign_block = f'\n_CAMPAIGN_ID = "{campaign_id}"' if campaign_id else '\n_CAMPAIGN_ID = ""'
    campaign_ref = "_CAMPAIGN_ID"
    dedup_campaign = "[_CAMPAIGN_ID]"
    dedup_lists = "[_LIST_ID]"
    subseq_block = (
        f'\n_SUBSEQUENCE_ID = "{subsequence_id}"' if subsequence_id else '\n_SUBSEQUENCE_ID = ""'
    )
    group_exports = ""
    if niche_group:
        group_exports = (
            f'\nNICHE_GROUP = "{niche_group}"\n'
            f'NICHE_GROUP_LABEL = "{niche_group_label.replace(chr(34), chr(92)+chr(34))}"\n'
            f'SUBNICHE_LABEL = "{subniche_label.replace(chr(34), chr(92)+chr(34))}"\n'
        )

    subseq_ref = "_SUBSEQUENCE_ID"

    return f'''"""{label} scraper preset — static rules; secrets come from config_loader."""

from french_cities import FRENCH_EXPANSION_LOCATIONS, FRENCH_LOCATIONS

PRESET_ID = "{preset_id}"
PRESET_LABEL = "{label.replace(chr(34), chr(92)+chr(34))}"
{group_exports}
{list_block}{campaign_block}{subseq_block}

{var_name} = {{
    "OUTSCRAPER_API_KEY": "",
    "INSTANTLY_API_KEY": "",
    "INSTANTLY_LIST_ID": {list_ref},
    "INSTANTLY_CAMPAIGN_ID": {campaign_ref},
    "INSTANTLY_SUBSEQUENCE_ID": {subseq_ref},
    "INSTANTLY_DEDUP_LIST_IDS": {dedup_lists},
    "INSTANTLY_DEDUP_CAMPAIGN_IDS": {dedup_campaign},
    "INSTANTLY_PUSH_EVERY": {tuning.get("INSTANTLY_PUSH_EVERY", 100)},
    "ENRICH_ENABLED": {tuning.get("ENRICH_ENABLED", False)!r},
    "ENRICH_BATCH_SIZE": {tuning.get("ENRICH_BATCH_SIZE", 50)},
    "ENRICH_CONCURRENCY": {tuning.get("ENRICH_CONCURRENCY", 20)},
    "ENRICH_TIMEOUT_MS": {tuning.get("ENRICH_TIMEOUT_MS", 10000)},
    "ENRICH_INCLUDED_KEYWORDS": {_format_string_list(enrich_included, indent=8)},
    "ENRICH_HARD_EXCLUDED_KEYWORDS": {_format_string_list(enrich_hard_excluded, indent=8)},
    "ENRICH_SOFT_EXCLUDED_KEYWORDS": {_format_string_list(enrich_soft_excluded, indent=8)},
    "OUTSCRAPER_BATCH_SIZE": {tuning.get("OUTSCRAPER_BATCH_SIZE", 200)},
    "OUTSCRAPER_CONCURRENCY": {tuning.get("OUTSCRAPER_CONCURRENCY", 6)},
    "OUTSCRAPER_LIMIT_PER_QUERY": {tuning.get("OUTSCRAPER_LIMIT_PER_QUERY", 30)},
    "OUTSCRAPER_POLL_INITIAL_S": {tuning.get("OUTSCRAPER_POLL_INITIAL_S", 45)},
    "OUTSCRAPER_POLL_INTERVAL_S": {tuning.get("OUTSCRAPER_POLL_INTERVAL_S", 5)},
    "OUTSCRAPER_POLL_SLOW_S": {tuning.get("OUTSCRAPER_POLL_SLOW_S", 10)},
    "OUTSCRAPER_POLL_TIMEOUT_S": {tuning.get("OUTSCRAPER_POLL_TIMEOUT_S", 600)},
    "OUTSCRAPER_TOTAL_LIMIT_BUFFER": {tuning.get("OUTSCRAPER_TOTAL_LIMIT_BUFFER", 8)},
    "TARGET_LEADS": {target_leads},
    "TARGET_MODE": "instantly_pushed",
    "SERVICE_DEFAULT": "{service_default.replace(chr(34), chr(92)+chr(34))}",
    "SERVICE_RULES": {_format_service_rules(service_rules, indent=4)},
    "KEYWORDS": {_format_string_list(keywords, indent=8)},
    "EXPANSION_KEYWORDS": {_format_string_list(expansion_keywords, indent=8)},
    "LOCATIONS": FRENCH_LOCATIONS,
    "EXPANSION_LOCATIONS": FRENCH_EXPANSION_LOCATIONS,
    "EXCLUDE_DOMAINS": {_format_string_list(list(tuning.get("EXCLUDE_DOMAINS") or []), indent=8)},
    "PAPPERS_ENABLED": {tuning.get("PAPPERS_ENABLED", False)!r},
    "PAPPERS_MIN_EMPLOYEES": {int(tuning.get("PAPPERS_MIN_EMPLOYEES", 3))},
    "PAPPERS_MIN_SCORE": {int(tuning.get("PAPPERS_MIN_SCORE", 55))},
    "PAPPERS_SCORING_ENABLED": {tuning.get("PAPPERS_SCORING_ENABLED", True)!r},
    "PAPPERS_ON_UNKNOWN": "{str(tuning.get("PAPPERS_ON_UNKNOWN") or "reject")}",
    "PAPPERS_CONCURRENCY": {int(tuning.get("PAPPERS_CONCURRENCY", 50))},
    "PAPPERS_NAF_PREFIXES": {_format_string_list(list(tuning.get("PAPPERS_NAF_PREFIXES") or []), indent=8)},
    "SIRENE_INDEX_ENABLED": {tuning.get("SIRENE_INDEX_ENABLED", True)!r},
    "SIRENE_INDEX_PATH": "{str(tuning.get("SIRENE_INDEX_PATH") or "data/sirene.db")}",
    "REGISTRY_DEEP_ENRICH": {tuning.get("REGISTRY_DEEP_ENRICH", False)!r},
    "REJECT_HOLDINGS": {tuning.get("REJECT_HOLDINGS", True)!r},
    "NICHE_METADATA": {_format_niche_metadata(tuning.get("NICHE_METADATA"), indent=8)},
}}

CONFIG = {var_name}
'''
