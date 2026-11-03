"""R-05 : conflits, R-06 : alerte d'attribution. Calcul pur, recalculé à chaque lecture et jamais
corrigé automatiquement. Les conflits rouges bloquent l'œil, pas l'action (P1)."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal
from uuid import UUID

Level = Literal["red", "orange"]


@dataclass(frozen=True)
class AssignmentFacts:
    id: UUID
    technician_id: UUID
    request_id: UUID
    request_ref: str
    start: date
    end: date
    status: str  # draft | pending_response | accepted (actifs uniquement)
    proposed_at: datetime | None = None
    token_expires_at: datetime | None = None


@dataclass(frozen=True)
class AbsenceFacts:
    technician_id: UUID
    start: date
    end: date


@dataclass(frozen=True)
class Conflict:
    level: Level
    code: str
    message: str


@dataclass
class ConflictSettings:
    pending_response_alert_days: int = 3


@dataclass
class ConflictInput:
    assignments: list[AssignmentFacts]
    absences: list[AbsenceFacts] = field(default_factory=list)
    holidays: set[date] = field(default_factory=set)
    # demandes avec une modification de dates en attente (R-05, orange)
    pending_date_change: set[UUID] = field(default_factory=set)


def _fmt(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _overlap(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    return a_start <= b_end and b_start <= a_end


def _aware(dt: datetime) -> datetime:
    from datetime import UTC

    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def assignment_conflicts(
    data: ConflictInput, now: datetime, settings: ConflictSettings | None = None
) -> dict[UUID, list[Conflict]]:
    """Conflits par assignment. Complexité : tri par technicien, O(n log n) + chevauchements réels."""
    settings = settings or ConflictSettings()
    out: dict[UUID, list[Conflict]] = defaultdict(list)

    by_tech: dict[UUID, list[AssignmentFacts]] = defaultdict(list)
    for a in data.assignments:
        by_tech[a.technician_id].append(a)
    absences: dict[UUID, list[AbsenceFacts]] = defaultdict(list)
    for ab in data.absences:
        absences[ab.technician_id].append(ab)

    for items in by_tech.values():
        items.sort(key=lambda x: (x.start, x.end))
        # rouge : chevauchement de deux activités d'un même technicien (R-02)
        for i, a in enumerate(items):
            for b in items[i + 1 :]:
                if b.start > a.end:
                    break
                out[a.id].append(Conflict("red", "overlap", f"Chevauchement avec {b.request_ref}"))
                out[b.id].append(Conflict("red", "overlap", f"Chevauchement avec {a.request_ref}"))

    for a in data.assignments:
        # rouge : activité sur une absence
        for ab in absences.get(a.technician_id, []):
            if _overlap(a.start, a.end, ab.start, ab.end):
                out[a.id].append(
                    Conflict("red", "absence", f"Technicien absent du {_fmt(ab.start)} au {_fmt(ab.end)}")
                )
        # orange : week-end ou jour férié couvert (R-04 : autorisé, mais signalé)
        days = [a.start + timedelta(days=i) for i in range((a.end - a.start).days + 1)]
        weekend = [d for d in days if d.weekday() >= 5]
        holidays = [d for d in days if d in data.holidays]
        if weekend:
            out[a.id].append(Conflict("orange", "weekend", f"Couvre un week-end ({_fmt(weekend[0])})"))
        if holidays:
            out[a.id].append(Conflict("orange", "holiday", f"Couvre un jour férié ({_fmt(holidays[0])})"))
        # orange : modification de dates proposée sur une demande attribuée
        if a.request_id in data.pending_date_change:
            out[a.id].append(
                Conflict("orange", "date_change", "Modification de dates proposée par le demandeur")
            )
        if a.status == "pending_response":
            if a.token_expires_at is not None and _aware(a.token_expires_at) < now:
                out[a.id].append(Conflict("orange", "link_expired", "Lien de réponse expiré"))
            elif a.proposed_at is not None:
                waited = (now - _aware(a.proposed_at)).days
                if waited > settings.pending_response_alert_days:
                    out[a.id].append(
                        Conflict("orange", "pending_too_long", f"En attente de réponse depuis {waited} jours")
                    )
    # les conflits rouges d'abord, sans doublon
    return {
        k: sorted(dict.fromkeys(v), key=lambda c: (c.level != "red", c.code)) for k, v in out.items() if v
    }


def level_of(conflicts: Iterable[Conflict]) -> Level | None:
    levels = {c.level for c in conflicts}
    return "red" if "red" in levels else "orange" if "orange" in levels else None


# --------------------------------------------------------------------------- R-06


def working_days_until(today: date, target: date, holidays: set[date]) -> int:
    """Jours ouvrés de demain jusqu'à target inclus (0 si target ≤ aujourd'hui)."""
    n, d = 0, today
    while d < target:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in holidays:
            n += 1
    return n


def date_alert(
    reference: date | None, today: date, holidays: set[date], orange_days: int = 10, red_days: int = 5
) -> tuple[Level, int] | None:
    """R-06 : rouge sous red_days jours ouvrés, orange sous orange_days. None sans date de référence."""
    if reference is None:
        return None
    n = working_days_until(today, reference, holidays)
    if n < red_days:
        return "red", n
    if n < orange_days:
        return "orange", n
    return None
