"""Préparation des brouillons de mails (F-20, F-23, F-26) et des notifications internes.
Rien n'est envoyé ici : les brouillons attendent la validation de Philippe (P2)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Assignment,
    AssignmentStatus,
    MissionType,
    Notification,
    OutboundKind,
    OutboundMessage,
    OutboundStatus,
    Request,
    Setting,
    Technician,
)
from app.rules.templates import DEFAULT_TEMPLATES, TEMPLATE_KEYS, format_dates, render

UNSENT = (OutboundStatus.DRAFT, OutboundStatus.VALIDATED, OutboundStatus.FAILED)


def tech_name(t: Technician) -> str:
    return " ".join(filter(None, [t.first_name, t.last_name]))


def load_template(session: Session, name: str) -> dict[str, str]:
    row = session.scalar(select(Setting).where(Setting.key == TEMPLATE_KEYS[name]))
    value = row.value if row is not None and isinstance(row.value, dict) else {}
    default = DEFAULT_TEMPLATES[name]
    return {
        "subject": value.get("subject") or default["subject"],
        "body": value.get("body") or default["body"],
    }


def template_values(session: Session, req: Request, technician: Technician | None = None) -> dict[str, str]:
    type_label = req.type_code or "Activité"
    if req.type_code:
        mt = session.scalar(select(MissionType).where(MissionType.code == req.type_code))
        if mt is not None:
            type_label = f"{mt.code} ({mt.label})"
    accepted = session.scalars(
        select(Technician)
        .join(Assignment, Assignment.technician_id == Technician.id)
        .where(Assignment.request_id == req.id, Assignment.status == AssignmentStatus.ACCEPTED)
        .order_by(Technician.last_name)
    )
    return {
        "demandeur": req.requester_name or "",
        "type": type_label,
        "dates": format_dates(req.start_date, req.end_date),
        "lieu": req.location or "à préciser",
        "technicien": tech_name(technician) if technician else "",
        "techniciens": ", ".join(tech_name(t) for t in accepted) or "à confirmer",
        "ref": req.ref,
        "titre": req.title or "",
        "client": req.client or "—",
        "cf": req.cf or "",
    }


def _assignment_values(session: Session, a: Assignment) -> tuple[Request, Technician, dict[str, str]]:
    req = session.get(Request, a.request_id)
    tech = session.get(Technician, a.technician_id)
    assert req is not None and tech is not None
    values = template_values(session, req, tech)
    # les dates du mail au technicien sont celles de son affectation
    values["dates"] = format_dates(a.start_date, a.end_date)
    return req, tech, values


def discard_unsent(
    session: Session, assignment_id: object, kind: OutboundKind = OutboundKind.TECH_PROPOSAL
) -> None:
    for msg in session.scalars(
        select(OutboundMessage).where(
            OutboundMessage.assignment_id == assignment_id,
            OutboundMessage.kind == kind,
            OutboundMessage.status.in_(UNSENT),
        )
    ):
        msg.status = OutboundStatus.DISCARDED


def draft_tech_proposal(session: Session, a: Assignment) -> OutboundMessage:
    """F-20 : brouillon de proposition. Les liens restent sous forme de variables jusqu'à l'envoi."""
    discard_unsent(session, a.id)
    req, tech, values = _assignment_values(session, a)
    tpl = load_template(session, "tech_proposal")
    msg = OutboundMessage(
        kind=OutboundKind.TECH_PROPOSAL,
        to_email=tech.email or "",
        subject=render(tpl["subject"], values),
        body=render(tpl["body"], values),  # {lien_accepter} et {lien_refuser} sont conservés
        request_id=req.id,
        assignment_id=a.id,
    )
    session.add(msg)
    return msg


def draft_tech_cancellation(
    session: Session, a: Assignment, technician_id: object | None = None
) -> OutboundMessage:
    """F-26 : information au technicien qu'une proposition déjà envoyée ne le concerne plus."""
    req, tech, values = _assignment_values(session, a)
    if technician_id is not None and technician_id != tech.id:
        other = session.get(Technician, technician_id)
        if other is not None:
            tech, values["technicien"] = other, tech_name(other)
    tpl = load_template(session, "tech_cancellation")
    msg = OutboundMessage(
        kind=OutboundKind.GENERIC,
        to_email=tech.email or "",
        subject=render(tpl["subject"], values),
        body=render(tpl["body"], values),
        request_id=req.id,
        assignment_id=a.id,
    )
    session.add(msg)
    return msg


def upsert_requester_confirmation(session: Session, req: Request) -> OutboundMessage:
    """F-23 : brouillon de confirmation au demandeur.
    Mis à jour à chaque acceptation tant qu'il n'est pas parti."""
    values = template_values(session, req)
    tpl = load_template(session, "requester_confirmation")
    msg = session.scalar(
        select(OutboundMessage).where(
            OutboundMessage.request_id == req.id,
            OutboundMessage.kind == OutboundKind.REQUESTER_CONFIRMATION,
            OutboundMessage.status.in_(UNSENT),
        )
    )
    if msg is None:
        msg = OutboundMessage(
            kind=OutboundKind.REQUESTER_CONFIRMATION, request_id=req.id, to_email="", subject="", body=""
        )
        session.add(msg)
    msg.to_email = req.requester_email or ""
    msg.subject = render(tpl["subject"], values)
    msg.body = render(tpl["body"], values)
    msg.status = OutboundStatus.DRAFT
    return msg


def notify(
    session: Session, kind: str, message: str, req: Request | None = None, a: Assignment | None = None
) -> None:
    session.add(
        Notification(
            kind=kind,
            message=message,
            request_id=req.id if req else None,
            assignment_id=a.id if a else None,
        )
    )
