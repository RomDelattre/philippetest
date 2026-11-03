"""Jetons de réponse des techniciens (F-21, NF-02) : aléatoires (256 bits), stockés hachés,
à usage unique et expirants. Le jeton en clair n'existe qu'au moment de l'envoi du mail."""

import hashlib
import secrets
from datetime import datetime, timedelta


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> tuple[str, str]:
    """Renvoie (jeton en clair, empreinte à stocker)."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def expiry(now: datetime, validity_days: int) -> datetime:
    return now + timedelta(days=validity_days)
