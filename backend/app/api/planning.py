"""Phase 1 : planning (F-01 à F-08 hors conflits), déplacement d'activités (F-07),
absences manuelles (F-31)."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.api.errors import check_version, not_found, unprocessable
from app.api.routes import HolidayOut, TechnicianOut
from app.auth import CurrentUserDep, SessionDep
from app.models import (
    ACTIVE_ASSIGNMENT_STATUSES,
    Absence,
    AbsenceCategory,
    Assignment,
    AssignmentStatus,
    Holiday,
    Request,
    RequestStatus,
    Technician,
    TechnicianRole,
)
from app.rules.periods import overlaps
from app.rules.status import compute_request_status

router = APIRouter(prefix="/api")

MAX_WINDOW_DAYS = 370


# --------------------------------------------------------------------------- schémas


class RequestSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    ref: str
    type_code: str | None
    title: str
    requester_name: str | None
    cf: str | None
    client: str | None
    location: str | None
    start_date: date | None
    end_date: date | None
    technicians_needed: int
    status: RequestStatus


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    request_id: UUID
    technician_id: UUID
    start_date: date
    end_date: date
    status: AssignmentStatus
    partner_electronician_id: UUID | None
    version: int


class AssignmentDetail(AssignmentOut):
    request: RequestSummary


class AbsenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    technician_id: UUID
    start_date: date
    end_date: date
    category: AbsenceCategory
    version: int


class PlanningOut(BaseModel):
    window_start: date
    window_end: date
    technicians: list[TechnicianOut]
    assignments: list[AssignmentOut]
    requests: list[RequestSummary]
    absences: list[AbsenceOut]
    holidays: list[HolidayOut]


class AssignmentPatch(BaseModel):
    version: int
    technician_id: UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    # F-07 : déplacer une activité déjà proposée ou confirmée exige une confirmation explicite
    confirm: bool = False


class AbsenceIn(BaseModel):
    technician_id: UUID
    start_date: date
    end_date: date
    category: AbsenceCategory

    @model_validator(mode="after")
    def _period(self) -> "AbsenceIn":
        if self.end_date < self.start_date:
            raise ValueError("La date de fin doit être postérieure ou égale à la date de début.")
        return self


class AbsencePatch(AbsenceIn):
    version: int


# --------------------------------------------------------------------------- utilitaires


def _window(from_: date, to: date) -> None:
    if to < from_:
        raise unprocessable("« to » doit être postérieure ou égale à « from »")
    if (to - from_).days > MAX_WINDOW_DAYS:
        raise unprocessable("Fenêtre limitée à un an")


def refresh_request_status(session: Session, request: Request) -> None:
    """R-01 : seul point d'écriture de requests.status."""
    statuses = session.scalars(select(Assignment.status).where(Assignment.request_id == request.id))
    new = compute_request_status(request.technicians_needed, statuses, request.cancelled_at)
    if new != request.status:
        request.status = new


def _technician(session: Session, tech_id: UUID, *, mechanic_only: bool = False) -> Technician:
    tech = session.get(Technician, tech_id)
    if tech is None or not tech.active:
        raise unprocessable("Technicien inconnu ou inactif")
    if mechanic_only and tech.role != TechnicianRole.MECHANIC:
        # Le planning détaillé des électroniciens est exclu de la V1 (2.2, R-11)
        raise unprocessable("Une activité ne peut être placée que sur un mécanicien")
    return tech


# --------------------------------------------------------------------------- planning


@router.get("/planning", response_model=PlanningOut)
def get_planning(
    session: SessionDep,
    _user: CurrentUserDep,
    from_: Annotated[date, Query(alias="from")],
    to: Annotated[date, Query()],
) -> PlanningOut:
    _window(from_, to)
    techs = session.scalars(
        select(Technician)
        .where(Technician.active.is_(True))
        .order_by(Technician.role, Technician.sort_order, Technician.last_name)
    ).all()
    assignments = session.scalars(
        select(Assignment)
        .where(
            Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
            Assignment.start_date <= to,
            Assignment.end_date >= from_,
        )
        .order_by(Assignment.start_date)
    ).all()
    request_ids = {a.request_id for a in assignments}
    requests = (
        session.scalars(select(Request).where(Request.id.in_(request_ids))).all() if request_ids else []
    )
    absences = session.scalars(
        select(Absence)
        .where(Absence.start_date <= to, Absence.end_date >= from_)
        .order_by(Absence.start_date)
    ).all()
    holidays = session.scalars(
        select(Holiday).where(Holiday.date >= from_, Holiday.date <= to).order_by(Holiday.date)
    ).all()
    return PlanningOut(
        window_start=from_,
        window_end=to,
        technicians=[TechnicianOut.model_validate(t) for t in techs],
        assignments=[AssignmentOut.model_validate(a) for a in assignments],
        requests=[RequestSummary.model_validate(r) for r in requests],
        absences=[AbsenceOut.model_validate(a) for a in absences],
        holidays=[HolidayOut.model_validate(h) for h in holidays],
    )


# --------------------------------------------------------------------------- assignments


@router.get("/assignments/{assignment_id}", response_model=AssignmentDetail)
def get_assignment(assignment_id: UUID, session: SessionDep, _user: CurrentUserDep) -> AssignmentDetail:
    a = session.get(Assignment, assignment_id)
    if a is None:
        raise not_found("Activité")
    req = session.get(Request, a.request_id)
    return AssignmentDetail.model_validate({**AssignmentOut.model_validate(a).model_dump(), "request": req})


@router.patch("/assignments/{assignment_id}", response_model=AssignmentOut)
def move_assignment(
    assignment_id: UUID, body: AssignmentPatch, session: SessionDep, user: CurrentUserDep
) -> Assignment:
    """F-07 : déplacement (autre technicien ou autres dates) et redimensionnement."""
    a = session.get(Assignment, assignment_id)
    if a is None:
        raise not_found("Activité")
    check_version(a.version, body.version)
    if a.status not in ACTIVE_ASSIGNMENT_STATUSES:
        raise unprocessable("Cette activité n'est plus active")

    new_tech = body.technician_id or a.technician_id
    new_start = body.start_date or a.start_date
    new_end = body.end_date or a.end_date
    if new_end < new_start:
        raise unprocessable("La date de fin doit être postérieure ou égale à la date de début.")
    if new_tech != a.technician_id:
        _technician(session, new_tech, mechanic_only=True)
    if (new_tech, new_start, new_end) == (a.technician_id, a.start_date, a.end_date):
        return a

    already_sent = a.status in (AssignmentStatus.PENDING_RESPONSE, AssignmentStatus.ACCEPTED)
    if already_sent and not body.confirm:
        raise HTTPException(
            status.HTTP_428_PRECONDITION_REQUIRED,
            "Cette activité a déjà été proposée au technicien : confirmez le déplacement.",
        )

    before = audit.snapshot(a)
    a.technician_id, a.start_date, a.end_date = new_tech, new_start, new_end
    if already_sent:
        # F-07 : retour en brouillon, l'ancien lien de réponse devient invalide.
        # Le nouveau mail (F-20) sera préparé automatiquement à partir de la phase 3.
        a.status = AssignmentStatus.DRAFT
        a.response_token_hash = None
        a.token_expires_at = None
        a.responded_at = None
    session.flush()
    req = session.get(Request, a.request_id)
    if req is not None:
        refresh_request_status(session, req)
    audit.record(session, user.audit_actor, "assignment.move", a, before, audit.snapshot(a))
    session.commit()
    return a


# --------------------------------------------------------------------------- absences (F-31)


def _check_absence_overlap(session: Session, body: AbsenceIn, exclude: UUID | None = None) -> None:
    others = session.scalars(select(Absence).where(Absence.technician_id == body.technician_id))
    for other in others:
        if other.id != exclude and overlaps(body.start_date, body.end_date, other.start_date, other.end_date):
            raise unprocessable("Ce technicien a déjà une absence sur cette période")


@router.get("/absences", response_model=list[AbsenceOut])
def list_absences(
    session: SessionDep,
    _user: CurrentUserDep,
    from_: Annotated[date, Query(alias="from")],
    to: Annotated[date, Query()],
) -> list[Absence]:
    _window(from_, to)
    q = (
        select(Absence)
        .where(Absence.start_date <= to, Absence.end_date >= from_)
        .order_by(Absence.start_date)
    )
    return list(session.scalars(q))


@router.post("/absences", response_model=AbsenceOut, status_code=status.HTTP_201_CREATED)
def create_absence(body: AbsenceIn, session: SessionDep, user: CurrentUserDep) -> Absence:
    _technician(session, body.technician_id)
    _check_absence_overlap(session, body)
    ab = Absence(**body.model_dump())
    session.add(ab)
    session.flush()
    audit.record(session, user.audit_actor, "absence.create", ab, None, audit.snapshot(ab))
    session.commit()
    return ab


@router.patch("/absences/{absence_id}", response_model=AbsenceOut)
def update_absence(
    absence_id: UUID, body: AbsencePatch, session: SessionDep, user: CurrentUserDep
) -> Absence:
    ab = session.get(Absence, absence_id)
    if ab is None:
        raise not_found("Absence")
    check_version(ab.version, body.version)
    _technician(session, body.technician_id)
    _check_absence_overlap(session, body, exclude=ab.id)
    before = audit.snapshot(ab)
    for field, value in body.model_dump(exclude={"version"}).items():
        setattr(ab, field, value)
    session.flush()
    audit.record(session, user.audit_actor, "absence.update", ab, before, audit.snapshot(ab))
    session.commit()
    return ab


@router.delete("/absences/{absence_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_absence(
    absence_id: UUID, version: Annotated[int, Query()], session: SessionDep, user: CurrentUserDep
) -> Response:
    ab = session.get(Absence, absence_id)
    if ab is None:
        raise not_found("Absence")
    check_version(ab.version, version)
    audit.record(session, user.audit_actor, "absence.delete", ab, audit.snapshot(ab), None)
    session.delete(ab)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
