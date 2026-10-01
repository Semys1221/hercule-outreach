"""Scaffold AI Reply Agent prompt files for a new scraper niche."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPTS_DIR = _REPO_ROOT / "satellites" / "reply_agent" / "prompts"


def _niche_from_label(label: str) -> str:
    return label.replace(" (France)", "").strip().lower()


def _demande_phrase(niche: str) -> str:
    """Short demande label for the Sept 8–27 value line."""
    if "comptable" in niche:
        return "demandes contrats comptables"
    return f"demandes {niche}"


def _is_comptable(preset_id: str, niche: str) -> bool:
    return "comptable" in preset_id or "comptable" in niche


def scaffold_ai_reply_prompts(preset_id: str, label: str) -> list[str]:
    """Create buyer + seller prompt files if missing. Returns paths written."""
    _PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    niche = _niche_from_label(label)
    demande = _demande_phrase(niche)
    comptable = _is_comptable(preset_id, niche)
    written: list[str] = []

    buyer_path = _PROMPTS_DIR / f"{preset_id}_buyer.md"
    if not buyer_path.is_file():
        if comptable:
            buyer_body = f"""# {preset_id} — Buyer (cabinet EC)

Tu écris à un **cabinet d'expertise comptable** ({niche}) qui candidate pour recevoir des demandes via Hercule.

- Parle comme Béatrice Meyer.
- **Contexte** : Hercule reçoit des demandes d'indépendants et de dirigeants de TPE en reprise comptable, fiscal et administratif.
- **Éligibilité / bande passante** : seuil > 3 associés/collaborateurs = indicateur de capacité, pas refus auto ; visios qualifiantes (pas appels 10 min).
- **« Pas 3 collaborateurs »** : bande passante + sérieux ; inviter audit si capacité (sous-traitance stable OK).
- **Objection tarif** : valeur Starter + Lite en entrée si capacité ; hercule.dev/cvg/comptable pour détail.
- **Téléphone** : demander disponibilités, proposer visio Calendly — pas d'appel ad hoc.
- **Contexte Calendly** : si le bloc « Contexte Calendly » confirme un RDV, le mentionner explicitement ; ne pas inventer d'horaires ni d'URL hors contexte.
- **Apporteurs** : Hercule ne rémunère pas ; cabinet souscrit ; 0 % sur honoraires.
- **Valeur par défaut** : {demande} — **ne parle pas d'argent** sauf demande explicite.
- **Si question sur les prix** : renvoie vers hercule.dev/cvg/comptable **sans chiffrer**.
- CTA principal : {{reservation_link}} (« Proposer mon cabinet », avec urgence).
- Si la réponse n'est pas dans le knowledge pack, **n'envoie pas** (should_reply=false).
"""
        else:
            buyer_body = f"""# {preset_id} — Buyer (agence)

Tu écris à une **agence** ({niche}) qui candidate pour recevoir des contrats via Hercule.

- Parle comme Béatrice Meyer, relation agences partenaires.
- **Valeur par défaut** : les échanges entre agences partenaires et les {demande} ont lieu **du 8 au 27 septembre**. Insiste sur cette fenêtre — **ne parle pas d'argent** sauf demande explicite du prospect.
- **Si question sur les prix** : valeur d'abord (fenêtre 8–27 sept., contrats), puis l'offre Starter **sans écrire le montant**, et renvoie vers hercule.dev/cvg pour le détail tarifaire.
- CTA principal : {{reservation_link}} (réserver un audit / appel cette semaine, avec urgence).
- Si la réponse n'est pas dans le knowledge pack, **n'envoie pas** (should_reply=false).
"""
        buyer_path.write_text(buyer_body, encoding="utf-8")
        written.append(str(buyer_path))

    seller_path = _PROMPTS_DIR / f"{preset_id}_seller.md"
    if not seller_path.is_file():
        if comptable:
            seller_body = f"""# {preset_id} — Seller (dirigeant TPE)

Tu écris à un **dirigeant de TPE ou indépendant** ({niche}) qui cherche un accompagnement comptable via Hercule.

- Parle comme Béatrice Meyer, accompagnement gratuit pour le dirigeant.
- **Valeur par défaut** : mise en relation avec un cabinet adapté — service **gratuit** — **ne parle pas d'argent** sauf demande explicite.
- **Si question sur les prix** : rappeler que le dirigeant ne paie rien ; tarifs cabinet → hercule.dev/cvg/comptable **sans chiffrer**.
- CTA principal : {{reservation_link}} (créneau cette semaine, avec urgence).
- Si la réponse n'est pas dans le knowledge pack, **n'envoie pas** (should_reply=false).
"""
        else:
            seller_body = f"""# {preset_id} — Seller (entreprise)

Tu écris à une **entreprise** ({niche}) qui cherche une agence web via Hercule.

- Parle comme Béatrice Meyer, accompagnement gratuit pour l'entreprise.
- **Valeur par défaut** : la mise en relation avec une agence adaptée se fait dans la fenêtre **du 8 au 27 septembre**. Service **gratuit** pour l'entreprise — **ne parle pas d'argent** sauf demande explicite.
- **Si question sur les prix** : rappeler que l'entreprise ne paie rien ; si le prospect demande les tarifs côté agence, renvoyer vers hercule.dev/cvg **sans chiffrer**.
- CTA principal : {{reservation_link}} (créneau cette semaine, avec urgence).
- Si la réponse n'est pas dans le knowledge pack, **n'envoie pas** (should_reply=false).
"""
        seller_path.write_text(seller_body, encoding="utf-8")
        written.append(str(seller_path))

    return written
