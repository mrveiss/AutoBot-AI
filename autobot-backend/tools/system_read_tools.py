# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Read-only system tools for ToolRegistry (#22267)."""

from __future__ import annotations

import asyncio
from typing import Any, Dict


class SystemReadToolsMixin:
    """query_system_information / list_system_services for ToolRegistry."""

    _system_integration: Any = None

    async def _execute_system_read(self, task_type: str, method: str) -> Dict[str, Any]:
        """Run a read-only system query via the worker node, else SystemIntegration.

        ``get_tool_registry = lazy_singleton(ToolRegistry)`` never receives a
        worker node in production, so without a fallback these tools always
        reported "Worker node not available" (#22267). The worker's own handler
        (``task_handlers/system_handlers.py``) just calls ``SystemIntegration``,
        so the fallback uses the same canonical implementation directly.
        """
        if self.worker_node:
            return await self._execute_worker_task(self._create_base_task(task_type))
        from system_integration import SystemIntegration  # noqa: PLC0415

        if self._system_integration is None:
            self._system_integration = SystemIntegration()
        return await asyncio.to_thread(getattr(self._system_integration, method))

    async def query_system_information(self) -> Dict[str, Any]:
        """Query system information (worker node, else SystemIntegration)."""
        result = await self._execute_system_read("system_query_info", "query_system_info")
        return {
            "tool_name": "query_system_information",
            "tool_args": {},
            "result": result.get("output", result.get("info", result.get("message", "System info retrieved"))),
            "status": result.get("status", "success"),
        }

    async def list_system_services(self) -> Dict[str, Any]:
        """List system services (worker node, else SystemIntegration)."""
        result = await self._execute_system_read("system_list_services", "list_services")
        return {
            "tool_name": "list_system_services",
            "tool_args": {},
            # Local (system_handlers.py) and worker (worker_node.py) paths both answer {"status", "services"};
            # a failure carries "message"/"output" instead, so it must not reach chat as "" (#22280).
            "result": result.get("services") or result.get("message") or result.get("output"),
            "status": result.get("status", "success"),
        }
