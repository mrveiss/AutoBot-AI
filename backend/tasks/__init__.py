# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Celery Tasks Package

Contains all Celery task definitions for AutoBot IaC platform.
"""

from .deployment_tasks import deploy_host, provision_ssh_key

__all__ = ["deploy_host", "provision_ssh_key"]
