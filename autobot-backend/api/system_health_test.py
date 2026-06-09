# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for system_health.register_health_probe sync-probe rejection (#6918).

Background: ``_run_probe`` enforces ``_PROBE_TIMEOUT_S`` via ``asyncio.wait_for``
but ``wait_for`` only cancels at ``await`` points. A sync probe that blocks
the event loop (e.g. ``time.sleep``) holds the aggregator past the timeout.
The fix rejects sync probes at registration time so the failure shows up at
import time as ``TypeError`` rather than a silent prod hang.
"""

import pytest

from api.system_health import _PROBES, register_health_probe


class TestRegisterHealthProbeSyncRejection:
    """Issue #6918: sync probes must be rejected at registration time."""

    def teardown_method(self):
        # Don't leak test-registered probes into other test files.
        for name in list(_PROBES.keys()):
            if name.startswith("test_6918_"):
                del _PROBES[name]

    def test_async_probe_registers_successfully(self):
        async def my_async_probe(request):
            from api.system_health import ComponentHealth

            return ComponentHealth(name="test_6918_a", status="ok")

        # Should NOT raise.
        decorated = register_health_probe("test_6918_a")(my_async_probe)
        assert "test_6918_a" in _PROBES
        assert decorated is my_async_probe  # decorator returns the original fn

    def test_sync_probe_raises_typeerror(self):
        def my_sync_probe(request):
            from api.system_health import ComponentHealth

            return ComponentHealth(name="test_6918_b", status="ok")

        with pytest.raises(TypeError, match="must be `async def`"):
            register_health_probe("test_6918_b")(my_sync_probe)

        # Crucially: the rejected probe is NOT in the registry.
        assert "test_6918_b" not in _PROBES

    def test_sync_probe_error_mentions_issue_number(self):
        """Error message points contributors to the issue for context."""

        def sleeper(request):
            import time

            time.sleep(5)  # the exact pattern that motivated #6918

        with pytest.raises(TypeError) as exc_info:
            register_health_probe("test_6918_c")(sleeper)
        assert "#6918" in str(exc_info.value)

    def test_lambda_probe_rejected(self):
        """Lambdas (also sync) must be rejected — narrow but real footgun."""
        with pytest.raises(TypeError, match="must be `async def`"):
            register_health_probe("test_6918_d")(lambda r: None)

    def test_async_probe_after_failed_registration_succeeds(self):
        """Failed registration must not corrupt registry state."""

        def bad(request):
            return None

        with pytest.raises(TypeError):
            register_health_probe("test_6918_e")(bad)

        async def good(request):
            from api.system_health import ComponentHealth

            return ComponentHealth(name="test_6918_e", status="ok")

        # Same name; should now succeed since the bad one was rejected.
        register_health_probe("test_6918_e")(good)
        assert "test_6918_e" in _PROBES
