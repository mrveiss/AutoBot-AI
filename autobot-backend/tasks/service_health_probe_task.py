# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Scheduled live service-health probe (#22273)."""

from autobot_shared.worker_loop import run_in_worker_loop
from celery_app import celery_app
from services.service_health_probe import probe_and_store


@celery_app.task(name="tasks.probe_service_health")
def probe_service_health() -> dict:
    """Probe every registered service and store the snapshot; returns the snapshot."""
    return run_in_worker_loop(probe_and_store())
