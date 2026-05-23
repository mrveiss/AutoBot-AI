# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLCServiceBase — shared DI slot for all LLC services."""

from typing import Optional


class LLCServiceBase:
    """Base class for all LLC services.

    Subclasses receive the activity_log DI slot which is populated by the
    LLC DI container once GH#8216 lands. Until then, the slot is None and
    callers must guard with ``if self.activity_log``.
    """

    def __init__(self, activity_log: Optional[object] = None) -> None:
        self.activity_log = activity_log
