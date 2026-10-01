"""Default Instantly bypass email copy for new campaign bootstrap."""

OPT_OUT_DISCLAIMER_HTML = (
    "<br/><br/><i>Répondez non si vous ne souhaitez plus de messages.</i>"
)

COMPTABLE_E1_BODY_HTML = """<p>Voici plus de précisions.<br/><br/>L'un des groupes de clients que nous avons actuellement regroupe des PME et dirigeants en recherche d'un accompagnement en tenue comptable, social / paie et conseil fiscal.<br/><br/>Ces demandes sont transmises à nos cabinets partenaires.<br/><br/>Pour recevoir ce type de contrat, votre cabinet doit compter au minimum 2 associés ou collaborateurs.<br/><br/>Les échanges entre cabinet et clients démarrent le 02 oct. dans la limite des attributions.<br/><br/><a href="{{reservation_link}}">Proposer mon cabinet</a><br/><br/>{{accountSignature}}</p>"""

COMPTABLE_E2_BODY_HTML = f"""<p>Bonjour,<br/><br/>Je reviens vers vous sur les demandes en attente — PME et dirigeants en recherche de tenue comptable, social / paie et conseil.<br/><br/>Les échanges entre cabinet et clients démarrent le 02 oct. dans la limite des attributions.<br/><br/>Êtes-vous disponible le {{{{slot_1}}}} ou le {{{{slot_2}}}} ?<br/><br/><a href="{{{{reservation_link}}}}">Proposer mon cabinet</a>{OPT_OUT_DISCLAIMER_HTML}<br/><br/>{{{{accountSignature}}}}</p>"""

COMPTABLE_E3_BODY_HTML = f"""<p>Bonjour {{{{first_name}}}},<br/><br/>N'ayant pas reçu de retour de votre part, je me dois de clôturer nos échanges ici.<br/><br/>Si le sujet devient pertinent pour votre cabinet à l'avenir, vous pourrez simplement revenir vers moi.<br/><br/>Bonne continuation,{OPT_OUT_DISCLAIMER_HTML}<br/><br/>{{{{accountSignature}}}}</p>"""

# Bootstrap default for generic/new campaigns (comptable-shaped E1).
DEFAULT_E1_BODY_HTML = COMPTABLE_E1_BODY_HTML

DEFAULT_E2_BODY_HTML = COMPTABLE_E2_BODY_HTML

DEFAULT_E3_BODY_HTML = COMPTABLE_E3_BODY_HTML

COMPTABLE_TEMPLATE_BODIES: dict[str, str] = {
    "interested_email1": COMPTABLE_E1_BODY_HTML,
    "interested_email2": COMPTABLE_E2_BODY_HTML,
    "interested_email3": COMPTABLE_E3_BODY_HTML,
}

COMPTABLE_TEMPLATE_SUBJECTS: dict[str, str] = {
    "interested_email1": "",
    "interested_email2": "Relance — demandes tenue comptable en attente",
    "interested_email3": "Dernier message",
}

AVOCAT_AFFAIRES_E1_BODY_HTML = """<p>Pour faire simple,<br/><br/>Nous avons des demandes de PME et startups de 5 à 50 salariés, sur des sujets de droit des sociétés et de contrats (transmission, cession, structuration).<br/><br/>Les échanges entre cabinet et clients démarrent le 02 oct. dans la limite des attributions.<br/><br/>Si vous souhaitez que nous vous mettions en relation avec ces clients : <a href="{{reservation_link}}">Mon cabinet est compatible</a><br/><br/>{{accountSignature}}</p>"""

AVOCAT_AFFAIRES_E2_BODY_HTML = f"""<p>Bonjour,<br/><br/>Je reviens vers vous sur les demandes en attente — transmission et cession de PME de 10 à 50 salariés.<br/><br/>Les échanges entre cabinet et clients démarrent le 02 oct. dans la limite des attributions.<br/><br/>Êtes-vous disponible le {{{{slot_1}}}} ou le {{{{slot_2}}}} ?<br/><br/><a href="{{{{reservation_link}}}}">Proposer mon cabinet</a>{OPT_OUT_DISCLAIMER_HTML}<br/><br/>{{{{accountSignature}}}}</p>"""

AVOCAT_AFFAIRES_E3_BODY_HTML = f"""<p>Bonjour {{{{first_name}}}},<br/><br/>N'ayant pas reçu de retour de votre part, je me dois de clôturer nos échanges ici.<br/><br/>Si le sujet devient pertinent pour votre cabinet à l'avenir, vous pourrez simplement revenir vers moi.<br/><br/>Bonne continuation,{OPT_OUT_DISCLAIMER_HTML}<br/><br/>{{{{accountSignature}}}}</p>"""

AVOCAT_AFFAIRES_TEMPLATE_BODIES: dict[str, str] = {
    "interested_email1": AVOCAT_AFFAIRES_E1_BODY_HTML,
    "interested_email2": AVOCAT_AFFAIRES_E2_BODY_HTML,
    "interested_email3": AVOCAT_AFFAIRES_E3_BODY_HTML,
}

AVOCAT_AFFAIRES_TEMPLATE_SUBJECTS: dict[str, str] = {
    "interested_email1": "",
    "interested_email2": "Relance — demandes transmission et cession PME",
    "interested_email3": "Dernier message",
}

AGENCES_IMMO_E1_BODY_HTML = """<p>Pour faire simple,<br/><br/>Nous avons des demandes de propriétaires vendeurs et d'investisseurs (biens de 250&nbsp;000&nbsp;€ et plus), qui souhaitent vendre rapidement et au juste prix.<br/><br/>L'accompagnement recherché porte sur l'estimation du bien, la mise en vente et la négociation jusqu'à la signature.<br/><br/>Si vous souhaitez que nous vous mettions en relation avec ces vendeurs : <a href="{{reservation_link}}">Mon agence est compatible</a><br/><br/>L'appel se réalisera le mercredi 08 octobre à 10h.</p>"""

AGENCES_IMMO_E2_BODY_HTML = """<p>Bonjour,<br/><br/>Je reviens vers vous sur les demandes en attente : des investisseurs et des propriétaires bailleurs qui souhaitent vendre une maison ou un appartement dans votre secteur.<br/><br/>Êtes-vous disponible le mercredi 08 octobre à 10h.<br/><br/><a href="{{reservation_link}}">Mon agence est compatible</a><br/><br/>{{accountSignature}}</p>"""

AGENCES_IMMO_E3_BODY_HTML = """<p>Bonjour {{first_name}},<br/><br/>N'ayant pas reçu de retour de votre part, je me dois de clôturer nos échanges ici.<br/><br/>Si le sujet devient pertinent pour votre agence à l'avenir, vous pourrez simplement revenir vers moi.<br/><br/>Bonne continuation,<br/><br/>{{accountSignature}}</p>"""

AGENCES_IMMOBILIERES_TEMPLATE_BODIES: dict[str, str] = {
    "interested_email1": AGENCES_IMMO_E1_BODY_HTML,
    "interested_email2": AGENCES_IMMO_E2_BODY_HTML,
    "interested_email3": AGENCES_IMMO_E3_BODY_HTML,
}

AGENCES_IMMOBILIERES_TEMPLATE_SUBJECTS: dict[str, str] = {
    "interested_email1": "",
    "interested_email2": "Relance — vendeurs et investisseurs en attente",
    "interested_email3": "Dernier message",
}

NICHE_SUBSEQUENCE_CAMPAIGNS: dict[str, dict[str, str]] = {
    "avocats": {
        "campaign_id": "8c3aee0c-5eeb-4c5c-9a6a-a9c79b4b936c",
        "campaign_name": "Avocat d'affaires",
    },
    "agences_immobilieres": {
        "campaign_id": "93c2e56f-4088-4495-94da-7891153e3947",
        "campaign_name": "Agence immobilière",
    },
    "cabinets_expertise_comptable": {
        "campaign_id": "5591a068-75f9-4826-8564-4dc2acc74bd4",
        "campaign_name": "Expert-comptable",
    },
}

AGENCE_WEB_2_PIPELINE_BASE_URL = "https://www.hercule.dev/email/agence/pipeline"

AGENCE_WEB_2_PIPELINE_IMAGES_HTML = "".join(
    f'<img src="{AGENCE_WEB_2_PIPELINE_BASE_URL}/pipeline-{index}.png" '
    f'alt="Aperçu pipeline {index}" '
    f'style="max-width:100%;display:block;margin:12px 0;" />'
    for index in range(1, 6)
)

AGENCE_WEB_2_TEMPLATE_BODIES: dict[str, str] = {
    "interested_email1": f"""<p>Bonjour,<br/><br/>Les rendez-vous actuellement planifiés sont visibles ci-dessous.<br/><br/>Il s'agit de PME, de cabinets comptables et de conseillers financiers.<br/><br/>Nous générons actuellement 5 rendez-vous par jour, et 29 rendez-vous sont déjà planifiés.<br/><br/>L'accès illimité au pipeline est proposé à 1 200 € forfaitaires pour le premier mois.<br/><br/>Nous n'acceptons qu'une seule agence.<br/><br/>Pour postuler, répondez mercredi ou jeudi afin que nous puissions vous présenter le Calendly et le fonctionnement du pipeline lors d'un appel en visioconférence.<br/><br/>{AGENCE_WEB_2_PIPELINE_IMAGES_HTML}<br/><br/>Cordialement,<br/>{{{{accountSignature}}}}</p>""",
    "interested_email2": f"""<p>Bonjour,<br/><br/>Je reviens vers vous sur l'accès au pipeline de rendez-vous visio (PME, cabinets comptables, conseillers financiers).<br/><br/>Nous générons environ 5 rendez-vous par jour — 29 sont déjà planifiés.<br/><br/>L'accès illimité reste à 1 200 € forfaitaires le premier mois. Une seule agence sera retenue.<br/><br/>Êtes-vous disponible mercredi ou jeudi pour un appel visio (présentation Calendly + fonctionnement du pipeline) ?<br/><br/>Répondez simplement avec le jour qui vous convient.{OPT_OUT_DISCLAIMER_HTML}<br/><br/>Cordialement,<br/>{{{{accountSignature}}}}</p>""",
    "interested_email3": f"""<p>Bonjour {{{{first_name}}}},<br/><br/>N'ayant pas reçu de retour de votre part, je clôture ici la candidature pour l'accès au pipeline.<br/><br/>Si le sujet redevient pertinent pour votre agence, vous pourrez simplement répondre à cet email.<br/><br/>Bonne continuation,{OPT_OUT_DISCLAIMER_HTML}<br/><br/>{{{{accountSignature}}}}</p>""",
}

JUM_OPT_OUT = (
    "<br/><br/><i>Répondez non si vous ne souhaitez plus de messages.</i>"
)

JUM_E2_BODY_HTML = f"""<p>Bonjour,<br/><br/>Je reviens vers vous suite à mon précédent message — avez-vous eu l'occasion d'y jeter un œil ?<br/><br/>Si le sujet vous parle, vous pouvez réserver un créneau ici : <a href="{{{{reservation_link}}}}">Réserver un créneau</a>{JUM_OPT_OUT}<br/><br/>{{{{accountSignature}}}}</p>"""

JUM_E3_BODY_HTML = f"""<p>Bonjour {{{{first_name}}}},<br/><br/>N'ayant pas reçu de retour de votre part, je clôture nos échanges ici.<br/><br/>Si le sujet devient pertinent pour vous à l'avenir, vous pourrez simplement revenir vers moi.<br/><br/>Bonne continuation,{JUM_OPT_OUT}<br/><br/>{{{{accountSignature}}}}</p>"""

JUM_TEMPLATE_BODIES: dict[str, str] = {
    "interested_email1_restaurant": """<p>Voici plus de précisions.<br/><br/>Votre comptable vous annonce combien votre restaurant gagne. Mais vous ignorez où il perd de l'argent.<br/><br/>Plutôt que d'attendre patiemment, nous aidons les restaurants à doubler leur marge en 3 mois grâce à une comptabilité active qui réduit vos charges, sans que vous ayez à tout gérer vous-même.<br/><br/>Pour voir ce que vous pourriez récupérer dès ce mois-ci : <a href="{{reservation_link}}">réservez un échange</a>.<br/><br/>Béatrice Meyer</p>""",
    "interested_email1_b2b": """<p>L'étude prendra environ 20 minutes.<br/><br/>À l'issue, vous saurez directement s'il vous est possible de ne plus avoir à avancer vous-même les frais de vos chantiers.<br/><br/>Si c'est accessible à votre situation, nous vous expliquerons ensuite les possibilités adaptées.<br/><br/>Vous pouvez choisir directement un créneau ici : <a href="{{reservation_link}}">Choisir un créneau</a><br/><br/>Béatrice Meyer</p>""",
    "interested_email1_dentiste": """<p>Bonjour,<br/><br/>Les cotisations bloquent une partie de vos honoraires, mais plusieurs leviers réglementaires permettent de réduire la taxe à 30 % à 41 % avant le prélèvement final.<br/><br/>Pour vérifier si votre structure est éligible aux critères mis en vigueur par la DGFiP, nous validons l'étude de votre dossier lors d'un entretien individuel.<br/><br/>Votre première étude se déroulera à distance avec un consultant agréé par l'AMF.<br/><br/>Réserver votre échange : <a href="{{reservation_link}}">Réserver votre échange</a><br/><br/>{{accountSignature}}</p>""",
    "interested_email1_medecin": """<p>Note reçue.<br/><br/>Les cotisations bloquent une partie de vos honoraires, mais plusieurs leviers réglementaires permettent d'intercepter la taxe à 30 % à 41 % avant le prélèvement final.<br/><br/>Pour vérifier si votre structure est éligible aux critères mis en vigueur par la DGFiP, nous validons l'étude de votre dossier lors d'un entretien individuel.<br/><br/>Votre première étude se déroulera à distance avec un consultant agréé par l'AMF.<br/><br/>Réserver votre échange : <a href="{{reservation_link}}">Réserver votre échange</a><br/><br/>Béatrice Meyer<br/>Secrétaire Famille Marceau<br/>Famille Marceau — Bureau Interprofessionnelle de Régulation Fiscale<br/>famillemarceau.fr</p>""",
    "interested_email1_kine": """<p>Bonjour,<br/><br/>Les cotisations bloquent une partie de vos honoraires, mais plusieurs leviers réglementaires permettent de réduire la taxe à 30 % à 41 % avant le prélèvement final.<br/><br/>Pour vérifier si votre cabinet de kinésithérapie est éligible aux critères mis en vigueur par la DGFiP, nous validons l'étude de votre dossier lors d'un entretien individuel.<br/><br/>Votre première étude se déroulera à distance avec un consultant agréé par l'AMF.<br/><br/>Réserver votre échange : <a href="{{reservation_link}}">Réserver votre échange</a><br/><br/>{{accountSignature}}</p>""",
    "interested_email1_avocat": """<p>Bonjour,<br/><br/>Les cotisations bloquent une partie de vos honoraires, mais plusieurs leviers réglementaires permettent de réduire la taxe à 30 % à 41 % avant le prélèvement final.<br/><br/>Pour vérifier si votre cabinet d'avocats est éligible aux critères mis en vigueur par la DGFiP, nous validons l'étude de votre dossier lors d'un entretien individuel.<br/><br/>Votre première étude se déroulera à distance avec un consultant agréé par l'AMF.<br/><br/>Réserver votre échange : <a href="{{reservation_link}}">Réserver votre échange</a><br/><br/>{{accountSignature}}</p>""",
    "interested_email1_architecte": """<p>Bonjour,<br/><br/>Les cotisations bloquent une partie de vos honoraires, mais plusieurs leviers réglementaires permettent de réduire la taxe à 30 % à 41 % avant le prélèvement final.<br/><br/>Pour vérifier si votre cabinet d'architecture est éligible aux critères mis en vigueur par la DGFiP, nous validons l'étude de votre dossier lors d'un entretien individuel.<br/><br/>Votre première étude se déroulera à distance avec un consultant agréé par l'AMF.<br/><br/>Réserver votre échange : <a href="{{reservation_link}}">Réserver votre échange</a><br/><br/>{{accountSignature}}</p>""",
    "interested_email1_veterinaire": """<p>Bonjour,<br/><br/>Les cotisations bloquent une partie de vos honoraires, mais plusieurs leviers réglementaires permettent de réduire la taxe à 30 % à 41 % avant le prélèvement final.<br/><br/>Pour vérifier si votre clinique vétérinaire est éligible aux critères mis en vigueur par la DGFiP, nous validons l'étude de votre dossier lors d'un entretien individuel.<br/><br/>Votre première étude se déroulera à distance avec un consultant agréé par l'AMF.<br/><br/>Réserver votre échange : <a href="{{reservation_link}}">Réserver votre échange</a><br/><br/>{{accountSignature}}</p>""",
    "interested_email1": """<p>Bonjour,<br/><br/>Les dirigeants que nous accompagnons ont souvent le problème suivant : ils doivent avancer les salaires et les fournisseurs pendant plusieurs semaines avant que leurs clients ne les paient.<br/><br/>Il existe des leviers légaux permettant de réduire ce décalage.<br/><br/><strong>Cliquez ici pour résoudre ce problème rapidement :</strong> <a href="{{reservation_link}}">Réserver un créneau</a><br/><br/>{{accountSignature}}</p>""",
    "interested_email2": JUM_E2_BODY_HTML,
    "interested_email3": JUM_E3_BODY_HTML,
}

CIF_TEMPLATE_BODIES: dict[str, str] = {
    "interested_email1": """<p>Pour faire simple,<br/><br/>Nous avons des demandes de cabinets de dentistes et vétérinaires (2+ salariés), confrontés à des enjeux de croissance, trésorerie et pression fiscale.<br/><br/>L'expertise recherchée porte sur le placement des avoirs professionnels et privés et la réduction de la pression fiscale.<br/><br/>Les échanges entre cabinet et clients démarrent le 02 oct. dans la limite des attributions.<br/><br/>Si vous souhaitez que nous vous mettions en relation avec ces cabinets : <a href="{{reservation_link}}">Mon cabinet est compatible</a><br/><br/>L'appel de présentation de Hercule sera réalisé ce mercredi 23 septembre à 10h (heure de Paris).<br/><br/>{{accountSignature}}</p>""",
    "interested_email2": f"""<p>Bonjour,<br/><br/>Je reviens vers vous sur les demandes en attente — cabinets dentistes/vétérinaires (2+ salariés), enjeux trésorerie et fiscalité.<br/><br/>Les échanges entre cabinet et clients démarrent le 02 oct. dans la limite des attributions.<br/><br/>Disponible le {{{{slot_1}}}} ou le {{{{slot_2}}}} ?<br/><br/><a href="{{{{reservation_link}}}}">Mon cabinet est compatible</a>{OPT_OUT_DISCLAIMER_HTML}<br/><br/>{{{{accountSignature}}}}</p>""",
    "interested_email3": DEFAULT_E3_BODY_HTML.replace("{{reservation_link}}", "{{reservation_link}}"),
}
