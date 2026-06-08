# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Deprecated request-handling API extracted from orchestrator.py (#5060).

These methods have no live callers (GH#7423).  They are preserved here as a
mixin so Orchestrator maintains API compatibility without inflating its line
count.
"""

import time
import uuid
import warnings
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from autobot_types import TaskComplexity
from constants.threshold_constants import LLMDefaults
from task_execution_tracker import Priority, TaskType, get_task_tracker

logger = get_logger(__name__)


class _DeprecatedRequestMixin:
    """Mixin providing the deprecated process_user_request API.

    Inherited by Orchestrator for backward compatibility only.
    All methods here have zero live callers as of GH#7423.
    """

    def _start_request_tracking(self, task_id, user_message, priority, context) -> None:
        get_task_tracker().start_task(
            task_id=task_id,
            task_type=TaskType.USER_REQUEST,
            description=user_message[:200],
            priority=Priority(priority.value),
            context=context or {},
        )

    def _update_success_metrics(self, processing_time: float) -> None:
        self.metrics["tasks_completed"] += 1
        self.metrics["total_processing_time"] += processing_time
        self.metrics["average_response_time"] = self.metrics["total_processing_time"] / self.metrics["tasks_completed"]

    async def process_user_request(
        self,
        user_message: str,
        conversation_id: str | None = None,
        mode=None,
        priority=None,
        context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Process user request.

        .. deprecated::
            No live callers exist. Call execute_enhanced_workflow directly (GH#7423).
        """
        from autobot_shared.status_enums import Priority as TaskPriority
        from orchestrator import OrchestrationMode

        if mode is None:
            mode = OrchestrationMode.ENHANCED
        if priority is None:
            priority = TaskPriority.NORMAL

        warnings.warn(
            "process_user_request is deprecated and has no live callers — use execute_enhanced_workflow directly. (GH#7423)",  # noqa: E501
            DeprecationWarning,
            stacklevel=2,
        )
        start_time = time.time()
        task_id = str(uuid.uuid4())
        logger.info("Processing user request %s: %s...", task_id, user_message[:100])

        try:
            self._start_request_tracking(task_id, user_message, priority, context)
            classification_result = await self._classify_task(user_message)
            target_llm_model = self._select_model_for_task(classification_result)

            if mode == OrchestrationMode.SIMPLE:
                result = await self._process_simple_request(user_message, task_id, target_llm_model, context)
            else:
                result = await self.execute_enhanced_workflow(user_request=user_message, context=context or {})

            processing_time = time.time() - start_time
            self._update_success_metrics(processing_time)
            get_task_tracker().complete_task(task_id, result)
            logger.info("✅ Request %s completed in %.2fs", task_id, processing_time)
            return {
                "task_id": task_id,
                "success": True,
                "result": result,
                "processing_time": processing_time,
                "classification": classification_result.to_dict() if classification_result else None,
                "model_used": target_llm_model,
                "mode": mode.value,
            }
        except Exception as e:
            processing_time = time.time() - start_time
            self.metrics["tasks_failed"] += 1
            get_task_tracker().fail_task(task_id, str(e))
            logger.error("❌ Request %s failed after %.2fs: %s", task_id, processing_time, e)
            return {
                "task_id": task_id,
                "success": False,
                "error": str(e),
                "processing_time": processing_time,
                "mode": mode.value,
            }

    async def _classify_task(self, user_message: str) -> Any | None:
        if not self.classification_agent:
            return None
        try:
            result = await self.classification_agent.classify_user_request(user_message)
            logger.info("Task classified: %s complexity", result.complexity.value)
            return result
        except Exception as e:
            logger.warning("Classification failed: %s", e)
            return None

    def _select_model_for_task(self, classification_result: Any | None) -> str:
        if classification_result and classification_result.complexity == TaskComplexity.SIMPLE:
            from config.manager import get_config_manager

            model = get_config_manager().get_default_llm_model()
            logger.info("Using fast model for simple task: %s", model)
            return model
        return self.config.orchestrator_llm_model

    async def _process_simple_request(
        self, user_message: str, task_id: str, model: str, context: Dict | None
    ) -> Dict[str, Any]:
        response = await self.llm_service.chat(
            [{"role": "user", "content": user_message}],
            model_name=model,
            max_tokens=LLMDefaults.ENRICHED_MAX_TOKENS,
            context=context,
        )
        return {"type": "simple_response", "content": response.content, "sources": [{"type": "llm", "model": model}]}
