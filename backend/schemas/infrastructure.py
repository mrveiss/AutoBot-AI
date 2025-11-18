# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pydantic Schemas for Infrastructure Management API

Provides request/response validation for infrastructure host management,
deployments, and credentials.
"""

import ipaddress
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, field_validator


class HostCreate(BaseModel):
    """Schema for creating a new infrastructure host"""

    hostname: str
    ip_address: str
    role: str
    ssh_port: int = 22
    ssh_user: str = "autobot"

    @field_validator("ip_address")
    @classmethod
    def validate_ip_address(cls, v: str) -> str:
        """Validate IP address format (IPv4 or IPv6)"""
        try:
            ipaddress.ip_address(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid IP address: {v}")

    @field_validator("ssh_port")
    @classmethod
    def validate_ssh_port(cls, v: int) -> int:
        """Validate SSH port range"""
        if not 1 <= v <= 65535:
            raise ValueError(f"SSH port must be between 1 and 65535, got {v}")
        return v

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, v: str) -> str:
        """Validate hostname is not empty"""
        if not v or not v.strip():
            raise ValueError("Hostname cannot be empty")
        return v.strip()


class HostUpdate(BaseModel):
    """Schema for updating an existing host (all fields optional)"""

    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    ssh_port: Optional[int] = None
    ssh_user: Optional[str] = None
    status: Optional[str] = None

    @field_validator("ip_address")
    @classmethod
    def validate_ip_address(cls, v: Optional[str]) -> Optional[str]:
        """Validate IP address if provided"""
        if v is not None:
            try:
                ipaddress.ip_address(v)
            except ValueError:
                raise ValueError(f"Invalid IP address: {v}")
        return v

    @field_validator("ssh_port")
    @classmethod
    def validate_ssh_port(cls, v: Optional[int]) -> Optional[int]:
        """Validate SSH port if provided"""
        if v is not None and not 1 <= v <= 65535:
            raise ValueError(f"SSH port must be between 1 and 65535, got {v}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        """Validate status value"""
        valid_statuses = [
            "new",
            "provisioning",
            "deployed",
            "healthy",
            "degraded",
            "failed",
        ]
        if v is not None and v not in valid_statuses:
            raise ValueError(f"Status must be one of {valid_statuses}, got {v}")
        return v


class HostResponse(BaseModel):
    """Schema for host response"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    hostname: str
    ip_address: str
    role_id: int
    status: str
    ssh_port: int
    ssh_user: str
    ssh_key_path: Optional[str] = None
    ansible_facts: Optional[Dict[str, Any]] = None
    last_seen_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class HostDetailResponse(BaseModel):
    """Schema for detailed host response with related data"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    hostname: str
    ip_address: str
    role_id: int
    role_name: str
    status: str
    ssh_port: int
    ssh_user: str
    ssh_key_path: Optional[str] = None
    ansible_facts: Optional[Dict[str, Any]] = None
    last_seen_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    has_active_credential: bool = False
    deployment_count: int = 0
    last_deployment_status: Optional[str] = None


class DeploymentCreate(BaseModel):
    """Schema for creating a deployment"""

    host_ids: List[int]
    force_redeploy: bool = False

    @field_validator("host_ids")
    @classmethod
    def validate_host_ids(cls, v: List[int]) -> List[int]:
        """Validate host IDs list is not empty"""
        if not v:
            raise ValueError("host_ids cannot be empty")
        if len(v) != len(set(v)):
            raise ValueError("host_ids contains duplicates")
        return v


class DeploymentResponse(BaseModel):
    """Schema for deployment response"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    host_id: int
    role: str
    status: str
    ansible_run_id: Optional[str] = None
    log_path: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime


class DeploymentDetailResponse(BaseModel):
    """Schema for detailed deployment response with host info"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    host_id: int
    hostname: str
    ip_address: str
    role: str
    status: str
    ansible_run_id: Optional[str] = None
    log_path: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    duration_seconds: Optional[float] = None


class RoleResponse(BaseModel):
    """Schema for infrastructure role response"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    ansible_playbook_path: str
    required_ports: Optional[List[int]] = None
    created_at: datetime


class StatisticsResponse(BaseModel):
    """Schema for infrastructure statistics response"""

    total_hosts: int
    hosts_by_status: Dict[str, int]
    total_roles: int
    total_deployments: int
    deployments_by_status: Dict[str, int]
    active_credentials: int


class ProvisionKeyRequest(BaseModel):
    """Schema for SSH key provisioning request"""

    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password is not empty"""
        if not v or not v.strip():
            raise ValueError("Password cannot be empty")
        return v


class ProvisionKeyResponse(BaseModel):
    """Schema for SSH key provisioning response"""

    success: bool
    message: str
    host_id: int
    public_key_fingerprint: Optional[str] = None


class HostStatusResponse(BaseModel):
    """Schema for real-time host status"""

    host_id: int
    hostname: str
    ip_address: str
    status: str
    is_reachable: bool
    response_time_ms: Optional[float] = None
    last_seen_at: Optional[datetime] = None
    active_deployments: int
    error_message: Optional[str] = None
