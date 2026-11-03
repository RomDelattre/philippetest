"""Authentification et droits (F-80, NF-01). Aucune création de compte locale :
l'utilisateur doit exister dans la table users (créée par le seed ou un administrateur)."""

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.models import User, UserRole

DEV_USER_HEADER = "X-Dev-User"


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    email: str
    display_name: str
    role: UserRole

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    @property
    def audit_actor(self) -> str:
        return f"user:{self.email}"


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url)


def _email_from_oidc(request: Request, settings: Settings) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton manquant")
    token = auth.removeprefix("Bearer ")
    try:
        key = _jwks_client(settings.oidc_jwks_url or "").get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton invalide") from exc
    email = claims.get("preferred_username") or claims.get("email") or claims.get("upn")
    if not email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton sans adresse e-mail")
    return str(email)


def resolve_email(request: Request, settings: Settings) -> str:
    if settings.auth_mode == "dev":
        return request.headers.get(DEV_USER_HEADER) or settings.dev_user_email
    if settings.auth_mode == "proxy":
        email = request.headers.get(settings.proxy_user_header)
        if not email:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Non authentifié")
        return email
    return _email_from_oidc(request, settings)


def get_current_user(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentUser:
    email = resolve_email(request, settings).strip().lower()
    user = session.scalar(select(User).where(func.lower(User.email) == email, User.active.is_(True)))
    if user is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Utilisateur non autorisé")
    return CurrentUser(id=user.id, email=user.email, display_name=user.display_name, role=user.role)


def require_admin(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé à l'administrateur")
    return user


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
AdminDep = Annotated[CurrentUser, Depends(require_admin)]
SessionDep = Annotated[Session, Depends(get_session)]
