"""Shared legal markdown sources for the reply agent knowledge pack."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LEGAL_DOC_ROOT = _REPO_ROOT / "app" / "(marketing)" / "content" / "legal-documentation"
_DOC_DIR = _REPO_ROOT / "app" / "(legacy)" / "content" / "tech"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _cgv_path(audience: str) -> Path:
    return _LEGAL_DOC_ROOT / audience / "cgv.md"


def _faq_path(audience: str) -> Path:
    return _LEGAL_DOC_ROOT / audience / "faq.json"


def legal_audience_from_niche_preset(niche_preset_id: str) -> str:
    ident = niche_preset_id.strip().lower()
    if "comptable" in ident:
        return "comptable"
    if (
        "prevoyance" in ident
        or "prévoyance" in ident
        or "courtiers" in ident
        or "courtier" in ident
        or ident == "ias"
        or ident.startswith("ias_")
    ):
        return "assurance"
    if (
        "gestion_patrimoine" in ident
        or "conseiller" in ident
        or ident == "cif"
        or ident.startswith("cif_")
    ):
        return "cif"
    if (
        "jum" in ident
        or "restaurant" in ident
        or "btp" in ident
        or "terrassement" in ident
        or "dentiste" in ident
        or "medecin" in ident
        or "kine" in ident
        or "avocat" in ident
        or "architecte" in ident
        or "veterinaire" in ident
    ):
        return "jum"
    return "agence"


def is_comptable_niche_preset(niche_preset_id: str) -> bool:
    return legal_audience_from_niche_preset(niche_preset_id) == "comptable"


def is_cif_niche_preset(niche_preset_id: str) -> bool:
    return legal_audience_from_niche_preset(niche_preset_id) == "cif"


def is_assurance_niche_preset(niche_preset_id: str) -> bool:
    return legal_audience_from_niche_preset(niche_preset_id) == "assurance"


def is_jum_niche_preset(niche_preset_id: str) -> bool:
    return legal_audience_from_niche_preset(niche_preset_id) == "jum"


def get_cvg_markdown(*, audience: str = "buyer") -> str:
    if audience == "seller":
        path = _cgv_path("entreprise")
    else:
        path = _cgv_path("agence")
    if not path.is_file():
        path = _LEGAL_DOC_ROOT / "_shared" / "cgv.md"
    return _read_text(path)


def get_mentions_legales_markdown() -> str:
    return _read_text(_LEGAL_DOC_ROOT / "_shared" / "mentions-legales.md")


def get_confidentialite_markdown() -> str:
    return _read_text(_LEGAL_DOC_ROOT / "_shared" / "confidentialite.md")


def _with_partner_due_diligence(audience: str, body: str) -> str:
    if audience not in {"comptable", "cif", "assurance"}:
        return body
    shared = _read_text(_DOC_DIR / "ai-reply-knowledge-partner-dd-shared.md")
    return f"{body.strip()}\n\n{shared.strip()}\n"


def get_ai_reply_knowledge_markdown(*, audience: str = "agence") -> str:
    if audience == "comptable":
        return _with_partner_due_diligence(
            audience, _read_text(_DOC_DIR / "ai-reply-knowledge-comptable.md")
        )
    if audience == "cif":
        return _with_partner_due_diligence(
            audience, _read_text(_DOC_DIR / "ai-reply-knowledge-cif.md")
        )
    if audience == "assurance":
        return _with_partner_due_diligence(
            audience, _read_text(_DOC_DIR / "ai-reply-knowledge-ias.md")
        )
    if audience == "jum":
        jum_path = _DOC_DIR / "ai-reply-knowledge-jum.md"
        if jum_path.is_file():
            return _read_text(jum_path)
    return _read_text(_DOC_DIR / "ai-reply-knowledge.md")


def build_legal_knowledge_markdown(*, audience: str = "buyer") -> str:
    """Full legal bundle for site sync — not used in Grok knowledge pack."""
    return "\n".join(
        [
            "# Legal knowledge (ground truth)",
            "",
            "## Conditions Générales de Vente",
            get_cvg_markdown(audience=audience),
            "",
            "## Mentions légales",
            get_mentions_legales_markdown(),
            "",
            "## Politique de confidentialité",
            get_confidentialite_markdown(),
        ]
    )


def extract_entreprise_faq(markdown: str) -> str:
    start = markdown.find("### Questions entreprise")
    if start < 0:
        return ""
    after_start = markdown[start:]
    hr_match = re.search(r"\n---\n", after_start)
    section = after_start[: hr_match.start()] if hr_match else after_start
    rows: list[str] = []
    for line in section.split("\n"):
        match = re.match(r"^\|\s*E\d+\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|$", line)
        if match:
            rows.append(f"Q: {match.group(1)}\nA: {match.group(2)}")
    return "\n\n".join(rows)


def format_faq_for_audience(audience: str) -> str:
    faq_path = _faq_path(audience)
    if not faq_path.is_file():
        return ""
    data = json.loads(faq_path.read_text(encoding="utf-8"))
    entries = data.get("entries") or []
    rows: list[str] = []
    for entry in entries:
        question = str(entry.get("question") or "").strip()
        answer = str(entry.get("answer") or "").strip()
        if question and answer:
            rows.append(f"Q: {question}\nA: {answer}")
    return "\n\n".join(rows)


def format_comptable_faq() -> str:
    return format_faq_for_audience("comptable")


def _speaking_to_label(target_type: str, audience: str) -> str:
    if audience == "comptable":
        return "cabinet EC (Buyer)" if target_type == "buyer" else "dirigeant TPE (Seller)"
    if audience == "cif":
        return "cabinet CIF (Buyer)" if target_type == "buyer" else "dirigeant PME (Seller)"
    if audience == "assurance":
        return (
            "cabinet IAS / courtier ORIAS (Buyer)"
            if target_type == "buyer"
            else "dirigeant PME (Seller)"
        )
    if audience == "jum":
        return "prospect JUM (restaurant, dirigeant, dentiste)"
    return "agence (Buyer)" if target_type == "buyer" else "entreprise (Seller)"


@lru_cache(maxsize=32)
def build_knowledge_pack_cached(
    niche_preset_id: str,
    target_type: str,
    niche_angle: str,
    niche_effectif: str,
) -> str:
    return _build_knowledge_pack_uncached(
        niche_preset_id=niche_preset_id,
        target_type=target_type,
        niche_angle=niche_angle,
        niche_effectif=niche_effectif,
    )


def _build_knowledge_pack_uncached(
    *,
    niche_preset_id: str,
    target_type: str,
    niche_angle: str,
    niche_effectif: str,
) -> str:
    audience = legal_audience_from_niche_preset(niche_preset_id)
    pack_audience = (
        audience if audience in {"comptable", "cif", "assurance", "jum"} else "agence"
    )
    ai_reply_knowledge = get_ai_reply_knowledge_markdown(audience=pack_audience)
    overview = (_DOC_DIR / "00-overview.md").read_text(encoding="utf-8")

    if pack_audience == "comptable":
        faq_section = format_comptable_faq()
        faq_heading = "## FAQ comptable (Buyer/Seller)"
        faq_fallback = "Cabinet > 3 associés. Dirigeant TPE : service gratuit."
    elif pack_audience == "cif":
        faq_section = format_faq_for_audience("cif")
        faq_heading = "## FAQ CIF (Buyer/Seller)"
        faq_fallback = "Cabinet CIF min. 2 associés. Dirigeant PME : service gratuit."
    elif pack_audience == "assurance":
        faq_section = format_faq_for_audience("assurance")
        faq_heading = "## FAQ IAS / assurance (Buyer/Seller)"
        faq_fallback = "Cabinet courtage ORIAS. Dirigeant : service gratuit."
    elif pack_audience == "jum":
        faq_section = format_faq_for_audience("jum")
        if not faq_section:
            jum_content = _REPO_ROOT / "app" / "(marketing)" / "content" / "faq" / "jum.json"
            if jum_content.is_file():
                data = json.loads(jum_content.read_text(encoding="utf-8"))
                rows = []
                for entry in data.get("entries") or []:
                    q = str(entry.get("question") or "").strip()
                    a = str(entry.get("answer") or "").strip()
                    if q and a:
                        rows.append(f"Q: {q}\nA: {a}")
                faq_section = "\n\n".join(rows)
        faq_heading = "## FAQ JUM Advisory"
        faq_fallback = "JUM Advisory — accompagnement comptable restaurants, BTP, dentistes."
    else:
        deliverance_path = _DOC_DIR / "deliverance" / "front-client.md"
        if deliverance_path.is_file():
            faq_section = extract_entreprise_faq(
                deliverance_path.read_text(encoding="utf-8")
            )
        else:
            faq_section = format_faq_for_audience("entreprise")
        faq_heading = "## Entreprise FAQ (Seller)"
        faq_fallback = "Entreprise service is free. No commission. Calendly via email."

    parts = [
        "# Knowledge pack (ground truth only — do not invent facts outside this pack)",
        "",
        "## Product overview",
        overview[:4000],
        "",
        "## Reply-safe facts (condensed)",
        ai_reply_knowledge,
        "",
        faq_heading,
        faq_section or faq_fallback,
        "",
        "## Niche context",
        f"Preset: {niche_preset_id}",
        f"Angle: {niche_angle}",
    ]
    if niche_effectif:
        parts.append(f"Target size: {niche_effectif}")
    parts.append(f"Speaking to: {_speaking_to_label(target_type, pack_audience)}")
    return "\n".join(parts)
