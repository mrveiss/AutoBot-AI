# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
A2A Task Executor

Issue #961: Bridges incoming A2A tasks to AutoBot's existing AgentOrchestrator.
Runs as a FastAPI BackgroundTask so the POST /tasks endpoint returns immediately
with the task ID while execution continues asynchronously.
"""

import logging
from typing import Any, Dict, Optional

from .task_manager import get_task_manager
from .types import TaskArtifact, TaskState

logger = logging.getLogger(__name__)


def _extract_response_text(result: Dict[str, Any]) -> str:
    """Pull the human-readable response from an orchestrator result dict."""
    for key in ("response", "message", "text", "output"):
        value = result.get(key)
        if value and isinstance(value, str):
            return value
    return str(result)


def _extract_routing_metadata(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract non-response metadata (agent used, timing, etc.) from result."""
    skip = {"response", "message", "text", "output"}
    meta = {k: v for k, v in result.items() if k not in skip}
    return meta if meta else None


async def execute_a2a_task(
    task_id: str,
    input_text: str,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Execute an A2A task via the existing AgentOrchestrator.

    Lifecycle:
      SUBMITTED → WORKING → (adds text + metadata artifacts) → COMPLETED
                                                              → FAILED

    This function is intentionally fire-and-forget (called via BackgroundTasks).
    """
    manager = get_task_manager()
    manager.update_state(task_id, TaskState.WORKING)

    try:
        # Late import to avoid circular deps at module load time
        from agents.agent_orchestrator import get_agent_orchestrator

        orchestrator = get_agent_orchestrator()
        result: Dict[str, Any] = await orchestrator.process_request(
            input_text,
            context=context,
        )

        # Artifact 1: primary text response
        response_text = _extract_response_text(result)
        manager.add_artifact(
            task_id,
            TaskArtifact(artifact_type="text", content=response_text),
        )

        # Artifact 2: routing metadata (agent used, model, timing, etc.)
        metadata = _extract_routing_metadata(result)
        if metadata:
            manager.add_artifact(
                task_id,
                TaskArtifact(artifact_type="json", content=metadata),
            )

        manager.update_state(task_id, TaskState.COMPLETED)
        logger.info("A2A task %s completed successfully", task_id)

    except Exception as exc:
        logger.error("A2A task %s failed: %s", task_id, exc)
        manager.add_artifact(
            task_id,
            TaskArtifact(artifact_type="error", content=str(exc)),
        )
        manager.update_state(task_id, TaskState.FAILED, message=str(exc))
