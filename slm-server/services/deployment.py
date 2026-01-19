# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Deployment Service

Manages Ansible-based role deployments to nodes.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.database import Deployment, DeploymentStatus, Node, NodeStatus
from models.schemas import DeploymentCreate, DeploymentResponse

logger = logging.getLogger(__name__)


class DeploymentService:
    """Manages deployments to nodes via Ansible."""

    def __init__(self):
        self.ansible_dir = Path(settings.ansible_dir)
        self._running_deployments: Dict[str, asyncio.Task] = {}

    async def create_deployment(
        self, db: AsyncSession, deployment_data: DeploymentCreate, triggered_by: str
    ) -> DeploymentResponse:
        """Create a new deployment."""
        result = await db.execute(
            select(Node).where(Node.node_id == deployment_data.node_id)
        )
        node = result.scalar_one_or_none()
        if not node:
            raise ValueError(f"Node not found: {deployment_data.node_id}")

        deployment_id = str(uuid.uuid4())[:8]
        deployment = Deployment(
            deployment_id=deployment_id,
            node_id=deployment_data.node_id,
            roles=deployment_data.roles,
            status=DeploymentStatus.PENDING.value,
            triggered_by=triggered_by,
            extra_data=deployment_data.extra_data,
        )
        db.add(deployment)
        await db.commit()
        await db.refresh(deployment)

        asyncio.create_task(self._run_deployment(deployment_id))

        return DeploymentResponse.model_validate(deployment)

    async def get_deployment(
        self, db: AsyncSession, deployment_id: str
    ) -> Optional[DeploymentResponse]:
        """Get a deployment by ID."""
        result = await db.execute(
            select(Deployment).where(Deployment.deployment_id == deployment_id)
        )
        deployment = result.scalar_one_or_none()
        if deployment:
            return DeploymentResponse.model_validate(deployment)
        return None

    async def list_deployments(
        self,
        db: AsyncSession,
        node_id: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[DeploymentResponse], int]:
        """List deployments with optional filters."""
        query = select(Deployment)

        if node_id:
            query = query.where(Deployment.node_id == node_id)
        if status:
            query = query.where(Deployment.status == status)

        query = query.order_by(Deployment.created_at.desc())

        count_result = await db.execute(
            select(Deployment.id).where(query.whereclause or True)
        )
        total = len(count_result.all())

        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await db.execute(query)
        deployments = result.scalars().all()

        return (
            [DeploymentResponse.model_validate(d) for d in deployments],
            total,
        )

    async def cancel_deployment(
        self, db: AsyncSession, deployment_id: str
    ) -> Optional[DeploymentResponse]:
        """Cancel a pending or running deployment."""
        result = await db.execute(
            select(Deployment).where(Deployment.deployment_id == deployment_id)
        )
        deployment = result.scalar_one_or_none()

        if not deployment:
            return None

        if deployment.status not in [
            DeploymentStatus.PENDING.value,
            DeploymentStatus.IN_PROGRESS.value,
        ]:
            raise ValueError(f"Cannot cancel deployment in status: {deployment.status}")

        if deployment_id in self._running_deployments:
            self._running_deployments[deployment_id].cancel()
            del self._running_deployments[deployment_id]

        deployment.status = DeploymentStatus.CANCELLED.value
        deployment.completed_at = datetime.utcnow()
        await db.commit()
        await db.refresh(deployment)

        return DeploymentResponse.model_validate(deployment)

    async def rollback_deployment(
        self, db: AsyncSession, deployment_id: str
    ) -> Optional[DeploymentResponse]:
        """Rollback a completed deployment."""
        result = await db.execute(
            select(Deployment).where(Deployment.deployment_id == deployment_id)
        )
        deployment = result.scalar_one_or_none()

        if not deployment:
            return None

        if deployment.status != DeploymentStatus.COMPLETED.value:
            raise ValueError(f"Cannot rollback deployment in status: {deployment.status}")

        # Get the node
        node_result = await db.execute(
            select(Node).where(Node.node_id == deployment.node_id)
        )
        node = node_result.scalar_one_or_none()

        if not node:
            raise ValueError("Node not found")

        # Remove deployed roles from node
        current_roles = set(node.roles or [])
        deployed_roles = set(deployment.roles or [])
        node.roles = list(current_roles - deployed_roles)

        # Mark deployment as rolled back
        deployment.status = DeploymentStatus.ROLLED_BACK.value
        deployment.completed_at = datetime.utcnow()

        await db.commit()
        await db.refresh(deployment)

        return DeploymentResponse.model_validate(deployment)

    async def _run_deployment(self, deployment_id: str) -> None:
        """Execute a deployment using Ansible."""
        from services.database import db_service

        logger.info("Starting deployment: %s", deployment_id)

        async with db_service.session() as db:
            result = await db.execute(
                select(Deployment).where(Deployment.deployment_id == deployment_id)
            )
            deployment = result.scalar_one_or_none()

            if not deployment:
                logger.error("Deployment not found: %s", deployment_id)
                return

            node_result = await db.execute(
                select(Node).where(Node.node_id == deployment.node_id)
            )
            node = node_result.scalar_one_or_none()

            if not node:
                deployment.status = DeploymentStatus.FAILED.value
                deployment.error = "Node not found"
                deployment.completed_at = datetime.utcnow()
                await db.commit()
                return

            deployment.status = DeploymentStatus.IN_PROGRESS.value
            deployment.started_at = datetime.utcnow()
            await db.commit()

            try:
                output = await self._execute_ansible_playbook(
                    node.ip_address, deployment.roles
                )

                deployment.status = DeploymentStatus.COMPLETED.value
                deployment.playbook_output = output
                deployment.completed_at = datetime.utcnow()

                node.roles = list(set(node.roles or []) | set(deployment.roles))
                await db.commit()

                logger.info("Deployment completed: %s", deployment_id)

            except asyncio.CancelledError:
                deployment.status = DeploymentStatus.CANCELLED.value
                deployment.completed_at = datetime.utcnow()
                await db.commit()
                logger.info("Deployment cancelled: %s", deployment_id)

            except Exception as e:
                deployment.status = DeploymentStatus.FAILED.value
                deployment.error = str(e)
                deployment.completed_at = datetime.utcnow()
                await db.commit()
                logger.error("Deployment failed: %s - %s", deployment_id, e)

    async def _execute_ansible_playbook(
        self, host: str, roles: List[str]
    ) -> str:
        """Execute an Ansible playbook for the given roles."""
        playbook_path = self.ansible_dir / "deploy.yml"

        if not playbook_path.exists():
            raise FileNotFoundError(f"Playbook not found: {playbook_path}")

        roles_str = ",".join(roles)
        cmd = [
            "ansible-playbook",
            str(playbook_path),
            "-i", f"{host},",
            "-e", f"target_roles={roles_str}",
            "-e", f"target_host={host}",
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(self.ansible_dir),
        )

        stdout, _ = await process.communicate()
        output = stdout.decode("utf-8", errors="replace")

        if process.returncode != 0:
            raise RuntimeError(f"Ansible playbook failed:\n{output}")

        return output


deployment_service = DeploymentService()
