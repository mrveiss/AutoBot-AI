# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression tests for cross-project cross-language-pattern leakage (Issue #12356).

The ``/cross-language/*`` analytics endpoints accepted a ``source_id`` but
ignored it: the detector defaulted to AutoBot's own root and a single global
``_analysis_cache["latest"]`` entry, so opening one project's cross-language
analysis could return another project's patterns. The
``CrossLanguagePatternDetector`` also stored/queried its ChromaDB pattern
collection with no source scoping, so two projects sharing a fallback ChromaDB
path could cross-match.

These tests assert the fix end-to-end:
- the endpoint scopes both the scan root and the per-source cache to the caller;
- one source can never read another source's cached analysis;
- the detector tags every stored pattern with ``source_id``, filters queries by
  it, and keys its embedding cache per source.
"""

import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Endpoint-level isolation
# ---------------------------------------------------------------------------
class TestCrossLanguageCacheScoping:
    """The analysis cache and detector must be keyed per source, not global."""

    def test_cache_key_is_per_source(self):
        from api.codebase_analytics.endpoints.cross_language_patterns import _cache_key

        assert _cache_key(None) == "default"
        assert _cache_key("A") == "A"
        assert _cache_key("A") != _cache_key("B")

    async def test_analyze_scopes_detector_and_caches_per_source(self, tmp_path, monkeypatch):
        """POST /analyze binds the detector to the source root/tag and caches per source."""
        from api.codebase_analytics.endpoints import cross_language_patterns as clp

        root_a = tmp_path / "proj_a"
        root_a.mkdir()

        async def fake_scan_root(source_id, use_default=True):
            return {"A": root_a}.get(source_id, clp.Path("/tmp"))

        captured: dict = {}
        analysis_a = MagicMock(name="analysis_A")
        analysis_a.to_dict.return_value = {"marker": "A"}

        def fake_get_detector(project_root=None, source_id=None, use_llm=True, use_cache=True):
            captured["project_root"] = project_root
            captured["source_id"] = source_id
            detector = MagicMock()
            detector.run_analysis = AsyncMock(return_value=analysis_a)
            return detector

        clp._analysis_cache.clear()
        monkeypatch.setattr(clp, "resolve_scan_root", fake_scan_root)
        monkeypatch.setattr(clp, "_get_detector", fake_get_detector)

        await clp.run_cross_language_analysis(source_id="A")

        # Detector bound to the requested source's clone path and scope tag.
        assert captured["project_root"] == root_a
        assert captured["source_id"] == "A"
        # Cached under the per-source key, never the old global "latest".
        assert clp._analysis_cache["A"] is analysis_a
        assert "latest" not in clp._analysis_cache

    async def test_one_source_never_reads_anothers_analysis(self, tmp_path):
        """Project A's cached patterns are invisible to a project-B request."""
        from api.codebase_analytics.endpoints import cross_language_patterns as clp

        # Seed only source A.
        a_only = MagicMock()
        a_only.dto_mismatches = [MagicMock(to_dict=MagicMock(return_value={"owner": "A"}))]
        clp._analysis_cache.clear()
        clp._analysis_cache["A"] = a_only

        # B has no cached analysis → error, and A's data never leaks across.
        resp_b = await clp.get_dto_mismatches(source_id="B")
        assert resp_b.status_code == 400
        assert b"owner" not in resp_b.body

        # A still sees its own data.
        resp_a = await clp.get_dto_mismatches(source_id="A")
        data_a = json.loads(resp_a.body)
        assert data_a["status"] == "success"
        assert data_a["total"] == 1
        assert data_a["mismatches"] == [{"owner": "A"}]

    async def test_summary_scoped_to_source(self, tmp_path):
        """/summary returns 'empty' for an unseeded source rather than another's summary."""
        from api.codebase_analytics.endpoints import cross_language_patterns as clp

        clp._analysis_cache.clear()
        clp._analysis_cache["A"] = MagicMock()  # A seeded, B not

        resp_b = await clp.get_cross_language_summary(source_id="B")
        data_b = json.loads(resp_b.body)
        assert data_b["status"] == "empty"
        assert data_b["has_cached_data"] is False

    async def test_clear_cache_scoped_to_source(self):
        """Clearing one source's cache leaves other sources' entries intact."""
        from api.codebase_analytics.endpoints import cross_language_patterns as clp

        clp._analysis_cache.clear()
        clp._analysis_cache["A"] = MagicMock(name="A")
        clp._analysis_cache["B"] = MagicMock(name="B")

        await clp.clear_cross_language_cache(source_id="A")

        assert "A" not in clp._analysis_cache
        assert "B" in clp._analysis_cache


# ---------------------------------------------------------------------------
# Detector-level source scoping (real module, loaded under a synthetic package
# so the conftest ``code_intelligence`` stub is left untouched).
# ---------------------------------------------------------------------------
def _load_real_detector_class():
    """Load the real CrossLanguagePatternDetector without importing the heavy
    ``code_intelligence`` package __init__ (which the conftest stubs)."""
    base = Path(__file__).resolve().parents[3] / "code_intelligence" / "cross_language_patterns"
    pkg_name = "_real_clp_12356"

    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(base)]
        pkg.__package__ = pkg_name
        sys.modules[pkg_name] = pkg
        # Load submodules in dependency order so relative imports resolve.
        for sub in ("models", "extractors", "detector"):
            spec = importlib.util.spec_from_file_location(f"{pkg_name}.{sub}", base / f"{sub}.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[f"{pkg_name}.{sub}"] = module
            spec.loader.exec_module(module)

    return sys.modules[f"{pkg_name}.detector"].CrossLanguagePatternDetector


class TestDetectorSourceScoping:
    """The detector must scope its ChromaDB metadata/query and embedding cache."""

    def test_stored_pattern_metadata_tagged_with_source(self):
        detector_cls = _load_real_detector_class()

        det_a = detector_cls(source_id="A")
        meta = det_a._build_pattern_metadata({"language": "python", "pattern": {"type": "DTO", "name": "User"}})
        assert meta["source_id"] == "A"

        det_default = detector_cls()  # no source_id → "default", never another source's tag
        meta_default = det_default._build_pattern_metadata({"language": "python", "pattern": {}})
        assert meta_default["source_id"] == "default"

    async def test_query_filters_matches_by_source(self):
        detector_cls = _load_real_detector_class()
        det_a = detector_cls(source_id="A")

        captured: dict = {}

        class _FakeCollection:
            async def query(self, query_embeddings, n_results, where):
                captured["where"] = where
                return {"distances": [[]], "ids": [[]]}

        await det_a._query_cross_language_matches(
            _FakeCollection(),
            [{"id": "py1", "embedding": [0.1, 0.2]}],
            [],
        )

        assert captured["where"] == {"$and": [{"language": "typescript"}, {"source_id": "A"}]}

    def test_embedding_cache_key_is_per_source(self):
        detector_cls = _load_real_detector_class()

        det_a = detector_cls(source_id="A")
        det_b = detector_cls(source_id="B")

        assert det_a._embedding_cache_model != det_b._embedding_cache_model
        assert det_a._embedding_cache_model.startswith("nomic-embed-text")
        assert det_a._embedding_cache_model.endswith("A")
