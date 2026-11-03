"""Modèles de mails (F-52).
Les variables s'écrivent {nom} ; une variable inconnue est laissée telle quelle."""

import re
from datetime import date

# Clés des réglages (table settings) et modèles par défaut
TEMPLATE_KEYS = {
    "tech_proposal": "template_tech_proposal",
    "requester_confirmation": "template_requester_confirmation",
    "tech_cancellation": "template_tech_cancellation",
}

VARIABLES = (
    "demandeur",
    "type",
    "dates",
    "lieu",
    "lien_accepter",
    "lien_refuser",
    "technicien",
    "techniciens",
    "ref",
    "titre",
    "client",
    "cf",
)

LINK_PLACEHOLDERS = ("{lien_accepter}", "{lien_refuser}")

DEFAULT_TEMPLATES: dict[str, dict[str, str]] = {
    "tech_proposal": {
        "subject": "Proposition {ref} – {type} – {dates}",
        "body": (
            "Bonjour {technicien},\n\n"
            "Je vous propose l'activité suivante :\n"
            "- {type} : {titre}\n"
            "- Dates : {dates}\n"
            "- Lieu : {lieu}\n"
            "- Client : {client}\n"
            "- Demandeur : {demandeur}\n\n"
            "Merci de me donner votre réponse :\n"
            "J'accepte : {lien_accepter}\n"
            "Je refuse : {lien_refuser}\n\n"
            "Philippe"
        ),
    },
    "requester_confirmation": {
        "subject": "Confirmation {ref} – {titre}",
        "body": (
            "Bonjour {demandeur},\n\n"
            "Votre demande {ref} ({type}, {dates}, {lieu}) est confirmée.\n"
            "Technicien(s) : {techniciens}.\n\n"
            "Philippe"
        ),
    },
    "tech_cancellation": {
        "subject": "Annulation {ref} – {dates}",
        "body": (
            "Bonjour {technicien},\n\n"
            "L'activité {ref} ({type}, {dates}, {lieu}) qui vous avait été proposée "
            "ne vous est plus attribuée.\n"
            "Le lien de réponse précédent n'est plus valable.\n\n"
            "Philippe"
        ),
    },
}

_VAR = re.compile(r"\{([a-z_]+)\}")


def render(text: str, values: dict[str, str]) -> str:
    return _VAR.sub(lambda m: values.get(m.group(1), m.group(0)), text)


def format_dates(start: date | None, end: date | None) -> str:
    if start is None or end is None:
        return "dates à préciser"
    if start == end:
        return f"le {start:%d/%m/%Y}"
    return f"du {start:%d/%m/%Y} au {end:%d/%m/%Y}"


def missing_link_placeholders(body: str) -> list[str]:
    return [p for p in LINK_PLACEHOLDERS if p not in body]


def redact_links(body: str, accept_url: str, refuse_url: str) -> str:
    """Corps conservé après envoi : les liens (qui portent le jeton) ne sont jamais stockés (NF-02)."""
    return body.replace(accept_url, "[lien J'accepte]").replace(refuse_url, "[lien Je refuse]")
