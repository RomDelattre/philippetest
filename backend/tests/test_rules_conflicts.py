"""R-05, R-06 : tous les cas de conflits et d'alertes de date (critère de fin de la phase 4)."""

import time
import uuid
from datetime import UTC, date, datetime, timedelta

from app.holidays import belgian_holidays
from app.rules.conflicts import (
    AbsenceFacts,
    AssignmentFacts,
    ConflictInput,
    ConflictSettings,
    assignment_conflicts,
    date_alert,
    level_of,
    working_days_until,
)

D = date
NOW = datetime(2026, 11, 3, 10, tzinfo=UTC)
T1, T2 = uuid.uuid4(), uuid.uuid4()
HOL = {d for d, _ in belgian_holidays(2026)}


def a(start: date, end: date, tech=T1, status="accepted", ref="D-1", **kw) -> AssignmentFacts:
    return AssignmentFacts(
        uuid.uuid4(), tech, kw.pop("request_id", uuid.uuid4()), ref, start, end, status, **kw
    )


def codes(result, x: AssignmentFacts) -> list[str]:
    return [c.code for c in result.get(x.id, [])]


# --------------------------------------------------------------------------- R-05 rouge


def test_overlap_same_technician_is_red_on_both() -> None:
    x, y = a(D(2026, 11, 9), D(2026, 11, 11), ref="D-1"), a(D(2026, 11, 11), D(2026, 11, 12), ref="D-2")
    r = assignment_conflicts(ConflictInput([x, y]), NOW)
    assert codes(r, x) == ["overlap"] and codes(r, y) == ["overlap"]
    assert r[x.id][0].message == "Chevauchement avec D-2" and level_of(r[x.id]) == "red"


def test_no_overlap_for_adjacent_days_or_other_technician() -> None:
    x, y = a(D(2026, 11, 9), D(2026, 11, 10)), a(D(2026, 11, 11), D(2026, 11, 12))
    z = a(D(2026, 11, 9), D(2026, 11, 10), tech=T2)
    assert assignment_conflicts(ConflictInput([x, y, z]), NOW) == {}


def test_overlap_three_way() -> None:
    x = a(D(2026, 11, 9), D(2026, 11, 20), ref="D-1")
    y = a(D(2026, 11, 10), D(2026, 11, 10), ref="D-2")
    z = a(D(2026, 11, 18), D(2026, 11, 19), ref="D-3")
    r = assignment_conflicts(ConflictInput([x, y, z]), NOW)
    assert codes(r, x).count("overlap") == 2 and codes(r, y) == ["overlap"] and codes(r, z) == ["overlap"]


def test_activity_on_absence_is_red() -> None:
    x = a(D(2026, 11, 9), D(2026, 11, 11))
    r = assignment_conflicts(ConflictInput([x], [AbsenceFacts(T1, D(2026, 11, 11), D(2026, 11, 13))]), NOW)
    assert codes(r, x) == ["absence"]
    assert r[x.id][0].message == "Technicien absent du 11/11/2026 au 13/11/2026"
    other = assignment_conflicts(ConflictInput([x], [AbsenceFacts(T2, D(2026, 11, 9), D(2026, 11, 9))]), NOW)
    assert other == {}


# --------------------------------------------------------------------------- R-05 orange


def test_weekend_and_holiday_are_orange() -> None:
    x = a(D(2026, 11, 6), D(2026, 11, 9))  # vendredi → lundi
    y = a(D(2026, 11, 11), D(2026, 11, 11))  # Armistice
    r = assignment_conflicts(ConflictInput([x, y], holidays=HOL), NOW)
    assert codes(r, x) == ["weekend"] and codes(r, y) == ["holiday"]
    assert level_of(r[x.id]) == "orange"


def test_pending_date_change_on_assigned_request() -> None:
    rid = uuid.uuid4()
    x = a(D(2026, 11, 9), D(2026, 11, 10), request_id=rid)
    r = assignment_conflicts(ConflictInput([x], pending_date_change={rid}), NOW)
    assert codes(r, x) == ["date_change"]


def test_pending_response_too_long_with_parameter() -> None:
    x = a(D(2026, 11, 16), D(2026, 11, 16), status="pending_response", proposed_at=NOW - timedelta(days=4))
    y = a(D(2026, 11, 17), D(2026, 11, 17), status="pending_response", proposed_at=NOW - timedelta(days=3))
    r = assignment_conflicts(ConflictInput([x, y]), NOW)
    assert codes(r, x) == ["pending_too_long"] and codes(r, y) == []
    assert codes(assignment_conflicts(ConflictInput([y]), NOW, ConflictSettings(2)), y) == [
        "pending_too_long"
    ]


def test_expired_link() -> None:
    x = a(
        D(2026, 11, 16),
        D(2026, 11, 16),
        status="pending_response",
        proposed_at=NOW - timedelta(days=20),
        token_expires_at=NOW - timedelta(days=1),
    )
    assert codes(assignment_conflicts(ConflictInput([x]), NOW), x) == ["link_expired"]


def test_accepted_is_never_pending_too_long() -> None:
    x = a(D(2026, 11, 16), D(2026, 11, 16), status="accepted", proposed_at=NOW - timedelta(days=30))
    assert assignment_conflicts(ConflictInput([x]), NOW) == {}


def test_red_sorted_first() -> None:
    x = a(D(2026, 11, 7), D(2026, 11, 7))  # samedi
    r = assignment_conflicts(ConflictInput([x], [AbsenceFacts(T1, D(2026, 11, 7), D(2026, 11, 7))]), NOW)
    assert [c.level for c in r[x.id]] == ["red", "orange"]


# --------------------------------------------------------------------------- R-06


def test_working_days_skip_weekends_and_holidays() -> None:
    # mardi 03/11 → mardi 10/11 : 04, 05, 06, 09, 10 = 5 jours ouvrés
    assert working_days_until(D(2026, 11, 3), D(2026, 11, 10), HOL) == 5
    # le 11/11 est férié
    assert working_days_until(D(2026, 11, 3), D(2026, 11, 11), HOL) == 5
    assert working_days_until(D(2026, 11, 3), D(2026, 11, 2), HOL) == 0


def test_date_alert_thresholds() -> None:
    today = D(2026, 11, 3)
    assert date_alert(None, today, HOL) is None
    assert date_alert(D(2026, 11, 9), today, HOL) == ("red", 4)
    assert date_alert(D(2026, 11, 10), today, HOL) == ("orange", 5)
    assert date_alert(D(2026, 11, 16), today, HOL) == ("orange", 8)
    assert date_alert(D(2026, 11, 19), today, HOL) is None  # 11 jours ouvrés
    assert date_alert(D(2026, 11, 2), today, HOL) == ("red", 0)  # déjà commencée
    assert date_alert(D(2026, 11, 19), today, HOL, orange_days=12, red_days=6) == ("orange", 11)


# --------------------------------------------------------------------------- NF-11


def test_six_month_window_is_fast() -> None:
    start = D(2026, 11, 2)
    techs = [uuid.uuid4() for _ in range(25)]
    items = [
        a(start + timedelta(days=d), start + timedelta(days=d + 2), tech=t, ref=f"D-{i}")
        for i, (t, d) in enumerate((t, d) for t in techs for d in range(0, 182, 3))
    ]
    absences = [AbsenceFacts(t, start + timedelta(days=40), start + timedelta(days=44)) for t in techs]
    t0 = time.perf_counter()
    r = assignment_conflicts(ConflictInput(items, absences, HOL), NOW)
    assert time.perf_counter() - t0 < 0.3
    assert len(items) > 1500 and r
