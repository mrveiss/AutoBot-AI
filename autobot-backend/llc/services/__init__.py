"""LLC services package.

LLCServiceBase provides the shared DI slot for the activity log service.
All concrete LLC service classes should inherit from this base so they
receive a typed ``activity_log`` reference at construction time.
"""

from .activity_log import LLCActivityLogService
from .approval import ApprovalService
from .base import LLCServiceBase
from .board import BoardService
from .budget import BudgetService
from .ceo_chat import CeoChatService
from .goal import GoalService
from .handoff import HandoffError, HandoffService
from .review_gate import (
    ReviewGatePolicyConflictError,
    ReviewGatePolicyNotFoundError,
    ReviewGatePolicyService,
)
from .routine_service import RoutineService
from .sprint_autoclose import SprintAutoCloseService
from .sprint_planning import SprintNotFound, SprintPlanningService
from .work_product_service import WorkProductService

__all__ = [
    "ApprovalService",
    "CeoChatService",
    "BoardService",
    "BudgetService",
    "GoalService",
    "HandoffError",
    "HandoffService",
    "LLCActivityLogService",
    "LLCServiceBase",
    "ReviewGatePolicyConflictError",
    "ReviewGatePolicyNotFoundError",
    "ReviewGatePolicyService",
    "RoutineService",
    "SprintAutoCloseService",
    "SprintNotFound",
    "SprintPlanningService",
    "WorkProductService",
]
