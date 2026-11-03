"""Phase 3 : brouillon à l'attribution (F-20), envoi validé (F-50 à F-52, P2), liens de réponse
(F-21, F-22, NF-02), acceptation (F-23), refus (F-24), saisie manuelle (F-25), annulation (F-26)."""

import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.mail import MailError, get_mail_sender
from app.main import app
from app.models import Assignment, AssignmentStatus, Notification, Technician, TechnicianRole
from app.rules.tokens import hash_token

PLANNER = {"X-Dev-User": "olivier@example.local"}


class FakeSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []
        self.fail_with: str | None = None

    def send(self, to: str, subject: str, body: str) -> None:
        if self.fail_with:
            raise MailError(self.fail_with)
        self.sent.append((to, subject, body))


@pytest.fixture
def sender(client: TestClient) -> FakeSender:
    fake = FakeSender()
    app.dependency_overrides[get_mail_sender] = lambda: fake
    return fake


@pytest.fixture
def mechs(seeded: Session) -> list[Technician]:
    techs = list(
        seeded.scalars(
            select(Technician)
            .where(Technician.role == TechnicianRole.MECHANIC)
            .order_by(Technician.sort_order)
        )
    )
    for i, t in enumerate(techs[:3]):
        t.email = f"tech{i}@example.local"
    techs[5].email = None  # technicien sans adresse
    seeded.commit()
    return techs


def _request(client: TestClient, **over) -> dict:
    body = {
        "type_code": "MI",
        "title": "Visite délégation",
        "requester_name": "Chef A",
        "requester_email": "chef.a@example.local",
        "location": "Herstal",
        "technicians_needed": 2,
        "start_date": "2026-11-09",
        "end_date": "2026-11-11",
        **over,
    }
    r = client.post("/api/requests", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _assign(client: TestClient, req: dict, tech: Technician) -> dict:
    req = client.get(f"/api/requests/{req['id']}").json()
    r = client.post(
        f"/api/requests/{req['id']}/assignments",
        json={
            "request_version": req["version"],
            "technician_id": str(tech.id),
            "start_date": req["start_date"],
            "end_date": req["end_date"],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _outbox(client: TestClient, view: str = "pending") -> list[dict]:
    r = client.get("/api/outbox", params={"view": view})
    assert r.status_code == 200, r.text
    return r.json()


def _send(client: TestClient, *msgs: dict) -> list[dict]:
    r = client.post(
        "/api/outbox/send", json={"items": [{"id": m["id"], "version": m["version"]} for m in msgs]}
    )
    assert r.status_code == 200, r.text
    return r.json()


def _proposal(client: TestClient, assignment_id: str) -> dict:
    return next(
        m for m in _outbox(client) if m["assignment_id"] == assignment_id and m["kind"] == "tech_proposal"
    )


def _sent_token(sender: FakeSender, index: int = -1) -> str:
    m = re.search(r"/api/respond/([\w-]+)\?answer=accept", sender.sent[index][2])
    assert m, sender.sent[index][2]
    return m.group(1)


def _proposed(client: TestClient, sender: FakeSender, req: dict, tech: Technician) -> tuple[dict, str]:
    a = _assign(client, req, tech)
    _send(client, _proposal(client, a["id"]))
    return a, _sent_token(sender)


# --------------------------------------------------------------------------- F-20, F-50 à F-52


def test_drop_prepares_proposal_draft(
    client: TestClient, mechs: list[Technician], sender: FakeSender
) -> None:
    req = _request(client)
    a = _assign(client, req, mechs[0])
    msg = _proposal(client, a["id"])
    assert msg["status"] == "draft" and msg["to_email"] == "tech0@example.local"
    assert req["ref"] in msg["subject"]
    assert "{lien_accepter}" in msg["body"] and "{lien_refuser}" in msg["body"]
    assert "du 09/11/2026 au 11/11/2026" in msg["body"] and "Herstal" in msg["body"]
    assert msg["missing_links"] == []
    assert sender.sent == []  # P2 : rien ne part sans validation


def test_send_proposal_mints_token_and_waits_for_response(
    client: TestClient, mechs: list[Technician], sender: FakeSender, session_factory
) -> None:
    req = _request(client)
    a = _assign(client, req, mechs[0])
    [result] = _send(client, _proposal(client, a["id"]))
    assert result == {"id": result["id"], "status": "sent", "error": None}
    to, subject, body = sender.sent[0]
    assert to == "tech0@example.local"
    token = _sent_token(sender)
    assert f"/api/respond/{token}?answer=refuse" in body
    stored = _outbox(client, "sent")[0]
    assert token not in stored["body"] and "[lien J'accepte]" in stored["body"]  # NF-02
    with session_factory() as s:
        row = s.get(Assignment, UUID(a["id"]))
        assert row.status == AssignmentStatus.PENDING_RESPONSE
        assert row.response_token_hash == hash_token(token)
        assert row.token_expires_at.replace(tzinfo=UTC) - datetime.now(UTC) > timedelta(days=13)
    assert _outbox(client) == []


def test_send_failures_and_retry(client: TestClient, mechs: list[Technician], sender: FakeSender) -> None:
    req = _request(client)
    a = _assign(client, req, mechs[5])  # technicien sans adresse
    msg = _proposal(client, a["id"])
    [r1] = _send(client, msg)
    assert r1["status"] == "failed" and "Adresse" in r1["error"]
    msg = _proposal(client, a["id"])
    msg = client.patch(
        f"/api/outbox/{msg['id']}", json={"version": msg["version"], "to_email": "tf@example.local"}
    ).json()
    sender.fail_with = "relais indisponible"
    [r2] = _send(client, msg)
    assert r2 == {"id": msg["id"], "status": "failed", "error": "relais indisponible"}
    assert client.get(f"/api/assignments/{a['id']}").json()["status"] == "draft"
    sender.fail_with = None
    [r3] = _send(client, _proposal(client, a["id"]))
    assert r3["status"] == "sent" and sender.sent[0][0] == "tf@example.local"


def test_send_refused_without_links_or_with_stale_version(
    client: TestClient, mechs: list[Technician], sender: FakeSender
) -> None:
    req = _request(client)
    a = _assign(client, req, mechs[0])
    msg = _proposal(client, a["id"])
    stale = {**msg}
    msg = client.patch(f"/api/outbox/{msg['id']}", json={"version": msg["version"], "body": "Bonjour"}).json()
    assert msg["missing_links"] == ["{lien_accepter}", "{lien_refuser}"]
    assert _send(client, stale)[0]["error"] == "Mail modifié entre-temps : rechargez"
    assert "Variables obligatoires" in _send(client, msg)[0]["error"]
    assert sender.sent == []


def test_outbox_is_admin_only(client: TestClient) -> None:
    assert client.get("/api/outbox", headers=PLANNER).status_code == 403
    assert client.post("/api/outbox/send", headers=PLANNER, json={"items": []}).status_code == 403
    assert client.get("/api/settings/mail-templates", headers=PLANNER).status_code == 403


def test_discard_draft(client: TestClient, mechs: list[Technician]) -> None:
    req = _request(client)
    a = _assign(client, req, mechs[0])
    msg = _proposal(client, a["id"])
    assert client.delete(f"/api/outbox/{msg['id']}", params={"version": msg["version"]}).status_code == 204
    assert _outbox(client) == []
    assert (
        client.patch(
            f"/api/outbox/{msg['id']}", json={"version": msg["version"] + 1, "body": "x"}
        ).status_code
        == 422
    )


# --------------------------------------------------------------------------- F-21, F-22


def test_get_never_consumes_token(client: TestClient, mechs: list[Technician], sender: FakeSender) -> None:
    req = _request(client)
    a, token = _proposed(client, sender, req, mechs[0])
    for _ in range(3):  # antivirus, aperçu, ouverture par le technicien
        page = client.get(f"/api/respond/{token}", params={"answer": "refuse"})
        assert page.status_code == 200
        assert "Je confirme : je refuse" in page.text and "Herstal" in page.text
        assert "noindex" in page.text
    assert client.get(f"/api/assignments/{a['id']}").json()["status"] == "pending_response"


def test_accept_by_link(
    client: TestClient, mechs: list[Technician], sender: FakeSender, session_factory
) -> None:
    req = _request(client, technicians_needed=1)
    a, token = _proposed(client, sender, req, mechs[0])
    r = client.post(f"/api/respond/{token}", data={"answer": "accept"})
    assert r.status_code == 200 and "acceptation est enregistrée" in r.text
    assert client.get(f"/api/requests/{req['id']}").json()["status"] == "confirmed"
    conf = [m for m in _outbox(client) if m["kind"] == "requester_confirmation"]
    assert len(conf) == 1 and conf[0]["to_email"] == "chef.a@example.local"
    assert "Technicien A" in conf[0]["body"]
    # jeton à usage unique
    again = client.post(f"/api/respond/{token}", data={"answer": "refuse"})
    assert again.status_code == 410 and "déjà été enregistrée" in again.text
    assert client.get(f"/api/respond/{token}").status_code == 410
    with session_factory() as s:
        n = s.scalars(select(Notification)).one()
        assert n.kind == "accepted" and "Technicien A" in n.message
    notes = client.get("/api/notifications").json()
    assert notes[0]["read_at"] is None
    assert client.post(f"/api/notifications/{notes[0]['id']}/read").json()["read_at"] is not None


def test_refuse_by_link_returns_request_to_buffer(
    client: TestClient, mechs: list[Technician], sender: FakeSender
) -> None:
    req = _request(client, technicians_needed=1)
    a, token = _proposed(client, sender, req, mechs[0])
    assert client.post(f"/api/respond/{token}", data={"answer": "refuse"}).status_code == 200
    detail = client.get(f"/api/requests/{req['id']}").json()
    assert detail["status"] == "to_assign" and "technician_refused" in detail["badges"]
    assert detail["assignments"][0]["status"] == "refused"  # conservé dans l'historique
    assert any(v["id"] == req["id"] for v in client.get("/api/requests").json())
    assert client.get("/api/notifications").json()[0]["kind"] == "refused"
    _assign(client, req, mechs[1])
    assert "technician_refused" not in client.get(f"/api/requests/{req['id']}").json()["badges"]


def test_invalid_answers_and_unknown_tokens(
    client: TestClient, mechs: list[Technician], sender: FakeSender
) -> None:
    req = _request(client)
    _, token = _proposed(client, sender, req, mechs[0])
    assert client.post(f"/api/respond/{token}", data={"answer": "peut-être"}).status_code == 400
    r = client.get("/api/respond/inconnu")
    assert r.status_code == 410 and "plus valable" in r.text


def test_expired_token(
    client: TestClient, mechs: list[Technician], sender: FakeSender, seeded: Session
) -> None:
    req = _request(client)
    a, token = _proposed(client, sender, req, mechs[0])
    row = seeded.get(Assignment, UUID(a["id"]))
    row.token_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    seeded.commit()
    r = client.post(f"/api/respond/{token}", data={"answer": "accept"})
    assert r.status_code == 410 and "expiré" in r.text


def test_move_revokes_link_and_prepares_mails(
    client: TestClient, mechs: list[Technician], sender: FakeSender
) -> None:
    req = _request(client)
    a, token = _proposed(client, sender, req, mechs[0])
    a = client.get(f"/api/assignments/{a['id']}").json()
    r = client.patch(
        f"/api/assignments/{a['id']}",
        json={"version": a["version"], "technician_id": str(mechs[1].id), "confirm": True},
    )
    assert r.status_code == 200 and r.json()["status"] == "draft"
    assert client.get(f"/api/respond/{token}").status_code == 410  # F-07 : l'ancien lien n'est plus valable
    pending = [(m["kind"], m["to_email"]) for m in _outbox(client) if m["assignment_id"] == a["id"]]
    assert sorted(pending) == [("generic", "tech0@example.local"), ("tech_proposal", "tech1@example.local")]


def test_move_of_draft_replaces_unsent_proposal(client: TestClient, mechs: list[Technician]) -> None:
    req = _request(client)
    a = _assign(client, req, mechs[0])
    r = client.patch(f"/api/assignments/{a['id']}", json={"version": a["version"], "end_date": "2026-11-12"})
    assert r.status_code == 200
    proposals = [m for m in _outbox(client) if m["assignment_id"] == a["id"]]
    assert len(proposals) == 1 and "au 12/11/2026" in proposals[0]["body"]


# --------------------------------------------------------------------------- F-23, F-25, F-26


def test_manual_response(client: TestClient, mechs: list[Technician], sender: FakeSender) -> None:
    req = _request(client)
    a, token = _proposed(client, sender, req, mechs[0])
    a = client.get(f"/api/assignments/{a['id']}").json()
    r = client.patch(f"/api/assignments/{a['id']}", json={"version": a["version"], "response": "accept"})
    assert r.status_code == 200 and r.json()["status"] == "accepted"
    assert client.get(f"/api/respond/{token}").status_code == 410
    # réponse saisie avant l'envoi : la proposition en brouillon est retirée
    b = _assign(client, req, mechs[1])
    r2 = client.patch(f"/api/assignments/{b['id']}", json={"version": b["version"], "response": "refuse"})
    assert r2.json()["status"] == "refused"
    assert [m for m in _outbox(client) if m["kind"] == "tech_proposal"] == []
    r3 = client.patch(
        f"/api/assignments/{a['id']}", json={"version": r.json()["version"], "response": "refuse"}
    )
    assert r3.status_code == 422
    assert client.get("/api/notifications").json() == []  # Philippe a saisi lui-même


def test_confirmation_draft_is_updated_not_duplicated(
    client: TestClient, mechs: list[Technician], sender: FakeSender
) -> None:
    req = _request(client, technicians_needed=2)
    _, t1 = _proposed(client, sender, req, mechs[0])
    _, t2 = _proposed(client, sender, req, mechs[1])
    client.post(f"/api/respond/{t1}", data={"answer": "accept"})
    client.post(f"/api/respond/{t2}", data={"answer": "accept"})
    conf = [m for m in _outbox(client) if m["kind"] == "requester_confirmation"]
    assert len(conf) == 1
    assert "Technicien A" in conf[0]["body"] and "Technicien B" in conf[0]["body"]


def test_cancel_sent_proposal_prepares_information(
    client: TestClient, mechs: list[Technician], sender: FakeSender
) -> None:
    req = _request(client)
    a, token = _proposed(client, sender, req, mechs[0])
    a = client.get(f"/api/assignments/{a['id']}").json()
    assert (
        client.delete(
            f"/api/assignments/{a['id']}", params={"version": a["version"], "confirm": True}
        ).status_code
        == 204
    )
    assert client.get(f"/api/respond/{token}").status_code == 410
    info = [m for m in _outbox(client) if m["assignment_id"] == a["id"]]
    assert [(m["kind"], m["to_email"]) for m in info] == [("generic", "tech0@example.local")]
    assert "ne vous est plus attribuée" in info[0]["body"]


# --------------------------------------------------------------------------- modèles (F-52)


def test_templates(client: TestClient, mechs: list[Technician]) -> None:
    tpl = client.get("/api/settings/mail-templates").json()
    assert "{lien_accepter}" in tpl["tech_proposal"]["body"]
    bad = {**tpl, "tech_proposal": {"subject": "x", "body": "sans lien"}}
    assert client.put("/api/settings/mail-templates", json=bad).status_code == 422
    custom = {
        **tpl,
        "tech_proposal": {
            "subject": "Mission {ref}",
            "body": "Salut {technicien} {lien_accepter} {lien_refuser}",
        },
    }
    assert client.put("/api/settings/mail-templates", json=custom).status_code == 200
    req = _request(client)
    a = _assign(client, req, mechs[0])
    msg = _proposal(client, a["id"])
    assert msg["subject"] == f"Mission {req['ref']}" and msg["body"].startswith("Salut Technicien A")
