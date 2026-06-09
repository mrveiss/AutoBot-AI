# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLCServiceBase — shared DI slot for all LLC services."""

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .activity_log import LLCActivityLogService


class LLCServiceBase:
    """Base class for all LLC services.

    Subclasses receive the activity_log DI slot which is populated by the
    LLC DI container once GH#8216 lands. Until then, the slot is None and
    callers must guard with ``if self.activity_log``.
    """

    def __init__(self, activity_log: "Optional[LLCActivityLogService]" = None) -> None:
        self.activity_log = activity_log
