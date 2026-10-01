"""Tests for filter audit report classification."""

import tempfile
import os

from audit_filter import (
    analyze_filter_audit,
    classify_taxonomy_mismatch,
    is_cac_only_taxonomy,
    is_instantly_lead_cac_only,
    parse_scrape_log_batch_stats,
    run_audit,
)


def test_classify_cac_only():
    bucket = classify_taxonomy_mismatch(
        "Guyot commissaire aux comptes",
        "Commissaire aux comptes | Commissaire aux comptes | Commissaire aux comptes",
    )
    assert bucket == "cac_only"


def test_is_cac_only_taxonomy_pure_cac():
    assert is_cac_only_taxonomy(
        "commissaire aux comptes | commissaire aux comptes | commissaire aux comptes"
    )


def test_is_cac_only_taxonomy_ec_without_cac():
    assert not is_cac_only_taxonomy("expert-comptable | expert-comptable")


def test_is_instantly_lead_cac_only_pure_cac():
    lead = {
        "id": "lead-1",
        "email": "hello@monecp.fr",
        "company_name": "Mon audit légal - Commissaire aux comptes Paris",
        "payload": {
            "type": "Commissaire aux comptes",
            "category": "Commissaire aux comptes",
            "subtypes": "Commissaire aux comptes",
        },
    }
    assert is_instantly_lead_cac_only(lead)


def test_is_instantly_lead_cac_only_ec_cac_mixed():
    lead = {
        "id": "lead-2",
        "email": "hello@liberize.fr",
        "company_name": "Liberize",
        "payload": {
            "type": "Commissaire aux comptes",
            "category": "Expert-comptable",
            "subtypes": (
                "Commissaire aux comptes, Cabinet d'expertise comptable, Expert-comptable"
            ),
        },
    }
    assert not is_instantly_lead_cac_only(lead)


def test_is_instantly_lead_cac_only_ec_only():
    lead = {
        "id": "lead-3",
        "email": "contact@cabinet.fr",
        "payload": {
            "type": "Expert-comptable",
            "category": "Expert-comptable",
            "subtypes": "Cabinet d'expertise comptable",
        },
    }
    assert not is_instantly_lead_cac_only(lead)


def test_classify_noise_huissier():
    bucket = classify_taxonomy_mismatch(
        "Etude XYZ",
        "Huissier | Huissier | Huissier",
    )
    assert bucket == "noise"


def test_classify_borderline_service_comptabilite():
    bucket = classify_taxonomy_mismatch(
        "Amarris Expertise Comptable ST MALO",
        "Service de comptabilité | Service de comptabilité | Service de comptabilité",
    )
    assert bucket == "borderline"


def test_classify_name_ec_mismatch():
    bucket = classify_taxonomy_mismatch(
        "Cabinet Expert Comptable Web Agency",
        "Concepteur de sites Web | Concepteur de sites Web",
    )
    assert bucket == "name_ec_mismatch"


def test_parse_scrape_log_batch_stats():
    log = """
[2026-09-07 16:14:32 UTC] Scrape stats — places=542, emails=435, accepted=284, rejected=258, enriched_valid=0
[2026-09-07 16:30:02 UTC] Scrape stats — places=2790, emails=2395, accepted=257, rejected=2533, enriched_valid=0
"""
    with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False, encoding="utf-8") as tmp:
        tmp.write(log)
        path = tmp.name
    try:
        batches = parse_scrape_log_batch_stats(path)
    finally:
        os.unlink(path)

    assert len(batches) == 2
    assert batches[0]["accepted"] == 284
    assert batches[1]["acceptance_rate"] == 9.2


def test_analyze_filter_audit(tmp_path):
    audit = tmp_path / "filter_audit.csv"
    audit.write_text(
        "Email,Company,Category,Verdict,Reason\n"
        ",Foo,Huissier | Huissier,rejected,taxonomy_mismatch\n"
        ",Bar,Service de comptabilité | Service de comptabilité,rejected,taxonomy_mismatch\n"
        ",Baz,Expert-comptable | Expert-comptable,rejected,duplicate company (domain) or email\n",
        encoding="utf-8",
    )
    leads = tmp_path / "outscraper_leads.csv"
    leads.write_text("Email,Company\na@b.com,OK\n", encoding="utf-8")

    report = analyze_filter_audit("test", out_dir=str(tmp_path))
    assert report["accepted"] == 1
    assert report["rejected"] == 3
    assert report["taxonomy_mismatch_total"] == 2
    assert len(report["borderline_rows"]) == 1


def test_run_audit_writes_review_csv(tmp_path):
    audit = tmp_path / "filter_audit.csv"
    audit.write_text(
        "Email,Company,Category,Verdict,Reason\n"
        ",Borderline Co,Service de comptabilité | Service de comptabilité,rejected,taxonomy_mismatch\n",
        encoding="utf-8",
    )
    leads = tmp_path / "outscraper_leads.csv"
    leads.write_text("Email,Company\n", encoding="utf-8")

    report = run_audit("test", out_dir=str(tmp_path))
    review = tmp_path / "taxonomy_review.csv"
    assert review.is_file()
    assert "Borderline Co" in review.read_text(encoding="utf-8")
    assert "acceptance rate" in report["text"].lower() or "acceptance_rate" in str(report)
