"""Tests for lead segmentation helpers."""

from __future__ import annotations

from company_registry.models import CompanyRecord
from company_registry.registry_client import parse_search_result
from company_registry.segmentation import (
    compute_angle_flags,
    detect_compta_on_site,
    enrich_lead_segmentation,
)


def test_parse_search_result_extracts_dirigeant_and_finances():
    item = {
        "siren": "123456789",
        "siege": {"siret": "12345678900012", "libelle_commune": "Paris"},
        "activite_principale": "47.91A",
        "nature_juridique": "5710",
        "tranche_effectif_salarie": "11",
        "date_creation": "2018-01-01",
        "categorie_entreprise": "PME",
        "complements": {"est_entrepreneur_individuel": False},
        "dirigeants": [
            {"nom": "Dupont", "prenoms": ["Jean", "Pierre"], "qualite": "Gérant"},
        ],
        "finances": {
            "2022": {"ca": 850000, "resultat_net": 42000},
            "2021": {"ca": 620000, "resultat_net": 31000},
        },
        "matching_etablissements": [{"siret": "12345678900012"}, {"siret": "12345678900034"}],
    }
    record = parse_search_result(item, match_score=90.0)
    assert record.dirigeant_prenom == "Jean Pierre"
    assert record.dirigeant_nom == "Dupont"
    assert record.dirigeant_qualite == "Gérant"
    assert record.chiffre_affaires == "850000"
    assert record.resultat_net == "42000"
    assert record.nb_etablissements == 2
    assert record.categorie_entreprise == "PME"


def test_detect_compta_on_site():
    text = "Notre cabinet expert-comptable vous accompagne."
    deja, outil = detect_compta_on_site(text)
    assert deja == "oui"
    assert outil == "non"


def test_compute_angle_flags_for_ir_and_charges():
    record = CompanyRecord(
        forme_juridique="Entrepreneur individuel",
        forme_juridique_code="1000",
        effectif_min=8,
        code_naf="47.91A",
        est_entrepreneur_individuel=True,
        chiffre_affaires="400000",
        annee_creation="2019",
    )
    flags = compute_angle_flags(record, site_text="boutique en ligne shopify")
    assert flags["AngleIr"] == "oui"
    assert flags["AngleCotisations"] == "oui"
    assert flags["DejaExpertComptable"] == "non"
    assert int(flags["EconomieEstimee"]) >= 800


def test_enrich_lead_segmentation_merges_row_fields():
    record = CompanyRecord(
        dirigeant_prenom="Marie",
        dirigeant_nom="Martin",
        effectif_min=12,
        code_naf="62.01Z",
        chiffre_affaires="1200000",
        annee_creation="2016",
    )
    row = {
        "Phone": "+33102030405",
        "Rating": "4.6",
        "ReviewsCount": "38",
        "_website_text": "agence e-commerce shopify",
    }
    fields = enrich_lead_segmentation(record, row)
    assert fields["DirigeantPrenom"] == "Marie"
    assert fields["Phone"] == "+33102030405"
    assert fields["AngleFraisKm"] == "oui"
