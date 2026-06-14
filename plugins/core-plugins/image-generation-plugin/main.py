# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Image Generation Plugin — GH#9015

Registers the generate_image tool with the ToolSDKRegistry so LLC agent
tasks and direct chat requests can generate images via DALL-E 3, Flux, and
Stable Diffusion.

Plugin lifecycle:
    initialize() → registers GenerateImageTool
    shutdown()   → unregisters tool
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from plugin_sdk.base import BasePlugin, PluginManifest
from tool_sdk.registry import get_tool_registry

from .tools import GenerateImageTool

logger = logging.getLogger(__name__)


class ImageGenerationPlugin(BasePlugin):
    """Plugin that adds image generation as an agent-callable tool."""

    def __init__(self, manifest: PluginManifest, config: Optional[Dict] = None) -> None:
        super().__init__(manifest, config)
        cfg = config or {}
        self._registered: bool = False

    async def initialize(self) -> None:
        self._logger.info("ImageGenerationPlugin: initializing")

        openai_key = os.environ.get("OPENAI_API_KEY", "")
        flux_key = os.environ.get("FLUX_API_KEY", "")
        stability_key = os.environ.get("STABILITY_API_KEY", "")

        if not any([openai_key, flux_key, stability_key]):
            self._logger.warning(
                "ImageGenerationPlugin: no API keys configured — "
                "tool registered but all providers will fail at call time. "
                "Set OPENAI_API_KEY, FLUX_API_KEY, or STABILITY_API_KEY."
            )

        registry = get_tool_registry()
        registry.register(GenerateImageTool)
        self._registered = True
        self._logger.info("ImageGenerationPlugin: registered generate_image tool")

    async def shutdown(self) -> None:
        self._logger.info("ImageGenerationPlugin: shutting down")
        if self._registered:
            try:
                registry = get_tool_registry()
                registry.unregister(GenerateImageTool.metadata.name)
            except Exception:
                pass
