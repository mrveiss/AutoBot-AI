"""LLC services package.

LLCServiceBase provides the shared DI slot for the activity log service.
All concrete LLC service classes should inherit from this base so they
receive a typed ``activity_log`` reference at construction time.
"""

from .activity_log import LLCActivityLogService
from .base import LLCServiceBase
from .budget import BudgetService
from .goal import GoalService

__all__ = ["BudgetService", "GoalService", "LLCActivityLogService", "LLCServiceBase"]
