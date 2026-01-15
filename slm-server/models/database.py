# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Database Models

SQLAlchemy models for SLM state persistence.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    JSON,
    Enum,
)
from sqlalchemy.orm import DeclarativeBase
import enum


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class NodeStatus(str, enum.Enum):
    """Node status enumeration."""
    PENDING = "pending"
    ENROLLING = "enrolling"
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    ERROR = "error"
    MAINTENANCE = "maintenance"


class DeploymentStatus(str, enum.Enum):
    """Deployment status enumeration."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


class BackupStatus(str, enum.Enum):
    """Backup status enumeration."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Node(Base):
    """Node model representing a managed machine."""

    __tablename__ = "nodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(String(64), unique=True, nullable=False, index=True)
    hostname = Column(String(255), nullable=False)
    ip_address = Column(String(45), nullable=False)
    status = Column(String(20), default=NodeStatus.PENDING.value)
    roles = Column(JSON, default=list)

    # SSH connectivity
    ssh_user = Column(String(64), default="autobot")
    ssh_port = Column(Integer, default=22)
    auth_method = Column(String(20), default="key")

    # Health metrics
    cpu_percent = Column(Float, default=0.0)
    memory_percent = Column(Float, default=0.0)
    disk_percent = Column(Float, default=0.0)
    last_heartbeat = Column(DateTime, nullable=True)

    # Metadata
    agent_version = Column(String(20), nullable=True)
    os_info = Column(String(255), nullable=True)
    extra_data = Column(JSON, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Deployment(Base):
    """Deployment model for tracking role deployments."""

    __tablename__ = "deployments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    deployment_id = Column(String(64), unique=True, nullable=False, index=True)
    node_id = Column(String(64), nullable=False, index=True)
    roles = Column(JSON, default=list)
    status = Column(String(20), default=DeploymentStatus.PENDING.value)

    # Execution details
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    playbook_output = Column(Text, nullable=True)

    # Metadata
    triggered_by = Column(String(64), nullable=True)
    extra_data = Column(JSON, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Backup(Base):
    """Backup model for tracking backup operations."""

    __tablename__ = "backups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    backup_id = Column(String(64), unique=True, nullable=False, index=True)
    node_id = Column(String(64), nullable=False, index=True)
    service_type = Column(String(32), default="redis")
    backup_path = Column(String(512), nullable=True)
    status = Column(String(20), default=BackupStatus.PENDING.value)

    # Backup details
    size_bytes = Column(Integer, default=0)
    checksum = Column(String(64), nullable=True)
    error = Column(Text, nullable=True)

    # Timestamps
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Setting(Base):
    """Settings model for storing configuration."""

    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(64), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    value_type = Column(String(20), default="string")  # string, int, bool, json
    description = Column(String(255), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class User(Base):
    """User model for authentication."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
