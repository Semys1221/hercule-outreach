# Revue manuelle — borderline `taxonomy_mismatch` (pipe vol EC)

Échantillon de 10 leads classés **borderline** par [`audit_filter.py`](../audit_filter.py) sur les données VPS du 2026-09-07 (`filter_audit.csv`, 66 borderline au total).

Verdicts : **vrai EC** | **non-EC crédible** | **bruit**

| # | Entreprise | Taxonomy Outscraper | Verdict | Notes |
|---|------------|---------------------|---------|-------|
| 1 | Amarris Expertise Comptable ST MALO | Service de comptabilité | **vrai EC** | Cabinet Amarris inscrit Ordre EC, bureau Saint-Malo (Océane Thouanel). Google tague « Service de comptabilité » — **faux négatif taxonomy**. Keyword `service de comptabilité` récupérerait ce lead. |
| 2 | Agilea Conseil - Vendée | Service de comptabilité | **vrai EC** | OEC n°33449, NAF 69.20Z, site agileaconseil.com — cabinet EC fondé 2023. **Faux négatif taxonomy** (même cause qu'Amarris). |
| 3 | Mandare | Service de comptabilité | **non-EC crédible** | Plateforme SaaS compta + accompagnement optionnel ; pas un cabinet EC indépendant classique. Rejet **correct** pour la cible « cabinets EC ». |
| 4 | Office Experts Patrimoine | Conseiller financier (+ fiscal) | **bruit** | Gestion de patrimoine / investissement, pas cabinet d'expertise comptable. Rejet **correct**. |
| 5 | Alexia Compta | Service de comptabilité | **non-EC crédible** | Offre low-cost en ligne (forfaits 59–149 €/mois) ; pas un cabinet EC ordinaire. Rejet **acceptable**. |
| 6 | Expert Impôts | Conseiller fiscal | **bruit** | Plateforme de défiscalisation patrimoniale (B2C), pas EC entreprise. Rejet **correct**. |
| 7 | Norak | Conseiller en gestion des affaires | **non-EC crédible** | Conseil en gestion / accompagnement dirigeants, pas cabinet EC. Rejet **correct**. |
| 8 | CALM - Cabinet Administratif | Service de préparation déclarations fiscales | **non-EC crédible** | Cabinet administratif / déclaratif, pas expertise comptable ordinaire. Rejet **acceptable**. |
| 9 | ADGestion 81 | Service d'administration + comptabilité | **non-EC crédible** | Assistante administrative indépendante, pas cabinet EC. Rejet **correct**. |
| 10 | VILOGI | Logiciel + service de comptabilité | **bruit** | Éditeur logiciel immobilier/compta, pas cabinet EC. Rejet **correct**. |

## Synthèse

| Verdict | Count (échantillon 10) |
|---------|------------------------|
| vrai EC | **2** (20%) |
| non-EC crédible | 4 |
| bruit | 4 |

Sur l'échantillon, **2/10 borderline sont de vrais cabinets EC** mal tagués par Google (`Service de comptabilité`). En extrapolant grossièrement sur 66 borderline → ~13 leads EC manqués — faible vs 2 808 acceptés (~0,5% du volume).

**Recommandation taxonomy (hors CAC, confirmé exclus) :**

- Envisager `service de comptabilité` dans `TAXONOMY_INCLUDED_KEYWORDS` **uniquement si** on accepte aussi des prestataires compta non-EC (Mandare, Alexia Compta, etc.).
- Alternative plus sûre : garder la taxonomy stricte ; les vrais EC mal tagués passent déjà quand Google met `Expert-comptable` en type (majorité des acceptés).
- Ne **pas** élargir sur le nom Google — les faux positifs (recrutement « expert-comptable », agences web) restent nombreux.

## Rejouer l'audit

```bash
cd lib/backend/streamlit_scraper
python main.py audit-filter --preset cabinets_expertise_comptable_fresh_geo
# ou sur copie VPS :
python lib/backend/scripts/audit_filter.py --preset cabinets_expertise_comptable_fresh_geo --out-dir /path/to/output --json
```

Génère `taxonomy_review.csv` (borderline) et affiche le breakdown Reason + batch acceptance depuis `scrape.log`.
