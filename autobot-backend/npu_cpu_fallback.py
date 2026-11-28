# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""CPU fallback search for the NPU semantic search: retry a transient failure, surface any other. #21799."""

import os
from typing import Any, Dict, List, Optional, Tuple

from autobot_shared.logging_manager import get_llm_logger
from autobot_shared.retry_mechanism import RETRYABLE_EXCEPTIONS, RetryMechanism, RetryPolicy

logger = get_llm_logger(__name__)

# Override via AUTOBOT_NPU_CPU_FALLBACK_ATTEMPTS and AUTOBOT_NPU_CPU_FALLBACK_RETRY_DELAY (seconds).
CPU_FALLBACK_ATTEMPTS = int(os.environ.get("AUTOBOT_NPU_CPU_FALLBACK_ATTEMPTS", "3"))
CPU_FALLBACK_RETRY_DELAY = float(os.environ.get("AUTOBOT_NPU_CPU_FALLBACK_RETRY_DELAY", "0.5"))

_POLICY = RetryPolicy(
    max_attempts=CPU_FALLBACK_ATTEMPTS,
    base_delay=CPU_FALLBACK_RETRY_DELAY,
    retryable_exceptions=RETRYABLE_EXCEPTIONS,
)


async def cpu_search(knowledge_base: Any, query: str, top_k: int, filters: Optional[Dict[str, Any]]) -> List[Any]:
    """KB search on the CPU backend; transient failures are retried, any other error is raised."""
    return await RetryMechanism(_POLICY).execute_async(
        knowledge_base.search, query, top_k=top_k, filters=filters, hardware_backend="cpu"
    )


async def cpu_search_or_error(
    knowledge_base: Any, query: str, top_k: int, filters: Optional[Dict[str, Any]]
) -> Tuple[List[Any], Optional[str]]:
    """Like cpu_search, but a failure comes back as ([], reason) for the caller's error metric."""
    try:
        return await cpu_search(knowledge_base, query, top_k, filters), None
    except Exception as exc:
        logger.error("CPU fallback search failed: %s", exc)
        return [], f"CPU fallback failed: {exc}"
