from datetime import date

import pytest

from app.holidays import belgian_holidays, easter_sunday, is_working_day


@pytest.mark.parametrize(
    ("year", "expected"),
    [
        (2026, date(2026, 4, 5)),
        (2027, date(2027, 3, 28)),
        (2028, date(2028, 4, 16)),
        (2029, date(2029, 4, 1)),
        (2030, date(2030, 4, 21)),
    ],
)
def test_easter(year: int, expected: date) -> None:
    assert easter_sunday(year) == expected


def test_belgian_holidays_2026() -> None:
    days = dict(belgian_holidays(2026))
    assert len(days) == 10
    assert days[date(2026, 4, 6)] == "Lundi de Pâques"
    assert days[date(2026, 5, 14)] == "Ascension"
    assert days[date(2026, 5, 25)] == "Lundi de Pentecôte"
    assert days[date(2026, 7, 21)] == "Fête nationale"
    assert days[date(2026, 11, 11)] == "Armistice"


def test_working_day() -> None:
    hol = {d for d, _ in belgian_holidays(2026)}
    assert not is_working_day(date(2026, 11, 1), hol)  # dimanche + Toussaint
    assert not is_working_day(date(2026, 11, 11), hol)  # mercredi férié
    assert not is_working_day(date(2026, 11, 7), hol)  # samedi
    assert is_working_day(date(2026, 11, 3), hol)
