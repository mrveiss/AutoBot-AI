# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Infrastructure Pydantic models for Docker deployment orchestration.

These models represent the request/response shapes used when autobot-backend
orchestrates Docker container deployments via the SLM Ansible playbook runner.

Related to Issue #3407.
"""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field


class DeploymentStrategy(str, enum.Enum):
    """Deployment rollout strategy."""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CANARY = "canary"


class PortMapping(BaseModel):
    """A single host-to-container port mapping."""

    host_port: int
    container_port: int
    protocol: str = "tcp"


class DockerContainerSpec(BaseModel):
    """Specification for a single Docker container to deploy."""

    name: str
    image: str
    tag: str = "latest"
    ports: list[PortMapping] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)
    restart_policy: str = "unless-stopped"


class DockerDeploymentRequest(BaseModel):
    """Request body for triggering a Docker deployment via the SLM."""

    node_id: str
    containers: list[DockerContainerSpec]
    playbook: str = "deploy-hybrid-docker.yml"


class DockerDeploymentStatus(BaseModel):
    """Status of a Docker deployment returned by the SLM."""

    deployment_id: str
    node_id: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


class DeploymentCreateRequest(BaseModel):
    """Generic deployment create request (multi-role, non-Docker path)."""

    role_name: str
    target_nodes: list[str]
    strategy: DeploymentStrategy = DeploymentStrategy.SEQUENTIAL
    playbook_path: str | None = None


class DeploymentActionResponse(BaseModel):
    """Response for execute / cancel / rollback actions."""

    deployment_id: str
    action: str
    success: bool
    message: str | None = None
