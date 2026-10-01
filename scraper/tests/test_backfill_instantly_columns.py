"""Tests for Instantly segmentation column backfill."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from backfill_instantly_columns import (  # noqa: E402
    build_enriched_row,
    csv_row_to_company_record,
    instantly_lead_to_csv_row,
    should_skip_lead,
)
from company_registry.models import CompanyRecord, GateVerdict  # noqa: E402
from instantly_client import custom_variables_from_row  # noqa: E402


def test_csv_row_to_company_record_maps_registry_fields() -> None:
    record = csv_row_to_company_record(
        {
            "Email": "a@example.com",
            "Company": "Acme SAS",
            "City": "Paris",
            "Siret": "12345678901234",
            "Siren": "123456789",
            "Effectif": "12",
            "TrancheEffectif": "11",
            "Naf": "47.91A",
            "DirigeantPrenom": "Jean",
            "DirigeantNom": "Dupont",
            "EstEntrepreneurIndividuel": "non",
            "NbEtablissements": "3",
        }
    )
    assert record.siret == "12345678901234"
    assert record.effectif_min == 12
    assert record.dirigeant_prenom == "Jean"
    assert record.nb_etablissements == 3


def test_build_enriched_row_adds_segmentation_columns() -> None:
    csv_row = {
        "Email": "a@example.com",
        "Company": "EI Dupont",
        "City": "Lyon",
        "FormeJuridique": "Entrepreneur individuel",
        "EstEntrepreneurIndividuel": "oui",
        "Effectif": "1",
    }
    company = CompanyRecord(
        siren="123456789",
        siret="12345678901234",
        forme_juridique="Entrepreneur individuel",
        effectif_min=1,
        est_entrepreneur_individuel=True,
        dirigeant_prenom="Marie",
        dirigeant_nom="Dupont",
    )
    verdict = GateVerdict(True, "", company, lead_score=70, taille_entreprise="TPE")
    enriched = build_enriched_row(csv_row, verdict)

    assert enriched["DirigeantPrenom"] == "Marie"
    assert enriched["AngleIr"] == "oui"
    assert enriched["Siret"] == "12345678901234"
    assert custom_variables_from_row(enriched)["angle_ir"] == "oui"


def test_should_skip_lead_when_custom_variables_complete() -> None:
    custom_vars = {
        "city": "Paris",
        "phone": "+33123456789",
        "angle_ir": "oui",
        "angle_charges": "non",
        "angle_frais_km": "non",
        "angle_cotisations": "oui",
        "economie_estimee": "1200",
        "deja_expert_comptable": "non",
        "dirigeant_prenom": "Jean",
        "dirigeant_nom": "Martin",
        "resultat_net": "50000",
        "est_entrepreneur_individuel": "non",
    }
    assert should_skip_lead(custom_vars) is True
    assert should_skip_lead(custom_vars, force=True) is False
    assert should_skip_lead({"angle_ir": "oui"}) is False


def test_instantly_lead_to_csv_row_fallback() -> None:
    row = instantly_lead_to_csv_row(
        {
            "id": "lead-1",
            "email": "shop@example.com",
            "company_name": "Shop SAS",
            "website": "https://shop.fr",
            "custom_variables": {
                "city": "Nantes",
                "siret": "98765432109876",
                "angle_ir": "non",
            },
        }
    )
    assert row["Email"] == "shop@example.com"
    assert row["Company"] == "Shop SAS"
    assert row["City"] == "Nantes"
    assert row["Siret"] == "98765432109876"


@pytest.mark.asyncio
async def test_backfill_list_dry_run_does_not_patch() -> None:
    from backfill_instantly_columns import backfill_list

    sample_leads = [
        {
            "id": "lead-1",
            "email": "a@example.com",
            "company_name": "Acme",
            "custom_variables": {},
        }
    ]
    verdict = GateVerdict(
        True,
        "",
        CompanyRecord(
            siret="12345678901234",
            siren="123456789",
            effectif_min=5,
            dirigeant_prenom="Paul",
            dirigeant_nom="Martin",
        ),
    )

    with patch(
        "backfill_instantly_columns.load_csv_index",
        return_value=({"a@example.com": {"Email": "a@example.com", "Company": "Acme"}}, {}),
    ), patch(
        "backfill_instantly_columns.paginate_list_leads",
        return_value=sample_leads,
    ), patch(
        "backfill_instantly_columns.load_config",
        return_value={"PAPPERS_ENABLED": True},
    ), patch(
        "backfill_instantly_columns.pappers_settings",
        return_value={"enabled": True, "timeout_s": 10, "concurrency": 1},
    ), patch(
        "backfill_instantly_columns.build_validator",
        return_value=MagicMock(flush_cache=MagicMock()),
    ), patch(
        "backfill_instantly_columns.enrich_row_from_registry",
        new=AsyncMock(return_value=verdict),
    ), patch("backfill_instantly_columns.patch_lead") as patch_mock:
        report = await backfill_list(
            "api-key",
            "list-id",
            ["boutiques_ecommerce"],
            dry_run=True,
            limit=1,
        )

    assert report["dry_run_count"] == 1
    assert report["patched"] == 0
    patch_mock.assert_not_called()
    assert report["sample_patches"]
    assert report["sample_patches"][0]["patch_body"]["custom_variables"]["dirigeant_prenom"] == "Paul"

def test_should_skip_lead_when_city_missing() -> None:
    custom_vars = {
        "city": "",
        "phone": "+33123456789",
        "angle_ir": "oui",
        "angle_charges": "non",
        "angle_frais_km": "non",
        "angle_cotisations": "oui",
        "economie_estimee": "1200",
        "deja_expert_comptable": "non",
        "dirigeant_prenom": "Jean",
        "dirigeant_nom": "Martin",
        "resultat_net": "50000",
        "est_entrepreneur_individuel": "non",
    }
    assert should_skip_lead(custom_vars) is False


@pytest.mark.asyncio
async def test_backfill_campaign_dry_run() -> None:
    from backfill_instantly_columns import backfill_campaign

    sample_leads = [
        {
            "id": "lead-1",
            "email": "a@example.com",
            "company_name": "Acme",
            "custom_variables": {},
        }
    ]
    verdict = GateVerdict(
        True,
        "",
        CompanyRecord(siret="12345678901234", siren="123456789", effectif_min=5),
    )

    with patch(
        "backfill_instantly_columns.load_csv_index",
        return_value=({"a@example.com": {"Email": "a@example.com", "Company": "Acme", "City": "Paris"}}, {}),
    ), patch(
        "backfill_instantly_columns.paginate_campaign_leads",
        return_value=sample_leads,
    ), patch(
        "backfill_instantly_columns.load_config",
        return_value={"PAPPERS_ENABLED": True},
    ), patch(
        "backfill_instantly_columns.pappers_settings",
        return_value={"enabled": True, "timeout_s": 10, "concurrency": 1},
    ), patch(
        "backfill_instantly_columns.build_validator",
        return_value=MagicMock(flush_cache=MagicMock()),
    ), patch(
        "backfill_instantly_columns.enrich_row_from_registry",
        new=AsyncMock(return_value=verdict),
    ), patch("backfill_instantly_columns.patch_lead") as patch_mock:
        report = await backfill_campaign(
            "api-key",
            "campaign-id",
            ["boutiques_ecommerce"],
            dry_run=True,
            limit=1,
        )

    assert report["dry_run_count"] == 1
    assert report["scope"] == {"campaign": "campaign-id"}
    patch_mock.assert_not_called()
    assert report["sample_patches"][0]["patch_body"]["custom_variables"]["city"] == "Paris"
