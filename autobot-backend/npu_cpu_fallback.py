# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""CPU fallback search for the NPU semantic search: retry a transient failure, surface any other. #21799."""

import os
from typing import Any, Dict, List, Optional, Tuple

from autobot_shared.embedding_model import EmbeddingUnavailableError
from autobot_shared.logging_manager import get_llm_logger
from autobot_shared.retry_mechanism import RETRYABLE_EXCEPTIONS, RetryExhaustedError, RetryMechanism, RetryPolicy

logger = get_llm_logger(__name__)

# Override via AUTOBOT_NPU_CPU_FALLBACK_ATTEMPTS and AUTOBOT_NPU_CPU_FALLBACK_RETRY_DELAY (seconds).
CPU_FALLBACK_ATTEMPTS = int(os.environ.get("AUTOBOT_NPU_CPU_FALLBACK_ATTEMPTS", "3"))
CPU_FALLBACK_RETRY_DELAY = float(os.environ.get("AUTOBOT_NPU_CPU_FALLBACK_RETRY_DELAY", "0.5"))

# EmbeddingUnavailableError is how a transient embedding failure surfaces (the model produced no vector); it carries
# no transient/permanent flag, so it is retried within the same attempt cap. A missing file or a permission error is
# an OSError that no retry cures. ValueError and TypeError stay non-retryable via the policy default.
_NON_RETRYABLE = RetryPolicy().non_retryable_exceptions + (FileNotFoundError, PermissionError)

_POLICY = RetryPolicy(
    max_attempts=CPU_FALLBACK_ATTEMPTS,
    base_delay=CPU_FALLBACK_RETRY_DELAY,
    retryable_exceptions=RETRYABLE_EXCEPTIONS + (EmbeddingUnavailableError,),
    non_retryable_exceptions=_NON_RETRYABLE,
)


class CpuFallbackExhaustedError(RetryExhaustedError):
    """The CPU fallback used its whole retry budget; a caller must not run another CPU cycle."""


async def cpu_search(knowledge_base: Any, query: str, top_k: int, filters: Optional[Dict[str, Any]]) -> List[Any]:
    """KB search on the CPU backend; transient failures are retried, any other error is raised."""
    try:
        return await RetryMechanism(_POLICY).execute_async(
            knowledge_base.search, query, top_k=top_k, filters=filters, hardware_backend="cpu"
        )
    except RetryExhaustedError as exc:
        raise CpuFallbackExhaustedError(exc.attempts, exc.last_exception) from exc


async def cpu_search_or_error(
    knowledge_base: Any, query: str, top_k: int, filters: Optional[Dict[str, Any]], prior: Optional[Exception] = None
) -> Tuple[List[Any], Optional[str]]:
    """Like cpu_search, but a failure comes back as ([], reason) for the caller's error metric.

    ``prior`` is the error that sent the caller here: one that already spent the CPU retry budget is
    reported as is, so one search runs one bounded CPU cycle, not two.
    """
    if isinstance(prior, CpuFallbackExhaustedError):
        return [], f"CPU fallback failed: {prior}"
    try:
        return await cpu_search(knowledge_base, query, top_k, filters), None
    except Exception as exc:
        logger.error("CPU fallback search failed: %s", exc)
        return [], f"CPU fallback failed: {exc}"
