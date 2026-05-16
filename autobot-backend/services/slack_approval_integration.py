# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Slack Approval Integration with Redis Error Handling (#4163)

Provides Slack integration for approval workflow tracking with robust error handling
for Redis operations. Includes circuit breaker for persistent Redis failures.

Usage::

    from services.slack_approval_integration import SlackApprovalManager

    mgr = SlackApprovalManager()
    thread_id = await mgr.store_approval_thread(
        node_id="node-123",
        workflow_id="wf-abc",
        channel_id="C123456",
    )
    approval = await mgr.load_approval_thread(thread_id)
"""

import json
import time
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from circuit_breaker import CircuitState

logger = get_logger(__name__)

# Redis database and key prefixes
_APPROVAL_REDIS_DB = "main"
_APPROVAL_THREAD_PREFIX = "approval_thread"
_CHANNEL_MAPPING_PREFIX = "slack_channel_mapping"
_APPROVAL_CIRCUIT_BREAKER_PREFIX = "approval_redis_circuit"
_APPROVAL_TTL_SECONDS = 86400  # 24 hours


class SlackApprovalManager:
    """
    Manages Slack approval thread tracking with Redis backend and circuit breaker.

    Wraps all Redis operations with try/except to gracefully degrade if Redis is
    unavailable. Uses a circuit breaker pattern to avoid repeated failures.
    """

    # Circuit breaker thresholds
    _FAILURE_THRESHOLD = 3  # Failures before opening circuit
    _RECOVERY_TIMEOUT = 60  # Seconds before attempting to recover
    _HALF_OPEN_TIMEOUT = 30  # Seconds for half-open testing window

    def __init__(self) -> None:
        """Initialize the Slack approval manager."""
        self._circuit_state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0

    async def store_approval_thread(
        self,
        node_id: str,
        workflow_id: str,
        channel_id: str,
        thread_ts: str | None = None,
        approval_context: Dict[str, Any] | None = None,
    ) -> str | None:
        """
        Store approval thread metadata in Redis.

        Args:
            node_id: Node executing the approval workflow
            workflow_id: Workflow requesting approval
            channel_id: Slack channel for the approval thread
            thread_ts: Slack thread timestamp (if replying to existing thread)
            approval_context: Additional context dict (approval_type, required_approvers, etc.)

        Returns:
            Thread ID on success, None if Redis is unavailable or circuit is open.
            Logs warnings/errors but does not raise.
        """
        if not self._should_attempt_redis_op():
            logger.warning(
                "Skipping Redis store_approval_thread (circuit=%s, failures=%d)",
                self._circuit_state,
                self._failure_count,
            )
            return None

        thread_id = f"{node_id}:{workflow_id}:{int(time.time())}"
        record: Dict[str, Any] = {
            "thread_id": thread_id,
            "node_id": node_id,
            "workflow_id": workflow_id,
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "created_at": time.time(),
            "context": approval_context or {},
        }

        try:
            client = await get_redis_client(async_client=True, database=_APPROVAL_REDIS_DB)
            if client is None:
                self._record_redis_failure("store_approval_thread", "Redis client is None")
                return None

            key = f"{_APPROVAL_THREAD_PREFIX}:{thread_id}"
            serialized = json.dumps(record)
            await client.set(key, serialized, ex=_APPROVAL_TTL_SECONDS)
            self._record_redis_success()
            logger.info(
                "Stored approval thread %s (node=%s, workflow=%s, channel=%s)",
                thread_id,
                node_id,
                workflow_id,
                channel_id,
            )
            return thread_id
        except Exception as exc:
            self._record_redis_failure("store_approval_thread", str(exc))
            logger.error(
                "Failed to store approval thread for node=%s workflow=%s: %s",
                node_id,
                workflow_id,
                exc,
            )
            return None

    async def load_approval_thread(self, thread_id: str) -> Dict[str, Any] | None:
        """
        Load approval thread metadata from Redis.

        Args:
            thread_id: Thread ID to retrieve

        Returns:
            Approval thread dict on success, None if not found or Redis unavailable.
            Logs warnings/errors but does not raise.
        """
        if not self._should_attempt_redis_op():
            logger.warning(
                "Skipping Redis load_approval_thread (circuit=%s, failures=%d)",
                self._circuit_state,
                self._failure_count,
            )
            return None

        try:
            client = await get_redis_client(async_client=True, database=_APPROVAL_REDIS_DB)
            if client is None:
                self._record_redis_failure("load_approval_thread", "Redis client is None")
                return None

            key = f"{_APPROVAL_THREAD_PREFIX}:{thread_id}"
            raw = await client.get(key)
            if raw is None:
                logger.warning("Approval thread %s not found in Redis", thread_id)
                return None

            record = json.loads(raw)
            self._record_redis_success()
            logger.debug("Loaded approval thread %s", thread_id)
            return record
        except json.JSONDecodeError as exc:
            logger.error("Malformed JSON in approval thread %s: %s", thread_id, exc)
            return None
        except Exception as exc:
            self._record_redis_failure("load_approval_thread", str(exc))
            logger.error("Failed to load approval thread %s: %s", thread_id, exc)
            return None

    async def manage_channel_mapping(
        self,
        workspace_id: str,
        workflow_name: str,
        channel_id: str,
        operation: str = "set",
    ) -> bool:
        """
        Store or retrieve Slack channel mapping for workflow approvals.

        Tracks which Slack channel approvals for a given workflow should be posted to.
        Used to ensure all approvals for a workflow go to the same channel.

        Args:
            workspace_id: Slack workspace ID
            workflow_name: Workflow name/identifier
            channel_id: Slack channel ID
            operation: "set" to store mapping, "get" to retrieve

        Returns:
            True if successful, False if Redis unavailable.
            Logs warnings/errors but does not raise.
        """
        if not self._should_attempt_redis_op():
            logger.warning(
                "Skipping Redis manage_channel_mapping (circuit=%s, failures=%d)",
                self._circuit_state,
                self._failure_count,
            )
            return False

        try:
            client = await get_redis_client(async_client=True, database=_APPROVAL_REDIS_DB)
            if client is None:
                self._record_redis_failure("manage_channel_mapping", "Redis client is None")
                return False

            mapping_key = f"{_CHANNEL_MAPPING_PREFIX}:{workspace_id}:{workflow_name}"

            if operation == "set":
                mapping_data = json.dumps(
                    {
                        "channel_id": channel_id,
                        "mapped_at": time.time(),
                    }
                )
                await client.set(mapping_key, mapping_data, ex=_APPROVAL_TTL_SECONDS)
                self._record_redis_success()
                logger.info(
                    "Set channel mapping for workflow %s in workspace %s -> %s",
                    workflow_name,
                    workspace_id,
                    channel_id,
                )
                return True
            elif operation == "get":
                raw = await client.get(mapping_key)
                if raw is None:
                    logger.debug(
                        "No channel mapping found for workflow %s in workspace %s",
                        workflow_name,
                        workspace_id,
                    )
                    return False
                mapping_data = json.loads(raw)
                self._record_redis_success()
                logger.debug(
                    "Retrieved channel mapping for workflow %s in workspace %s",
                    workflow_name,
                    workspace_id,
                )
                return True
            else:
                logger.warning("Unknown manage_channel_mapping operation: %s", operation)
                return False
        except json.JSONDecodeError as exc:
            logger.error(
                "Malformed JSON in channel mapping for %s:%s: %s",
                workspace_id,
                workflow_name,
                exc,
            )
            return False
        except Exception as exc:
            self._record_redis_failure("manage_channel_mapping", str(exc))
            logger.error(
                "Failed to manage channel mapping for %s:%s: %s",
                workspace_id,
                workflow_name,
                exc,
            )
            return False

    # -----------------------------------------------------------------------
    # Circuit breaker implementation
    # -----------------------------------------------------------------------

    def _should_attempt_redis_op(self) -> bool:
        """Check if a Redis operation should be attempted based on circuit state."""
        now = time.time()

        if self._circuit_state == CircuitState.CLOSED:
            return True
        elif self._circuit_state == CircuitState.OPEN:
            # Try to recover after recovery timeout
            if now - self._last_failure_time >= self._RECOVERY_TIMEOUT:
                self._circuit_state = CircuitState.HALF_OPEN
                self._failure_count = 0
                logger.info("Circuit breaker entering HALF_OPEN state")
                return True
            return False
        elif self._circuit_state == CircuitState.HALF_OPEN:
            # In half-open: allow operation, will transition to CLOSED or OPEN
            # Reset half-open timeout if too long has passed
            if now - self._last_failure_time >= self._RECOVERY_TIMEOUT + (self._HALF_OPEN_TIMEOUT):
                self._circuit_state = CircuitState.OPEN
                logger.warning("Circuit breaker timeout — returning to OPEN state")
                return False
            return True
        return False

    def _record_redis_success(self) -> None:
        """Record a successful Redis operation."""
        if self._circuit_state == CircuitState.HALF_OPEN:
            self._circuit_state = CircuitState.CLOSED
            self._failure_count = 0
            logger.info("Circuit breaker returning to CLOSED state")
        elif self._circuit_state == CircuitState.CLOSED:
            self._failure_count = max(0, self._failure_count - 1)

    def _record_redis_failure(self, operation: str, error_msg: str) -> None:
        """Record a failed Redis operation and update circuit state."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._failure_count >= self._FAILURE_THRESHOLD:
            if self._circuit_state != CircuitState.OPEN:
                self._circuit_state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker OPEN after %d failures (last: %s: %s)",
                    self._failure_count,
                    operation,
                    error_msg,
                )
