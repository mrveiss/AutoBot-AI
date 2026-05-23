"""LLC services package.

LLCServiceBase provides the shared DI slot for the activity log service.
All concrete LLC service classes should inherit from this base so they
receive a typed ``activity_log`` reference at construction time.
"""

from typing import Optional

from .activity_log import LLCActivityLogService


class LLCServiceBase:
    """Base class for all LLC services.

    Subclasses receive the activity_log DI slot which is populated by the
    LLC DI container once GH#8216 lands. Until then, the slot is None and
    callers must guard with ``if self.activity_log``.
    """

    def __init__(self, activity_log: Optional[LLCActivityLogService] = None) -> None:
        self.activity_log = activity_log


__all__ = ["GoalService", "LLCActivityLogService", "LLCServiceBase"]

from .goal import GoalService  # noqa: E402 — after base class definition
