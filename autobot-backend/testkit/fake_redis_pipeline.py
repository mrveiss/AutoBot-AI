# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One fake Redis pipeline, instead of eighteen hand-rolled ones (#18991).

Tests across the backend each wrote their own ``_FakePipeline`` / ``_Pipe``: a list of queued
commands and an ``execute``. They differed in whether commands applied at call time or at
``execute``, whether ``execute`` returned the per-command results, and whether ``watch`` /
``multi`` / a ``WatchError`` were modelled at all. A pipeline whose commands apply at call time
passes a test for code that forgot to call ``execute``.

Rules (the same shape as ``testkit.fake_async_session``):

1. **Real semantics.** Commands QUEUE and return the pipeline; ``execute`` applies them in order
   and returns one result per command. After ``watch`` and before ``multi`` a command runs
   immediately (redis-py's ``immediate_execute_command``). ``async with`` / ``with`` resets on exit.
   ``FakeAsyncPipeline`` is also awaitable (``await pipe.hincrby(...)`` works, as on redis.asyncio).
2. **`transaction=False` is not MULTI/EXEC**: no WATCH conflict, no ``WatchError``. An empty queue returns ``[]``.
3. **Recording is always on** (``commands`` for what is queued, ``executed`` for each flushed batch);
   behaviour is opt-in through the constructor.
4. **A command that redis-py's pipeline does not have is an ``AttributeError``**, not silently
   accepted: ``COMMANDS`` is the closed set tests use, checked against redis-py by
   ``fake_redis_pipeline_test.py``.

The commands apply to ``target`` -- any object with a method of that name (sync or async), e.g. a
test's in-memory fake client. With no target nothing is applied and each result is ``True``.

Usage::

    from testkit.fake_redis_pipeline import FakeAsyncPipeline

    class FakeRedis:
        def pipeline(self, transaction=True):
            return FakeAsyncPipeline(self, transaction=transaction)

    # a retry path: the first EXEC raises WatchError, the second applies
    FakeAsyncPipeline(redis, execute_errors=[WatchError()])
"""

from __future__ import annotations

import inspect
from typing import Any, Iterable, Mapping, Optional

from redis.exceptions import WatchError

__all__ = ["COMMANDS", "DualReply", "FakeAsyncPipeline", "FakePipeline", "WatchError"]

#: Every command the tests and their fake clients queue through a pipeline (#18991); each exists on redis-py's pipeline.
COMMANDS = frozenset(
    {
        "delete",
        "exists",
        "expire",
        "get",
        "hget",
        "hgetall",
        "hincrby",
        "hincrbyfloat",
        "hset",
        "incrby",
        "lpush",
        "lrange",
        "ltrim",
        "sadd",
        "set",
        "setex",
        "srem",
        "zadd",
        "zcard",
        "zrem",
    }
)


def _queue_command(name: str):
    def method(self, *args: Any, **kwargs: Any):
        return self._command(name, args, kwargs)

    method.__name__ = name
    return method


class _JsonCommands:
    """What ``pipe.json()`` returns: ``.get`` queues ``json.get`` on the owning pipeline."""

    def __init__(self, pipe: "_PipelineBase") -> None:
        self._pipe = pipe

    def get(self, *args: Any, **kwargs: Any):
        return self._pipe._command("json.get", args, kwargs)


class _PipelineBase:
    """State, queueing and recording shared by the sync and async pipelines."""

    def __init__(
        self,
        target: Any = None,
        *,
        transaction: bool = True,
        execute_error: Optional[BaseException] = None,
        execute_errors: Iterable[BaseException] = (),
        command_errors: Optional[Mapping[str, BaseException]] = None,
        detect_watch_conflicts: bool = False,
    ) -> None:
        """Opt-ins: ``execute_error`` raises on every EXEC; ``execute_errors`` raises one per EXEC, in order,
        then lets later EXECs apply (a retry path); ``command_errors`` maps a command name to the error
        that command returns inside EXEC (not applied); ``detect_watch_conflicts`` raises ``WatchError``
        when ``target.get(key)`` changed since ``watch(key)``."""
        self._target = target
        self._transaction = transaction
        self._execute_error = execute_error
        self._execute_errors = list(execute_errors)
        self._command_errors = dict(command_errors or {})
        self._detect_conflicts = detect_watch_conflicts
        self._queue: list[tuple[str, tuple, dict]] = []
        self._executed: list[list[tuple]] = []
        self._watched: dict[Any, Any] = {}
        self._watching = False
        self._explicit_multi = False

    @property
    def commands(self) -> list[tuple]:
        """The queued, not yet executed commands as ``(name, *args)``."""
        return [(name, *args) for name, args, _ in self._queue]

    @property
    def executed(self) -> list[list[tuple]]:
        """One list of ``(name, *args)`` per ``execute()`` that reached EXEC."""
        return self._executed

    def json(self) -> _JsonCommands:
        return _JsonCommands(self)

    def multi(self) -> None:
        self._explicit_multi = True

    def _command(self, name: str, args: tuple, kwargs: dict):
        if self._watching and not self._explicit_multi:
            return self._immediate(name, args, kwargs)
        self._queue.append((name, args, kwargs))
        return self

    def _callable(self, name: str):
        head, _, tail = name.partition(".")
        if self._target is None:
            return None
        return getattr(getattr(self._target, head)(), tail) if tail else getattr(self._target, head)

    def _clear(self) -> None:
        self._queue.clear()
        self._watched.clear()
        self._watching = False
        self._explicit_multi = False

    def _begin(self) -> list[tuple[str, tuple, dict]]:
        """Return the batch to apply, recording it; an empty queue sends nothing, like redis-py.

        Without a transaction there is no MULTI/EXEC, so there is no WATCH conflict and no ``WatchError``;
        other injected EXEC errors (a dead connection) still fire.
        """
        if not self._queue:
            self._clear()
            return []
        if not self._transaction:
            self._watched.clear()
        error = self._next_execute_error()
        if error is not None:
            self._clear()
            raise error
        batch = list(self._queue)
        self._executed.append([(name, *args) for name, args, _ in batch])
        return batch

    def _next_execute_error(self) -> Optional[BaseException]:
        pending = self._execute_errors[0] if self._execute_errors else self._execute_error
        if isinstance(pending, WatchError) and not self._transaction:
            return None
        return self._execute_errors.pop(0) if self._execute_errors else pending

    def _conflict(self, key: Any) -> WatchError:
        self._clear()
        return WatchError(f"WATCH key {key!r} was modified")

    def _finish(self, results: list, raise_on_error: bool) -> list:
        self._clear()
        if raise_on_error:
            for result in results:
                if isinstance(result, BaseException):
                    raise result
        return results


for _name in COMMANDS:
    setattr(_PipelineBase, _name, _queue_command(_name))
del _name


class FakePipeline(_PipelineBase):
    """``redis.Redis.pipeline()``: synchronous commands, ``execute`` returns the result list."""

    def __enter__(self) -> "FakePipeline":
        return self

    def __exit__(self, *exc_info: Any) -> bool:
        self.reset()
        return False

    def watch(self, *keys: Any) -> bool:
        self._watching = True
        if self._detect_conflicts:
            self._watched.update({key: self._target.get(key) for key in keys})
        return True

    def unwatch(self) -> bool:
        self._watching = False
        self._watched.clear()
        return True

    def reset(self) -> None:
        self._clear()

    def _apply(self, name: str, args: tuple, kwargs: dict):
        fn = self._callable(name)
        return True if fn is None else fn(*args, **kwargs)

    def _immediate(self, name: str, args: tuple, kwargs: dict):
        return self._apply(name, args, kwargs)

    def execute(self, raise_on_error: bool = True) -> list:
        batch = self._begin()
        for key, snapshot in self._watched.items():
            if self._target.get(key) != snapshot:
                raise self._conflict(key)
        results = []
        for name, args, kwargs in batch:
            error = self._command_errors.get(name)
            results.append(error if error is not None else self._apply(name, args, kwargs))
        return self._finish(results, raise_on_error)


class FakeAsyncPipeline(_PipelineBase):
    """``redis.asyncio.Redis.pipeline()``: async ``watch`` / ``execute`` / ``reset``, awaitable commands."""

    async def __aenter__(self) -> "FakeAsyncPipeline":
        return self

    async def __aexit__(self, *exc_info: Any) -> bool:
        await self.reset()
        return False

    def __await__(self):
        return self._self().__await__()

    async def _self(self) -> "FakeAsyncPipeline":
        return self

    async def watch(self, *keys: Any) -> bool:
        self._watching = True
        if self._detect_conflicts:
            for key in keys:
                self._watched[key] = await self._resolve(self._target.get(key))
        return True

    async def unwatch(self) -> bool:
        self._watching = False
        self._watched.clear()
        return True

    async def reset(self) -> None:
        self._clear()

    @staticmethod
    async def _resolve(result: Any) -> Any:
        return await result if inspect.isawaitable(result) else result

    async def _apply(self, name: str, args: tuple, kwargs: dict):
        fn = self._callable(name)
        return True if fn is None else await self._resolve(fn(*args, **kwargs))

    def _immediate(self, name: str, args: tuple, kwargs: dict):
        return self._apply(name, args, kwargs)

    async def execute(self, raise_on_error: bool = True) -> list:
        batch = self._begin()
        for key, snapshot in self._watched.items():
            if await self._resolve(self._target.get(key)) != snapshot:
                raise self._conflict(key)
        results = []
        for name, args, kwargs in batch:
            error = self._command_errors.get(name)
            results.append(error if error is not None else await self._apply(name, args, kwargs))
        return self._finish(results, raise_on_error)


class DualReply:
    """A write's reply usable from a sync client AND awaited from an async one (#19630).

    For a fake that stands in for both clients of one key: the sync caller ignores it, the async
    caller awaits it, and both see the write already applied.
    """

    def __await__(self):
        return iter(())
