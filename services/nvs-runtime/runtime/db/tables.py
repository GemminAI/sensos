import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Agent(Base):
    __tablename__ = "agents"

    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    display_name: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    transport: Mapped[str] = mapped_column(String(32), nullable=False, default="mcp")
    capabilities: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    auth_principal: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    participants: Mapped[list["SessionParticipant"]] = relationship(back_populates="agent")


class Session(Base):
    __tablename__ = "sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    kernel_run_ids: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    options: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    participants: Mapped[list["SessionParticipant"]] = relationship(back_populates="session")
    experiments: Mapped[list["Experiment"]] = relationship(back_populates="session")
    events: Mapped[list["Event"]] = relationship(back_populates="session")


class SessionParticipant(Base):
    __tablename__ = "session_participants"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.session_id"), primary_key=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.agent_id"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="participant")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    session: Mapped["Session"] = relationship(back_populates="participants")
    agent: Mapped["Agent"] = relationship(back_populates="participants")


class Experiment(Base):
    __tablename__ = "experiments"

    experiment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.session_id"), nullable=False)
    experiment_type: Mapped[str] = mapped_column(String(32), nullable=False, default="sep")
    label: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    session: Mapped["Session"] = relationship(back_populates="experiments")
    events: Mapped[list["Event"]] = relationship(back_populates="experiment")


class NarrativeState(Base):
    __tablename__ = "narrative_states"
    __table_args__ = (
        Index("idx_narrative_states_created", "created_at"),
        Index("idx_narrative_states_event", "event_id"),
    )

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    subject_origin: Mapped[str] = mapped_column(String(8), nullable=False, default="us")
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    epistemic_diffusion_state: Mapped[str] = mapped_column(String(32), nullable=False)
    article: Mapped[str] = mapped_column(Text, nullable=False, default="")
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="openai")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "state_hash": self.state_hash,
            "event_id": self.event_id,
            "narrative": self.narrative,
            "tags": self.tags,
            "subject_origin": self.subject_origin,
            "schema_version": self.schema_version,
            "epistemic_diffusion_state": self.epistemic_diffusion_state,
            "article": self.article,
            "provider": self.provider,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("idx_events_session_seq", "session_id", "sequence_id"),
        Index("idx_events_experiment", "experiment_id"),
        Index("idx_events_type", "event_type"),
        Index("idx_events_sep_type", "sep_event_type"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False, default="nvs.runtime.event.v1")
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    experiment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("experiments.experiment_id"))
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.session_id"), nullable=False)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.agent_id"))
    source_provider: Mapped[str | None] = mapped_column(String(64))
    source_model: Mapped[str | None] = mapped_column(Text)
    parent_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("events.event_id"))
    sequence_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(Text)
    sep_event_type: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    forward_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    kernel_run_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["Session"] = relationship(back_populates="events")
    experiment: Mapped["Experiment | None"] = relationship(back_populates="events")
