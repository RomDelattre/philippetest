"""Règles pures sur les demandes (vignettes) : complétude (F-13), placement (R-03), division (F-15)."""

from dataclasses import dataclass
from datetime import date, timedelta

# F-13 [Q-06] : informations minimales d'une demande complète
REQUIRED_FIELDS = ("type_code", "technicians_needed", "start_date", "end_date", "location")


def compute_missing_fields(
    *,
    type_code: str | None,
    start_date: date | None,
    end_date: date | None,
    location: str | None,
    technicians_known: bool = True,
) -> list[str]:
    """Liste des champs minimaux absents. Leur absence n'empêche jamais l'attribution (F-13)."""
    values = {
        "type_code": type_code,
        "technicians_needed": True if technicians_known else None,
        "start_date": start_date,
        "end_date": end_date,
        "location": (location or "").strip() or None,
    }
    return [f for f in REQUIRED_FIELDS if values[f] is None]


@dataclass(frozen=True)
class Placement:
    start: date
    end: date
    differs_from_request: bool  # confirmation « dates différentes de la demande » (R-03)
    request_dates_incomplete: bool  # proposer d'écrire les dates dans la demande (R-03)


def placement_for_drop(req_start: date | None, req_end: date | None, drop_day: date) -> Placement:
    """R-03 : une vignette déposée sur le jour J.
    - demande datée, J dans sa période : l'affectation couvre exactement les dates de la demande ;
    - demande datée, J hors période : décalage à J en gardant le même nombre de jours ;
    - demande sans dates complètes : affectation de J à J.
    """
    if req_start is None or req_end is None:
        return Placement(drop_day, drop_day, differs_from_request=False, request_dates_incomplete=True)
    if req_start <= drop_day <= req_end:
        return Placement(req_start, req_end, differs_from_request=False, request_dates_incomplete=False)
    return Placement(
        drop_day,
        drop_day + (req_end - req_start),
        differs_from_request=True,
        request_dates_incomplete=False,
    )


def split_period(start: date, end: date, split_date: date) -> tuple[tuple[date, date], tuple[date, date]]:
    """F-15 : coupe [start, end] avant split_date (premier jour de la seconde partie)."""
    if not start < split_date <= end:
        raise ValueError(
            "La date de coupure doit être comprise entre le 2e et le dernier jour de la demande."
        )
    return (start, split_date - timedelta(days=1)), (split_date, end)
