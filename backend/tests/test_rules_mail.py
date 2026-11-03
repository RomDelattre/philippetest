from datetime import UTC, date, datetime, timedelta

from app.rules.templates import (
    DEFAULT_TEMPLATES,
    format_dates,
    missing_link_placeholders,
    redact_links,
    render,
)
from app.rules.tokens import expiry, hash_token, new_token


def test_tokens_are_random_long_and_hashed() -> None:
    t1, h1 = new_token()
    t2, _ = new_token()
    assert t1 != t2
    assert len(t1) >= 22  # ≥ 128 bits en base64url (NF-02)
    assert h1 == hash_token(t1) and h1 != t1 and len(h1) == 64


def test_expiry() -> None:
    now = datetime(2026, 11, 3, tzinfo=UTC)
    assert expiry(now, 14) == now + timedelta(days=14)


def test_render_keeps_unknown_variables() -> None:
    assert render("Bonjour {technicien}, {inconnu}", {"technicien": "Jean"}) == "Bonjour Jean, {inconnu}"


def test_default_proposal_has_both_links() -> None:
    assert missing_link_placeholders(DEFAULT_TEMPLATES["tech_proposal"]["body"]) == []
    assert missing_link_placeholders("Bonjour {lien_accepter}") == ["{lien_refuser}"]


def test_format_dates() -> None:
    assert format_dates(date(2026, 11, 9), date(2026, 11, 11)) == "du 09/11/2026 au 11/11/2026"
    assert format_dates(date(2026, 11, 9), date(2026, 11, 9)) == "le 09/11/2026"
    assert format_dates(None, None) == "dates à préciser"


def test_redact_links() -> None:
    body = "Oui : https://x/a?answer=accept\nNon : https://x/a?answer=refuse"
    assert redact_links(body, "https://x/a?answer=accept", "https://x/a?answer=refuse") == (
        "Oui : [lien J'accepte]\nNon : [lien Je refuse]"
    )
