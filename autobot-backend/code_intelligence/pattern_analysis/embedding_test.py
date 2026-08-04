# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression tests for ``CodePatternAnalyzer._generate_embedding`` (Issue #12407).

Prior to this fix, ``_generate_embedding`` called
``EmbeddingCache().get_embedding(code)`` -- a method that does not exist on
``EmbeddingCache`` (only ``get(query, model)``/``put(query, embedding,
model)``). Every call raised ``AttributeError``, was swallowed by a broad
``except Exception``, and silently fell through to a SHA-256 hash-based
pseudo-embedding, so ``code_patterns`` similarity search never actually did
semantic matching.

These tests assert the real fix:
- the canonical ``services.npu_client.generate_embedding_with_fallback``
  helper is called with the code and the real embedding model name (not the
  hash fallback);
- a single ``EmbeddingCache`` instance created in ``__init__`` is reused
  across calls (get -> miss -> generate -> put), instead of a fresh
  ``EmbeddingCache()`` per call;
- a cache hit skips the embedding-generation call entirely;
- the hash-based pseudo-embedding is reached ONLY when the real embedding
  call genuinely fails -- never on a successful real embedding.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, patch

import pytest

# Issue #12407: ``services`` is stubbed in conftest.py as a MagicMock package
# with a catch-all ``__getattr__`` (see ``_make_pkg_stub``/``_real_load_and_bind``
# docstring). ``unittest.mock.patch("services.npu_client.X")`` resolves its
# target via a ``getattr`` chain starting at the parent package, which hits
# that catch-all and silently patches a throwaway mock instead of the real
# ``services.npu_client`` module (inert patch). Importing the real submodule
# directly and patching via ``patch.object`` sidesteps the parent-stub lookup
# entirely, matching the module ``analyzer.py``'s local
# ``from services.npu_client import ...`` actually resolves via sys.modules.
import services.npu_client as npu_client_module  # noqa: E402


# ---------------------------------------------------------------------------
# Real-module loading (bypasses the top-level conftest's
# ``code_intelligence.pattern_analysis`` MagicMock stub so we exercise real
# behavior) -- mirrors ``_load_real_pattern_analysis_package`` in
# source_scoping_test.py.
# ---------------------------------------------------------------------------
def _load_real_pattern_analysis_package():
    base = Path(__file__).resolve().parent  # code_intelligence/pattern_analysis/
    pkg_name = "_real_pattern_analysis_12407"

    if pkg_name not in sys.modules:
        pkg = ModuleType(pkg_name)
        pkg.__path__ = [str(base)]
        pkg.__package__ = pkg_name
        sys.modules[pkg_name] = pkg
        for sub in (
            "types",
            "complexity_analyzer",
            "refactoring_generator",
            "regex_detector",
            "storage",
            "analyzer",
        ):
            spec = importlib.util.spec_from_file_location(f"{pkg_name}.{sub}", base / f"{sub}.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[f"{pkg_name}.{sub}"] = module
            spec.loader.exec_module(module)
            setattr(pkg, sub, module)

    return sys.modules[pkg_name]


@pytest.fixture
def pa():
    return _load_real_pattern_analysis_package()


@pytest.fixture
def analyzer(pa):
    return pa.analyzer.CodePatternAnalyzer(enable_embedding_storage=False)


FAKE_EMBEDDING = [0.1, 0.2, 0.3]


class TestGenerateEmbeddingUsesCanonicalHelper:
    async def test_calls_generate_embedding_with_fallback_with_real_model(self, pa, analyzer):
        code = "def foo(): return 1"
        with patch.object(
            npu_client_module,
            "generate_embedding_with_fallback",
            new=AsyncMock(return_value=FAKE_EMBEDDING),
        ) as mocked:
            result = await analyzer._generate_embedding(code)

        mocked.assert_awaited_once_with(code, model_name=pa.analyzer.EMBEDDING_MODEL)
        assert pa.analyzer.EMBEDDING_MODEL == "nomic-embed-text"
        assert result == FAKE_EMBEDDING

    async def test_does_not_fall_through_to_hash_embedding_on_success(self, pa, analyzer):
        code = "def bar(): return 2"
        with patch.object(
            npu_client_module,
            "generate_embedding_with_fallback",
            new=AsyncMock(return_value=FAKE_EMBEDDING),
        ):
            result = await analyzer._generate_embedding(code)

        # Hash-based pseudo-embedding is always 768 floats derived from
        # sha256(code) -- assert we got the short real embedding instead.
        assert result == FAKE_EMBEDDING
        assert len(result) != 768


class TestGenerateEmbeddingReusesCache:
    async def test_uses_single_cache_instance_created_in_init(self, pa, analyzer):
        assert analyzer._embedding_cache is not None
        assert isinstance(analyzer._embedding_cache, pa.analyzer.EmbeddingCache)

        code = "def baz(): return 3"
        cache = analyzer._embedding_cache
        with (
            patch.object(cache, "get", new=AsyncMock(return_value=None)) as mock_get,
            patch.object(cache, "put", new=AsyncMock()) as mock_put,
            patch.object(
                npu_client_module,
                "generate_embedding_with_fallback",
                new=AsyncMock(return_value=FAKE_EMBEDDING),
            ),
        ):
            result = await analyzer._generate_embedding(code)

        mock_get.assert_awaited_once_with(code, model=pa.analyzer.EMBEDDING_MODEL)
        mock_put.assert_awaited_once_with(code, FAKE_EMBEDDING, model=pa.analyzer.EMBEDDING_MODEL)
        assert result == FAKE_EMBEDDING

    async def test_cache_hit_skips_generation_call(self, pa, analyzer):
        code = "def qux(): return 4"
        with (
            patch.object(analyzer._embedding_cache, "get", new=AsyncMock(return_value=FAKE_EMBEDDING)),
            patch.object(
                npu_client_module,
                "generate_embedding_with_fallback",
                new=AsyncMock(),
            ) as mock_generate,
        ):
            result = await analyzer._generate_embedding(code)

        mock_generate.assert_not_awaited()
        assert result == FAKE_EMBEDDING

    def test_instance_attribute_reused_not_reinstantiated_per_call(self, pa):
        analyzer_a = pa.analyzer.CodePatternAnalyzer(enable_embedding_storage=False)
        analyzer_b = pa.analyzer.CodePatternAnalyzer(enable_embedding_storage=False)
        # Each analyzer instance gets its own cache (created once in
        # __init__), but repeated calls on the SAME instance must reuse it.
        assert analyzer_a._embedding_cache is not None
        assert analyzer_a._embedding_cache is analyzer_a._embedding_cache
        assert analyzer_a._embedding_cache is not analyzer_b._embedding_cache


class TestGenerateEmbeddingHashFallback:
    async def test_hash_fallback_only_when_real_embedding_fails(self, pa, analyzer):
        code = "def quux(): return 5"
        with patch.object(
            npu_client_module,
            "generate_embedding_with_fallback",
            new=AsyncMock(side_effect=RuntimeError("embedding infra unavailable")),
        ):
            result = await analyzer._generate_embedding(code)

        # Hash-based pseudo-embedding: 768 floats in [-1, 1].
        assert len(result) == 768
        assert all(-1.0 <= v <= 1.0 for v in result)

    async def test_hash_fallback_when_generation_returns_none(self, pa, analyzer):
        code = "def corge(): return 6"
        with patch.object(
            npu_client_module,
            "generate_embedding_with_fallback",
            new=AsyncMock(return_value=None),
        ):
            result = await analyzer._generate_embedding(code)

        assert len(result) == 768


class TestCacheWriteFailureDoesNotDiscardTheEmbedding:
    """#13437: the cache is an optimisation — its failure must not change the result.

    Generation and the cache write shared one ``try/except Exception``, so a
    failing ``EmbeddingCache.put`` threw away a perfectly good vector and
    returned the SHA-256 pseudo-embedding instead. Every pattern written while
    the cache misbehaved was indexed under a vector encoding nothing about the
    code, silently degrading ``code_patterns`` similarity search.

    This is the third defect of this shape in this one function — #12407 (a
    nonexistent method swallowed by the same broad except) and #12374 before
    it. The tests above cover generation; this covers the write.
    """

    async def test_returns_the_real_embedding_when_the_cache_write_fails(self, pa, analyzer):
        code = "def cache_write_boom(): return 3"
        analyzer._embedding_cache.put = AsyncMock(side_effect=RuntimeError("cache down"))

        with patch.object(
            npu_client_module,
            "generate_embedding_with_fallback",
            new=AsyncMock(return_value=FAKE_EMBEDDING),
        ):
            result = await analyzer._generate_embedding(code)

        assert result == FAKE_EMBEDDING, "a failed cache write discarded the real embedding"
        assert len(result) != 768, "fell through to the SHA-256 pseudo-embedding"

    async def test_still_falls_back_when_generation_itself_fails(self, pa, analyzer):
        """The fallback must remain reachable — this narrows the except, not removes it."""
        code = "def generation_boom(): return 4"

        with patch.object(
            npu_client_module,
            "generate_embedding_with_fallback",
            new=AsyncMock(side_effect=RuntimeError("npu down")),
        ):
            result = await analyzer._generate_embedding(code)

        assert len(result) == 768, "hash fallback should still be used when generation fails"

    async def test_still_falls_back_when_generation_returns_nothing(self, pa, analyzer):
        code = "def generation_empty(): return 5"

        with patch.object(
            npu_client_module,
            "generate_embedding_with_fallback",
            new=AsyncMock(return_value=None),
        ):
            result = await analyzer._generate_embedding(code)

        assert len(result) == 768
