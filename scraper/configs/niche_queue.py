"""Ordered niche scrape queue (prepare only — do not auto-start workers)."""

from __future__ import annotations

from typing import TypedDict


class NicheQueueEntry(TypedDict):
    preset_id: str
    instantly_name: str
    rank: int
    notes: str


# Priority 1 = scrape first when the fleet is launched.
NICHE_SCRAPE_QUEUE: tuple[NicheQueueEntry, ...] = (
    {
        "preset_id": "chirurgiens_plasticiens",
        "instantly_name": "Chirurgien plasticien",
        "rank": 1,
        "notes": "Ticket 3–10 k€ / acte ; décideur solo ; angle décret com. 23 sept. 2026.",
    },
    {
        "preset_id": "medecine_esthetique",
        "instantly_name": "Médecin esthétique",
        "rank": 2,
        "notes": "Patients récurrents (injections) ; décision rapide ; budget un peu plus serré.",
    },
    {
        "preset_id": "agences_immobilieres",
        "instantly_name": "Agence immobilière",
        "rank": 3,
        "notes": "Mandat ~8–10 k€ commission ; cibler agences >300 k€ CA (sinon décrochent).",
    },
    {
        "preset_id": "centres_dentaires_independants",
        "instantly_name": "Centre dentaire indépendant",
        "rank": 4,
        "notes": "Implant 1–2,5 k€ ; exclure réseaux / sièges.",
    },
    {
        "preset_id": "hotels_independants",
        "instantly_name": "Hôtel indépendant",
        "rank": 5,
        "notes": "3★+ ; angle commission Booking 15–18 % ; saisonnalité / groupes.",
    },
    {
        "preset_id": "cabinets_expertise_comptable_fresh_geo",
        "instantly_name": "Expert-comptable",
        "rank": 6,
        "notes": "Meilleure cible long terme ; prudents ; pic jan–mai ; angle facture électronique.",
    },
    {
        "preset_id": "dentistes_cabinet_groupe",
        "instantly_name": "Dentiste cabinet de groupe",
        "rank": 7,
        "notes": "Plusieurs associés ; souvent saturés patients.",
    },
    {
        "preset_id": "avocats",
        "instantly_name": "Avocat d'affaires",
        "rank": 8,
        "notes": "Cabinet structuré ; décision collégiale ; cycle long.",
    },
    {
        "preset_id": "notaires",
        "instantly_name": "Notaire",
        "rank": 9,
        "notes": "Institutionnel ; faible appétit ; signature la plus lente.",
    },
)


def queue_preset_ids() -> list[str]:
    return [entry["preset_id"] for entry in NICHE_SCRAPE_QUEUE]
