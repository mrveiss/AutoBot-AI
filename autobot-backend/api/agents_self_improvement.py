# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Self-Improvement API (Issue #930)

Endpoints for accessing task outcome history, learned strategies,
and resetting learning state per agent/task type.
"""

from typing import List

from fastapi import APIRouter, Query

from api.schemas_agent import (
    LearnedStrategyResponse,
    ResetLearningResponse,
    TaskOutcomeResponse,
)
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Module-level singletons initialized on first use
_judge = None
_pattern_learner = None


def _get_judge():
    """Return singleton TaskOutcomeJudge instance."""
    global _judge
    if _judge is None:
        from judges.task_outcome_judge import TaskOutcomeJudge

        _judge = TaskOutcomeJudge()
    return _judge


def _get_learner():
    """Return singleton TaskPatternLearner instance."""
    global _pattern_learner
    if _pattern_learner is None:
        from agents.task_pattern_learner import TaskPatternLearner

        _pattern_learner = TaskPatternLearner()
    return _pattern_learner


@router.get(
    "/{agent_id}/outcomes",
    response_model=List[TaskOutcomeResponse],
    summary="Get task outcome history for an agent",
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_agent_outcomes",
    error_code_prefix="AGENTS_SELF_IMPROVEMENT",
)
async def get_agent_outcomes(
    agent_id: str,
    task_type: str | None = Query(None, description="Filter by task type"),
    limit: int = Query(20, ge=1, le=100),
) -> List[TaskOutcomeResponse]:
    """Return recent task outcome records for an agent or task type."""
    judge = _get_judge()
    effective_type = task_type or agent_id
    outcomes = await judge.get_outcomes(effective_type, limit=limit)
    return [TaskOutcomeResponse(**o.__dict__) for o in outcomes]


@router.get(
    "/{agent_id}/learned-strategies",
    response_model=LearnedStrategyResponse | None,
    summary="Get learned strategy for an agent's task type",
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_learned_strategies",
    error_code_prefix="AGENTS_SELF_IMPROVEMENT",
)
async def get_learned_strategies(
    agent_id: str,
    task_type: str | None = Query(None, description="Task type to retrieve"),
) -> LearnedStrategyResponse | None:
    """Return the current learned best strategy for a given task type."""
    learner = _get_learner()
    effective_type = task_type or agent_id
    strategy = await learner.get_learned_strategy(effective_type)
    if not strategy:
        return None
    return LearnedStrategyResponse(**strategy.__dict__)


@router.post(
    "/{agent_id}/reset-learning",
    response_model=ResetLearningResponse,
    summary="Clear learned state for an agent",
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reset_agent_learning",
    error_code_prefix="AGENTS_SELF_IMPROVEMENT",
)
async def reset_agent_learning(
    agent_id: str,
    task_type: str | None = Query(None, description="Task type to reset"),
) -> ResetLearningResponse:
    """Clear all learned outcomes and strategies for an agent or task type."""
    judge = _get_judge()
    learner = _get_learner()
    effective_type = task_type or agent_id
    await judge.clear_outcomes(effective_type)
    await learner.clear_strategy(effective_type)
    return ResetLearningResponse(
        success=True,
        message=f"Learning state cleared for task type '{effective_type}'",
    )
