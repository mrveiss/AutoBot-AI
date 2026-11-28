# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""CPU fallback search for the NPU semantic search: retry a transient failure, surface any other. #21799."""

from typing import Any, Dict, List, Optional, Tuple

from autobot_shared.embedding_model import EmbeddingUnavailableError
from autobot_shared.env_utils import env_float_clamped, env_int_clamped
from autobot_shared.logging_manager import get_llm_logger
from autobot_shared.retry_mechanism import RETRYABLE_EXCEPTIONS, RetryExhaustedError, RetryMechanism, RetryPolicy

logger = get_llm_logger(__name__)

# Override via AUTOBOT_NPU_CPU_FALLBACK_ATTEMPTS and AUTOBOT_NPU_CPU_FALLBACK_RETRY_DELAY (seconds).
# A blank or malformed value gets the default; attempts below 1 clamp to 1, a delay is clamped to [0, 60] (NaN/inf too).
CPU_FALLBACK_ATTEMPTS = env_int_clamped("AUTOBOT_NPU_CPU_FALLBACK_ATTEMPTS", 3, min_v=1, max_v=10)
CPU_FALLBACK_RETRY_DELAY = env_float_clamped("AUTOBOT_NPU_CPU_FALLBACK_RETRY_DELAY", 0.5, min_v=0.0, max_v=60.0)

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


class CpuFallbackError(Exception):
    """A failure that escaped a CPU fallback cycle; a caller must not start another cycle for it."""

    def __init__(self, cause: BaseException, message: Optional[str] = None):
        """Carry the cause; the message defaults to the cause's own text."""
        super().__init__(message if message is not None else str(cause))
        self.cause = cause


class CpuFallbackExhaustedError(CpuFallbackError):
    """The CPU fallback used its whole retry budget."""


async def cpu_search(knowledge_base: Any, query: str, top_k: int, filters: Optional[Dict[str, Any]]) -> List[Any]:
    """KB search on the CPU backend; transient failures are retried, any failure is raised as CpuFallbackError."""
    try:
        return await RetryMechanism(_POLICY).execute_async(
            knowledge_base.search, query, top_k=top_k, filters=filters, hardware_backend="cpu"
        )
    except RetryExhaustedError as exc:
        raise CpuFallbackExhaustedError(exc.last_exception, str(exc)) from exc
    except Exception as exc:
        raise CpuFallbackError(exc) from exc


async def cpu_search_or_error(
    knowledge_base: Any, query: str, top_k: int, filters: Optional[Dict[str, Any]], prior: Optional[Exception] = None
) -> Tuple[List[Any], Optional[str]]:
    """Like cpu_search, but a failure comes back as ([], reason) for the caller's error metric.

    ``prior`` is the error that sent the caller here: one that came out of a CPU cycle (exhausted or
    not) is reported as is, so one search runs one bounded CPU cycle, not two.
    """
    if isinstance(prior, CpuFallbackError):
        return [], f"CPU fallback failed: {prior}"
    try:
        return await cpu_search(knowledge_base, query, top_k, filters), None
    except Exception as exc:
        logger.error("CPU fallback search failed: %s", exc)
        return [], f"CPU fallback failed: {exc}"
