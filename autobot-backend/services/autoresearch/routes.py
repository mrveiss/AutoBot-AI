# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoResearch REST API

Issue #2597: Endpoints for managing experiments, viewing results, and stats.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth_middleware import check_admin_permission
from constants.error_constants import ERR_EXPERIMENT_NOT_FOUND, ERR_SESSION_NOT_FOUND
from constants.ttl_constants import TTL_24_HOURS

from .config import AutoResearchConfig
from .knowledge_synthesizer import KnowledgeSynthesizer
from .models import Experiment, ExperimentState, HyperParams
from .prompt_optimizer import PromptOptimizer, PromptOptTarget
from .runner import ExperimentRunner
from .store import ExperimentStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["autoresearch"])


class CreateExperimentRequest(BaseModel):
    hypothesis: str = Field(default="", max_length=1000)
    description: str = Field(default="", max_length=5000)
    code_diff: str = Field(default="", max_length=50000)
    tags: List[str] = Field(default_factory=list, max_length=20)
    hyperparams: Optional[Dict] = None


class SetBaselineRequest(BaseModel):
    val_bpb: float


class StartOptimizationRequest(BaseModel):
    agent_name: str = Field(..., max_length=100)
    max_rounds: int = Field(default=3, ge=1, le=10)


class SubmitScoreRequest(BaseModel):
    score: int = Field(..., ge=0, le=10)
    comment: str = Field(default="", max_length=1000)


class ApprovalDecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(approved|rejected)$")


class SynthesizeRequest(BaseModel):
    session_id: str = Field(..., max_length=100)


# Lazy-initialized singletons
_runner: Optional[ExperimentRunner] = None
_store: Optional[ExperimentStore] = None
_optimizer: Optional[PromptOptimizer] = None
_synthesizer: Optional[KnowledgeSynthesizer] = None


def _get_store(request: Request) -> ExperimentStore:
    """Get or create the ExperimentStore singleton."""
    global _store
    app_store = getattr(request.app.state, "autoresearch_store", None)
    if app_store is not None:
        return app_store
    if _store is None:
        _store = ExperimentStore(AutoResearchConfig())
    request.app.state.autoresearch_store = _store
    return _store


def _get_runner(request: Request) -> ExperimentRunner:
    """Get or create the ExperimentRunner singleton."""
    global _runner
    app_runner = getattr(request.app.state, "autoresearch_runner", None)
    if app_runner is not None:
        return app_runner
    if _runner is None:
        store = _get_store(request)
        _runner = ExperimentRunner(store=store)
    request.app.state.autoresearch_runner = _runner
    return _runner


@router.get("/experiments")
async def list_experiments(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    state: Optional[str] = Query(default=None),
    _admin: bool = Depends(check_admin_permission),
):
    """List experiments, most recent first."""
    store = _get_store(request)
    exp_state = None
    if state:
        try:
            exp_state = ExperimentState(state)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid state: {state}. "
                f"Valid: {[s.value for s in ExperimentState]}",
            )

    experiments = await store.list_experiments(
        limit=limit, offset=offset, state=exp_state
    )
    return {
        "experiments": [e.to_dict() for e in experiments],
        "count": len(experiments),
        "offset": offset,
        "limit": limit,
    }


@router.get("/experiments/stats")
async def get_stats(
    request: Request,
    _admin: bool = Depends(check_admin_permission),
):
    """Get aggregate experiment statistics."""
    store = _get_store(request)
    stats = await store.get_stats()
    return stats.to_dict()


@router.get("/experiments/{experiment_id}")
async def get_experiment(
    request: Request,
    experiment_id: str,
    _admin: bool = Depends(check_admin_permission),
):
    """Get a single experiment by ID."""
    store = _get_store(request)
    experiment = await store.get_experiment(experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail=ERR_EXPERIMENT_NOT_FOUND)
    return experiment.to_dict()


@router.post("/experiments")
async def create_experiment(
    request: Request,
    body: CreateExperimentRequest,
    background_tasks: BackgroundTasks,
    _admin: bool = Depends(check_admin_permission),
):
    """Create and queue a new experiment (non-blocking).

    Returns the experiment ID immediately. Poll GET /experiments/{id}
    for status updates.
    """
    runner = _get_runner(request)
    if runner.is_running:
        raise HTTPException(
            status_code=409,
            detail="An experiment is already running",
        )

    experiment = Experiment(
        hypothesis=body.hypothesis,
        description=body.description,
        code_diff=body.code_diff,
        tags=body.tags,
    )
    if body.hyperparams:
        experiment.hyperparams = HyperParams.from_dict(body.hyperparams)

    store = _get_store(request)
    await store.save_experiment(experiment)
    background_tasks.add_task(runner.run_experiment, experiment)

    return {"id": experiment.id, "state": experiment.state.value}


@router.post("/experiments/baseline")
async def set_baseline(
    request: Request,
    body: SetBaselineRequest,
    _admin: bool = Depends(check_admin_permission),
):
    """Set the baseline val_bpb for improvement comparison."""
    store = _get_store(request)
    await store.set_baseline(body.val_bpb)
    return {"baseline_val_bpb": body.val_bpb}


@router.get("/status")
async def get_status(
    request: Request,
    _admin: bool = Depends(check_admin_permission),
):
    """Get current runner status."""
    runner = _get_runner(request)
    store = _get_store(request)
    baseline = await store.get_baseline()
    return {
        "running": runner.is_running,
        "baseline_val_bpb": baseline,
    }


@router.post("/cancel")
async def cancel_experiment(
    request: Request,
    _admin: bool = Depends(check_admin_permission),
):
    """Cancel the currently running experiment."""
    runner = _get_runner(request)
    if not runner.is_running:
        raise HTTPException(
            status_code=409,
            detail="No experiment is currently running",
        )
    await runner.cancel()
    return {"status": "cancelled"}


def _get_optimizer(request: Request) -> PromptOptimizer:
    """Get or create the PromptOptimizer singleton."""
    global _optimizer
    app_opt = getattr(request.app.state, "autoresearch_optimizer", None)
    if app_opt is not None:
        return app_opt
    if _optimizer is None:
        from services.llm_service import get_llm_service

        _optimizer = PromptOptimizer(
            scorers={},  # scorers registered at runtime
            llm_service=get_llm_service(),
        )
    request.app.state.autoresearch_optimizer = _optimizer
    return _optimizer


def _get_synthesizer(request: Request) -> KnowledgeSynthesizer:
    """Get or create the KnowledgeSynthesizer singleton."""
    global _synthesizer
    app_synth = getattr(request.app.state, "autoresearch_synthesizer", None)
    if app_synth is not None:
        return app_synth
    if _synthesizer is None:
        from services.llm_service import get_llm_service

        store = _get_store(request)
        _synthesizer = KnowledgeSynthesizer(
            store=store,
            llm_service=get_llm_service(),
        )
    request.app.state.autoresearch_synthesizer = _synthesizer
    return _synthesizer


# --- Prompt Optimizer Endpoints ---


@router.get("/prompt-optimizer/status")
async def get_optimizer_status(
    request: Request,
    _admin: bool = Depends(check_admin_permission),
):
    """Get current prompt optimization session status."""
    optimizer = _get_optimizer(request)
    session = optimizer.current_session
    if session is None:
        return {"running": False, "session": None}
    return {"running": True, "session": session.to_dict()}


@router.post("/prompt-optimizer/start")
async def start_optimization(
    request: Request,
    body: StartOptimizationRequest,
    background_tasks: BackgroundTasks,
    _admin: bool = Depends(check_admin_permission),
):
    """Start prompt optimization for a registered target."""
    optimizer = _get_optimizer(request)
    if optimizer.current_session is not None:
        raise HTTPException(status_code=409, detail="Optimization already running")

    # For now, only autoresearch_hypothesis is a valid target
    if body.agent_name != "autoresearch_hypothesis":
        raise HTTPException(
            status_code=400,
            detail=f"Unknown agent target: {body.agent_name}",
        )

    target = PromptOptTarget(
        agent_name=body.agent_name,
        current_prompt="",  # loaded from agent at runtime
        scorer_chain=["val_bpb"],
    )

    async def _benchmark(prompt: str) -> str:
        return prompt  # placeholder — real benchmark set up by agent

    background_tasks.add_task(optimizer.optimize, target, _benchmark, body.max_rounds)
    return {"status": "started", "agent_name": body.agent_name}


@router.post("/prompt-optimizer/cancel")
async def cancel_optimization(
    request: Request,
    _admin: bool = Depends(check_admin_permission),
):
    """Cancel running optimization."""
    optimizer = _get_optimizer(request)
    if optimizer.current_session is None:
        raise HTTPException(status_code=409, detail="No optimization running")
    optimizer.cancel()
    return {"status": "cancelling"}


@router.get("/prompt-optimizer/variants/{session_id}")
async def get_variants(
    request: Request,
    session_id: str,
    _admin: bool = Depends(check_admin_permission),
):
    """List prompt variants for an optimization session."""
    import json as _json

    from autobot_shared.redis_client import get_redis_client

    redis = get_redis_client(async_client=True, database="main")
    key = f"autoresearch:prompt_opt:session:{session_id}"
    raw = await redis.get(key)
    if raw is None:
        raise HTTPException(status_code=404, detail=ERR_SESSION_NOT_FOUND)
    data = _json.loads(raw)
    return {"variants": data.get("all_variants", [])}


_UUID_PATTERN = re.compile(r"^[a-f0-9-]{1,64}$")


@router.post("/prompt-optimizer/variants/{variant_id}/score")
async def submit_variant_score(
    request: Request,
    variant_id: str,
    body: SubmitScoreRequest,
    session_id: str = Query(..., min_length=1, max_length=64),
    _admin: bool = Depends(check_admin_permission),
):
    """Submit a human score for a prompt variant."""
    import json as _json

    from autobot_shared.redis_client import get_redis_client

    # Validate key components to prevent Redis key injection
    if not _UUID_PATTERN.match(session_id) or not _UUID_PATTERN.match(variant_id):
        raise HTTPException(
            status_code=400, detail="Invalid session_id or variant_id format"
        )

    redis = get_redis_client(async_client=True, database="main")
    key = f"autoresearch:prompt_review:{session_id}:{variant_id}"
    notify_key = f"autoresearch:prompt_review:notify:{session_id}:{variant_id}"
    await redis.set(
        key,
        _json.dumps({"score": body.score, "comment": body.comment}),
        ex=TTL_24_HOURS,
    )
    # Push a notification so HumanReviewScorer.score() unblocks immediately
    # instead of busy-polling.  The notify key is short-lived — the scorer
    # consumes it via BLPOP, and we set a 24-hour TTL as a safety net in case
    # the scorer is not currently waiting.
    await redis.lpush(notify_key, "ready")
    await redis.expire(notify_key, TTL_24_HOURS)
    return {"status": "scored", "variant_id": variant_id, "score": body.score}


# --- Approval Endpoints ---


@router.get("/approvals/pending")
async def list_pending_approvals(
    request: Request,
    _admin: bool = Depends(check_admin_permission),
):
    """List pending approval requests."""
    import json as _json

    from autobot_shared.redis_client import get_redis_client

    redis = get_redis_client(async_client=True, database="main")
    approvals = []
    async for key in redis.scan_iter("autoresearch:approval:pending:*"):
        raw = await redis.get(key)
        if raw:
            data = _json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
            key_str = key if isinstance(key, str) else key.decode("utf-8")
            parts = key_str.split(":")
            if len(parts) >= 5:
                status_key = f"autoresearch:approval:status:{parts[3]}:{parts[4]}"
                status = await redis.get(status_key)
                status_str = (
                    (status.decode("utf-8") if isinstance(status, bytes) else status)
                    if status
                    else "unknown"
                )
                if status_str == "pending":
                    data["status"] = "pending"
                    approvals.append(data)
    return {"approvals": approvals}


@router.post("/approvals/{session_id}/{experiment_id}")
async def submit_approval_decision(
    request: Request,
    session_id: str,
    experiment_id: str,
    body: ApprovalDecisionRequest,
    _admin: bool = Depends(check_admin_permission),
):
    """Submit approve/reject decision for an experiment."""
    from autobot_shared.redis_client import get_redis_client

    redis = get_redis_client(async_client=True, database="main")
    status_key = f"autoresearch:approval:status:{session_id}:{experiment_id}"
    current = await redis.get(status_key)
    if current is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    await redis.set(status_key, body.decision, ex=TTL_24_HOURS)
    return {
        "session_id": session_id,
        "experiment_id": experiment_id,
        "decision": body.decision,
    }


# --- Knowledge Insights Endpoints ---


@router.get("/insights")
async def list_insights(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    _admin: bool = Depends(check_admin_permission),
):
    """List distilled experiment insights."""
    synthesizer = _get_synthesizer(request)
    insights = await synthesizer.query_insights("*", limit=limit)
    filtered = [i for i in insights if i.confidence >= min_confidence]
    return {"insights": [i.to_dict() for i in filtered], "count": len(filtered)}


@router.get("/insights/search")
async def search_insights(
    request: Request,
    q: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(default=5, ge=1, le=50),
    _admin: bool = Depends(check_admin_permission),
):
    """Semantic search over experiment insights."""
    synthesizer = _get_synthesizer(request)
    insights = await synthesizer.query_insights(q, limit=limit)
    return {"insights": [i.to_dict() for i in insights], "query": q}


@router.post("/insights/synthesize")
async def trigger_synthesis(
    request: Request,
    body: SynthesizeRequest,
    _admin: bool = Depends(check_admin_permission),
):
    """Manually trigger insight synthesis for a session."""
    synthesizer = _get_synthesizer(request)
    insights = await synthesizer.synthesize_session(body.session_id)
    return {
        "session_id": body.session_id,
        "insights_generated": len(insights),
        "insights": [i.to_dict() for i in insights],
    }
