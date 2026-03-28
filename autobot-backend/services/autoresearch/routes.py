# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoResearch REST API

Issue #2597: Endpoints for managing experiments, viewing results, and stats.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth_middleware import check_admin_permission

from .config import AutoResearchConfig
from .models import Experiment, ExperimentState, HyperParams
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


# Lazy-initialized singleton
_runner: Optional[ExperimentRunner] = None
_store: Optional[ExperimentStore] = None


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
        raise HTTPException(status_code=404, detail="Experiment not found")
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
