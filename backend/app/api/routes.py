"""Routes de la phase 0 : santé, utilisateur courant, référentiels en lecture.
Les autres routes de la section 10 arrivent avec leurs phases."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text

from app.auth import CurrentUserDep, SessionDep
from app.config import get_settings
from app.models import Holiday, MissionType, Technician, TechnicianRole, UserRole

router = APIRouter(prefix="/api")


class HealthOut(BaseModel):
    status: str
    database: str
    auth_mode: str


class MeOut(BaseModel):
    id: UUID
    email: str
    display_name: str
    role: UserRole


class TechnicianOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    last_name: str
    first_name: str
    email: str | None
    role: TechnicianRole
    active: bool
    sort_order: int
    version: int


class MissionTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    label: str
    color: str
    sort_order: int


class HolidayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    date: date
    label: str


@router.get("/health", response_model=HealthOut)
def health(session: SessionDep) -> HealthOut:
    try:
        session.execute(text("SELECT 1"))
        db = "ok"
    except Exception:  # pragma: no cover - dépend de l'infrastructure
        db = "unavailable"
    return HealthOut(status="ok", database=db, auth_mode=get_settings().auth_mode)


@router.get("/me", response_model=MeOut)
def me(user: CurrentUserDep) -> MeOut:
    return MeOut(id=user.id, email=user.email, display_name=user.display_name, role=user.role)


@router.get("/technicians", response_model=list[TechnicianOut])
def list_technicians(
    session: SessionDep, _user: CurrentUserDep, include_inactive: bool = False
) -> list[Technician]:
    q = select(Technician).order_by(Technician.role, Technician.sort_order, Technician.last_name)
    if not include_inactive:
        q = q.where(Technician.active.is_(True))
    return list(session.scalars(q))


@router.get("/mission-types", response_model=list[MissionTypeOut])
def list_mission_types(session: SessionDep, _user: CurrentUserDep) -> list[MissionType]:
    q = select(MissionType).where(MissionType.active.is_(True)).order_by(MissionType.sort_order)
    return list(session.scalars(q))


@router.get("/holidays", response_model=list[HolidayOut])
def list_holidays(
    session: SessionDep,
    _user: CurrentUserDep,
    from_: Annotated[date, Query(alias="from")],
    to: Annotated[date, Query()],
) -> list[Holiday]:
    if to < from_:
        raise HTTPException(422, "« to » doit être postérieure ou égale à « from »")
    q = select(Holiday).where(Holiday.date >= from_, Holiday.date <= to).order_by(Holiday.date)
    return list(session.scalars(q))
