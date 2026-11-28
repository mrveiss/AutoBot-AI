# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for NPU code search agent - Issue #3290.

Covers:
- NPU device is used (not CPU fallback) when OpenVINO model is compiled on NPU
- CPU fallback is reported accurately when NPU is unavailable
- search_code() stats reflect actual device used, not just npu_available flag
- _fallback_word_matching sets npu_acceleration_used=False
- get_index_status exposes NPU utilisation fields
"""

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.base_agent_types import AgentRequest
from agents.npu_code_search_agent import NPUCodeSearchAgent, NpuCodeSearchResult, SearchStats

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_agent(npu_available: bool = True) -> NPUCodeSearchAgent:
    """Construct a minimally-initialised NPUCodeSearchAgent for testing."""
    with (
        patch("agents.npu_code_search_agent.get_redis_client", return_value=MagicMock()),
        patch("agents.npu_code_search_agent.WorkerNode") as mock_worker,
    ):
        mock_worker.return_value.detect_capabilities.return_value = {
            "openvino_npu_available": npu_available,
        }
        # Patch Core so _init_npu doesn't need real OpenVINO
        with patch("agents.npu_code_search_agent.Core", MagicMock(), create=True):
            agent = NPUCodeSearchAgent.__new__(NPUCodeSearchAgent)
            # Manually set required attributes to avoid full __init__
            agent.logger = MagicMock()
            agent.redis_client = MagicMock()
            agent.redis_async_client = None
            agent.npu_available = npu_available
            agent.npu_search_engine = None
            agent.index_prefix = "autobot:code:index:"
            agent.search_cache_prefix = "autobot:search:cache:"
            agent.cache_ttl = 3600
            agent.stats = SearchStats(0, 0.0, False, False, 0)
            agent.supported_extensions = NPUCodeSearchAgent._get_supported_extensions()
            agent.language_patterns = NPUCodeSearchAgent._get_language_patterns()
    return agent


def _make_code_result(file_path: str = "foo.py", confidence: float = 0.9) -> NpuCodeSearchResult:
    return NpuCodeSearchResult(
        file_path=file_path,
        content="def foo(): pass",
        line_number=1,
        confidence=confidence,
        context_lines=[],
        metadata={"search_type": "semantic_embedding", "device_used": "npu"},
    )


# ---------------------------------------------------------------------------
# Tests: search_code() stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_code_stats_reflect_actual_device_npu():
    """search_code() must not overwrite npu_acceleration_used set by sub-methods."""
    agent = _make_agent(npu_available=True)
    expected_result = [_make_code_result()]

    # Simulate _execute_search_by_type setting stats via _search_code_embeddings
    async def _fake_execute(query, search_type, language, max_results, source_id):
        agent.stats.npu_acceleration_used = True  # set by real embedding path
        return expected_result

    agent.redis_client.get = MagicMock(return_value=None)  # no cache hit

    async def _fake_redis_get(cache_key):
        return None

    async def _fake_redis_setex(key, ttl, value):
        pass

    with (
        patch.object(agent, "_execute_search_by_type", side_effect=_fake_execute),
        patch(
            "agents.npu_code_search_agent.asyncio.to_thread",
            new=AsyncMock(return_value=None),
        ),
    ):
        results = await agent.search_code("find auth function", search_type="semantic", source_id="src")

    assert results == expected_result
    # Issue #3290: npu_acceleration_used must reflect what _fake_execute set (True)
    assert agent.stats.npu_acceleration_used is True


@pytest.mark.asyncio
async def test_search_code_stats_reflect_actual_device_cpu_fallback():
    """When embedding search fails and word-matching runs, npu_acceleration_used=False."""
    agent = _make_agent(npu_available=True)

    async def _fake_execute(query, search_type, language, max_results, source_id):
        # Simulate the fallback path having run (sets False)
        agent.stats.npu_acceleration_used = False
        return []

    with (
        patch.object(agent, "_execute_search_by_type", side_effect=_fake_execute),
        patch(
            "agents.npu_code_search_agent.asyncio.to_thread",
            new=AsyncMock(return_value=None),
        ),
    ):
        await agent.search_code("find something", search_type="semantic", source_id="src")

    # Issue #3290: must NOT override False with True just because npu_available=True
    assert agent.stats.npu_acceleration_used is False


# ---------------------------------------------------------------------------
# Tests: _fallback_word_matching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_word_matching_marks_npu_not_used():
    """_fallback_word_matching must set npu_acceleration_used=False."""
    agent = _make_agent(npu_available=True)
    agent.stats.npu_acceleration_used = True  # pretend it was set earlier

    with patch(
        "agents.npu_code_search_agent.asyncio.to_thread",
        new=AsyncMock(return_value=[]),  # no indexed files
    ):
        results = await agent._fallback_word_matching("auth", None, 10, "src")

    assert results == []
    # Issue #3290: word-matching path must mark NPU as NOT used
    assert agent.stats.npu_acceleration_used is False


# ---------------------------------------------------------------------------
# Tests: get_index_status NPU fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_index_status_exposes_npu_fields():
    """get_index_status must include npu_acceleration_used and last_search_device."""
    agent = _make_agent(npu_available=True)
    agent.stats.npu_acceleration_used = True

    def _fake_thread_call(fn, *args, **kwargs):
        # Return (file_count, language_stats, cache_count)
        return fn()

    def _fetch_status():
        return 5, {"python": 3, "javascript": 2}, 1

    with patch(
        "agents.npu_code_search_agent.asyncio.to_thread",
        new=AsyncMock(return_value=(5, {"python": 3}, 1)),
    ):
        status = await agent.get_index_status()

    assert "npu_acceleration_used" in status
    assert "last_search_device" in status
    assert status["npu_acceleration_used"] is True
    assert status["last_search_device"] == "npu"


@pytest.mark.asyncio
async def test_get_index_status_last_device_cpu_when_not_npu():
    """last_search_device must be 'cpu' when npu_acceleration_used=False."""
    agent = _make_agent(npu_available=False)
    agent.stats.npu_acceleration_used = False

    with patch(
        "agents.npu_code_search_agent.asyncio.to_thread",
        new=AsyncMock(return_value=(0, {}, 0)),
    ):
        status = await agent.get_index_status()

    assert status["last_search_device"] == "cpu"


# ---------------------------------------------------------------------------
# Tests: declared_scopes (#16173, #15950)
# ---------------------------------------------------------------------------


def _request(action: str, payload: dict | None = None) -> AgentRequest:
    return AgentRequest(
        request_id="req-1",
        agent_type="npu_code_search",
        action=action,
        payload=payload or {},
    )


def test_index_directory_declares_a_scope():
    agent = _make_agent()
    scopes = agent.declared_scopes(_request("index_directory", {"directory": "/repo/src"}))
    assert len(scopes) == 1
    assert re.fullmatch(r"project:code-index-[0-9a-f]{16}", scopes[0])


def test_index_directory_without_a_directory_declares_nothing():
    agent = _make_agent()
    assert agent.declared_scopes(_request("index_directory", {})) == []


def test_search_code_declares_nothing():
    agent = _make_agent()
    assert agent.declared_scopes(_request("search_code", {"query": "foo"})) == []


def test_get_capabilities_declares_nothing():
    agent = _make_agent()
    assert agent.declared_scopes(_request("get_capabilities", {})) == []


def test_declared_scope_leaks_neither_a_path_separator_nor_the_directory():
    """The leak this design avoids: a raw path in the claim table (#15949)."""
    agent = _make_agent()
    directory = "/repo/internal/secret-project-name"
    (scope,) = agent.declared_scopes(_request("index_directory", {"directory": directory}))

    assert "/" not in scope
    assert "\\" not in scope
    assert directory not in scope
    assert "secret-project-name" not in scope


def test_two_runs_on_the_same_directory_declare_the_same_scope():
    """The one collision that matters -- must agree with `_get_index_key`."""
    agent = _make_agent()
    directory = "/repo/src"

    first = agent.declared_scopes(_request("index_directory", {"directory": directory}))
    second = agent.declared_scopes(_request("index_directory", {"directory": directory}))

    assert first == second
    assert first[0].removeprefix("project:code-index-") in agent._get_index_key(directory, "src")


# ---------------------------------------------------------------------------
# Tests: the index is keyed by source (#20402)
# ---------------------------------------------------------------------------


class _FakeRedis:
    """Just enough Redis for the index: strings, sets, lists and glob `keys`."""

    def __init__(self):
        self.data = {}

    def setex(self, key, ttl, value):
        self.data[key] = value

    def get(self, key):
        return self.data.get(key)

    def exists(self, key):
        return key in self.data

    def sadd(self, key, member):
        self.data.setdefault(key, set()).add(member)

    def lpush(self, key, value):
        self.data.setdefault(key, []).insert(0, value)

    def expire(self, key, ttl):
        pass

    def keys(self, pattern):
        import fnmatch

        return [k for k in self.data if fnmatch.fnmatchcase(k, pattern)]


def _two_roots(tmp_path):
    """Two roots holding the SAME relative path `pkg/mod.py` with different content."""
    roots = {}
    for name in ("a", "b"):
        root = tmp_path / name
        (root / "pkg").mkdir(parents=True)
        (root / "pkg" / "mod.py").write_text(f"def only_in_{name}():\n    return '{name}'\n", encoding="utf-8")
        roots[name] = str(root)
    return roots


async def _index_both_roots(agent, roots):
    agent.redis_client = _FakeRedis()
    agent._generate_and_store_embeddings = AsyncMock(return_value=0)
    identity = lambda path, allowed_roots=None: path  # noqa: E731 - tmp_path is outside the project roots
    with patch("agents.npu_code_search_agent.validate_path", identity):
        for source_id, root in (("src-a", roots["a"]), ("src-b", roots["b"])):
            await agent._index_file(f"{root}/pkg/mod.py", "pkg/mod.py", root, source_id)
    return identity


@pytest.mark.asyncio
async def test_two_roots_with_the_same_relative_path_are_both_retrievable(tmp_path):
    """The later index no longer overwrites the earlier file's entry (#20402 AC1)."""
    agent = _make_agent()
    roots = _two_roots(tmp_path)
    identity = await _index_both_roots(agent, roots)

    file_keys = sorted(agent.redis_client.keys("autobot:code:index:source_id:*:file:*"))
    assert file_keys == [
        "autobot:code:index:source_id:src-a:file:pkg/mod.py",
        "autobot:code:index:source_id:src-b:file:pkg/mod.py",
    ]
    with patch("agents.npu_code_search_agent.validate_path", identity):
        found_a = await agent._search_exact("only_in_a", None, 10, "src-a")
        found_b = await agent._search_exact("only_in_b", None, 10, "src-b")
    assert [r.file_path for r in found_a] == [f"{roots['a']}/pkg/mod.py"]
    assert [r.file_path for r in found_b] == [f"{roots['b']}/pkg/mod.py"]


@pytest.mark.asyncio
async def test_search_is_limited_to_one_source(tmp_path):
    """A source's search never returns another source's file, for every file-scanning search type (#20402 AC2)."""
    agent = _make_agent()
    identity = await _index_both_roots(agent, _two_roots(tmp_path))

    with patch("agents.npu_code_search_agent.validate_path", identity):
        assert await agent._search_exact("only_in_b", None, 10, "src-a") == []
        assert await agent._search_regex("only_in_b", None, 10, "src-a") == []
        assert await agent._fallback_word_matching("only_in_b", None, 10, "src-a") == []
        assert len(await agent._search_regex("only_in_a", None, 10, "src-a")) == 1


@pytest.mark.asyncio
async def test_a_search_or_index_without_a_source_is_refused_not_unscoped():
    agent = _make_agent()
    with pytest.raises(ValueError):
        await agent.search_code("q", search_type="exact")
    with pytest.raises(ValueError):
        await agent.index_codebase("/repo")
    with pytest.raises(ValueError):
        agent._get_index_key("/repo", "bad:id")


def test_the_same_root_under_two_sources_has_two_index_keys():
    agent = _make_agent()
    assert agent._get_index_key("/repo", "src-a") != agent._get_index_key("/repo", "src-b")
