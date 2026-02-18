# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Skills System DB Models"""
import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class SkillsBase(DeclarativeBase):
    pass


class SkillState(str, Enum):
    DRAFT = "draft"
    INSTALLED = "installed"
    ACTIVE = "active"
    BUILTIN = "builtin"


class RepoType(str, Enum):
    GIT = "git"
    LOCAL = "local"
    HTTP = "http"
    MCP = "mcp"


class GovernanceMode(str, Enum):
    FULL_AUTO = "full_auto"
    SEMI_AUTO = "semi_auto"
    LOCKED = "locked"


class TrustLevel(str, Enum):
    TRUSTED = "trusted"
    MONITORED = "monitored"
    SANDBOXED = "sandboxed"
    RESTRICTED = "restricted"


class SkillPackage(SkillsBase):
    """Persistent record of a skill package and its lifecycle state."""

    __tablename__ = "skill_packages"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, unique=True, index=True)
    version = Column(String, default="1.0.0")
    state = Column(String, nullable=False, default=SkillState.DRAFT)
    repo_id = Column(String, nullable=True)
    skill_md = Column(Text, nullable=False)
    skill_py = Column(Text, nullable=True)
    manifest = Column(JSON, default=dict)
    trust_level = Column(String, default=TrustLevel.MONITORED)
    mcp_pid = Column(Integer, nullable=True)
    gap_reason = Column(Text, nullable=True)
    requested_by = Column(String, default="autobot-self")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    promoted_at = Column(DateTime, nullable=True)


class SkillRepo(SkillsBase):
    """Registry entry for an external or local skill repository."""

    __tablename__ = "skill_repos"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, unique=True)
    url = Column(String, nullable=False)
    repo_type = Column(String, nullable=False)
    auto_sync = Column(Boolean, default=False)
    sync_interval = Column(Integer, default=60)
    last_synced = Column(DateTime, nullable=True)
    skill_count = Column(Integer, default=0)
    status = Column(String, default="active")
    error_message = Column(Text, nullable=True)


class SkillApproval(SkillsBase):
    """Approval workflow record for a skill promotion request."""

    __tablename__ = "skill_approvals"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    skill_id = Column(String, nullable=False, index=True)
    requested_by = Column(String, nullable=False)
    requested_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    reason = Column(Text, nullable=False)
    status = Column(String, default="pending")
    reviewed_by = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    restrictions = Column(JSON, default=dict)

    def __init__(self, **kwargs):
        """Set Python-level defaults for columns used before DB INSERT."""
        kwargs.setdefault("status", "pending")
        kwargs.setdefault("restrictions", {})
        super().__init__(**kwargs)


class GovernanceConfig(SkillsBase):
    """Singleton row storing the active governance policy for skills."""

    __tablename__ = "skill_governance"
    id = Column(Integer, primary_key=True, default=1)
    mode = Column(String, default=GovernanceMode.SEMI_AUTO)
    default_trust_level = Column(String, default=TrustLevel.MONITORED)
    gap_detection_enabled = Column(Boolean, default=True)
    self_generation_enabled = Column(Boolean, default=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    updated_by = Column(String, nullable=True)

    def __init__(self, **kwargs):
        """Set Python-level defaults for columns used before DB INSERT."""
        kwargs.setdefault("mode", GovernanceMode.SEMI_AUTO)
        kwargs.setdefault("default_trust_level", TrustLevel.MONITORED)
        kwargs.setdefault("gap_detection_enabled", True)
        kwargs.setdefault("self_generation_enabled", True)
        super().__init__(**kwargs)
