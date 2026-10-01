"""Tests for company_registry package."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from contextlib import closing

import pytest

from company_registry.classifier import classify_company, tranche_max, tranche_min
from company_registry.config import CompanyGateConfig
from company_registry.gate import CompanyGate
from company_registry.matcher import normalize_name, score_api_result
from company_registry.models import CompanyRecord, CompanySize, RejectReason
from company_registry.scorer import compute_lead_score, is_holding
from company_registry.sirene_build import _row_to_record
from company_registry.sirene_index import ensure_schema, normalize_denomination
from company_registry.siret_extract import extract_siret_siren


def test_extract_siret_labeled():
    text = "SIRET : 123 456 789 00012"
    siret, siren = extract_siret_siren(text)
    assert siret == "12345678900012"
    assert siren == "123456789"


def test_tranche_min_mapping():
    assert tranche_min("02") == 3
    assert tranche_min("01") == 1
    assert tranche_min("11") == 10


def test_tranche_max_mapping():
    assert tranche_max("02") == 5
    assert tranche_max("11") == 19
    assert tranche_max("12") == 49


def test_classify_tpe_pme_eti():
    assert classify_company(effectif_min=5) == CompanySize.TPE
    assert classify_company(effectif_min=25) == CompanySize.PME
    assert classify_company(effectif_min=300) == CompanySize.ETI
    assert classify_company(effectif_min=6000) == CompanySize.GE


def test_holding_detection():
    record = CompanyRecord(forme_juridique_code="6540", code_naf="68.20A")
    assert is_holding(record)


def test_scorer_unknown_effectif_can_pass():
    record = CompanyRecord(
        siren="123456789",
        code_naf="69.20Z",
        annee_creation="2015",
        forme_juridique_code="5599",
        match_score=80,
        siret_from_site=True,
    )
    score = compute_lead_score(
        record,
        company="Cabinet Test",
        city="Paris",
        min_employees=3,
        naf_prefixes=["69."],
    )
    assert score >= 55


def test_gate_rejects_low_effectif():
    gate = CompanyGate(CompanyGateConfig(min_employees=3, scoring_enabled=True))
    record = CompanyRecord(effectif_min=1, code_naf="69.20Z")
    verdict = gate._apply_rules(record, company="Test", city="Paris")
    assert not verdict.accepted
    assert verdict.reason == str(RejectReason.EMPLOYEE_COUNT)


def test_gate_accepts_known_effectif():
    gate = CompanyGate(CompanyGateConfig(min_employees=3))
    record = CompanyRecord(effectif_min=10, code_naf="69.20Z")
    verdict = gate._apply_rules(record, company="Test", city="Paris")
    assert verdict.accepted


def test_gate_accepts_not_found_when_on_unknown_accept():
    gate = CompanyGate(CompanyGateConfig(on_unknown="accept"))
    verdict = gate._reject(RejectReason.NOT_FOUND, CompanyRecord())
    assert verdict.accepted


def test_gate_accepts_unavailable_when_on_unknown_accept():
    gate = CompanyGate(CompanyGateConfig(on_unknown="accept"))
    verdict = gate._reject(RejectReason.UNAVAILABLE, CompanyRecord())
    assert verdict.accepted


def test_gate_rejects_high_effectif_with_max():
    gate = CompanyGate(CompanyGateConfig(min_employees=3, max_employees=15))
    record = CompanyRecord(effectif_min=20, tranche_effectif="12", code_naf="43.22A")
    verdict = gate._apply_rules(record, company="Test", city="Paris")
    assert not verdict.accepted
    assert verdict.reason == str(RejectReason.EMPLOYEE_COUNT)


def test_gate_accepts_ambiguous_tranche_within_max():
    gate = CompanyGate(CompanyGateConfig(min_employees=3, max_employees=15))
    record = CompanyRecord(effectif_min=10, tranche_effectif="11", code_naf="43.22A")
    verdict = gate._apply_rules(record, company="Test", city="Paris")
    assert verdict.accepted


def test_fuzzy_api_match_prefers_city():
    results = [
        {
            "nom_complet": "Agence Alpha",
            "siren": "111111111",
            "siege": {"libelle_commune": "Lyon", "siret": "11111111100011"},
            "activite_principale": "73.11Z",
            "tranche_effectif_salarie": "11",
        },
        {
            "nom_complet": "Agence Alpha Paris",
            "siren": "222222222",
            "siege": {"libelle_commune": "Paris", "siret": "22222222200022"},
            "activite_principale": "73.11Z",
            "tranche_effectif_salarie": "12",
        },
    ]
    score_paris = score_api_result(results[1], company="Agence Alpha", city="Paris")
    score_lyon = score_api_result(results[0], company="Agence Alpha", city="Paris")
    assert score_paris > score_lyon


def test_sirene_row_to_record_parses_csv_dict():
    row = {
        "siren": "123456789",
        "nic": "00012",
        "siret": "12345678900012",
        "denominationUsuelleEtablissement": "Acme SARL",
        "enseigne1Etablissement": "",
        "activitePrincipaleEtablissement": "25.62",
        "trancheEffectifsEtablissement": "11",
        "libelleCommuneEtablissement": "Paris",
    }
    record = _row_to_record(row)
    assert record is not None
    assert record[0] == "12345678900012"
    assert record[1] == "123456789"
    assert record[2] == "Acme SARL"
    assert record[3] == normalize_denomination("Acme SARL")
    assert record[4] == "25.62"
    assert record[5] == "11"
    assert record[7] == "Paris"


def test_sirene_row_to_record_falls_back_to_siren_nic():
    row = {
        "siren": "123456789",
        "nic": "00012",
        "siret": "",
        "denominationUsuelleEtablissement": "",
        "enseigne1Etablissement": "Acme Shop",
        "activitePrincipaleEtablissement": "47.11",
        "trancheEffectifsEtablissement": "02",
        "libelleCommuneEtablissement": "Lyon",
    }
    record = _row_to_record(row)
    assert record is not None
    assert record[0] == "12345678900012"
    assert record[2] == "Acme Shop"


def test_sirene_row_to_record_skips_invalid_siret():
    assert _row_to_record({"siren": "bad", "nic": "00012", "siret": ""}) is None
    assert _row_to_record({"siren": "123456789", "nic": "00012", "siret": "123"}) is None


def test_sirene_index_lookup():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with closing(sqlite3.connect(db_path)) as conn:
            ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO etablissements
                (siret, siren, denomination, denomination_norm, naf, tranche_effectif,
                 forme_juridique_code, commune)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "12345678900012",
                    "123456789",
                    "Acme SARL",
                    normalize_denomination("Acme SARL"),
                    "25.62",
                    "11",
                    "5710",
                    "Paris",
                ),
            )
            conn.commit()
        from company_registry.sirene_index import SireneIndex

        index = SireneIndex(db_path)
        hit = index.lookup_siret("12345678900012")
        assert hit is not None
        assert hit.effectif_min == 10
        assert hit.siren == "123456789"
