# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
generate_video tool — GH#9016.

LLC-callable tool that generates a short video clip from a text prompt via
Runway ML (baseline), OpenAI Sora, or Kling AI. Generation is async: the tool
submits the job, polls the provider until completion, and returns the video URL.

Returns ToolResult.data = {video_url, provider, prompt, duration, job_id}.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict

from tool_sdk.base import BaseTool, ToolMetadata, ToolPermission, ToolResult

from .providers import ProviderError, get_provider

logger = logging.getLogger(__name__)

# Poll cadence / ceiling are env-tunable (no hard-coded magic numbers).
_POLL_INTERVAL_S = float(os.environ.get("VIDEO_GEN_POLL_INTERVAL_S", "5"))
_POLL_MAX_ATTEMPTS = int(os.environ.get("VIDEO_GEN_POLL_MAX_ATTEMPTS", "120"))


class GenerateVideoTool(BaseTool):
    """Generate a short video clip using Runway ML, Sora, or Kling AI."""

    metadata = ToolMetadata(
        name="generate_video",
        description=(
            "Generate a short video clip from a text prompt. Generation is "
            "asynchronous; the tool waits for the provider and returns the "
            "playable video URL. Use provider='runway' (default, most stable), "
            "'sora', or 'kling'. duration is in seconds."
        ),
        version="1.0.0",
        permission=ToolPermission.AUTHENTICATED,
        tags=["media", "video", "generation", "ai"],
    )

    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Text description of the video to generate",
                "minLength": 1,
                "maxLength": 4000,
            },
            "duration": {
                "type": "integer",
                "description": "Clip duration in seconds (1-20, provider limits apply).",
                "minimum": 1,
                "maximum": 20,
            },
            "provider": {
                "type": "string",
                "enum": ["runway", "sora", "kling"],
                "description": "Video generation provider. Defaults to 'runway'.",
            },
            "resolution": {
                "type": "string",
                "description": "Output resolution, e.g. '1280x720'.",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["16:9", "9:16", "1:1"],
                "description": "Aspect ratio. Defaults to '16:9'.",
            },
        },
        "required": ["prompt"],
        "additionalProperties": False,
    }

    async def execute(self, validated_input: Dict[str, Any]) -> ToolResult:
        prompt: str = validated_input["prompt"]
        provider_name: str = validated_input.get("provider", "runway")
        duration: int = int(validated_input.get("duration", 5))
        resolution: str = validated_input.get("resolution", "1280x720")
        aspect_ratio: str = validated_input.get("aspect_ratio", "16:9")

        try:
            provider = get_provider(provider_name)
        except ProviderError as exc:
            return ToolResult(success=False, error=str(exc))

        if not provider.available:
            return ToolResult(
                success=False,
                error=f"{provider.env_var} not configured — {provider_name} provider disabled",
            )

        try:
            job_id = await provider.submit(
                prompt, duration=duration, resolution=resolution, aspect_ratio=aspect_ratio
            )
            return await self._await_completion(provider, job_id, prompt, duration)
        except ProviderError as exc:
            logger.warning("generate_video provider error (provider=%s): %s", provider_name, exc)
            return ToolResult(success=False, error=str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("generate_video failed (provider=%s): %s", provider_name, exc, exc_info=True)
            return ToolResult(success=False, error=str(exc))

    async def _await_completion(self, provider, job_id: str, prompt: str, duration: int) -> ToolResult:
        """Poll the provider until the job finishes or the ceiling is reached."""
        for _ in range(_POLL_MAX_ATTEMPTS):
            status = await provider.poll(job_id)
            if status.status == "succeeded" and status.video_url:
                return ToolResult(
                    success=True,
                    data={
                        "video_url": status.video_url,
                        "provider": provider.name,
                        "prompt": prompt,
                        "duration": duration,
                        "job_id": job_id,
                    },
                )
            if status.status == "failed":
                return ToolResult(success=False, error=status.error or "video generation failed")
            await asyncio.sleep(_POLL_INTERVAL_S)
        return ToolResult(success=False, error="video generation timed out waiting for provider")
