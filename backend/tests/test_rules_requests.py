from datetime import date

import pytest

from app.rules.requests import compute_missing_fields, placement_for_drop, split_period

D = date


def test_complete_request_has_no_missing_fields() -> None:
    assert (
        compute_missing_fields(
            type_code="MI", start_date=D(2026, 11, 9), end_date=D(2026, 11, 9), location="Herstal"
        )
        == []
    )


def test_missing_fields_listed_in_order() -> None:
    assert compute_missing_fields(
        type_code=None, start_date=None, end_date=None, location="  ", technicians_known=False
    ) == ["type_code", "technicians_needed", "start_date", "end_date", "location"]


def test_drop_inside_period_snaps_to_request_dates() -> None:
    p = placement_for_drop(D(2026, 11, 9), D(2026, 11, 13), D(2026, 11, 11))
    assert (p.start, p.end, p.differs_from_request) == (D(2026, 11, 9), D(2026, 11, 13), False)


def test_drop_outside_period_shifts_and_keeps_length() -> None:
    p = placement_for_drop(D(2026, 11, 9), D(2026, 11, 13), D(2026, 11, 23))
    assert (p.start, p.end, p.differs_from_request) == (D(2026, 11, 23), D(2026, 11, 27), True)


def test_drop_without_dates_is_one_day() -> None:
    p = placement_for_drop(D(2026, 11, 9), None, D(2026, 11, 23))
    assert (p.start, p.end, p.request_dates_incomplete) == (D(2026, 11, 23), D(2026, 11, 23), True)


def test_split_period() -> None:
    assert split_period(D(2026, 11, 9), D(2026, 11, 13), D(2026, 11, 11)) == (
        (D(2026, 11, 9), D(2026, 11, 10)),
        (D(2026, 11, 11), D(2026, 11, 13)),
    )
    with pytest.raises(ValueError):
        split_period(D(2026, 11, 9), D(2026, 11, 13), D(2026, 11, 9))
    with pytest.raises(ValueError):
        split_period(D(2026, 11, 9), D(2026, 11, 13), D(2026, 11, 14))
