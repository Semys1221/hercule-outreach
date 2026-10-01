"""Onboarding completion tracking per preset."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bootstrap.discovery import preset_config_path
from bootstrap.validators import UUID_RE
from repo_paths import reply_prompts_dir

_REPLY_PROMPTS = reply_prompts_dir()


@dataclass(frozen=True)
class OnboardingStatus:
    preset_id: str
    config_saved: bool
    list_linked: bool
    campaign_linked: bool
    campaign_emails_saved: bool
    subsequence_saved: bool
    buyer_prompt_saved: bool

    @property
    def complete(self) -> bool:
        return all(
            (
                self.config_saved,
                self.list_linked,
                self.campaign_linked,
                self.campaign_emails_saved,
                self.subsequence_saved,
                self.buyer_prompt_saved,
            )
        )

    def missing(self) -> list[str]:
        labels = {
            "config_saved": "Config file saved",
            "list_linked": "Instantly list linked",
            "campaign_linked": "Instantly campaign linked",
            "campaign_emails_saved": "2 campaign emails saved",
            "subsequence_saved": "E1/E2/E3 subsequence saved",
            "buyer_prompt_saved": "Buyer reply prompt saved",
        }
        out: list[str] = []
        for key, label in labels.items():
            if not getattr(self, key):
                out.append(label)
        return out


def _state_path(preset_id: str) -> str:
    import sys

    app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    from outreach_data import scraper_output_base

    return os.path.join(scraper_output_base(), preset_id, "onboarding_state.json")


def load_onboarding_state(preset_id: str) -> dict[str, Any]:
    path = _state_path(preset_id)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_onboarding_state(preset_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    path = _state_path(preset_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = load_onboarding_state(preset_id)
    data.update(patch)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
    return data


def _read_config_ids(preset_id: str) -> dict[str, str]:
    path = preset_config_path(preset_id)
    if not os.path.isfile(path):
        return {"list_id": "", "campaign_id": "", "subsequence_id": ""}
    text = Path(path).read_text(encoding="utf-8")
    ids = {"list_id": "", "campaign_id": "", "subsequence_id": ""}
    for key, pattern in (
        ("list_id", r'_LIST_ID\s*=\s*["\']([^"\']*)["\']'),
        ("campaign_id", r'_CAMPAIGN_ID\s*=\s*["\']([^"\']*)["\']'),
        ("subsequence_id", r'_SUBSEQUENCE_ID\s*=\s*["\']([^"\']*)["\']'),
    ):
        match = re.search(pattern, text)
        if match:
            ids[key] = match.group(1).strip()
    return ids


def onboarding_status(preset_id: str) -> OnboardingStatus:
    config_path = preset_config_path(preset_id)
    config_saved = os.path.isfile(config_path)
    ids = _read_config_ids(preset_id)
    list_id = ids["list_id"]
    campaign_id = ids["campaign_id"]

    list_linked = bool(list_id and UUID_RE.fullmatch(list_id))
    campaign_linked = bool(campaign_id and UUID_RE.fullmatch(campaign_id))

    state = load_onboarding_state(preset_id)
    campaign_emails_saved = bool(state.get("campaign_emails_saved"))
    subsequence_saved = bool(state.get("subsequence_saved")) and campaign_linked

    buyer_path = _REPLY_PROMPTS / f"{preset_id}_buyer.md"
    buyer_prompt_saved = buyer_path.is_file() and bool(buyer_path.read_text(encoding="utf-8").strip())

    return OnboardingStatus(
        preset_id=preset_id,
        config_saved=config_saved,
        list_linked=list_linked,
        campaign_linked=campaign_linked,
        campaign_emails_saved=campaign_emails_saved,
        subsequence_saved=subsequence_saved,
        buyer_prompt_saved=buyer_prompt_saved,
    )


def onboarding_complete(preset_id: str) -> bool:
    return onboarding_status(preset_id).complete
