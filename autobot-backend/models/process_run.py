# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Process Adapter Models (#1406)

SQLAlchemy models for background process execution, task decomposition,
and agent session persistence.
Tables: process_runs, task_decompositions, agent_sessions.
"""

import uuid
from enum import Enum

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.types import Uuid

from user_management.models.base import Base


class ProcessRunStatus(str, Enum):
    """Lifecycle states for a background process run (#1406)."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class ProcessRun(Base):
    """A single background process execution spawned by an agent (#1406)."""

    __tablename__ = "process_runs"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String(255), nullable=False, index=True)
    task_id = Column(String(255), nullable=True, index=True)
    command = Column(Text, nullable=False)
    args = Column(JSONB, nullable=True)
    status = Column(
        String(30),
        nullable=False,
        default=ProcessRunStatus.QUEUED.value,
        index=True,
    )
    exit_code = Column(Integer, nullable=True)
    signal = Column(String(30), nullable=True)
    log_excerpt = Column(Text, nullable=True)
    log_path = Column(String(1024), nullable=True)
    timeout_seconds = Column(Integer, nullable=False, default=300)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    decompositions = relationship(
        "TaskDecomposition",
        back_populates="process_run",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ProcessRun id={self.id} agent={self.agent_id} status={self.status}>"


class TaskDecomposition(Base):
    """
    One ordered subtask within a decomposed parent task (#1406).

    depends_on holds a list of sibling TaskDecomposition IDs that must
    complete before this subtask may begin.
    """

    __tablename__ = "task_decompositions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_task_id = Column(String(255), nullable=False, index=True)
    subtask_order = Column(Integer, nullable=False)
    process_run_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("process_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    depends_on = Column(JSONB, nullable=True)
    context_in = Column(JSONB, nullable=True)
    context_out = Column(JSONB, nullable=True)
    status = Column(
        String(30),
        nullable=False,
        default=ProcessRunStatus.QUEUED.value,
        index=True,
    )

    process_run = relationship("ProcessRun", back_populates="decompositions")

    def __repr__(self) -> str:
        return f"<TaskDecomposition parent={self.parent_task_id} " f"order={self.subtask_order} status={self.status}>"


class AgentSession(Base):
    """Serialised agent session state with TTL-based expiry (#1406)."""

    __tablename__ = "agent_sessions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String(255), nullable=False, index=True)
    task_id = Column(String(255), nullable=False, index=True)
    session_state = Column(JSONB, nullable=True)
    ttl_seconds = Column(Integer, nullable=False, default=3600)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<AgentSession agent={self.agent_id} task={self.task_id} " f"expires={self.expires_at}>"
