# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Deployment Bridge

Bridges autobot-backend to the SLM deployment API so that Docker containers
can be deployed via Ansible playbooks without callers needing to know the SLM
request shape.  Also exposes a richer in-process DeploymentCoordinator for
multi-role, multi-node rollouts that tracks steps locally before forwarding
the underlying playbook call to the SLM.

Related to Issue #3407.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from autobot_shared.logging_manager import get_logger
from models.infrastructure import (
    DeploymentStrategy,
    DockerContainerSpec,
    DockerDeploymentRequest,
    DockerDeploymentStatus,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DeploymentStatus(str, enum.Enum):
    """Lifecycle states for an in-process deployment."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"


class DeploymentStepType(str, enum.Enum):
    """Types of steps within a deployment."""

    DRAIN = "drain"
    DEPLOY = "deploy"
    HEALTH_CHECK = "health_check"
    ROLLBACK = "rollback"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DeploymentStep:
    """A single step within a deployment context."""

    step_type: DeploymentStepType
    node_id: str
    node_name: str
    description: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    success: bool | None = None
    error: str | None = None


@dataclass
class DeploymentContext:
    """Tracks a multi-node, multi-step deployment in memory."""

    deployment_id: str
    strategy: DeploymentStrategy
    role_name: str
    target_nodes: list[str]
    playbook_path: str | None = None
    status: DeploymentStatus = DeploymentStatus.QUEUED
    steps: list[DeploymentStep] = field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# SLMDeploymentBridge — thin SLM HTTP bridge for Docker deployments
# ---------------------------------------------------------------------------


class SLMDeploymentBridge:
    """
    Calls the SLM backend to trigger and query Docker deployments.

    This class handles the translation between autobot-backend's
    DockerDeploymentRequest model and the SLM's POST /deployments payload.
    It does not maintain in-process state; all state lives in the SLM.
    """

    def __init__(self, slm_client: Any) -> None:
        self._client = slm_client

    def _build_extra_vars(self, containers: list[DockerContainerSpec]) -> dict:
        """Build Ansible extra_vars dict from container specs."""
        return {
            "docker_containers": [
                {
                    "name": c.name,
                    "image": f"{c.image}:{c.tag}",
                    "ports": [f"{p.host_port}:{p.container_port}/{p.protocol}" for p in c.ports],
                    "environment": c.environment,
                    "restart_policy": c.restart_policy,
                }
                for c in containers
            ]
        }

    async def deploy_docker(self, request: DockerDeploymentRequest) -> DockerDeploymentStatus:
        """
        Trigger a Docker deployment on the target node via the SLM.

        Translates DockerDeploymentRequest into the SLM POST /deployments body
        and returns a DockerDeploymentStatus built from the SLM response.
        """
        extra_vars = self._build_extra_vars(request.containers)
        payload = {
            "node_id": request.node_id,
            "roles": ["docker"],
            "extra_data": {
                "playbook": request.playbook,
                "extra_vars": extra_vars,
            },
        }
        logger.info("Triggering Docker deployment on node %s via SLM", request.node_id)
        response = await self._client.create_deployment(payload)
        return self._map_response(response)

    async def get_deployment(self, deployment_id: str) -> DockerDeploymentStatus:
        """Fetch the status of a single deployment from the SLM."""
        response = await self._client.get_deployment(deployment_id)
        return self._map_response(response)

    async def list_deployments(self, node_id: str | None = None) -> list[DockerDeploymentStatus]:
        """List deployments, optionally filtered by node_id."""
        response = await self._client.list_deployments(node_id=node_id)
        deployments = response.get("deployments", [])
        return [self._map_response(d) for d in deployments]

    def _map_response(self, data: dict) -> DockerDeploymentStatus:
        """Map a raw SLM response dict to a DockerDeploymentStatus."""
        return DockerDeploymentStatus(
            deployment_id=data.get("deployment_id", ""),
            node_id=data.get("node_id", ""),
            status=data.get("status", "unknown"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            error=data.get("error"),
        )


# ---------------------------------------------------------------------------
# DeploymentCoordinator — in-process multi-step coordinator
# ---------------------------------------------------------------------------


class DeploymentCoordinator:
    """
    In-process orchestrator that tracks multi-role, multi-node deployments.

    Maintains an active_deployments list so that the API layer can query and
    act on in-flight deployments without a database round-trip.  Actual
    playbook execution is delegated to the SLM via the slm_client.
    """

    def __init__(self, slm_client: Any) -> None:
        self._client = slm_client
        self.active_deployments: list[DeploymentContext] = []

    async def create_deployment(
        self,
        role_name: str,
        target_nodes: list[str],
        strategy: DeploymentStrategy = DeploymentStrategy.SEQUENTIAL,
        playbook_path: str | None = None,
    ) -> DeploymentContext:
        """Create and queue a new deployment context."""
        ctx = DeploymentContext(
            deployment_id=str(uuid.uuid4()),
            strategy=strategy,
            role_name=role_name,
            target_nodes=target_nodes,
            playbook_path=playbook_path,
            status=DeploymentStatus.QUEUED,
        )
        self.active_deployments.append(ctx)
        logger.info(
            "Deployment queued: %s for role=%s nodes=%s",
            ctx.deployment_id,
            role_name,
            target_nodes,
        )
        return ctx

    def get_deployment(self, deployment_id: str) -> DeploymentContext | None:
        """Return the DeploymentContext for the given id, or None."""
        for ctx in self.active_deployments:
            if ctx.deployment_id == deployment_id:
                return ctx
        return None

    async def execute_deployment(self, deployment_id: str) -> bool:
        """Execute a QUEUED deployment by forwarding each node to the SLM.

        Transitions the context through RUNNING → COMPLETED/FAILED.
        Returns False if the deployment is not found or not QUEUED.
        """
        ctx = self.get_deployment(deployment_id)
        if ctx is None or ctx.status != DeploymentStatus.QUEUED:
            return False
        ctx.status = DeploymentStatus.RUNNING
        try:
            for node_id in ctx.target_nodes:
                extra: dict = {}
                if ctx.playbook_path:
                    extra["playbook"] = ctx.playbook_path
                await self._client.create_deployment(node_id=node_id, roles=[ctx.role_name], extra_data=extra)
            ctx.status = DeploymentStatus.COMPLETED
            logger.info("Deployment completed: %s", deployment_id)
        except Exception as exc:
            ctx.status = DeploymentStatus.FAILED
            logger.error("Deployment %s failed: %s", deployment_id, exc)
        return True

    async def cancel_deployment(self, deployment_id: str) -> bool:
        """
        Cancel a deployment.

        Returns True if the deployment was found and cancelled; False otherwise.
        """
        ctx = self.get_deployment(deployment_id)
        if ctx is None:
            return False
        if ctx.status not in (DeploymentStatus.QUEUED, DeploymentStatus.RUNNING):
            return False
        ctx.status = DeploymentStatus.CANCELLED
        logger.info("Deployment cancelled: %s", deployment_id)
        return True

    async def trigger_rollback(self, deployment_id: str) -> bool:
        """
        Trigger a rollback for the given deployment.

        Returns True if a rollback step was queued; False if there is nothing
        to roll back (e.g. no nodes have been deployed yet).
        """
        ctx = self.get_deployment(deployment_id)
        if ctx is None:
            return False
        deployed_nodes = [s.node_id for s in ctx.steps if s.success]
        if not deployed_nodes:
            return False
        for node_id in deployed_nodes:
            ctx.steps.append(
                DeploymentStep(
                    step_type=DeploymentStepType.ROLLBACK,
                    node_id=node_id,
                    node_name=node_id,
                    description=f"Rolling back {node_id}",
                )
            )
        ctx.status = DeploymentStatus.ROLLED_BACK
        logger.info("Rollback triggered for deployment %s", deployment_id)
        return True


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_orchestrator: DeploymentCoordinator | None = None


def get_orchestrator() -> DeploymentCoordinator | None:
    """Return the module-level DeploymentCoordinator singleton, or None."""
    return _orchestrator


def init_orchestrator(slm_client: Any) -> DeploymentCoordinator:
    """Initialize the module-level coordinator singleton."""
    global _orchestrator
    _orchestrator = DeploymentCoordinator(slm_client=slm_client)
    logger.info("DeploymentCoordinator initialised")
    return _orchestrator
