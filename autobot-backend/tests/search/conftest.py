# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared fakes + real-module wiring for web-search provider tests. (#9022/#9023).

The root ``autobot-backend/conftest.py`` stubs ``agent_loop`` (and submodules)
to break orchestration import chains. These tests need the *real*
``agent_loop.search`` package, so — mirroring ``tests/agent_loop/conftest.py``
(#6627) — we fill in whatever is still a stub and restore exactly that
afterwards, so sibling directories are unaffected.

This file must never swap the *package identity* (#13551).  It used to pop
every ``agent_loop*`` key out of ``sys.modules`` and plant a fresh
``agent_loop`` module.  That is harmless when this directory is named on the
command line — pytest loads initial conftests before importing any test module
— and fatal in a full-suite run, where pytest imports this conftest during the
collection of ``autobot-backend/tests/search`` long after
``autobot-backend/agent_loop/tests/`` has already imported and bound
``AgentLoop`` / ``PreActionVerifier`` from the *previous* module objects.
Those bindings survive the pop, but ``sys.modules`` no longer holds the module
that owns them, so every later ``patch("agent_loop.loop._bus_publish_event")``
and ``patch.object(_PAV, "HARD_BLOCK")`` re-imported a SECOND ``agent_loop.loop``
from disk and patched that one.  The real module's globals stayed untouched:
an inert patch that leaves the production code running unmocked while the test
asserts against a mock nothing ever calls.  Three tests failed loudly on it
(``test_finalize_task_emits_agent_abstained_event``,
``test_belief_cache_hit_event_published``,
``test_hard_block_prevents_approval_request``) and every other patch of an
``agent_loop`` target in the same session was silently inert.  Same hazard
``tests/agent_loop/conftest.py`` documents for this exact package (#13162).

The root conftest already plants ``agent_loop`` with a REAL ``__path__``, so
the light ``agent_loop.search`` submodules resolve from disk on their own; this
file only has to replace entries that are still stubs.

All fakes here keep tests fully offline (no real network).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from testkit.module_stubs import StubSet

_BACKEND = Path(__file__).parent.parent.parent  # .../autobot-backend
_SEARCH_DIR = _BACKEND / "agent_loop" / "search"

_SUBMODULES = [
    "base",
    "registry",
    "searxng_provider",
    "brave_provider",
    "content_reach_provider",
]

_stubs = StubSet()

# adopt_package, NOT install_package. The root conftest already planted
# ``agent_loop``; replacing that object is precisely the identity swap #13551
# traced, and install_package would do exactly that. adopt keeps the session's
# module and only gives it a real ``__path__``, recorded for restore.
_stubs.adopt_package("agent_loop", _BACKEND / "agent_loop")
_stubs.adopt_package("agent_loop.search", _SEARCH_DIR)

# Dependency order. real_load reuses an entry already loaded from the same file
# rather than re-executing it, so an already-real module keeps its identity and
# is only re-bound on its parent.
for _submod in _SUBMODULES:
    _stubs.real_load(f"agent_loop.search.{_submod}", _BACKEND / f"agent_loop/search/{_submod}.py")

# real_load_package, not real_load: executing __init__.py through a file spec
# yields a module with no __path__, which stops ``from agent_loop.search.X import Y``
# resolving from disk for everything imported afterwards.
_stubs.real_load_package("agent_loop.search", _SEARCH_DIR / "__init__.py", _SEARCH_DIR)

for _submod in _SUBMODULES:
    _stubs.real_load(f"agent_loop.search.{_submod}", _BACKEND / f"agent_loop/search/{_submod}.py")


def pytest_unconfigure(config) -> None:  # noqa: ARG001
    """Undo exactly what this file changed, and nothing else.

    StubSet.restore() reverses sys.modules entries, parent bindings and __path__
    mutations in one place. The hand-rolled version had ``_ADDED`` and ``_SAVED``
    overlap, so popping the added key and then restoring the saved one put a
    synthetic ``agent_loop.search`` straight back (#13575).
    """
    _stubs.restore()


# ---------------------------------------------------------------------------
# Offline HTTP fakes
# ---------------------------------------------------------------------------


class FakeResponse:
    """Minimal aiohttp-like response usable as an async context manager."""

    def __init__(self, *, status: int = 200, json_data: Optional[Dict[str, Any]] = None, text: str = "") -> None:
        self.status = status
        self._json = json_data or {}
        self._text = text

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, *_exc: Any) -> bool:
        return False

    async def json(self) -> Dict[str, Any]:
        return self._json

    async def text(self) -> str:
        return self._text


class FakeHTTPClient:
    """Records GET calls and returns a queued FakeResponse.

    ``get`` mirrors the real ``get_http_client().get`` contract: it is awaited
    and yields an async-context-manager response.
    """

    def __init__(self, response: FakeResponse) -> None:
        self._response = response
        self.calls: List[Dict[str, Any]] = []

    async def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self._response
