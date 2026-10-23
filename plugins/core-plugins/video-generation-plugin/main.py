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
from typing import Dict, Optional

# Fully-qualified (#14373): the bare `tool_sdk` path is not guaranteed to be
# importable at plugin-load time and, where it is, resolves to a second
# module identity with its own, independently empty, registry singleton.
from autobot_shared.plugin_sdk.credential_binding import CredentialUnavailableError
from autobot_shared.tool_sdk.registry import get_tool_registry
from plugin_sdk.base import BasePlugin, PluginManifest

from .tools import GenerateVideoTool
from .tools.providers import read_provider_key, set_credential_resolver

logger = logging.getLogger(__name__)


class VideoGenerationPlugin(BasePlugin):
    """Plugin that adds video generation as an agent-callable tool."""

    def __init__(self, manifest: PluginManifest, config: Optional[Dict] = None) -> None:
        super().__init__(manifest, config)
        self._registered: bool = False

    async def initialize(self) -> None:
        self._logger.info("VideoGenerationPlugin: initializing")

        set_credential_resolver(self.credential_resolver)
        usable = [
            self._key_usable("RUNWAY_API_KEY"),
            self._key_usable("SORA_API_KEY"),
            self._key_usable("KLING_API_KEY"),
        ]

        if not any(usable):
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

    def _key_usable(self, name: str) -> bool:
        """Whether *name* resolves to a key. A host refusal (vault unreadable, #18094) is logged, not fatal;
        the same refusal is returned as the provider error at call time."""
        try:
            return bool(read_provider_key(name))
        except CredentialUnavailableError as exc:
            self._logger.error("VideoGenerationPlugin: %s unavailable at load: %s", name, exc)
            return False

    async def shutdown(self) -> None:
        self._logger.info("VideoGenerationPlugin: shutting down")
        set_credential_resolver(None)
        if self._registered:
            try:
                registry = get_tool_registry()
                registry.unregister(GenerateVideoTool.metadata.name)
            except Exception:
                pass


# Loader entry-point alias (#10294)
Plugin = VideoGenerationPlugin
