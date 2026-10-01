"""Sanity checks for niche Interested subsequence copy."""

from __future__ import annotations

import sys
from pathlib import Path

_SUBSEQUENCE_DIR = Path(__file__).resolve().parent
if str(_SUBSEQUENCE_DIR) not in sys.path:
    sys.path.insert(0, str(_SUBSEQUENCE_DIR))

from default_templates import (  # noqa: E402
    AGENCES_IMMOBILIERES_TEMPLATE_BODIES,
    AVOCAT_AFFAIRES_TEMPLATE_BODIES,
    COMPTABLE_TEMPLATE_BODIES,
    NICHE_SUBSEQUENCE_CAMPAIGNS,
)

_REQUIRED_KEYS = ("interested_email1", "interested_email2", "interested_email3")


def _assert_pack(name: str, bodies: dict[str, str], *, forbidden: tuple[str, ...]) -> None:
    for key in _REQUIRED_KEYS:
        assert key in bodies, f"{name}: missing {key}"
        body = bodies[key]
        assert body.strip(), f"{name}: empty {key}"
        assert "<p>" in body, f"{name}: {key} should be HTML"
        for token in forbidden:
            assert token not in body.lower(), f"{name}: {key} must not mention {token}"


def test_comptable_not_restaurant_or_btp() -> None:
    _assert_pack(
        "comptable",
        COMPTABLE_TEMPLATE_BODIES,
        forbidden=("restaurant", "btp", "turnover", "ratio matière"),
    )
    assert "{{reservation_link}}" in COMPTABLE_TEMPLATE_BODIES["interested_email1"]


def test_avocat_uses_entreprise_link_not_jum() -> None:
    _assert_pack("avocat", AVOCAT_AFFAIRES_TEMPLATE_BODIES, forbidden=("dgfip", "amf"))
    assert "{{reservation_link}}" in AVOCAT_AFFAIRES_TEMPLATE_BODIES["interested_email1"]
    assert "{{slot_1}}" in AVOCAT_AFFAIRES_TEMPLATE_BODIES["interested_email2"]


def test_agence_immo_carte_t_link() -> None:
    _assert_pack("agence_immo", AGENCES_IMMOBILIERES_TEMPLATE_BODIES, forbidden=("expert comptable",))
    assert "{{reservation_link}}" in AGENCES_IMMOBILIERES_TEMPLATE_BODIES["interested_email1"]


def test_campaign_ids_match_scraper_configs() -> None:
    assert NICHE_SUBSEQUENCE_CAMPAIGNS["avocats"]["campaign_id"] == "8c3aee0c-5eeb-4c5c-9a6a-a9c79b4b936c"
    assert NICHE_SUBSEQUENCE_CAMPAIGNS["agences_immobilieres"]["campaign_id"] == (
        "93c2e56f-4088-4495-94da-7891153e3947"
    )
    assert NICHE_SUBSEQUENCE_CAMPAIGNS["cabinets_expertise_comptable"]["campaign_id"] == (
        "5591a068-75f9-4826-8564-4dc2acc74bd4"
    )


if __name__ == "__main__":
    test_comptable_not_restaurant_or_btp()
    test_avocat_uses_entreprise_link_not_jum()
    test_agence_immo_carte_t_link()
    test_campaign_ids_match_scraper_configs()
    print("OK default_templates_niches tests passed")
