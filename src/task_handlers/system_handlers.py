# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
System Integration Task Handlers
"""

import logging
from typing import TYPE_CHECKING, Any, Dict

from .base import TaskHandler

if TYPE_CHECKING:
    from src.worker_node import WorkerNode

logger = logging.getLogger(__name__)


class SystemQueryInfoHandler(TaskHandler):
    """Handler for system_query_info tasks"""

    async def execute(
        self,
        worker: "WorkerNode",
        task_payload: Dict[str, Any],
        user_role: str,
        task_id: str,
    ) -> Dict[str, Any]:
        result = worker.system_integration.query_system_info()

        worker.security_layer.audit_log(
            "system_query_info",
            user_role,
            result.get("status", "unknown"),
            {"task_id": task_id},
        )

        return result


class SystemListServicesHandler(TaskHandler):
    """Handler for system_list_services tasks"""

    async def execute(
        self,
        worker: "WorkerNode",
        task_payload: Dict[str, Any],
        user_role: str,
        task_id: str,
    ) -> Dict[str, Any]:
        result = worker.system_integration.list_services()

        worker.security_layer.audit_log(
            "system_list_services",
            user_role,
            result.get("status", "unknown"),
            {"task_id": task_id},
        )

        return result


class SystemManageServiceHandler(TaskHandler):
    """Handler for system_manage_service tasks"""

    async def execute(
        self,
        worker: "WorkerNode",
        task_payload: Dict[str, Any],
        user_role: str,
        task_id: str,
    ) -> Dict[str, Any]:
        service_name = task_payload["service_name"]
        action = task_payload["action"]

        result = worker.system_integration.manage_service(service_name, action)

        worker.security_layer.audit_log(
            "system_manage_service",
            user_role,
            result.get("status", "unknown"),
            {"task_id": task_id, "service": service_name, "action": action},
        )

        return result


class SystemExecuteCommandHandler(TaskHandler):
    """Handler for system_execute_command tasks"""

    async def execute(
        self,
        worker: "WorkerNode",
        task_payload: Dict[str, Any],
        user_role: str,
        task_id: str,
    ) -> Dict[str, Any]:
        command = task_payload["command"]

        result = worker.system_integration.execute_system_command(command)

        worker.security_layer.audit_log(
            "system_execute_command",
            user_role,
            result.get("status", "unknown"),
            {"task_id": task_id, "command": command},
        )

        return result


class SystemGetProcessInfoHandler(TaskHandler):
    """Handler for system_get_process_info tasks"""

    async def execute(
        self,
        worker: "WorkerNode",
        task_payload: Dict[str, Any],
        user_role: str,
        task_id: str,
    ) -> Dict[str, Any]:
        process_name = task_payload.get("process_name")
        pid = task_payload.get("pid")

        result = worker.system_integration.get_process_info(process_name, pid)

        worker.security_layer.audit_log(
            "system_get_process_info",
            user_role,
            result.get("status", "unknown"),
            {"task_id": task_id, "process_name": process_name, "pid": pid},
        )

        return result


class SystemTerminateProcessHandler(TaskHandler):
    """Handler for system_terminate_process tasks"""

    async def execute(
        self,
        worker: "WorkerNode",
        task_payload: Dict[str, Any],
        user_role: str,
        task_id: str,
    ) -> Dict[str, Any]:
        pid = task_payload["pid"]

        result = worker.system_integration.terminate_process(pid)

        worker.security_layer.audit_log(
            "system_terminate_process",
            user_role,
            result.get("status", "unknown"),
            {"task_id": task_id, "pid": pid},
        )

        return result


class WebFetchHandler(TaskHandler):
    """Handler for web_fetch tasks"""

    async def execute(
        self,
        worker: "WorkerNode",
        task_payload: Dict[str, Any],
        user_role: str,
        task_id: str,
    ) -> Dict[str, Any]:
        url = task_payload["url"]

        result = await worker.system_integration.web_fetch(url)

        worker.security_layer.audit_log(
            "web_fetch",
            user_role,
            result.get("status", "unknown"),
            {"task_id": task_id, "url": url},
        )

        return result
