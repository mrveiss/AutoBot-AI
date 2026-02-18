# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
System Tasks for AutoBot IaC Platform

Celery tasks for system management (RBAC, updates).

NOTE: These tasks have been moved to SLM server (#729).
Stubs maintained for backward compatibility with existing API endpoints.
"""

import logging

from backend.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.initialize_rbac")
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
    raise NotImplementedError(
        "RBAC initialization moved to SLM server. Use SLM API for RBAC setup (#729)."
    )


@celery_app.task(bind=True, name="tasks.run_system_update")
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
    raise NotImplementedError(
        "System updates moved to SLM server. Use SLM API for system updates (#729)."
    )


@celery_app.task(bind=True, name="tasks.check_available_updates")
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
    raise NotImplementedError(
        "Update checking moved to SLM server. Use SLM API to check for updates (#729)."
    )
