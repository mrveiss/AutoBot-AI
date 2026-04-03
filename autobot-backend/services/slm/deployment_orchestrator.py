# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Deployment Orchestrator

Bridges autobot-backend to the SLM deployment API so that Docker containers
can be deployed via Ansible playbooks without callers needing to know the SLM
request shape.  Also exposes a richer in-process DeploymentOrchestrator for
multi-role, multi-node rollouts that tracks steps locally before forwarding
the underlying playbook call to the SLM.

Related to Issue #3407.
"""

from __future__ import annotations

import enum
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from models.infrastructure import (
    DeploymentStrategy,
    DockerContainerSpec,
    DockerDeploymentRequest,
    DockerDeploymentStatus,
)

logger = logging.getLogger(__name__)


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
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    success: Optional[bool] = None
    error: Optional[str] = None


@dataclass
class DeploymentContext:
    """Tracks a multi-node, multi-step deployment in memory."""

    deployment_id: str
    strategy: DeploymentStrategy
    role_name: str
    target_nodes: list[str]
    playbook_path: Optional[str] = None
    status: DeploymentStatus = DeploymentStatus.QUEUED
    steps: list[DeploymentStep] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# SLMDeploymentOrchestrator — thin SLM HTTP bridge for Docker deployments
# ---------------------------------------------------------------------------


class SLMDeploymentOrchestrator:
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
                    "ports": [
                        f"{p.host_port}:{p.container_port}/{p.protocol}"
                        for p in c.ports
                    ],
                    "environment": c.environment,
                    "restart_policy": c.restart_policy,
                }
                for c in containers
            ]
        }

    async def deploy_docker(
        self, request: DockerDeploymentRequest
    ) -> DockerDeploymentStatus:
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

    async def list_deployments(
        self, node_id: Optional[str] = None
    ) -> list[DockerDeploymentStatus]:
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
# DeploymentOrchestrator — in-process multi-step orchestrator
# ---------------------------------------------------------------------------


class DeploymentOrchestrator:
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
        playbook_path: Optional[str] = None,
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

    def get_deployment(self, deployment_id: str) -> Optional[DeploymentContext]:
        """Return the DeploymentContext for the given id, or None."""
        for ctx in self.active_deployments:
            if ctx.deployment_id == deployment_id:
                return ctx
        return None

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

_orchestrator: Optional[DeploymentOrchestrator] = None


def get_orchestrator() -> Optional[DeploymentOrchestrator]:
    """Return the module-level DeploymentOrchestrator singleton, or None."""
    return _orchestrator


def init_orchestrator(slm_client: Any) -> DeploymentOrchestrator:
    """Initialize the module-level orchestrator singleton."""
    global _orchestrator
    _orchestrator = DeploymentOrchestrator(slm_client=slm_client)
    logger.info("DeploymentOrchestrator initialised")
    return _orchestrator
