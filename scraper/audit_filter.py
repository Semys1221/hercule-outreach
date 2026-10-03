"""Analyze filter_audit.csv — reason breakdown and taxonomy_mismatch classification."""

from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from core_logic import output_paths

# ── Preset-specific taxonomy analysis profiles ────────────────────────────────
# Each profile defines the marker lists used by classify_taxonomy_mismatch.
# The "default" profile is the backward-compatible expert-comptable analysis.

_PROFILES: dict[str, dict[str, list[str]]] = {
    "default": {
        "taxonomy_keywords": [
            "expert-comptable",
            "expert comptable",
            "expertise comptable",
            "cabinet d'expertise comptable",
            "cabinet comptable",
            "accounting firm",
            "chartered accountant",
            "comptable",
        ],
        "name_hints": [
            "expert-comptable",
            "expert comptable",
            "expertise comptable",
            "experts-comptables",
            "cabinet d'expertise comptable",
            "cabinet comptable",
        ],
        "borderline_markers": [
            "service de comptabilit",
            "comptabilité analytique",
            "tax preparation",
            "déclarations fiscales",
            "conseil fiscal",
            "conseiller fiscal",
            "audit financier",
            "services aux entreprises",
            "conseiller en gestion des affaires",
        ],
        "noise_markers": [
            "huissier",
            "assurance",
            "agence d'assurance",
            "compagnie d'assurance",
            "école",
            "ecole",
            "établissement d'enseignement",
            "centre de formation",
            "cabinet de recrutement",
            "agence de recrutement",
            "recruteur",
            "avocat",
            "cabinet d'avocats",
            "conseiller financier",
            "conseil en investissement",
            "agent immobilier",
            "expert immobilier",
            "expert en sinistres",
            "géomètre",
            "syndicat",
            "association ou organisation",
            "administration",
            "centre des impôts",
            "concepteur de sites",
            "agence d'intérim",
            "magasin d'informatique",
        ],
    },
    "btp_pme": {
        "taxonomy_keywords": [
            "entrepreneur en bâtiment",
            "société de construction",
            "entreprise de construction",
            "artisan bâtiment",
            "plombier",
            "électricien",
            "maçon",
            "carreleur",
            "couvreur",
            "menuisier",
            "charpentier",
            "chauffagiste",
            "btp",
            "génie civil",
        ],
        "name_hints": [
            "btp",
            "bâtiment",
            "construction",
            "rénovation",
            "travaux",
            "artisan",
        ],
        "borderline_markers": [
            "bureau d'études",
            "cabinet d'ingénierie",
            "maître d'œuvre",
            "ingénierie du bâtiment",
            "diagnostic immobilier",
        ],
        "noise_markers": [
            "magasin de matériaux",
            "négoce de matériaux",
            "grossiste",
            "distributeur",
            "architecte",
            "promoteur immobilier",
            "agence immobilière",
            "école",
            "centre de formation",
            "syndicat",
            "association",
            "administration",
            "assurance construction",
            "location d'équipement",
            "location de matériel",
        ],
    },
    "terrassement_vrd": {
        "taxonomy_keywords": [
            "terrassement",
            "terrassier",
            "vrd",
            "voirie",
            "travaux publics",
            "assainissement",
            "canalisation",
            "réseaux humides",
            "réseaux secs",
            "nivellement",
            "enrobé",
            "génie civil",
        ],
        "name_hints": [
            "terrassement",
            "terrassier",
            "vrd",
            "voirie",
            "assainissement",
            "canalisation",
            "réseaux",
        ],
        "borderline_markers": [
            "bureau d'études",
            "cabinet d'ingénierie",
            "maître d'œuvre",
            "ingénierie du bâtiment",
        ],
        "noise_markers": [
            "plombier",
            "électricien",
            "maçon",
            "couvreur",
            "menuisier",
            "magasin de matériaux",
            "négoce de matériaux",
            "grossiste",
            "distributeur",
            "location d'équipement",
            "location de matériel",
            "architecte",
            "promoteur immobilier",
            "agence immobilière",
            "école",
            "centre de formation",
            "syndicat",
            "association",
            "administration",
        ],
    },
}

# Backward-compatible module-level constants (expert-comptable profile)
_default = _PROFILES["default"]
_TAXONOMY_KEYWORDS: list[str] = _default["taxonomy_keywords"]
_NAME_EC_HINTS: list[str] = _default["name_hints"]
_NOISE_MARKERS: list[str] = _default["noise_markers"]
_BORDERLINE_MARKERS: list[str] = _default["borderline_markers"]

_BATCH_STATS_RE = re.compile(
    r"places=(\d+), emails=(\d+), accepted=(\d+), rejected=(\d+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TaxonomyBucket:
    label: str
    description: str


TAXONOMY_BUCKETS = {
    "cac_only": TaxonomyBucket(
        "cac_only",
        "Commissaire aux comptes sans mot-clé EC dans type/category/subtypes",
    ),
    "borderline": TaxonomyBucket(
        "borderline",
        "Catégorie proche mais non confirmée — revue manuelle recommandée",
    ),
    "name_ec_mismatch": TaxonomyBucket(
        "name_ec_mismatch",
        "Nom Google suggère le métier cible mais taxonomy Outscraper = autre métier",
    ),
    # Generic alias used by non-EC presets
    "name_mismatch": TaxonomyBucket(
        "name_mismatch",
        "Nom Google suggère le métier cible mais taxonomy Outscraper = autre métier",
    ),
    "noise": TaxonomyBucket(
        "noise",
        "Hors cible (magasin, grossiste, école, administration, architecture…)",
    ),
    "hard_excluded": TaxonomyBucket(
        "hard_excluded",
        "Rejeté par TAXONOMY_HARD_EXCLUDED_KEYWORDS avant vérification inclusion",
    ),
}


def _lower(*parts: str) -> str:
    return " ".join(p.strip().lower() for p in parts if p and str(p).strip())


def _matches_taxonomy_keywords(category: str) -> bool:
    text = category.lower()
    return any(kw in text for kw in _TAXONOMY_KEYWORDS)


def _name_suggests_ec(company: str) -> bool:
    name = company.lower()
    return any(hint in name for hint in _NAME_EC_HINTS)


def is_cac_only_taxonomy(text: str) -> bool:
    """True when taxonomy is CAC-only (no EC keyword in type/category/subtypes)."""
    cat = text.lower()
    if "commissaire aux comptes" not in cat:
        return False
    return not _matches_taxonomy_keywords(text)


def _is_cac_only(category: str) -> bool:
    return is_cac_only_taxonomy(category)


def instantly_lead_taxonomy_dict(lead: dict[str, Any]) -> dict[str, Any]:
    """Build Outscraper-shaped taxonomy fields from an Instantly lead payload."""
    payload = lead.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}
    return {
        "type": payload.get("type") or "",
        "category": payload.get("category") or "",
        "subtypes": payload.get("subtypes") or "",
    }


def is_instantly_lead_cac_only(lead: dict[str, Any]) -> bool:
    """True when Instantly lead taxonomy matches pure CAC (no EC keyword)."""
    from category_filter import taxonomy_text

    return is_cac_only_taxonomy(taxonomy_text(instantly_lead_taxonomy_dict(lead)))


def classify_taxonomy_mismatch(
    company: str,
    category: str,
    preset: str = "default",
) -> str:
    """Return bucket id for a taxonomy_mismatch row.

    Args:
        company: company name from the audit CSV.
        category: category/taxonomy text from the audit CSV.
        preset: profile key from ``_PROFILES`` (defaults to ``"default"``).
    """
    profile = _PROFILES.get(preset, _PROFILES["default"])
    taxonomy_keywords: list[str] = profile["taxonomy_keywords"]
    name_hints: list[str] = profile["name_hints"]
    borderline_markers: list[str] = profile["borderline_markers"]
    noise_markers: list[str] = profile["noise_markers"]

    cat = category.lower()
    company_l = company.lower()

    def _matches_tax(text: str) -> bool:
        return any(kw in text.lower() for kw in taxonomy_keywords)

    def _name_suggests_target(name: str) -> bool:
        return any(h in name.lower() for h in name_hints)

    # Expert-comptable specific: CAC-only bucket
    if preset == "default" and _is_cac_only(category):
        return "cac_only"

    if any(marker in cat or marker in company_l for marker in borderline_markers):
        return "borderline"

    if _name_suggests_target(company) and not _matches_tax(cat):
        return "name_mismatch"

    if any(marker in cat for marker in noise_markers):
        return "noise"

    if _name_suggests_target(company):
        return "name_mismatch"

    return "noise"


def _read_filter_audit(audit_path: str) -> list[dict[str, str]]:
    if not os.path.isfile(audit_path):
        raise FileNotFoundError(f"filter_audit not found: {audit_path}")
    with open(audit_path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _count_accepted(csv_path: str) -> int:
    if not os.path.isfile(csv_path):
        return 0
    with open(csv_path, newline="", encoding="utf-8") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def parse_scrape_log_batch_stats(log_path: str) -> list[dict[str, Any]]:
    if not os.path.isfile(log_path):
        return []
    batches: list[dict[str, Any]] = []
    batch_index = 0
    with open(log_path, encoding="utf-8") as handle:
        for line in handle:
            match = _BATCH_STATS_RE.search(line)
            if not match:
                continue
            places, emails, accepted, rejected = (int(match.group(i)) for i in range(1, 5))
            total = accepted + rejected
            batch_index += 1
            batches.append(
                {
                    "batch": batch_index,
                    "places": places,
                    "emails": emails,
                    "accepted": accepted,
                    "rejected": rejected,
                    "acceptance_rate": round(accepted / total * 100, 1) if total else 0.0,
                }
            )
    return batches


def analyze_filter_audit(
    preset: str,
    *,
    out_dir: str | None = None,
) -> dict[str, Any]:
    """Build audit report from preset output directory."""
    if out_dir is None:
        paths = output_paths(preset)
        audit_path = paths.filter_audit
        csv_path = paths.csv
        log_path = os.path.join(paths.out_dir, "scrape.log")
    else:
        audit_path = os.path.join(out_dir, "filter_audit.csv")
        csv_path = os.path.join(out_dir, "outscraper_leads.csv")
        log_path = os.path.join(out_dir, "scrape.log")

    rows = _read_filter_audit(audit_path)
    accepted = _count_accepted(csv_path)
    rejected = len(rows)
    total = accepted + rejected

    reason_counts: Counter[str] = Counter()
    taxonomy_buckets: Counter[str] = Counter()
    borderline_rows: list[dict[str, str]] = []

    for row in rows:
        reason = str(row.get("Reason") or "").strip()
        reason_counts[reason] += 1

        # Hard-excluded rows get their own bucket without further classification
        if reason.startswith("taxonomy_hard_excluded"):
            taxonomy_buckets["hard_excluded"] += 1
            continue

        if reason != "taxonomy_mismatch":
            continue

        bucket = classify_taxonomy_mismatch(
            str(row.get("Company") or ""),
            str(row.get("Category") or ""),
            preset=preset,
        )
        taxonomy_buckets[bucket] += 1
        if bucket == "borderline":
            borderline_rows.append(
                {
                    "Email": str(row.get("Email") or ""),
                    "Company": str(row.get("Company") or ""),
                    "Category": str(row.get("Category") or ""),
                    "Taxonomy_Bucket": bucket,
                    "Manual_Verdict": "",
                    "Notes": "",
                }
            )

    reason_breakdown = [
        {
            "reason": reason,
            "count": count,
            "pct_of_total": round(count / total * 100, 1) if total else 0.0,
            "pct_of_rejected": round(count / rejected * 100, 1) if rejected else 0.0,
        }
        for reason, count in reason_counts.most_common()
    ]

    all_buckets = ("hard_excluded", "noise", "cac_only", "borderline", "name_mismatch", "name_ec_mismatch")
    taxonomy_breakdown = [
        {
            "bucket": bucket,
            "label": TAXONOMY_BUCKETS[bucket].label,
            "description": TAXONOMY_BUCKETS[bucket].description,
            "count": taxonomy_buckets[bucket],
            "pct_of_tax_rejects": round(
                taxonomy_buckets[bucket]
                / max(sum(taxonomy_buckets[b] for b in all_buckets), 1)
                * 100,
                1,
            ),
        }
        for bucket in all_buckets
        if taxonomy_buckets[bucket]
    ]

    batch_stats = parse_scrape_log_batch_stats(log_path)

    # Taxonomy quality indicators
    tax_mismatch_total = reason_counts.get("taxonomy_mismatch", 0)
    tax_hard_excluded_total = sum(
        v for k, v in reason_counts.items() if k.startswith("taxonomy_hard_excluded")
    )
    tax_total = tax_mismatch_total + tax_hard_excluded_total
    tax_trash_rate = round(tax_total / total * 100, 1) if total else 0.0

    # Per-batch taxonomy trash rate from scrape.log metrics (if available)
    batch_tax_rates: list[dict[str, Any]] = []
    metrics_path = os.path.join(os.path.dirname(audit_path), "scrape_metrics.jsonl")
    if os.path.isfile(metrics_path):
        try:
            with open(metrics_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        evt = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if evt.get("event") != "batch_complete":
                        continue
                    rp = int(evt.get("raw_places") or 0)
                    tm = int(evt.get("taxonomy_mismatches") or 0)
                    if rp > 0:
                        batch_tax_rates.append(
                            {
                                "raw_places": rp,
                                "taxonomy_mismatches": tm,
                                "taxonomy_trash_rate_pct": round(tm / rp * 100, 1),
                                "taxonomy_hard_excluded": int(
                                    evt.get("taxonomy_hard_excluded") or 0
                                ),
                            }
                        )
        except OSError:
            pass

    return {
        "preset": preset,
        "audit_path": audit_path,
        "accepted": accepted,
        "rejected": rejected,
        "total": total,
        "acceptance_rate": round(accepted / total * 100, 1) if total else 0.0,
        "reason_breakdown": reason_breakdown,
        "taxonomy_mismatch_total": tax_mismatch_total,
        "taxonomy_hard_excluded_total": tax_hard_excluded_total,
        "taxonomy_total_rejected": tax_total,
        "taxonomy_trash_rate_pct": tax_trash_rate,
        "taxonomy_breakdown": taxonomy_breakdown,
        "borderline_rows": borderline_rows,
        "batch_stats": batch_stats,
        "batch_taxonomy_rates": batch_tax_rates,
        "review_csv_path": os.path.join(
            os.path.dirname(audit_path),
            "taxonomy_review.csv",
        ),
    }


def write_taxonomy_review_csv(report: dict[str, Any]) -> str:
    path = str(report["review_csv_path"])
    rows: list[dict[str, str]] = report.get("borderline_rows") or []
    fieldnames = ["Email", "Company", "Category", "Taxonomy_Bucket", "Manual_Verdict", "Notes"]
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def format_report_text(report: dict[str, Any]) -> str:
    from taxonomy_gate import TAXONOMY_TRASH_RATE_WARN

    warn_threshold_pct = int(TAXONOMY_TRASH_RATE_WARN * 100)
    tax_rate = float(report.get("taxonomy_trash_rate_pct") or 0)
    tax_flag = f"  ⚠️  TRASH RATE HIGH (>{warn_threshold_pct}%)" if tax_rate > warn_threshold_pct else ""

    lines = [
        f"Filter audit — preset {report['preset']}",
        f"  accepted:        {report['accepted']}",
        f"  rejected:        {report['rejected']}",
        f"  total:           {report['total']}",
        f"  acceptance rate: {report['acceptance_rate']}%",
        "",
        "Taxonomy quality:",
        f"  mismatch (soft): {report.get('taxonomy_mismatch_total', 0)}",
        f"  hard-excluded:   {report.get('taxonomy_hard_excluded_total', 0)}",
        f"  total taxonomy:  {report.get('taxonomy_total_rejected', 0)} "
        f"({tax_rate}% of all processed){tax_flag}",
        "",
        "Reason breakdown:",
    ]
    for item in report["reason_breakdown"]:
        lines.append(
            f"  {item['count']:5d} ({item['pct_of_total']:5.1f}% total, "
            f"{item['pct_of_rejected']:5.1f}% rejected)  {item['reason']}"
        )

    tax_breakdown = report.get("taxonomy_breakdown") or []
    if tax_breakdown:
        lines.append("")
        lines.append("Taxonomy mismatch breakdown:")
        for item in tax_breakdown:
            pct = item.get("pct_of_tax_rejects", 0)
            lines.append(
                f"  {item['count']:4d} ({pct:5.1f}%)  {item['bucket']}: {item['description']}"
            )

    # Per-batch taxonomy trash rates
    batch_tax = report.get("batch_taxonomy_rates") or []
    if batch_tax:
        lines.append("")
        lines.append("Per-batch taxonomy trash rate (from scrape_metrics.jsonl):")
        for idx, b in enumerate(batch_tax, 1):
            flag = "  ⚠️" if b["taxonomy_trash_rate_pct"] > warn_threshold_pct else ""
            lines.append(
                f"  batch {idx:3d}: {b['taxonomy_trash_rate_pct']:5.1f}% trash "
                f"({b['taxonomy_mismatches']}/{b['raw_places']} places, "
                f"hard-excl={b['taxonomy_hard_excluded']}){flag}"
            )

    batches = report.get("batch_stats") or []
    if batches:
        lines.append("")
        lines.append("Batch acceptance (from scrape.log):")
        for batch in batches:
            lines.append(
                f"  batch {batch['batch']}: {batch['acceptance_rate']}% "
                f"(acc={batch['accepted']} rej={batch['rejected']} places={batch['places']})"
            )

    review_path = report.get("review_csv_path")
    if review_path and report.get("borderline_rows"):
        lines.append("")
        lines.append(f"Borderline export: {review_path} ({len(report['borderline_rows'])} rows)")

    return "\n".join(lines)


def run_audit(
    preset: str,
    *,
    out_dir: str | None = None,
    write_review: bool = True,
    write_json: bool = False,
) -> dict[str, Any]:
    report = analyze_filter_audit(preset, out_dir=out_dir)
    if write_review and report["borderline_rows"]:
        write_taxonomy_review_csv(report)
    if write_json:
        json_path = os.path.join(os.path.dirname(report["audit_path"]), "audit_filter_report.json")
        payload = {k: v for k, v in report.items() if k != "borderline_rows"}
        payload["borderline_count"] = len(report.get("borderline_rows") or [])
        with open(json_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        report["json_path"] = json_path
    report["text"] = format_report_text(report)
    return report
