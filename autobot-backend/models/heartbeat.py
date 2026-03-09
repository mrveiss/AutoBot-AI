# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Heartbeat System Models (#1407)

SQLAlchemy models for scheduled agent wakeups and session persistence.
Tables: heartbeat_runs, heartbeat_run_events, agent_runtime_state,
        agent_wakeup_requests.
"""

import uuid
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from user_management.models.base import Base, TimestampMixin


class HeartbeatRunStatus(str, Enum):
    """Lifecycle states for a single heartbeat run (#1407)."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class WakeupTrigger(str, Enum):
    """What caused this heartbeat run (#1407)."""

    INTERVAL = "interval"
    EVENT = "event"
    MANUAL = "manual"


class AgentRuntimeState(Base, TimestampMixin):
    """Persistent runtime state per agent, survives restarts (#1407)."""

    __tablename__ = "agent_runtime_state"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String(255), nullable=False, unique=True, index=True)
    heartbeat_enabled = Column(Boolean, nullable=False, default=False)
    heartbeat_interval_seconds = Column(Integer, nullable=False, default=300)
    max_run_duration_seconds = Column(Integer, nullable=False, default=600)
    current_task_id = Column(String(255), nullable=True, index=True)
    session_params = Column(JSONB, nullable=True)
    last_heartbeat_at = Column(DateTime, nullable=True)
    extra = Column(JSONB, nullable=True)

    runs = relationship(
        "HeartbeatRun",
        back_populates="runtime_state",
        cascade="all, delete-orphan",
        order_by="HeartbeatRun.created_at.desc()",
    )
    wakeup_requests = relationship(
        "AgentWakeupRequest",
        back_populates="runtime_state",
        cascade="all, delete-orphan",
        order_by="AgentWakeupRequest.priority.desc()",
    )

    def __repr__(self) -> str:
        return f"<AgentRuntimeState agent={self.agent_id} enabled={self.heartbeat_enabled}>"


class HeartbeatRun(Base, TimestampMixin):
    """A single heartbeat execution for an agent (#1407)."""

    __tablename__ = "heartbeat_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String(255), nullable=False, index=True)
    runtime_state_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_runtime_state.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(
        String(30),
        nullable=False,
        default=HeartbeatRunStatus.QUEUED.value,
        index=True,
    )
    trigger = Column(String(30), nullable=False, default=WakeupTrigger.INTERVAL.value)
    wakeup_context = Column(JSONB, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    tokens_used = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)
    model = Column(String(255), nullable=True)
    provider = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)

    runtime_state = relationship("AgentRuntimeState", back_populates="runs")
    events = relationship(
        "HeartbeatRunEvent",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="HeartbeatRunEvent.occurred_at",
    )

    def __repr__(self) -> str:
        return f"<HeartbeatRun id={self.id} agent={self.agent_id} status={self.status}>"


class HeartbeatRunEvent(Base):
    """Granular event within a heartbeat run (#1407)."""

    __tablename__ = "heartbeat_run_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("heartbeat_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type = Column(String(100), nullable=False, index=True)
    message = Column(Text, nullable=True)
    payload = Column(JSONB, nullable=True)
    occurred_at = Column(String(50), nullable=False)

    run = relationship("HeartbeatRun", back_populates="events")

    def __repr__(self) -> str:
        return f"<HeartbeatRunEvent run={self.run_id} type={self.event_type}>"


class AgentWakeupRequest(Base, TimestampMixin):
    """Queued wakeup request consumed on the next heartbeat tick (#1407)."""

    __tablename__ = "agent_wakeup_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String(255), nullable=False, index=True)
    runtime_state_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_runtime_state.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    priority = Column(Integer, nullable=False, default=0, index=True)
    context = Column(JSONB, nullable=True)
    reason = Column(String(255), nullable=True)
    consumed_at = Column(DateTime, nullable=True)
    consumed_by_run_id = Column(UUID(as_uuid=True), nullable=True)

    runtime_state = relationship("AgentRuntimeState", back_populates="wakeup_requests")

    def __repr__(self) -> str:
        return (
            f"<AgentWakeupRequest agent={self.agent_id} "
            f"priority={self.priority} consumed={self.consumed_at is not None}>"
        )
