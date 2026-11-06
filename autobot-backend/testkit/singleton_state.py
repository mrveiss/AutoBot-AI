# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No test inherits the feature-flag singleton or its read cache from another (#18998).

``get_feature_flags()`` returns a process-wide ``FeatureFlags`` whose enforcement-mode and
per-endpoint reads are cached for ``AUTOBOT_FEATURE_FLAG_CACHE_TTL_SECONDS``. Without a reset, a
value one test stored (or a Redis failure it simulated) is served to the next test for that window.
"""

from __future__ import annotations

import sys

import pytest


def _reset_feature_flags() -> None:
    """Drop the singleton and empty its cache. A no-op until a test has imported the module."""
    module = sys.modules.get("services.feature_flags")
    if module is None:
        return
    flags = getattr(module, "_feature_flags", None)
    if flags is not None:
        flags._cache_invalidate()
    module._feature_flags = None


@pytest.fixture(autouse=True)
def reset_feature_flags_singleton():
    """Fresh ``_feature_flags`` singleton and empty cache before and after every test."""
    _reset_feature_flags()
    yield
    _reset_feature_flags()


@pytest.fixture(autouse=True)
def fake_session_lease(monkeypatch):
    """Back the per-session chat lease with an in-memory Redis, so no test waits on a real one (#20862).

    A save needs the session lease, and with no Redis a writer waits out the lease bound rather than
    writing unlocked. The lease module is imported here, unconditionally, so a test that imports the
    chat code lazily inside its body is bound to the fake too (an unbound test would reach the real
    client and wait for the whole bound). Each test gets a fresh server; a test that needs the lease
    store gone or contended rebinds ``chat_history.session_lease._lease_client`` itself.
    """
    import fakeredis
    import fakeredis.aioredis

    from chat_history import session_lease  # a broken chat_history import fails loudly, never skips silently

    server = fakeredis.FakeServer()

    async def _client(database):
        return fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)

    monkeypatch.setattr(session_lease, "_lease_client", _client)
    yield server
