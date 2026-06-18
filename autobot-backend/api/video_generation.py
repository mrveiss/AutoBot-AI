# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Video Generation API — GH#9016.

REST surface for the video-generation-plugin. Video generation is async, so
unlike image generation this exposes a submit + poll lifecycle:

    POST /api/video-generation/generate       — submit a job, returns job_id
    GET  /api/video-generation/status/{id}     — poll progress + final URL
    GET  /api/video-generation/providers       — list configured providers

Mirrors api/image_generation.py (provider listing, secrets-gated keys, router
shape). The job record is persisted in Redis so polling works across workers.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api._video_providers_loader import load_video_providers
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.redis_client import redis_get, redis_set

logger = logging.getLogger(__name__)

# Providers live in the video-generation-plugin tree. The plugin loader's
# package path (plugins.core_plugins.*) is not importable directly, so we
# resolve the module by file path. The loader is guarded so startup-import-smoke
# never breaks if the plugin tree or its deps are absent.
_providers = load_video_providers()
_PROVIDERS_AVAILABLE = _providers is not None

if _PROVIDERS_AVAILABLE:
    ProviderError = _providers.ProviderError  # type: ignore[attr-defined]
    get_provider = _providers.get_provider  # type: ignore[attr-defined]
    provider_names = _providers.provider_names  # type: ignore[attr-defined]
else:  # pragma: no cover - import guard

    class ProviderError(Exception):  # type: ignore[no-redef]
        pass

    def get_provider(name: str):  # type: ignore[no-redef]
        raise ProviderError("video providers unavailable")

    def provider_names():  # type: ignore[no-redef]
        return ["runway", "sora", "kling"]

router = APIRouter(tags=["video-generation", "media"])

# Job records are short-lived; TTL is env-tunable (no hard-coded magic number).
_JOB_TTL_S = int(os.environ.get("VIDEO_GEN_JOB_TTL_S", "3600"))
_JOB_KEY_PREFIX = "video_gen:job:"

_PROVIDER_ENV = {"runway": "RUNWAY_API_KEY", "sora": "SORA_API_KEY", "kling": "KLING_API_KEY"}


# ------------------------------------------------------------------
# Request / Response models
# ------------------------------------------------------------------


class VideoGenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    provider: str = Field("runway", pattern="^(runway|sora|kling)$")
    duration: int = Field(5, ge=1, le=20)
    resolution: Optional[str] = Field(None)
    aspect_ratio: Optional[str] = Field(None, pattern="^(16:9|9:16|1:1)$")


class VideoJobResponse(BaseModel):
    success: bool
    job_id: str = ""
    provider: str = ""
    status: str = "pending"
    error: Optional[str] = None


class VideoStatusResponse(BaseModel):
    success: bool
    job_id: str = ""
    status: str = "pending"
    progress: float = 0.0
    video_url: Optional[str] = None
    provider: str = ""
    prompt: str = ""
    error: Optional[str] = None


class ProviderStatus(BaseModel):
    name: str
    available: bool
    reason: Optional[str] = None


class ProvidersResponse(BaseModel):
    providers: list[ProviderStatus]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _job_key(job_id: str) -> str:
    return f"{_JOB_KEY_PREFIX}{job_id}"


async def _load_job(job_id: str) -> Optional[dict]:
    raw = await redis_get(_job_key(job_id))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


async def _store_job(job_id: str, record: dict) -> None:
    await redis_set(_job_key(job_id), json.dumps(record), expire=_JOB_TTL_S)


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get("/providers", response_model=ProvidersResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR, operation="list_video_providers", error_code_prefix="VIDEO_GEN"
)
async def list_providers(current_user=Depends(get_current_user)):
    """Return which video providers have API keys configured."""
    providers = []
    for name in provider_names():
        env_var = _PROVIDER_ENV.get(name, "")
        configured = bool(os.environ.get(env_var))
        providers.append(
            ProviderStatus(
                name=name,
                available=configured,
                reason=None if configured else f"{env_var} not set",
            )
        )
    return ProvidersResponse(providers=providers)


@router.post("/generate", response_model=VideoJobResponse)
@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="generate_video", error_code_prefix="VIDEO_GEN")
async def generate_video(request: VideoGenerationRequest, current_user=Depends(get_current_user)):
    """Submit an async video-generation job; returns a job id to poll."""
    if not _PROVIDERS_AVAILABLE:
        return VideoJobResponse(success=False, error="video-generation-plugin not installed")

    try:
        provider = get_provider(request.provider)
    except ProviderError as exc:
        return VideoJobResponse(success=False, error=str(exc))

    if not provider.available:
        env_var = _PROVIDER_ENV.get(request.provider, "API key")
        return VideoJobResponse(
            success=False,
            provider=request.provider,
            error=f"{env_var} not configured — {request.provider} provider disabled",
        )

    try:
        job_id = await provider.submit(
            request.prompt,
            duration=request.duration,
            resolution=request.resolution or "1280x720",
            aspect_ratio=request.aspect_ratio or "16:9",
        )
    except ProviderError as exc:
        logger.warning("video submit failed (provider=%s): %s", request.provider, exc)
        return VideoJobResponse(success=False, provider=request.provider, error=str(exc))

    record = {
        "provider": request.provider,
        "provider_job_id": job_id,
        "prompt": request.prompt,
        "duration": request.duration,
    }
    local_id = uuid.uuid4().hex
    await _store_job(local_id, record)
    return VideoJobResponse(success=True, job_id=local_id, provider=request.provider, status="pending")


@router.get("/status/{job_id}", response_model=VideoStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR, operation="video_job_status", error_code_prefix="VIDEO_GEN"
)
async def get_status(job_id: str, current_user=Depends(get_current_user)):
    """Poll a submitted job for progress and the final video URL."""
    record = await _load_job(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Video job not found or expired")

    try:
        provider = get_provider(record["provider"])
        status = await provider.poll(record["provider_job_id"])
    except ProviderError as exc:
        logger.warning("video poll failed (job=%s): %s", job_id, exc)
        return VideoStatusResponse(
            success=False, job_id=job_id, status="failed", provider=record.get("provider", ""),
            prompt=record.get("prompt", ""), error=str(exc),
        )

    return VideoStatusResponse(
        success=status.status != "failed",
        job_id=job_id,
        status=status.status,
        progress=status.progress,
        video_url=status.video_url,
        provider=status.provider or record.get("provider", ""),
        prompt=record.get("prompt", ""),
        error=status.error,
    )
