# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
System Tasks for AutoBot IaC Platform

Celery tasks for system management (RBAC, updates).

NOTE: These tasks have been moved to SLM server (#729).
Stubs maintained for backward compatibility with existing API endpoints.
"""

from autobot_shared.logging_manager import get_logger
from celery_app import celery_app
from utils.celery_reliability import (
    CELERY_MAX_RETRIES,
    CELERY_RETRY_BACKOFF_MAX,
    CELERY_TRANSIENT_ERRORS,
    DeadLetterTask,
    idempotent_task,
)

logger = get_logger(__name__)

# #11586: shared reliability options for the side-effectful queue tasks below
# (deployments queue). Transient errors back off with jitter; validation errors
# fail fast; terminal failures are parked by DeadLetterTask; duplicate broker
# deliveries are skipped by @idempotent_task.
_RELIABLE_TASK_OPTIONS = {
    "bind": True,
    "base": DeadLetterTask,
    "autoretry_for": CELERY_TRANSIENT_ERRORS,
    "retry_backoff": True,
    "retry_jitter": True,
    "retry_backoff_max": CELERY_RETRY_BACKOFF_MAX,
    "max_retries": CELERY_MAX_RETRIES,
}


@celery_app.task(name="tasks.initialize_rbac", **_RELIABLE_TASK_OPTIONS)
@idempotent_task
def initialize_rbac(self, create_admin: bool = False, admin_username: str = "admin"):
    """
    Initialize RBAC system using Ansible playbook (Issue #687).

    NOTE: Moved to SLM server (#729). This stub raises NotImplementedError.

    Args:
        self: Celery task instance (bound)
        create_admin: Whether to create initial admin user
        admin_username: Username for admin user if create_admin is True

    Returns:
        Dict with initialization results

    Raises:
        NotImplementedError: RBAC initialization moved to SLM server
    """
    logger.error("RBAC initialization called but moved to SLM server (#729)")
    raise NotImplementedError("RBAC initialization moved to SLM server. Use SLM API for RBAC setup (#729).")


@celery_app.task(name="tasks.run_system_update", **_RELIABLE_TASK_OPTIONS)
@idempotent_task
def run_system_update(
    self,
    update_type: str = "dependencies",
    target_groups: list = None,
    dry_run: bool = False,
    force_update: bool = False,
):
    """
    Run system updates via Ansible playbook (Issue #544).

    NOTE: Moved to SLM server (#729). This stub raises NotImplementedError.

    Args:
        self: Celery task instance (bound)
        update_type: Type of update ('dependencies' or 'system')
        target_groups: Host groups to update (None = all)
        dry_run: Preview mode without applying changes
        force_update: Skip version checks

    Returns:
        Dict with update results

    Raises:
        NotImplementedError: System updates moved to SLM server
    """
    logger.error("System update called but moved to SLM server (#729)")
    raise NotImplementedError("System updates moved to SLM server. Use SLM API for system updates (#729).")


@celery_app.task(name="tasks.check_available_updates", **_RELIABLE_TASK_OPTIONS)
@idempotent_task
def check_available_updates(self):
    """
    Check for available updates without applying them (Issue #544).

    NOTE: Moved to SLM server (#729). This stub raises NotImplementedError.

    Args:
        self: Celery task instance (bound)

    Returns:
        Dict with available updates

    Raises:
        NotImplementedError: Update checking moved to SLM server
    """
    logger.error("Check updates called but moved to SLM server (#729)")
    raise NotImplementedError("Update checking moved to SLM server. Use SLM API to check for updates (#729).")
