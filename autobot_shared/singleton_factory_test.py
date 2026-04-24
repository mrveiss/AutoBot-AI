# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for autobot_shared.singleton_factory.lazy_singleton."""
import threading
import pytest
from autobot_shared.singleton_factory import lazy_singleton


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

    def test_arg_guard_raises_on_mismatch(self):
        get = lazy_singleton(lambda x: x)
        get(1)
        with pytest.raises(RuntimeError, match="different args"):
            get(2)

    def test_arg_guard_raises_on_kwarg_mismatch(self):
        def factory(**kwargs): return object()
        get = lazy_singleton(factory)
        get(x=1)
        with pytest.raises(RuntimeError, match="different args"):
            get(x=2)

    def test_arg_guard_allows_same_args(self):
        get = lazy_singleton(lambda x: x)
        a = get(42)
        b = get(42)
        assert a is b

    def test_arg_guard_not_triggered_with_no_args(self):
        get = lazy_singleton(object)
        a = get()
        b = get()
        assert a is b  # no RuntimeError

    def test_multiple_independent_singletons(self):
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
