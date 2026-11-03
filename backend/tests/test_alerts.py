"""Phase 4 : voyants de conflit (F-08, R-05), confirmation des chevauchements (R-02), alertes de date
(R-06), centre d'alertes (F-40, F-41), paramètres (F-43)."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Assignment, AssignmentStatus, ChangeKind, ChangeRequest, Technician, TechnicianRole
from app.services.dates import today_brussels

PLANNER = {"X-Dev-User": "olivier@example.local"}


def next_monday(weeks: int = 3) -> date:
    t = today_brussels()
    return t + timedelta(days=7 * weeks - t.weekday())


def iso(d: date) -> str:
    return d.isoformat()


@pytest.fixture
def mechs(seeded: Session) -> list[Technician]:
    return list(
        seeded.scalars(
            select(Technician)
            .where(Technician.role == TechnicianRole.MECHANIC)
            .order_by(Technician.sort_order)
        )
    )


def _request(client: TestClient, start: date, end: date, **over) -> dict:
    body = {
        "type_code": "MI",
        "title": "Essai",
        "location": "Herstal",
        "technicians_needed": 1,
        "start_date": iso(start),
        "end_date": iso(end),
        **over,
    }
    r = client.post("/api/requests", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _assign(
    client: TestClient,
    req: dict,
    tech: Technician,
    start: date | None = None,
    end: date | None = None,
    **flags,
):
    req = client.get(f"/api/requests/{req['id']}").json()
    return client.post(
        f"/api/requests/{req['id']}/assignments",
        json={
            "request_version": req["version"],
            "technician_id": str(tech.id),
            "start_date": iso(start) if start else req["start_date"],
            "end_date": iso(end) if end else req["end_date"],
            "confirm_dates_differ": True,
            **flags,
        },
    )


def _planning(client: TestClient, start: date, days: int = 56) -> dict:
    r = client.get("/api/planning", params={"from": iso(start), "to": iso(start + timedelta(days=days))})
    assert r.status_code == 200, r.text
    return r.json()


def _conflicts(client: TestClient, start: date) -> dict[str, dict]:
    return {c["assignment_id"]: c for c in _planning(client, start - timedelta(days=7))["conflicts"]}


def _alerts(client: TestClient) -> list[dict]:
    r = client.get("/api/alerts")
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------- R-02, F-08


def test_overlap_requires_confirmation_then_shows_red(client: TestClient, mechs: list[Technician]) -> None:
    mon = next_monday()
    r1 = _request(client, mon, mon + timedelta(days=2))
    r2 = _request(client, mon + timedelta(days=1), mon + timedelta(days=3))
    a1 = _assign(client, r1, mechs[0]).json()
    blocked = _assign(client, r2, mechs[0])
    assert blocked.status_code == 428
    assert blocked.json()["detail"]["code"] == "conflict"
    assert r1["ref"] in blocked.json()["detail"]["message"]
    a2 = _assign(client, r2, mechs[0], confirm_conflict=True).json()
    c = _conflicts(client, mon)
    assert c[a1["id"]]["level"] == "red" and c[a2["id"]]["items"][0]["code"] == "overlap"
    # F-41 : le conflit disparaît quand la cause disparaît
    a2 = client.get(f"/api/assignments/{a2['id']}").json()
    moved = client.patch(
        f"/api/assignments/{a2['id']}", json={"version": a2["version"], "technician_id": str(mechs[1].id)}
    )
    assert moved.status_code == 200, moved.text
    assert _conflicts(client, mon) == {}


def test_move_onto_busy_technician_requires_confirmation(client: TestClient, mechs: list[Technician]) -> None:
    mon = next_monday()
    a1 = _assign(client, _request(client, mon, mon), mechs[0]).json()
    a2 = _assign(client, _request(client, mon, mon), mechs[1]).json()
    url = f"/api/assignments/{a2['id']}"
    r = client.patch(url, json={"version": a2["version"], "technician_id": str(mechs[0].id)})
    assert r.status_code == 428 and r.json()["detail"]["code"] == "conflict"
    r = client.patch(
        url, json={"version": a2["version"], "technician_id": str(mechs[0].id), "confirm_conflict": True}
    )
    assert r.status_code == 200
    assert _conflicts(client, mon)[a1["id"]]["level"] == "red"


def test_sent_move_asks_sent_confirmation_first(
    client: TestClient, mechs: list[Technician], seeded: Session
) -> None:
    mon = next_monday()
    a = _assign(client, _request(client, mon, mon), mechs[0]).json()
    row = seeded.get(Assignment, UUID(a["id"]))
    row.status = AssignmentStatus.ACCEPTED
    seeded.commit()
    r = client.patch(
        f"/api/assignments/{a['id']}", json={"version": row.version, "end_date": iso(mon + timedelta(days=1))}
    )
    assert r.json()["detail"]["code"] == "confirm_sent"


def test_absence_on_activity_is_red(client: TestClient, mechs: list[Technician]) -> None:
    mon = next_monday()
    a = _assign(client, _request(client, mon, mon + timedelta(days=2)), mechs[0]).json()
    r = client.post(
        "/api/absences",
        json={
            "technician_id": str(mechs[0].id),
            "start_date": iso(mon + timedelta(days=1)),
            "end_date": iso(mon + timedelta(days=1)),
            "category": "sick",
        },
    )
    assert r.status_code == 201
    c = _conflicts(client, mon)[a["id"]]
    assert c["level"] == "red" and c["items"][0]["code"] == "absence"
    assert any(x["assignment_id"] == a["id"] and x["level"] == "red" for x in _alerts(client))


def test_assign_onto_absence_requires_confirmation(client: TestClient, mechs: list[Technician]) -> None:
    mon = next_monday()
    client.post(
        "/api/absences",
        json={
            "technician_id": str(mechs[2].id),
            "start_date": iso(mon),
            "end_date": iso(mon),
            "category": "leave",
        },
    )
    r = _assign(client, _request(client, mon, mon), mechs[2])
    assert r.status_code == 428 and "absent" in r.json()["detail"]["message"]


def test_weekend_is_orange_on_bar_but_not_in_alert_centre(
    client: TestClient, mechs: list[Technician]
) -> None:
    sat = next_monday() + timedelta(days=5)
    a = _assign(client, _request(client, sat, sat + timedelta(days=1)), mechs[0]).json()
    c = _conflicts(client, sat)[a["id"]]
    assert c["level"] == "orange" and c["items"][0]["code"] == "weekend"
    assert not any(x["assignment_id"] == a["id"] for x in _alerts(client))


def test_neighbour_outside_window_is_detected(client: TestClient, mechs: list[Technician]) -> None:
    mon = next_monday(6)
    long = _assign(client, _request(client, mon, mon + timedelta(days=14)), mechs[0]).json()
    _assign(client, _request(client, mon, mon), mechs[0], confirm_conflict=True)
    window = _planning(client, mon + timedelta(days=7), days=14)
    assert {c["assignment_id"] for c in window["conflicts"]} == {long["id"]}


# --------------------------------------------------------------------------- R-05 orange, F-40


def test_pending_too_long_and_expired_link(
    client: TestClient, mechs: list[Technician], seeded: Session
) -> None:
    mon = next_monday()
    a = _assign(client, _request(client, mon, mon), mechs[0]).json()
    b = _assign(client, _request(client, mon, mon), mechs[1]).json()
    now = datetime.now(UTC)
    for x, proposed, expires in ((a, 4, 10), (b, 20, -1)):
        row = seeded.get(Assignment, UUID(x["id"]))
        row.status = AssignmentStatus.PENDING_RESPONSE
        row.proposed_at = now - timedelta(days=proposed)
        row.token_expires_at = now + timedelta(days=expires)
    seeded.commit()
    kinds = {x["assignment_id"]: x["kind"] for x in _alerts(client)}
    assert kinds[a["id"]] == "pending_too_long" and kinds[b["id"]] == "link_expired"


def test_pending_date_change_on_assigned_request(
    client: TestClient, mechs: list[Technician], seeded: Session
) -> None:
    mon = next_monday()
    req = _request(client, mon, mon)
    a = _assign(client, req, mechs[0]).json()
    seeded.add(
        ChangeRequest(
            request_id=UUID(req["id"]),
            kind=ChangeKind.MODIFICATION,
            proposed_changes={
                "old": {"start_date": iso(mon)},
                "new": {"start_date": iso(mon + timedelta(days=7))},
            },
        )
    )
    seeded.commit()
    assert _conflicts(client, mon)[a["id"]]["items"][0]["code"] == "date_change"
    kinds = {x["kind"] for x in _alerts(client) if x["request_id"] == req["id"]}
    assert kinds == {"date_change", "pending_change"}


# --------------------------------------------------------------------------- R-06, F-11


def test_date_alerts_on_unassigned_requests_and_vignettes(
    client: TestClient, mechs: list[Technician]
) -> None:
    today = today_brussels()
    soon = _request(client, today + timedelta(days=1), today + timedelta(days=1), technicians_needed=2)
    medium = _request(client, next_monday(1) + timedelta(days=3), next_monday(1) + timedelta(days=3))
    far = _request(client, today + timedelta(days=60), today + timedelta(days=60))
    alerts = {x["request_id"]: x for x in _alerts(client) if x["kind"] == "date_close"}
    assert (
        alerts[soon["id"]]["level"] == "red" and "2 technicien(s) à trouver" in alerts[soon["id"]]["message"]
    )
    assert far["id"] not in alerts
    vignettes = {v["id"]: v for v in client.get("/api/requests").json()}
    assert vignettes[soon["id"]]["date_alert"] == "red"
    assert vignettes[far["id"]]["date_alert"] is None
    assert vignettes[medium["id"]]["working_days_left"] is not None
    # partiellement attribuée : toujours en alerte ; complète : l'alerte disparaît (F-41)
    _assign(client, soon, mechs[0])
    assert any(x["request_id"] == soon["id"] for x in _alerts(client) if x["kind"] == "date_close")
    _assign(client, soon, mechs[1])
    assert not any(x["request_id"] == soon["id"] for x in _alerts(client) if x["kind"] == "date_close")


def test_refused_request_alert(client: TestClient, mechs: list[Technician]) -> None:
    mon = next_monday(8)
    req = _request(client, mon, mon)
    a = _assign(client, req, mechs[0]).json()
    client.patch(f"/api/assignments/{a['id']}", json={"version": a["version"], "response": "refuse"})
    assert any(x["kind"] == "refused" and x["request_id"] == req["id"] for x in _alerts(client))


def test_alerts_sorted_red_first(client: TestClient, mechs: list[Technician]) -> None:
    today = today_brussels()
    _request(client, today + timedelta(days=12), today + timedelta(days=12))
    _request(client, today + timedelta(days=1), today + timedelta(days=1))
    levels = [x["level"] for x in _alerts(client)]
    assert levels == sorted(levels, key=lambda lv: lv != "red")


# --------------------------------------------------------------------------- F-43


def test_alert_settings(client: TestClient) -> None:
    current = client.get("/api/settings/alerts").json()
    assert current == {
        "alert_orange_days": 10,
        "alert_red_days": 5,
        "pending_response_alert_days": 3,
        "token_validity_days": 14,
    }
    assert client.put("/api/settings/alerts", json={**current, "alert_red_days": 12}).status_code == 422
    assert client.put("/api/settings/alerts", headers=PLANNER, json=current).status_code == 403
    r = client.put("/api/settings/alerts", json={**current, "alert_orange_days": 20, "alert_red_days": 15})
    assert r.status_code == 200 and r.json()["alert_red_days"] == 15
    today = today_brussels()
    req = _request(client, today + timedelta(days=16), today + timedelta(days=16))
    alert = next(x for x in _alerts(client) if x["request_id"] == req["id"])
    assert alert["level"] == "red"  # 16 jours calendaires < 15 jours ouvrés
