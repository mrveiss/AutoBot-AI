# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Celery Tasks Package

Contains all Celery task definitions for AutoBot IaC platform.

Note: Deployment tasks removed - now managed by SLM server (#729)
System tasks (RBAC, updates) maintained as stubs for backward compatibility.
"""

from .system_tasks import (
    initialize_rbac,
    run_system_update,
    check_available_updates,
)

__all__ = [
    "initialize_rbac",
    "run_system_update",
    "check_available_updates",
]
