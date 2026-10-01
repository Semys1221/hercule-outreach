"""Load scraper niche presets for AI Reply Agent onboarding."""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from typing import Any

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SCRAPER_DIR = os.path.join(_REPO_ROOT, "scraper")

if _SCRAPER_DIR not in sys.path:
    sys.path.insert(0, _SCRAPER_DIR)


def list_preset_options() -> dict[str, str]:
    """Return {label: preset_id}."""
    from config_loader import PRESET_LABELS

    return {label: preset_id for preset_id, label in PRESET_LABELS.items()}


def preset_label(preset_id: str) -> str:
    from config_loader import PRESET_LABELS

    return PRESET_LABELS.get(preset_id, preset_id)


def load_niche_metadata(preset_id: str) -> dict[str, Any]:
    from config_loader import load_config

    config = load_config(preset_id, require_keys=False)
    meta = config.get("NICHE_METADATA")
    return meta if isinstance(meta, dict) else {}


@lru_cache(maxsize=1)
def build_campaign_preset_index() -> dict[str, str]:
    """Map Instantly campaign UUIDs to scraper preset_id."""
    from config_loader import PRESETS, load_config

    def _assign(index: dict[str, str], campaign_id: str, preset_id: str) -> None:
        cid = campaign_id.strip()
        if not cid:
            return
        existing = index.get(cid)
        if not existing:
            index[cid] = preset_id
            return
        # Dual comptable workers share one campaign — prefer main preset over *_vol.
        if existing.endswith("_vol") and not preset_id.endswith("_vol"):
            index[cid] = preset_id
        elif not existing.endswith("_vol") and preset_id.endswith("_vol"):
            return
        else:
            index[cid] = preset_id

    index: dict[str, str] = {}
    for preset_id in PRESETS:
        config = load_config(preset_id, require_keys=False)
        primary = str(config.get("INSTANTLY_CAMPAIGN_ID") or "").strip()
        if primary:
            _assign(index, primary, preset_id)

    for preset_id in PRESETS:
        config = load_config(preset_id, require_keys=False)
        dedup_ids = config.get("INSTANTLY_DEDUP_CAMPAIGN_IDS") or []
        if isinstance(dedup_ids, list):
            for campaign_id in dedup_ids:
                cid = str(campaign_id or "").strip()
                if cid and cid not in index:
                    index[cid] = preset_id
    return index


def resolve_preset_for_campaign(campaign_id: str) -> str | None:
    return build_campaign_preset_index().get(campaign_id.strip())
