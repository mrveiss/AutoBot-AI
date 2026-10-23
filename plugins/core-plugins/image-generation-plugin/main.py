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
from typing import Dict, Optional

# Fully-qualified (#14373): the bare `tool_sdk` path is not guaranteed to be
# importable at plugin-load time and, where it is, resolves to a second
# module identity with its own, independently empty, registry singleton.
from autobot_shared.plugin_sdk.credential_binding import CredentialUnavailableError
from autobot_shared.tool_sdk.registry import get_tool_registry
from plugin_sdk.base import BasePlugin, PluginManifest

from .tools import GenerateImageTool, read_provider_key, set_credential_resolver

logger = logging.getLogger(__name__)


class ImageGenerationPlugin(BasePlugin):
    """Plugin that adds image generation as an agent-callable tool."""

    def __init__(self, manifest: PluginManifest, config: Optional[Dict] = None) -> None:
        super().__init__(manifest, config)
        self._registered: bool = False

    async def initialize(self) -> None:
        self._logger.info("ImageGenerationPlugin: initializing")

        set_credential_resolver(self.credential_resolver)
        usable = [
            self._key_usable("OPENAI_API_KEY"),
            self._key_usable("FLUX_API_KEY"),
            self._key_usable("STABILITY_API_KEY"),
        ]

        if not any(usable):
            self._logger.warning(
                "ImageGenerationPlugin: no API keys configured — "
                "tool registered but all providers will fail at call time. "
                "Set OPENAI_API_KEY, FLUX_API_KEY, or STABILITY_API_KEY."
            )

        registry = get_tool_registry()
        registry.register(GenerateImageTool)
        self._registered = True
        self._logger.info("ImageGenerationPlugin: registered generate_image tool")

    def _key_usable(self, name: str) -> bool:
        """Whether *name* resolves to a key. A host refusal (vault unreadable, #18094) is logged, not fatal;
        the same refusal is returned as the tool error at call time."""
        try:
            return bool(read_provider_key(name))
        except CredentialUnavailableError as exc:
            self._logger.error("ImageGenerationPlugin: %s unavailable at load: %s", name, exc)
            return False

    async def shutdown(self) -> None:
        self._logger.info("ImageGenerationPlugin: shutting down")
        set_credential_resolver(None)
        if self._registered:
            try:
                registry = get_tool_registry()
                registry.unregister(GenerateImageTool.metadata.name)
            except Exception:
                pass


# Loader entry-point alias (#10294)
Plugin = ImageGenerationPlugin
