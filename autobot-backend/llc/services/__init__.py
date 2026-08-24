# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""LLC services package.

LLCServiceBase provides the shared DI slot for the activity log service.
All concrete LLC service classes should inherit from this base so they
receive a typed ``activity_log`` reference at construction time.

Lazy-loaded (PEP 562, #13057): importing this package used to eagerly import
all 13 concrete service modules, so importing even one unrelated
``llc.services.<module>`` submodule (Python always initializes a parent
package before its submodule) paid for all of them — including two
(``handoff.py`` -> ``kb/handoff_brief.py``, ``sprint_autoclose.py`` ->
``kb/sprint_summarizer.py``) that import ``llm_shared.types`` and trigger
PyTorch/CUDA probing at import time, and several that hit live Redis via
module-level state. Each name in ``__all__`` now resolves lazily via
``__getattr__`` on first access, so a caller pays only for the service it
actually imports. Existing ``from llc.services import X`` call sites keep
working unchanged — none exist in this repo today (every call site already
imports the concrete submodule directly), but the re-export contract is
preserved regardless.
"""

from typing import Any

__all__ = [
    "AgentBudgetState",
    "AgentBudgetTracker",
    "ApprovalService",
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
    "PortabilityService",
    "SprintNotFound",
    "SprintPlanningService",
    "WorkProductService",
]

# name -> submodule it lives in, so __getattr__ imports exactly one module.
_LAZY_ATTRS: dict[str, str] = {
    "AgentBudgetState": "agent_budget_tracker",
    "AgentBudgetTracker": "agent_budget_tracker",
    "ApprovalService": "approval",
    "BoardService": "board",
    "BudgetService": "budget",
    "GoalService": "goal",
    "HandoffError": "handoff",
    "HandoffService": "handoff",
    "LLCActivityLogService": "activity_log",
    "LLCServiceBase": "base",
    "ReviewGatePolicyConflictError": "review_gate",
    "ReviewGatePolicyNotFoundError": "review_gate",
    "ReviewGatePolicyService": "review_gate",
    "RoutineService": "routine_service",
    "SprintAutoCloseService": "sprint_autoclose",
    "PortabilityService": "portability",
    "SprintNotFound": "sprint_planning",
    "SprintPlanningService": "sprint_planning",
    "WorkProductService": "work_product_service",
}


def __getattr__(name: str) -> Any:
    """PEP 562 lazy attribute resolution — one submodule import per name."""
    module_name = _LAZY_ATTRS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    import importlib

    module = importlib.import_module(f".{module_name}", __name__)
    value = getattr(module, name)
    globals()[name] = value  # cache: subsequent access skips __getattr__ entirely
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
