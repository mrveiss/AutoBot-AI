# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for thread-safe singleton init (Issue #10784).

Verifies that get_engine (api/diagnostics.py) and get_screen_analyzer
(api/vision.py) return a stable singleton — same instance on repeated
calls, and same instance across concurrent threads.

diagnostics.get_engine was migrated from an unprotected check-then-set to
lazy_singleton in #10784.  vision.get_screen_analyzer was already protected
(threading.Lock double-checked locking); its test confirms the stability
contract is met regardless of implementation.
"""

import threading
from unittest.mock import patch


class TestDiagnosticsGetEngineSingleton:
    """get_engine() in api/diagnostics.py must return a stable singleton."""

    def test_repeated_calls_same_instance(self):
        """Two sequential calls return the same CausalInferenceEngine object."""
        from services.causal_inference_engine import CausalInferenceEngine

        with patch.object(CausalInferenceEngine, "__init__", return_value=None):
            # Import after patch so module-level lazy_singleton picks up mock
            import importlib

            import api.diagnostics as diag

            importlib.reload(diag)
            a = diag.get_engine()
            b = diag.get_engine()
        assert a is b, "get_engine() must return the same instance on repeated calls"

    def test_concurrent_calls_same_instance(self):
        """Concurrent calls from multiple threads return the same instance."""
        from services.causal_inference_engine import CausalInferenceEngine

        with patch.object(CausalInferenceEngine, "__init__", return_value=None):
            import importlib

            import api.diagnostics as diag

            importlib.reload(diag)

            results = []
            barrier = threading.Barrier(10)

            def call_getter():
                barrier.wait()  # all threads start at the same time
                results.append(diag.get_engine())

            threads = [threading.Thread(target=call_getter) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert len(results) == 10
        first = results[0]
        assert all(r is first for r in results), "get_engine() must return the same instance from all threads"

    def test_get_engine_is_callable(self):
        """get_engine is a callable (lazy_singleton wrapper), not a bare instance."""
        import api.diagnostics as diag

        assert callable(diag.get_engine), "get_engine must be callable (lazy_singleton)"


class TestVisionGetScreenAnalyzerSingleton:
    """get_screen_analyzer() in api/vision.py must return a stable singleton."""

    def test_repeated_calls_same_instance(self):
        """Two sequential calls return the same ScreenAnalyzer object."""
        from computer_vision.screen_analyzer import ScreenAnalyzer

        with patch.object(ScreenAnalyzer, "__init__", return_value=None):
            import importlib

            import api.vision as vision_mod

            importlib.reload(vision_mod)
            a = vision_mod.get_screen_analyzer()
            b = vision_mod.get_screen_analyzer()
        assert a is b, "get_screen_analyzer() must return the same instance on repeated calls"

    def test_concurrent_calls_same_instance(self):
        """Concurrent calls from multiple threads return the same instance."""
        from computer_vision.screen_analyzer import ScreenAnalyzer

        with patch.object(ScreenAnalyzer, "__init__", return_value=None):
            import importlib

            import api.vision as vision_mod

            importlib.reload(vision_mod)

            results = []
            barrier = threading.Barrier(10)

            def call_getter():
                barrier.wait()
                results.append(vision_mod.get_screen_analyzer())

            threads = [threading.Thread(target=call_getter) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert len(results) == 10
        first = results[0]
        assert all(r is first for r in results), "get_screen_analyzer() must return the same instance from all threads"


class TestLockedNewSingletons:
    """__new__-based singletons gained double-checked locking in #11637.

    Each class must construct exactly one instance under concurrent first
    access (barrier-synchronized threads racing __new__).
    """

    @staticmethod
    def _race(cls_factory, reset):
        reset()
        results = []
        barrier = threading.Barrier(10)

        def construct():
            barrier.wait()
            results.append(cls_factory())

        threads = [threading.Thread(target=construct) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(results) == 10
        assert all(r is results[0] for r in results)

    def test_hook_registry_concurrent_new(self):
        from autobot_shared.plugin_sdk.hooks import HookRegistry

        self._race(HookRegistry, lambda: setattr(HookRegistry, "_instance", None))

    def test_plugin_registry_concurrent_new(self):
        from autobot_shared.plugin_sdk.base import PluginRegistry

        self._race(PluginRegistry, lambda: setattr(PluginRegistry, "_instance", None))

    def test_capability_checker_concurrent_new(self):
        from autobot_shared.plugin_sdk.capabilities import CapabilityChecker

        self._race(CapabilityChecker, lambda: setattr(CapabilityChecker, "_instance", None))

    def test_adapter_registry_concurrent_new(self):
        from llm_shared.adapters.registry import AdapterRegistry

        self._race(AdapterRegistry, AdapterRegistry.reset)

    def test_external_provider_factory_concurrent_new(self):
        from services.memory.external_provider_factory import ExternalProviderFactory

        self._race(
            ExternalProviderFactory,
            lambda: setattr(ExternalProviderFactory, "_instance", None),
        )

    def test_http_client_manager_concurrent_new(self):
        from autobot_shared.http_client import HTTPClientManager

        self._race(HTTPClientManager, lambda: setattr(HTTPClientManager, "_instance", None))

    def test_http_client_reset_for_new_loop(self):
        import autobot_shared.http_client as hc

        first = hc.get_http_client()
        hc.reset_http_client_for_new_loop()
        second = hc.get_http_client()
        assert first is not second, "reset must discard the loop-bound manager"

    def test_http_client_reset_rebinds_asyncio_lock(self):
        """Reset must replace the class-level asyncio.Lock — a contended lock
        stays bound to the loop that contended it (#11654 review M1)."""
        import autobot_shared.http_client as hc

        old_lock = hc.HTTPClientManager._lock
        hc.reset_http_client_for_new_loop()
        assert hc.HTTPClientManager._lock is not old_lock

    def test_http_client_usable_across_loops_after_reset(self):
        """Contend the lock in loop A, reset, then acquire it in loop B."""
        import asyncio

        import autobot_shared.http_client as hc

        async def _contend():
            lock = hc.HTTPClientManager._lock

            async def hold():
                async with lock:
                    await asyncio.sleep(0.01)

            await asyncio.gather(hold(), hold())  # forces the contended path

        asyncio.run(_contend())
        hc.reset_http_client_for_new_loop()

        async def _acquire_in_new_loop():
            async with hc.HTTPClientManager._lock:
                return True

        assert asyncio.run(_acquire_in_new_loop())
