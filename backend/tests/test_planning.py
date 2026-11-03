"""Phase 1 : GET /planning, déplacement d'activités (F-07), absences manuelles (F-31)."""

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Absence,
    AbsenceCategory,
    Assignment,
    AssignmentStatus,
    AuditLog,
    Request,
    RequestOrigin,
    RequestStatus,
    Technician,
    TechnicianRole,
)


def _techs(session: Session, role: TechnicianRole = TechnicianRole.MECHANIC) -> list[Technician]:
    return list(
        session.scalars(select(Technician).where(Technician.role == role).order_by(Technician.sort_order))
    )


@pytest.fixture
def scene(seeded: Session) -> dict:
    """Une demande à 1 technicien, attribuée et acceptée, du 09/11 au 11/11/2026."""
    a_tech, b_tech = _techs(seeded)[:2]
    req = Request(
        ref="D-2026-0001",
        origin=RequestOrigin.MANUAL,
        type_code="MI",
        title="Visite délégation",
        location="Herstal",
        start_date=date(2026, 11, 9),
        end_date=date(2026, 11, 11),
        technicians_needed=1,
        status=RequestStatus.CONFIRMED,
    )
    seeded.add(req)
    seeded.flush()
    asg = Assignment(
        request_id=req.id,
        technician_id=a_tech.id,
        start_date=req.start_date,
        end_date=req.end_date,
        status=AssignmentStatus.ACCEPTED,
        response_token_hash="x" * 64,
        token_used_at=datetime.now(UTC),
        responded_at=datetime.now(UTC),
    )
    old = Assignment(
        request_id=req.id,
        technician_id=b_tech.id,
        start_date=req.start_date,
        end_date=req.end_date,
        status=AssignmentStatus.REFUSED,
    )
    seeded.add_all([asg, old])
    seeded.commit()
    return {"req": req, "asg": asg, "a": a_tech, "b": b_tech}


def _planning(client: TestClient, start: str = "2026-11-02", end: str = "2026-12-27") -> dict:
    r = client.get("/api/planning", params={"from": start, "to": end})
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------- GET /planning


def test_planning_returns_window_content(client: TestClient, scene: dict) -> None:
    data = _planning(client)
    assert data["window_start"] == "2026-11-02"
    assert len(data["technicians"]) == 25
    # seuls les assignments actifs sont affichés
    assert [a["id"] for a in data["assignments"]] == [str(scene["asg"].id)]
    assert data["requests"][0]["ref"] == "D-2026-0001"
    assert {h["label"] for h in data["holidays"]} == {"Armistice", "Noël"}


def test_planning_excludes_outside_window(client: TestClient, scene: dict) -> None:
    assert _planning(client, "2026-12-01", "2026-12-31")["assignments"] == []
    # chevauchement partiel inclus
    assert len(_planning(client, "2026-11-11", "2026-11-30")["assignments"]) == 1


def test_planning_window_validation(client: TestClient) -> None:
    assert client.get("/api/planning", params={"from": "2026-11-10", "to": "2026-11-01"}).status_code == 422
    assert client.get("/api/planning", params={"from": "2026-01-01", "to": "2027-06-01"}).status_code == 422


def test_assignment_detail(client: TestClient, scene: dict) -> None:
    r = client.get(f"/api/assignments/{scene['asg'].id}")
    assert r.status_code == 200
    assert r.json()["request"]["title"] == "Visite délégation"


# --------------------------------------------------------------------------- F-07


def _patch(client: TestClient, asg: Assignment, **body) -> object:
    return client.patch(f"/api/assignments/{asg.id}", json={"version": asg.version, **body})


def test_move_sent_assignment_requires_confirmation(client: TestClient, scene: dict) -> None:
    r = _patch(client, scene["asg"], start_date="2026-11-16", end_date="2026-11-18")
    assert r.status_code == 428


def test_move_confirmed_resets_to_draft_and_revokes_token(
    client: TestClient, scene: dict, session_factory
) -> None:
    r = _patch(
        client,
        scene["asg"],
        technician_id=str(scene["b"].id),
        start_date="2026-11-16",
        end_date="2026-11-18",
        confirm=True,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "draft"
    assert body["technician_id"] == str(scene["b"].id)
    assert body["version"] == scene["asg"].version + 1
    with session_factory() as s:
        a = s.get(Assignment, scene["asg"].id)
        assert a.response_token_hash is None and a.responded_at is None
        # R-01 : la demande repasse de confirmed à pending (poste pourvu, réponse attendue)
        assert s.get(Request, scene["req"].id).status == RequestStatus.PENDING
        log = s.scalars(select(AuditLog).where(AuditLog.action == "assignment.move")).one()
        assert log.actor == "user:philippe.zander@example.local"
        assert log.before["start_date"] == "2026-11-09" and log.after["start_date"] == "2026-11-16"


def test_move_draft_needs_no_confirmation(client: TestClient, scene: dict, seeded: Session) -> None:
    scene["asg"].status = AssignmentStatus.DRAFT
    seeded.commit()
    r = _patch(client, scene["asg"], end_date="2026-11-13")
    assert r.status_code == 200
    assert r.json()["status"] == "draft"


def test_resize_only_end(client: TestClient, scene: dict) -> None:
    r = _patch(client, scene["asg"], end_date="2026-11-12", confirm=True)
    assert r.json()["start_date"] == "2026-11-09" and r.json()["end_date"] == "2026-11-12"


def test_stale_version_is_409(client: TestClient, scene: dict) -> None:
    r = client.patch(
        f"/api/assignments/{scene['asg'].id}",
        json={"version": scene["asg"].version - 1, "end_date": "2026-11-12", "confirm": True},
    )
    assert r.status_code == 409


def test_invalid_period_is_422(client: TestClient, scene: dict) -> None:
    assert _patch(client, scene["asg"], end_date="2026-11-01", confirm=True).status_code == 422


def test_cannot_move_onto_electronician(client: TestClient, scene: dict, seeded: Session) -> None:
    elec = _techs(seeded, TechnicianRole.ELECTRONICIAN)[0]
    assert _patch(client, scene["asg"], technician_id=str(elec.id), confirm=True).status_code == 422


def test_noop_move_changes_nothing(client: TestClient, scene: dict) -> None:
    r = _patch(client, scene["asg"], start_date="2026-11-09")
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"


# --------------------------------------------------------------------------- F-31


def test_absence_crud(client: TestClient, scene: dict, session_factory) -> None:
    tech = str(scene["a"].id)
    r = client.post(
        "/api/absences",
        json={
            "technician_id": tech,
            "start_date": "2026-11-23",
            "end_date": "2026-11-27",
            "category": "leave",
        },
    )
    assert r.status_code == 201, r.text
    ab = r.json()

    # chevauchement d'absences refusé
    r2 = client.post(
        "/api/absences",
        json={
            "technician_id": tech,
            "start_date": "2026-11-27",
            "end_date": "2026-11-30",
            "category": "sick",
        },
    )
    assert r2.status_code == 422

    r3 = client.patch(
        f"/api/absences/{ab['id']}",
        json={**ab, "end_date": "2026-11-24", "category": "recovery"},
    )
    assert r3.status_code == 200 and r3.json()["category"] == "recovery"
    assert client.patch(f"/api/absences/{ab['id']}", json={**ab}).status_code == 409  # ancienne version

    listed = client.get("/api/absences", params={"from": "2026-11-01", "to": "2026-11-30"}).json()
    assert [a["id"] for a in listed] == [ab["id"]]

    assert client.delete(f"/api/absences/{ab['id']}", params={"version": ab["version"]}).status_code == 409
    r4 = client.delete(f"/api/absences/{ab['id']}", params={"version": r3.json()["version"]})
    assert r4.status_code == 204
    with session_factory() as s:
        assert s.scalars(select(Absence)).all() == []
        actions = sorted(x.action for x in s.scalars(select(AuditLog)))
        assert actions == ["absence.create", "absence.delete", "absence.update"]


def test_absence_invalid_period(client: TestClient, scene: dict) -> None:
    r = client.post(
        "/api/absences",
        json={
            "technician_id": str(scene["a"].id),
            "start_date": "2026-11-23",
            "end_date": "2026-11-20",
            "category": AbsenceCategory.LEAVE.value,
        },
    )
    assert r.status_code == 422


def test_planner_can_edit_planning(client: TestClient, scene: dict) -> None:
    r = client.post(
        "/api/absences",
        headers={"X-Dev-User": "olivier@example.local"},
        json={
            "technician_id": str(scene["b"].id),
            "start_date": "2026-11-23",
            "end_date": "2026-11-23",
            "category": "other",
        },
    )
    assert r.status_code == 201
