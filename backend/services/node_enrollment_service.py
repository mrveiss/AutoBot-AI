# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Node Enrollment Service - Issue #695

Handles oVirt-style node enrollment using Ansible playbooks.
Provides idempotent operations for:
- Node provisioning with role-specific configuration
- PKI certificate deployment
- Service configuration and startup
- Node status monitoring

Integration Points:
- ansible/playbooks/enroll-node.yml - Main enrollment playbook
- ansible/roles/{role}/ - Role-specific configurations
- src/pki/distributor.py - Certificate distribution
"""

import asyncio
import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class EnrollmentStep(Enum):
    """Enrollment process steps."""

    VALIDATE_SSH = 0
    CHECK_OS = 1
    INSTALL_DEPENDENCIES = 2
    DEPLOY_CERTIFICATES = 3
    CONFIGURE_SERVICES = 4
    REGISTER_NODE = 5
    START_MONITORING = 6


class EnrollmentStatus(Enum):
    """Overall enrollment status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class EnrollmentProgress:
    """Tracks enrollment progress for a node."""

    node_id: str
    task_id: str
    status: EnrollmentStatus = EnrollmentStatus.PENDING
    current_step: EnrollmentStep = EnrollmentStep.VALIDATE_SSH
    step_message: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    ansible_output: List[str] = field(default_factory=list)


@dataclass
class NodeCredentials:
    """Node authentication credentials."""

    auth_method: str  # 'password' or 'pki'
    username: str
    password: Optional[str] = None
    ssh_key: Optional[str] = None
    ssh_key_path: Optional[str] = None


def _find_project_root() -> Path:
    """Find the project root directory containing .env file."""
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".env").exists():
            return parent
    return Path("/home/kali/Desktop/AutoBot")


PROJECT_ROOT = _find_project_root()
ANSIBLE_DIR = PROJECT_ROOT / "ansible"


class NodeEnrollmentService:
    """
    Service for managing node enrollment with Ansible.

    Provides oVirt-style host enrollment flow:
    1. Validate SSH connectivity
    2. Check OS compatibility
    3. Run role-specific Ansible playbook
    4. Deploy PKI certificates
    5. Configure services
    6. Register in SSOT config
    """

    def __init__(self):
        """Initialize the enrollment service."""
        self.ansible_dir = ANSIBLE_DIR
        self.playbooks_dir = self.ansible_dir / "playbooks"
        self._active_enrollments: Dict[str, EnrollmentProgress] = {}
        self._progress_callbacks: Dict[str, List[Callable]] = {}

    async def enroll_node(
        self,
        node_id: str,
        hostname: str,
        ip_address: str,
        credentials: NodeCredentials,
        role: str,
        task_id: Optional[str] = None,
        progress_callback: Optional[Callable[[EnrollmentProgress], None]] = None,
    ) -> EnrollmentProgress:
        """
        Enroll a new node using Ansible.

        Args:
            node_id: Unique node identifier
            hostname: Node hostname
            ip_address: Node IP address
            credentials: Authentication credentials
            role: Node role (frontend, npu-worker, redis, etc.)
            task_id: Optional task ID for tracking
            progress_callback: Optional callback for progress updates

        Returns:
            EnrollmentProgress with final status
        """
        import uuid

        if task_id is None:
            task_id = str(uuid.uuid4())

        progress = EnrollmentProgress(
            node_id=node_id,
            task_id=task_id,
            status=EnrollmentStatus.RUNNING,
            started_at=datetime.now().isoformat(),
        )

        self._active_enrollments[task_id] = progress

        if progress_callback:
            if task_id not in self._progress_callbacks:
                self._progress_callbacks[task_id] = []
            self._progress_callbacks[task_id].append(progress_callback)

        try:
            # Step 1: Validate SSH connectivity
            await self._update_progress(progress, EnrollmentStep.VALIDATE_SSH, "Validating SSH connectivity")
            ssh_valid = await self._validate_ssh(ip_address, credentials)
            if not ssh_valid:
                raise RuntimeError("SSH connectivity validation failed")

            # Step 2: Check OS compatibility
            await self._update_progress(progress, EnrollmentStep.CHECK_OS, "Checking OS compatibility")
            os_info = await self._check_os_compatibility(ip_address, credentials)
            if not os_info.get("compatible"):
                raise RuntimeError(f"Incompatible OS: {os_info.get('os', 'Unknown')}")

            # Step 3: Run Ansible provisioning playbook
            await self._update_progress(progress, EnrollmentStep.INSTALL_DEPENDENCIES, "Installing dependencies via Ansible")
            provision_result = await self._run_ansible_provision(
                hostname=hostname,
                ip_address=ip_address,
                credentials=credentials,
                role=role,
                progress=progress,
            )
            if not provision_result["success"]:
                raise RuntimeError(f"Ansible provisioning failed: {provision_result.get('error')}")

            # Step 4: Deploy PKI certificates
            await self._update_progress(progress, EnrollmentStep.DEPLOY_CERTIFICATES, "Deploying PKI certificates")
            pki_result = await self._deploy_pki_certificates(hostname, ip_address)
            if not pki_result["success"]:
                logger.warning("PKI deployment skipped or failed: %s", pki_result.get("error"))

            # Step 5: Configure services
            await self._update_progress(progress, EnrollmentStep.CONFIGURE_SERVICES, f"Configuring services for role: {role}")
            service_result = await self._configure_services(
                hostname=hostname,
                ip_address=ip_address,
                credentials=credentials,
                role=role,
            )
            if not service_result["success"]:
                raise RuntimeError(f"Service configuration failed: {service_result.get('error')}")

            # Step 6: Register node
            await self._update_progress(progress, EnrollmentStep.REGISTER_NODE, "Registering node in configuration")
            await self._register_node(hostname, ip_address, role)

            # Step 7: Start monitoring
            await self._update_progress(progress, EnrollmentStep.START_MONITORING, "Starting node monitoring")
            await self._start_monitoring(node_id, ip_address)

            # Enrollment complete
            progress.status = EnrollmentStatus.COMPLETED
            progress.completed_at = datetime.now().isoformat()
            progress.step_message = "Enrollment completed successfully"

            logger.info("Node enrollment completed: %s (%s)", hostname, ip_address)

        except Exception as e:
            logger.error("Node enrollment failed for %s: %s", hostname, e)
            progress.status = EnrollmentStatus.FAILED
            progress.error = str(e)
            progress.completed_at = datetime.now().isoformat()

        finally:
            await self._notify_progress(progress)

        return progress

    async def _update_progress(
        self,
        progress: EnrollmentProgress,
        step: EnrollmentStep,
        message: str,
    ) -> None:
        """Update and notify enrollment progress."""
        progress.current_step = step
        progress.step_message = message
        await self._notify_progress(progress)

    async def _notify_progress(self, progress: EnrollmentProgress) -> None:
        """Notify all registered callbacks of progress update."""
        callbacks = self._progress_callbacks.get(progress.task_id, [])
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(progress)
                else:
                    callback(progress)
            except Exception as e:
                logger.error("Progress callback error: %s", e)

    async def _validate_ssh(self, ip_address: str, credentials: NodeCredentials) -> bool:
        """Validate SSH connectivity to the node."""
        try:
            import asyncssh

            connect_kwargs = {
                "host": ip_address,
                "username": credentials.username,
                "known_hosts": None,
                "connect_timeout": 10,
            }

            if credentials.auth_method == "password" and credentials.password:
                connect_kwargs["password"] = credentials.password
            elif credentials.ssh_key:
                connect_kwargs["client_keys"] = [asyncssh.import_private_key(credentials.ssh_key)]
            elif credentials.ssh_key_path:
                connect_kwargs["client_keys"] = [credentials.ssh_key_path]
            else:
                # Use default key
                default_key = os.path.expanduser("~/.ssh/autobot_key")
                if os.path.exists(default_key):
                    connect_kwargs["client_keys"] = [default_key]

            async with asyncssh.connect(**connect_kwargs) as conn:
                result = await conn.run("echo 'SSH OK'", check=True)
                return result.exit_status == 0

        except Exception as e:
            logger.error("SSH validation failed: %s", e)
            return False

    async def _check_os_compatibility(
        self,
        ip_address: str,
        credentials: NodeCredentials,
    ) -> Dict[str, Any]:
        """Check if the target OS is compatible (Debian/Ubuntu based)."""
        try:
            import asyncssh

            connect_kwargs = {
                "host": ip_address,
                "username": credentials.username,
                "known_hosts": None,
                "connect_timeout": 10,
            }

            if credentials.auth_method == "password" and credentials.password:
                connect_kwargs["password"] = credentials.password
            else:
                default_key = os.path.expanduser("~/.ssh/autobot_key")
                if os.path.exists(default_key):
                    connect_kwargs["client_keys"] = [default_key]

            async with asyncssh.connect(**connect_kwargs) as conn:
                # Get OS info
                result = await conn.run("cat /etc/os-release", check=False)
                os_info = result.stdout if result.exit_status == 0 else ""

                # Check for Debian/Ubuntu
                compatible = "debian" in os_info.lower() or "ubuntu" in os_info.lower()

                # Extract pretty name
                os_name = "Unknown"
                for line in os_info.split("\n"):
                    if line.startswith("PRETTY_NAME="):
                        os_name = line.split("=", 1)[1].strip('"')
                        break

                return {
                    "compatible": compatible,
                    "os": os_name,
                    "raw": os_info,
                }

        except Exception as e:
            logger.error("OS compatibility check failed: %s", e)
            return {"compatible": False, "os": "Unknown", "error": str(e)}

    async def _run_ansible_provision(
        self,
        hostname: str,
        ip_address: str,
        credentials: NodeCredentials,
        role: str,
        progress: EnrollmentProgress,
    ) -> Dict[str, Any]:
        """Run Ansible provisioning playbook for the node."""
        # Create temporary inventory
        inventory_content = self._generate_inventory(hostname, ip_address, credentials, role)

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yml",
            prefix="inventory_",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(inventory_content)
            inventory_path = f.name

        try:
            # Determine playbook based on role
            playbook_path = self.playbooks_dir / "provision_host.yml"
            if not playbook_path.exists():
                logger.warning("provision_host.yml not found, using deploy-base.yml")
                playbook_path = self.playbooks_dir / "deploy-base.yml"

            if not playbook_path.exists():
                return {
                    "success": False,
                    "error": "No suitable playbook found",
                }

            # Build Ansible command
            cmd = [
                "ansible-playbook",
                str(playbook_path),
                "-i", inventory_path,
                "-e", f"target_host={hostname}",
                "-e", f"vm_role={role}",
                "--timeout", "60",
            ]

            # Add password if using password auth
            if credentials.auth_method == "password" and credentials.password:
                cmd.extend(["--extra-vars", f"ansible_password={credentials.password}"])

            logger.info("Running Ansible: %s", " ".join(cmd[:5]) + "...")

            # Run Ansible
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(self.ansible_dir),
            )

            # Stream output
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                line_str = line.decode().strip()
                progress.ansible_output.append(line_str)
                logger.debug("Ansible: %s", line_str)

            await process.wait()

            if process.returncode == 0:
                return {"success": True}
            else:
                return {
                    "success": False,
                    "error": f"Ansible exited with code {process.returncode}",
                    "output": progress.ansible_output[-10:],
                }

        except Exception as e:
            logger.error("Ansible provisioning error: %s", e)
            return {"success": False, "error": str(e)}

        finally:
            # Clean up temporary inventory
            try:
                os.unlink(inventory_path)
            except OSError:
                pass

    def _generate_inventory(
        self,
        hostname: str,
        ip_address: str,
        credentials: NodeCredentials,
        role: str,
    ) -> str:
        """Generate dynamic Ansible inventory for a single host."""
        # Map role to Ansible group
        role_group_mapping = {
            "frontend": "frontend",
            "npu-worker": "npu_workers",
            "redis": "database",
            "ai-stack": "ai_stack",
            "browser": "browser",
            "custom": "custom",
        }
        group = role_group_mapping.get(role, "custom")

        inventory = {
            "all": {
                "vars": {
                    "ansible_user": credentials.username,
                    "ansible_python_interpreter": "/usr/bin/python3",
                },
                "children": {
                    group: {
                        "hosts": {
                            hostname: {
                                "ansible_host": ip_address,
                            }
                        }
                    }
                }
            }
        }

        # Add authentication
        if credentials.auth_method == "password":
            inventory["all"]["vars"]["ansible_ssh_pass"] = credentials.password
        else:
            ssh_key_path = credentials.ssh_key_path or os.path.expanduser("~/.ssh/autobot_key")
            inventory["all"]["vars"]["ansible_ssh_private_key_file"] = ssh_key_path

        # Convert to YAML
        import yaml

        return yaml.dump(inventory, default_flow_style=False)

    async def _deploy_pki_certificates(
        self,
        hostname: str,
        ip_address: str,
    ) -> Dict[str, Any]:
        """Deploy PKI certificates to the node using the PKI distributor."""
        try:
            from src.pki.config import TLSConfig
            from src.pki.distributor import CertificateDistributor

            config = TLSConfig()

            if not config.is_enabled:
                return {"success": True, "message": "TLS disabled, skipping PKI deployment"}

            distributor = CertificateDistributor(config)

            # Create VM info for this host
            vm_info = config.get_vm_cert_info(hostname, ip_address)

            # Distribute certificates
            success = await distributor._distribute_to_vm(vm_info)

            return {"success": success}

        except ImportError:
            logger.warning("PKI module not available")
            return {"success": True, "message": "PKI module not available"}
        except Exception as e:
            logger.error("PKI deployment failed: %s", e)
            return {"success": False, "error": str(e)}

    async def _configure_services(
        self,
        hostname: str,
        ip_address: str,
        credentials: NodeCredentials,
        role: str,
    ) -> Dict[str, Any]:
        """Configure services on the node for the assigned role."""
        # This would typically run the role-specific service configuration
        # For now, we assume Ansible provisioning handles most of this

        try:
            # Run service management playbook if available
            service_playbook = self.playbooks_dir / "manage_services.yml"

            if service_playbook.exists():
                inventory_content = self._generate_inventory(hostname, ip_address, credentials, role)

                with tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=".yml",
                    prefix="inventory_",
                    delete=False,
                    encoding="utf-8",
                ) as f:
                    f.write(inventory_content)
                    inventory_path = f.name

                try:
                    cmd = [
                        "ansible-playbook",
                        str(service_playbook),
                        "-i", inventory_path,
                        "-e", f"target_host={hostname}",
                        "-e", "service_action=start",
                    ]

                    process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=str(self.ansible_dir),
                    )

                    stdout, stderr = await process.communicate()

                    if process.returncode == 0:
                        return {"success": True}
                    else:
                        return {
                            "success": False,
                            "error": stderr.decode() if stderr else "Unknown error",
                        }

                finally:
                    try:
                        os.unlink(inventory_path)
                    except OSError:
                        pass

            return {"success": True, "message": "No service management playbook"}

        except Exception as e:
            logger.error("Service configuration failed: %s", e)
            return {"success": False, "error": str(e)}

    async def _register_node(self, hostname: str, ip_address: str, role: str) -> None:
        """Register the node in the SSOT configuration."""
        # Update VM_DEFINITIONS dynamically
        # In production, this would update a database or config file

        try:
            from src.pki.config import VM_DEFINITIONS

            # Add to definitions if not present
            if hostname not in VM_DEFINITIONS:
                VM_DEFINITIONS[hostname] = ip_address
                logger.info("Registered node %s (%s) with role %s", hostname, ip_address, role)

        except Exception as e:
            logger.error("Node registration failed: %s", e)

    async def _start_monitoring(self, node_id: str, ip_address: str) -> None:
        """Start monitoring for the enrolled node."""
        # This would integrate with the monitoring system
        # For now, just log the action

        logger.info("Started monitoring for node %s at %s", node_id, ip_address)

    def get_enrollment_progress(self, task_id: str) -> Optional[EnrollmentProgress]:
        """Get the progress of an enrollment task."""
        return self._active_enrollments.get(task_id)

    def cancel_enrollment(self, task_id: str) -> bool:
        """Cancel an ongoing enrollment (if possible)."""
        progress = self._active_enrollments.get(task_id)
        if progress and progress.status == EnrollmentStatus.RUNNING:
            progress.status = EnrollmentStatus.FAILED
            progress.error = "Enrollment cancelled by user"
            progress.completed_at = datetime.now().isoformat()
            return True
        return False


# Singleton instance
_service_instance: Optional[NodeEnrollmentService] = None


def get_node_enrollment_service() -> NodeEnrollmentService:
    """Get or create the singleton NodeEnrollmentService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = NodeEnrollmentService()
    return _service_instance
