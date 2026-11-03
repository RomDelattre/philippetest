"""Configuration lue dans les variables d'environnement (NF-03 : aucun secret en dur)."""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./dev.db"
    timezone: str = "Europe/Brussels"
    log_level: str = "INFO"

    # Authentification (F-80, NF-01)
    # dev   : utilisateur simulé (en-tête X-Dev-User ou DEV_USER_EMAIL), interdit en production
    # proxy : le reverse proxy (ex. oauth2-proxy branché sur Entra ID) authentifie et transmet l'e-mail
    # oidc  : jeton Bearer OIDC validé par l'API (JWKS)
    auth_mode: Literal["dev", "proxy", "oidc"] = "dev"
    dev_user_email: str = "philippe.zander@example.local"
    proxy_user_header: str = "X-Forwarded-Email"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None

    # Mails sortants (F-50 à F-52). Le connecteur Microsoft (Graph ou Power Automate, Q-01)
    # viendra s'ajouter derrière la même interface (app/mail.py).
    # file : écrit des .eml dans MAIL_FILE_DIR (développement) ; smtp : relais interne ; disabled : refus
    mail_backend: Literal["file", "smtp", "disabled"] = "file"
    mail_from: str = "philippe.zander@example.local"
    mail_file_dir: str = "./outbox-mails"
    smtp_host: str | None = None
    smtp_port: int = 25
    smtp_starttls: bool = True
    smtp_user: str | None = None
    smtp_password: str | None = None
    # Adresse publique (interne) de l'application, utilisée dans les liens de réponse (F-21)
    public_base_url: str = "http://localhost:8080"

    # Comptes créés par le seed
    seed_admin_email: str = "philippe.zander@example.local"
    seed_admin_name: str = "Philippe Zander"
    seed_planner_email: str = "olivier@example.local"
    seed_planner_name: str = "Olivier"

    @model_validator(mode="after")
    def _check(self) -> "Settings":
        if self.app_env == "production" and self.auth_mode == "dev":
            raise ValueError("AUTH_MODE=dev est interdit en production")
        if self.auth_mode == "oidc" and not (self.oidc_issuer and self.oidc_audience and self.oidc_jwks_url):
            raise ValueError("AUTH_MODE=oidc exige OIDC_ISSUER, OIDC_AUDIENCE et OIDC_JWKS_URL")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
