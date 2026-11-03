from fastapi.testclient import TestClient

from app.auth import DEV_USER_HEADER
from app.config import Settings, get_settings
from app.main import app


def test_health_without_auth(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"


def test_me_default_dev_user_is_admin(client: TestClient) -> None:
    r = client.get("/api/me")
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def test_me_dev_header_switches_user(client: TestClient) -> None:
    r = client.get("/api/me", headers={DEV_USER_HEADER: "Olivier@example.local"})
    assert r.status_code == 200
    assert r.json()["role"] == "planner"


def test_unknown_user_is_forbidden(client: TestClient) -> None:
    r = client.get("/api/me", headers={DEV_USER_HEADER: "inconnu@example.local"})
    assert r.status_code == 403


def test_proxy_mode_requires_header(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(auth_mode="proxy", app_env="test")
    try:
        assert client.get("/api/me").status_code == 401
        r = client.get("/api/me", headers={"X-Forwarded-Email": "philippe.zander@example.local"})
        assert r.status_code == 200
        # en mode proxy, l'en-tête de développement est ignoré
        assert client.get("/api/me", headers={DEV_USER_HEADER: "olivier@example.local"}).status_code == 401
    finally:
        app.dependency_overrides.pop(get_settings)


def test_dev_mode_forbidden_in_production() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(app_env="production", auth_mode="dev")


def test_reference_lists(client: TestClient) -> None:
    techs = client.get("/api/technicians").json()
    assert sum(t["role"] == "mechanic" for t in techs) == 20
    assert sum(t["role"] == "electronician" for t in techs) == 5
    codes = [m["code"] for m in client.get("/api/mission-types").json()]
    assert codes[:5] == ["MI", "SD", "AT", "FI_FE", "TI_TE"]
    hol = client.get("/api/holidays", params={"from": "2026-01-01", "to": "2026-12-31"}).json()
    assert len(hol) == 10
    assert client.get("/api/holidays", params={"from": "2026-12-31", "to": "2026-01-01"}).status_code == 422
