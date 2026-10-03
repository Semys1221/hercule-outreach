"""Runbook Test scraper preset — static rules; secrets come from config_loader."""

from french_cities import FRENCH_EXPANSION_LOCATIONS, FRENCH_LOCATIONS

PRESET_ID = "runbook_test"
PRESET_LABEL = "Runbook Test"

_LIST_ID = "78a1464e-7311-4541-b36f-deaf979b1cff"
_CAMPAIGN_ID = "7fb37956-5ed0-43e2-9512-fa7469ca52c6"
_SUBSEQUENCE_ID = "d612e951-4b5f-4344-a753-59fbad01aa8b"

RUNBOOK_TEST_CONFIG = {
    "OUTSCRAPER_API_KEY": "",
    "INSTANTLY_API_KEY": "",
    "INSTANTLY_LIST_ID": _LIST_ID,
    "INSTANTLY_CAMPAIGN_ID": _CAMPAIGN_ID,
    "INSTANTLY_SUBSEQUENCE_ID": _SUBSEQUENCE_ID,
    "INSTANTLY_DEDUP_LIST_IDS": [_LIST_ID],
    "INSTANTLY_DEDUP_CAMPAIGN_IDS": [_CAMPAIGN_ID],
    "INSTANTLY_PUSH_EVERY": 100,
    "ENRICH_ENABLED": False,
    "ENRICH_BATCH_SIZE": 50,
    "ENRICH_CONCURRENCY": 20,
    "ENRICH_TIMEOUT_MS": 10000,
    "ENRICH_INCLUDED_KEYWORDS": [
        "comptabilité",
        "expert-comptable",
    ],
    "ENRICH_HARD_EXCLUDED_KEYWORDS": [
        "recrutement",
    ],
    "ENRICH_SOFT_EXCLUDED_KEYWORDS": [],
    "OUTSCRAPER_BATCH_SIZE": 200,
    "OUTSCRAPER_CONCURRENCY": 6,
    "OUTSCRAPER_LIMIT_PER_QUERY": 30,
    "OUTSCRAPER_POLL_INITIAL_S": 45,
    "OUTSCRAPER_POLL_INTERVAL_S": 5,
    "OUTSCRAPER_POLL_SLOW_S": 10,
    "OUTSCRAPER_POLL_TIMEOUT_S": 600,
    "OUTSCRAPER_TOTAL_LIMIT_BUFFER": 8,
    "TARGET_LEADS": 5000,
    "TARGET_MODE": "instantly_pushed",
    "SERVICE_DEFAULT": "Comptabilité",
    "SERVICE_RULES": [
    {'label': "Comptabilité", 'keywords': [
            "comptable",
            "expert-comptable",
        ]},
],
    "KEYWORDS": [
        "comptable",
    ],
    "EXPANSION_KEYWORDS": [
        "expert comptable",
        "cabinet comptable",
    ],
    "LOCATIONS": FRENCH_LOCATIONS,
    "EXPANSION_LOCATIONS": FRENCH_EXPANSION_LOCATIONS,
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
        "angle": "runbook validation",
        "valeur_client": "test onboarding",
        "effectif_cible": "PME 10-50",
    },
}

CONFIG = RUNBOOK_TEST_CONFIG
