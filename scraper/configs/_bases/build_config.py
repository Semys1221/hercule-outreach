"""Helper to assemble sub-niche preset CONFIG dicts."""

from __future__ import annotations

from typing import Any


def build_subniche_config(
    shared: dict[str, Any],
    *,
    list_id: str,
    campaign_id: str,
    subsequence_id: str,
    service_default: str,
    service_rules: list[dict[str, Any]],
    keywords: list[str],
    expansion_keywords: list[str],
    enrich_included: list[str],
    enrich_hard_excluded: list[str],
    enrich_soft_excluded: list[str],
    subniche_label: str,
) -> dict[str, Any]:
    config = dict(shared)
    config["INSTANTLY_LIST_ID"] = list_id
    config["INSTANTLY_CAMPAIGN_ID"] = campaign_id
    config["INSTANTLY_SUBSEQUENCE_ID"] = subsequence_id
    config["INSTANTLY_DEDUP_LIST_IDS"] = [list_id] if list_id else []
    config["INSTANTLY_DEDUP_CAMPAIGN_IDS"] = [campaign_id] if campaign_id else []
    config["SERVICE_DEFAULT"] = service_default
    config["SERVICE_RULES"] = service_rules
    config["KEYWORDS"] = keywords
    config["EXPANSION_KEYWORDS"] = expansion_keywords
    config["ENRICH_INCLUDED_KEYWORDS"] = enrich_included
    config["ENRICH_HARD_EXCLUDED_KEYWORDS"] = enrich_hard_excluded
    config["ENRICH_SOFT_EXCLUDED_KEYWORDS"] = enrich_soft_excluded
    config["SUBNICHE_LABEL"] = subniche_label
    return config
