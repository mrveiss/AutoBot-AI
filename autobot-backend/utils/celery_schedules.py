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

logger = logging.getLogger(__name__)


def crontab_from_string(cron_expr: str) -> crontab:
    """Parse a 5-field cron string ('m h dom mon dow') into a Celery crontab.

    Falls back to a daily 03:00 UTC schedule if the expression is malformed,
    logging a warning so misconfiguration does not prevent Beat from starting.
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        logger.warning(
            "Invalid cron expression %r (expected 5 fields); falling back to '0 3 * * *'",
            cron_expr,
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
