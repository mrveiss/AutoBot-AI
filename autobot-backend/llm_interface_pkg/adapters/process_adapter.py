# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Process Adapter - Spawn CLI tools as subprocess LLM backends.

Issue #1403: Enables running local CLI tools (e.g. Claude Code)
as LLM backends via subprocess execution.
"""

import asyncio
import logging
import shutil
import time
from typing import Any, Dict, List, Optional

from ..models import LLMRequest, LLMResponse
from .base import (
    AdapterBase,
    AdapterConfig,
    DiagnosticLevel,
    DiagnosticMessage,
    EnvironmentTestResult,
)

logger = logging.getLogger(__name__)

DEFAULT_ALLOWED_TOOLS = {
    "claude": {
        "binary": "claude",
        "args": ["--print"],
        "description": "Claude Code CLI",
    },
}


class ProcessAdapter(AdapterBase):
    """Adapter that spawns CLI tools as subprocess backends (#1403)."""

    def __init__(self, config: Optional[AdapterConfig] = None):
        super().__init__("process", config)
        self._tools: Dict[str, Dict[str, Any]] = self.config.settings.get(
            "tools", DEFAULT_ALLOWED_TOOLS
        )
        self._timeout = self.config.settings.get("timeout", 120)

    def _get_tool_config(self, tool_name: Optional[str] = None) -> Dict[str, Any]:
        """Get configuration for a specific tool."""
        name = tool_name or next(iter(self._tools), None)
        if not name or name not in self._tools:
            raise ValueError(
                f"Unknown process tool: {tool_name}. "
                f"Available: {list(self._tools.keys())}"
            )
        return self._tools[name]

    async def execute(self, request: LLMRequest) -> LLMResponse:
        """Execute LLM call by spawning a CLI subprocess."""
        tool_name = request.metadata.get("process_tool")
        tool_config = self._get_tool_config(tool_name)
        start = time.time()

        prompt_parts = []
        for msg in request.messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt_parts.insert(0, content)
            else:
                prompt_parts.append(content)
        prompt = "\n\n".join(prompt_parts)

        binary = tool_config["binary"]
        args = list(tool_config.get("args", []))

        try:
            proc = await asyncio.create_subprocess_exec(
                binary,
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=prompt.encode("utf-8")),
                timeout=self._timeout,
            )

            content = stdout.decode("utf-8").strip()
            elapsed = time.time() - start

            if proc.returncode != 0:
                err = stderr.decode("utf-8").strip()
                logger.error(
                    "Process %s exited %d: %s",
                    binary,
                    proc.returncode,
                    err,
                )
                content = content or f"Process error: {err}"

            return LLMResponse(
                content=content,
                model=f"process:{tool_name or binary}",
                provider="process",
                processing_time=elapsed,
                request_id=request.request_id,
                metadata={
                    "exit_code": proc.returncode,
                    "binary": binary,
                },
            )

        except asyncio.TimeoutError:
            elapsed = time.time() - start
            return LLMResponse(
                content=f"Process timed out after {self._timeout}s",
                model=f"process:{tool_name or binary}",
                provider="process",
                processing_time=elapsed,
                request_id=request.request_id,
                error="timeout",
            )

    async def test_environment(self) -> EnvironmentTestResult:
        """Test that configured CLI tools are available."""
        diagnostics: List[DiagnosticMessage] = []
        start = time.time()
        available_tools: List[str] = []

        for name, tool_config in self._tools.items():
            binary = tool_config["binary"]
            path = shutil.which(binary)
            if path:
                available_tools.append(name)
                diagnostics.append(
                    DiagnosticMessage(
                        level=DiagnosticLevel.INFO,
                        message=f"Tool '{name}' found at {path}",
                    )
                )
            else:
                diagnostics.append(
                    DiagnosticMessage(
                        level=DiagnosticLevel.WARN,
                        message=f"Tool '{name}' not found",
                    )
                )

        elapsed = time.time() - start
        healthy = len(available_tools) > 0

        return EnvironmentTestResult(
            healthy=healthy,
            adapter_type="process",
            diagnostics=diagnostics,
            models_available=[f"process:{t}" for t in available_tools],
            response_time=elapsed,
        )

    async def list_models(self) -> List[str]:
        """List available process tools as models."""
        result = await self.test_environment()
        return result.models_available


__all__ = ["ProcessAdapter"]
