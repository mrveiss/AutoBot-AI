# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for run_code_analysis's silent-failure fix (#14543).

Every one of the five sub-scripts this orchestrator shells out to used to be
addressed under ``tools/code-analysis-suite/scripts/``, a directory that does
not exist in this repository. A missing script, a non-zero exit, and stdout
that fails to parse as JSON were all folded into an ``error`` key nested three
levels deep, while the *top-level* ``status`` stayed hardcoded to ``"success"``
and ``main()`` exited 0 -- a run that found nothing read as a completed one.

These drive the real orchestration functions against a scratch directory of
fake sub-scripts rather than the real (heavy, Redis-dependent) analyzers, so
a missing, failing, or malformed sub-script can be simulated deterministically.
"""

import importlib.util
import json
import pathlib
import sys

import pytest

_MODULE_PATH = pathlib.Path(__file__).with_name("run_code_analysis.py")


def _load_module():
    """Import run_code_analysis by path -- its directory is not a package."""
    spec = importlib.util.spec_from_file_location("run_code_analysis", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_code_analysis"] = module
    spec.loader.exec_module(module)
    return module


rca = _load_module()

_ALL_ANALYSIS_KEYS = ("code_quality", "duplicates", "performance", "architecture")


def _write_script(scripts_dir: pathlib.Path, name: str, body: str) -> None:
    (scripts_dir / name).write_text(body, encoding="utf-8")


@pytest.fixture
def scripts_dir(tmp_path, monkeypatch):
    """An empty stand-in for ``_ANALYSIS_SCRIPTS_DIR``, one per test."""
    directory = tmp_path / "scripts"
    directory.mkdir()
    monkeypatch.setattr(rca, "_ANALYSIS_SCRIPTS_DIR", directory)
    return directory


@pytest.fixture
def target_dir(tmp_path):
    directory = tmp_path / "target"
    directory.mkdir()
    return directory


def test_missing_scripts_flip_status_to_error(scripts_dir, target_dir):
    """No sub-script exists -- #14543's original bug report scenario."""
    results = rca.run_full_analysis(str(target_dir), "full")

    assert results["status"] == "error"
    assert sorted(results["failed_analyses"]) == sorted(_ALL_ANALYSIS_KEYS)
    for key in _ALL_ANALYSIS_KEYS:
        assert "Script not found" in results[key]["error"]
    # #14543: no per-analysis fallback may fabricate placeholder metrics.
    assert "codebase_metrics" not in results


def test_missing_script_is_never_folded_into_success(scripts_dir, target_dir):
    result = rca.run_code_quality_analysis(str(target_dir))
    assert "error" in result
    assert result.get("status") != "success"


def test_nonzero_exit_reports_error_not_success(scripts_dir, target_dir):
    _write_script(scripts_dir, "analyze_code_quality.py", "import sys\nsys.exit(3)\n")

    result = rca.run_code_quality_analysis(str(target_dir))

    assert "error" in result
    assert "complexity" not in result


def test_malformed_output_reports_error_not_fabricated_defaults(scripts_dir, target_dir):
    """A returncode-0 script that prints non-JSON must not synthesize metrics.

    This used to return ``{"complexity": 5, "test_coverage": 70, ...}`` on a
    ``JSONDecodeError`` -- numbers invented by the orchestrator, not measured.
    """
    _write_script(scripts_dir, "analyze_code_quality.py", "print('not json, just log lines')\n")

    result = rca.run_code_quality_analysis(str(target_dir))

    assert "error" in result
    assert "complexity" not in result
    assert "test_coverage" not in result


def test_valid_json_output_is_returned_verbatim(scripts_dir, target_dir):
    payload = {"status": "success", "complexity": 3, "maintainability": "excellent"}
    _write_script(
        scripts_dir,
        "analyze_code_quality.py",
        f"import json\nprint(json.dumps({payload!r}))\n",
    )

    result = rca.run_code_quality_analysis(str(target_dir))

    assert result == payload
    assert "error" not in result


def test_subprocess_cwd_is_pinned_to_target_path(scripts_dir, target_dir):
    """The sub-scripts resolve their own analysis root from cwd, not argv."""
    _write_script(
        scripts_dir,
        "analyze_architecture.py",
        "import json, os\nprint(json.dumps({'cwd': os.getcwd()}))\n",
    )

    result = rca.run_architecture_analysis(str(target_dir))

    assert result["cwd"] == str(target_dir.resolve())


def test_main_exits_nonzero_when_every_analysis_fails(scripts_dir, target_dir, capsys, monkeypatch):
    argv = ["run_code_analysis.py", "--target", str(target_dir), "--analysis-type", "quality"]
    monkeypatch.setattr(sys, "argv", argv)

    with pytest.raises(SystemExit) as exc_info:
        rca.main()

    assert exc_info.value.code != 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == "error"


def test_main_exits_zero_when_analysis_succeeds(scripts_dir, target_dir, capsys, monkeypatch):
    _write_script(
        scripts_dir,
        "analyze_code_quality.py",
        "import json\nprint(json.dumps({'status': 'success', 'complexity': 1}))\n",
    )
    argv = ["run_code_analysis.py", "--target", str(target_dir), "--analysis-type", "quality"]
    monkeypatch.setattr(sys, "argv", argv)

    rca.main()

    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == "success"
