# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shared In-Flight Workflow Memory

Issue #3019: When WorkflowExecutor runs parallel steps via asyncio.gather(),
each agent has isolated context.  WorkflowMemory provides a lightweight shared
KV store so parallel steps running inside a single workflow can collaborate —
one step can publish a finding and a peer step (or a later step) can read it.

Architecture
------------
Each workflow gets a Redis Hash keyed as::

    workflow:memory:<workflow_id>

All values are JSON-serialised.  The hash expires automatically after
``ttl_seconds`` (default 1 hour) so stale entries never accumulate.

Usage example inside a step executor
-------------------------------------
::

    memory = WorkflowMemory(workflow_id="wf-abc123")
    memory.set("scan_result", {"open_ports": [22, 80]})

    # in a parallel peer step:
    data = memory.get("scan_result")          # {"open_ports": [22, 80]}

    # after the workflow completes:
    memory.clear()

Thread / async safety
---------------------
The underlying Redis Hash operations (HSET, HGET, HGETALL, HDEL, DEL, EXPIRE)
are each atomic on the Redis side.  Concurrent asyncio tasks writing different
keys into the same hash will not corrupt each other.  Writes to the *same* key
from two concurrent tasks are last-writer-wins — callers are responsible for
ensuring they do not race on a single key when ordering matters.
"""

import json
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from constants.ttl_constants import TTL_1_HOUR

logger = get_logger(__name__)

# Redis key prefix — mirrors the autobot:workflow:checkpoint: convention from
# error_handler.py so all workflow keys share the same namespace.
MEMORY_KEY_PREFIX = "workflow:memory:"

# Default TTL matches a typical long-running workflow session (1 hour).
DEFAULT_TTL_SECONDS = TTL_1_HOUR


class WorkflowMemory:
    """
    Lightweight shared KV store for in-flight workflow collaboration.

    Backed by a Redis Hash so all parallel steps in a single workflow can
    read and write a common key space without locking.  The hash expires
    automatically via a TTL so no manual cleanup is required unless you want
    to release memory earlier.

    Key layout::

        workflow:memory:<workflow_id>  →  Redis Hash
            field = arbitrary string key
            value = JSON-serialised Python value

    Issue #3019.
    """

    def __init__(self, workflow_id: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        """
        Initialise memory for *workflow_id*.

        Args:
            workflow_id:   Unique identifier of the running workflow.
            ttl_seconds:   Seconds after the last write before the hash
                           expires.  Defaults to 3600 (1 hour).
        """
        if not workflow_id:
            raise ValueError("workflow_id must be a non-empty string")
        self._workflow_id = workflow_id
        self._ttl = ttl_seconds
        self._redis: Any = None
        self._redis_key = f"{MEMORY_KEY_PREFIX}{workflow_id}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_redis(self) -> Any:
        """Lazy-initialise a synchronous Redis client for the workflows DB."""
        if self._redis is None:
            self._redis = get_redis_client(async_client=False, database="workflows")
        return self._redis

    def _refresh_ttl(self, redis: Any) -> None:
        """Re-arm the hash TTL after every mutating operation."""
        try:
            redis.expire(self._redis_key, self._ttl)
        except Exception as exc:
            logger.warning(
                "WorkflowMemory %s: failed to refresh TTL: %s",
                self._workflow_id,
                exc,
            )

    @staticmethod
    def _decode(raw: Any) -> str:
        """Decode bytes → str when Redis returns bytes."""
        return raw.decode("utf-8") if isinstance(raw, bytes) else raw

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set(self, key: str, value: Any) -> None:
        """
        Store *value* under *key* in this workflow's shared memory.

        *value* is JSON-serialised; any JSON-compatible Python object is
        accepted (dict, list, str, int, float, bool, None).

        The hash TTL is refreshed on every successful write.

        Args:
            key:   Arbitrary string key — must be non-empty.
            value: JSON-serialisable value to store.

        Issue #3019.
        """
        if not key:
            raise ValueError("key must be a non-empty string")
        redis = self._get_redis()
        try:
            redis.hset(self._redis_key, key, json.dumps(value))
            self._refresh_ttl(redis)
            logger.debug(
                "WorkflowMemory %s: set key=%r",
                self._workflow_id,
                key,
            )
        except Exception as exc:
            logger.error(
                "WorkflowMemory %s: failed to set key=%r: %s",
                self._workflow_id,
                key,
                exc,
            )
            raise

    def get(self, key: str, default: Any | None = None) -> Any:
        """
        Retrieve the value stored under *key*, or *default* if absent.

        Args:
            key:     Key to look up.
            default: Returned when *key* is not present (default: None).

        Returns:
            The deserialised Python value, or *default*.

        Issue #3019.
        """
        redis = self._get_redis()
        try:
            raw = redis.hget(self._redis_key, key)
        except Exception as exc:
            logger.error(
                "WorkflowMemory %s: failed to get key=%r: %s",
                self._workflow_id,
                key,
                exc,
            )
            return default

        if raw is None:
            return default

        try:
            return json.loads(self._decode(raw))
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "WorkflowMemory %s: corrupt value for key=%r: %s",
                self._workflow_id,
                key,
                exc,
            )
            return default

    def get_all(self) -> Dict[str, Any]:
        """
        Return all KV pairs stored in this workflow's shared memory.

        Returns an empty dict when the hash does not exist or Redis is
        unavailable.

        Issue #3019.
        """
        redis = self._get_redis()
        try:
            raw_map = redis.hgetall(self._redis_key)
        except Exception as exc:
            logger.error(
                "WorkflowMemory %s: failed to get_all: %s",
                self._workflow_id,
                exc,
            )
            return {}

        result: Dict[str, Any] = {}
        for raw_key, raw_value in raw_map.items():
            str_key = self._decode(raw_key)
            str_value = self._decode(raw_value)
            try:
                result[str_key] = json.loads(str_value)
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning(
                    "WorkflowMemory %s: corrupt value for key=%r in get_all: %s",
                    self._workflow_id,
                    str_key,
                    exc,
                )
        return result

    def delete(self, key: str) -> bool:
        """
        Remove *key* from this workflow's shared memory.

        Args:
            key: Key to remove.

        Returns:
            True if the key existed and was removed, False if it was absent.

        Issue #3019.
        """
        redis = self._get_redis()
        try:
            removed = redis.hdel(self._redis_key, key)
            existed = bool(removed)
            logger.debug(
                "WorkflowMemory %s: delete key=%r existed=%s",
                self._workflow_id,
                key,
                existed,
            )
            return existed
        except Exception as exc:
            logger.error(
                "WorkflowMemory %s: failed to delete key=%r: %s",
                self._workflow_id,
                key,
                exc,
            )
            raise

    def clear(self) -> None:
        """
        Remove the entire shared memory hash for this workflow.

        Called automatically by WorkflowExecutor on full completion, or
        explicitly by callers who want to release memory early.

        Issue #3019.
        """
        redis = self._get_redis()
        try:
            redis.delete(self._redis_key)
            logger.debug("WorkflowMemory %s: cleared", self._workflow_id)
        except Exception as exc:
            logger.error(
                "WorkflowMemory %s: failed to clear: %s",
                self._workflow_id,
                exc,
            )
            raise
