# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Lightweight Celery schedule helpers (#11606).

Extracted from ``celery_app.py`` so the cron parser is importable without
the celery_app Redis/config dependency chain — the test conftest replaces
``celery_app`` in ``sys.modules`` with a stub app (issue #7766), which made
the helper unreachable in any stubbed test run.
"""

import logging

from celery.schedules import crontab

from autobot_shared.env_utils import env_int_clamped, env_str

logger = logging.getLogger(__name__)

#: Cron for the daily agent capability-manifest audit beat entry (#22271; registered in env_registry_llc).
CAPABILITY_AUDIT_SCHEDULE = env_str("AUTOBOT_CAPABILITY_AUDIT_SCHEDULE", "40 3 * * *")

#: Seconds between live service-health probes (#22273; registered in env_registry_llc).
SERVICE_HEALTH_PROBE_INTERVAL_SECONDS = env_int_clamped("AUTOBOT_SERVICE_HEALTH_PROBE_INTERVAL_SECONDS", 60, min_v=10)


def crontab_from_string(cron_expr: str) -> crontab:
    """Parse a 5-field cron string ('m h dom mon dow') into a Celery crontab.

    Falls back to a daily 03:00 UTC schedule if the expression is malformed,
    logging a warning so misconfiguration does not prevent Beat from starting.
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        logger.warning(
            "Invalid cron expression: %d fields, expected 5; falling back to '0 3 * * *'",
            len(parts),
        )
        parts = ["0", "3", "*", "*", "*"]
    minute, hour, day_of_month, month_of_year, day_of_week = parts
    return crontab(
        minute=minute,
        hour=hour,
        day_of_month=day_of_month,
        month_of_year=month_of_year,
        day_of_week=day_of_week,
    )
