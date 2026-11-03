"""R-01 : statut calculé d'une demande."""

from datetime import UTC, datetime

from app.models import AssignmentStatus as A
from app.models import RequestStatus as R
from app.rules.status import compute_request_status


def test_no_assignment_is_to_assign() -> None:
    assert compute_request_status(2, [], None) == R.TO_ASSIGN


def test_inactive_assignments_are_ignored() -> None:
    assert compute_request_status(1, [A.REFUSED, A.CANCELLED], None) == R.TO_ASSIGN


def test_partially_assigned() -> None:
    assert compute_request_status(3, [A.ACCEPTED, A.REFUSED], None) == R.PARTIALLY_ASSIGNED


def test_draft_counts_as_active_and_pending() -> None:
    assert compute_request_status(1, [A.DRAFT], None) == R.PENDING


def test_pending_when_one_response_awaited() -> None:
    assert compute_request_status(2, [A.ACCEPTED, A.PENDING_RESPONSE], None) == R.PENDING


def test_confirmed_when_all_accepted() -> None:
    assert compute_request_status(2, [A.ACCEPTED, A.ACCEPTED, A.REFUSED], None) == R.CONFIRMED


def test_cancelled_wins() -> None:
    assert compute_request_status(1, [A.ACCEPTED], datetime.now(UTC)) == R.CANCELLED
