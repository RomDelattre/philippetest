"""Réponse d'un technicien à une proposition : par lien (F-22) ou saisie par Philippe (F-25)."""

from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.orm import Session

from app import audit
from app.models import Assignment, AssignmentStatus, OutboundKind, Request, Technician
from app.services.outbox import discard_unsent, notify, tech_name, upsert_requester_confirmation
from app.services.status import refresh_request_status

Answer = Literal["accept", "refuse"]
REFUSED_BADGE = "technician_refused"


def apply_response(session: Session, a: Assignment, answer: Answer, actor: str, *, via_link: bool) -> None:
    now = datetime.now(UTC)
    before = audit.snapshot(a)
    req = session.get(Request, a.request_id)
    tech = session.get(Technician, a.technician_id)
    assert req is not None and tech is not None

    a.status = AssignmentStatus.ACCEPTED if answer == "accept" else AssignmentStatus.REFUSED
    a.responded_at = now
    if a.response_token_hash is not None and a.token_used_at is None:
        a.token_used_at = now
    # une réponse saisie avant l'envoi rend la proposition en brouillon inutile
    discard_unsent(session, a.id, OutboundKind.TECH_PROPOSAL)
    refresh_request_status(session, req)

    name = tech_name(tech)
    if answer == "accept":
        upsert_requester_confirmation(session, req)  # F-23
        if via_link:
            notify(session, "accepted", f"{name} a accepté {req.ref}.", req, a)
    else:
        # F-24 : la demande revient dans le tampon avec la trace du refus
        if REFUSED_BADGE not in (req.badges or []):
            req.badges = [*(req.badges or []), REFUSED_BADGE]
        if via_link:
            notify(session, "refused", f"{name} a refusé {req.ref}.", req, a)
    action = f"assignment.{'accept' if answer == 'accept' else 'refuse'}{'' if via_link else '_manual'}"
    audit.record(session, actor, action, a, before, audit.snapshot(a))
