# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for run_code_analysis's silent-failure fix (#14543) and its
output-channel fix (#14587).

Every one of the five sub-scripts this orchestrator shells out to used to be
addressed under ``tools/code-analysis-suite/scripts/``, a directory that does
not exist in this repository (#14543). Fixing that path revealed a second,
deeper defect (#14587): the orchestrator parsed the subprocess's *stdout* as
JSON, but all five real sub-scripts write their report to a *file* in their
``cwd`` (four via ``json.dump``, printing only human-readable text; the fifth,
``analyze_performance_simple.py``, wrote no structured output at all) -- so a
real invocation always hit the "no parseable JSON" branch and a run could
never report ``status: "success"``.

#14583's own tests for #14543 drove the orchestrator against hand-written fake
sub-scripts that printed JSON to stdout -- a shape no real producer emits, and
exactly the gap that let #14587 through unnoticed. The tests below keep the
channel-agnostic failure-mode cases (missing script, non-zero exit -- these
don't depend on which channel carries the payload), rewrite the success-path
cases to use the file channel the real scripts actually use, add a test that
derives the orchestrator/analyzer contract from both sides by reading it out
of the five real script files, and add an end-to-end test that copies and
runs the real, unmodified ``analyze_performance_simple.py`` -- the lightest of
the five sub-scripts (stdlib plus one repo utility, no Redis/sklearn) -- to
prove a real invocation reaches ``status: "success"``.

Lives under ``repo_tests/`` rather than beside the module it tests: this file
was originally created (#14543/#14583) at
``autobot-infrastructure/shared/scripts/run_code_analysis_test.py``, but
``autobot-infrastructure/`` is in no pytest ``testpaths`` entry and in no CI
pytest invocation -- it was never collected, so its guarantees, including the
both-sides contract check added here, never actually ran. Same defect class,
same fix, as ``infra_scripts_live_defects_14507_test.py`` and #14131 (the
broader collection-gap tracking issue; this file's move does not close it).
"""

import importlib.util
import json
import pathlib
import re
import shutil
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_MODULE_PATH = _REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts" / "run_code_analysis.py"


def _load_module():
    """Import run_code_analysis by path -- its directory is not a package."""
    spec = importlib.util.spec_from_file_location("run_code_analysis", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_code_analysis"] = module
    spec.loader.exec_module(module)
    return module


rca = _load_module()

# Captured before any test monkeypatches ``rca._ANALYSIS_SCRIPTS_DIR`` --
# this is the orchestrator's own resolution of where the real sub-scripts
# live, so the real-script tests below stay correct if that resolution ever
# changes rather than restating the path independently.
_REAL_SCRIPTS_DIR = rca._ANALYSIS_SCRIPTS_DIR
_REAL_PERFORMANCE_SIMPLE = _REAL_SCRIPTS_DIR / "analyze_performance_simple.py"

_ALL_ANALYSIS_KEYS = ("code_quality", "duplicates", "performance", "architecture")

# Matches the ``report_path = Path("...")`` assignment each real sub-script
# uses right before its ``json.dump`` call.
_REPORT_PATH_RE = re.compile(r'report_path\s*=\s*Path\("([^"]+\.json)"\)')


def _write_script(scripts_dir: pathlib.Path, name: str, body: str) -> None:
    (scripts_dir / name).write_text(body, encoding="utf-8")


def _write_report_writing_script(scripts_dir: pathlib.Path, name: str, output_name: str, payload: dict) -> None:
    """A fake sub-script that writes ``payload`` to ``output_name`` in its cwd.

    Used for the failure-mode and contract tests below, which exercise
    orchestrator behaviour (missing file, malformed file, cwd pinning) that
    does not depend on any particular analyzer's real logic.
    """
    body = f"import json\njson.dump({payload!r}, open({output_name!r}, 'w', encoding='utf-8'))\n"
    _write_script(scripts_dir, name, body)


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


def test_missing_report_file_reports_error_not_success(scripts_dir, target_dir):
    """A script that exits 0 without writing its report file is not success.

    #14587: this is the file-channel analogue of the old "malformed stdout"
    case -- a returncode-0 run whose payload never showed up on the channel
    the orchestrator actually reads must not be folded into success.
    """
    _write_script(scripts_dir, "analyze_code_quality.py", "print('ran, but wrote nothing')\n")

    result = rca.run_code_quality_analysis(str(target_dir))

    assert "error" in result
    assert "did not write" in result["error"]
    assert "complexity" not in result


def test_malformed_report_file_reports_error_not_fabricated_defaults(scripts_dir, target_dir):
    """A report file that exists but is not valid JSON must not synthesize metrics.

    This used to return ``{"complexity": 5, "test_coverage": 70, ...}`` on a
    ``JSONDecodeError`` reading stdout -- numbers invented by the
    orchestrator, not measured. Same guarantee, now against the file channel.
    """
    _write_script(
        scripts_dir,
        "analyze_code_quality.py",
        "open('comprehensive_quality_report.json', 'w', encoding='utf-8').write('not json')\n",
    )

    result = rca.run_code_quality_analysis(str(target_dir))

    assert "error" in result
    assert "complexity" not in result
    assert "test_coverage" not in result


def test_missing_script_error_has_no_filesystem_path(scripts_dir, target_dir):
    """#14587: a result that could reach a caller must not carry an absolute
    filesystem path -- the script's own name identifies it just as well.
    """
    result = rca.run_code_quality_analysis(str(target_dir))

    assert result["error"] == "Script not found: analyze_code_quality.py"
    assert str(scripts_dir) not in result["error"]


def test_report_directory_instead_of_file_reports_error_not_crash(scripts_dir, target_dir):
    """A report path that exists but is a directory (e.g. a permissions
    problem or a race with another writer) must degrade to an error, not
    propagate an ``OSError`` out of the orchestrator.
    """
    _write_script(scripts_dir, "analyze_code_quality.py", "import os\nos.mkdir('comprehensive_quality_report.json')\n")

    result = rca.run_code_quality_analysis(str(target_dir))

    assert "error" in result
    assert "could not be read" in result["error"]


def test_report_file_with_non_dict_top_level_reports_error(scripts_dir, target_dir):
    """A report file whose JSON top level is an array must not flow through
    as a result -- downstream code calls ``.get("error")`` on it.
    """
    _write_script(
        scripts_dir,
        "analyze_code_quality.py",
        "import json\njson.dump([1, 2, 3], open('comprehensive_quality_report.json', 'w', encoding='utf-8'))\n",
    )

    result = rca.run_code_quality_analysis(str(target_dir))

    assert isinstance(result, dict)
    assert "error" in result


def test_valid_report_file_is_returned_verbatim(scripts_dir, target_dir):
    """#14587: the orchestrator reads the file the analyzer writes, not stdout."""
    payload = {"status": "success", "complexity": 3, "maintainability": "excellent"}
    _write_report_writing_script(
        scripts_dir, "analyze_code_quality.py", "comprehensive_quality_report.json", payload
    )

    result = rca.run_code_quality_analysis(str(target_dir))

    assert result == payload
    assert "error" not in result


def test_stdout_json_is_ignored_in_favour_of_the_file(scripts_dir, target_dir):
    """A script that prints JSON to stdout but writes a *different* payload to
    its file must be read from the file -- proves the channel switch, not
    just that a file-writing fixture happens to also work.
    """
    stdout_payload = {"complexity": 999}
    file_payload = {"complexity": 1, "source": "file"}
    body = (
        "import json\n"
        f"print(json.dumps({stdout_payload!r}))\n"
        f"json.dump({file_payload!r}, open('comprehensive_quality_report.json', 'w', encoding='utf-8'))\n"
    )
    _write_script(scripts_dir, "analyze_code_quality.py", body)

    result = rca.run_code_quality_analysis(str(target_dir))

    assert result == file_payload


def test_subprocess_cwd_is_pinned_to_target_path(scripts_dir, target_dir):
    """The sub-scripts resolve their own analysis root from cwd, not argv."""
    body = "import json, os\njson.dump({'cwd': os.getcwd()}, open('architectural_analysis_report.json', 'w'))\n"
    _write_script(scripts_dir, "analyze_architecture.py", body)

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
    _write_report_writing_script(
        scripts_dir, "analyze_code_quality.py", "comprehensive_quality_report.json", {"complexity": 1}
    )
    argv = ["run_code_analysis.py", "--target", str(target_dir), "--analysis-type", "quality"]
    monkeypatch.setattr(sys, "argv", argv)

    rca.main()

    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == "success"


def test_output_file_map_matches_what_each_real_script_writes():
    """Derive the channel contract from BOTH sides.

    #14587: the failure this whole test file exists to catch is the
    orchestrator and the analyzers *each* being internally self-consistent
    while disagreeing with each other. Read the report filename directly out
    of each real sub-script's own ``report_path = Path(...)`` line, and
    assert it equals what ``_ANALYSIS_OUTPUT_FILES`` says the orchestrator
    will read back for that same script -- rather than restating either side
    by hand.
    """
    for script_name, expected_output in rca._ANALYSIS_OUTPUT_FILES.items():
        script_path = _REAL_SCRIPTS_DIR / script_name
        assert script_path.exists(), f"real sub-script missing at {script_path}"
        source = script_path.read_text(encoding="utf-8")
        match = _REPORT_PATH_RE.search(source)
        assert match is not None, f"{script_name} has no report_path = Path(...) assignment"
        assert match.group(1) == expected_output, (
            f"{script_name} writes {match.group(1)!r} but the orchestrator reads "
            f"{expected_output!r} back for it"
        )


@pytest.mark.skipif(
    not _REAL_PERFORMANCE_SIMPLE.exists(),
    reason="real analyze_performance_simple.py not present in this checkout",
)
def test_real_performance_simple_script_reaches_success(tmp_path, monkeypatch):
    """#14587: drive the orchestrator against the REAL, unmodified
    ``analyze_performance_simple.py`` -- not a fixture that prints a shape no
    real producer emits. This is the exact defect #14583's tests repeated.
    """
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    shutil.copy(_REAL_PERFORMANCE_SIMPLE, scripts_dir / "analyze_performance_simple.py")
    monkeypatch.setattr(rca, "_ANALYSIS_SCRIPTS_DIR", scripts_dir)

    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "sample.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    result = rca.run_performance_analysis(str(target_dir))

    assert "error" not in result, result
    assert result["files_analyzed"] == 1
    assert "total_issues" in result

    report_file = target_dir / "performance_simple_analysis_report.json"
    assert report_file.exists()
    assert json.loads(report_file.read_text(encoding="utf-8")) == result
