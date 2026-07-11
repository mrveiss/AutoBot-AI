# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Thread-safe lazy singleton factory primitives.

Issue #5423: extracted from the repeated double-checked locking pattern in
``utils/semantic_chunker*.py``.  Third-occurrence rule triggered extraction.
Issue #5632: ``async_lazy_singleton`` added for async-context singletons.
Issue #11635: every returned factory carries ``reset()`` and
``set_for_test()`` attributes (test seams, mirroring
``functools.lru_cache``'s ``cache_clear`` convention).
"""

import asyncio
from threading import Lock
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")


def lazy_optional_singleton(factory: Callable[[], T | None]) -> Callable[[], T | None]:
    """Return a factory that creates and caches a thread-safe optional singleton.

    Like ``lazy_singleton`` but supports ``None`` as a valid cached value.
    Uses a sentinel ``_UNSET`` object to distinguish "not yet initialised"
    from "initialised to None" (e.g. when construction fails gracefully).

    Issue #5576: used for ``get_secure_sandbox()`` which returns None on
    Docker initialisation failure.

    The returned factory exposes ``reset()`` (clear the cached value so the
    next call re-invokes the factory) and ``set_for_test(value)`` (inject a
    replacement, including ``None``). Test seams only — production code must
    not call them.
    """
    _lock = Lock()
    _UNSET: Any = object()
    _instance: Any = _UNSET

    def _get() -> T | None:
        nonlocal _instance
        if _instance is _UNSET:
            with _lock:
                if _instance is _UNSET:
                    _instance = factory()
        return _instance  # type: ignore[return-value]

    def _reset() -> None:
        nonlocal _instance
        with _lock:
            _instance = _UNSET

    def _set_for_test(value: T | None) -> None:
        nonlocal _instance
        with _lock:
            _instance = value

    _get.reset = _reset  # type: ignore[attr-defined]
    _get.set_for_test = _set_for_test  # type: ignore[attr-defined]
    return _get


def lazy_singleton(factory: Callable[..., T]) -> Callable[..., T]:
    """Return a factory that creates and caches a thread-safe singleton.

    Uses double-checked locking so the common (already-initialised) path
    never acquires the lock.

    Raises RuntimeError if called again with different args than the first
    call, to prevent silent mis-configuration.

    The returned factory exposes ``reset()`` (clear the cached instance and
    first-args guard so the next call re-constructs) and
    ``set_for_test(instance)`` (inject a test double; after injection, call
    the factory with no args). Test seams only — production code must not
    call them.
    """
    instance: T | None = None
    lock = Lock()
    _first_args: tuple | None = None
    _first_kwargs: dict | None = None

    def get(*args, **kwargs) -> T:
        nonlocal instance, _first_args, _first_kwargs
        if instance is None:
            with lock:
                if instance is None:
                    instance = factory(*args, **kwargs)
                    _first_args = args
                    _first_kwargs = dict(kwargs)
        elif args or kwargs:
            if args != _first_args or kwargs != _first_kwargs:
                raise RuntimeError(
                    f"lazy_singleton: called with different args after first construction. "
                    f"First: args={_first_args!r}, kwargs={_first_kwargs!r}. "
                    f"Now: args={args!r}, kwargs={kwargs!r}."
                )
        return instance

    def _reset() -> None:
        nonlocal instance, _first_args, _first_kwargs
        with lock:
            instance = None
            _first_args = None
            _first_kwargs = None

    def _set_for_test(value: T) -> None:
        nonlocal instance, _first_args, _first_kwargs
        with lock:
            instance = value
            _first_args = ()
            _first_kwargs = {}

    get.reset = _reset  # type: ignore[attr-defined]
    get.set_for_test = _set_for_test  # type: ignore[attr-defined]
    return get


def async_lazy_singleton(factory: Callable[..., Any]) -> Callable[[], Awaitable[T]]:
    """Return an async factory that creates and caches a lazy singleton.

    Like ``lazy_singleton`` but uses ``asyncio.Lock`` for async contexts.
    The factory may be a plain callable (sync) or a coroutine function (async def).
    Construction runs exactly once; subsequent ``await get()`` calls return the
    cached instance.

    Issue #5632: extracted from ~7 repeated async double-checked locking patterns.

    The returned factory exposes ``await reset()`` (clear the cached instance
    under the construction lock) and ``set_for_test(instance)`` (synchronous
    injection of a test double; safe on the event-loop thread because no
    construction can be in flight concurrently). Test seams only — production
    code must not call them.
    """
    instance: T | None = None  # type: ignore[valid-type]  # GH#7105: T unbound in closure; async singleton pattern  # noqa: E501
    lock = asyncio.Lock()

    async def get() -> T:
        nonlocal instance
        if instance is None:
            async with lock:
                if instance is None:
                    if asyncio.iscoroutinefunction(factory):
                        instance = await factory()
                    else:
                        instance = factory()
        return instance  # type: ignore[return-value]

    async def _reset() -> None:
        nonlocal instance
        async with lock:
            instance = None

    def _set_for_test(value: T) -> None:
        nonlocal instance
        instance = value

    get.reset = _reset  # type: ignore[attr-defined]
    get.set_for_test = _set_for_test  # type: ignore[attr-defined]
    return get
