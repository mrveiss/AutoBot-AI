# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for LibrarianAssistant.search_web registry wiring (#10932).

Verifies:
- search_web delegates to get_search_registry().search (not Playwright /search)
- emits research:result_found per result
- returns {url,title,snippet} dicts
- returns [] on exception
- extract_content path is UNCHANGED (still calls Playwright /extract)
"""

from __future__ import annotations

import logging
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub heavy optional dependencies so LibrarianAssistant can be imported
# without a live database, Playwright service, or LLM.
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_AGENTS_DIR = _BACKEND_DIR / "agents"

# Plant a minimal 'agents' package so relative imports in the module work.
if "agents" not in sys.modules:
    _agents_pkg = types.ModuleType("agents")
    _agents_pkg.__path__ = [str(_AGENTS_DIR)]
    _agents_pkg.__package__ = "agents"
    sys.modules["agents"] = _agents_pkg


def _make_stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__path__ = []  # type: ignore[assignment]
    mod.__package__ = name
    mock_attr = MagicMock()
    mod.__getattr__ = lambda attr: mock_attr  # type: ignore[attr-defined]
    sys.modules[name] = mod
    return mod


for _stub_name in [
    "knowledge_base",
    "services",
    "services.llm_service",
    "utils.service_registry",
]:
    sys.modules.setdefault(_stub_name, _make_stub(_stub_name))

# Ensure 'utils' package stub is present IF and ONLY IF not already a real module.
# IMPORTANT: never replace a real 'utils' package — other tests may rely on real submodules
# (e.g. utils.display_utils used by research_browser_manager).
if "utils" not in sys.modules:
    _utils_pkg = types.ModuleType("utils")
    _utils_pkg.__path__ = []  # type: ignore[assignment]
    _utils_pkg.__package__ = "utils"
    sys.modules["utils"] = _utils_pkg

# Plant a real-ish agent_loop.search.registry so search_web's lazy import
# resolves.  We give it a real get_search_registry function that tests can
# patch; the actual registry object is replaced per-test via patch().
_al_search_pkg = sys.modules.get("agent_loop.search")
if _al_search_pkg is None or not hasattr(_al_search_pkg, "__path__"):
    _al_search_pkg = types.ModuleType("agent_loop.search")
    _al_search_pkg.__path__ = []  # type: ignore[assignment]
    _al_search_pkg.__package__ = "agent_loop.search"
    sys.modules["agent_loop.search"] = _al_search_pkg
    _al_pkg = sys.modules.get("agent_loop")
    if _al_pkg is not None:
        _al_pkg.search = _al_search_pkg  # type: ignore[attr-defined]

# Ensure agent_loop.search.registry exists in sys.modules with get_search_registry callable.
# If the real module is already loaded (e.g., by the search conftest), keep it — it already
# has get_search_registry.  If not, plant a minimal stub.
if "agent_loop.search.registry" not in sys.modules:
    _al_search_registry_mod = types.ModuleType("agent_loop.search.registry")
    _al_search_registry_mod.__package__ = "agent_loop.search"
    _mock_registry_singleton = MagicMock()
    _al_search_registry_mod.get_search_registry = MagicMock(  # type: ignore[attr-defined]
        return_value=_mock_registry_singleton
    )
    sys.modules["agent_loop.search.registry"] = _al_search_registry_mod
    setattr(_al_search_pkg, "registry", _al_search_registry_mod)

# ---------------------------------------------------------------------------
# Patch the config object and heavy singletons BEFORE importing the module.
# ---------------------------------------------------------------------------
_fake_config = MagicMock()
_fake_config.get_nested = MagicMock(side_effect=lambda key, default=None: default)

sys.modules.setdefault("config", types.SimpleNamespace(config=_fake_config))

# Patch autobot_shared stubs if not already real modules.
for _shared in ["autobot_shared.http_client", "autobot_shared.logging_manager"]:
    if _shared not in sys.modules:
        _make_stub(_shared)

# lazy_singleton: if the real module is loaded, use it (don't overwrite its implementation).
# If not loaded, plant a stub that maps lazy_singleton(cls) -> cls so LibrarianAssistant
# can be constructed without the real singleton machinery.
if "autobot_shared.singleton_factory" not in sys.modules:
    _singleton_stub = _make_stub("autobot_shared.singleton_factory")
    _singleton_stub.lazy_singleton = lambda cls: cls  # type: ignore[attr-defined]

# get_logger must return a real logger so log calls don't blow up.
_logging_mod = sys.modules.get("autobot_shared.logging_manager")
if _logging_mod is not None:
    _logging_mod.get_logger = logging.getLogger  # type: ignore[attr-defined]

# get_http_client must return a mock with async context-manager methods.
_http_mod = sys.modules.get("autobot_shared.http_client")
if _http_mod is not None:
    _http_mod.get_http_client = MagicMock(return_value=MagicMock())  # type: ignore[attr-defined]

# get_service_url can return any string.
_utils_mod = sys.modules.get("utils.service_registry")
if _utils_mod is not None:
    _utils_mod.get_service_url = MagicMock(return_value="http://playwright:3000")  # type: ignore[attr-defined]

# get_llm_service can return a mock.
_llm_mod = sys.modules.get("services.llm_service")
if _llm_mod is not None:
    _llm_mod.get_llm_service = MagicMock(return_value=MagicMock())  # type: ignore[attr-defined]

# KnowledgeBase stub.
_kb_mod = sys.modules.get("knowledge_base")
if _kb_mod is not None:
    _kb_mod.KnowledgeBase = MagicMock  # type: ignore[attr-defined]

# Now import the module under test.
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "agents.librarian_assistant",
    str(_AGENTS_DIR / "librarian_assistant.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_mod.__package__ = "agents"
sys.modules["agents.librarian_assistant"] = _mod
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

LibrarianAssistant = _mod.LibrarianAssistant


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_assistant() -> LibrarianAssistant:
    """Construct a LibrarianAssistant with all heavy deps mocked out."""
    with patch.object(_mod, "config", _fake_config):
        assistant = LibrarianAssistant.__new__(LibrarianAssistant)
        assistant.config = _fake_config
        assistant.knowledge_base = MagicMock()
        assistant.llm = MagicMock()
        assistant.enabled = True
        assistant.playwright_service_url = "http://playwright:3000"
        assistant.max_search_results = 5
        assistant.max_content_length = 2000
        assistant.quality_threshold = 0.7
        assistant.auto_store_quality = True
        assistant.trusted_domains = []
        assistant.http_client = MagicMock()
    return assistant


def _sr(n: int) -> MagicMock:
    """Build a mock SearchResult with a real to_dict() method."""
    sr = MagicMock()
    sr.title = f"Title {n}"
    sr.url = f"https://example.com/{n}"
    sr.snippet = f"Snippet {n}"
    sr.source = "test"
    sr.to_dict = lambda: {"title": sr.title, "url": sr.url, "snippet": sr.snippet, "source": sr.source}
    return sr


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _patch_registry(mock_registry: MagicMock):
    """Patch get_search_registry in the module currently in sys.modules.

    Uses patch.object on the live module entry so the patch always targets the
    right module, regardless of which conftest loaded it first.
    """
    reg_mod = sys.modules["agent_loop.search.registry"]
    return patch.object(reg_mod, "get_search_registry", return_value=mock_registry)


@pytest.mark.asyncio
async def test_search_web_uses_registry_not_playwright():
    """search_web must call get_search_registry().search, never POST /search."""
    assistant = _make_assistant()
    mock_registry = MagicMock()
    mock_registry.search = AsyncMock(return_value=[_sr(1), _sr(2)])

    with _patch_registry(mock_registry):
        results = await assistant.search_web("python asyncio")

    mock_registry.search.assert_awaited_once()
    # Must NOT have called the Playwright /search endpoint.
    assistant.http_client.post.assert_not_called()
    assert len(results) == 2
    assert results[0]["url"] == "https://example.com/1"
    assert results[0]["title"] == "Title 1"
    assert results[0]["snippet"] == "Snippet 1"


@pytest.mark.asyncio
async def test_search_web_emits_result_found_per_result():
    """Each SearchResult must fire a research:result_found callback event."""
    assistant = _make_assistant()
    mock_registry = MagicMock()
    mock_registry.search = AsyncMock(return_value=[_sr(1), _sr(2), _sr(3)])

    emitted = []

    async def _cb(event):
        emitted.append(event)

    with _patch_registry(mock_registry):
        await assistant.search_web("q", progress_callback=_cb)

    result_found_events = [e for e in emitted if e.get("event") == "research:result_found"]
    assert len(result_found_events) == 3
    urls = {e["url"] for e in result_found_events}
    assert urls == {"https://example.com/1", "https://example.com/2", "https://example.com/3"}


@pytest.mark.asyncio
async def test_search_web_emits_searching_event():
    """research:searching must be emitted before results."""
    assistant = _make_assistant()
    mock_registry = MagicMock()
    mock_registry.search = AsyncMock(return_value=[])

    emitted = []

    async def _cb(event):
        emitted.append(event)

    with _patch_registry(mock_registry):
        await assistant.search_web("test", search_engine="duckduckgo", progress_callback=_cb)

    searching_events = [e for e in emitted if e.get("event") == "research:searching"]
    assert len(searching_events) == 1
    assert searching_events[0]["query"] == "test"


@pytest.mark.asyncio
async def test_search_web_returns_empty_when_disabled():
    assistant = _make_assistant()
    assistant.enabled = False

    results = await assistant.search_web("q")

    assert results == []


@pytest.mark.asyncio
async def test_search_web_returns_empty_on_exception():
    """Registry exceptions must be caught; returns [] not raises."""
    assistant = _make_assistant()
    mock_registry = MagicMock()
    mock_registry.search = AsyncMock(side_effect=RuntimeError("registry boom"))

    with _patch_registry(mock_registry):
        results = await assistant.search_web("q")

    assert results == []


@pytest.mark.asyncio
async def test_search_web_returns_dicts_not_search_result_objects():
    """Return value must be plain dicts (url/title/snippet), not SearchResult objects."""
    assistant = _make_assistant()
    mock_registry = MagicMock()
    mock_registry.search = AsyncMock(return_value=[_sr(1)])

    with _patch_registry(mock_registry):
        results = await assistant.search_web("q")

    assert isinstance(results[0], dict)
    assert "url" in results[0]
    assert "title" in results[0]
    assert "snippet" in results[0]


@pytest.mark.asyncio
async def test_extract_content_still_calls_playwright_extract():
    """extract_content must POST to Playwright /extract (unchanged path)."""
    assistant = _make_assistant()

    extract_response = MagicMock()
    extract_response.status = 200
    extract_response.json = AsyncMock(
        return_value={
            "success": True,
            "url": "https://example.com/page",
            "title": "Page Title",
            "description": "desc",
            "content": "content text",
            "domain": "example.com",
            "is_trusted": True,
            "timestamp": "2026-01-01T00:00:00Z",
            "content_length": 12,
        }
    )
    extract_response.__aenter__ = AsyncMock(return_value=extract_response)
    extract_response.__aexit__ = AsyncMock(return_value=False)

    health_response = MagicMock()
    health_response.status = 200
    health_response.__aenter__ = AsyncMock(return_value=health_response)
    health_response.__aexit__ = AsyncMock(return_value=False)

    assistant.http_client.get = AsyncMock(return_value=health_response)
    assistant.http_client.post = AsyncMock(return_value=extract_response)

    result = await assistant.extract_content("https://example.com/page")

    assert result is not None
    assert result["url"] == "https://example.com/page"
    # Confirm the POST went to /extract, not /search.
    call_url = assistant.http_client.post.call_args[0][0]
    assert "/extract" in call_url
    assert "/search" not in call_url
