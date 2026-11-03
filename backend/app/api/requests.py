"""Phase 2 : zone tampon et vignettes (F-10 à F-15), attribution par glisser-déposer (R-03).
Le brouillon de mail de F-20 arrive avec la boîte d'envoi (phase 3)."""

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import audit
from app.api.errors import check_version, not_found, precondition, unprocessable
from app.api.planning import AssignmentOut, _technician
from app.auth import CurrentUserDep, SessionDep
from app.models import (
    ACTIVE_ASSIGNMENT_STATUSES,
    Assignment,
    AssignmentStatus,
    AuditLog,
    ChangeKind,
    ChangeRequest,
    MissionType,
    OutboundKind,
    ProposalStatus,
    Request,
    RequestOrigin,
    RequestStatus,
    SourceKind,
    SourceMessage,
    Technician,
)
from app.rules.requests import compute_missing_fields, split_period
from app.rules.status import compute_request_status
from app.services.alerts import alert_settings, holidays_between, placement_conflicts, request_date_alert
from app.services.dates import today_brussels
from app.services.outbox import discard_unsent, draft_tech_cancellation, draft_tech_proposal
from app.services.responses import REFUSED_BADGE
from app.services.status import refresh_request_status

router = APIRouter(prefix="/api")

# Champs copiés lors d'une division et complétés lors d'une fusion (F-15)
COPY_FIELDS = (
    "type_code",
    "title",
    "requester_name",
    "requester_email",
    "cf",
    "client",
    "location",
    "objective",
    "date_flexible",
    "flex_justification",
    "comments",
    "needed_by",
    "attachment_url",
)


# --------------------------------------------------------------------------- schémas


class ProductLine(BaseModel):
    product: str = ""
    ammunition: str | None = None
    comment: str | None = None


def _check_url(v: str | None) -> str | None:
    v = (v or "").strip() or None
    if v and not v.lower().startswith(("http://", "https://")):
        raise ValueError("Le lien doit commencer par http:// ou https://")
    return v


class RequestFields(BaseModel):
    """Champs du formulaire SharePoint existant, plus type, titre et lieu (F-12)."""

    type_code: str | None = None
    title: str = Field(default="", max_length=300)
    requester_name: str | None = None
    requester_email: str | None = None
    cf: str | None = None
    client: str | None = None
    location: str | None = None
    objective: str | None = None
    technicians_needed: int = Field(default=1, ge=1, le=50)
    start_date: date | None = None
    end_date: date | None = None
    date_flexible: bool = False
    flex_justification: str | None = None
    comments: str | None = None
    products: list[ProductLine] = []
    needed_by: date | None = None
    attachment_url: str | None = None

    _url = field_validator("attachment_url")(_check_url)

    @model_validator(mode="after")
    def _period(self) -> "RequestFields":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("La date de fin doit être postérieure ou égale à la date de début.")
        return self


class RequestPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int
    type_code: str | None = None
    title: str | None = Field(default=None, max_length=300)
    requester_name: str | None = None
    requester_email: str | None = None
    cf: str | None = None
    client: str | None = None
    location: str | None = None
    objective: str | None = None
    technicians_needed: int | None = Field(default=None, ge=1, le=50)
    start_date: date | None = None
    end_date: date | None = None
    date_flexible: bool | None = None
    flex_justification: str | None = None
    comments: str | None = None
    products: list[ProductLine] | None = None
    needed_by: date | None = None
    attachment_url: str | None = None
    needs_review: bool | None = None

    _url = field_validator("attachment_url")(_check_url)


class VignetteOut(BaseModel):
    """F-11"""

    id: UUID
    ref: str
    type_code: str | None
    title: str
    requester_name: str | None
    client: str | None
    cf: str | None
    location: str | None
    start_date: date | None
    end_date: date | None
    technicians_needed: int
    remaining: int
    status: RequestStatus
    needs_review: bool
    missing_fields: list[str]
    badges: list[str]
    pending_changes: list[ChangeKind]
    origin: RequestOrigin
    date_flexible: bool
    date_alert: Literal["red", "orange"] | None = None
    working_days_left: int | None = None
    version: int


class AssignmentLine(AssignmentOut):
    technician_name: str
    created_at: datetime


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    source: SourceKind
    received_at: datetime
    sender: str | None
    subject: str | None
    body_excerpt: str | None
    web_link: str | None


class ChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    kind: ChangeKind
    proposed_changes: dict[str, Any]
    created_at: datetime


class HistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime
    actor: str
    action: str
    entity_type: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class RequestDetail(RequestFields):
    """F-14"""

    id: UUID
    ref: str
    status: RequestStatus
    needs_review: bool
    missing_fields: list[str]
    badges: list[str]
    origin: RequestOrigin
    confidence: float | None
    requested_at: datetime | None
    cancelled_at: datetime | None
    merged_into_ref: str | None
    remaining: int
    version: int
    assignments: list[AssignmentLine]
    sources: list[SourceOut]
    pending_changes: list[ChangeOut]
    history: list[HistoryOut]


class AssignmentCreate(BaseModel):
    request_version: int
    technician_id: UUID
    start_date: date
    end_date: date
    # R-03 : dépose hors des dates d'une demande datée → confirmation explicite
    confirm_dates_differ: bool = False
    # R-03 : demande sans dates complètes → proposer d'y écrire les dates de l'affectation
    write_dates_to_request: bool = False
    # R-02 : attribuer malgré un chevauchement ou une absence
    confirm_conflict: bool = False

    @model_validator(mode="after")
    def _period(self) -> "AssignmentCreate":
        if self.end_date < self.start_date:
            raise ValueError("La date de fin doit être postérieure ou égale à la date de début.")
        return self


class MergeIn(BaseModel):
    version: int
    other_id: UUID
    other_version: int


class SplitIn(BaseModel):
    version: int
    split_date: date


# --------------------------------------------------------------------------- utilitaires


def _now() -> datetime:
    return datetime.now(UTC)


def _active(session: Session, request_id: UUID) -> list[Assignment]:
    return list(
        session.scalars(
            select(Assignment).where(
                Assignment.request_id == request_id, Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES)
            )
        )
    )


def _get_open(session: Session, request_id: UUID) -> Request:
    req = session.get(Request, request_id)
    if req is None:
        raise not_found("Demande")
    if req.cancelled_at is not None:
        raise unprocessable("Cette demande est annulée")
    return req


def next_ref(session: Session, year: int) -> str:
    prefix = f"D-{year}-"
    last = session.scalar(select(func.max(Request.ref)).where(Request.ref.like(f"{prefix}%")))
    n = int(last.removeprefix(prefix)) + 1 if last else 1
    return f"{prefix}{n:04d}"


def _refresh_missing(req: Request, technicians_known: bool | None = None) -> None:
    if technicians_known is None:
        technicians_known = "technicians_needed" not in (req.missing_fields or [])
    req.missing_fields = compute_missing_fields(
        type_code=req.type_code,
        start_date=req.start_date,
        end_date=req.end_date,
        location=req.location,
        technicians_known=technicians_known,
    )


def _check_type(session: Session, code: str | None) -> None:
    if code is not None and session.scalar(select(MissionType.id).where(MissionType.code == code)) is None:
        raise unprocessable("Type d'activité inconnu")


def _touch(req: Request) -> None:
    """Force la montée de version de la demande (verrou optimiste sur ses attributions)."""
    req.updated_at = _now()


def _pending_changes(session: Session, ids: list[UUID]) -> dict[UUID, list[ChangeKind]]:
    out: dict[UUID, list[ChangeKind]] = {}
    if not ids:
        return out
    rows = session.execute(
        select(ChangeRequest.request_id, ChangeRequest.kind).where(
            ChangeRequest.request_id.in_(ids), ChangeRequest.status == ProposalStatus.PENDING
        )
    )
    for rid, kind in rows:
        if rid is not None:
            out.setdefault(rid, []).append(kind)
    return out


def _vignettes(session: Session, requests: list[Request]) -> list[VignetteOut]:
    ids = [r.id for r in requests]
    counts = dict(
        session.execute(
            select(Assignment.request_id, func.count())
            .where(Assignment.request_id.in_(ids), Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES))
            .group_by(Assignment.request_id)
        ).all()
    )
    changes = _pending_changes(session, ids)
    today = today_brussels()
    settings = alert_settings(session)
    holidays = holidays_between(session, today, today + timedelta(days=400))
    alerts = {r.id: request_date_alert(r, today, holidays, settings) for r in requests}
    return [
        VignetteOut(
            id=r.id,
            ref=r.ref,
            type_code=r.type_code,
            title=r.title,
            requester_name=r.requester_name,
            client=r.client,
            cf=r.cf,
            location=r.location,
            start_date=r.start_date,
            end_date=r.end_date,
            technicians_needed=r.technicians_needed,
            remaining=max(0, r.technicians_needed - counts.get(r.id, 0)),
            status=r.status,
            needs_review=r.needs_review,
            missing_fields=r.missing_fields or [],
            badges=r.badges or [],
            pending_changes=changes.get(r.id, []),
            origin=r.origin,
            date_flexible=r.date_flexible,
            date_alert=(alerts[r.id] or (None, None))[0],
            working_days_left=(alerts[r.id] or (None, None))[1],
            version=r.version,
        )
        for r in requests
    ]


def _detail(session: Session, req: Request) -> RequestDetail:
    assignments = list(
        session.scalars(
            select(Assignment).where(Assignment.request_id == req.id).order_by(Assignment.created_at)
        )
    )
    techs = {t.id: t for t in session.scalars(select(Technician))}
    lines = [
        AssignmentLine(
            **AssignmentOut.model_validate(a).model_dump(),
            technician_name=" ".join(
                filter(None, [techs[a.technician_id].first_name, techs[a.technician_id].last_name])
            ),
            created_at=a.created_at,
        )
        for a in assignments
    ]
    entity_ids = [req.id, *[a.id for a in assignments]]
    history = session.scalars(
        select(AuditLog)
        .where(AuditLog.entity_id.in_(entity_ids))
        .order_by(AuditLog.created_at.desc())
        .limit(200)
    )
    sources = session.scalars(
        select(SourceMessage).where(SourceMessage.request_id == req.id).order_by(SourceMessage.received_at)
    )
    changes = session.scalars(
        select(ChangeRequest).where(
            ChangeRequest.request_id == req.id, ChangeRequest.status == ProposalStatus.PENDING
        )
    )
    merged = session.get(Request, req.merged_into_id) if req.merged_into_id else None
    active = sum(a.status in ACTIVE_ASSIGNMENT_STATUSES for a in assignments)
    fields = {f: getattr(req, f) for f in RequestFields.model_fields}
    return RequestDetail(
        **fields,
        id=req.id,
        ref=req.ref,
        status=req.status,
        needs_review=req.needs_review,
        missing_fields=req.missing_fields or [],
        badges=req.badges or [],
        origin=req.origin,
        confidence=req.confidence,
        requested_at=req.requested_at,
        cancelled_at=req.cancelled_at,
        merged_into_ref=merged.ref if merged else None,
        remaining=max(0, req.technicians_needed - active),
        version=req.version,
        assignments=lines,
        sources=[SourceOut.model_validate(s) for s in sources],
        pending_changes=[ChangeOut.model_validate(c) for c in changes],
        history=[HistoryOut.model_validate(h) for h in history],
    )


# --------------------------------------------------------------------------- F-10, F-11


@router.get("/requests", response_model=list[VignetteOut])
def list_requests(
    session: SessionDep,
    _user: CurrentUserDep,
    view: Annotated[Literal["buffer", "all"], Query()] = "buffer",
) -> list[VignetteOut]:
    q = select(Request).where(Request.merged_into_id.is_(None))
    if view == "buffer":
        # F-10 : à attribuer, partiellement attribuées, ou à vérifier (hors annulées)
        q = q.where(
            Request.cancelled_at.is_(None),
            or_(
                Request.status.in_([RequestStatus.TO_ASSIGN, RequestStatus.PARTIALLY_ASSIGNED]),
                Request.needs_review.is_(True),
            ),
        )
    q = q.order_by(Request.start_date.is_(None), Request.start_date, Request.ref)
    return _vignettes(session, list(session.scalars(q)))


# --------------------------------------------------------------------------- F-12 à F-14


@router.post("/requests", response_model=RequestDetail, status_code=status.HTTP_201_CREATED)
def create_request(body: RequestFields, session: SessionDep, user: CurrentUserDep) -> RequestDetail:
    _check_type(session, body.type_code)
    data = body.model_dump()
    data["products"] = [p.model_dump() for p in body.products]
    req = Request(
        **data,
        ref=next_ref(session, datetime.now(UTC).year),
        origin=RequestOrigin.MANUAL,
        requested_at=_now(),
        status=compute_request_status(body.technicians_needed, [], None),
        needs_review=False,
    )
    _refresh_missing(req, technicians_known=True)
    session.add(req)
    session.flush()
    audit.record(session, user.audit_actor, "request.create", req, None, audit.snapshot(req))
    session.commit()
    return _detail(session, req)


@router.get("/requests/{request_id}", response_model=RequestDetail)
def get_request(request_id: UUID, session: SessionDep, _user: CurrentUserDep) -> RequestDetail:
    req = session.get(Request, request_id)
    if req is None:
        raise not_found("Demande")
    return _detail(session, req)


@router.patch("/requests/{request_id}", response_model=RequestDetail)
def update_request(
    request_id: UUID, body: RequestPatch, session: SessionDep, user: CurrentUserDep
) -> RequestDetail:
    """F-14 : tous les champs sont éditables. Les dates des affectations existantes ne bougent pas
    (P1) : elles se déplacent sur le planning."""
    req = _get_open(session, request_id)
    check_version(req.version, body.version)
    changes = body.model_dump(exclude_unset=True, exclude={"version"})
    if "type_code" in changes:
        _check_type(session, changes["type_code"])
    if "title" in changes and changes["title"] is None:
        changes["title"] = ""
    for flag in ("technicians_needed", "date_flexible", "needs_review"):
        if flag in changes and changes[flag] is None:
            raise unprocessable(f"Le champ {flag} ne peut pas être vide")
    if "products" in changes:
        changes["products"] = [ProductLine.model_validate(p).model_dump() for p in changes["products"]]
    start = changes.get("start_date", req.start_date)
    end = changes.get("end_date", req.end_date)
    if start and end and end < start:
        raise unprocessable("La date de fin doit être postérieure ou égale à la date de début.")
    if "technicians_needed" in changes and changes["technicians_needed"] < len(_active(session, req.id)):
        raise unprocessable("Le nombre de techniciens ne peut pas être inférieur aux affectations en cours")

    before = audit.snapshot(req)
    for field, value in changes.items():
        setattr(req, field, value)
    _refresh_missing(req, technicians_known=True if "technicians_needed" in changes else None)
    session.flush()
    refresh_request_status(session, req)
    action = "request.review" if set(changes) == {"needs_review"} else "request.update"
    audit.record(session, user.audit_actor, action, req, before, audit.snapshot(req))
    session.commit()
    return _detail(session, req)


# --------------------------------------------------------------------------- attribution (R-03, F-20 partiel)


@router.post(
    "/requests/{request_id}/assignments", response_model=AssignmentOut, status_code=status.HTTP_201_CREATED
)
def create_assignment(
    request_id: UUID, body: AssignmentCreate, session: SessionDep, user: CurrentUserDep
) -> Assignment:
    req = _get_open(session, request_id)
    check_version(req.version, body.request_version)
    _technician(session, body.technician_id, mechanic_only=True)
    active = _active(session, req.id)
    if len(active) >= req.technicians_needed:
        raise unprocessable("Tous les postes de cette demande sont déjà pourvus")
    if any(a.technician_id == body.technician_id for a in active):
        raise unprocessable("Ce technicien est déjà affecté à cette demande")

    dated = req.start_date is not None and req.end_date is not None
    if (
        dated
        and (body.start_date, body.end_date) != (req.start_date, req.end_date)
        and not body.confirm_dates_differ
    ):
        raise precondition("dates_differ", "Les dates diffèrent de celles de la demande : confirmez.")
    conflicts = placement_conflicts(session, body.technician_id, body.start_date, body.end_date)
    if conflicts and not body.confirm_conflict:
        raise precondition("conflict", f"Conflit : {' ; '.join(conflicts)}. Attribuer quand même ?")  # R-02

    before_req = audit.snapshot(req)
    a = Assignment(
        request_id=req.id,
        technician_id=body.technician_id,
        start_date=body.start_date,
        end_date=body.end_date,
        status=AssignmentStatus.DRAFT,
    )
    session.add(a)
    if not dated and body.write_dates_to_request:
        req.start_date = req.start_date or body.start_date
        req.end_date = req.end_date or body.end_date
        if req.end_date < req.start_date:
            req.end_date = req.start_date
        _refresh_missing(req)
    if REFUSED_BADGE in (req.badges or []):
        req.badges = [b for b in req.badges if b != REFUSED_BADGE]
    _touch(req)
    session.flush()
    refresh_request_status(session, req)
    draft_tech_proposal(session, a)  # F-20 : « Mail préparé, à valider »
    audit.record(session, user.audit_actor, "assignment.create", a, None, audit.snapshot(a))
    if not dated and body.write_dates_to_request:
        audit.record(session, user.audit_actor, "request.update", req, before_req, audit.snapshot(req))
    session.commit()
    return a


@router.delete("/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_assignment(
    assignment_id: UUID,
    version: Annotated[int, Query()],
    session: SessionDep,
    user: CurrentUserDep,
    confirm: Annotated[bool, Query()] = False,
) -> Response:
    """Retire un brouillon, ou annule une proposition envoyée (F-26) après confirmation.
    L'affectation est conservée en « cancelled » ; un mail d'information est préparé si besoin."""
    a = session.get(Assignment, assignment_id)
    if a is None:
        raise not_found("Activité")
    check_version(a.version, version)
    if a.status not in ACTIVE_ASSIGNMENT_STATUSES:
        raise unprocessable("Cette activité n'est plus active")
    sent = a.status in (AssignmentStatus.PENDING_RESPONSE, AssignmentStatus.ACCEPTED)
    if sent and not confirm:
        raise precondition("confirm_sent", "Cette proposition a déjà été envoyée : confirmez l'annulation.")
    before = audit.snapshot(a)
    a.status = AssignmentStatus.CANCELLED
    a.response_token_hash = None  # le lien envoyé n'est plus valable
    discard_unsent(session, a.id, OutboundKind.TECH_PROPOSAL)
    session.flush()
    if sent:
        draft_tech_cancellation(session, a)
    req = session.get(Request, a.request_id)
    if req is not None:
        _touch(req)
        refresh_request_status(session, req)
    audit.record(session, user.audit_actor, "assignment.cancel", a, before, audit.snapshot(a))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- F-15


@router.post("/requests/{request_id}/merge", response_model=RequestDetail)
def merge_requests(
    request_id: UUID, body: MergeIn, session: SessionDep, user: CurrentUserDep
) -> RequestDetail:
    """La demande de l'URL est conservée ; other_id est absorbée puis annulée."""
    if body.other_id == request_id:
        raise unprocessable("Choisissez deux demandes différentes")
    keep = _get_open(session, request_id)
    other = _get_open(session, body.other_id)
    check_version(keep.version, body.version)
    check_version(other.version, body.other_version)

    keep_active, other_active = _active(session, keep.id), _active(session, other.id)
    if len(keep_active) + len(other_active) > keep.technicians_needed:
        raise unprocessable(
            "Fusion impossible : le nombre d'affectations dépasserait le nombre de techniciens demandés"
        )
    if {a.technician_id for a in keep_active} & {a.technician_id for a in other_active}:
        raise unprocessable("Fusion impossible : un même technicien est affecté aux deux demandes")

    before_keep, before_other = audit.snapshot(keep), audit.snapshot(other)
    for a in other_active:
        a.request_id = keep.id
    for msg in session.scalars(select(SourceMessage).where(SourceMessage.request_id == other.id)):
        msg.request_id = keep.id
    for field in COPY_FIELDS:
        if getattr(keep, field) in (None, "") and getattr(other, field) not in (None, ""):
            setattr(keep, field, getattr(other, field))
    if keep.start_date is None and keep.end_date is None:
        keep.start_date, keep.end_date = other.start_date, other.end_date
    keep.needs_review = keep.needs_review or other.needs_review
    other.cancelled_at, other.cancelled_by, other.merged_into_id = _now(), user.id, keep.id
    _refresh_missing(keep)
    _touch(keep)
    session.flush()
    refresh_request_status(session, keep)
    refresh_request_status(session, other)
    audit.record(session, user.audit_actor, "request.merge", keep, before_keep, audit.snapshot(keep))
    audit.record(session, user.audit_actor, "request.merged_into", other, before_other, audit.snapshot(other))
    session.commit()
    return _detail(session, keep)


@router.post("/requests/{request_id}/split", response_model=RequestDetail)
def split_request(
    request_id: UUID, body: SplitIn, session: SessionDep, user: CurrentUserDep
) -> RequestDetail:
    """Coupe la demande à split_date (premier jour de la seconde partie). Renvoie la nouvelle demande."""
    req = _get_open(session, request_id)
    check_version(req.version, body.version)
    if req.start_date is None or req.end_date is None:
        raise unprocessable("La demande doit avoir une date de début et une date de fin")
    try:
        (s1, e1), (s2, e2) = split_period(req.start_date, req.end_date, body.split_date)
    except ValueError as exc:
        raise unprocessable(str(exc)) from exc

    before = audit.snapshot(req)
    new = Request(
        **{f: getattr(req, f) for f in COPY_FIELDS},
        ref=next_ref(session, datetime.now(UTC).year),
        origin=req.origin,
        requested_at=req.requested_at,
        technicians_needed=req.technicians_needed,
        products=list(req.products or []),
        needs_review=req.needs_review,
        confidence=req.confidence,
        start_date=s2,
        end_date=e2,
        status=compute_request_status(req.technicians_needed, [], None),
        missing_fields=list(req.missing_fields or []),
    )
    session.add(new)
    req.end_date = e1
    session.flush()

    for a in _active(session, req.id):
        if a.start_date >= s2:
            a.request_id = new.id
        elif a.end_date >= s2:
            # à cheval : coupé en deux, même technicien et même statut, sans nouveau mail
            session.add(
                Assignment(
                    request_id=new.id,
                    technician_id=a.technician_id,
                    start_date=s2,
                    end_date=a.end_date,
                    status=a.status,
                    proposed_at=a.proposed_at,
                    responded_at=a.responded_at,
                    partner_electronician_id=a.partner_electronician_id,
                )
            )
            a.end_date = e1
    _touch(req)
    session.flush()
    refresh_request_status(session, req)
    refresh_request_status(session, new)
    audit.record(session, user.audit_actor, "request.split", req, before, audit.snapshot(req))
    audit.record(session, user.audit_actor, "request.create_from_split", new, None, audit.snapshot(new))
    session.commit()
    return _detail(session, new)
