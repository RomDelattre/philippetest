"""F-40 à F-43 : centre d'alertes et paramètres d'alerte."""

import datetime as _dt
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from app import audit
from app.auth import AdminDep, CurrentUserDep, SessionDep
from app.models import Setting
from app.services.alerts import alert_settings, compute_alerts
from app.services.dates import today_brussels

router = APIRouter(prefix="/api")


class AlertOut(BaseModel):
    key: str
    level: str
    kind: str
    message: str
    request_id: UUID | None
    request_ref: str | None
    assignment_id: UUID | None
    date: _dt.date | None


class AlertSettings(BaseModel):
    alert_orange_days: int = Field(ge=1, le=60)
    alert_red_days: int = Field(ge=0, le=60)
    pending_response_alert_days: int = Field(ge=1, le=60)
    token_validity_days: int = Field(ge=1, le=90)

    @model_validator(mode="after")
    def _order(self) -> "AlertSettings":
        if self.alert_red_days >= self.alert_orange_days:
            raise ValueError("Le seuil rouge doit être inférieur au seuil orange.")
        return self


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(session: SessionDep, _user: CurrentUserDep) -> list[AlertOut]:
    return [AlertOut(**a.__dict__) for a in compute_alerts(session, today_brussels())]


@router.get("/settings/alerts", response_model=AlertSettings)
def get_alert_settings(session: SessionDep, _user: CurrentUserDep) -> AlertSettings:
    return AlertSettings(**alert_settings(session))


@router.put("/settings/alerts", response_model=AlertSettings)
def put_alert_settings(body: AlertSettings, session: SessionDep, admin: AdminDep) -> AlertSettings:
    """F-43 : modifiables par Philippe seulement."""
    for key, value in body.model_dump().items():
        row = session.scalar(select(Setting).where(Setting.key == key))
        if row is None:
            row = Setting(key=key, value=value)
            session.add(row)
            session.flush()
            audit.record(session, admin.audit_actor, "settings.update", row, None, audit.snapshot(row))
        elif row.value != value:
            before = audit.snapshot(row)
            row.value = value
            session.flush()
            audit.record(session, admin.audit_actor, "settings.update", row, before, audit.snapshot(row))
    session.commit()
    return AlertSettings(**alert_settings(session))
