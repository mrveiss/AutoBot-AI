# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for autobot_shared.singleton_factory."""

import asyncio
import threading

import pytest

from autobot_shared.singleton_factory import async_lazy_singleton, lazy_optional_singleton, lazy_singleton


class TestLazySingleton:
    def test_basic_caching(self):
        calls = []

        def factory():
            calls.append(1)
            return object()

        get = lazy_singleton(factory)
        a = get()
        b = get()
        assert a is b
        assert len(calls) == 1

    def test_factory_receives_first_call_args(self):
        received = []

        def factory(*args, **kwargs):
            received.append((args, kwargs))
            return object()

        get = lazy_singleton(factory)
        get(1, 2, x=3)
        assert received == [((1, 2), {"x": 3})]

    def test_arg_guard_raises_on_mismatch(self) -> None:
        get = lazy_singleton(lambda x: x)
        get(1)
        with pytest.raises(RuntimeError, match="different args"):
            get(2)

    def test_arg_guard_raises_on_kwarg_mismatch(self):
        def factory(**kwargs):
            return object()

        get = lazy_singleton(factory)
        get(x=1)
        with pytest.raises(RuntimeError, match="different args"):
            get(x=2)

    def test_arg_guard_allows_same_args(self) -> None:
        get = lazy_singleton(lambda x: x)
        a = get(42)
        b = get(42)
        assert a is b

    def test_arg_guard_not_triggered_with_no_args(self) -> None:
        get = lazy_singleton(object)
        a = get()
        b = get()
        assert a is b  # no RuntimeError

    def test_multiple_independent_singletons(self) -> None:
        """Each lazy_singleton call creates an independent closure."""
        get_a = lazy_singleton(object)
        get_b = lazy_singleton(object)
        assert get_a() is get_a()
        assert get_b() is get_b()
        assert get_a() is not get_b()

    def test_factory_exception_allows_retry(self):
        calls = []
        sentinel = object()

        def factory():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("first call fails")
            return sentinel

        get = lazy_singleton(factory)
        with pytest.raises(RuntimeError, match="first call fails"):
            get()
        result = get()
        assert result is sentinel
        assert len(calls) == 2

    def test_thread_safety(self):
        calls = []

        def factory():
            calls.append(1)
            return object()

        get = lazy_singleton(factory)
        results = []
        threads = [threading.Thread(target=lambda: results.append(get())) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert all(r is results[0] for r in results)
        assert len(calls) == 1


# ---------------------------------------------------------------------------
# lazy_optional_singleton
# ---------------------------------------------------------------------------


def test_lazy_optional_singleton_caches_non_none_result():
    """Factory called once; result cached and returned on every subsequent call."""
    call_count = 0

    def factory():
        nonlocal call_count
        call_count += 1
        return object()

    get = lazy_optional_singleton(factory)
    r1 = get()
    r2 = get()
    assert r1 is r2
    assert call_count == 1


def test_lazy_optional_singleton_caches_none():
    """None is a valid cached value; factory must NOT be called again after returning None."""
    call_count = 0

    def factory():
        nonlocal call_count
        call_count += 1
        return None

    get = lazy_optional_singleton(factory)
    assert get() is None
    assert get() is None
    assert call_count == 1


def test_lazy_optional_singleton_independent_closures() -> None:
    """Two separate lazy_optional_singleton(...) calls produce independent singletons."""
    get_a = lazy_optional_singleton(object)
    get_b = lazy_optional_singleton(object)
    assert get_a() is get_a()
    assert get_b() is get_b()
    assert get_a() is not get_b()


def test_lazy_optional_singleton_thread_safety():
    """Concurrent callers all receive the same object; factory called exactly once."""
    call_count = 0

    def factory():
        nonlocal call_count
        call_count += 1
        return object()

    get = lazy_optional_singleton(factory)
    results = []
    threads = [threading.Thread(target=lambda: results.append(get())) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(r is results[0] for r in results)
    assert call_count == 1


def test_lazy_optional_singleton_none_not_reinitialised():
    """After a None result is cached, subsequent calls return None without re-invoking the factory."""
    call_count = 0

    def factory():
        nonlocal call_count
        call_count += 1
        return None

    get = lazy_optional_singleton(factory)
    get()  # initialises to None
    result = get()  # must use cached None, not call factory again
    assert result is None
    assert call_count == 1  # still exactly one call


# ---------------------------------------------------------------------------
# async_lazy_singleton
# ---------------------------------------------------------------------------


class TestAsyncLazySingleton:
    @pytest.mark.asyncio
    async def test_sync_factory_cached(self):
        """Sync factory called once; all awaits return the same instance."""
        calls = []

        def factory():
            calls.append(1)
            return object()

        get = async_lazy_singleton(factory)
        a = await get()
        b = await get()
        assert a is b
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_async_factory_cached(self):
        """Async factory called once; all awaits return the same instance."""
        calls = []

        async def factory():
            calls.append(1)
            return object()

        get = async_lazy_singleton(factory)
        a = await get()
        b = await get()
        assert a is b
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_independent_closures(self) -> None:
        """Two async_lazy_singleton calls produce independent singletons."""
        get_a = async_lazy_singleton(object)
        get_b = async_lazy_singleton(object)
        assert await get_a() is await get_a()
        assert await get_b() is await get_b()
        assert await get_a() is not await get_b()

    @pytest.mark.asyncio
    async def test_concurrent_callers_receive_same_instance(self):
        """Concurrent awaiters all receive the same object; factory called once."""
        calls = []

        async def factory():
            calls.append(1)
            await asyncio.sleep(0)
            return object()

        get = async_lazy_singleton(factory)
        results = await asyncio.gather(*[get() for _ in range(20)])
        assert all(r is results[0] for r in results)
        assert len(calls) == 1
