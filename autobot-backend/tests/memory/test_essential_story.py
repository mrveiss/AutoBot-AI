# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for EssentialStoryGenerator (#3787)."""

# ---------------------------------------------------------------------------
# Stub out heavy optional imports before any project module is loaded.
# We use importlib to load essential_story.py directly, bypassing the
# memory package __init__ (which pulls in aiosqlite, ssot_config, etc.).
# ---------------------------------------------------------------------------
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _stub(name: str, attrs: dict = None, is_pkg: bool = False):
    """Register a lightweight stub module in sys.modules."""
    mod = types.ModuleType(name)
    if is_pkg:
        mod.__path__ = []
    if attrs:
        for k, v in attrs.items():
            setattr(mod, k, v)
    sys.modules.setdefault(name, mod)
    return mod


_stub("autobot_shared", is_pkg=True)
_stub("autobot_shared.redis_client")
_stub("autobot_shared.ssot_config", {"config": MagicMock()})
_stub("constants", is_pkg=True)
_stub("constants.ttl_constants", {"TTL_5_MINUTES": 300})
_stub("knowledge", is_pkg=True)
_stub("knowledge._composed")


def _load_essential_story():
    """Load memory/essential_story.py directly, bypassing memory/__init__."""
    _stub("memory", is_pkg=True)
    src = Path(__file__).parent.parent.parent / "memory" / "essential_story.py"
    spec = importlib.util.spec_from_file_location("memory.essential_story", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["memory.essential_story"] = mod
    spec.loader.exec_module(mod)
    return mod


_es_mod = _load_essential_story()
EssentialStoryGenerator = _es_mod.EssentialStoryGenerator
# Make the module reachable as an attribute so patch("memory.essential_story.X") works
sys.modules["memory"].essential_story = _es_mod

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_YAML_CONTENT = """
models:
  default:
    name: small-model
    context_window_tokens: 8192
    essential_story_tokens: 300
  big-model:
    context_window_tokens: 128000
    essential_story_tokens: 800
  medium-model:
    context_window_tokens: 32768
    essential_story_tokens: 600
token_estimation:
  chars_per_token: 4
  safety_margin: 0.9
"""


def _make_facts(count: int, quality_step: float = 0.1) -> list:
    return [
        {
            "fact_id": f"f{i}",
            "content": f"Fact number {i} with some content to fill tokens.",
            "metadata": {
                "category": f"cat{i % 3}",
                "quality_score": round(count * quality_step - i * quality_step, 2),
            },
            "timestamp": "2026-01-01T00:00:00",
        }
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetTokenBudget:
    @pytest.mark.asyncio
    async def test_reads_explicit_essential_story_tokens(self, tmp_path):
        yaml_file = tmp_path / "context_windows.yaml"
        yaml_file.write_text(_YAML_CONTENT, encoding="utf-8")
        gen = EssentialStoryGenerator()
        with patch("memory.essential_story._YAML_PATH", yaml_file):
            budget = await gen._get_token_budget("big-model")
        assert budget == 800

    @pytest.mark.asyncio
    async def test_derives_300_for_small_context(self, tmp_path):
        yaml_file = tmp_path / "context_windows.yaml"
        yaml_file.write_text("models:\n  tiny:\n    context_window_tokens: 4096\n", encoding="utf-8")
        gen = EssentialStoryGenerator()
        with patch("memory.essential_story._YAML_PATH", yaml_file):
            budget = await gen._get_token_budget("tiny")
        assert budget == 300

    @pytest.mark.asyncio
    async def test_derives_600_for_medium_context(self, tmp_path):
        yaml_file = tmp_path / "context_windows.yaml"
        yaml_file.write_text("models:\n  mid:\n    context_window_tokens: 32768\n", encoding="utf-8")
        gen = EssentialStoryGenerator()
        with patch("memory.essential_story._YAML_PATH", yaml_file):
            budget = await gen._get_token_budget("mid")
        assert budget == 600

    @pytest.mark.asyncio
    async def test_derives_800_for_large_context(self, tmp_path):
        yaml_file = tmp_path / "context_windows.yaml"
        yaml_file.write_text("models:\n  large:\n    context_window_tokens: 128000\n", encoding="utf-8")
        gen = EssentialStoryGenerator()
        with patch("memory.essential_story._YAML_PATH", yaml_file):
            budget = await gen._get_token_budget("large")
        assert budget == 800

    @pytest.mark.asyncio
    async def test_falls_back_to_default_on_missing_yaml(self, tmp_path):
        missing = tmp_path / "no_such_file.yaml"
        gen = EssentialStoryGenerator()
        with patch("memory.essential_story._YAML_PATH", missing):
            budget = await gen._get_token_budget("whatever")
        assert budget == 600  # _DEFAULT_BUDGET


class TestEstimateTokens:
    def test_empty_string(self):
        gen = EssentialStoryGenerator()
        assert gen._estimate_tokens("") == 0

    def test_ten_words(self):
        gen = EssentialStoryGenerator()
        text = "one two three four five six seven eight nine ten"
        assert gen._estimate_tokens(text) == int(10 * 1.3)


class TestFetchTopFacts:
    """Tests for _fetch_top_facts.

    Patch the `get_knowledge_base` attribute on the knowledge._composed stub
    module — that is what the lazy import inside _fetch_top_facts resolves to.
    """

    @pytest.mark.asyncio
    async def test_sorts_by_quality_desc(self):
        facts = _make_facts(5, quality_step=0.2)
        mock_kb = AsyncMock()
        mock_kb.get_all_facts = AsyncMock(return_value=facts)
        sys.modules["knowledge._composed"].get_knowledge_base = AsyncMock(return_value=mock_kb)

        gen = EssentialStoryGenerator()
        result = await gen._fetch_top_facts(max_tokens=10000)

        qualities = [f["metadata"]["quality_score"] for f in result]
        assert qualities == sorted(qualities, reverse=True)

    @pytest.mark.asyncio
    async def test_respects_token_budget(self):
        """Only facts that fit within max_tokens are returned."""
        # Each fact ~10 words * 1.3 = 13 tokens
        facts = _make_facts(20, quality_step=0.05)
        mock_kb = AsyncMock()
        mock_kb.get_all_facts = AsyncMock(return_value=facts)
        sys.modules["knowledge._composed"].get_knowledge_base = AsyncMock(return_value=mock_kb)

        gen = EssentialStoryGenerator()
        result = await gen._fetch_top_facts(max_tokens=40)

        # Each fact is ~13 tokens; 40 tokens allows at most 3
        assert len(result) <= 3

    @pytest.mark.asyncio
    async def test_passes_limit_to_get_all_facts(self):
        """Issue #3808: get_all_facts must be called with limit=200, not unbounded."""
        facts = _make_facts(200, quality_step=0.005)
        mock_kb = AsyncMock()
        mock_kb.get_all_facts = AsyncMock(return_value=facts)
        sys.modules["knowledge._composed"].get_knowledge_base = AsyncMock(return_value=mock_kb)

        gen = EssentialStoryGenerator()
        await gen._fetch_top_facts(max_tokens=100_000)

        mock_kb.get_all_facts.assert_awaited_once_with(limit=200)

    @pytest.mark.asyncio
    async def test_empty_kb_returns_empty_list(self):
        mock_kb = AsyncMock()
        mock_kb.get_all_facts = AsyncMock(return_value=[])
        sys.modules["knowledge._composed"].get_knowledge_base = AsyncMock(return_value=mock_kb)

        gen = EssentialStoryGenerator()
        result = await gen._fetch_top_facts(max_tokens=600)

        assert result == []


class TestFormatOutput:
    @pytest.mark.asyncio
    async def test_empty_facts_returns_empty_string(self):
        gen = EssentialStoryGenerator()
        assert await gen._format_output([]) == ""

    @pytest.mark.asyncio
    async def test_includes_header_and_category(self):
        facts = [
            {"content": "AutoBot is great.", "metadata": {"category": "product"}},
            {"content": "Redis is fast.", "metadata": {"category": "tech"}},
        ]
        gen = EssentialStoryGenerator()
        output = await gen._format_output(facts)
        assert output.startswith("## Essential Context")
        assert "[product] AutoBot is great." in output
        assert "[tech] Redis is fast." in output

    @pytest.mark.asyncio
    async def test_fact_with_no_category_defaults_to_general(self):
        facts = [{"content": "Some fact.", "metadata": {}}]
        gen = EssentialStoryGenerator()
        output = await gen._format_output(facts)
        assert "[general] Some fact." in output

    @pytest.mark.asyncio
    async def test_facts_with_empty_content_skipped(self):
        facts = [
            {"content": "", "metadata": {"category": "x"}},
            {"content": "Valid fact.", "metadata": {"category": "y"}},
        ]
        gen = EssentialStoryGenerator()
        output = await gen._format_output(facts)
        assert "[x]" not in output
        assert "[y] Valid fact." in output


class TestGenerate:
    @pytest.mark.asyncio
    async def test_returns_empty_string_on_kb_error(self):
        gen = EssentialStoryGenerator()
        # Patch _get_cached to return None (miss) then _fetch_top_facts raises
        with (
            patch.object(gen, "_get_cached", AsyncMock(return_value=None)),
            patch.object(gen, "_fetch_top_facts", AsyncMock(side_effect=RuntimeError("KB unavailable"))),
        ):
            result = await gen.generate(model_name="test-model")
        assert result == ""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_kb(self, tmp_path):
        yaml_file = tmp_path / "cw.yaml"
        yaml_file.write_text(_YAML_CONTENT, encoding="utf-8")

        gen = EssentialStoryGenerator()
        cached_story = "## Essential Context\n[x] cached"

        with (
            patch("memory.essential_story._YAML_PATH", yaml_file),
            patch.object(gen, "_get_cached", AsyncMock(return_value=cached_story)),
            patch.object(gen, "_fetch_top_facts", AsyncMock(side_effect=AssertionError("KB should not be called"))),
        ):
            result = await gen.generate(model_name="big-model")

        assert result == cached_story

    @pytest.mark.asyncio
    async def test_cache_miss_calls_kb_and_writes_cache(self, tmp_path):
        yaml_file = tmp_path / "cw.yaml"
        yaml_file.write_text(_YAML_CONTENT, encoding="utf-8")

        facts = _make_facts(2, quality_step=0.5)
        set_cached_mock = AsyncMock()

        gen = EssentialStoryGenerator()
        with (
            patch("memory.essential_story._YAML_PATH", yaml_file),
            patch.object(gen, "_get_cached", AsyncMock(return_value=None)),
            patch.object(gen, "_fetch_top_facts", AsyncMock(return_value=facts)),
            patch.object(gen, "_set_cached", set_cached_mock),
        ):
            result = await gen.generate(model_name="big-model")

        assert "## Essential Context" in result
        set_cached_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_never_raises(self):
        gen = EssentialStoryGenerator()
        # Simulate a failure deep in the pipeline
        with patch.object(gen, "_get_token_budget", AsyncMock(side_effect=Exception("boom"))):
            result = await gen.generate(model_name="broken-model")
        assert result == ""
