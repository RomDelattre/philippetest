"""R-01 : calcul du statut d'une demande. Seule fonction autorisée à écrire requests.status."""

from collections.abc import Iterable
from datetime import datetime

from app.models import ACTIVE_ASSIGNMENT_STATUSES, AssignmentStatus, RequestStatus


def compute_request_status(
    technicians_needed: int,
    assignment_statuses: Iterable[AssignmentStatus],
    cancelled_at: datetime | None,
) -> RequestStatus:
    if cancelled_at is not None:
        return RequestStatus.CANCELLED
    active = [s for s in assignment_statuses if s in ACTIVE_ASSIGNMENT_STATUSES]
    if not active:
        return RequestStatus.TO_ASSIGN
    if len(active) < technicians_needed:
        return RequestStatus.PARTIALLY_ASSIGNED
    if all(s == AssignmentStatus.ACCEPTED for s in active):
        return RequestStatus.CONFIRMED
    return RequestStatus.PENDING
