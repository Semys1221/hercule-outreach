"""Tests for niche template routing in campaign bootstrap."""

from __future__ import annotations

import sys
from pathlib import Path

_BOOTSTRAP_DIR = Path(__file__).resolve().parent
_SCRAPER_DIR = _BOOTSTRAP_DIR.parent
if str(_SCRAPER_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRAPER_DIR))

from bootstrap.campaign_layers import resolve_niche_template_bodies  # noqa: E402


def test_avocats_preset_not_jum() -> None:
    bodies = resolve_niche_template_bodies("avocats")
    assert bodies is not None
    assert "dgfip" not in bodies["interested_email1"].lower()
    assert "{{reservation_entreprise_link}}" in bodies["interested_email1"]


def test_agences_immobilieres_preset() -> None:
    bodies = resolve_niche_template_bodies("agences_immobilieres")
    assert bodies is not None
    assert "{{reservation_carte_t_link}}" in bodies["interested_email1"]


def test_comptable_preset() -> None:
    bodies = resolve_niche_template_bodies("cabinets_expertise_comptable")
    assert bodies is not None
    assert "restaurant" not in bodies["interested_email1"].lower()


if __name__ == "__main__":
    test_avocats_preset_not_jum()
    test_agences_immobilieres_preset()
    test_comptable_preset()
    print("OK campaign_layers_niches tests passed")
