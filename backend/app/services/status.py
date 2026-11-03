from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Assignment, Request
from app.rules.status import compute_request_status


def refresh_request_status(session: Session, request: Request) -> None:
    """R-01 : seul point d'écriture de requests.status."""
    session.flush()
    statuses = session.scalars(select(Assignment.status).where(Assignment.request_id == request.id))
    new = compute_request_status(request.technicians_needed, statuses, request.cancelled_at)
    if new != request.status:
        request.status = new
