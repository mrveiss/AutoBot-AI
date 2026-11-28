# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Scheduled agent capability-manifest audit (#22271)."""

from celery_app import celery_app
from orchestration.capability_audit import run_capability_audit


@celery_app.task(name="tasks.run_capability_audit")
def run_capability_audit_task() -> dict:
    """Run the manifest audit; the report is logged by the audit and returned as the task result."""
    return run_capability_audit()
