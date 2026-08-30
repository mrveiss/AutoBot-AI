# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared test helpers for the ``llm_shared`` test package.

Lifted out of ``test_provider_degradation.py`` (#15022) when that module's
needs_reauth coverage split into a sibling
(``test_provider_degradation_reauth.py``) to stay under the repo's 600-line
cap: both halves need the same fakeredis / store / global-injection
plumbing, and a forked copy of it would drift.

These are plain helper functions, not pytest fixtures, so conftest.py's
auto-discovery does not inject them on its own — import explicitly::

    from llm_shared.tests.conftest import (
        _inject_globals,
        _make_store_with_fake_server,
        _require_fakeredis,
        fakeredis_async,
    )
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

try:
    import fakeredis.aioredis as fakeredis_async

    _FAKEREDIS_AVAILABLE = True
except ImportError:
    fakeredis_async = None  # type: ignore[assignment]
    _FAKEREDIS_AVAILABLE = False


def _require_fakeredis():
    """Skip the test when fakeredis is not installed."""
    if not _FAKEREDIS_AVAILABLE:
        pytest.skip("fakeredis not installed — skipping Redis-backed tests")


def _make_store_with_fake_server(server):
    """Return a ProviderDegradationStore whose Redis calls hit *server*."""
    from llm_shared.provider_degradation import ProviderDegradationStore

    store = ProviderDegradationStore()

    async def _fake_redis(*_args, **_kwargs):
        return fakeredis_async.FakeRedis(server=server, decode_responses=True)

    store._get_redis = _fake_redis  # type: ignore[method-assign]
    return store


@contextmanager
def _inject_globals(func, **replacements):
    """Swap names in *func*'s own module globals for the duration of the block.

    ``unittest.mock.patch("llm_shared.X.name")`` resolves the target through
    ``sys.modules``, which the conftest stub machinery can leave pointing at a
    MagicMock module while the real class lives in a separately loaded module
    object — silently patching the wrong namespace.  Injecting through
    ``func.__globals__`` always hits the dict the executing code reads.
    """
    g = func.__globals__
    saved = {k: g[k] for k in replacements}
    g.update(replacements)
    try:
        yield
    finally:
        g.update(saved)
