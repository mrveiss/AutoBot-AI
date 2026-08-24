#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The marker-suite presence assertion must not be satisfiable by nothing (#14930).

Two halves, and both are needed:

* **The script.** Its whole reason to exist is that an empty or absent result
  must not read as a clean one, so most of these tests feed it exactly that and
  assert it fails.
* **The wiring.** A guard that is correct and unreferenced guards nothing. The
  last class asserts `.github/workflows/marker-tests.yml` actually invokes it,
  on the report paths pytest is actually told to write — so moving or renaming
  either end breaks a test instead of silently disarming the check.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))

from marker_suite_report import Counts, ReportError, check, main, parse_report  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "marker-tests.yml"
SCRIPT = Path(__file__).parent / "marker_suite_report.py"


def write_report(path: Path, tests: int, failures: int = 0, errors: int = 0, skipped: int = 0) -> Path:
    path.write_text(
        f'<?xml version="1.0" encoding="utf-8"?>\n'
        f'<testsuites><testsuite name="pytest" tests="{tests}" failures="{failures}" '
        f'errors="{errors}" skipped="{skipped}" time="1.0"></testsuite></testsuites>\n',
        encoding="utf-8",
    )
    return path


class TestParseReport:
    def test_reads_the_four_counts(self, tmp_path):
        report = write_report(tmp_path / "r.xml", tests=85, failures=19, errors=19, skipped=12)
        counts = parse_report(report)

        assert counts.collected == 85
        assert counts.failures == 19
        assert counts.errors == 19
        assert counts.skipped == 12
        assert counts.passed == 35
        assert counts.executed == 73

    def test_a_missing_report_raises_instead_of_counting_zero(self, tmp_path):
        """The trap this script exists for: an absent result must not read as clean.

        Returning ``Counts()`` here would make a pytest that died before writing
        its XML indistinguishable from a run that collected nothing, and both
        indistinguishable from a healthy run once the floors were relaxed.
        """
        with pytest.raises(ReportError, match="does not exist"):
            parse_report(tmp_path / "never-written.xml")

    def test_malformed_xml_raises(self, tmp_path):
        bad = tmp_path / "bad.xml"
        bad.write_text("<testsuites><testsuite tests=", encoding="utf-8")

        with pytest.raises(ReportError, match="not parseable"):
            parse_report(bad)

    def test_a_file_with_no_testsuite_raises(self, tmp_path):
        empty = tmp_path / "empty.xml"
        empty.write_text("<testsuites></testsuites>", encoding="utf-8")

        with pytest.raises(ReportError, match="no <testsuite>"):
            parse_report(empty)

    def test_a_missing_attribute_raises_rather_than_defaulting_to_zero(self, tmp_path):
        """A pytest that renames an attribute must break loudly, not count zero."""
        partial = tmp_path / "partial.xml"
        partial.write_text(
            '<testsuites><testsuite name="pytest" tests="10" failures="0" errors="0"/></testsuites>',
            encoding="utf-8",
        )

        with pytest.raises(ReportError, match="missing attribute"):
            parse_report(partial)

    def test_multiple_testsuites_are_summed(self, tmp_path):
        multi = tmp_path / "multi.xml"
        multi.write_text(
            '<testsuites>'
            '<testsuite name="a" tests="4" failures="1" errors="0" skipped="1"/>'
            '<testsuite name="b" tests="6" failures="0" errors="2" skipped="0"/>'
            '</testsuites>',
            encoding="utf-8",
        )
        counts = parse_report(multi)

        assert counts.collected == 10
        assert counts.failures == 1
        assert counts.errors == 2
        assert counts.skipped == 1


class TestFloors:
    def test_zero_collected_is_a_violation(self):
        problems = check({"backend": Counts(collected=0)}, min_collected=1, min_passed=1)
        assert problems, "collecting nothing must never read as a clean run"
        assert "selecting nothing" in problems[0]

    def test_a_healthy_run_reports_no_violation(self):
        problems = check({"backend": Counts(collected=85, skipped=49)}, min_collected=1, min_passed=1)
        assert problems == []

    def test_a_run_that_only_skips_violates_the_passed_floor(self):
        """All-skipped is the failure mode a naive 'no failures' check would miss."""
        problems = check({"backend": Counts(collected=85, skipped=85)}, min_collected=1, min_passed=1)

        assert problems
        assert "passed" in problems[0]

    def test_the_floors_are_summed_across_invocations(self):
        problems = check(
            {"backend": Counts(collected=0), "slm": Counts(collected=4, skipped=3)},
            min_collected=1,
            min_passed=1,
        )
        assert problems == [], "a legitimately empty second invocation must not fail the run on its own"


class TestMain:
    def test_exit_zero_on_a_healthy_pair(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        a = write_report(tmp_path / "a.xml", tests=85, skipped=49)
        b = write_report(tmp_path / "b.xml", tests=0)

        assert main([f"backend={a}", f"slm={b}", "--min-collected", "1", "--min-passed", "1"]) == 0

    def test_exit_one_when_nothing_was_collected(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        a = write_report(tmp_path / "a.xml", tests=0)
        b = write_report(tmp_path / "b.xml", tests=0)

        assert main([f"backend={a}", f"slm={b}"]) == 1

    def test_exit_one_when_a_report_is_absent(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        a = write_report(tmp_path / "a.xml", tests=85, skipped=49)

        assert main([f"backend={a}", f"slm={tmp_path / 'gone.xml'}"]) == 1

    def test_exit_one_when_the_passed_floor_is_missed(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        a = write_report(tmp_path / "a.xml", tests=85, skipped=60)

        assert main([f"backend={a}", "--min-passed", "35"]) == 1

    def test_a_zero_min_collected_is_rejected(self, tmp_path):
        """The presence assertion must not be disableable from the call site."""
        a = write_report(tmp_path / "a.xml", tests=1)

        with pytest.raises(SystemExit) as excinfo:
            main([f"backend={a}", "--min-collected", "0"])
        assert excinfo.value.code != 0

    def test_the_summary_is_written_to_the_github_step_summary(self, tmp_path, monkeypatch):
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        a = write_report(tmp_path / "a.xml", tests=85, failures=0, errors=0, skipped=49)

        assert main([f"backend={a}"]) == 0

        written = summary.read_text(encoding="utf-8")
        assert "Marker-excluded suite coverage" in written
        assert "85" in written and "36" in written

    def test_runs_as_a_script(self, tmp_path):
        """The workflow invokes it through the interpreter, so prove that path works."""
        a = write_report(tmp_path / "a.xml", tests=0)
        result = subprocess.run(  # nosec B603
            [sys.executable, str(SCRIPT), f"backend={a}"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1
        assert "selecting nothing" in result.stderr


class TestWorkflowWiring:
    """A guard nothing calls is not a guard. Pin both ends of the wire."""

    @pytest.fixture(scope="class")
    def marker_job(self):
        parsed = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        return parsed["jobs"]["marker-tests"]

    @pytest.fixture(scope="class")
    def run_steps(self, marker_job):
        return [step for step in marker_job["steps"] if "run" in step]

    def test_the_workflow_invokes_this_script(self, run_steps):
        invocations = [step for step in run_steps if "marker_suite_report.py" in step["run"]]
        assert invocations, (
            "marker-tests.yml no longer runs marker_suite_report.py — the presence "
            "assertion is disarmed and an empty collection would read as clean again"
        )

    def test_the_script_path_the_workflow_uses_exists(self, run_steps):
        """Catches the rename half of the pair: move the script, this fails."""
        for step in run_steps:
            for token in step["run"].split():
                if token.endswith("marker_suite_report.py"):
                    assert (REPO_ROOT / token).exists(), f"workflow references a script that does not exist: {token}"

    def test_every_junitxml_pytest_writes_is_checked_by_the_report_step(self, run_steps):
        """The report step must consume exactly the files pytest is told to produce.

        A junitxml path that nothing checks is an invocation whose emptiness
        nobody would notice — the original defect, one file over.
        """
        produced = set()
        consumed = set()
        for step in run_steps:
            for token in step["run"].replace("=", " ").split():
                if token.endswith(".xml"):
                    if "marker_suite_report.py" in step["run"]:
                        consumed.add(token)
                    else:
                        produced.add(token)

        assert produced, "no --junitxml path found in the pytest steps; nothing can be counted"
        assert produced <= consumed, f"junit reports written but never checked: {sorted(produced - consumed)}"

    def test_the_report_step_runs_even_when_a_pytest_step_failed(self, run_steps):
        """Otherwise a failing suite skips the count and the collapse stays hidden."""
        report_steps = [step for step in run_steps if "marker_suite_report.py" in step["run"]]
        for step in report_steps:
            condition = str(step.get("if", ""))
            assert "cancelled" in condition or "always" in condition, (
                "the marker-suite report step must run on failure too, or a red pytest "
                f"run hides the coverage count entirely; got if: {condition!r}"
            )

    def test_the_marker_expression_is_not_narrowed(self, marker_job):
        """Nobody may quietly shrink the selection to make the run green."""
        expression = marker_job["env"]["MARKER_EXPRESSION"]
        for marker in ("integration", "slow", "distributed", "performance"):
            assert marker in expression, f"the {marker!r} marker is no longer selected by this suite"
