# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for run_code_analysis's codebase_metrics rollup (#14635).

``_extract_codebase_metrics`` used to read ``complexity`` / ``maintainability``
/ ``test_coverage`` / ``doc_coverage`` off the *top level* of the parsed
``comprehensive_quality_report.json``. The real producer -- ``code_quality_
dashboard.py``'s ``generate_comprehensive_report``, written verbatim to that
file by ``analyze_code_quality.py`` -- nests its scores under a
``quality_metrics`` object instead, as ``maintainability_index`` and
``test_coverage_score``, and has no ``complexity`` or ``doc_coverage`` field
anywhere. Every one of the four numbers this function returned was therefore
its own hardcoded ``.get(key, default)`` fallback, even on a genuinely
successful run.

Derives the producer's real ``quality_metrics`` key set from
``code_quality_dashboard.py``'s own source (the dict literal in
``_build_report_dict``) rather than restating it by hand, then drives that
shape through ``_extract_codebase_metrics`` and asserts the real numbers come
through -- not fallback constants.
"""

import importlib.util
import pathlib
import re
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_MODULE_PATH = _REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts" / "run_code_analysis.py"
_DASHBOARD_PATH = _REPO_ROOT / "autobot-backend" / "code_analysis" / "src" / "code_quality_dashboard.py"

# Matches each ``"key": qm.attr,`` line inside the ``quality_metrics`` dict
# literal in ``CodeQualityDashboard._build_report_dict``.
_QUALITY_METRICS_KEY_RE = re.compile(r'"([a-z_]+)":\s*qm\.\w+,')


def _load_module():
    """Import run_code_analysis by path -- its directory is not a package."""
    spec = importlib.util.spec_from_file_location("run_code_analysis_14635", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_code_analysis_14635"] = module
    spec.loader.exec_module(module)
    return module


def _real_quality_metrics_keys() -> set:
    """The key set the real dashboard's ``quality_metrics`` object carries."""
    source = _DASHBOARD_PATH.read_text(encoding="utf-8")
    block = source.split('"quality_metrics": {', 1)[1].split("},", 1)[0]
    return set(_QUALITY_METRICS_KEY_RE.findall(block))


rca = _load_module()

# A payload shaped exactly like the real ``generate_comprehensive_report``
# output: scores nested under "quality_metrics", no top-level "complexity" /
# "maintainability" / "test_coverage" / "doc_coverage" keys at all.
_REAL_SHAPED_REPORT = {
    "status": "success",
    "timestamp": "2026-08-16T00:00:00+00:00",
    "overall_quality_score": 91.2,
    "quality_metrics": {
        "overall_score": 91.2,
        "code_duplication_score": 95.0,
        "environment_config_score": 88.0,
        "performance_score": 90.5,
        "security_score": 97.0,
        "api_consistency_score": 84.0,
        "test_coverage_score": 88.0,
        "architecture_score": 92.0,
        "maintainability_index": 77.5,
        "technical_debt_ratio": 3.1,
    },
    "files_analyzed": 42,
}


def test_real_dashboard_key_set_has_no_complexity_or_doc_coverage():
    """Ground truth: the producer's real key set, read from its own source."""
    keys = _real_quality_metrics_keys()
    assert "maintainability_index" in keys
    assert "test_coverage_score" in keys
    assert "complexity" not in keys
    assert "doc_coverage" not in keys


def test_field_map_targets_keys_the_real_producer_actually_writes():
    """The orchestrator's mapping must draw only from keys the dashboard emits."""
    real_keys = _real_quality_metrics_keys()
    assert set(rca._QUALITY_METRICS_FIELD_MAP.values()) <= real_keys


def test_extract_returns_real_numbers_not_fabricated_defaults():
    metrics = rca._extract_codebase_metrics({"code_quality": _REAL_SHAPED_REPORT})

    assert metrics == {"maintainability": 77.5, "test_coverage": 88.0}
    # The historical fabricated defaults must never appear.
    assert metrics.get("complexity") is None
    assert metrics.get("doc_coverage") is None
    assert "complexity" not in metrics
    assert "doc_coverage" not in metrics


def test_extract_returns_none_when_quality_analysis_failed():
    results = {"code_quality": {"error": "boom"}}
    assert rca._extract_codebase_metrics(results) is None


def test_extract_returns_none_when_no_quality_analysis_ran():
    assert rca._extract_codebase_metrics({}) is None


def test_extract_raises_on_shape_mismatch_missing_quality_metrics():
    """A successful report missing 'quality_metrics' is a producer/consumer
    disagreement -- it must surface, not silently degrade to defaults."""
    results = {"code_quality": {"status": "success", "complexity": 3, "maintainability": "excellent"}}

    with pytest.raises(ValueError, match="quality_metrics"):
        rca._extract_codebase_metrics(results)


def test_extract_raises_on_shape_mismatch_incomplete_quality_metrics():
    results = {"code_quality": {"status": "success", "quality_metrics": {"overall_score": 91.2}}}

    with pytest.raises(ValueError, match="missing expected keys"):
        rca._extract_codebase_metrics(results)


def test_run_full_analysis_reports_the_real_metrics(tmp_path, monkeypatch):
    """End-to-end through run_full_analysis with a real-shaped report file."""
    import json

    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    monkeypatch.setattr(rca, "_ANALYSIS_SCRIPTS_DIR", scripts_dir)

    body = (
        "import json\n"
        f"json.dump({_REAL_SHAPED_REPORT!r}, open('comprehensive_quality_report.json', 'w', encoding='utf-8'))\n"
    )
    (scripts_dir / "analyze_code_quality.py").write_text(body, encoding="utf-8")

    target_dir = tmp_path / "target"
    target_dir.mkdir()

    results = rca.run_full_analysis(str(target_dir), "quality")

    assert results["status"] == "success"
    assert results["codebase_metrics"] == {"maintainability": 77.5, "test_coverage": 88.0}
