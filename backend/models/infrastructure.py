# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SQLAlchemy ORM Models for Infrastructure Management

This module provides the complete database schema for AutoBot's Infrastructure as Code (IaC)
platform, including host inventory, role definitions, credentials, deployments, and audit logging.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class InfraRole(Base):
    """
    Infrastructure role definitions for host provisioning.

    Defines the available roles that can be deployed to infrastructure hosts
    (e.g., frontend, redis, npu-worker, ai-stack, browser).
    """
    __tablename__ = 'infra_roles'

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text)
    ansible_playbook_path = Column(String(255), nullable=False)
    required_ports = Column(JSON)  # JSON array of required ports
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    hosts = relationship("InfraHost", back_populates="role", cascade="all, delete-orphan")

    def __repr__(self):
        """Return string representation of InfraRole."""
        return f"<InfraRole(id={self.id}, name='{self.name}')>"


class InfraHost(Base):
    """
    Infrastructure host inventory for distributed VM architecture.

    Tracks all managed hosts including their connection details, role assignments,
    and current deployment status.
    """
    __tablename__ = 'infra_hosts'

    id = Column(Integer, primary_key=True)
    hostname = Column(String(255), nullable=False, index=True)
    ip_address = Column(String(45), unique=True, nullable=False, index=True)  # IPv4/IPv6 support
    role_id = Column(Integer, ForeignKey('infra_roles.id', ondelete='RESTRICT'), nullable=False)
    status = Column(String(20), default='new', nullable=False, index=True)
    # Status values: new, provisioning, deployed, healthy, degraded, failed

    # SSH connection details
    ssh_port = Column(Integer, default=22, nullable=False)
    ssh_user = Column(String(50), default='autobot', nullable=False)
    ssh_key_path = Column(String(500))  # Path to SSH private key file

    # Ansible facts and metadata
    ansible_facts = Column(JSON)  # Gathered system facts

    # Timestamps
    last_seen_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    role = relationship("InfraRole", back_populates="hosts")
    credentials = relationship(
        "InfraCredential", back_populates="host", cascade="all, delete-orphan"
    )
    deployments = relationship(
        "InfraDeployment", back_populates="host", cascade="all, delete-orphan"
    )

    def __repr__(self):
        """Return string representation of InfraHost."""
        return (
            f"<InfraHost(id={self.id}, hostname='{self.hostname}', "
            f"ip='{self.ip_address}', status='{self.status}')>"
        )


class InfraCredential(Base):
    """
    Encrypted SSH credentials for infrastructure hosts.

    Stores encrypted SSH credentials (passwords or private keys) using Fernet encryption.
    Supports credential rotation and expiration.
    """
    __tablename__ = 'infra_credentials'

    id = Column(Integer, primary_key=True)
    host_id = Column(
        Integer, ForeignKey('infra_hosts.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    credential_type = Column(String(20), nullable=False)  # 'password' or 'ssh_key'
    encrypted_value = Column(Text, nullable=False)  # Fernet encrypted credential
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    expires_at = Column(DateTime)  # Optional expiration for credential rotation
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    host = relationship("InfraHost", back_populates="credentials")

    def __repr__(self):
        """Return string representation of InfraCredential."""
        return (
            f"<InfraCredential(id={self.id}, host_id={self.host_id}, "
            f"type='{self.credential_type}', active={self.is_active})>"
        )


class InfraDeployment(Base):
    """
    Deployment tracking and history for infrastructure operations.

    Records all deployment attempts including Ansible playbook executions,
    success/failure status, and detailed logs.
    """
    __tablename__ = 'infra_deployments'

    id = Column(Integer, primary_key=True)
    host_id = Column(
        Integer, ForeignKey('infra_hosts.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    role = Column(String(50), nullable=False, index=True)
    status = Column(String(20), default='queued', nullable=False, index=True)
    # Status values: queued, running, success, failed, rolled_back

    ansible_run_id = Column(String(36), index=True)  # UUID for Ansible execution
    log_path = Column(String(500))  # Path to deployment log file
    error_message = Column(Text)  # Error details if deployment failed

    # Timestamps
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    host = relationship("InfraHost", back_populates="deployments")

    def __repr__(self):
        """Return string representation of InfraDeployment."""
        return (
            f"<InfraDeployment(id={self.id}, host_id={self.host_id}, "
            f"role='{self.role}', status='{self.status}')>"
        )


class InfraAuditLog(Base):
    """
    Comprehensive audit trail for all infrastructure operations.

    Records all infrastructure changes for security, compliance, and debugging purposes.
    """
    __tablename__ = 'infra_audit_logs'

    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), index=True)  # User or service account that performed action
    # Action performed (e.g., 'create_host', 'deploy_role')
    action = Column(String(100), nullable=False, index=True)
    # Resource type (e.g., 'host', 'credential')
    resource_type = Column(String(50), nullable=False, index=True)
    resource_id = Column(Integer, index=True)  # ID of affected resource
    details = Column(JSON)  # Additional action details and context
    ip_address = Column(String(45))  # Source IP address of request
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        """Return string representation of InfraAuditLog."""
        return (
            f"<InfraAuditLog(id={self.id}, action='{self.action}', "
            f"resource_type='{self.resource_type}', timestamp={self.timestamp})>"
        )
