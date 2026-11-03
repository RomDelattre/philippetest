"""Seed des données (section 14).

Usage :
    python -m app.seed                      # référentiels + données de démonstration (si base vide)
    python -m app.seed --no-demo            # référentiels seulement (production)
    python -m app.seed --technicians f.csv  # remplace les noms anonymisés par les vrais (F-70)

Le CSV attendu : last_name;first_name;email;role(mechanic|electronician);sort_order
Le seed est idempotent : relancé, il ne crée pas de doublons.
"""

import argparse
import csv
import random
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from string import ascii_uppercase

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.holidays import belgian_holidays
from app.models import (
    Absence,
    AbsenceCategory,
    Assignment,
    AssignmentStatus,
    Holiday,
    MissionType,
    Request,
    RequestOrigin,
    Setting,
    Technician,
    TechnicianRole,
    User,
    UserRole,
)
from app.rules.status import compute_request_status

HOLIDAY_YEARS = range(2026, 2031)

# Libellés et couleurs provisoires, à confirmer par Philippe [Q-08] [Q-13]
MISSION_TYPES = [
    ("MI", "Mission", "#2563eb"),
    ("SD", "Salon / démo", "#9333ea"),
    ("AT", "Atelier", "#059669"),
    ("FI_FE", "Formation", "#d97706"),
    ("TI_TE", "Tir", "#dc2626"),
    ("AB", "Absence", "#6b7280"),
    ("?", "Activité incertaine", "#a3a3a3"),
]

DEFAULT_SETTINGS: dict[str, object] = {
    "alert_orange_days": 10,  # R-06 [Q-03]
    "alert_red_days": 5,
    "pending_response_alert_days": 3,  # R-05
    "token_validity_days": 14,  # F-21 [Q-07]
    "body_retention_days": 30,  # NF-04 [Q-05]
    "agent_poll_minutes": 5,  # 9.2
    "irh_senders": [],  # F-65
}


def seed_reference(session: Session) -> None:
    s = get_settings()
    for email, name, role in (
        (s.seed_admin_email, s.seed_admin_name, UserRole.ADMIN),
        (s.seed_planner_email, s.seed_planner_name, UserRole.PLANNER),
    ):
        if not session.scalar(select(User).where(func.lower(User.email) == email.lower())):
            session.add(User(email=email.lower(), display_name=name, role=role))

    existing_codes = set(session.scalars(select(MissionType.code)))
    for order, (code, label, color) in enumerate(MISSION_TYPES):
        if code not in existing_codes:
            session.add(MissionType(code=code, label=label, color=color, sort_order=order))

    existing_days = set(session.scalars(select(Holiday.date)))
    for year in HOLIDAY_YEARS:
        for d, label in belgian_holidays(year):
            if d not in existing_days:
                session.add(Holiday(date=d, label=label))

    existing_keys = set(session.scalars(select(Setting.key)))
    for key, value in DEFAULT_SETTINGS.items():
        if key not in existing_keys:
            session.add(Setting(key=key, value=value))
    session.flush()


def seed_anonymous_technicians(session: Session) -> None:
    if session.scalar(select(func.count()).select_from(Technician)):
        return
    for i, letter in enumerate(ascii_uppercase[:20]):
        session.add(
            Technician(
                last_name=f"Technicien {letter}",
                email=f"technicien.{letter.lower()}@example.local",
                role=TechnicianRole.MECHANIC,
                sort_order=i,
            )
        )
    for i, letter in enumerate(ascii_uppercase[:5]):
        session.add(
            Technician(
                last_name=f"Électronicien {letter}",
                email=f"electronicien.{letter.lower()}@example.local",
                role=TechnicianRole.ELECTRONICIAN,
                sort_order=i,
            )
        )
    session.flush()


def import_technicians(session: Session, path: Path) -> int:
    """Crée ou met à jour les techniciens à partir d'un CSV (clé : e-mail, sinon nom + prénom)."""
    count = 0
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh, delimiter=";"):
            email = (row.get("email") or "").strip().lower() or None
            last, first = row["last_name"].strip(), (row.get("first_name") or "").strip()
            tech = None
            if email:
                tech = session.scalar(select(Technician).where(Technician.email == email))
            if tech is None:
                tech = session.scalar(
                    select(Technician).where(Technician.last_name == last, Technician.first_name == first)
                )
            if tech is None:
                tech = Technician(last_name=last, first_name=first, role=TechnicianRole(row["role"]))
                session.add(tech)
            tech.last_name, tech.first_name, tech.email = last, first, email
            tech.role = TechnicianRole(row["role"])
            tech.sort_order = int(row.get("sort_order") or 0)
            tech.active = True
            count += 1
    session.flush()
    return count


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _overlaps(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    return a_start <= b_end and b_start <= a_end


def seed_demo(session: Session, today: date | None = None) -> None:
    """30 demandes variées, quelques absences et attributions, sans chevauchement (R-02)."""
    if session.scalar(select(func.count()).select_from(Request)):
        return
    today = today or date.today()
    rng = random.Random(42)
    base = _monday(today) - timedelta(weeks=2)
    mechanics = list(
        session.scalars(
            select(Technician)
            .where(Technician.role == TechnicianRole.MECHANIC, Technician.active.is_(True))
            .order_by(Technician.sort_order)
        )
    )
    electronicians = list(
        session.scalars(select(Technician).where(Technician.role == TechnicianRole.ELECTRONICIAN))
    )
    busy: dict = {t.id: [] for t in mechanics}

    for _ in range(8):  # absences
        tech = rng.choice(mechanics)
        ab_start = base + timedelta(days=rng.randrange(0, 56))
        ab_end = ab_start + timedelta(days=rng.randrange(0, 5))
        if any(_overlaps(ab_start, ab_end, s, e) for s, e in busy[tech.id]):
            continue
        busy[tech.id].append((ab_start, ab_end))
        session.add(
            Absence(
                technician_id=tech.id,
                start_date=ab_start,
                end_date=ab_end,
                category=rng.choice(list(AbsenceCategory)),
            )
        )

    clients = ["Client Alpha", "Client Bravo", "Client Charlie", "Client Delta", "Client Echo", None]
    places = ["Herstal", "Liège", "Paris", "Dubaï", "Bruxelles", "Camp de Lagland", None]
    types = ["MI", "SD", "AT", "FI_FE", "TI_TE", None]
    now = datetime.now(UTC)
    year = today.year

    for n in range(1, 31):
        type_code = rng.choice(types)
        has_dates = n % 7 != 0  # quelques demandes sans dates (informations manquantes)
        start = base + timedelta(days=rng.randrange(0, 80)) if has_dates else None
        end = start + timedelta(days=rng.choice([0, 0, 1, 2, 4, 9])) if start else None
        location, client = rng.choice(places), rng.choice(clients)
        needed = rng.choice([1, 1, 1, 2, 2, 3])
        chef = rng.choice("ABCDEFG")
        missing = [
            name
            for name, value in (
                ("type_code", type_code),
                ("start_date", start),
                ("end_date", end),
                ("location", location),
            )
            if value is None
        ]
        req = Request(
            ref=f"D-{year}-{n:04d}",
            type_code=type_code,
            title=f"Demande de démonstration {n}",
            requester_name=f"Chef de projet {chef}",
            requester_email=f"chef.{chef.lower()}@example.local",
            cf=f"CF{rng.randrange(10000, 99999)}" if rng.random() > 0.2 else None,
            client=client,
            location=location,
            technicians_needed=needed,
            start_date=start,
            end_date=end,
            date_flexible=rng.random() < 0.3,
            missing_fields=missing,
            needs_review=n % 5 == 0,
            origin=rng.choice(list(RequestOrigin)),
            requested_at=now - timedelta(days=rng.randrange(1, 30)),
        )
        session.add(req)
        session.flush()

        statuses: list[AssignmentStatus] = []
        if start and end and rng.random() < 0.6:
            target = rng.randrange(1, needed + 1)
            for tech in rng.sample(mechanics, len(mechanics)):
                if len(statuses) >= target:
                    break
                if any(_overlaps(start, end, s, e) for s, e in busy[tech.id]):
                    continue
                busy[tech.id].append((start, end))
                status = rng.choice([AssignmentStatus.ACCEPTED, AssignmentStatus.PENDING_RESPONSE])
                statuses.append(status)
                session.add(
                    Assignment(
                        request_id=req.id,
                        technician_id=tech.id,
                        start_date=start,
                        end_date=end,
                        status=status,
                        proposed_at=now - timedelta(days=rng.randrange(0, 5)),
                        responded_at=now if status == AssignmentStatus.ACCEPTED else None,
                        partner_electronician_id=(
                            rng.choice(electronicians).id if electronicians and rng.random() < 0.2 else None
                        ),
                    )
                )
        req.status = compute_request_status(needed, statuses, req.cancelled_at)
    session.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed du planning ATS")
    parser.add_argument("--no-demo", action="store_true", help="référentiels seulement")
    parser.add_argument("--technicians", type=Path, help="CSV des vrais techniciens")
    args = parser.parse_args()
    with SessionLocal() as session:
        seed_reference(session)
        if args.technicians:
            print(f"{import_technicians(session, args.technicians)} techniciens importés")
        else:
            seed_anonymous_technicians(session)
        if not args.no_demo:
            seed_demo(session)
        session.commit()
    print("Seed terminé")


if __name__ == "__main__":
    main()
