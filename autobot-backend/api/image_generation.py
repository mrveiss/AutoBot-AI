# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Image Generation API — GH#9015

REST surface for the image-generation-plugin.  Wraps the generate_image
ToolSDK tool so both the chat frontend and external callers can request
image generation without going through an LLC agent session.

Endpoints:
    POST /api/image-generation/generate  — generate images
    GET  /api/image-generation/providers — list configured providers
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter(tags=["image-generation", "media"])


# ------------------------------------------------------------------
# Request / Response models
# ------------------------------------------------------------------


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    provider: str = Field("dalle", pattern="^(dalle|flux|stable_diffusion)$")
    size: Optional[str] = Field(None)
    quality: Optional[str] = Field(None, pattern="^(standard|hd)$")
    n: Optional[int] = Field(None, ge=1, le=4)
    negative_prompt: Optional[str] = Field(None, max_length=2000)


class GeneratedImage(BaseModel):
    url: str
    revised_prompt: Optional[str] = None


class ImageGenerationResponse(BaseModel):
    success: bool
    images: List[GeneratedImage] = []
    provider: str = ""
    model: str = ""
    prompt: str = ""
    size: str = ""
    error: Optional[str] = None


class ProviderStatus(BaseModel):
    name: str
    available: bool
    reason: Optional[str] = None


class ProvidersResponse(BaseModel):
    providers: List[ProviderStatus]


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get("/providers", response_model=ProvidersResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR, operation="list_image_providers", error_code_prefix="IMAGE_GEN"
)
async def list_providers(current_user=Depends(get_current_user)):
    """Return which image providers have API keys configured."""
    providers = [
        ProviderStatus(
            name="dalle",
            available=bool(os.environ.get("OPENAI_API_KEY")),
            reason=None if os.environ.get("OPENAI_API_KEY") else "OPENAI_API_KEY not set",
        ),
        ProviderStatus(
            name="flux",
            available=bool(os.environ.get("FLUX_API_KEY")),
            reason=None if os.environ.get("FLUX_API_KEY") else "FLUX_API_KEY not set",
        ),
        ProviderStatus(
            name="stable_diffusion",
            available=bool(os.environ.get("STABILITY_API_KEY")),
            reason=None if os.environ.get("STABILITY_API_KEY") else "STABILITY_API_KEY not set",
        ),
    ]
    return ProvidersResponse(providers=providers)


@router.post("/generate", response_model=ImageGenerationResponse)
@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="generate_image", error_code_prefix="IMAGE_GEN")
async def generate_image(
    request: ImageGenerationRequest,
    current_user=Depends(get_current_user),
):
    """Generate image(s) from a text prompt.

    Uses the ToolSDKRegistry so the generate_image tool's validation and
    execution logic is reused. Falls back to direct provider call if the
    plugin is not loaded.
    """
    try:
        from tool_sdk.registry import get_tool_registry

        registry = get_tool_registry()
        input_data: Dict[str, Any] = {"prompt": request.prompt, "provider": request.provider}
        if request.size:
            input_data["size"] = request.size
        if request.quality:
            input_data["quality"] = request.quality
        if request.n:
            input_data["n"] = request.n
        if request.negative_prompt:
            input_data["negative_prompt"] = request.negative_prompt

        result = await registry.execute("generate_image", input_data)

        if not result.success:
            return ImageGenerationResponse(
                success=False,
                error=result.error or "Image generation failed",
            )

        data = result.data or {}
        images = [GeneratedImage(**img) for img in data.get("images", [])]
        return ImageGenerationResponse(
            success=True,
            images=images,
            provider=data.get("provider", request.provider),
            model=data.get("model", ""),
            prompt=data.get("prompt", request.prompt),
            size=data.get("size", request.size or ""),
        )

    except Exception as exc:
        logger.error("image_generation API error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
