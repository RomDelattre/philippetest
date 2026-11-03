"""Jours fériés légaux belges (R-04). Fixes + mobiles dérivés de Pâques."""

from datetime import date, timedelta


def easter_sunday(year: int) -> date:
    """Dimanche de Pâques (calendrier grégorien, algorithme de Meeus/Jones/Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month, day = divmod(h + l_ - 7 * m + 114, 31)
    return date(year, month, day + 1)


def belgian_holidays(year: int) -> list[tuple[date, str]]:
    easter = easter_sunday(year)
    days = [
        (date(year, 1, 1), "Jour de l'an"),
        (easter + timedelta(days=1), "Lundi de Pâques"),
        (date(year, 5, 1), "Fête du travail"),
        (easter + timedelta(days=39), "Ascension"),
        (easter + timedelta(days=50), "Lundi de Pentecôte"),
        (date(year, 7, 21), "Fête nationale"),
        (date(year, 8, 15), "Assomption"),
        (date(year, 11, 1), "Toussaint"),
        (date(year, 11, 11), "Armistice"),
        (date(year, 12, 25), "Noël"),
    ]
    return sorted(days)


def is_working_day(d: date, holidays: set[date]) -> bool:
    return d.weekday() < 5 and d not in holidays
