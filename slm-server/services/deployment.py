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

    async def retry_deployment(
        self, db: AsyncSession, deployment_id: str, triggered_by: str
    ) -> Optional[DeploymentResponse]:
        """Retry a failed deployment by creating a new deployment with same config."""
        result = await db.execute(
            select(Deployment).where(Deployment.deployment_id == deployment_id)
        )
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

        # Start the deployment in background
        asyncio.create_task(self._run_deployment(new_deployment_id))

        logger.info(
            "Retry deployment created: %s (retry of %s)",
            new_deployment_id,
            deployment_id,
        )

        return DeploymentResponse.model_validate(new_deployment)

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

    async def enroll_node(
        self, db: AsyncSession, node_id: str, ssh_password: Optional[str] = None
    ) -> Tuple[bool, str]:
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

        # Use provided password, or fall back to stored password from node registration
        effective_password = ssh_password
        if not effective_password and node.extra_data:
            effective_password = node.extra_data.get("ssh_password")

        try:
            # Deploy the slm-agent role
            output = await self._execute_enrollment_playbook(
                node.ip_address,
                node_id,
                node.ssh_user or "autobot",
                node.ssh_port or 22,
                ssh_password=effective_password,
            )

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

            logger.info("Enrollment completed for node %s - auth_method set to key", node_id)
            return True, f"Agent deployed successfully. Output:\n{output}"

        except Exception as e:
            logger.error("Enrollment failed for node %s: %s", node_id, e)
            node.status = NodeStatus.ERROR.value
            await db.commit()
            return False, str(e)

    async def _execute_enrollment_playbook(
        self, host: str, node_id: str, ssh_user: str, ssh_port: int,
        ssh_password: Optional[str] = None
    ) -> str:
        """Execute the SLM agent enrollment playbook."""
        import shutil

        playbook_path = self.ansible_dir / "enroll.yml"

        # Create enrollment playbook if it doesn't exist
        if not playbook_path.exists():
            await self._create_enrollment_playbook(playbook_path)

        # Use external_url from config for the admin URL that nodes will use
        admin_url = settings.external_url

        # Build the ansible command
        # Always skip host key checking for automated enrollment
        cmd = [
            "ansible-playbook",
            str(playbook_path),
            "-i", f"{host},",
            "-e", f"ansible_host={host}",
            "-e", f"ansible_user={ssh_user}",
            "-e", f"ansible_port={ssh_port}",
            "-e", f"slm_node_id={node_id}",
            "-e", f"slm_admin_url={admin_url}",
            "-e", f"slm_heartbeat_interval={settings.heartbeat_interval}",
            "-e", "ansible_ssh_common_args='-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'",
        ]

        # Add password authentication if provided
        if ssh_password:
            if not shutil.which("sshpass"):
                raise RuntimeError(
                    "Password auth requires 'sshpass'. Install: sudo apt install sshpass"
                )
            # Use sshpass with ansible for both SSH and sudo
            cmd.extend([
                "-e", "ansible_ssh_pass=" + ssh_password,
                "-e", "ansible_become_pass=" + ssh_password,
            ])

        logger.debug("Running enrollment: %s", " ".join(cmd[:10]) + " ...")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(self.ansible_dir),
        )

        stdout, _ = await process.communicate()
        output = stdout.decode("utf-8", errors="replace")

        if process.returncode != 0:
            raise RuntimeError(f"Enrollment playbook failed:\n{output}")

        return output

    async def _get_slm_public_key(self) -> str:
        """
        Get the SLM server's SSH public key for deploying to nodes.

        This enables passwordless SSH access from the SLM server to enrolled nodes.
        The key is read from the configured path or generated if it doesn't exist.

        Returns:
            The public key content, or empty string if unavailable.
        """
        # Default SSH key paths for the autobot user
        ssh_dir = Path.home() / ".ssh"
        pubkey_path = ssh_dir / "id_rsa.pub"
        privkey_path = ssh_dir / "id_rsa"

        # Try to read existing public key
        if pubkey_path.exists():
            try:
                return pubkey_path.read_text(encoding="utf-8").strip()
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
                    "-t", "rsa",
                    "-b", "4096",
                    "-f", str(privkey_path),
                    "-N", "",  # No passphrase
                    "-C", "slm-server@autobot",
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
                    return pubkey_path.read_text(encoding="utf-8").strip()

            except Exception as e:
                logger.error("Error generating SSH key pair: %s", e)

        return ""

    async def _create_enrollment_playbook(self, path: Path) -> None:
        """Create the enrollment playbook for deploying SLM agent."""
        # Get SLM server's public key for SSH key deployment
        slm_pubkey = await self._get_slm_public_key()

        # Use regular string with placeholder to avoid f-string conflicts with
        # Ansible {{ variables }} and embedded Python f-strings
        playbook_content = """# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# SLM Agent Enrollment Playbook
# This playbook:
# 1. Creates the autobot user for agent operations
# 2. Sets up SSH key-based authentication for future passwordless access
# 3. Installs and configures the SLM agent
# 4. Starts the agent service for heartbeat reporting
---
- name: Enroll Node - Deploy SLM Agent
  hosts: all
  become: true
  gather_facts: true

  vars:
    slm_agent_dir: /opt/autobot
    slm_agent_data_dir: /var/lib/autobot
    slm_agent_user: autobot
    slm_agent_group: autobot
    slm_agent_python_packages:
      - psutil
      - requests
      - pyyaml
    slm_server_pubkey: "__SLM_PUBKEY_PLACEHOLDER__"

  tasks:
    # ==========================================================
    # SSH Key Setup for Passwordless Future Access
    # ==========================================================
    - name: Ensure .ssh directory exists for autobot user
      file:
        path: "/home/{{ slm_agent_user }}/.ssh"
        state: directory
        owner: "{{ slm_agent_user }}"
        group: "{{ slm_agent_group }}"
        mode: '0700'
      when: slm_server_pubkey | length > 0

    - name: Deploy SLM server SSH public key for passwordless access
      authorized_key:
        user: "{{ slm_agent_user }}"
        key: "{{ slm_server_pubkey }}"
        state: present
        comment: "SLM Server - AutoBot Fleet Management"
      when: slm_server_pubkey | length > 0

    # ==========================================================
    # User and Directory Setup
    # ==========================================================
    - name: Create autobot user
      user:
        name: "{{ slm_agent_user }}"
        system: yes
        shell: /bin/bash
        home: "/home/{{ slm_agent_user }}"
        create_home: yes

    - name: Create agent directories
      file:
        path: "{{ item }}"
        state: directory
        owner: "{{ slm_agent_user }}"
        group: "{{ slm_agent_group }}"
        mode: '0755'
      loop:
        - "{{ slm_agent_dir }}"
        - "{{ slm_agent_dir }}/slm"
        - "{{ slm_agent_dir }}/slm/agent"
        - "{{ slm_agent_data_dir }}"

    - name: Install Python dependencies
      pip:
        name: "{{ slm_agent_python_packages }}"
        state: present
        executable: pip3

    - name: Deploy agent __init__.py (slm package)
      copy:
        content: |
          # AutoBot - AI-Powered Automation Platform
          # Copyright (c) 2025 mrveiss
          '''SLM Package.'''
        dest: "{{ slm_agent_dir }}/slm/__init__.py"
        owner: "{{ slm_agent_user }}"
        group: "{{ slm_agent_group }}"
        mode: '0644'

    - name: Deploy agent __init__.py (agent module)
      copy:
        content: |
          # AutoBot - AI-Powered Automation Platform
          # Copyright (c) 2025 mrveiss
          '''SLM Agent Module.'''
          from .agent import SLMAgent
          __all__ = ["SLMAgent"]
        dest: "{{ slm_agent_dir }}/slm/agent/__init__.py"
        owner: "{{ slm_agent_user }}"
        group: "{{ slm_agent_group }}"
        mode: '0644'

    - name: Deploy agent.py
      copy:
        src: "{{ playbook_dir }}/../roles/slm-agent/files/slm/agent/agent.py"
        dest: "{{ slm_agent_dir }}/slm/agent/agent.py"
        owner: "{{ slm_agent_user }}"
        group: "{{ slm_agent_group }}"
        mode: '0644'
      when: false  # Skip - use inline content instead

    - name: Deploy agent.py (inline)
      copy:
        content: |
          #!/usr/bin/env python3
          # AutoBot - AI-Powered Automation Platform
          # Copyright (c) 2025 mrveiss
          '''SLM Node Agent - Lightweight heartbeat agent.'''

          import logging
          import os
          import platform
          import signal
          import sys
          import time

          import psutil
          import requests
          import urllib3
          import yaml

          # Suppress InsecureRequestWarning for self-signed certs
          urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

          logging.basicConfig(
              level=logging.INFO,
              format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
          )
          logger = logging.getLogger("slm-agent")


          class SLMAgent:
              '''SLM Node Agent.'''

              def __init__(self, config_path: str = "/opt/autobot/config.yaml"):
                  self.running = False
                  self.config = self._load_config(config_path)

              def _load_config(self, path: str) -> dict:
                  if os.path.exists(path):
                      with open(path, encoding="utf-8") as f:
                          return yaml.safe_load(f)
                  return {
                      "node_id": os.environ.get("SLM_NODE_ID", "unknown"),
                      "admin_url": os.environ.get("SLM_ADMIN_URL", "http://127.0.0.1:8000"),
                      "heartbeat_interval": int(os.environ.get("SLM_HEARTBEAT_INTERVAL", "30")),
                  }

              def collect_health(self) -> dict:
                  return {
                      "cpu_percent": psutil.cpu_percent(interval=1),
                      "memory_percent": psutil.virtual_memory().percent,
                      "disk_percent": psutil.disk_usage("/").percent,
                      "agent_version": "1.0.0",
                      "os_info": f"{platform.system()} {platform.release()}",
                  }

              def send_heartbeat(self) -> bool:
                  try:
                      health = self.collect_health()
                      url = f"{self.config['admin_url']}/api/nodes/{self.config['node_id']}/heartbeat"
                      # verify=False for self-signed certs on nginx proxy
                      response = requests.post(url, json=health, timeout=10, verify=False)
                      response.raise_for_status()
                      logger.debug("Heartbeat sent successfully")
                      return True
                  except Exception as e:
                      logger.error("Heartbeat failed: %s", e)
                      return False

              def run(self):
                  self.running = True
                  signal.signal(signal.SIGTERM, lambda *_: setattr(self, "running", False))
                  signal.signal(signal.SIGINT, lambda *_: setattr(self, "running", False))

                  logger.info("SLM Agent starting - Node: %s", self.config["node_id"])
                  logger.info("Admin URL: %s", self.config["admin_url"])
                  logger.info("Heartbeat interval: %ds", self.config["heartbeat_interval"])

                  while self.running:
                      self.send_heartbeat()
                      time.sleep(self.config["heartbeat_interval"])

                  logger.info("SLM Agent stopped")


          if __name__ == "__main__":
              agent = SLMAgent()
              agent.run()
        dest: "{{ slm_agent_dir }}/slm/agent/agent.py"
        owner: "{{ slm_agent_user }}"
        group: "{{ slm_agent_group }}"
        mode: '0755'

    - name: Deploy agent configuration
      copy:
        content: |
          # SLM Agent Configuration
          node_id: "{{ slm_node_id }}"
          admin_url: "{{ slm_admin_url }}"
          heartbeat_interval: {{ slm_heartbeat_interval | default(30) }}
        dest: "{{ slm_agent_dir }}/config.yaml"
        owner: "{{ slm_agent_user }}"
        group: "{{ slm_agent_group }}"
        mode: '0640'

    - name: Deploy systemd service
      copy:
        content: |
          [Unit]
          Description=AutoBot SLM Agent
          After=network.target

          [Service]
          Type=simple
          User={{ slm_agent_user }}
          Group={{ slm_agent_group }}
          WorkingDirectory={{ slm_agent_dir }}
          ExecStart=/usr/bin/python3 -m slm.agent.agent
          Restart=always
          RestartSec=10
          Environment=PYTHONPATH={{ slm_agent_dir }}

          [Install]
          WantedBy=multi-user.target
        dest: /etc/systemd/system/autobot-agent.service
        owner: root
        group: root
        mode: '0644'
      notify: Restart agent

    - name: Enable and start agent service
      systemd:
        name: autobot-agent
        enabled: yes
        state: started
        daemon_reload: yes

  handlers:
    - name: Restart agent
      systemd:
        name: autobot-agent
        state: restarted
        daemon_reload: yes
"""
        # Substitute the SLM public key placeholder
        playbook_content = playbook_content.replace(
            "__SLM_PUBKEY_PLACEHOLDER__", slm_pubkey
        )
        path.write_text(playbook_content, encoding="utf-8")
        logger.info("Created enrollment playbook: %s", path)


deployment_service = DeploymentService()
