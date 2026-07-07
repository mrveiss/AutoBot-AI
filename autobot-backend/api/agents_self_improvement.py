# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Self-Improvement API (Issue #930)

Endpoints for accessing task outcome history, learned strategies,
and resetting learning state per agent/task type.
"""

import os
from typing import Any, List

from fastapi import APIRouter, Depends, Query

from api.schemas_agent import (
    FailurePatternRecord,
    KnowledgeImportResponse,
    LearnedKnowledgeExport,
    LearnedKnowledgeImport,
    LearnedStrategyResponse,
    ResetLearningResponse,
    TaskOutcomeResponse,
)
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Default confidence floor for exporting a failure pattern (governance review).
_DEFAULT_MIN_CONFIDENCE = float(os.environ.get("AUTOBOT_KNOWLEDGE_EXPORT_MIN_CONFIDENCE", "0.8"))
# Max chars kept from untrusted imported free-text (mirrors the learned-template
# sanitization limit in orchestration/orchestrator_prompts.py, #11060).
_IMPORT_TEXT_MAX = int(os.environ.get("AUTOBOT_LEARNED_TEMPLATE_MAX", "500"))
# Max failure patterns scanned for a knowledge export (explicit, not the store's
# default 50) so a governance export doesn't silently omit patterns (GH#11179).
_EXPORT_PATTERN_LIMIT = int(os.environ.get("AUTOBOT_KNOWLEDGE_EXPORT_PATTERN_LIMIT", "500"))

# Module-level singletons initialized on first use
_judge = None
_pattern_learner = None
_detector = None


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


def _get_detector():
    """Return singleton FailurePatternDetector instance."""
    global _detector
    if _detector is None:
        from services.failure_pattern_detector import FailurePatternDetector

        _detector = FailurePatternDetector()
    return _detector


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
    _user: Any = Depends(get_current_user),
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
    _user: Any = Depends(get_current_user),
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
    _admin: bool = Depends(check_admin_permission),
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


@router.get(
    "/{agent_id}/knowledge-export",
    response_model=LearnedKnowledgeExport,
    summary="Export an agent's learned strategy + high-confidence failure patterns",
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_agent_knowledge",
    error_code_prefix="AGENTS_SELF_IMPROVEMENT",
)
async def export_agent_knowledge(
    agent_id: str,
    task_type: str | None = Query(None, description="Task type to export"),
    min_confidence: float = Query(
        _DEFAULT_MIN_CONFIDENCE,
        ge=0.0,
        le=1.0,
        description="Only export failure patterns at or above this confidence",
    ),
    _user: Any = Depends(get_current_user),
) -> LearnedKnowledgeExport:
    """Render an agent's opaque learned knowledge as a human-reviewable document (GH#11151)."""
    learner = _get_learner()
    detector = _get_detector()
    effective_type = task_type or agent_id

    strategy = await learner.get_learned_strategy(effective_type)
    strategy_resp = LearnedStrategyResponse(**strategy.__dict__) if strategy else None

    patterns = await detector.list_known_patterns(limit=_EXPORT_PATTERN_LIMIT)
    high_conf = [
        FailurePatternRecord(
            pattern_id=p.pattern_id,
            causal_chain=p.causal_chain,
            occurrence_count=p.occurrence_count,
            successful_resolutions=p.successful_resolutions,
            resolution_success_rate=p.resolution_success_rate,
            confidence=p.confidence,
        )
        for p in patterns
        if p.confidence >= min_confidence
    ]
    return LearnedKnowledgeExport(
        task_type=effective_type,
        learned_strategy=strategy_resp,
        high_confidence_threshold=min_confidence,
        high_confidence_failure_patterns=high_conf,
    )


@router.post(
    "/{agent_id}/knowledge-import",
    response_model=KnowledgeImportResponse,
    summary="Import an operator-curated learned strategy",
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="import_agent_knowledge",
    error_code_prefix="AGENTS_SELF_IMPROVEMENT",
)
async def import_agent_knowledge(
    agent_id: str,
    payload: LearnedKnowledgeImport,
    _admin: bool = Depends(check_admin_permission),
) -> KnowledgeImportResponse:
    """Persist a reviewer-curated strategy, sanitizing untrusted free-text first (GH#11151)."""
    from agents.task_pattern_learner import LearnedStrategy, TaskPatternLearner
    from orchestration.orchestrator_prompts import _sanitize_injected

    learner = _get_learner()
    task_type = TaskPatternLearner.normalize_task_type(payload.task_type or agent_id)
    strategy = LearnedStrategy(
        task_type=task_type,
        # Imported free-text is untrusted — neutralize it exactly like a learned
        # template before it can ever reach the planner prompt (#11060).
        best_approach=_sanitize_injected(payload.best_approach, _IMPORT_TEXT_MAX),
        best_prompt_template=_sanitize_injected(payload.best_prompt_template, _IMPORT_TEXT_MAX),
        avg_score=payload.avg_score,
        sample_size=payload.sample_size,
        confidence=payload.confidence,
        failure_patterns=[_sanitize_injected(fp, _IMPORT_TEXT_MAX) for fp in payload.failure_patterns],
    )
    await learner.save_strategy(strategy)
    return KnowledgeImportResponse(
        success=True,
        message=f"Imported curated strategy for task type '{strategy.task_type}'",
        task_type=strategy.task_type,
    )
