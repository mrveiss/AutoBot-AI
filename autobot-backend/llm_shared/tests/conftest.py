# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared test fixtures for the ``llm_shared`` test package.

Lifted out of ``test_provider_degradation.py`` (#15022) when that module's
needs_reauth coverage split into a sibling
(``test_provider_degradation_reauth.py``) to stay under the repo's 600-line
cap: both halves need the same store/global-injection plumbing, and a
forked copy of it would drift.

These are pytest fixtures, not plain importable functions — ``autobot-backend/
llm_shared/tests/`` has no ``__init__.py`` (``llm_shared.tests`` is not an
importable package), so ``from llm_shared.tests.conftest import ...``
fails collection with ``ModuleNotFoundError`` (#15320 review). conftest.py
is loaded by pytest through its own discovery mechanism instead — a test
simply requests a fixture by name as a parameter, no import statement and
no packaging question:

    async def test_foo(_require_fakeredis, _make_store_with_fake_server, _inject_globals):
        server = fakeredis_async.FakeServer()
        store = _make_store_with_fake_server(server)
        ...

``fakeredis_async`` itself is deliberately NOT provided here — it is a
third-party import, not a helper, so each module does its own one-line
guarded import instead of treating it as shared state.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest


@pytest.fixture
def _require_fakeredis():
    """Skip the test when fakeredis is not installed."""
    pytest.importorskip("fakeredis.aioredis")


@pytest.fixture
def _make_store_with_fake_server():
    """Factory fixture: build a ProviderDegradationStore backed by a FakeRedis server.

    Returns a callable ``factory(server) -> ProviderDegradationStore`` so
    call sites keep today's ``_make_store_with_fake_server(server)`` shape.
    Skips (via ``importorskip``) independently of ``_require_fakeredis`` —
    a test can request this factory on its own.
    """
    fakeredis_async = pytest.importorskip("fakeredis.aioredis")

    def _factory(server):
        from llm_shared.provider_degradation import ProviderDegradationStore

        store = ProviderDegradationStore()

        async def _fake_redis(*_args, **_kwargs):
            return fakeredis_async.FakeRedis(server=server, decode_responses=True)

        store._get_redis = _fake_redis  # type: ignore[method-assign]
        return store

    return _factory


@pytest.fixture
def _inject_globals():
    """Factory fixture: return the global-injection context manager.

    Not "setup" in the fixture sense — it is a pure context manager whose
    arguments (which function, which replacements) differ per call site,
    sometimes more than once within the same test, so it cannot be
    parametrized as an ordinary fixture value. Providing the callable
    itself through a fixture keeps the same call-site shape
    (``with _inject_globals(func, **replacements):``) without an import
    that depends on ``llm_shared.tests`` being an importable package.
    """

    @contextmanager
    def _swap(func, **replacements):
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

    return _swap
