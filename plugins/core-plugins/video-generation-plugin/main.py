# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Video Generation Plugin — GH#9016.

Registers the generate_video tool with the ToolSDKRegistry so LLC agent tasks
and direct chat requests can generate short video clips via Runway ML (baseline),
OpenAI Sora, and Kling AI (the latter two credential-gated).

Plugin lifecycle:
    initialize() → registers GenerateVideoTool
    shutdown()   → unregisters tool
"""

from __future__ import annotations

import logging
import os
from typing import Dict, Optional

from plugin_sdk.base import BasePlugin, PluginManifest
from tool_sdk.registry import get_tool_registry

from .tools import GenerateVideoTool

logger = logging.getLogger(__name__)


class VideoGenerationPlugin(BasePlugin):
    """Plugin that adds video generation as an agent-callable tool."""

    def __init__(self, manifest: PluginManifest, config: Optional[Dict] = None) -> None:
        super().__init__(manifest, config)
        self._registered: bool = False

    async def initialize(self) -> None:
        self._logger.info("VideoGenerationPlugin: initializing")

        runway_key = os.environ.get("RUNWAY_API_KEY", "")
        sora_key = os.environ.get("SORA_API_KEY", "")
        kling_key = os.environ.get("KLING_API_KEY", "")

        if not any([runway_key, sora_key, kling_key]):
            self._logger.warning(
                "VideoGenerationPlugin: no API keys configured — "
                "tool registered but all providers will fail at call time. "
                "Set RUNWAY_API_KEY (baseline), SORA_API_KEY, or KLING_API_KEY."
            )

        registry = get_tool_registry()
        if "generate_video" not in {m.name for m in registry.list_tools()}:
            registry.register(GenerateVideoTool)
        self._registered = True
        self._logger.info("VideoGenerationPlugin: registered generate_video tool")

    async def shutdown(self) -> None:
        self._logger.info("VideoGenerationPlugin: shutting down")
        if self._registered:
            try:
                registry = get_tool_registry()
                registry.unregister(GenerateVideoTool.metadata.name)
            except Exception:
                pass

# Loader entry-point alias (#10294)
Plugin = VideoGenerationPlugin
