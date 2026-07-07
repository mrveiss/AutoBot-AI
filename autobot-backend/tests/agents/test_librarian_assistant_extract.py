# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for LibrarianAssistant extract_content via content_reach (#10932).

Verifies:
- _source_for_url routes youtube.com/youtu.be → "youtube", reddit.com → "reddit",
  everything else → "web_page"; handles missing scheme
- extract_content fetches via get_content_source_registry().fetch with the
  correct source name derived from the URL
- content_data has exactly the 8 required keys with correct values
- success=False or empty text → None
- fetch raises → None (no propagation)
- research_query no longer calls _check_playwright_service (removed)
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
# without a live database or LLM.
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
]:
    sys.modules.setdefault(_stub_name, _make_stub(_stub_name))

# Ensure 'utils' package stub is present only if not already a real module.
if "utils" not in sys.modules:
    _utils_pkg = types.ModuleType("utils")
    _utils_pkg.__path__ = []  # type: ignore[assignment]
    _utils_pkg.__package__ = "utils"
    sys.modules["utils"] = _utils_pkg

# Stub agent_loop.search.registry so any indirect import doesn't fail.
_al_search_pkg = sys.modules.get("agent_loop.search")
if _al_search_pkg is None or not hasattr(_al_search_pkg, "__path__"):
    _al_search_pkg = types.ModuleType("agent_loop.search")
    _al_search_pkg.__path__ = []  # type: ignore[assignment]
    _al_search_pkg.__package__ = "agent_loop.search"
    sys.modules["agent_loop.search"] = _al_search_pkg
    _al_pkg = sys.modules.get("agent_loop")
    if _al_pkg is not None:
        _al_pkg.search = _al_search_pkg  # type: ignore[attr-defined]

if "agent_loop.search.registry" not in sys.modules:
    _al_search_registry_mod = types.ModuleType("agent_loop.search.registry")
    _al_search_registry_mod.__package__ = "agent_loop.search"
    _mock_search_singleton = MagicMock()
    _al_search_registry_mod.get_search_registry = MagicMock(  # type: ignore[attr-defined]
        return_value=_mock_search_singleton
    )
    sys.modules["agent_loop.search.registry"] = _al_search_registry_mod
    setattr(_al_search_pkg, "registry", _al_search_registry_mod)

# content_reach is a real installed package — do NOT stub it here.
# Per-test patch.dict overrides for content_reach.base and content_reach.registry
# are applied at call time to avoid contaminating the real modules.

# ---------------------------------------------------------------------------
# Patch config and singletons BEFORE importing the module under test.
# ---------------------------------------------------------------------------
_fake_config = MagicMock()
_fake_config.get_nested = MagicMock(side_effect=lambda key, default=None: default)

sys.modules.setdefault("config", types.SimpleNamespace(config=_fake_config))

# Patch autobot_shared stubs if not already real modules.
for _shared in ["autobot_shared.logging_manager"]:
    if _shared not in sys.modules:
        _make_stub(_shared)

if "autobot_shared.singleton_factory" not in sys.modules:
    _singleton_stub = _make_stub("autobot_shared.singleton_factory")
    _singleton_stub.lazy_singleton = lambda cls: cls  # type: ignore[attr-defined]

_logging_mod = sys.modules.get("autobot_shared.logging_manager")
if _logging_mod is not None:
    _logging_mod.get_logger = logging.getLogger  # type: ignore[attr-defined]

_llm_mod = sys.modules.get("services.llm_service")
if _llm_mod is not None:
    _llm_mod.get_llm_service = MagicMock(return_value=MagicMock())  # type: ignore[attr-defined]

_kb_mod = sys.modules.get("knowledge_base")
if _kb_mod is not None:
    _kb_mod.KnowledgeBase = MagicMock  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Load the module under test.
# ---------------------------------------------------------------------------
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
_source_for_url = _mod._source_for_url


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXPECTED_CONTENT_DATA_KEYS = frozenset(
    {"url", "title", "description", "content", "domain", "is_trusted", "timestamp", "content_length"}
)


def _make_assistant() -> LibrarianAssistant:
    """Construct a LibrarianAssistant with all heavy deps mocked out."""
    assistant = LibrarianAssistant.__new__(LibrarianAssistant)
    assistant.config = _fake_config
    assistant.knowledge_base = MagicMock()
    assistant.llm = MagicMock()
    assistant.enabled = True
    assistant.max_search_results = 5
    assistant.max_content_length = 2000
    assistant.quality_threshold = 0.7
    assistant.auto_store_quality = True
    assistant.trusted_domains = [
        "wikipedia.org",
        "github.com",
        "stackoverflow.com",
    ]
    return assistant


def _make_content_result(
    success: bool = True,
    text: str = "hello world content",
    url: str = "",
    structured: dict | None = None,
) -> MagicMock:
    """Build a mock ContentResult."""
    r = MagicMock()
    r.success = success
    r.text = text
    r.url = url
    r.structured = structured or {}
    return r


def _make_registry(fetch_result: MagicMock) -> MagicMock:
    """Build a mock content_reach registry whose fetch returns fetch_result."""
    reg = MagicMock()
    reg.get_chain = MagicMock(return_value=MagicMock())  # chain present → skip bootstrap
    reg.fetch = AsyncMock(return_value=fetch_result)
    return reg


# ---------------------------------------------------------------------------
# _source_for_url tests
# ---------------------------------------------------------------------------


def test_source_for_url_youtube_dot_com():
    assert _source_for_url("https://www.youtube.com/watch?v=abc") == "youtube"


def test_source_for_url_youtu_be():
    assert _source_for_url("https://youtu.be/abc123") == "youtube"


def test_source_for_url_reddit_dot_com():
    assert _source_for_url("https://www.reddit.com/r/python/") == "reddit"


def test_source_for_url_old_reddit():
    assert _source_for_url("https://old.reddit.com/r/programming/") == "reddit"


def test_source_for_url_generic():
    assert _source_for_url("https://example.com/some/page") == "web_page"


def test_source_for_url_no_scheme_youtube():
    assert _source_for_url("youtube.com/watch?v=abc") == "youtube"


def test_source_for_url_no_scheme_reddit():
    assert _source_for_url("reddit.com/r/python") == "reddit"


def test_source_for_url_no_scheme_generic():
    assert _source_for_url("example.com/page") == "web_page"


# ---------------------------------------------------------------------------
# extract_content routing tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_content_routes_youtube_url():
    """A youtube.com URL must call fetch with source='youtube'."""
    assistant = _make_assistant()
    result = _make_content_result(
        url="https://www.youtube.com/watch?v=abc",
        structured={"title": "My Video"},
    )
    reg = _make_registry(result)

    with patch.dict(
        sys.modules,
        {
            "content_reach.registry": types.SimpleNamespace(get_content_source_registry=lambda: reg),
            "content_reach.base": types.SimpleNamespace(ContentRequest=MagicMock(side_effect=lambda **kw: kw)),
        },
    ):
        content = await assistant.extract_content("https://www.youtube.com/watch?v=abc")

    assert content is not None
    call_args = reg.fetch.call_args
    assert call_args[0][0] == "youtube"


@pytest.mark.asyncio
async def test_extract_content_routes_reddit_url():
    """A reddit.com URL must call fetch with source='reddit'."""
    assistant = _make_assistant()
    result = _make_content_result(url="https://www.reddit.com/r/python/", text="reddit post body")
    reg = _make_registry(result)

    with patch.dict(
        sys.modules,
        {
            "content_reach.registry": types.SimpleNamespace(get_content_source_registry=lambda: reg),
            "content_reach.base": types.SimpleNamespace(ContentRequest=MagicMock(side_effect=lambda **kw: kw)),
        },
    ):
        content = await assistant.extract_content("https://www.reddit.com/r/python/")

    assert content is not None
    assert reg.fetch.call_args[0][0] == "reddit"


@pytest.mark.asyncio
async def test_extract_content_routes_generic_to_web_page():
    """A generic URL must call fetch with source='web_page'."""
    assistant = _make_assistant()
    result = _make_content_result(
        url="https://example.com/page",
        text="page body text",
        structured={"title": "Example Page"},
    )
    reg = _make_registry(result)

    with patch.dict(
        sys.modules,
        {
            "content_reach.registry": types.SimpleNamespace(get_content_source_registry=lambda: reg),
            "content_reach.base": types.SimpleNamespace(ContentRequest=MagicMock(side_effect=lambda **kw: kw)),
        },
    ):
        content = await assistant.extract_content("https://example.com/page")

    assert content is not None
    assert reg.fetch.call_args[0][0] == "web_page"


@pytest.mark.asyncio
async def test_extract_content_maps_content_data_shape():
    """Returned dict must have exactly the 8 expected keys with correct values."""
    assistant = _make_assistant()
    result = _make_content_result(
        url="https://example.com/page",
        text="the main body text",
        structured={"title": "Page Title", "description": "Short desc"},
    )
    reg = _make_registry(result)

    with patch.dict(
        sys.modules,
        {
            "content_reach.registry": types.SimpleNamespace(get_content_source_registry=lambda: reg),
            "content_reach.base": types.SimpleNamespace(ContentRequest=MagicMock(side_effect=lambda **kw: kw)),
        },
    ):
        content = await assistant.extract_content("https://example.com/page")

    assert content is not None
    assert set(content.keys()) == _EXPECTED_CONTENT_DATA_KEYS
    assert content["url"] == "https://example.com/page"
    assert content["title"] == "Page Title"
    assert content["description"] == "Short desc"
    assert content["content"] == "the main body text"
    assert content["domain"] == "example.com"
    assert content["content_length"] == len("the main body text")
    assert content["timestamp"]  # non-empty ISO string
    assert isinstance(content["is_trusted"], bool)


@pytest.mark.asyncio
async def test_extract_content_trusted_domain_flagged():
    """A domain matching trusted_domains list must yield is_trusted=True."""
    assistant = _make_assistant()
    result = _make_content_result(
        url="https://github.com/some/repo",
        text="repo readme text",
        structured={"title": "Repo"},
    )
    reg = _make_registry(result)

    with patch.dict(
        sys.modules,
        {
            "content_reach.registry": types.SimpleNamespace(get_content_source_registry=lambda: reg),
            "content_reach.base": types.SimpleNamespace(ContentRequest=MagicMock(side_effect=lambda **kw: kw)),
        },
    ):
        content = await assistant.extract_content("https://github.com/some/repo")

    assert content is not None
    assert content["is_trusted"] is True


@pytest.mark.asyncio
async def test_extract_content_returns_none_on_failure():
    """success=False must return None."""
    assistant = _make_assistant()
    result = _make_content_result(success=False, text="")
    reg = _make_registry(result)

    with patch.dict(
        sys.modules,
        {
            "content_reach.registry": types.SimpleNamespace(get_content_source_registry=lambda: reg),
            "content_reach.base": types.SimpleNamespace(ContentRequest=MagicMock(side_effect=lambda **kw: kw)),
        },
    ):
        content = await assistant.extract_content("https://example.com/page")

    assert content is None


@pytest.mark.asyncio
async def test_extract_content_returns_none_on_empty_text():
    """success=True but empty/whitespace text must return None."""
    assistant = _make_assistant()
    result = _make_content_result(success=True, text="   ")
    reg = _make_registry(result)

    with patch.dict(
        sys.modules,
        {
            "content_reach.registry": types.SimpleNamespace(get_content_source_registry=lambda: reg),
            "content_reach.base": types.SimpleNamespace(ContentRequest=MagicMock(side_effect=lambda **kw: kw)),
        },
    ):
        content = await assistant.extract_content("https://example.com/page")

    assert content is None


@pytest.mark.asyncio
async def test_extract_content_returns_none_on_fetch_exception():
    """A fetch exception must be caught; returns None not raises."""
    assistant = _make_assistant()
    reg = MagicMock()
    reg.get_chain = MagicMock(return_value=MagicMock())
    reg.fetch = AsyncMock(side_effect=RuntimeError("network error"))

    with patch.dict(
        sys.modules,
        {
            "content_reach.registry": types.SimpleNamespace(get_content_source_registry=lambda: reg),
            "content_reach.base": types.SimpleNamespace(ContentRequest=MagicMock(side_effect=lambda **kw: kw)),
        },
    ):
        content = await assistant.extract_content("https://example.com/page")

    assert content is None


@pytest.mark.asyncio
async def test_extract_content_title_falls_back_to_netloc():
    """When structured has no title, title must default to the netloc."""
    assistant = _make_assistant()
    result = _make_content_result(
        url="https://example.com/page",
        text="body text",
        structured={},
    )
    reg = _make_registry(result)

    with patch.dict(
        sys.modules,
        {
            "content_reach.registry": types.SimpleNamespace(get_content_source_registry=lambda: reg),
            "content_reach.base": types.SimpleNamespace(ContentRequest=MagicMock(side_effect=lambda **kw: kw)),
        },
    ):
        content = await assistant.extract_content("https://example.com/page")

    assert content is not None
    assert content["title"] == "example.com"


@pytest.mark.asyncio
async def test_extract_content_description_falls_back_to_content_slice():
    """When structured has no description, description must be content[:200]."""
    assistant = _make_assistant()
    body = "A" * 300
    result = _make_content_result(url="https://example.com/page", text=body, structured={})
    reg = _make_registry(result)

    with patch.dict(
        sys.modules,
        {
            "content_reach.registry": types.SimpleNamespace(get_content_source_registry=lambda: reg),
            "content_reach.base": types.SimpleNamespace(ContentRequest=MagicMock(side_effect=lambda **kw: kw)),
        },
    ):
        content = await assistant.extract_content("https://example.com/page")

    assert content is not None
    assert content["description"] == body[:200]


# ---------------------------------------------------------------------------
# research_query no longer calls _check_playwright_service
# ---------------------------------------------------------------------------


def test_research_query_has_no_playwright_check():
    """research_query must not call _check_playwright_service (method removed)."""
    assert not hasattr(
        LibrarianAssistant, "_check_playwright_service"
    ), "_check_playwright_service was not removed from LibrarianAssistant"
