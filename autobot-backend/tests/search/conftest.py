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

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any, Dict, List, Optional

_BACKEND = Path(__file__).parent.parent.parent  # .../autobot-backend
_SEARCH_DIR = _BACKEND / "agent_loop" / "search"

# Only the entries this file actually replaces are saved — restoring keys we
# never touched is what made the old save/pop/restore cycle destructive.
_SAVED: Dict[str, object] = {}
_ADDED: set = set()

_SUBMODULES = [
    "base",
    "registry",
    "searxng_provider",
    "brave_provider",
    "content_reach_provider",
]


def _bind_on_parent(full_name: str, mod: object) -> None:
    """Bind *mod* as an attribute of its parent package.

    Load-bearing for ``unittest.mock.patch``: it resolves ``"agent_loop.search.X"``
    via ``getattr(sys.modules["agent_loop"], "search")``, NOT via
    ``sys.modules["agent_loop.search"]``.  A module registered in ``sys.modules``
    by hand never gets that bind from the import machinery.
    """
    parent, _, child = full_name.rpartition(".")
    if parent and parent in sys.modules:
        setattr(sys.modules[parent], child, mod)


def _load_real(full_name: str, rel: str) -> None:
    """Register the REAL module for *full_name*, unless it already is real.

    Re-executing a module that is already loaded from this same file builds a
    second set of class objects while every importer keeps referencing the
    first — the identity split #13551 traced.  An already-real entry is
    therefore left alone and only (re)bound on its parent.
    """
    path = _BACKEND / rel
    existing = sys.modules.get(full_name)
    if existing is not None and getattr(existing, "__file__", None) == str(path):
        _bind_on_parent(full_name, existing)
        return
    spec = importlib.util.spec_from_file_location(full_name, str(path))
    if not spec or not spec.loader:
        return
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = full_name.rpartition(".")[0] or full_name
    if existing is None:
        _ADDED.add(full_name)
    else:
        _SAVED.setdefault(full_name, existing)
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    _bind_on_parent(full_name, mod)


def _ensure_package(full_name: str, path: Path) -> types.ModuleType:
    """Return the session's package object for *full_name*, giving it a real ``__path__``.

    Reuses the existing ``sys.modules`` entry rather than planting a new one —
    see the module docstring.
    """
    pkg = sys.modules.get(full_name)
    if pkg is None:
        pkg = types.ModuleType(full_name)
        pkg.__package__ = full_name
        sys.modules[full_name] = pkg
        _ADDED.add(full_name)
    pkg.__path__ = [str(path)]  # type: ignore[attr-defined]
    _bind_on_parent(full_name, pkg)
    return pkg


_ensure_package("agent_loop", _BACKEND / "agent_loop")
_ensure_package("agent_loop.search", _SEARCH_DIR)

# Load the search modules in dependency order; already-real entries are reused.
for _submod in _SUBMODULES:
    _load_real(f"agent_loop.search.{_submod}", f"agent_loop/search/{_submod}.py")
_load_real("agent_loop.search", "agent_loop/search/__init__.py")

# Executing ``__init__.py`` through a file spec yields a module with no
# ``__path__``; restore it so ``from agent_loop.search.X import Y`` keeps
# resolving from disk for anything imported after this point.
_search_pkg = sys.modules["agent_loop.search"]
_search_pkg.__path__ = [str(_SEARCH_DIR)]  # type: ignore[attr-defined]

# Attach submodules as attributes on the package so unittest.mock.patch can
# resolve them via getattr (patch walks the dotted path via attribute access).
for _submod in _SUBMODULES:
    _full = f"agent_loop.search.{_submod}"
    if _full in sys.modules:
        setattr(_search_pkg, _submod, sys.modules[_full])


def pytest_unconfigure(config) -> None:  # noqa: ARG001
    """Undo exactly what this file changed, and nothing else.

    Sweeping every ``agent_loop*`` key out of ``sys.modules`` here would drop
    submodules other collectors imported on their own during the session.
    """
    for k in _ADDED:
        sys.modules.pop(k, None)
    for k, v in _SAVED.items():
        sys.modules[k] = v  # type: ignore[assignment]


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
