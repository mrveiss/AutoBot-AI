# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16337 -- the npm audit gate tells "could not check" apart from "found".

Fixtures are npm audit's own output shapes: the v2 ``--json`` report, the
``{"error": ...}`` object npm prints with ``--json`` when the audit endpoint
fails (the 2026-09-11 message is used verbatim), and the ``--loglevel=http``
lines that name the endpoint.
"""

from __future__ import annotations

import json
import subprocess

import npm_audit_gate as gate
import pytest

BULK_LOG = "npm http fetch POST 200 https://registry.npmjs.org/-/npm/v1/security/advisories/bulk 412ms\n"
QUICK_LOG = (
    "npm http fetch POST 500 https://registry.npmjs.org/-/npm/v1/security/advisories/bulk 90ms\n"
    "npm http fetch POST 200 https://registry.npmjs.org/-/npm/v1/security/audits/quick 300ms\n"
)


def _report(**counts: int) -> str:
    vulnerabilities = {key: counts.get(key, 0) for key in ("info", "low", "moderate", "high", "critical")}
    vulnerabilities["total"] = sum(vulnerabilities.values())
    return json.dumps(
        {"auditReportVersion": 2, "vulnerabilities": {}, "metadata": {"vulnerabilities": vulnerabilities}}
    )


ENDPOINT_ERROR = json.dumps(
    {
        "error": {
            "code": "E400",
            "summary": "400 Bad Request - POST https://registry.npmjs.org/-/npm/v1/security/audits/quick"
            " - Invalid package tree, run  npm install  to rebuild your package-lock.json",
            "detail": "",
        }
    }
)


class _FakeNpm:
    """Replays one (stdout, stderr) pair per call, then repeats the last."""

    def __init__(self, *results: tuple[str, str]) -> None:
        self.results = list(results)
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        stdout, stderr = self.results[min(len(self.calls), len(self.results)) - 1]
        return subprocess.CompletedProcess(command, 1, stdout=stdout, stderr=stderr)


# --- the three results -----------------------------------------------------


def test_low_and_moderate_advisories_pass() -> None:
    verdict = gate.classify(_report(low=1, moderate=1), BULK_LOG)

    assert verdict.result == gate.PASSED
    assert verdict.counts["moderate"] == 1
    assert verdict.endpoint == "advisories/bulk"


@pytest.mark.parametrize("severity", ["high", "critical"])
def test_a_high_or_critical_advisory_is_found(severity: str) -> None:
    verdict = gate.classify(_report(**{severity: 1}), BULK_LOG)

    assert verdict.result == gate.FOUND
    assert verdict.counts[severity] == 1


def test_the_endpoint_error_is_unavailable_and_names_the_error() -> None:
    verdict = gate.classify(ENDPOINT_ERROR, "")

    assert verdict.result == gate.UNAVAILABLE
    assert verdict.reason.startswith("audit endpoint error: 400 Bad Request")
    assert verdict.counts == {}


def _with_counts(**overrides: object) -> str:
    counts: dict[str, object] = {"info": 0, "low": 0, "moderate": 0, "high": 0, "critical": 0}
    counts.update(overrides)
    return json.dumps({"metadata": {"vulnerabilities": {k: v for k, v in counts.items() if v != "absent"}}})


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        "npm error audit endpoint returned an error",
        "[]",
        json.dumps({"metadata": {}}),
        json.dumps({"metadata": {"vulnerabilities": {}}}),
        _with_counts(high="1"),
        _with_counts(critical=None),
        _with_counts(critical=True),
        _with_counts(high=-1),
        _with_counts(info="absent"),
    ],
    ids=[
        "empty",
        "not-json",
        "not-a-report",
        "no-counts",
        "empty-counts",
        "string-count",
        "null-count",
        "bool-count",
        "negative-count",
        "missing-severity",
    ],
)
def test_no_usable_report_is_unavailable_never_a_pass(stdout: str) -> None:
    assert gate.classify(stdout, BULK_LOG).result == gate.UNAVAILABLE


def test_a_report_that_came_through_audits_quick_is_unavailable() -> None:
    verdict = gate.classify(_report(), QUICK_LOG)

    assert verdict.result == gate.UNAVAILABLE
    assert verdict.endpoint == "audits/quick"
    assert "audits/quick" in verdict.reason


# --- retries ---------------------------------------------------------------


def test_an_endpoint_error_is_retried_until_a_report_arrives() -> None:
    npm, sleeps = _FakeNpm((ENDPOINT_ERROR, ""), (ENDPOINT_ERROR, ""), (_report(), BULK_LOG)), []

    outcome = gate.audit_with_retries(["npm"], 3, 7, run=npm, sleep=sleeps.append)

    assert outcome.verdict.result == gate.PASSED
    assert (outcome.attempts, len(npm.calls), sleeps) == (3, 3, [7, 7])


def test_a_persistent_endpoint_error_stops_at_the_attempt_limit() -> None:
    npm, sleeps = _FakeNpm((ENDPOINT_ERROR, "")), []

    outcome = gate.audit_with_retries(["npm"], 4, 1, run=npm, sleep=sleeps.append)

    assert outcome.verdict.result == gate.UNAVAILABLE
    assert (outcome.attempts, len(npm.calls), len(sleeps)) == (4, 4, 3)


def test_a_found_advisory_is_not_retried() -> None:
    npm = _FakeNpm((_report(high=2), BULK_LOG))

    outcome = gate.audit_with_retries(["npm"], 3, 1, run=npm, sleep=lambda _s: None)

    assert (outcome.verdict.result, len(npm.calls)) == (gate.FOUND, 1)


def test_a_timed_out_attempt_is_unavailable() -> None:
    def timing_out(command: list[str]) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, 1)

    outcome = gate.audit_with_retries(["npm"], 2, 0, run=timing_out, sleep=lambda _s: None)

    assert outcome.verdict.result == gate.UNAVAILABLE


def test_the_npm_command_and_the_audit_flags_reach_the_runner(monkeypatch) -> None:
    seen: list[tuple[list[str], dict]] = []

    def fake_run(argv, **kwargs):
        seen.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout=_report(), stderr=BULK_LOG)

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    gate._run_npm_audit(["npx", "--yes", "npm@11.19.1"])

    (argv, kwargs), *rest = seen
    assert rest == []
    assert argv == ["npx", "--yes", "npm@11.19.1", "audit", "--json", "--loglevel=http"]
    # An undecodable byte must reach classify() as text, not raise (#16357 review).
    assert (kwargs["text"], kwargs["errors"]) == (True, "replace")


# --- env-backed constants ----------------------------------------------------


def test_every_constant_comes_from_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("NPM_AUDIT_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("NPM_AUDIT_RETRY_DELAY_SECONDS", "0")
    monkeypatch.setenv("NPM_AUDIT_TIMEOUT_SECONDS", "30")

    assert (gate.max_attempts(), gate.retry_delay_seconds(), gate.timeout_seconds()) == (5, 0, 30)


@pytest.mark.parametrize(
    "name,getter,default,raw",
    [
        *(("NPM_AUDIT_MAX_ATTEMPTS", "max_attempts", gate.DEFAULT_MAX_ATTEMPTS, r) for r in ("", "0", "-2", "three")),
        *(
            ("NPM_AUDIT_RETRY_DELAY_SECONDS", "retry_delay_seconds", gate.DEFAULT_RETRY_DELAY_SECONDS, r)
            for r in ("", "-1", "1.5", "soon")
        ),
        *(
            ("NPM_AUDIT_TIMEOUT_SECONDS", "timeout_seconds", gate.DEFAULT_TIMEOUT_SECONDS, r)
            for r in ("", "0", "-5", "x")
        ),
    ],
)
def test_an_invalid_constant_falls_back_to_its_default(monkeypatch, name, getter, default, raw) -> None:
    monkeypatch.setenv(name, raw)

    assert getattr(gate, getter)() == default


# --- what the job reports ------------------------------------------------------


@pytest.mark.parametrize(
    "stdout,log,exit_code,headline,annotation",
    [
        (_report(low=1), BULK_LOG, 0, "**Passed:**", None),
        (_report(critical=1), BULK_LOG, 1, "**Failed, advisories found:** 1 critical", "npm audit: advisories found"),
        (ENDPOINT_ERROR, "", 2, "**Failed, could not check:**", "npm audit: could not check"),
    ],
    ids=["passed", "found", "unavailable"],
)
def test_main_states_which_result_happened(
    tmp_path, monkeypatch, capsys, stdout, log, exit_code, headline, annotation
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("NPM_AUDIT_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("NPM_AUDIT_RETRY_DELAY_SECONDS", "0")
    monkeypatch.setattr(gate, "_run_npm_audit", _FakeNpm((stdout, log)))
    report = tmp_path / "audit-results.json"

    assert gate.main(["--report", str(report)]) == exit_code

    text = summary.read_text(encoding="utf-8")
    assert headline in text
    assert report.read_text(encoding="utf-8") == stdout
    out = capsys.readouterr().out
    if annotation:
        assert f"::error title={annotation}::" in out
    else:
        assert "::error" not in out


def test_the_summary_says_could_not_check_distinctly_from_found() -> None:
    unavailable = gate.Outcome(gate.Verdict(gate.UNAVAILABLE, reason="audit endpoint error: E400"), 3, "")
    found = gate.Outcome(gate.classify(_report(high=1), BULK_LOG), 1, "")

    unavailable_text = "\n".join(gate.summary_lines(unavailable, 3))
    found_text = "\n".join(gate.summary_lines(found, 3))

    assert "could not check" in unavailable_text and "advisories found" not in unavailable_text
    assert "advisories found" in found_text and "could not check" not in found_text
    assert "attempts: 3 of 3" in unavailable_text


@pytest.mark.parametrize(
    "error",
    [UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"), RuntimeError("boom")],
    ids=["undecodable-output", "anything-else"],
)
def test_a_crash_inside_the_gate_is_could_not_check_never_found(tmp_path, monkeypatch, capsys, error) -> None:
    """An uncaught exception used to exit 1 -- the "advisories found" code -- with no summary."""
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    def crashing(command: list[str]) -> subprocess.CompletedProcess[str]:
        raise error

    monkeypatch.setattr(gate, "_run_npm_audit", crashing)

    assert gate.main(["--report", str(tmp_path / "audit-results.json")]) == gate.EXIT_CODES[gate.UNAVAILABLE]
    text = summary.read_text(encoding="utf-8")
    assert "**Failed, could not check:**" in text and type(error).__name__ in text
    assert "::error title=npm audit: could not check::" in capsys.readouterr().out
