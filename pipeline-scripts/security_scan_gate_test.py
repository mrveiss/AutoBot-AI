#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The security gate must fail on a planted finding, and be wired to the workflow (#13543).

Reading `security.yml` proves nothing about whether a job can go red — the
scanners it runs ended in `|| true` for years while the checks tab stayed green.
So this suite plants findings and asserts a non-zero exit:

* `TestPlantedFindingEndToEnd` runs the REAL bandit over a file with a real
  vulnerability and feeds bandit's own JSON to the gate. Nothing here is
  hand-written except the vulnerable line.
* the rest drive the parsers and thresholds directly, including the cases a
  scanner produces when it dies — an absent or empty report must fail, never
  read as "no findings".
* `TestWorkflowWiring` pins both ends of the wire: a gate the workflow stopped
  calling guards nothing, and a `|| true` re-added to a gating step disarms it
  silently.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess  # nosec B404
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "security.yml"
SCRIPT = Path(__file__).with_name("security_scan_gate.py")

_MODULE_NAME = "security_scan_gate"


def _load_script():
    """Load the gate leaving no ``sys.modules`` entry behind (#13337)."""
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_gate = _load_script()
Finding = _gate.Finding
ReportError = _gate.ReportError
at_or_above = _gate.at_or_above
counts_by_severity = _gate.counts_by_severity
main = _gate.main
read_report = _gate.read_report
render = _gate.render


# A hardcoded password and a subprocess shell call: two findings bandit reports
# at MEDIUM/HIGH with its default rule set. Assembled at runtime so the literal
# never sits in the tree as a scannable string of its own.
_VULNERABLE_SOURCE = "\n".join(
    [
        "import subprocess",
        "",
        "PASSWORD = " + repr("hunter2-not-a-real-secret"),
        "",
        "def run(user_input):",
        "    return subprocess.check_output(user_input, shell=True)",
        "",
    ]
)


class TestPlantedFindingEndToEnd:
    """The claim under test is 'a finding turns this check red', so plant one."""

    @pytest.fixture
    def bandit_report(self, tmp_path):
        pytest.importorskip("bandit", reason="bandit is installed by requirements-ci-test.txt")
        target = tmp_path / "planted_vulnerability.py"
        target.write_text(_VULNERABLE_SOURCE, encoding="utf-8")
        report = tmp_path / "bandit-report.json"
        subprocess.run(  # nosec B603
            [sys.executable, "-m", "bandit", "-f", "json", "-o", str(report), str(target)],
            capture_output=True,
            check=False,
        )
        return report

    def test_bandit_actually_found_the_planted_vulnerability(self, bandit_report):
        """Without this the next test could pass because bandit found nothing at all."""
        findings = read_report(bandit_report, "bandit")

        assert findings, "bandit reported no finding on a file with a hardcoded password and shell=True"
        assert {f.severity for f in findings} <= set(_gate.SEVERITIES)

    def test_the_gate_fails_on_the_planted_finding(self, bandit_report, monkeypatch):
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

        exit_code = main(
            [
                "--format",
                "bandit",
                "--report",
                str(bandit_report),
                "--title",
                "planted",
                "--fail-on",
                "any",
            ]
        )

        assert exit_code == 1, "a real bandit finding must turn the step red"

    def test_a_clean_file_passes_the_same_gate(self, tmp_path, monkeypatch):
        """The other half: the gate must not be red regardless of input."""
        pytest.importorskip("bandit", reason="bandit is installed by requirements-ci-test.txt")
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        clean = tmp_path / "clean.py"
        clean.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        report = tmp_path / "clean-report.json"
        subprocess.run(  # nosec B603
            [sys.executable, "-m", "bandit", "-f", "json", "-o", str(report), str(clean)],
            capture_output=True,
            check=False,
        )

        assert main(["--format", "bandit", "--report", str(report), "--title", "clean", "--fail-on", "any"]) == 0


class TestReportsThatMustNotReadAsClean:
    def test_an_absent_report_is_a_hard_failure(self, tmp_path):
        with pytest.raises(ReportError, match="does not exist"):
            read_report(tmp_path / "never-written.json", "bandit")

    def test_an_empty_report_is_a_hard_failure(self, tmp_path):
        empty = tmp_path / "empty.json"
        empty.write_text("", encoding="utf-8")

        with pytest.raises(ReportError, match="empty"):
            read_report(empty, "bandit")

    def test_an_unparseable_report_is_a_hard_failure(self, tmp_path):
        broken = tmp_path / "broken.json"
        broken.write_text("{not json", encoding="utf-8")

        with pytest.raises(ReportError, match="not readable"):
            read_report(broken, "bandit")

    def test_main_exits_non_zero_when_the_scanner_wrote_nothing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

        assert main(
            ["--format", "pip-audit", "--report", str(tmp_path / "gone.json"), "--title", "x", "--fail-on", "any"]
        ) == 1


def _write(path: Path, payload) -> Path:
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
    return path


class TestParsers:
    def test_pip_audit_reports_one_finding_per_vulnerability(self, tmp_path):
        report = _write(
            tmp_path / "pip.json",
            {
                "dependencies": [
                    {"name": "somelib", "version": "1.0", "vulns": [{"id": "GHSA-x"}, {"id": "GHSA-y"}]},
                    {"name": "clean", "version": "2.0", "vulns": []},
                ]
            },
        )
        findings = read_report(report, "pip-audit")

        assert [f.identifier for f in findings] == ["GHSA-x", "GHSA-y"]
        assert all(f.severity == "unknown" for f in findings)

    def test_npm_audit_keeps_each_advisory_severity(self, tmp_path):
        report = _write(
            tmp_path / "npm.json",
            {"vulnerabilities": {"a": {"severity": "critical", "range": "<1"}, "b": {"severity": "low"}}},
        )
        counts = counts_by_severity(read_report(report, "npm-audit"))

        assert counts["critical"] == 1
        assert counts["low"] == 1

    def test_flake8_text_output_is_counted_by_code(self, tmp_path):
        report = _write(
            tmp_path / "flake8.txt",
            "a/b.py:1:80: E501 line too long\na/b.py:4:1: E402 module import not at top\nnot a finding\n",
        )
        findings = read_report(report, "flake8")

        assert [f.identifier for f in findings] == ["E501", "E402"]

    def test_an_empty_flake8_report_is_a_legitimate_zero(self, tmp_path):
        """flake8 writes an empty file when it finds nothing — unlike the JSON tools."""
        assert read_report(_write(tmp_path / "flake8.txt", ""), "flake8") == []


class TestThresholds:
    @pytest.fixture
    def findings(self):
        return [
            Finding("critical", "C", "x"),
            Finding("high", "H", "x"),
            Finding("medium", "M", "x"),
            Finding("low", "L", "x"),
            Finding("unknown", "U", "x"),
        ]

    def test_high_selects_critical_and_high_only(self, findings):
        assert [f.identifier for f in at_or_above(findings, "high")] == ["C", "H"]

    def test_any_selects_everything_including_unknown(self, findings):
        assert len(at_or_above(findings, "any")) == len(findings)

    def test_never_selects_nothing(self, findings):
        assert at_or_above(findings, "never") == []

    def test_an_allowance_absorbs_exactly_that_many(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        report = _write(
            tmp_path / "pip.json",
            {"dependencies": [{"name": "x", "version": "1", "vulns": [{"id": "A"}, {"id": "B"}]}]},
        )
        argv = ["--format", "pip-audit", "--report", str(report), "--title", "t", "--fail-on", "any"]

        assert main([*argv, "--allowed", "2"]) == 0
        assert main([*argv, "--allowed", "1"]) == 1

    def test_a_non_gating_step_says_so_in_the_summary(self):
        """A report-only step must never read as a verdict."""
        text = render("t", [Finding("high", "H", "x")], "never", 0)

        assert "does not gate" in text

    def test_the_summary_carries_the_counts_and_the_verdict(self):
        text = render("t", [Finding("high", "H", "pkg.py:1")], "high", 0)

        assert "| high | 1 |" in text
        assert "**FAIL**" in text
        assert "pkg.py:1" in text


class TestWorkflowWiring:
    """A gate the workflow does not call, or calls behind `|| true`, is not a gate."""

    @pytest.fixture(scope="class")
    def workflow(self):
        return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))

    @pytest.fixture(scope="class")
    def run_steps(self, workflow):
        return [
            (job_name, step)
            for job_name, job in workflow["jobs"].items()
            for step in job.get("steps", [])
            if "run" in step
        ]

    @pytest.fixture(scope="class")
    def gate_steps(self, run_steps):
        return [(job, step) for job, step in run_steps if SCRIPT.name in step["run"]]

    def test_the_workflow_invokes_the_gate(self, gate_steps):
        assert gate_steps, (
            f"security.yml no longer runs {SCRIPT.name} — every scanner is back to reporting "
            "into an artifact nobody reads, and the jobs can only fail on infrastructure"
        )

    @staticmethod
    def _gated_reports(gate_steps) -> set[str]:
        """Report paths named by a `--report PATH` argument of the gate."""
        gated = set()
        for _, step in gate_steps:
            tokens = step["run"].replace("\\\n", " ").split()
            gated |= {
                Path(value).name
                for flag, value in zip(tokens, tokens[1:])
                if flag == "--report"
            }
        return gated

    @staticmethod
    def _written_reports(run_steps) -> set[str]:
        """Report paths a scanner is told to write, by any of the three spellings."""
        written = set()
        for _, step in run_steps:
            tokens = step["run"].replace("\\\n", " ").split()
            for index, token in enumerate(tokens):
                candidate = None
                if token.startswith(("--output=", "--output-file=", "-o=")):
                    candidate = token.split("=", 1)[1]
                elif token in ("-o", ">") and index + 1 < len(tokens):
                    candidate = tokens[index + 1]
                if candidate and candidate.endswith((".json", ".txt")):
                    written.add(Path(candidate.strip("\"'")).name)
        return written

    def test_every_scanner_report_the_workflow_writes_is_gated(self, run_steps, gate_steps):
        """A report written and never judged is the original defect, one file over.

        Derived from the workflow at both ends rather than listed here: a
        scanner added later is checked on arrival, and a report that stops being
        gated fails instead of quietly becoming an artifact nobody opens.
        """
        written = self._written_reports(run_steps)
        assert written, "no scanner output path found in security.yml; this check is inspecting nothing"

        gated = self._gated_reports(gate_steps)
        # `safety-report.json` and `semgrep.sarif` are the two recorded exceptions:
        # safety is report-only by decision (see the header comment) and semgrep
        # gates through its own `--error` exit rather than through this gate.
        exceptions = {"safety-report.json", "semgrep.sarif", "semgrep-report.json"}
        ungated = sorted(name for name in written - exceptions if name not in gated)
        assert not ungated, f"scanner reports written but judged by nothing: {ungated}"

    def test_the_recorded_exceptions_are_still_named_honestly(self, workflow):
        """A report-only scanner must say so in its step name, or the name overclaims."""
        names = [
            step.get("name", "")
            for job in workflow["jobs"].values()
            for step in job.get("steps", [])
        ]
        for scanner in ("Safety Check", "Python Lint Report"):
            matching = [name for name in names if name.startswith(scanner)]
            assert matching, f"the {scanner!r} step has been renamed; re-check whether it gates"
            assert all("does not gate" in name for name in matching), (
                f"{matching} does not gate but its name does not say so — that is the overclaiming "
                "this issue is about (#13543)"
            )

    def test_no_gate_invocation_is_neutralised_by_a_shell_or(self, gate_steps):
        """`|| true` after the gate would restore the exact defect #13543 is about.

        Line continuations are joined first, so the whole gate command is judged
        as one unit — and only that command. A `|| true` on the SCANNER line in
        the same step is deliberate and must not be flagged: the scanner's exit
        code only says findings exist, which is what the gate is there to judge.
        """
        for job, step in gate_steps:
            for command in step["run"].replace("\\\n", " ").splitlines():
                if SCRIPT.name in command:
                    assert "||" not in command, f"{job}: gate invocation is neutralised: {command.strip()!r}"

    def test_the_gate_script_referenced_by_the_workflow_exists(self, gate_steps):
        referenced = {
            token
            for _, step in gate_steps
            for token in step["run"].split()
            if token.endswith(".py") and "/" in token
        }
        assert referenced, "no gate step names a script path"
        missing = sorted(token for token in referenced if not (REPO_ROOT / token).exists())
        assert not missing, f"security.yml references script(s) that do not exist: {missing}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
