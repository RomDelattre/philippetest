"""Conflits (R-05) et alertes (R-06, F-40) calculés depuis la base. Rien n'est stocké : une alerte
disparaît d'elle-même quand sa cause disparaît (F-41)."""

import datetime as _dt
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    ACTIVE_ASSIGNMENT_STATUSES,
    Absence,
    Assignment,
    ChangeKind,
    ChangeRequest,
    Holiday,
    ProposalStatus,
    Request,
    RequestStatus,
    Setting,
    Technician,
)
from app.rules.conflicts import (
    AbsenceFacts,
    AssignmentFacts,
    Conflict,
    ConflictInput,
    ConflictSettings,
    assignment_conflicts,
    date_alert,
    level_of,
)
from app.services.outbox import tech_name

ALERT_SETTINGS = {
    "alert_orange_days": 10,
    "alert_red_days": 5,
    "pending_response_alert_days": 3,
    "token_validity_days": 14,
}
# Les conflits de calendrier restent des voyants sur les barres, sans encombrer le centre d'alertes
CALENDAR_CODES = {"weekend", "holiday"}


def alert_settings(session: Session) -> dict[str, int]:
    rows = {s.key: s.value for s in session.scalars(select(Setting).where(Setting.key.in_(ALERT_SETTINGS)))}
    return {k: int(rows[k]) if isinstance(rows.get(k), int | float) else v for k, v in ALERT_SETTINGS.items()}


def holidays_between(session: Session, start: date, end: date) -> set[date]:
    return set(session.scalars(select(Holiday.date).where(Holiday.date >= start, Holiday.date <= end)))


def _pending_date_changes(session: Session) -> set[UUID]:
    out: set[UUID] = set()
    for cr in session.scalars(
        select(ChangeRequest).where(
            ChangeRequest.status == ProposalStatus.PENDING, ChangeRequest.kind == ChangeKind.MODIFICATION
        )
    ):
        changes = cr.proposed_changes or {}
        new = changes.get("new", changes) if isinstance(changes, dict) else {}
        if cr.request_id and isinstance(new, dict) and ({"start_date", "end_date"} & set(new)):
            out.add(cr.request_id)
    return out


def conflicts_for(
    session: Session, assignments: list[Assignment], now: datetime
) -> dict[UUID, list[Conflict]]:
    """Conflits des assignments donnés, en tenant compte de tous leurs voisins (même hors fenêtre)."""
    active = [a for a in assignments if a.status in ACTIVE_ASSIGNMENT_STATUSES]
    if not active:
        return {}
    techs = {a.technician_id for a in active}
    lo, hi = min(a.start_date for a in active), max(a.end_date for a in active)
    neighbours = list(
        session.scalars(
            select(Assignment).where(
                Assignment.technician_id.in_(techs),
                Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
                Assignment.start_date <= hi,
                Assignment.end_date >= lo,
            )
        )
    )
    refs = dict(
        session.execute(
            select(Request.id, Request.ref).where(Request.id.in_({a.request_id for a in neighbours}))
        )
        .tuples()
        .all()
    )
    absences = session.scalars(
        select(Absence).where(
            Absence.technician_id.in_(techs), Absence.start_date <= hi, Absence.end_date >= lo
        )
    )
    data = ConflictInput(
        assignments=[
            AssignmentFacts(
                a.id,
                a.technician_id,
                a.request_id,
                refs.get(a.request_id, "?"),
                a.start_date,
                a.end_date,
                a.status.value,
                a.proposed_at,
                a.token_expires_at,
            )
            for a in neighbours
        ],
        absences=[AbsenceFacts(ab.technician_id, ab.start_date, ab.end_date) for ab in absences],
        holidays=holidays_between(session, lo, hi),
        pending_date_change=_pending_date_changes(session),
    )
    result = assignment_conflicts(
        data, now, ConflictSettings(alert_settings(session)["pending_response_alert_days"])
    )
    wanted = {a.id for a in active}
    return {k: v for k, v in result.items() if k in wanted}


def placement_conflicts(
    session: Session, technician_id: UUID, start: date, end: date, exclude: UUID | None = None
) -> list[str]:
    """R-02 : chevauchements et absences qu'entraînerait une affectation, avant confirmation."""
    msgs: list[str] = []
    conditions = [
        Assignment.technician_id == technician_id,
        Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
        Assignment.start_date <= end,
        Assignment.end_date >= start,
    ]
    if exclude is not None:
        conditions.append(Assignment.id != exclude)
    others = session.scalars(
        select(Request.ref).join(Assignment, Assignment.request_id == Request.id).where(*conditions)
    )
    msgs += [f"chevauchement avec {ref}" for ref in others]
    for ab in session.scalars(
        select(Absence).where(
            Absence.technician_id == technician_id, Absence.start_date <= end, Absence.end_date >= start
        )
    ):
        msgs.append(f"technicien absent du {ab.start_date:%d/%m/%Y} au {ab.end_date:%d/%m/%Y}")
    return msgs


def request_date_alert(
    req: Request, today: date, holidays: set[date], settings: dict[str, int]
) -> tuple[Literal["red", "orange"], int] | None:
    """R-06 : seulement pour une demande à attribuer ou partiellement attribuée."""
    if req.cancelled_at or req.status not in (RequestStatus.TO_ASSIGN, RequestStatus.PARTIALLY_ASSIGNED):
        return None
    if (req.end_date or req.start_date or req.needed_by or today) < today:
        return None  # demande passée : plus d'alerte
    return date_alert(
        req.start_date or req.needed_by,
        today,
        holidays,
        settings["alert_orange_days"],
        settings["alert_red_days"],
    )


@dataclass
class Alert:
    key: str
    level: Literal["red", "orange"]
    kind: str
    message: str
    request_id: UUID | None = None
    request_ref: str | None = None
    assignment_id: UUID | None = None
    date: _dt.date | None = None


def compute_alerts(session: Session, today: date, now: datetime | None = None) -> list[Alert]:
    """F-40 : dates proches, conflits, refus, réponses trop attendues, changements en attente,
    activités remises dans le tampon."""
    now = now or datetime.now(UTC)
    settings = alert_settings(session)
    holidays = holidays_between(session, today, today + timedelta(days=400))
    alerts: list[Alert] = []
    open_requests = list(
        session.scalars(
            select(Request).where(Request.cancelled_at.is_(None), Request.merged_into_id.is_(None))
        )
    )
    by_id = {r.id: r for r in open_requests}

    for r in open_requests:
        da = request_date_alert(r, today, holidays, settings)
        if da:
            level, n = da
            when = "déjà commencée" if n == 0 else f"dans {n} jour(s) ouvré(s)"
            missing = r.technicians_needed - sum(
                1
                for _ in session.scalars(
                    select(Assignment.id).where(
                        Assignment.request_id == r.id, Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES)
                    )
                )
            )
            alerts.append(
                Alert(
                    f"date:{r.id}",
                    level,
                    "date_close",
                    f"{r.ref} {when}, {missing} technicien(s) à trouver",
                    r.id,
                    r.ref,
                    date=r.start_date or r.needed_by,
                )
            )
        if "technician_refused" in (r.badges or []) and r.status in (
            RequestStatus.TO_ASSIGN,
            RequestStatus.PARTIALLY_ASSIGNED,
        ):
            alerts.append(
                Alert(
                    f"refused:{r.id}",
                    "orange",
                    "refused",
                    f"{r.ref} refusée : à réattribuer",
                    r.id,
                    r.ref,
                    date=r.start_date,
                )
            )
        if "technician_absent" in (r.badges or []):
            alerts.append(
                Alert(
                    f"absent:{r.id}",
                    "orange",
                    "back_to_buffer",
                    f"{r.ref} remise dans le tampon : technicien absent",
                    r.id,
                    r.ref,
                    date=r.start_date,
                )
            )

    for cr in session.scalars(select(ChangeRequest).where(ChangeRequest.status == ProposalStatus.PENDING)):
        cr_req = by_id.get(cr.request_id) if cr.request_id else None
        what = "Annulation" if cr.kind == ChangeKind.CANCELLATION else "Modification"
        alerts.append(
            Alert(
                f"change:{cr.id}",
                "orange",
                "pending_change",
                f"{what} en attente{f' pour {cr_req.ref}' if cr_req else ' (demande à identifier)'}",
                cr_req.id if cr_req else None,
                cr_req.ref if cr_req else None,
                date=cr_req.start_date if cr_req else None,
            )
        )

    current = list(
        session.scalars(
            select(Assignment).where(
                Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
                or_(Assignment.end_date >= today, Assignment.status == "pending_response"),
            )
        )
    )
    techs = {t.id: t for t in session.scalars(select(Technician))}
    refs = {r.id: r.ref for r in open_requests}
    for a_id, conflicts in conflicts_for(session, current, now).items():
        relevant = [c for c in conflicts if c.code not in CALENDAR_CODES]
        if not relevant:
            continue
        a = next(x for x in current if x.id == a_id)
        level = level_of(relevant) or "orange"
        who = tech_name(techs[a.technician_id]) if a.technician_id in techs else "?"
        kind = "conflict" if level == "red" else relevant[0].code
        alerts.append(
            Alert(
                f"assignment:{a.id}",
                level,
                kind,
                f"{refs.get(a.request_id, '?')} · {who} : {' ; '.join(c.message for c in relevant)}",
                a.request_id,
                refs.get(a.request_id),
                a.id,
                a.start_date,
            )
        )

    alerts.sort(key=lambda x: (x.level != "red", x.date or date.max, x.key))
    return alerts
