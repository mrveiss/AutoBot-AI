# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tool descriptions for ToolRegistry, moved out of it unchanged (#5871)."""

from __future__ import annotations

import asyncio
from typing import Dict

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class ToolDescriptionsMixin:
    """Raw and compressed per-tool descriptions; needs ``self.get_available_tools``."""

    def _tool_description(self, name: str) -> str:
        """Return the raw (uncompressed) description for a single tool. Issue #5871."""
        import inspect  # noqa: PLC0415

        method = getattr(self, name, None)
        if method is not None:
            doc = inspect.getdoc(method)
            if doc:
                return doc.split("\n")[0]
        try:
            from chat_workflow.tool_handler import _BUILTIN_TOOL_SCHEMAS  # noqa: PLC0415

            schema = _BUILTIN_TOOL_SCHEMAS.get(name, {})
            desc = (schema or {}).get("description", "")
            if desc:
                return desc
        except ImportError:
            pass
        return name

    def get_raw_descriptions(self) -> Dict[str, str]:
        """Return uncompressed descriptions for all registered tools. Issue #5871."""
        return {name: self._tool_description(name) for name in self.get_available_tools()}

    async def get_compressed_descriptions(self) -> Dict[str, str]:
        """Return a mapping of tool_name -> compressed description for all registered tools.

        Uses :func:`tools.description_compressor.compress_description` with Redis
        caching and Ollama LLM compression.  Falls back to the tool name string for
        any tool whose description cannot be resolved.
        """
        from tools.description_compressor import compress_description  # noqa: PLC0415

        tool_names = self.get_available_tools()
        tasks = [compress_description(name, {"description": self._tool_description(name)}) for name in tool_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        compressed: Dict[str, str] = {}
        for name, result in zip(tool_names, results):
            if isinstance(result, Exception):
                logger.warning("compress_description failed for tool '%s': %s", name, result)
                compressed[name] = self._tool_description(name)
            else:
                compressed[name] = result
        return compressed
