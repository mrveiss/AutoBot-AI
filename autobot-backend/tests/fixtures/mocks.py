# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Mock fixtures for AutoBot backend testing (canonical location for #6994).

Provides mock implementations of core components for tests and the
`__main__` demo blocks under `intelligence/`:

- MockLLMInterface  - Mock for UnifiedLLMInterface (llm_multi_provider); covers
                      both chat_completion() and legacy generate_response().
- MockLLMService    - Mock matching the LLMService surface that replaced
                      LLMInterface in #3185. Returns LLMResponse-shaped
                      objects via `.chat(...)` so demos exercising
                      `IntelligentAgent` / `StreamingCommandExecutor`
                      run offline without network calls.
- MockCommandValidator - Mock validator for command safety testing.
- MockKnowledgeBase    - In-memory knowledge base for testing.
- MockWorkerNode       - Mock NPU/worker node for distributed-flow tests.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List


class MockLLMInterface:
    """Mock for ``UnifiedLLMInterface`` (``llm_multi_provider.UnifiedLLMInterface``).

    Covers the full surface of ``UnifiedLLMInterface``: both the primary
    ``chat_completion()`` method and the legacy ``generate_response()`` shim.
    New test code should prefer ``MockLLMService`` (which mocks the canonical
    ``LLMService.chat()`` surface); this class is retained for tests that
    still exercise ``UnifiedLLMInterface`` directly.
    """

    def __init__(self, responses: Dict[str, str] | None = None):
        self._custom_responses = responses or {}
        self._call_count = 0
        self._call_history: list = []

    def _pick_response(self, prompt: str) -> str:
        for keyword, response in self._custom_responses.items():
            if keyword.lower() in prompt.lower():
                return response
        prompt_lower = prompt.lower()
        if "progress" in prompt_lower:
            return "Processing data..."
        if "completion" in prompt_lower:
            return "Task completed successfully!"
        if "command" in prompt_lower:
            return "COMMAND: echo 'This is a test response'\nEXPLANATION: Testing the system"
        return "Command executing..."

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> Any:
        """Mock primary method matching ``UnifiedLLMInterface.chat_completion``."""
        prompt = messages[-1].get("content", "") if messages else ""
        self._call_count += 1
        self._call_history.append({"prompt": prompt, "kwargs": kwargs})
        return make_llm_response(content=self._pick_response(prompt))

    async def generate_response(self, prompt: str, **kwargs: Any) -> str:
        """Legacy shim matching ``UnifiedLLMInterface.generate_response``."""
        self._call_count += 1
        self._call_history.append({"prompt": prompt, "kwargs": kwargs})
        return self._pick_response(prompt)

    async def initialize(self) -> None:
        """No-op — matches ``UnifiedLLMInterface.initialize``."""

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def call_history(self) -> list:
        return self._call_history

    def reset(self) -> None:
        self._call_count = 0
        self._call_history = []


@dataclass
class _MockLLMResponseShim:
    """Duck-typed fallback if `llm_shared.models.LLMResponse` is
    unavailable at import time. Matches the fields agents/cognifiers read
    (`.content`, `.model`, `.provider`)."""

    content: str
    model: str = "mock"
    provider: str = "mock"
    tokens_used: int | None = None
    processing_time: float = 0.0
    cached: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    usage: Dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
    request_id: str = ""
    error: str | None = None


def make_llm_response(
    *,
    content: str = "",
    error: str | None = None,
    model: str = "mock",
    provider: str = "mock",
):
    """Build an LLMResponse-shaped value for tests (canonical, #7134).

    Returns the real ``LLMResponse`` from ``llm_shared.models`` when
    importable — that pins the field contract, so a future field rename or
    type change breaks the fixture (and every test that uses it) at import
    time rather than silently producing wrong-shape mocks. Falls back to a
    duck-typed shim when the real module isn't available (e.g. during
    `tests/fixtures/` collection in a stripped-down environment).

    All arguments are keyword-only — positional args would invite the same
    field-shape drift the lesson in
    ``feedback_verify_return_shape_in_method_migration.md`` is about.

    Replaces the 7+ ad-hoc patterns surfaced in #7134:
      - ``_StubResponse`` / ``_MockLLMResponseShim`` private classes
      - ``MagicMock(content=..., error=None)`` inline forms
      - ``_make_llm_response(content)`` factories
      - ``MagicMock(content=...)`` without explicit error= field

    Args:
        content: ``LLMResponse.content`` value.
        error: ``LLMResponse.error`` value (None for healthy responses).
        model: provider model name; defaults to ``"mock"``.
        provider: provider name; defaults to ``"mock"``.
    """
    try:
        from llm_shared.models import LLMResponse

        return LLMResponse(content=content, error=error, model=model, provider=provider)
    except Exception:
        return _MockLLMResponseShim(content=content, error=error, model=model, provider=provider)


# Back-compat alias — internal callers still reference the underscore name.
# New code should use `make_llm_response` directly.
def _build_mock_response(content: str):
    return make_llm_response(content=content)


def make_redis_pipeline(execute_returns: Any = None) -> "AsyncMock":
    """Build an async-redis pipeline mock (canonical, #7339).

    Supports both common pipeline usage patterns:

    1. **Async context manager** —
       ``async with redis.pipeline() as pipe: pipe.X(...); await pipe.execute()``
    2. **Direct caller** —
       ``pipe = redis.pipeline(); pipe.X(...); result = await pipe.execute()``

    Buffered ops (``xadd``, ``hset``, etc.) are auto-created child
    AsyncMocks via the parent's child-spawning behavior — sufficient for
    both ``pipe.X(...)`` (returns coroutine, ignored by buffered code that
    doesn't await) and ``await pipe.X(...)`` (returns AsyncMock from the
    awaited coroutine).

    ``pipe.execute()`` is async (always awaited in production).

    Args:
        execute_returns: value returned by ``await pipe.execute()``.
            Default ``[]`` if ``None``. Pass a list of per-op results to
            simulate multi-op pipeline returns (e.g. ``[1, 1, 1]`` for
            three writes).

    Returns:
        An ``AsyncMock`` representing a redis pipeline.
    """
    from unittest.mock import AsyncMock

    pipe = AsyncMock()
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock(return_value=False)
    pipe.execute = AsyncMock(return_value=execute_returns if execute_returns is not None else [])
    return pipe


def make_async_redis(
    *,
    get_returns: Any = None,
    set_returns: Any = True,
    setex_returns: Any = True,
    delete_returns: int = 1,
    expire_returns: bool = True,
    exists_returns: int = 0,
    incr_returns: int = 1,
    decr_returns: int = 0,
    keys_returns: List[bytes] | None = None,
    ttl_returns: int = -1,
    # Hash ops
    hget_returns: Any = None,
    hset_returns: int = 1,
    hgetall_returns: Dict[bytes, bytes] | None = None,
    hkeys_returns: List[bytes] | None = None,
    hvals_returns: List[bytes] | None = None,
    hdel_returns: int = 1,
    hexists_returns: int = 0,
    # Set ops
    sadd_returns: int = 1,
    srem_returns: int = 1,
    smembers_returns: set | None = None,
    sismember_returns: bool = False,
    # List ops
    lrange_returns: List[bytes] | None = None,
    lpush_returns: int = 1,
    rpush_returns: int = 1,
    llen_returns: int = 0,
    # Sorted-set ops
    zadd_returns: int = 1,
    zcard_returns: int = 0,
    zrange_returns: List[bytes] | None = None,
    zrangebyscore_returns: List[bytes] | None = None,
    zrevrange_returns: List[bytes] | None = None,
    zremrangebyrank_returns: int = 0,
    # Pub/sub
    publish_returns: int = 0,
    # Pipeline + scan-iter (#7339)
    pipeline: "AsyncMock" | None = None,
    scan_iter_keys: List[bytes] | None = None,
    **extra_methods: Any,
) -> "AsyncMock":
    """Build an async-redis-shaped ``AsyncMock`` for tests (canonical, #7264).

    Replaces the 11+ ad-hoc ``_make_redis*()`` helpers across the test
    tree. All redis methods are pre-configured as ``AsyncMock`` so
    ``await redis.X(...)`` works correctly — the same lesson as #7216
    (``return_value=`` alone isn't awaitable).

    Defaults pick the common "empty/healthy" shape:

      - get/hget/hgetall/keys/smembers/lrange/zrange → empty/None
      - set/setex/expire → True
      - sadd/srem/zadd/lpush/rpush/incr/hset/delete → ``1`` (one element changed)
      - sismember/hexists/exists → ``0/False`` (not present)

    Override per call via the corresponding ``X_returns`` kwarg. For methods
    not pre-configured (e.g. project-specific Redis modules), pass via
    ``**extra_methods`` — each becomes ``AsyncMock(return_value=value)``::

        redis = make_async_redis(get_returns=b"hello", xadd=("stream", "1-0"))

    For pipeline support (sync ``redis.pipeline()`` returning an async
    context manager), pass an ``AsyncMock`` built via ``make_redis_pipeline()``
    (#7339)::

        pipe = make_redis_pipeline(execute_returns=[1, 1, 1])
        redis = make_async_redis(pipeline=pipe)

    For ``redis.scan_iter()`` (an async generator, not a coroutine), pass
    a list of keys via ``scan_iter_keys=`` (#7339)::

        redis = make_async_redis(scan_iter_keys=[b"key:1", b"key:2"])

    Args:
        \\*_returns: per-method return value overrides (see method names above).
        pipeline: pre-built pipeline mock (use ``make_redis_pipeline()``).
            Attached as a sync-callable ``redis.pipeline`` returning the mock.
        scan_iter_keys: keys to yield from ``redis.scan_iter(match=…, count=…)``.
            Use ``[]`` for an empty stream (skips override; AsyncMock default).
        \\**extra_methods: arbitrary additional method names → return values.

    Returns:
        An ``AsyncMock`` matching the redis-py async client surface.
    """
    from unittest.mock import AsyncMock, MagicMock

    redis = AsyncMock()

    # Defaults — picks the empty/healthy shape callers usually want.
    redis.get = AsyncMock(return_value=get_returns)
    redis.set = AsyncMock(return_value=set_returns)
    redis.setex = AsyncMock(return_value=setex_returns)
    redis.delete = AsyncMock(return_value=delete_returns)
    redis.expire = AsyncMock(return_value=expire_returns)
    redis.exists = AsyncMock(return_value=exists_returns)
    redis.incr = AsyncMock(return_value=incr_returns)
    redis.decr = AsyncMock(return_value=decr_returns)
    redis.keys = AsyncMock(return_value=keys_returns or [])
    redis.ttl = AsyncMock(return_value=ttl_returns)

    redis.hget = AsyncMock(return_value=hget_returns)
    redis.hset = AsyncMock(return_value=hset_returns)
    redis.hgetall = AsyncMock(return_value=hgetall_returns or {})
    redis.hkeys = AsyncMock(return_value=hkeys_returns or [])
    redis.hvals = AsyncMock(return_value=hvals_returns or [])
    redis.hdel = AsyncMock(return_value=hdel_returns)
    redis.hexists = AsyncMock(return_value=hexists_returns)

    redis.sadd = AsyncMock(return_value=sadd_returns)
    redis.srem = AsyncMock(return_value=srem_returns)
    redis.smembers = AsyncMock(return_value=smembers_returns or set())
    redis.sismember = AsyncMock(return_value=sismember_returns)

    redis.lrange = AsyncMock(return_value=lrange_returns or [])
    redis.lpush = AsyncMock(return_value=lpush_returns)
    redis.rpush = AsyncMock(return_value=rpush_returns)
    redis.llen = AsyncMock(return_value=llen_returns)

    redis.zadd = AsyncMock(return_value=zadd_returns)
    redis.zcard = AsyncMock(return_value=zcard_returns)
    redis.zrange = AsyncMock(return_value=zrange_returns or [])
    redis.zrangebyscore = AsyncMock(return_value=zrangebyscore_returns or [])
    redis.zrevrange = AsyncMock(return_value=zrevrange_returns or [])
    redis.zremrangebyrank = AsyncMock(return_value=zremrangebyrank_returns)

    redis.publish = AsyncMock(return_value=publish_returns)

    # Pipeline support (#7339): redis.pipeline() is SYNC in redis-py, returning
    # a pipeline object whose execute() is async. Wrapping with MagicMock keeps
    # the call sync; the inner pipe is an AsyncMock built by make_redis_pipeline().
    if pipeline is not None:
        redis.pipeline = MagicMock(return_value=pipeline)

    # scan_iter support (#7339): redis.scan_iter() is an ASYNC GENERATOR, not a
    # coroutine. AsyncMock can't directly produce one, so we attach a real
    # async-generator function. Accepts arbitrary kwargs (match, count, _type)
    # so callers passing real redis-py kwargs don't TypeError.
    if scan_iter_keys is not None:
        keys_snapshot = list(scan_iter_keys)

        async def _scan_iter(*_args: Any, **_kwargs: Any):
            for k in keys_snapshot:
                yield k

        redis.scan_iter = _scan_iter

    for method_name, value in extra_methods.items():
        setattr(redis, method_name, AsyncMock(return_value=value))

    return redis


def make_stateful_redis() -> "AsyncMock":
    """Build a stateful async-redis ``AsyncMock`` that tracks stored values (#7753).

    Unlike ``make_async_redis`` (which returns fixed values), this helper
    wires ``set``/``get``/``publish`` to an in-memory ``_store`` dict and
    ``_published`` list so tests can assert on the actual data written:

        fake = make_stateful_redis()
        await fake.set("k", "v")
        assert fake._store["k"] == "v"

        await fake.publish("chan", "msg")
        assert fake._published == [("chan", "msg")]

    All other redis methods remain standard ``AsyncMock`` instances from
    the parent ``AsyncMock``.

    Returns:
        An ``AsyncMock`` with ``_store: dict`` and ``_published: list``
        attributes wired through ``side_effect`` callbacks.
    """
    from unittest.mock import AsyncMock

    fake = AsyncMock()
    fake._store: dict = {}
    fake._published: list = []

    async def _set(key, value, *_args, **_kwargs):
        fake._store[key] = value
        return True

    async def _get(key):
        return fake._store.get(key)

    async def _publish(channel, message):
        fake._published.append((channel, message))
        return 1

    fake.set.side_effect = _set
    fake.get.side_effect = _get
    fake.publish.side_effect = _publish
    return fake


@contextmanager
def patch_async_redis(target: str, redis: "AsyncMock" | None = None):
    """Context manager: patch ``get_async_redis_client`` at ``target`` with
    correct ``AsyncMock`` wrapping (canonical, #7264).

    Production code does ``await get_async_redis_client(database="...")``,
    so the patched callable must itself be an ``AsyncMock`` whose call
    returns the redis mock when awaited. Bare ``patch(target,
    return_value=redis)`` returns the default AsyncMock when awaited —
    that's the #7216 bug. This helper applies the correct shape and
    yields the **inner redis mock** so callers can configure per-call
    behavior::

        with patch_async_redis("api.foo.get_async_redis_client") as redis:
            redis.get = AsyncMock(return_value=b"hit")
            result = await foo()
            redis.get.assert_awaited_once_with("key")

    Or pass a pre-configured redis::

        redis = make_async_redis(get_returns=b"value")
        with patch_async_redis("api.foo.get_async_redis_client", redis=redis):
            ...

    Args:
        target: dotted path to ``get_async_redis_client`` on the module
            that production code imports it from.
        redis: pre-configured ``AsyncMock`` (default: ``make_async_redis()``).

    Yields:
        The redis mock — production's ``await get_async_redis_client(...)``
        receives this same object.
    """
    from unittest.mock import AsyncMock, patch

    redis = redis if redis is not None else make_async_redis()
    with patch(target, new=AsyncMock(return_value=redis)):
        yield redis


class MockLLMService:
    """Mock `LLMService` for offline demo / sanity-check runs (#6994 wire-in).

    `IntelligentAgent` and `StreamingCommandExecutor` switched to the
    `LLMService.chat(messages, **kwargs)` surface during the #3185
    `LLMInterface` retirement. Their `__main__` demo blocks need a mock
    exposing that surface — which `MockLLMInterface` (with its legacy
    `generate_response()` method) does not. This class fills the gap.
    """

    def __init__(self, responses: Dict[str, str] | None = None):
        self._custom_responses = responses or {}
        self._call_count = 0
        self._call_history: List[Dict[str, Any]] = []

    async def chat(self, messages, **kwargs):
        """Return a deterministic `LLMResponse` for the last user message."""
        self._call_count += 1
        prompt = self._extract_prompt(messages)
        self._call_history.append({"prompt": prompt, "kwargs": kwargs})
        return _build_mock_response(self._select_response(prompt))

    async def chat_optimized(self, messages, **kwargs):
        return await self.chat(messages, **kwargs)

    async def generate(self, prompt: str, **kwargs):
        return await self.chat([{"role": "user", "content": prompt}], **kwargs)

    async def get_metrics(self) -> Dict[str, Any]:
        return {"calls": self._call_count, "provider": "mock", "cached": 0}

    @staticmethod
    def _extract_prompt(messages) -> str:
        if isinstance(messages, str):
            return messages
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if isinstance(last, dict):
                return str(last.get("content", ""))
            return str(last)
        return ""

    def _select_response(self, prompt: str) -> str:
        for keyword, response in self._custom_responses.items():
            if keyword.lower() in prompt.lower():
                return response

        prompt_lower = prompt.lower()
        if "command" in prompt_lower:
            return "COMMAND: echo 'mock LLM response'\n" "EXPLANATION: Demo path — no real LLM was called."
        if "progress" in prompt_lower:
            return "Processing data..."
        if "complet" in prompt_lower:
            return "Task completed successfully!"
        return "Mock LLM response."

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def call_history(self) -> list:
        return self._call_history

    def reset(self) -> None:
        self._call_count = 0
        self._call_history = []


class MockCommandValidator:
    """Mock command validator for testing command safety."""

    def __init__(
        self,
        default_safe: bool = True,
        dangerous_patterns: list | None = None,
    ):
        self._default_safe = default_safe
        self._dangerous_patterns = dangerous_patterns or [
            "rm -r",
            "format",
            "del /s",
            "mkfs",
            "dd if=",
        ]
        self._validation_history: list = []

    def is_command_safe(self, command: str) -> bool:
        self._validation_history.append(command)
        command_lower = command.lower()
        for pattern in self._dangerous_patterns:
            if pattern.lower() in command_lower:
                return False
        return self._default_safe

    @property
    def validation_history(self) -> list:
        return self._validation_history

    def reset(self) -> None:
        self._validation_history = []


class MockKnowledgeBase:
    """In-memory mock knowledge base for testing."""

    def __init__(self):
        self._facts: list = []
        self._queries: list = []

    async def store_fact(
        self,
        content: str,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        fact = {
            "id": len(self._facts) + 1,
            "content": content,
            "metadata": metadata or {},
        }
        self._facts.append(fact)
        return {"status": "stored", "id": fact["id"]}

    async def query(self, query: str, limit: int = 10) -> list:
        self._queries.append(query)
        query_lower = query.lower()
        matches = [f for f in self._facts if query_lower in f["content"].lower()]
        return matches[:limit]

    @property
    def facts(self) -> list:
        return self._facts

    @property
    def query_history(self) -> list:
        return self._queries

    def reset(self) -> None:
        self._facts = []
        self._queries = []


class MockWorkerNode:
    """Mock worker node for testing distributed processing."""

    def __init__(
        self,
        node_id: str = "mock-worker-1",
        capabilities: list | None = None,
    ):
        self.node_id = node_id
        self.capabilities = capabilities or ["text", "vision", "audio"]
        self._tasks_processed: list = []
        self._is_healthy = True

    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        self._tasks_processed.append(task)
        return {
            "status": "completed",
            "node_id": self.node_id,
            "task_id": task.get("id", "unknown"),
            "result": f"Mock processed: {task.get('type', 'unknown')}",
        }

    async def health_check(self) -> Dict[str, Any]:
        return {
            "healthy": self._is_healthy,
            "node_id": self.node_id,
            "capabilities": self.capabilities,
            "tasks_processed": len(self._tasks_processed),
        }

    def set_healthy(self, healthy: bool) -> None:
        self._is_healthy = healthy

    @property
    def tasks_processed(self) -> list:
        return self._tasks_processed

    def reset(self) -> None:
        self._tasks_processed = []
        self._is_healthy = True


__all__ = [
    "MockLLMInterface",
    "MockLLMService",
    "MockCommandValidator",
    "MockKnowledgeBase",
    "MockWorkerNode",
    "make_llm_response",
    "make_async_redis",
    "make_redis_pipeline",
    "patch_async_redis",
]
