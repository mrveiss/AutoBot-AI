# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Notification channel and event vocabularies -- enum-only, so codegen can load them (#19334).

Split out of ``notification_service`` (which pulls in aiohttp and Redis) so
``gen_frontend_types.py`` can generate the frontend unions from them in its slim environment.
``notification_service`` re-imports both names, so existing imports keep working.
"""

from enum import Enum


class NotificationChannel(str, Enum):
    """Supported delivery channels for notifications."""

    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    IN_APP = "in_app"
    TELEGRAM = "telegram"  # MVA-2075


class NotificationEvent(str, Enum):
    """Workflow lifecycle events that can trigger notifications."""

    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    STEP_FAILED = "step_failed"
    APPROVAL_NEEDED = "approval_needed"
    SERVICE_FAILED = "service_failed"
