# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared fakes + real-module wiring for web-search provider tests. (#9022/#9023).

The root ``autobot-backend/conftest.py`` stubs ``agent_loop`` (and submodules)
to break orchestration import chains. These tests need the *real*
``agent_loop.search`` package, so — mirroring ``tests/agent_loop/conftest.py``
(#6627) — we plant a real package entry and load the search modules directly,
restoring the stubs afterwards so sibling directories are unaffected.

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

_AGENT_LOOP_KEYS = [k for k in sys.modules if k == "agent_loop" or k.startswith("agent_loop.")]
_SAVED: Dict[str, object] = {k: sys.modules[k] for k in _AGENT_LOOP_KEYS}


def _load_real(full_name: str, rel: str) -> None:
    """Load a Python file directly and register it under *full_name*."""
    path = _BACKEND / rel
    spec = importlib.util.spec_from_file_location(full_name, str(path))
    if not spec or not spec.loader:
        return
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = full_name.rpartition(".")[0] or full_name
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]


# Drop any stubs planted by the parent conftest.
for _k in _AGENT_LOOP_KEYS:
    sys.modules.pop(_k, None)

# Plant a real ``agent_loop`` package WITHOUT running its heavy __init__.
_pkg = types.ModuleType("agent_loop")
_pkg.__path__ = [str(_BACKEND / "agent_loop")]  # type: ignore[assignment]
_pkg.__package__ = "agent_loop"
sys.modules["agent_loop"] = _pkg

# Plant the search sub-package and load its modules in dependency order.
_search_pkg = types.ModuleType("agent_loop.search")
_search_pkg.__path__ = [str(_SEARCH_DIR)]  # type: ignore[assignment]
_search_pkg.__package__ = "agent_loop.search"
sys.modules["agent_loop.search"] = _search_pkg
_pkg.search = _search_pkg  # type: ignore[attr-defined]

_load_real("agent_loop.search.base", "agent_loop/search/base.py")
_load_real("agent_loop.search.registry", "agent_loop/search/registry.py")
_load_real("agent_loop.search.searxng_provider", "agent_loop/search/searxng_provider.py")
_load_real("agent_loop.search.brave_provider", "agent_loop/search/brave_provider.py")
_load_real("agent_loop.search.content_reach_provider", "agent_loop/search/content_reach_provider.py")
_load_real("agent_loop.search", "agent_loop/search/__init__.py")

# Attach submodules as attributes on the package so unittest.mock.patch can
# resolve them via getattr (patch walks the dotted path via attribute access).
for _submod in ["base", "registry", "searxng_provider", "brave_provider", "content_reach_provider"]:
    _full = f"agent_loop.search.{_submod}"
    if _full in sys.modules:
        setattr(_search_pkg, _submod, sys.modules[_full])


def pytest_unconfigure(config) -> None:  # noqa: ARG001
    """Restore the original stub state so other directories are unaffected."""
    for k in list(sys.modules):
        if k == "agent_loop" or k.startswith("agent_loop."):
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
