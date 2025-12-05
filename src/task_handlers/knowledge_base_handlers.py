# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Task Handlers
"""

import logging
from typing import TYPE_CHECKING, Any, Dict

from .base import TaskHandler

if TYPE_CHECKING:
    from src.worker_node import WorkerNode

logger = logging.getLogger(__name__)


class KBAddFileHandler(TaskHandler):
    """Handler for kb_add_file tasks"""

    async def execute(
        self,
        worker: "WorkerNode",
        task_payload: Dict[str, Any],
        user_role: str,
        task_id: str,
    ) -> Dict[str, Any]:
        file_path = task_payload["file_path"]
        file_type = task_payload["file_type"]
        metadata = task_payload.get("metadata")

        result = await worker.knowledge_base.add_file(file_path, file_type, metadata)

        worker.security_layer.audit_log(
            "kb_add_file",
            user_role,
            result.get("status", "unknown"),
            {"task_id": task_id, "file_path": file_path},
        )

        return result


class KBSearchHandler(TaskHandler):
    """Handler for kb_search tasks"""

    async def execute(
        self,
        worker: "WorkerNode",
        task_payload: Dict[str, Any],
        user_role: str,
        task_id: str,
    ) -> Dict[str, Any]:
        query = task_payload["query"]
        n_results = task_payload.get("n_results", 5)

        kb_results = await worker.knowledge_base.search(query, n_results)

        result = {
            "status": "success",
            "message": "KB search successful.",
            "results": kb_results,
        }

        worker.security_layer.audit_log(
            "kb_search",
            user_role,
            "success",
            {"task_id": task_id, "query": query},
        )

        return result


class KBStoreFactHandler(TaskHandler):
    """Handler for kb_store_fact tasks"""

    async def execute(
        self,
        worker: "WorkerNode",
        task_payload: Dict[str, Any],
        user_role: str,
        task_id: str,
    ) -> Dict[str, Any]:
        content = task_payload["content"]
        metadata = task_payload.get("metadata")

        result = await worker.knowledge_base.store_fact(content, metadata)

        worker.security_layer.audit_log(
            "kb_store_fact",
            user_role,
            result.get("status", "unknown"),
            {"task_id": task_id, "content_preview": content[:50]},
        )

        return result
