"""Phase 2 : tampon (F-10, F-11), création manuelle (F-12, F-13), fiche (F-14), attribution (R-03),
fusion et division (F-15)."""

from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Assignment,
    AssignmentStatus,
    AuditLog,
    ChangeKind,
    ChangeRequest,
    Request,
    SourceKind,
    SourceMessage,
    Technician,
    TechnicianRole,
)

FULL = {
    "type_code": "MI",
    "title": "Visite délégation",
    "requester_name": "Chef A",
    "requester_email": "chef.a@example.local",
    "cf": "CF12345",
    "client": "Client Alpha",
    "location": "Herstal",
    "objective": "Démonstration produit",
    "technicians_needed": 2,
    "start_date": "2026-11-09",
    "end_date": "2026-11-11",
    "date_flexible": True,
    "flex_justification": "Client souple",
    "comments": "RAS",
    "products": [{"product": "Fusil X", "ammunition": "5.56", "comment": "2 caisses"}],
    "attachment_url": "https://sharepoint.example.local/doc",
}


@pytest.fixture
def mechs(seeded: Session) -> list[Technician]:
    return list(
        seeded.scalars(
            select(Technician)
            .where(Technician.role == TechnicianRole.MECHANIC)
            .order_by(Technician.sort_order)
        )
    )


def _create(http: TestClient, **over) -> dict:
    r = http.post("/api/requests", json={**FULL, **over})
    assert r.status_code == 201, r.text
    return r.json()


def _assign(client: TestClient, req: dict, tech: Technician, start: str, end: str, **extra) -> object:
    return client.post(
        f"/api/requests/{req['id']}/assignments",
        json={
            "request_version": req["version"],
            "technician_id": str(tech.id),
            "start_date": start,
            "end_date": end,
            **extra,
        },
    )


def _get(client: TestClient, req: dict) -> dict:
    return client.get(f"/api/requests/{req['id']}").json()


# --------------------------------------------------------------------------- F-12, F-13


def test_create_complete_request(client: TestClient) -> None:
    req = _create(client)
    assert req["ref"] == f"D-{datetime.now(UTC).year}-0001"
    assert req["missing_fields"] == []
    assert req["status"] == "to_assign" and req["origin"] == "manual" and req["needs_review"] is False
    assert req["products"][0]["ammunition"] == "5.56"
    assert req["remaining"] == 2
    assert req["history"][0]["action"] == "request.create"
    assert _create(client)["ref"].endswith("-0002")


def test_create_incomplete_request_lists_missing_fields(client: TestClient) -> None:
    req = _create(client, type_code=None, start_date=None, end_date=None, location="")
    assert req["missing_fields"] == ["type_code", "start_date", "end_date", "location"]


def test_create_validation(client: TestClient) -> None:
    assert client.post("/api/requests", json={**FULL, "end_date": "2026-11-01"}).status_code == 422
    assert client.post("/api/requests", json={**FULL, "technicians_needed": 0}).status_code == 422
    assert client.post("/api/requests", json={**FULL, "type_code": "ZZ"}).status_code == 422
    assert client.post("/api/requests", json={**FULL, "attachment_url": "file:///c:/x"}).status_code == 422


# --------------------------------------------------------------------------- F-10, F-11


def test_buffer_lists_sorted_and_flags(client: TestClient, seeded: Session) -> None:
    late = _create(client, start_date="2026-12-01", end_date="2026-12-02")
    undated = _create(client, start_date=None, end_date=None)
    early = _create(client, start_date="2026-11-02", end_date="2026-11-02")
    seeded.add(ChangeRequest(request_id=UUID(early["id"]), kind=ChangeKind.CANCELLATION, proposed_changes={}))
    seeded.commit()
    buffer = client.get("/api/requests").json()
    assert [v["id"] for v in buffer] == [early["id"], late["id"], undated["id"]]
    assert buffer[0]["pending_changes"] == ["cancellation"]
    assert buffer[2]["missing_fields"] == ["start_date", "end_date"]


def test_buffer_excludes_confirmed_but_keeps_needs_review(
    client: TestClient, mechs: list[Technician], seeded: Session
) -> None:
    req = _create(client, technicians_needed=1)
    assert _assign(client, req, mechs[0], "2026-11-09", "2026-11-11").status_code == 201
    a = seeded.scalars(select(Assignment)).one()
    a.status = AssignmentStatus.ACCEPTED
    r = seeded.get(Request, a.request_id)
    from app.api.planning import refresh_request_status

    refresh_request_status(seeded, r)
    seeded.commit()
    assert client.get("/api/requests").json() == []
    r.needs_review = True
    seeded.commit()
    assert [v["id"] for v in client.get("/api/requests").json()] == [req["id"]]
    assert len(client.get("/api/requests", params={"view": "all"}).json()) == 1


# --------------------------------------------------------------------------- F-14


def test_update_request_fields_and_review(client: TestClient) -> None:
    req = _create(client, location=None)
    assert req["missing_fields"] == ["location"]
    r = client.patch(
        f"/api/requests/{req['id']}",
        json={"version": req["version"], "location": "Liège", "needs_review": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["location"] == "Liège" and body["missing_fields"] == []
    assert (
        client.patch(f"/api/requests/{req['id']}", json={"version": req["version"], "cf": "X"}).status_code
        == 409
    )
    assert {h["action"] for h in body["history"]} == {"request.create", "request.update"}


def test_update_rejects_bad_values(client: TestClient, mechs: list[Technician]) -> None:
    req = _create(client, technicians_needed=1)
    _assign(client, req, mechs[0], "2026-11-09", "2026-11-11")
    req = _get(client, req)
    url = f"/api/requests/{req['id']}"
    assert client.patch(url, json={"version": req["version"], "end_date": "2026-11-01"}).status_code == 422
    assert client.patch(url, json={"version": req["version"], "unknown": 1}).status_code == 422
    assert client.patch(url, json={"version": req["version"], "technicians_needed": None}).status_code == 422


def test_needs_review_agent_request_and_sources(client: TestClient, seeded: Session) -> None:
    req = _create(client)
    seeded.add(
        SourceMessage(
            source=SourceKind.MAIL,
            external_id="m1",
            received_at=datetime.now(UTC),
            subject="Demande de visite",
            web_link="https://outlook.example.local/m1",
            request_id=UUID(req["id"]),
        )
    )
    seeded.commit()
    detail = _get(client, req)
    assert detail["sources"][0]["subject"] == "Demande de visite"


# --------------------------------------------------------------------------- attribution (R-03)


def test_assign_with_request_dates_creates_draft(
    client: TestClient, mechs: list[Technician], session_factory
) -> None:
    req = _create(client)
    r = _assign(client, req, mechs[0], "2026-11-09", "2026-11-11")
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "draft"
    detail = _get(client, req)
    assert detail["status"] == "partially_assigned" and detail["remaining"] == 1
    assert detail["version"] > req["version"]  # verrou optimiste sur la demande
    assert detail["assignments"][0]["technician_name"] == "Technicien A"
    with session_factory() as s:
        assert s.scalars(select(AuditLog).where(AuditLog.action == "assignment.create")).one()


def test_assign_with_other_dates_requires_confirmation(client: TestClient, mechs: list[Technician]) -> None:
    req = _create(client)
    assert _assign(client, req, mechs[0], "2026-11-16", "2026-11-18").status_code == 428
    r = _assign(client, req, mechs[0], "2026-11-16", "2026-11-18", confirm_dates_differ=True)
    assert r.status_code == 201
    assert _get(client, req)["start_date"] == "2026-11-09"  # la demande garde ses dates


def test_assign_undated_request_can_write_dates(client: TestClient, mechs: list[Technician]) -> None:
    req = _create(client, start_date=None, end_date=None)
    r = _assign(client, req, mechs[0], "2026-11-16", "2026-11-16", write_dates_to_request=True)
    assert r.status_code == 201
    detail = _get(client, req)
    assert (detail["start_date"], detail["end_date"]) == ("2026-11-16", "2026-11-16")
    assert detail["missing_fields"] == []


def test_assign_rules(client: TestClient, mechs: list[Technician], seeded: Session) -> None:
    req = _create(client, technicians_needed=2)
    assert _assign(client, req, mechs[0], "2026-11-09", "2026-11-11").status_code == 201
    assert _assign(client, req, mechs[1], "2026-11-09", "2026-11-11").status_code == 409  # version périmée
    req = _get(client, req)
    assert _assign(client, req, mechs[0], "2026-11-09", "2026-11-11").status_code == 422  # déjà affecté
    assert _assign(client, req, mechs[1], "2026-11-09", "2026-11-11").status_code == 201
    req = _get(client, req)
    assert req["status"] == "pending"
    assert _assign(client, req, mechs[2], "2026-11-09", "2026-11-11").status_code == 422  # complet
    elec = seeded.scalars(select(Technician).where(Technician.role == TechnicianRole.ELECTRONICIAN)).first()
    r2 = _create(client)
    assert _assign(client, r2, elec, "2026-11-09", "2026-11-11").status_code == 422


def test_remove_draft_assignment(client: TestClient, mechs: list[Technician], seeded: Session) -> None:
    req = _create(client, technicians_needed=1)
    a = _assign(client, req, mechs[0], "2026-11-09", "2026-11-11").json()
    assert (
        client.delete(f"/api/assignments/{a['id']}", params={"version": a["version"] + 5}).status_code == 409
    )
    assert client.delete(f"/api/assignments/{a['id']}", params={"version": a["version"]}).status_code == 204
    detail = _get(client, req)
    assert detail["status"] == "to_assign"
    assert detail["assignments"][0]["status"] == "cancelled"  # conservé, jamais supprimé
    # une affectation envoyée ne se retire pas ici (F-26, phase 3)
    b = _assign(client, detail, mechs[1], "2026-11-09", "2026-11-11").json()
    row = seeded.get(Assignment, UUID(b["id"]))
    row.status = AssignmentStatus.PENDING_RESPONSE
    seeded.commit()
    assert client.delete(f"/api/assignments/{b['id']}", params={"version": row.version}).status_code == 422


# --------------------------------------------------------------------------- F-15


def test_merge(client: TestClient, mechs: list[Technician], seeded: Session) -> None:
    keep = _create(client, technicians_needed=2, client=None, cf=None)
    other = _create(client, technicians_needed=1, client="Client Bravo", cf="CF999")
    _assign(client, other, mechs[3], "2026-11-09", "2026-11-11")
    seeded.add(
        SourceMessage(
            source=SourceKind.MAIL,
            external_id="m2",
            received_at=datetime.now(UTC),
            request_id=UUID(other["id"]),
        )
    )
    seeded.commit()
    other = _get(client, other)
    r = client.post(
        f"/api/requests/{keep['id']}/merge",
        json={"version": keep["version"], "other_id": other["id"], "other_version": other["version"]},
    )
    assert r.status_code == 200, r.text
    merged = r.json()
    assert merged["client"] == "Client Bravo" and merged["cf"] == "CF999"  # champs vides complétés
    assert [a["technician_name"] for a in merged["assignments"]] == ["Technicien D"]
    assert len(merged["sources"]) == 1
    assert merged["status"] == "partially_assigned"
    absorbed = _get(client, other)
    assert absorbed["status"] == "cancelled" and absorbed["merged_into_ref"] == keep["ref"]
    assert other["id"] not in [v["id"] for v in client.get("/api/requests").json()]


def test_merge_refused_when_too_many_assignments(client: TestClient, mechs: list[Technician]) -> None:
    keep = _create(client, technicians_needed=1)
    other = _create(client, technicians_needed=1)
    _assign(client, keep, mechs[0], "2026-11-09", "2026-11-11")
    _assign(client, other, mechs[1], "2026-11-09", "2026-11-11")
    keep, other = _get(client, keep), _get(client, other)
    r = client.post(
        f"/api/requests/{keep['id']}/merge",
        json={"version": keep["version"], "other_id": other["id"], "other_version": other["version"]},
    )
    assert r.status_code == 422
    r2 = client.post(
        f"/api/requests/{keep['id']}/merge",
        json={"version": keep["version"], "other_id": keep["id"], "other_version": keep["version"]},
    )
    assert r2.status_code == 422


def test_split(client: TestClient, mechs: list[Technician]) -> None:
    req = _create(client, start_date="2026-11-09", end_date="2026-11-20", technicians_needed=3)
    _assign(client, req, mechs[0], "2026-11-09", "2026-11-20")  # à cheval
    req = _get(client, req)
    _assign(client, req, mechs[1], "2026-11-09", "2026-11-12", confirm_dates_differ=True)  # avant
    req = _get(client, req)
    _assign(client, req, mechs[2], "2026-11-17", "2026-11-20", confirm_dates_differ=True)  # après
    req = _get(client, req)

    r = client.post(
        f"/api/requests/{req['id']}/split", json={"version": req["version"], "split_date": "2026-11-16"}
    )
    assert r.status_code == 200, r.text
    second = r.json()
    first = _get(client, req)
    assert (first["start_date"], first["end_date"]) == ("2026-11-09", "2026-11-15")
    assert (second["start_date"], second["end_date"]) == ("2026-11-16", "2026-11-20")
    assert second["ref"] != first["ref"] and second["client"] == "Client Alpha"
    spans = lambda d: sorted((a["technician_name"], a["start_date"], a["end_date"]) for a in d["assignments"])  # noqa: E731
    assert spans(first) == [
        ("Technicien A", "2026-11-09", "2026-11-15"),
        ("Technicien B", "2026-11-09", "2026-11-12"),
    ]
    assert spans(second) == [
        ("Technicien A", "2026-11-16", "2026-11-20"),
        ("Technicien C", "2026-11-17", "2026-11-20"),
    ]
    bad = client.post(
        f"/api/requests/{first['id']}/split", json={"version": first["version"], "split_date": "2026-11-09"}
    )
    assert bad.status_code == 422


def test_split_requires_dates(client: TestClient) -> None:
    req = _create(client, start_date=None, end_date=None)
    r = client.post(
        f"/api/requests/{req['id']}/split", json={"version": req["version"], "split_date": "2026-11-16"}
    )
    assert r.status_code == 422


def test_cancelled_request_is_locked(client: TestClient, seeded: Session) -> None:
    req = _create(client)
    row = seeded.get(Request, UUID(req["id"]))
    row.cancelled_at = datetime.now(UTC)
    seeded.commit()
    assert (
        client.patch(f"/api/requests/{req['id']}", json={"version": row.version, "cf": "x"}).status_code
        == 422
    )
    assert date.fromisoformat(req["start_date"])  # sanity
