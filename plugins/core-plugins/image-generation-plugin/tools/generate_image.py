# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
generate_image tool — GH#9015

LLC-callable tool that generates images via DALL-E 3, Flux, or Stable Diffusion.
Provider is chosen per-call; API keys are read from environment variables.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

from tool_sdk.base import BaseTool, ToolMetadata, ToolPermission, ToolResult

logger = logging.getLogger(__name__)


class GenerateImageTool(BaseTool):
    """Generate an image using DALL-E 3, Flux, or Stable Diffusion."""

    metadata = ToolMetadata(
        name="generate_image",
        description=(
            "Generate an image from a text prompt using DALL-E 3, Flux, or "
            "Stable Diffusion. Returns image URL(s) and metadata. "
            "Use provider='dalle' for photorealistic quality, 'flux' for artistic "
            "control, or 'stable_diffusion' for open-weights generation."
        ),
        version="1.0.0",
        permission=ToolPermission.AUTHENTICATED,
        tags=["media", "image", "generation", "ai"],
    )

    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Text description of the image to generate",
                "minLength": 1,
                "maxLength": 4000,
            },
            "provider": {
                "type": "string",
                "enum": ["dalle", "flux", "stable_diffusion"],
                "description": "Image generation provider. Defaults to 'dalle'.",
            },
            "size": {
                "type": "string",
                "description": (
                    "Image dimensions. DALL-E: '1024x1024', '1792x1024', '1024x1792'. "
                    "Flux: '1024x1024'. SD: '1024x1024', '512x512'."
                ),
            },
            "quality": {
                "type": "string",
                "enum": ["standard", "hd"],
                "description": "DALL-E 3 quality level (ignored for other providers).",
            },
            "n": {
                "type": "integer",
                "description": "Number of images to generate (1–4, DALL-E 3 only supports 1).",
                "minimum": 1,
                "maximum": 4,
            },
            "negative_prompt": {
                "type": "string",
                "description": "Elements to exclude (Stable Diffusion and Flux only).",
                "maxLength": 2000,
            },
        },
        "required": ["prompt"],
        "additionalProperties": False,
    }

    async def execute(self, validated_input: Dict[str, Any]) -> ToolResult:
        prompt: str = validated_input["prompt"]
        provider: str = validated_input.get("provider", "dalle")
        size: str = validated_input.get("size", "1024x1024")
        quality: str = validated_input.get("quality", "standard")
        n: int = validated_input.get("n", 1)
        negative_prompt: str = validated_input.get("negative_prompt", "")

        try:
            if provider == "dalle":
                return await self._generate_dalle(prompt, size, quality, n)
            elif provider == "flux":
                return await self._generate_flux(prompt, size, negative_prompt)
            elif provider == "stable_diffusion":
                return await self._generate_sd(prompt, size, negative_prompt, n)
            else:
                return ToolResult(success=False, error=f"Unknown provider: {provider}")
        except Exception as exc:
            logger.error("generate_image failed (provider=%s): %s", provider, exc, exc_info=True)
            return ToolResult(success=False, error=str(exc))

    # ------------------------------------------------------------------
    # DALL-E 3
    # ------------------------------------------------------------------

    async def _generate_dalle(self, prompt: str, size: str, quality: str, n: int) -> ToolResult:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return ToolResult(success=False, error="OPENAI_API_KEY not configured")

        try:
            import openai
        except ImportError:
            return ToolResult(success=False, error="openai package not installed (pip install openai)")

        valid_sizes = {"1024x1024", "1792x1024", "1024x1792"}
        if size not in valid_sizes:
            size = "1024x1024"

        # DALL-E 3 only supports n=1
        effective_n = 1

        client = openai.AsyncOpenAI(api_key=api_key)
        response = await client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,  # type: ignore[arg-type]
            quality=quality,  # type: ignore[arg-type]
            n=effective_n,
            response_format="url",
        )

        images = [
            {
                "url": img.url,
                "revised_prompt": getattr(img, "revised_prompt", None),
            }
            for img in response.data
        ]

        return ToolResult(
            success=True,
            data={
                "images": images,
                "provider": "dalle",
                "model": "dall-e-3",
                "prompt": prompt,
                "size": size,
                "quality": quality,
            },
        )

    # ------------------------------------------------------------------
    # Flux (api.bfl.ml)
    # ------------------------------------------------------------------

    async def _generate_flux(self, prompt: str, size: str, negative_prompt: str) -> ToolResult:
        api_key = os.environ.get("FLUX_API_KEY", "")
        if not api_key:
            return ToolResult(success=False, error="FLUX_API_KEY not configured")

        try:
            import aiohttp
        except ImportError:
            return ToolResult(success=False, error="aiohttp package not installed")

        width, height = self._parse_size(size, default_w=1024, default_h=1024)

        payload: Dict[str, Any] = {
            "prompt": prompt,
            "width": width,
            "height": height,
            "steps": 28,
            "guidance": 3.5,
        }
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.bfl.ml/v1/flux-pro-1.1",
                json=payload,
                headers={"x-key": api_key, "Content-Type": "application/json"},
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    return ToolResult(success=False, error=f"Flux API error {resp.status}: {body}")
                task_data = await resp.json()

        task_id = task_data.get("id")
        if not task_id:
            return ToolResult(success=False, error=f"Flux: no task id in response: {task_data}")

        # Poll for result (Flux is async)
        import asyncio

        for _ in range(60):
            await asyncio.sleep(2)
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://api.bfl.ml/v1/get_result?id={task_id}",
                    headers={"x-key": api_key},
                ) as poll:
                    if poll.status != 200:
                        continue
                    result = await poll.json()

            status = result.get("status")
            if status == "Ready":
                url = result.get("result", {}).get("sample", "")
                return ToolResult(
                    success=True,
                    data={
                        "images": [{"url": url, "revised_prompt": None}],
                        "provider": "flux",
                        "model": "flux-pro-1.1",
                        "prompt": prompt,
                        "size": size,
                    },
                )
            elif status in ("Error", "Content Moderated"):
                return ToolResult(success=False, error=f"Flux generation failed: {status}")

        return ToolResult(success=False, error="Flux: timed out waiting for image result")

    # ------------------------------------------------------------------
    # Stable Diffusion (Stability AI)
    # ------------------------------------------------------------------

    async def _generate_sd(
        self, prompt: str, size: str, negative_prompt: str, n: int
    ) -> ToolResult:
        api_key = os.environ.get("STABILITY_API_KEY", "")
        if not api_key:
            return ToolResult(success=False, error="STABILITY_API_KEY not configured")

        try:
            import aiohttp
        except ImportError:
            return ToolResult(success=False, error="aiohttp package not installed")

        width, height = self._parse_size(size, default_w=1024, default_h=1024)
        # SD v2 supported sizes: multiples of 64, max 2048
        width = min(max(width // 64 * 64, 512), 2048)
        height = min(max(height // 64 * 64, 512), 2048)

        payload: Dict[str, Any] = {
            "text_prompts": [{"text": prompt, "weight": 1.0}],
            "cfg_scale": 7,
            "width": width,
            "height": height,
            "samples": min(n, 4),
            "steps": 30,
        }
        if negative_prompt:
            payload["text_prompts"].append({"text": negative_prompt, "weight": -1.0})

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image",
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    return ToolResult(success=False, error=f"Stability API error {resp.status}: {body}")
                data = await resp.json()

        images = []
        for artifact in data.get("artifacts", []):
            if artifact.get("finishReason") == "SUCCESS":
                import base64

                b64 = artifact.get("base64", "")
                # Return as data URL so frontend can display without a CDN
                images.append({
                    "url": f"data:image/png;base64,{b64}",
                    "revised_prompt": None,
                })

        if not images:
            return ToolResult(success=False, error="Stable Diffusion: no successful artifacts returned")

        return ToolResult(
            success=True,
            data={
                "images": images,
                "provider": "stable_diffusion",
                "model": "stable-diffusion-xl-1024-v1-0",
                "prompt": prompt,
                "size": f"{width}x{height}",
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_size(size: str, default_w: int = 1024, default_h: int = 1024):
        """Parse 'WxH' string into (width, height) ints."""
        try:
            parts = size.lower().split("x")
            return int(parts[0]), int(parts[1])
        except Exception:
            return default_w, default_h
