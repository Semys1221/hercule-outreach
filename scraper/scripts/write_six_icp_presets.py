#!/usr/bin/env python3
"""One-shot writer for the six locked ICP scraper presets."""

from __future__ import annotations

import os
import sys

_SCRAPER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRAPER_DIR not in sys.path:
    sys.path.insert(0, _SCRAPER_DIR)

from bootstrap.discovery import preset_config_path
from bootstrap.form_defaults import default_tuning
from bootstrap.template import render_preset_config

PRESETS = [
    {
        "preset_id": "cabinets_expertise_comptable",
        "label": "Cabinets expertise comptable (France)",
        "service_default": "Expertise comptable",
        "keywords": [
            "expert comptable",
            "cabinet expertise comptable",
            "cabinet d'expertise comptable",
        ],
        "expansion_keywords": [
            "expert-comptable",
            "commissaire aux comptes",
        ],
        "enrich_included": [
            "expert-comptable",
            "expertise comptable",
        ],
        "enrich_hard_excluded": [
            "dougs",
            "pennylane",
            "indy",
            "fiducial",
            "in extenso",
            "centre de gestion",
            "aga",
            "kpmg",
            "deloitte",
            "ey",
            "pwc",
            "pricewaterhousecoopers",
        ],
        "niche_metadata": {
            "angle": "Lead gen pour cabinets d'expertise comptable",
            "valeur_client": "Prise de RDV avec des cabinets EC indépendants",
            "effectif_cible": "3+ salariés",
        },
    },
    {
        "preset_id": "conseillers_gestion_patrimoine",
        "label": "CGP et courtiers (France)",
        "service_default": "Gestion de patrimoine",
        "keywords": [
            "conseiller gestion patrimoine",
            "CGP",
            "CGPI",
            "CIF",
            "courtier assurance",
        ],
        "expansion_keywords": [
            "gestion de patrimoine",
            "courtier en assurance",
        ],
        "enrich_included": [
            "gestion de patrimoine",
            "conseiller en investissements financiers",
            "courtier",
            "cgp",
            "cif",
        ],
        "enrich_hard_excluded": [
            "crédit agricole",
            "bnp paribas",
            "société générale",
            "banque populaire",
            "caisse d'épargne",
            "axa",
            "fortuneo",
            "linxea",
            "mutuelle",
        ],
        "niche_metadata": {
            "angle": "Lead gen pour cabinets CGP et courtiers",
            "valeur_client": "Prise de RDV avec des cabinets patrimoine / assurance",
            "effectif_cible": "3+ salariés",
        },
    },
    {
        "preset_id": "daf_partage",
        "label": "DAF à temps partagé (France)",
        "service_default": "DAF temps partagé",
        "keywords": [
            "DAF temps partagé",
            "directeur financier partagé",
            "DAF externalisé",
            "DAF de transition",
        ],
        "expansion_keywords": [
            "direction financière déléguée",
            "DAF externalisé",
        ],
        "enrich_included": [
            "temps partagé",
            "daf externalisé",
            "direction financière déléguée",
            "daf de transition",
        ],
        "enrich_hard_excluded": [
            "expert-comptable",
            "expertise comptable",
            "recrutement",
            "cabinet de recrutement",
            "esn",
            "portage salarial",
        ],
        "niche_metadata": {
            "angle": "Lead gen pour cabinets DAF temps partagé",
            "valeur_client": "Prise de RDV avec des cabinets DAF externalisé / transition",
            "effectif_cible": "3+ salariés",
        },
    },
    {
        "preset_id": "organismes_formation_qualiopi",
        "label": "Organismes formation Qualiopi (France)",
        "service_default": "Formation Qualiopi",
        "keywords": [
            "organisme formation qualiopi",
            "centre formation qualiopi",
            "CFA qualiopi",
        ],
        "expansion_keywords": [
            "organisme de formation qualiopi",
            "formation certifiée qualiopi",
        ],
        "enrich_included": [
            "qualiopi",
            "certifié qualiopi",
            "certification qualiopi",
        ],
        "enrich_hard_excluded": [
            "greta",
            "afpa",
            "auto-école",
            "auto ecole",
            "université",
            "maformation",
            "coaching",
            "sécurité incendie",
            "extincteur",
            "désenfumage",
            "ssi",
        ],
        "niche_metadata": {
            "angle": "Lead gen pour organismes de formation Qualiopi",
            "valeur_client": "Prise de RDV avec des OF privés et CFA certifiés Qualiopi",
            "effectif_cible": "3+ salariés",
        },
    },
    {
        "preset_id": "maintenance_securite_incendie",
        "label": "Maintenance sécurité incendie tertiaire (France)",
        "service_default": "Sécurité incendie",
        "keywords": [
            "sécurité incendie",
            "maintenance SSI",
            "extincteur tertiaire",
            "désenfumage",
            "RIA incendie",
        ],
        "expansion_keywords": [
            "maintenance extincteur",
            "système sécurité incendie",
        ],
        "enrich_included": [
            "sécurité incendie",
            "système de sécurité incendie",
            "extincteur",
            "désenfumage",
            "ria",
        ],
        "enrich_hard_excluded": [
            "particulier",
            "maison",
            "alarme",
            "vidéosurveillance",
            "ssiap",
            "apave",
            "socotec",
            "veritas",
            "vinci facilities",
        ],
        "niche_metadata": {
            "angle": "Lead gen pour maintenance sécurité incendie tertiaire",
            "valeur_client": "Prise de RDV avec des PME SSI / extincteurs / désenfumage",
            "effectif_cible": "3+ salariés",
        },
    },
    {
        "preset_id": "agences_growth_outbound",
        "label": "Agences growth cold outbound (France)",
        "service_default": "Outbound B2B",
        "keywords": [
            "agence outbound",
            "agence cold email",
            "lead generation B2B",
            "prospection commerciale B2B",
        ],
        "expansion_keywords": [
            "cold mailing",
            "prospection b2b",
            "prise de rendez-vous b2b",
        ],
        "enrich_included": [
            "cold email",
            "cold mailing",
            "outbound",
            "prospection b2b",
            "génération de leads",
            "prise de rendez-vous",
        ],
        "enrich_hard_excluded": [
            "branding",
            "community management",
            "création de site",
            "print",
            "flyer",
            "publicis",
            "graphisme",
        ],
        "niche_metadata": {
            "angle": "Lead gen pour agences outbound B2B",
            "valeur_client": "Prise de RDV avec des agences cold email / prospection B2B",
            "effectif_cible": "3+ salariés",
        },
    },
]


def main() -> None:
    tuning_base = default_tuning()
    for spec in PRESETS:
        tuning = dict(tuning_base)
        tuning["NICHE_METADATA"] = spec["niche_metadata"]
        tuning["PAPPERS_NAF_PREFIXES"] = []

        content = render_preset_config(
            preset_id=spec["preset_id"],
            label=spec["label"],
            list_id="",
            campaign_id="",
            subsequence_id="",
            target_leads=int(tuning.get("TARGET_LEADS", 5000)),
            keywords=spec["keywords"],
            expansion_keywords=spec["expansion_keywords"],
            enrich_included=spec["enrich_included"],
            enrich_hard_excluded=spec["enrich_hard_excluded"],
            enrich_soft_excluded=[],
            service_default=spec["service_default"],
            service_rules=[],
            tuning=tuning,
        )
        path = preset_config_path(spec["preset_id"])
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
