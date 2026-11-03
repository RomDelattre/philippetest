"""Modèle de données (section 6 du cahier des spécifications v0.2).

Règles transverses :
- toutes les tables ont id (UUID), created_at, updated_at et version (verrouillage optimiste, R-12),
  sauf audit_log et holidays (id et created_at seulement) ;
- une période est toujours start_date + end_date incluses (P4, R-03) : aucun nombre de jours stocké ;
- les étapes sont horodatées (demande, attribution, réponse) pour les statistiques V2.
"""

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    func,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.db import Base


def _enum(e: type[enum.Enum]) -> Enum:
    # Stockage en VARCHAR (portable SQLite / PostgreSQL), valeurs = .value
    return Enum(e, native_enum=False, length=32, values_callable=lambda cls: [m.value for m in cls])


# --------------------------------------------------------------------------- énumérations


class UserRole(enum.StrEnum):
    ADMIN = "admin"  # Philippe : tout
    PLANNER = "planner"  # Olivier : planning, tampon, vignettes, absences (F-80)


class TechnicianRole(enum.StrEnum):
    MECHANIC = "mechanic"
    ELECTRONICIAN = "electronician"


class RequestStatus(enum.StrEnum):
    TO_ASSIGN = "to_assign"
    PARTIALLY_ASSIGNED = "partially_assigned"
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class RequestOrigin(enum.StrEnum):
    MAIL = "mail"
    TEAMS = "teams"
    SHAREPOINT = "sharepoint"
    MANUAL = "manual"


class AssignmentStatus(enum.StrEnum):
    DRAFT = "draft"
    PENDING_RESPONSE = "pending_response"
    ACCEPTED = "accepted"
    REFUSED = "refused"
    CANCELLED = "cancelled"


ACTIVE_ASSIGNMENT_STATUSES = frozenset(
    {AssignmentStatus.DRAFT, AssignmentStatus.PENDING_RESPONSE, AssignmentStatus.ACCEPTED}
)


class AbsenceCategory(enum.StrEnum):
    LEAVE = "leave"
    SICK = "sick"
    RECOVERY = "recovery"
    OTHER = "other"


class SourceKind(enum.StrEnum):
    MAIL = "mail"
    TEAMS = "teams"
    SHAREPOINT = "sharepoint"


class ChangeKind(enum.StrEnum):
    MODIFICATION = "modification"
    CANCELLATION = "cancellation"


class ProposalStatus(enum.StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    IGNORED = "ignored"


class OutboundKind(enum.StrEnum):
    TECH_PROPOSAL = "tech_proposal"
    REQUESTER_CONFIRMATION = "requester_confirmation"
    GENERIC = "generic"


class OutboundStatus(enum.StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    SENT = "sent"
    FAILED = "failed"
    DISCARDED = "discarded"


# --------------------------------------------------------------------------- mixins


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EntityMixin(IdMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:
        # Verrouillage optimiste (R-12) : UPDATE ... WHERE version = :ancienne_version
        return {"version_id_col": cls.__table__.c.version}  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- tables


class User(EntityMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[UserRole] = mapped_column(_enum(UserRole), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Technician(EntityMixin, Base):
    __tablename__ = "technicians"

    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    role: Mapped[TechnicianRole] = mapped_column(_enum(TechnicianRole), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class MissionType(EntityMixin, Base):
    __tablename__ = "mission_types"

    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str] = mapped_column(String(16), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Request(EntityMixin, Base):
    """La vignette. Période = start_date..end_date incluses ; nombre de jours calculé, jamais stocké."""

    __tablename__ = "requests"
    __table_args__ = (
        CheckConstraint(
            "start_date IS NULL OR end_date IS NULL OR end_date >= start_date", name="period_order"
        ),
        CheckConstraint("technicians_needed >= 1", name="technicians_needed_positive"),
    )

    ref: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    type_code: Mapped[str | None] = mapped_column(ForeignKey("mission_types.code"))
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    requester_name: Mapped[str | None] = mapped_column(String(200))
    requester_email: Mapped[str | None] = mapped_column(String(255))
    cf: Mapped[str | None] = mapped_column(String(50), index=True)
    client: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    objective: Mapped[str | None] = mapped_column(Text)
    technicians_needed: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    start_date: Mapped[date | None] = mapped_column(Date, index=True)
    end_date: Mapped[date | None] = mapped_column(Date)
    date_flexible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    flex_justification: Mapped[str | None] = mapped_column(Text)
    comments: Mapped[str | None] = mapped_column(Text)
    products: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[RequestStatus] = mapped_column(
        _enum(RequestStatus), nullable=False, default=RequestStatus.TO_ASSIGN, index=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    missing_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    badges: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    origin: Mapped[RequestOrigin] = mapped_column(_enum(RequestOrigin), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    needed_by: Mapped[date | None] = mapped_column(Date)


class Assignment(EntityMixin, Base):
    __tablename__ = "assignments"
    __table_args__ = (CheckConstraint("end_date >= start_date", name="period_order"),)

    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requests.id"), nullable=False, index=True)
    technician_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("technicians.id"), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[AssignmentStatus] = mapped_column(
        _enum(AssignmentStatus), nullable=False, default=AssignmentStatus.DRAFT
    )
    response_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    proposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    partner_electronician_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("technicians.id"))


class SourceMessage(EntityMixin, Base):
    __tablename__ = "source_messages"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_source_messages_source_external"),)

    source: Mapped[SourceKind] = mapped_column(_enum(SourceKind), nullable=False)
    external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("requests.id"), index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(512), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sender: Mapped[str | None] = mapped_column(String(320))
    subject: Mapped[str | None] = mapped_column(String(998))
    body_excerpt: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)
    body_purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    web_link: Mapped[str | None] = mapped_column(Text)
    classification: Mapped[str | None] = mapped_column(String(32))
    confidence: Mapped[float | None] = mapped_column(Float)
    extraction: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False, default="new")
    error: Mapped[str | None] = mapped_column(Text)


class Absence(EntityMixin, Base):
    """Aucun motif médical stocké : seule la catégorie (NF-04)."""

    __tablename__ = "absences"
    __table_args__ = (CheckConstraint("end_date >= start_date", name="period_order"),)

    technician_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("technicians.id"), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[AbsenceCategory] = mapped_column(_enum(AbsenceCategory), nullable=False)
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("source_messages.id"))


class Holiday(IdMixin, Base):
    __tablename__ = "holidays"

    date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)


class ChangeRequest(EntityMixin, Base):
    __tablename__ = "change_requests"

    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("requests.id"), index=True)
    kind: Mapped[ChangeKind] = mapped_column(_enum(ChangeKind), nullable=False)
    proposed_changes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("source_messages.id"))
    status: Mapped[ProposalStatus] = mapped_column(
        _enum(ProposalStatus), nullable=False, default=ProposalStatus.PENDING
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AbsenceProposal(EntityMixin, Base):
    __tablename__ = "absence_proposals"

    source_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("source_messages.id"))
    person_name: Mapped[str] = mapped_column(String(200), nullable=False)
    candidate_technician_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[AbsenceCategory] = mapped_column(_enum(AbsenceCategory), nullable=False)
    status: Mapped[ProposalStatus] = mapped_column(
        _enum(ProposalStatus), nullable=False, default=ProposalStatus.PENDING
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OutboundMessage(EntityMixin, Base):
    __tablename__ = "outbound_messages"

    kind: Mapped[OutboundKind] = mapped_column(_enum(OutboundKind), nullable=False)
    to_email: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(998), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[OutboundStatus] = mapped_column(
        _enum(OutboundStatus), nullable=False, default=OutboundStatus.DRAFT
    )
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("requests.id"))
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assignments.id"))
    validated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class Notification(EntityMixin, Base):
    __tablename__ = "notifications"

    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("requests.id"))
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assignments.id"))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(IdMixin, Base):
    """Journal append-only (NF-05) : toute mise à jour ou suppression via l'ORM est refusée."""

    __tablename__ = "audit_log"

    actor: Mapped[str] = mapped_column(String(320), nullable=False)  # "user:<email>", "agent", "system"
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class Setting(EntityMixin, Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)


class AuditLogImmutableError(RuntimeError):
    pass


@event.listens_for(AuditLog, "before_update")
def _audit_no_update(*_args: Any) -> None:
    raise AuditLogImmutableError("audit_log est en ajout seul (NF-05)")


@event.listens_for(AuditLog, "before_delete")
def _audit_no_delete(*_args: Any) -> None:
    raise AuditLogImmutableError("audit_log est en ajout seul (NF-05)")
