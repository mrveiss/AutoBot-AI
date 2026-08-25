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

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "marker-tests.yml"
SCRIPT = Path(__file__).with_name("marker_suite_report.py")


_MODULE_NAME = "marker_suite_report"


def _load_script():
    """Load the checker, leaving no ``sys.modules`` entry behind.

    Same intent as this directory's other guard tests — the repo-wide sys.modules
    leak guard (#13337) fails a shard that strands a synthetic entry, and a
    sibling import via ``sys.path`` would strand one.

    The entry is installed for the duration of ``exec_module`` and removed in a
    ``finally``. Executing with NO entry at all is what the first version did,
    and it broke collection on Python 3.14: ``@dataclass`` resolves string
    annotations through ``sys.modules[cls.__module__]``, which was ``None``.
    The module no longer uses ``from __future__ import annotations`` so it does
    not depend on this, but a future edit that re-adds it must not silently
    resurrect a collection error.
    """
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, SCRIPT)
    assert spec is not None and spec.loader is not None, f"cannot build an import spec for {SCRIPT}"
    module = importlib.util.module_from_spec(spec)

    had_previous = _MODULE_NAME in sys.modules
    previous = sys.modules.get(_MODULE_NAME)
    sys.modules[_MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if had_previous:
            sys.modules[_MODULE_NAME] = previous
        else:
            sys.modules.pop(_MODULE_NAME, None)
    return module


_report = _load_script()
Counts = _report.Counts
ReportError = _report.ReportError
check = _report.check
main = _report.main
parse_report = _report.parse_report
parse_floor = _report.parse_floor


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
            "<testsuites>"
            '<testsuite name="a" tests="4" failures="1" errors="0" skipped="1"/>'
            '<testsuite name="b" tests="6" failures="0" errors="2" skipped="0"/>'
            "</testsuites>",
            encoding="utf-8",
        )
        counts = parse_report(multi)

        assert counts.collected == 10
        assert counts.failures == 1
        assert counts.errors == 2
        assert counts.skipped == 1


class TestFloors:
    """Floors are judged per invocation. The union form is the bug this class pins."""

    def _floors(self, *values):
        return parse_floor(list(values) or ["1"], "--min-collected")

    def test_zero_collected_is_a_violation(self):
        problems = check({"backend": Counts(collected=0)}, self._floors("1"), self._floors("1"))
        assert problems, "collecting nothing must never read as a clean run"
        assert "selecting nothing" in problems[0]

    def test_a_healthy_run_reports_no_violation(self):
        problems = check({"backend": Counts(collected=85, skipped=49)}, self._floors("1"), self._floors("1"))
        assert problems == []

    def test_a_run_that_only_skips_violates_the_passed_floor(self):
        """All-skipped is the failure mode a naive 'no failures' check would miss."""
        problems = check({"backend": Counts(collected=85, skipped=85)}, self._floors("1"), self._floors("1"))

        assert problems
        assert "passed" in problems[0]

    def test_a_collapsed_invocation_is_not_covered_by_its_sibling(self):
        """The trap: a union floor is satisfied by whichever invocation still works.

        `backend` collecting nothing while `slm` collects four is precisely the
        shape that left an earlier sweep here blind to ~44% of its population.
        Judged per invocation, `backend` must be named in the failure.
        """
        problems = check(
            {"backend": Counts(collected=0), "slm": Counts(collected=4, skipped=3)},
            self._floors("1"),
            self._floors("1"),
        )

        assert [p for p in problems if p.startswith("backend:")], problems

    def test_an_invocation_that_legitimately_collects_nothing_must_declare_it(self):
        """A floor of 0 is reachable only by naming the invocation, never by default."""
        floors = self._floors("1", "slm=0")

        assert floors.for_report("slm") == 0
        assert floors.is_explicit("slm")
        assert floors.for_report("backend") == 1
        assert (
            check(
                {"backend": Counts(collected=4, skipped=3), "slm": Counts(collected=0)},
                floors,
                self._floors("1", "slm=0"),
            )
            == []
        )

    def test_each_invocation_is_judged_against_its_own_override(self):
        floors = self._floors("1", "backend=83")
        problems = check({"backend": Counts(collected=40)}, floors, self._floors("1"))

        assert problems and "below its floor of 83" in problems[0]

    def test_a_bare_default_below_one_is_rejected(self):
        with pytest.raises(ReportError):
            parse_floor(["0"], "--min-collected")

    def test_a_floor_with_no_bare_default_is_rejected(self):
        """An override-only spec leaves every unnamed invocation unchecked."""
        with pytest.raises(ReportError):
            parse_floor(["slm=0"], "--min-collected")


class TestMain:
    def test_exit_zero_on_a_healthy_pair(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        a = write_report(tmp_path / "a.xml", tests=85, skipped=49)
        b = write_report(tmp_path / "b.xml", tests=0)

        assert (
            main(
                [
                    f"backend={a}",
                    f"slm={b}",
                    "--min-collected",
                    "1",
                    "--min-collected",
                    "slm=0",
                    "--min-passed",
                    "1",
                    "--min-passed",
                    "slm=0",
                ]
            )
            == 0
        )

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

    def test_exit_one_when_one_invocation_collapses_and_the_other_does_not(self, tmp_path, monkeypatch):
        """End to end, through argv: the sibling's count must not rescue the run."""
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        collapsed = write_report(tmp_path / "collapsed.xml", tests=0)
        healthy = write_report(tmp_path / "healthy.xml", tests=40, skipped=5)

        assert main([f"backend={collapsed}", f"slm={healthy}"]) == 1

    def test_exit_one_when_a_floor_names_an_invocation_that_does_not_exist(self, tmp_path, monkeypatch):
        """A floor pointing at nothing checks nothing — a renamed report must not disarm it."""
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        a = write_report(tmp_path / "a.xml", tests=40, skipped=5)

        assert main([f"backend={a}", "--min-collected", "1", "--min-collected", "typo=7"]) == 1

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

    def test_every_script_path_the_workflow_references_exists(self, run_steps):
        """Catches the rename half of the pair, from either end.

        Deliberately NOT keyed on the name ``marker_suite_report.py``. A first
        draft of this test was, and it passed vacuously when the workflow was
        mutated to call ``moved_elsewhere.py`` — no token matched, so the loop
        body never ran and the check reported success. A guard whose subject can
        disappear must assert on what IS there, not iterate over what might be.
        """
        referenced = {
            token for step in run_steps for token in step["run"].split() if token.endswith(".py") and "/" in token
        }
        assert referenced, "no run step references a script path; the coverage report is not wired to anything"

        missing = sorted(token for token in referenced if not (REPO_ROOT / token).exists())
        assert not missing, f"marker-tests.yml references script(s) that do not exist: {missing}"

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

    @pytest.mark.parametrize("marker", ["integration", "slow", "distributed", "performance"])
    def test_the_marker_expression_is_not_narrowed(self, marker_job, marker):
        """Nobody may quietly shrink the selection to make the run green.

        Narrowing the selection is the one "fix" #14930 explicitly rules out: a
        suite that passes because it stopped selecting the failing tests is the
        inert-suite defect wearing a green tick.
        """
        assert (
            marker in marker_job["env"]["MARKER_EXPRESSION"]
        ), f"the {marker!r} marker is no longer selected by the scheduled run"

    @pytest.mark.parametrize("marker", ["integration", "slow", "distributed", "performance"])
    def test_the_dispatch_default_is_not_narrowed(self, marker):
        """The manual-dispatch default is a second way to shrink the selection.

        ``MARKER_EXPRESSION`` is ``inputs.markers || <default>``, so both strings
        decide what runs and guarding only the first leaves the other open. A
        mutation of the dispatch default alone slipped past an earlier version
        of this class, which is why it is pinned separately.
        """
        parsed = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        # `on:` parses as the boolean True under YAML 1.1, not the string "on".
        triggers = parsed.get("on", parsed.get(True))
        default = triggers["workflow_dispatch"]["inputs"]["markers"]["default"]

        assert marker in default, f"the workflow_dispatch default no longer offers the {marker!r} marker"
