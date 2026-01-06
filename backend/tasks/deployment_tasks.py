# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Deployment Tasks for AutoBot IaC Platform

Celery tasks for asynchronous Ansible playbook execution with real-time progress.
"""

import asyncio
import json
import logging
import subprocess

from backend.type_defs.common import Metadata

from backend.celery_app import celery_app
from backend.services.ansible_executor import AnsibleExecutor

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for loggable deployment event types
_DEPLOYMENT_LOGGABLE_EVENTS = frozenset({"runner_on_ok", "runner_on_failed", "runner_on_unreachable"})


def _create_deployment_event_callback(task, ip_address: str, role: str):
    """Create event callback for real-time deployment monitoring (Issue #398: extracted).

    Args:
        task: Celery task instance for state updates
        ip_address: Host IP address
        role: Ansible role being deployed

    Returns:
        Callback function for Ansible event handling
    """
    def event_callback(event):
        """Publish Ansible events to Celery state for real-time monitoring."""
        event_type = event.get("event", "unknown")
        task.update_state(
            state="PROGRESS",
            meta={
                "event_type": event_type,
                "event_data": event.get("event_data", {}),
                "host": ip_address,
                "role": role,
                "stdout": event.get("stdout", ""),
            },
        )
        if event_type in _DEPLOYMENT_LOGGABLE_EVENTS:
            logger.info("Deployment event [%s]: %s", ip_address, event_type)
    return event_callback


def _build_ansible_inventory(role: str, ip_address: str, ssh_user: str, ssh_key_path: str, ssh_port: int) -> dict:
    """Build Ansible inventory dictionary (Issue #398: extracted).

    Args:
        role: Ansible role name
        ip_address: Target host IP
        ssh_user: SSH username
        ssh_key_path: Path to SSH private key
        ssh_port: SSH port number

    Returns:
        Ansible inventory dictionary
    """
    return {
        role: {
            "hosts": [ip_address],
            "vars": {
                "ansible_user": ssh_user,
                "ansible_ssh_private_key_file": ssh_key_path,
                "ansible_port": ssh_port,
                "ansible_python_interpreter": "/usr/bin/python3",
            },
        }
    }


def _build_deployment_result(status: str, ip_address: str, role: str, runner=None, error: str = None) -> dict:
    """Build deployment result dictionary (Issue #398: extracted).

    Args:
        status: 'success' or 'failed'
        ip_address: Host IP address
        role: Deployed role
        runner: Ansible runner object (for failure details)
        error: Optional error message

    Returns:
        Deployment result dictionary
    """
    if status == "success":
        return {
            "status": "success",
            "host": ip_address,
            "role": role,
            "message": f"Successfully deployed {role} to {ip_address}",
        }
    else:
        result = {
            "status": "failed",
            "host": ip_address,
            "role": role,
        }
        if error:
            result["error"] = error
        if runner:
            result["error"] = f"Ansible playbook failed with return code {runner.rc}"
            result["return_code"] = runner.rc
        return result


@celery_app.task(bind=True, name="tasks.deploy_host")
def deploy_host(self, host_config: Metadata, force_redeploy: bool = False):
    """
    Deploy or redeploy a host using Ansible

    Args:
        self: Celery task instance (bound)
        host_config: Host configuration dictionary with keys:
            - ip_address: Host IP address
            - role: Ansible role to deploy
            - ssh_user: SSH username (default: 'autobot')
            - ssh_key_path: Path to SSH private key
            - ssh_port: SSH port (default: 22)
        force_redeploy: Force redeployment even if already deployed

    Returns:
        Dict with deployment results
    """
    # Run in asyncio event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(
            _deploy_host_async(self, host_config, force_redeploy)
        )
        return result
    except Exception as e:
        logger.exception("Deployment task failed: %s", e)
        raise
    finally:
        loop.close()


async def _deploy_host_async(task, host_config: Metadata, force_redeploy: bool):
    """Async implementation of host deployment (Issue #398: refactored to use helpers).

    Args:
        task: Celery task instance
        host_config: Host configuration dictionary
        force_redeploy: Force redeployment flag

    Returns:
        Dict with deployment results
    """
    executor = AnsibleExecutor()

    ip_address = host_config.get("ip_address")
    role = host_config.get("role")
    ssh_user = host_config.get("ssh_user", "autobot")
    ssh_key_path = host_config.get("ssh_key_path", "~/.ssh/autobot_key")
    ssh_port = host_config.get("ssh_port", 22)

    if not ip_address or not role:
        raise ValueError("host_config must include 'ip_address' and 'role'")

    logger.info("Starting deployment for host %s with role %s", ip_address, role)

    # Issue #398: Use extracted helpers
    event_callback = _create_deployment_event_callback(task, ip_address, role)
    inventory = _build_ansible_inventory(role, ip_address, ssh_user, ssh_key_path, ssh_port)
    extra_vars = {"role_name": role, "target_host": ip_address, "force_redeploy": force_redeploy}

    try:
        playbook_path = await executor.get_playbook_path("deploy_role.yml")
        runner = await executor.run_playbook(
            playbook_path=playbook_path,
            inventory=inventory,
            extra_vars=extra_vars,
            event_callback=event_callback,
            run_id=f"deploy_{role}_{ip_address}",
        )

        if runner.status == "successful":
            logger.info("Deployment successful: %s (role: %s)", ip_address, role)
            return _build_deployment_result("success", ip_address, role)
        else:
            logger.error("Deployment failed: %s (role: %s)", ip_address, role)
            logger.error("Return code: %s", runner.rc)
            return _build_deployment_result("failed", ip_address, role, runner=runner)

    except Exception as e:
        logger.exception("Deployment exception for %s: %s", ip_address, e)
        raise


@celery_app.task(name="tasks.provision_ssh_key")
def provision_ssh_key(host_ip: str, password: str, ssh_user: str = "autobot"):
    """
    Provision SSH key from initial password authentication

    This task uses password authentication to copy SSH public key to remote host,
    enabling password-less authentication for future operations.

    Args:
        host_ip: IP address of host
        password: Initial password for authentication
        ssh_user: SSH username (default: 'autobot')

    Returns:
        Dict with provisioning results
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(
            _provision_ssh_key_async(host_ip, password, ssh_user)
        )
        return result
    except Exception as e:
        logger.exception("SSH key provisioning failed: %s", e)
        raise
    finally:
        loop.close()


async def _provision_ssh_key_async(host_ip: str, password: str, ssh_user: str):
    """
    Async implementation of SSH key provisioning

    Args:
        host_ip: IP address of host
        password: Initial password for authentication
        ssh_user: SSH username

    Returns:
        Dict with provisioning results
    """
    executor = AnsibleExecutor()

    logger.info("Starting SSH key provisioning for %s@%s", ssh_user, host_ip)

    # Generate inventory with password authentication
    inventory = {
        "provision_hosts": {
            "hosts": [host_ip],
            "vars": {
                "ansible_user": ssh_user,
                "ansible_password": password,
                "ansible_become_password": password,
                "ansible_python_interpreter": "/usr/bin/python3",
            },
        }
    }

    # Extra variables for playbook
    extra_vars = {"target_host": host_ip, "ssh_user": ssh_user}

    try:
        playbook_path = await executor.get_playbook_path("provision_host.yml")

        runner = await executor.run_playbook(
            playbook_path=playbook_path,
            inventory=inventory,
            extra_vars=extra_vars,
            run_id=f"provision_{host_ip}",
        )

        if runner.status == "successful":
            logger.info("SSH key provisioning successful: %s", host_ip)
            return {
                "status": "success",
                "host": host_ip,
                "message": f"Successfully provisioned SSH key for {ssh_user}@{host_ip}",
            }
        else:
            logger.error("SSH key provisioning failed: %s", host_ip)
            return {
                "status": "failed",
                "host": host_ip,
                "error": f"Provisioning playbook failed with return code {runner.rc}",
                "return_code": runner.rc,
            }

    except Exception as e:
        logger.exception("SSH key provisioning exception for %s: %s", host_ip, e)
        raise


# Issue #687: Module-level frozenset for loggable RBAC event types
_RBAC_LOGGABLE_EVENTS = frozenset({"runner_on_ok", "runner_on_failed", "runner_on_unreachable"})


def _create_rbac_event_callback(task):
    """Create event callback for RBAC initialization monitoring (Issue #687).

    Args:
        task: Celery task instance for state updates

    Returns:
        Callback function for Ansible event handling
    """
    def event_callback(event):
        """Publish Ansible events to Celery state for real-time monitoring."""
        event_type = event.get("event", "unknown")
        event_data = event.get("event_data", {})
        task_name = event_data.get("task", "")
        task.update_state(
            state="PROGRESS",
            meta={
                "event_type": event_type,
                "task_name": task_name,
                "stdout": event.get("stdout", ""),
                "step": "initializing",
            },
        )
        if event_type in _RBAC_LOGGABLE_EVENTS:
            logger.info("RBAC init event: %s - %s", event_type, task_name)
    return event_callback


@celery_app.task(bind=True, name="tasks.initialize_rbac")
def initialize_rbac(self, create_admin: bool = False, admin_username: str = "admin"):
    """
    Initialize RBAC system using Ansible playbook (Issue #687).

    Runs setup-rbac.yml to create:
    - System permissions
    - System roles
    - Role-permission mappings
    - Optional admin user

    Args:
        self: Celery task instance (bound)
        create_admin: Whether to create initial admin user
        admin_username: Username for admin user if create_admin is True

    Returns:
        Dict with initialization results
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(
            _initialize_rbac_async(self, create_admin, admin_username)
        )
        return result
    except Exception as e:
        logger.exception("RBAC initialization task failed: %s", e)
        raise
    finally:
        loop.close()


async def _initialize_rbac_async(task, create_admin: bool, admin_username: str):
    """
    Async implementation of RBAC initialization (Issue #687).

    Args:
        task: Celery task instance
        create_admin: Whether to create admin user
        admin_username: Admin username

    Returns:
        Dict with initialization results
    """
    executor = AnsibleExecutor()

    logger.info("Starting RBAC initialization (create_admin=%s)", create_admin)

    # Inventory for localhost (RBAC runs on backend host)
    inventory = {
        "backend": {
            "hosts": ["localhost"],
            "vars": {
                "ansible_connection": "local",
                "ansible_python_interpreter": "/usr/bin/python3",
            },
        }
    }

    # Extra variables for playbook
    extra_vars = {
        "create_admin": create_admin,
        "admin_username": admin_username,
    }

    try:
        event_callback = _create_rbac_event_callback(task)
        playbook_path = await executor.get_playbook_path("setup-rbac.yml")

        runner = await executor.run_playbook(
            playbook_path=playbook_path,
            inventory=inventory,
            extra_vars=extra_vars,
            event_callback=event_callback,
            run_id="rbac_init",
        )

        if runner.status == "successful":
            logger.info("RBAC initialization successful")
            return {
                "status": "success",
                "message": "RBAC system initialized successfully",
                "create_admin": create_admin,
                "admin_username": admin_username if create_admin else None,
            }
        else:
            logger.error("RBAC initialization failed")
            return {
                "status": "failed",
                "error": f"RBAC playbook failed with return code {runner.rc}",
                "return_code": runner.rc,
            }

    except FileNotFoundError as e:
        logger.error("RBAC playbook not found: %s", e)
        return {
            "status": "failed",
            "error": "RBAC playbook not found. Ensure setup-rbac.yml exists.",
        }
    except Exception as e:
        logger.exception("RBAC initialization exception: %s", e)
        raise


# Issue #544: Module-level frozenset for loggable system update event types
_SYSTEM_UPDATE_LOGGABLE_EVENTS = frozenset({"runner_on_ok", "runner_on_failed", "runner_on_unreachable"})


def _create_system_update_event_callback(task, update_type: str):
    """Create event callback for system update monitoring (Issue #544).

    Args:
        task: Celery task instance for state updates
        update_type: Type of update ('dependencies' or 'system')

    Returns:
        Callback function for Ansible event handling
    """
    def event_callback(event):
        """Publish Ansible events to Celery state for real-time monitoring."""
        event_type = event.get("event", "unknown")
        event_data = event.get("event_data", {})
        task_name = event_data.get("task", "")
        host = event_data.get("host", "localhost")
        task.update_state(
            state="PROGRESS",
            meta={
                "event_type": event_type,
                "task_name": task_name,
                "host": host,
                "stdout": event.get("stdout", ""),
                "update_type": update_type,
                "step": "updating",
            },
        )
        if event_type in _SYSTEM_UPDATE_LOGGABLE_EVENTS:
            logger.info("System update event [%s]: %s - %s", update_type, event_type, task_name)
    return event_callback


@celery_app.task(bind=True, name="tasks.run_system_update")
def run_system_update(
    self,
    update_type: str = "dependencies",
    target_groups: list | None = None,
    dry_run: bool = False,
    force_update: bool = False,
):
    """
    Run system updates using Ansible playbook (Issue #544).

    Runs patch-dependencies.yml or patch-system-packages.yml to update:
    - Python dependencies (CVE fixes)
    - System packages (apt updates)

    Args:
        self: Celery task instance (bound)
        update_type: 'dependencies' (Python pip) or 'system' (apt packages)
        target_groups: List of host groups to update (None = all)
        dry_run: Preview changes without applying
        force_update: Skip version checks

    Returns:
        Dict with update results
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(
            _run_system_update_async(self, update_type, target_groups, dry_run, force_update)
        )
        return result
    except Exception as e:
        logger.exception("System update task failed: %s", e)
        raise
    finally:
        loop.close()


def _select_update_playbook(update_type: str) -> tuple[str | None, dict | None]:
    """
    Select the appropriate playbook based on update type.

    Issue #665: Extracted from _run_system_update_async to reduce function length.

    Args:
        update_type: Type of update ('dependencies' or 'system')

    Returns:
        Tuple of (playbook_name, error_dict) - one will be None
    """
    if update_type == "dependencies":
        return "patch-dependencies.yml", None
    elif update_type == "system":
        return "patch-system-packages.yml", None
    else:
        error = {
            "status": "failed",
            "error": f"Invalid update type: {update_type}. Use 'dependencies' or 'system'.",
        }
        return None, error


def _build_update_inventory() -> dict:
    """
    Build Ansible inventory for system updates.

    Issue #665: Extracted from _run_system_update_async to reduce function length.

    Returns:
        Ansible inventory dictionary for localhost
    """
    return {
        "backend": {
            "hosts": ["localhost"],
            "vars": {
                "ansible_connection": "local",
                "ansible_python_interpreter": "/usr/bin/python3",
            },
        }
    }


def _build_update_extra_vars(
    dry_run: bool,
    force_update: bool,
    target_groups: list | None
) -> dict:
    """
    Build extra variables for system update playbook.

    Issue #665: Extracted from _run_system_update_async to reduce function length.

    Args:
        dry_run: Preview mode flag
        force_update: Force update flag
        target_groups: Target host groups (optional)

    Returns:
        Dictionary of extra variables for Ansible playbook
    """
    extra_vars = {
        "dry_run": dry_run,
        "force_update": force_update,
        "auto_confirm": True,  # Skip interactive prompts when run via API
        "rollback_on_failure": True,
        "health_check_enabled": True,
    }

    if target_groups:
        extra_vars["target_groups"] = target_groups

    return extra_vars


def _build_update_result(
    success: bool,
    update_type: str,
    dry_run: bool,
    runner=None,
    playbook_name: str = None
) -> dict:
    """
    Build result dictionary for system update operation.

    Issue #665: Extracted from _run_system_update_async to reduce function length.

    Args:
        success: Whether update was successful
        update_type: Type of update performed
        dry_run: Whether this was a dry run
        runner: Ansible runner object (for failures)
        playbook_name: Name of playbook (for file not found errors)

    Returns:
        Result dictionary with status and details
    """
    if success:
        logger.info("System update successful (type=%s)", update_type)
        return {
            "status": "success",
            "message": f"System {update_type} update completed successfully",
            "update_type": update_type,
            "dry_run": dry_run,
        }
    else:
        logger.error("System update failed (type=%s)", update_type)
        return {
            "status": "failed",
            "error": f"Update playbook failed with return code {runner.rc}",
            "return_code": runner.rc,
            "update_type": update_type,
        }


async def _run_system_update_async(
    task,
    update_type: str,
    target_groups: list | None,
    dry_run: bool,
    force_update: bool,
):
    """
    Async implementation of system updates (Issue #544).

    Args:
        task: Celery task instance
        update_type: Type of update
        target_groups: Target host groups
        dry_run: Preview mode
        force_update: Force update flag

    Returns:
        Dict with update results
    """
    executor = AnsibleExecutor()

    logger.info(
        "Starting system update (type=%s, dry_run=%s, force=%s, targets=%s)",
        update_type, dry_run, force_update, target_groups
    )

    # Select playbook based on update type (Issue #665: extracted)
    playbook_name, error = _select_update_playbook(update_type)
    if error:
        return error

    # Build inventory and extra vars (Issue #665: extracted)
    inventory = _build_update_inventory()
    extra_vars = _build_update_extra_vars(dry_run, force_update, target_groups)

    try:
        event_callback = _create_system_update_event_callback(task, update_type)
        playbook_path = await executor.get_playbook_path(playbook_name)

        runner = await executor.run_playbook(
            playbook_path=playbook_path,
            inventory=inventory,
            extra_vars=extra_vars,
            event_callback=event_callback,
            run_id=f"system_update_{update_type}",
        )

        # Build result based on runner status (Issue #665: extracted)
        return _build_update_result(
            success=(runner.status == "successful"),
            update_type=update_type,
            dry_run=dry_run,
            runner=runner
        )

    except FileNotFoundError as e:
        logger.error("Update playbook not found: %s", e)
        return {
            "status": "failed",
            "error": f"Update playbook not found: {playbook_name}",
        }
    except Exception as e:
        logger.exception("System update exception: %s", e)
        raise


@celery_app.task(bind=True, name="tasks.check_available_updates")
def check_available_updates(self):
    """
    Check for available updates without applying them (Issue #544).

    Runs pip-audit and apt check to identify available updates.

    Returns:
        Dict with available updates
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(_check_available_updates_async(self))
        return result
    except Exception as e:
        logger.exception("Update check task failed: %s", e)
        raise
    finally:
        loop.close()


async def _check_available_updates_async(task):
    """
    Async implementation of update check (Issue #544).

    Args:
        task: Celery task instance

    Returns:
        Dict with available updates
    """
    logger.info("Checking for available updates")

    task.update_state(
        state="PROGRESS",
        meta={"step": "checking_python", "message": "Checking Python dependencies..."},
    )

    python_updates = []
    system_updates = []

    # Check Python dependencies with pip-audit
    try:
        result = subprocess.run(
            ["pip-audit", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
        )
        if result.returncode == 0:
            audit_data = json.loads(result.stdout)
            python_updates = audit_data if isinstance(audit_data, list) else []
    except FileNotFoundError:
        logger.warning("pip-audit not installed, skipping Python audit")
    except subprocess.TimeoutExpired:
        logger.warning("pip-audit timed out")
    except Exception as e:
        logger.warning("pip-audit failed: %s", e)

    task.update_state(
        state="PROGRESS",
        meta={"step": "checking_system", "message": "Checking system packages..."},
    )

    # Check system packages with apt
    try:
        result = subprocess.run(
            ["apt", "list", "--upgradable"],
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            # Skip header line "Listing..."
            for line in lines[1:]:
                if line.strip():
                    system_updates.append(line.strip())
    except FileNotFoundError:
        logger.warning("apt not available (not Debian-based)")
    except subprocess.TimeoutExpired:
        logger.warning("apt check timed out")
    except Exception as e:
        logger.warning("apt check failed: %s", e)

    return {
        "status": "success",
        "python_updates": python_updates,
        "python_update_count": len(python_updates),
        "system_updates": system_updates,
        "system_update_count": len(system_updates),
        "message": f"Found {len(python_updates)} Python and {len(system_updates)} system updates",
    }
