"""Default tuning values for the config onboarding form."""

from __future__ import annotations

from typing import Any

from configs._bases.common import (
    ENRICH_SETTINGS,
    EXCLUDE_DOMAINS,
    INGESTER_SETTINGS,
    OUTSCRAPER_SETTINGS,
    REGISTRY_SETTINGS,
    TARGET_SETTINGS,
)


def default_tuning() -> dict[str, Any]:
    return {
        **OUTSCRAPER_SETTINGS,
        **ENRICH_SETTINGS,
        **INGESTER_SETTINGS,
        **TARGET_SETTINGS,
        **REGISTRY_SETTINGS,
        "EXCLUDE_DOMAINS": list(EXCLUDE_DOMAINS),
        "NICHE_METADATA": {
            "angle": "",
            "valeur_client": "",
            "effectif_cible": "",
        },
    }
