# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SLM Deployment Service

Manages Ansible-based role deployments to nodes.
"""

import asyncio
import json
import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.async_compat import retain_until_done
from autobot_shared.ssot_config import config as ssot_config
from config import settings
from models.database import Deployment, DeploymentStatus, Node, NodeStatus
from models.schemas import DeploymentCreate, DeploymentResponse
from services.ansible_utils import _find_ansible_playbook as _resolve_ansible_playbook
from services.ansible_utils import ansible_config_env, ansible_run_failure
from services.encryption import decrypt_data
from services.yaml_scalar import yaml_double_quoted

logger = logging.getLogger(__name__)

# Tracked enrollment playbook (#18606), relative to settings.ansible_dir.
_ENROLLMENT_PLAYBOOK = "playbooks/enroll-slm-agent.yml"


class DeploymentService:
    """Manages deployments to nodes via Ansible."""

    def __init__(self):
        self.ansible_dir = Path(settings.ansible_dir)
        self._running_deployments: Dict[str, asyncio.Task] = {}

    async def create_deployment(
        self, db: AsyncSession, deployment_data: DeploymentCreate, triggered_by: str
    ) -> DeploymentResponse:
        """Create a new deployment."""
        result = await db.execute(select(Node).where(Node.node_id == deployment_data.node_id))
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

        retain_until_done(self._running_deployments, deployment_id, self._run_deployment(deployment_id))

        return DeploymentResponse.model_validate(deployment)

    async def get_deployment(self, db: AsyncSession, deployment_id: str) -> DeploymentResponse | None:
        """Get a deployment by ID."""
        result = await db.execute(select(Deployment).where(Deployment.deployment_id == deployment_id))
        deployment = result.scalar_one_or_none()
        if deployment:
            return DeploymentResponse.model_validate(deployment)
        return None

    async def list_deployments(
        self,
        db: AsyncSession,
        node_id: str | None = None,
        status: str | None = None,
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

        count_result = await db.execute(select(Deployment.id).where(query.whereclause or True))
        total = len(count_result.all())

        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await db.execute(query)
        deployments = result.scalars().all()

        return (
            [DeploymentResponse.model_validate(d) for d in deployments],
            total,
        )

    async def cancel_deployment(self, db: AsyncSession, deployment_id: str) -> DeploymentResponse | None:
        """Cancel a pending or running deployment."""
        result = await db.execute(select(Deployment).where(Deployment.deployment_id == deployment_id))
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
        deployment.completed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(deployment)

        return DeploymentResponse.model_validate(deployment)

    async def rollback_deployment(self, db: AsyncSession, deployment_id: str) -> DeploymentResponse | None:
        """Rollback a completed deployment."""
        result = await db.execute(select(Deployment).where(Deployment.deployment_id == deployment_id))
        deployment = result.scalar_one_or_none()

        if not deployment:
            return None

        if deployment.status != DeploymentStatus.COMPLETED.value:
            raise ValueError(f"Cannot rollback deployment in status: {deployment.status}")

        # Get the node
        node_result = await db.execute(select(Node).where(Node.node_id == deployment.node_id))
        node = node_result.scalar_one_or_none()

        if not node:
            raise ValueError("Node not found")

        # Remove deployed roles from node
        current_roles = set(node.roles or [])
        deployed_roles = set(deployment.roles or [])
        node.roles = list(current_roles - deployed_roles)

        # Mark deployment as rolled back
        deployment.status = DeploymentStatus.ROLLED_BACK.value
        deployment.completed_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(deployment)

        return DeploymentResponse.model_validate(deployment)

    async def retry_deployment(
        self, db: AsyncSession, deployment_id: str, triggered_by: str
    ) -> DeploymentResponse | None:
        """Retry a failed deployment by creating a new deployment with same config."""
        result = await db.execute(select(Deployment).where(Deployment.deployment_id == deployment_id))
        original = result.scalar_one_or_none()

        if not original:
            return None

        if original.status != DeploymentStatus.FAILED.value:
            raise ValueError(f"Cannot retry deployment in status: {original.status}")

        # Create a new deployment with the same configuration
        new_deployment_id = str(uuid.uuid4())[:8]
        new_deployment = Deployment(
            deployment_id=new_deployment_id,
            node_id=original.node_id,
            roles=original.roles,
            status=DeploymentStatus.PENDING.value,
            triggered_by=triggered_by,
            extra_data={"retry_of": deployment_id},
        )
        db.add(new_deployment)
        await db.commit()
        await db.refresh(new_deployment)

        retain_until_done(self._running_deployments, new_deployment_id, self._run_deployment(new_deployment_id))

        logger.info(
            "Retry deployment created: %s (retry of %s)",
            new_deployment_id,
            deployment_id,
        )

        return DeploymentResponse.model_validate(new_deployment)

    async def _get_deployment_and_node(
        self, db: AsyncSession, deployment_id: str
    ) -> Tuple[Deployment | None, Node | None]:
        """Get deployment and node records.

        Helper for _run_deployment (Issue #665).
        """
        result = await db.execute(select(Deployment).where(Deployment.deployment_id == deployment_id))
        deployment = result.scalar_one_or_none()

        if not deployment:
            return None, None

        node_result = await db.execute(select(Node).where(Node.node_id == deployment.node_id))
        node = node_result.scalar_one_or_none()

        return deployment, node

    def _get_ssh_credentials(self, node: Node) -> Tuple[str, int, str | None]:
        """Extract and decrypt SSH credentials from node.

        Helper for _run_deployment (Issue #665).

        Returns:
            Tuple of (ssh_user, ssh_port, ssh_password)
        """
        ssh_user = node.ssh_user or "autobot"
        ssh_port = node.ssh_port or 22
        ssh_password = None

        if node.extra_data:
            encrypted_password = node.extra_data.get("ssh_password")
            if encrypted_password:
                # Check if password is encrypted (new format) or plaintext (legacy)
                if node.extra_data.get("ssh_password_encrypted"):
                    try:
                        ssh_password = decrypt_data(encrypted_password)
                    except Exception as e:
                        logger.error(
                            "Failed to decrypt SSH password for node %s: %s",
                            node.node_id,
                            e,
                        )
                        raise RuntimeError("Failed to decrypt stored credentials")
                else:
                    # Legacy plaintext password (migration path)
                    ssh_password = encrypted_password

        return ssh_user, ssh_port, ssh_password

    async def _run_deployment(self, deployment_id: str) -> None:
        """Execute a deployment using Ansible."""
        from services.database import db_service

        logger.info("Starting deployment: %s", deployment_id)

        async with db_service.session() as db:
            deployment, node = await self._get_deployment_and_node(db, deployment_id)

            if not deployment:
                logger.error("Deployment not found: %s", deployment_id)
                return

            if not node:
                deployment.status = DeploymentStatus.FAILED.value
                deployment.error = "Node not found"
                deployment.completed_at = datetime.now(timezone.utc)
                await db.commit()
                return

            deployment.status = DeploymentStatus.IN_PROGRESS.value
            deployment.started_at = datetime.now(timezone.utc)
            await db.commit()

            try:
                ssh_user, ssh_port, ssh_password = self._get_ssh_credentials(node)

                extra = deployment.extra_data or {}
                output = await self._execute_ansible_playbook(
                    node.ip_address,
                    deployment.roles,
                    ssh_user=ssh_user,
                    ssh_port=ssh_port,
                    ssh_password=ssh_password,
                    playbook=extra.get("playbook"),
                )

                deployment.status = DeploymentStatus.COMPLETED.value
                deployment.playbook_output = output
                deployment.completed_at = datetime.now(timezone.utc)

                node.roles = list(set(node.roles or []) | set(deployment.roles))
                await db.commit()

                logger.info("Deployment completed: %s", deployment_id)

            except asyncio.CancelledError:
                deployment.status = DeploymentStatus.CANCELLED.value
                deployment.completed_at = datetime.now(timezone.utc)
                await db.commit()
                logger.info("Deployment cancelled: %s", deployment_id)

            except Exception as e:
                deployment.status = DeploymentStatus.FAILED.value
                deployment.error = str(e)
                deployment.completed_at = datetime.now(timezone.utc)
                await db.commit()
                logger.error("Deployment failed: %s - %s", deployment_id, e)

    def _find_ansible_playbook(self) -> str:
        """Find the ansible-playbook executable with system PATH.

        Shared search logic lives in services.ansible_utils (Issue #12693).
        """
        return _resolve_ansible_playbook()

    def _build_ansible_base_command(self, playbook_path: Path, host: str, roles: List[str]) -> List[str]:
        """Build the base ansible-playbook command list.

        Helper for _execute_ansible_playbook (Issue #665).
        """
        ansible_cmd = self._find_ansible_playbook()
        roles_str = ",".join(roles)
        return [
            ansible_cmd,
            str(playbook_path),
            "-i",
            f"{host},",
            "-e",
            f"target_roles={roles_str}",
            "-e",
            f"target_host={host}",
            "-e",
            "ansible_ssh_common_args='-o StrictHostKeyChecking=accept-new -o ControlPath=none'",
            "-e",
            "ansible_ssh_pipelining=false",
        ]

    def _add_ssh_options_to_command(
        self,
        cmd: List[str],
        ssh_user: str | None,
        ssh_port: int | None,
    ) -> None:
        """Add the non-secret SSH options to ansible command; the password goes via a secrets file.

        Helper for _execute_ansible_playbook (Issue #665).
        """
        if ssh_user:
            cmd.extend(["-e", f"ansible_user={ssh_user}"])

        if ssh_port:
            cmd.extend(["-e", f"ansible_port={ssh_port}"])

    def _get_ansible_environment(self) -> Dict[str, str]:
        """Build the environment dict for Ansible execution (Issue #665)."""
        return {
            **os.environ,
            "ANSIBLE_FORCE_COLOR": "0",
            "ANSIBLE_NOCOLOR": "1",
            "ANSIBLE_HOST_KEY_CHECKING": "False",
            "ANSIBLE_SSH_RETRIES": "3",
            **ansible_config_env(self.ansible_dir),
        }

    async def _execute_ansible_playbook(
        self,
        host: str,
        roles: List[str],
        ssh_user: str | None = None,
        ssh_port: int | None = None,
        ssh_password: str | None = None,
        playbook: str | None = None,
    ) -> str:
        """
        Execute an Ansible playbook for the given roles.

        Args:
            host: Target host IP address
            roles: List of roles to deploy
            ssh_user: SSH username (optional, uses ansible default if not provided)
            ssh_port: SSH port (optional, uses 22 if not provided)
            ssh_password: SSH password for authentication and sudo (optional)
            playbook: Playbook filename override (optional, defaults to deploy.yml)

        Returns:
            Ansible playbook output
        """
        playbook_path = self.ansible_dir / (playbook or "deploy.yml")

        if not playbook_path.exists():
            raise FileNotFoundError(f"Playbook not found: {playbook_path}")

        cmd = self._build_ansible_base_command(playbook_path, host, roles)
        self._add_ssh_options_to_command(cmd, ssh_user, ssh_port)
        logger.debug("Running deployment: %s", " ".join(cmd[:10]) + " ...")

        secrets_path = self._write_enrollment_secrets(ssh_password) if ssh_password else None
        try:
            if secrets_path:
                cmd.extend(["-e", "@" + secrets_path])
            return await self._run_ansible_command(cmd, "Ansible playbook failed", host)
        finally:
            if secrets_path:
                Path(secrets_path).unlink(missing_ok=True)

    def _get_effective_password(self, node: Node, ssh_password: str | None) -> str | None:
        """Get SSH password from parameter or decrypt from node storage.

        Helper for enroll_node (Issue #665).

        Args:
            node: The node record
            ssh_password: Optional password provided at enrollment time

        Returns:
            The effective password to use, or None if no password available
        """
        if ssh_password:
            return ssh_password

        if not node.extra_data:
            return None

        encrypted_password = node.extra_data.get("ssh_password")
        if not encrypted_password:
            return None

        # Check if password is encrypted (new format) or plaintext (legacy)
        if node.extra_data.get("ssh_password_encrypted"):
            try:
                return decrypt_data(encrypted_password)
            except Exception as e:
                logger.error("Failed to decrypt SSH password for node %s: %s", node.node_id, e)
                raise RuntimeError("Failed to decrypt stored credentials")
        else:
            # Legacy plaintext password (migration path)
            return encrypted_password

    async def _handle_enrollment_success(self, db: AsyncSession, node: Node, output: str) -> None:
        """Update node status and clear password after successful enrollment.

        Helper for enroll_node (Issue #665).

        Args:
            db: Database session
            node: The node that was enrolled
            output: Playbook output for logging
        """
        # Mark as online - agent will send first heartbeat
        node.status = NodeStatus.ONLINE.value

        # Update auth method to key-based (SSH keys deployed during enrollment)
        node.auth_method = "key"

        # Clear stored password from extra_data (no longer needed)
        if node.extra_data and "ssh_password" in node.extra_data:
            extra_data = dict(node.extra_data)
            del extra_data["ssh_password"]
            node.extra_data = extra_data

        await db.commit()

        logger.info("Enrollment completed for node %s - auth_method set to key", node.node_id)

    async def enroll_node(self, db: AsyncSession, node_id: str, ssh_password: str | None = None) -> Tuple[bool, str]:
        """
        Enroll a node by deploying the SLM agent.

        This deploys the slm-agent role which installs and starts
        the agent service that sends heartbeats to the SLM backend.

        Args:
            db: Database session
            node_id: The node ID to enroll
            ssh_password: Optional SSH password for password-based authentication

        Returns: (success, message)
        """
        result = await db.execute(select(Node).where(Node.node_id == node_id))
        node = result.scalar_one_or_none()

        if not node:
            return False, "Node not found"

        # Allow enrollment for pending, error, offline, or degraded nodes
        # Degraded = reachable but no agent running - enrollment deploys the agent
        allowed_statuses = [
            NodeStatus.PENDING.value,
            NodeStatus.ERROR.value,
            NodeStatus.OFFLINE.value,
            NodeStatus.DEGRADED.value,
        ]
        if node.status not in allowed_statuses:
            return False, f"Cannot enroll node in status: {node.status}"

        # Update status to enrolling
        node.status = NodeStatus.ENROLLING.value
        await db.commit()

        logger.info("Starting enrollment for node %s (%s)", node_id, node.ip_address)

        try:
            # Get effective password (provided or from stored encrypted)
            effective_password = self._get_effective_password(node, ssh_password)

            # Deploy the slm-agent role
            output = await self._execute_enrollment_playbook(
                node.ip_address,
                node_id,
                node.ssh_user or "autobot",
                node.ssh_port or 22,
                ssh_password=effective_password,
            )

            # Handle success: update status, clear password, commit
            await self._handle_enrollment_success(db, node, output)

            return True, f"Agent deployed successfully. Output:\n{output}"

        except Exception as e:
            logger.error("Enrollment failed for node %s: %s", node_id, e)
            node.status = NodeStatus.ERROR.value
            await db.commit()
            return False, "Node enrollment failed"

    def _enrollment_var_args(
        self,
        host: str,
        node_id: str,
        ssh_user: str,
        ssh_port: int,
        admin_url: str,
        slm_pubkey: str,
    ) -> List[str]:
        """The non-secret `-e` extra-vars of the enrollment command (#18606).

        The SLM public key travels as a JSON extra-var (it contains spaces), never
        by substitution into playbook text.
        """
        pairs = [
            f"ansible_host={host}",
            f"ansible_user={ssh_user}",
            f"ansible_port={ssh_port}",
            f"slm_node_id={node_id}",
            f"slm_admin_url={admin_url}",
            f"slm_heartbeat_interval={settings.heartbeat_interval}",
            "ansible_ssh_common_args='-o StrictHostKeyChecking=accept-new -o ControlPath=none'",
            "ansible_ssh_pipelining=false",
            json.dumps({"slm_server_pubkey": slm_pubkey}),
        ]
        return [arg for pair in pairs for arg in ("-e", pair)]

    def _build_enrollment_command(
        self,
        playbook_path: Path,
        host: str,
        node_id: str,
        ssh_user: str,
        ssh_port: int,
        admin_url: str,
        slm_pubkey: str = "",
    ) -> List[str]:
        """Build the ansible-playbook command for enrollment.

        Helper for _execute_enrollment_playbook (Issue #665).
        """
        return [
            self._find_ansible_playbook(),
            str(playbook_path),
            "-i",
            f"{host},",
            *self._enrollment_var_args(host, node_id, ssh_user, ssh_port, admin_url, slm_pubkey),
        ]

    def _write_enrollment_secrets(self, ssh_password: str) -> str:
        """Write the password to a 0600 `!unsafe` YAML vars file (`-e @file`, never argv); return its path."""
        if not shutil.which("sshpass"):
            raise RuntimeError("Password auth requires 'sshpass'. Install: sudo apt install sshpass")
        fd, path = tempfile.mkstemp(prefix="enroll-secrets-", suffix=".yml")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                quoted = yaml_double_quoted(ssh_password)
                handle.write(f"ansible_ssh_pass: !unsafe {quoted}\nansible_become_pass: !unsafe {quoted}\n")
        except BaseException:
            Path(path).unlink(missing_ok=True)
            raise
        return path

    async def _run_ansible_command(self, cmd: List[str], failure: str, host: str) -> str:
        """Run a single-host ansible-playbook; raise unless the recap proves ``host`` ran (#19475)."""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(self.ansible_dir),
            env=self._get_ansible_environment(),
        )
        output = (await process.communicate())[0].decode("utf-8", errors="replace")
        if problem := ansible_run_failure(output, host, process.returncode):
            raise RuntimeError(f"{failure}:\n{problem}")
        return output

    async def _execute_enrollment_playbook(
        self,
        host: str,
        node_id: str,
        ssh_user: str,
        ssh_port: int,
        ssh_password: str | None = None,
    ) -> str:
        """Execute the SLM agent enrollment playbook."""
        playbook_path = self.ansible_dir / _ENROLLMENT_PLAYBOOK
        if not playbook_path.exists():
            raise FileNotFoundError(f"Enrollment playbook not found: {playbook_path}")
        slm_pubkey = await self._get_slm_public_key()
        # external_url is the admin URL that nodes use
        cmd = self._build_enrollment_command(
            playbook_path, host, node_id, ssh_user, ssh_port, settings.external_url, slm_pubkey
        )
        secrets_path = self._write_enrollment_secrets(ssh_password) if ssh_password else None
        try:
            if secrets_path:
                cmd.extend(["-e", "@" + secrets_path])
            logger.debug("Running enrollment: %s", " ".join(cmd[:10]) + " ...")
            return await self._run_ansible_command(cmd, "Enrollment playbook failed", host)
        finally:
            if secrets_path:
                Path(secrets_path).unlink(missing_ok=True)

    async def _get_slm_public_key(self) -> str:
        """
        Get the SLM server's SSH public key for deploying to nodes.

        This enables passwordless SSH access from the SLM server to enrolled nodes.
        The key is read from the configured path or generated if it doesn't exist.

        Returns:
            The public key content, or empty string if unavailable.
        """
        # Default SSH key paths for the autobot user
        # Canonical inter-node fleet key (#12429) — same identity Ansible and
        # every SSH caller resolve, so the pubkey deployed to nodes matches the
        # private key later used to connect.
        privkey_path = ssot_config.path.ssh_key
        pubkey_path = Path(ssot_config.path.ssh_pubkey_path)
        ssh_dir = privkey_path.parent

        # Try to read existing public key
        if pubkey_path.exists():
            try:
                return (await asyncio.to_thread(pubkey_path.read_text, encoding="utf-8")).strip()
            except Exception as e:
                logger.warning("Failed to read SSH public key: %s", e)

        # Generate new SSH key pair if it doesn't exist
        if not privkey_path.exists():
            logger.info("Generating SSH key pair for SLM server...")
            try:
                # Ensure .ssh directory exists with correct permissions
                ssh_dir.mkdir(mode=0o700, exist_ok=True)

                # Generate RSA key pair
                proc = await asyncio.create_subprocess_exec(
                    "ssh-keygen",
                    "-t",
                    "rsa",
                    "-b",
                    "4096",
                    "-f",
                    str(privkey_path),
                    "-N",
                    "",  # No passphrase
                    "-C",
                    "slm-server@autobot",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await proc.communicate()

                if proc.returncode != 0:
                    logger.error("Failed to generate SSH key: %s", stderr.decode())
                    return ""

                logger.info("SSH key pair generated successfully")

                # Read the newly generated public key
                if pubkey_path.exists():
                    return (await asyncio.to_thread(pubkey_path.read_text, encoding="utf-8")).strip()

            except Exception as e:
                logger.error("Error generating SSH key pair: %s", e)

        return ""


deployment_service = DeploymentService()
