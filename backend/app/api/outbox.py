"""F-50 à F-52 : mails à valider (administrateur seulement, F-80), modèles de mails, notifications."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.api.errors import check_version, not_found, unprocessable
from app.auth import AdminDep, CurrentUser, CurrentUserDep, SessionDep
from app.config import get_settings
from app.mail import MailSender, get_mail_sender
from app.models import (
    Assignment,
    AssignmentStatus,
    Notification,
    OutboundKind,
    OutboundMessage,
    OutboundStatus,
    Request,
    Setting,
    Technician,
)
from app.rules.templates import (
    DEFAULT_TEMPLATES,
    TEMPLATE_KEYS,
    missing_link_placeholders,
    redact_links,
    render,
)
from app.rules.tokens import expiry, new_token
from app.services.outbox import UNSENT, load_template, tech_name
from app.services.status import refresh_request_status

router = APIRouter(prefix="/api")

MailSenderDep = Annotated[MailSender, Depends(get_mail_sender)]


# --------------------------------------------------------------------------- schémas


class OutboxItem(BaseModel):
    id: UUID
    kind: OutboundKind
    to_email: str
    subject: str
    body: str
    status: OutboundStatus
    error: str | None
    request_id: UUID | None
    request_ref: str | None
    assignment_id: UUID | None
    technician_name: str | None
    missing_links: list[str]
    created_at: datetime
    sent_at: datetime | None
    version: int


class OutboxPatch(BaseModel):
    version: int
    to_email: str | None = Field(default=None, max_length=320)
    subject: str | None = Field(default=None, max_length=998)
    body: str | None = None


class SendItem(BaseModel):
    id: UUID
    version: int


class SendIn(BaseModel):
    items: list[SendItem] = Field(min_length=1, max_length=200)


class SendResult(BaseModel):
    id: UUID
    status: OutboundStatus | None
    error: str | None


class Template(BaseModel):
    subject: str = Field(min_length=1, max_length=998)
    body: str = Field(min_length=1)


class Templates(BaseModel):
    tech_proposal: Template
    requester_confirmation: Template
    tech_cancellation: Template


class NotificationOut(BaseModel):
    id: UUID
    kind: str
    message: str
    request_id: UUID | None
    assignment_id: UUID | None
    created_at: datetime
    read_at: datetime | None
    version: int


# --------------------------------------------------------------------------- utilitaires


def _now() -> datetime:
    return datetime.now(UTC)


def _item(session: Session, m: OutboundMessage) -> OutboxItem:
    req = session.get(Request, m.request_id) if m.request_id else None
    a = session.get(Assignment, m.assignment_id) if m.assignment_id else None
    tech = session.get(Technician, a.technician_id) if a else None
    missing = (
        missing_link_placeholders(m.body)
        if m.kind == OutboundKind.TECH_PROPOSAL and m.status in UNSENT
        else []
    )
    return OutboxItem(
        id=m.id,
        kind=m.kind,
        to_email=m.to_email,
        subject=m.subject,
        body=m.body,
        status=m.status,
        error=m.error,
        request_id=m.request_id,
        request_ref=req.ref if req else None,
        assignment_id=m.assignment_id,
        technician_name=tech_name(tech) if tech else None,
        missing_links=missing,
        created_at=m.created_at,
        sent_at=m.sent_at,
        version=m.version,
    )


def _setting(session: Session, key: str, default: int) -> int:
    row = session.scalar(select(Setting).where(Setting.key == key))
    return int(row.value) if row is not None and isinstance(row.value, int | float) else default


def _fail(session: Session, m: OutboundMessage, user: CurrentUser, error: str) -> SendResult:
    before = audit.snapshot(m)
    m.status, m.error = OutboundStatus.FAILED, error
    session.flush()
    audit.record(session, user.audit_actor, "outbound.failed", m, before, audit.snapshot(m))
    session.commit()
    return SendResult(id=m.id, status=m.status, error=error)


def _send_one(session: Session, m: OutboundMessage, sender: MailSender, user: CurrentUser) -> SendResult:
    if m.status not in UNSENT:
        return SendResult(id=m.id, status=m.status, error="Ce mail a déjà été envoyé ou supprimé")
    if "@" not in m.to_email:
        return _fail(session, m, user, "Adresse du destinataire manquante")

    body, a, links, token_hash = m.body, None, None, None
    if m.kind == OutboundKind.TECH_PROPOSAL:
        a = session.get(Assignment, m.assignment_id) if m.assignment_id else None
        if a is None or a.status != AssignmentStatus.DRAFT:
            return _fail(
                session, m, user, "L'affectation n'est plus en brouillon : ce mail ne peut plus partir"
            )
        missing = missing_link_placeholders(body)
        if missing:
            return _fail(session, m, user, f"Variables obligatoires absentes du corps : {', '.join(missing)}")
        token, token_hash = new_token()
        base = get_settings().public_base_url.rstrip("/")
        links = (f"{base}/api/respond/{token}?answer=accept", f"{base}/api/respond/{token}?answer=refuse")
        body = render(body, {"lien_accepter": links[0], "lien_refuser": links[1]})

    before = audit.snapshot(m)
    try:
        sender.send(m.to_email, m.subject, body)
    except Exception as exc:  # noqa: BLE001 - toute erreur du connecteur est rapportée (F-51)
        return _fail(session, m, user, str(exc) or exc.__class__.__name__)

    now = _now()
    m.status, m.error, m.sent_at, m.validated_by = OutboundStatus.SENT, None, now, user.id
    if a is not None and links is not None:
        a_before = audit.snapshot(a)
        m.body = redact_links(body, *links)  # le jeton en clair n'est jamais stocké (NF-02)
        a.status = AssignmentStatus.PENDING_RESPONSE
        a.response_token_hash = token_hash
        a.token_expires_at = expiry(now, _setting(session, "token_validity_days", 14))
        a.token_used_at = None
        a.proposed_at, a.responded_at = now, None
        req = session.get(Request, a.request_id)
        if req is not None:
            refresh_request_status(session, req)
        session.flush()
        audit.record(session, user.audit_actor, "assignment.propose", a, a_before, audit.snapshot(a))
    session.flush()
    audit.record(session, user.audit_actor, "outbound.send", m, before, audit.snapshot(m))
    session.commit()
    return SendResult(id=m.id, status=m.status, error=None)


# --------------------------------------------------------------------------- F-50, F-51


@router.get("/outbox", response_model=list[OutboxItem])
def list_outbox(
    session: SessionDep, _admin: AdminDep, view: Annotated[Literal["pending", "sent"], Query()] = "pending"
) -> list[OutboxItem]:
    q = select(OutboundMessage)
    if view == "pending":
        q = q.where(OutboundMessage.status.in_(UNSENT)).order_by(OutboundMessage.created_at)
    else:
        q = (
            q.where(OutboundMessage.status == OutboundStatus.SENT)
            .order_by(OutboundMessage.sent_at.desc())
            .limit(100)
        )
    return [_item(session, m) for m in session.scalars(q)]


@router.patch("/outbox/{message_id}", response_model=OutboxItem)
def edit_outbox(message_id: UUID, body: OutboxPatch, session: SessionDep, admin: AdminDep) -> OutboxItem:
    m = session.get(OutboundMessage, message_id)
    if m is None:
        raise not_found("Mail")
    check_version(m.version, body.version)
    if m.status not in UNSENT:
        raise unprocessable("Seul un mail non envoyé est modifiable")
    before = audit.snapshot(m)
    for field, value in body.model_dump(exclude_unset=True, exclude={"version"}).items():
        if value is None:
            raise unprocessable(f"Le champ {field} ne peut pas être vide")
        setattr(m, field, value.strip() if field == "to_email" else value)
    session.flush()
    audit.record(session, admin.audit_actor, "outbound.edit", m, before, audit.snapshot(m))
    session.commit()
    return _item(session, m)


@router.delete("/outbox/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard_outbox(
    message_id: UUID, version: Annotated[int, Query()], session: SessionDep, admin: AdminDep
) -> Response:
    m = session.get(OutboundMessage, message_id)
    if m is None:
        raise not_found("Mail")
    check_version(m.version, version)
    if m.status not in UNSENT:
        raise unprocessable("Seul un mail non envoyé peut être supprimé")
    before = audit.snapshot(m)
    m.status = OutboundStatus.DISCARDED
    session.flush()
    audit.record(session, admin.audit_actor, "outbound.discard", m, before, audit.snapshot(m))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/outbox/send", response_model=list[SendResult])
def send_outbox(
    body: SendIn, session: SessionDep, admin: AdminDep, sender: MailSenderDep
) -> list[SendResult]:
    """Envoi d'un mail ou d'un lot (F-51). Chaque mail est traité et enregistré indépendamment."""
    results: list[SendResult] = []
    for item in body.items:
        m = session.get(OutboundMessage, item.id)
        if m is None:
            results.append(SendResult(id=item.id, status=None, error="Mail introuvable"))
        elif m.version != item.version:
            results.append(SendResult(id=m.id, status=m.status, error="Mail modifié entre-temps : rechargez"))
        else:
            results.append(_send_one(session, m, sender, admin))
    return results


# --------------------------------------------------------------------------- F-52 : modèles


@router.get("/settings/mail-templates", response_model=Templates)
def get_templates(session: SessionDep, _admin: AdminDep) -> Templates:
    return Templates(**{name: Template(**load_template(session, name)) for name in DEFAULT_TEMPLATES})


@router.put("/settings/mail-templates", response_model=Templates)
def put_templates(body: Templates, session: SessionDep, admin: AdminDep) -> Templates:
    missing = missing_link_placeholders(body.tech_proposal.body)
    if missing:
        raise unprocessable(f"Le modèle de proposition doit contenir {', '.join(missing)}")
    for name, key in TEMPLATE_KEYS.items():
        value = getattr(body, name).model_dump()
        row = session.scalar(select(Setting).where(Setting.key == key))
        if row is None:
            row = Setting(key=key, value=value)
            session.add(row)
            session.flush()
            audit.record(session, admin.audit_actor, "settings.update", row, None, audit.snapshot(row))
        elif row.value != value:
            before = audit.snapshot(row)
            row.value = value
            session.flush()
            audit.record(session, admin.audit_actor, "settings.update", row, before, audit.snapshot(row))
    session.commit()
    return get_templates(session, admin)


# --------------------------------------------------------------------------- notifications (F-23, F-24)


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(session: SessionDep, _user: CurrentUserDep) -> list[Notification]:
    q = (
        select(Notification)
        .order_by(Notification.read_at.is_not(None), Notification.created_at.desc())
        .limit(50)
    )
    return list(session.scalars(q))


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
def read_notification(notification_id: UUID, session: SessionDep, _user: CurrentUserDep) -> Notification:
    n = session.get(Notification, notification_id)
    if n is None:
        raise not_found("Notification")
    if n.read_at is None:
        n.read_at = _now()
        session.commit()
    return n


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
def read_all_notifications(session: SessionDep, _user: CurrentUserDep) -> Response:
    for n in session.scalars(select(Notification).where(Notification.read_at.is_(None))):
        n.read_at = _now()
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
