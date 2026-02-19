# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Self-Improvement API (Issue #930)

Endpoints for accessing task outcome history, learned strategies,
and resetting learning state per agent/task type.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

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


class TaskOutcomeResponse(BaseModel):
    """Serialized task outcome record."""

    task_type: str
    goal: str
    output_summary: str
    strategy_used: str
    score: float
    rationale: str
    timestamp: str


class LearnedStrategyResponse(BaseModel):
    """Serialized learned strategy record."""

    task_type: str
    best_approach: str
    best_prompt_template: str
    avg_score: float
    sample_size: int
    confidence: float
    failure_patterns: List[str]
    timestamp: str


class ResetLearningResponse(BaseModel):
    """Response for reset-learning operation."""

    success: bool
    message: str


@router.get(
    "/{agent_id}/outcomes",
    response_model=List[TaskOutcomeResponse],
    summary="Get task outcome history for an agent",
)
async def get_agent_outcomes(
    agent_id: str,
    task_type: Optional[str] = Query(None, description="Filter by task type"),
    limit: int = Query(20, ge=1, le=100),
) -> List[TaskOutcomeResponse]:
    """Return recent task outcome records for an agent or task type."""
    judge = _get_judge()
    effective_type = task_type or agent_id
    outcomes = await judge.get_outcomes(effective_type, limit=limit)
    return [TaskOutcomeResponse(**o.__dict__) for o in outcomes]


@router.get(
    "/{agent_id}/learned-strategies",
    response_model=Optional[LearnedStrategyResponse],
    summary="Get learned strategy for an agent's task type",
)
async def get_learned_strategies(
    agent_id: str,
    task_type: Optional[str] = Query(None, description="Task type to retrieve"),
) -> Optional[LearnedStrategyResponse]:
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
async def reset_agent_learning(
    agent_id: str,
    task_type: Optional[str] = Query(None, description="Task type to reset"),
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
