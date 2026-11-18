# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLCServiceBase — shared DI slot for all LLC services."""

from typing import Optional

from .activity_log import LLCActivityLogService


class LLCServiceBase:
    """Base class for all LLC services.

    Every service owns a real :class:`LLCActivityLogService` (#20101): a caller may pass
    another (a test double), but a service cannot be built without one, so an audit write
    is never skipped for lack of a log and no call site guards on ``self.activity_log``.
    """

    def __init__(self, activity_log: Optional[LLCActivityLogService] = None) -> None:
        self.activity_log: LLCActivityLogService = activity_log if activity_log is not None else LLCActivityLogService()
