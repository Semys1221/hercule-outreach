"""Tests for Outscraper taxonomy gate."""

from taxonomy_gate import matches_taxonomy

_KEYWORDS = [
    "expert-comptable",
    "expert comptable",
    "expertise comptable",
    "cabinet comptable",
    "accounting firm",
    "comptable",
]


def test_matches_expert_comptable_type():
    business = {
        "type": "Expert-comptable",
        "category": "",
        "subtypes": [],
    }
    ok, kw = matches_taxonomy(business, _KEYWORDS)
    assert ok is True
    assert kw == "expert-comptable"


def test_matches_category_and_subtypes_list():
    business = {
        "type": "",
        "category": "Cabinet d'expertise comptable",
        "subtypes": ["Conseil fiscal", "Service de comptabilité"],
    }
    ok, kw = matches_taxonomy(business, _KEYWORDS)
    assert ok is True
    assert kw in _KEYWORDS


def test_rejects_restaurant():
    business = {
        "type": "Restaurant",
        "category": "Restaurant français",
        "subtypes": "Pizzeria",
    }
    ok, kw = matches_taxonomy(business, _KEYWORDS)
    assert ok is False
    assert kw == ""


def test_rejects_empty_taxonomy():
    business = {"name": "Cabinet Dupont", "type": "", "category": "", "subtypes": ""}
    ok, kw = matches_taxonomy(business, _KEYWORDS)
    assert ok is False
    assert kw == ""
