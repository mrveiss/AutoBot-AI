# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
System Integration Task Handlers

Issue #322: Refactored to use TaskExecutionContext to eliminate data clump pattern.
"""

import logging
from typing import Any, Dict

from models.task_context import TaskExecutionContext

from .base import TaskHandler

logger = logging.getLogger(__name__)


class SystemQueryInfoHandler(TaskHandler):
    """Handler for system_query_info tasks"""

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """Execute system info query and log the audit result."""
        result = ctx.worker.system_integration.query_system_info()

        ctx.audit_log(
            "system_query_info",
            result.get("status", "unknown"),
            {},
        )

        return result


class SystemListServicesHandler(TaskHandler):
    """Handler for system_list_services tasks"""

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """Execute service listing and log the audit result."""
        result = ctx.worker.system_integration.list_services()

        ctx.audit_log(
            "system_list_services",
            result.get("status", "unknown"),
            {},
        )

        return result


class SystemManageServiceHandler(TaskHandler):
    """Handler for system_manage_service tasks"""

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """Execute service management action and log the audit result."""
        service_name = ctx.require_payload_value("service_name")
        action = ctx.require_payload_value("action")

        result = ctx.worker.system_integration.manage_service(service_name, action)

        ctx.audit_log(
            "system_manage_service",
            result.get("status", "unknown"),
            {"service": service_name, "action": action},
        )

        return result


class SystemExecuteCommandHandler(TaskHandler):
    """Handler for system_execute_command tasks"""

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """Execute system command and log the audit result."""
        command = ctx.require_payload_value("command")

        result = ctx.worker.system_integration.execute_system_command(command)

        ctx.audit_log(
            "system_execute_command",
            result.get("status", "unknown"),
            {"command": command},
        )

        return result


class SystemGetProcessInfoHandler(TaskHandler):
    """Handler for system_get_process_info tasks"""

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """Execute process info query and log the audit result."""
        process_name = ctx.get_payload_value("process_name")
        pid = ctx.get_payload_value("pid")

        result = ctx.worker.system_integration.get_process_info(process_name, pid)

        ctx.audit_log(
            "system_get_process_info",
            result.get("status", "unknown"),
            {"process_name": process_name, "pid": pid},
        )

        return result


class SystemTerminateProcessHandler(TaskHandler):
    """Handler for system_terminate_process tasks"""

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """Execute process termination and log the audit result."""
        pid = ctx.require_payload_value("pid")

        result = ctx.worker.system_integration.terminate_process(pid)

        ctx.audit_log(
            "system_terminate_process",
            result.get("status", "unknown"),
            {"pid": pid},
        )

        return result


class WebFetchHandler(TaskHandler):
    """Handler for web_fetch tasks"""

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """Execute web fetch request and log the audit result."""
        url = ctx.require_payload_value("url")

        result = await ctx.worker.system_integration.web_fetch(url)

        ctx.audit_log(
            "web_fetch",
            result.get("status", "unknown"),
            {"url": url},
        )

        return result
