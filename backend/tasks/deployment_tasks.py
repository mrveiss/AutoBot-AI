# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Deployment Tasks for AutoBot IaC Platform

Celery tasks for asynchronous Ansible playbook execution with real-time progress.
"""

import asyncio
import logging

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
