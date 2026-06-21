# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
LLM benchmark runs API (Issue #9024).

Persists saved multi-model comparison runs and their per-response star ratings
so operators can compare quality/cost across providers over time.  The actual
fan-out execution stays in POST /api/chat/compare (Issue #4414); this module
only stores the *outcome* of a run plus the human quality signal.

Endpoints (all per-user scoped, frontend contract = plain JSON, no envelope):
  GET    /api/benchmarks/prompt-sets   -> built-in benchmark prompt sets
  POST   /api/benchmarks/runs          -> save a run (201)
  GET    /api/benchmarks/runs          -> list runs (filters: model, prompt_type, since)
  GET    /api/benchmarks/runs/{id}     -> single run
  DELETE /api/benchmarks/runs/{id}     -> 204

Storage: a Redis hash in the sessions database, one field per run id:
  `benchmark:runs:user:{user_id}`

Each field value is a JSON-encoded run document.
"""

import json
from datetime import datetime, timezone
from typing import List, Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from auth_middleware import get_current_user
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

router = APIRouter(tags=["benchmarks"])

REDIS_DB = "sessions"


# ---------------------------------------------------------------------------
# Built-in benchmark prompt sets (Issue #9024)
# ---------------------------------------------------------------------------

BUILTIN_PROMPT_SETS: List[dict] = [
    {
        "id": "rag",
        "name": "Retrieval & grounding",
        "promptType": "rag",
        "prompts": [
            "Given the context, list only the facts that directly answer the question. "
            "If the context is insufficient, say so explicitly.",
            "Summarize the key claims in the provided passage and cite the sentence each claim came from.",
        ],
    },
    {
        "id": "code",
        "name": "Code generation",
        "promptType": "code",
        "prompts": [
            "Write a Python function that returns the nth Fibonacci number iteratively, with a docstring.",
            "Given this failing test, explain the bug and provide a corrected implementation.",
        ],
    },
    {
        "id": "summarization",
        "name": "Summarization",
        "promptType": "summarization",
        "prompts": [
            "Summarize the following text in three bullet points, preserving every numeric figure.",
            "Rewrite the passage as a one-sentence executive summary.",
        ],
    },
    {
        "id": "reasoning",
        "name": "Reasoning",
        "promptType": "reasoning",
        "prompts": [
            "A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. "
            "How much does the ball cost? Show your reasoning.",
            "If all Bloops are Razzies and all Razzies are Lazzies, are all Bloops definitely Lazzies? Explain.",
        ],
    },
]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BenchmarkResult(BaseModel):
    """One model's outcome within a benchmark run."""

    model: str = Field(..., description="'provider/model' spec")
    content: str = Field(default="", description="Model response text")
    rating: int = Field(default=0, ge=0, le=5, description="User star rating 0-5 (0 = unrated)")
    costUsd: float = Field(default=0.0, ge=0, description="Estimated cost in USD for this response")
    latencyMs: int = Field(default=0, ge=0, description="Response latency in milliseconds")
    error: Optional[str] = Field(default=None, description="Error message if the model failed")


class BenchmarkRunCreate(BaseModel):
    """Request body for saving a benchmark run."""

    prompt: str = Field(..., description="The prompt that was compared")
    promptType: str = Field(default="custom", description="rag | code | summarization | reasoning | custom")
    promptSetId: Optional[str] = Field(default=None, description="Source prompt-set id, if any")
    results: List[BenchmarkResult] = Field(default_factory=list)


def _user_hash_key(user_id: str) -> str:
    return f"benchmark:runs:user:{user_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _require_redis(user_id: str):
    redis = await get_async_redis_client(database=REDIS_DB)
    if redis is None:
        logger.warning("benchmarks: Redis unavailable for user %s", user_id)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    return redis


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/benchmarks/prompt-sets")
async def list_prompt_sets(
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Return the built-in benchmark prompt sets (Issue #9024)."""
    return JSONResponse(content=BUILTIN_PROMPT_SETS)


@router.post("/benchmarks/runs", status_code=201)
async def create_run(
    payload: BenchmarkRunCreate,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Persist a benchmark run for the authenticated user (Issue #9024)."""
    user_id = current_user.get("user_id") or current_user.get("username", "")
    redis = await _require_redis(user_id)

    run = {
        "id": str(uuid4()),
        "prompt": payload.prompt,
        "promptType": payload.promptType,
        "promptSetId": payload.promptSetId,
        "results": [r.model_dump() for r in payload.results],
        "models": [r.model for r in payload.results],
        "createdAt": _now_iso(),
    }
    await redis.hset(_user_hash_key(user_id), run["id"], json.dumps(run))
    logger.info("Saved benchmark run %s for user %s", run["id"], user_id)
    return JSONResponse(content=run, status_code=201)


def _matches_filters(run: dict, model: Optional[str], prompt_type: Optional[str], since: Optional[str]) -> bool:
    """Apply list filters to a single run document."""
    if model and model not in run.get("models", []):
        return False
    if prompt_type and run.get("promptType") != prompt_type:
        return False
    if since and run.get("createdAt", "") < since:
        return False
    return True


@router.get("/benchmarks/runs")
async def list_runs(
    model: Optional[str] = Query(default=None, description="Filter by 'provider/model' present in the run"),
    prompt_type: Optional[str] = Query(default=None, description="Filter by promptType"),
    since: Optional[str] = Query(default=None, description="ISO timestamp — only runs at/after this time"),
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """List saved runs for the user, newest first, with optional filters (Issue #9024)."""
    user_id = current_user.get("user_id") or current_user.get("username", "")
    redis = await _require_redis(user_id)

    raw = await redis.hgetall(_user_hash_key(user_id))
    runs: List[dict] = []
    for value in raw.values():
        try:
            run = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Skipping corrupt benchmark run for user %s", user_id)
            continue
        if _matches_filters(run, model, prompt_type, since):
            runs.append(run)

    runs.sort(key=lambda r: r.get("createdAt", ""), reverse=True)
    return JSONResponse(content=runs)


@router.get("/benchmarks/runs/{run_id}")
async def get_run(
    run_id: str,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Return a single saved run owned by the user (Issue #9024)."""
    user_id = current_user.get("user_id") or current_user.get("username", "")
    redis = await _require_redis(user_id)

    raw = await redis.hget(_user_hash_key(user_id), run_id)
    if raw is None:
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    try:
        return JSONResponse(content=json.loads(raw))
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=500, detail="Benchmark run data corrupted")


@router.delete("/benchmarks/runs/{run_id}", status_code=204)
async def delete_run(
    run_id: str,
    current_user: dict = Depends(get_current_user),
) -> Response:
    """Delete a saved run owned by the user (Issue #9024)."""
    user_id = current_user.get("user_id") or current_user.get("username", "")
    redis = await _require_redis(user_id)

    deleted = await redis.hdel(_user_hash_key(user_id), run_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    logger.info("Deleted benchmark run %s for user %s", run_id, user_id)
    return Response(status_code=204)
