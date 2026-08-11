# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Run every Prometheus rule file and rule test through promtool (#13765).

The reason this exists: `alerts-cgroup-memory.yml` shipped a recording rule whose
`and` operands were the wrong way round, so `ServiceMemoryHeadroomLow` compared a
byte count against `0.15` and could never fire for any unit. Every Python test
passed, because they asserted substrings of the expr strings — which say nothing
about what the PromQL evaluates to.

A promtool suite was written to catch it, and then `grep -rn promtool` over the
repo found no workflow, hook, or test that ran it. The one artifact that catches
this class of defect only ran when somebody typed it by hand, which is the same
gap in a different coat: an unexecuted test is not a test.

Two things are checked here, and the second is the one that matters:

* `promtool check rules` — every `alerts-*.yml` is a VALID rule file. Prometheus
  refuses to load its entire config if any rule file is malformed, so one bad
  file takes down all alerting. A promtool *test* file is not a valid rule file,
  which is why they are named `*.promtool-test.yml` and excluded from that glob.
* `promtool test rules` — the alerts actually fire, and actually stay quiet.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# Lives in repo_tests/ rather than autobot-monitoring/ because only testpaths
# directories are collected — a guard against unexecuted tests must not itself
# be unexecuted (pytest.ini testpaths does not include autobot-monitoring).
_MONITORING = Path(__file__).resolve().parents[1] / "autobot-monitoring"

# The glob the ansible monitoring role copies into Prometheus's rules/ directory
# (roles/monitoring/tasks/prometheus.yml). Anything matching it must parse as a
# rule file or Prometheus will not start.
_DEPLOYED_RULE_GLOB = "alerts-*.yml"
_TEST_SUITE_GLOB = "*.promtool-test.yml"

# PATH first, then the location install-prometheus-stack.sh uses, overridable so
# no machine-specific absolute path is baked into a repo test.
_PROMTOOL = shutil.which("promtool") or os.environ.get("AUTOBOT_PROMTOOL", "/opt/prometheus/promtool")
_HAVE_PROMTOOL = Path(_PROMTOOL).is_file()

# #13927: CI now installs promtool (ci.yml, python-shard), so a skip THERE means
# the install step regressed — not that the environment is simply bare. A skip
# and a pass are indistinguishable in a green check, which is how this file came
# to protect nothing on CI for as long as it did. On a developer machine without
# the Prometheus stack, skipping is still the right behaviour.
_ON_CI = bool(os.environ.get("CI"))


def _require_promtool() -> None:
    """Skip locally, FAIL on CI (#13927)."""
    if _HAVE_PROMTOOL:
        return
    message = (
        f"promtool not found at {_PROMTOOL} — Prometheus rule BEHAVIOUR is unverified. "
        "Install via autobot-infrastructure/shared/scripts/install-prometheus-stack.sh"
    )
    if _ON_CI:
        pytest.fail(
            f"{message}. On CI this is a regression in the install step, not a bare "
            "environment: a silent skip here is what let a rule that could never "
            "fire ship green (#13909)."
        )
    pytest.skip(message)


@pytest.fixture(autouse=False)
def promtool_required():
    _require_promtool()


needs_promtool = pytest.mark.usefixtures("promtool_required")


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # nosec B603  # fixed binary, repo-local paths
        [_PROMTOOL, *args],
        cwd=_MONITORING,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _deployed_rule_files() -> list[Path]:
    return sorted(_MONITORING.glob(_DEPLOYED_RULE_GLOB))


def _test_suites() -> list[Path]:
    return sorted(_MONITORING.glob(_TEST_SUITE_GLOB))


def test_there_are_rule_files_to_check():
    """Guard the guard: a glob that stops matching would pass everything."""
    assert _deployed_rule_files(), f"no {_DEPLOYED_RULE_GLOB} found in {_MONITORING.name}"


def test_no_promtool_test_file_is_inside_the_deployment_glob():
    """A promtool test file is NOT a valid rule file.

    Named `alerts-*.yml` it gets copied into Prometheus's rules directory, and
    Prometheus then refuses to load its whole config — taking down every alert,
    including the ones the test file was written to verify. Caught in review
    before it shipped; this keeps it caught.
    """
    # Detected by CONTENT, not by filename. Matching only ".test.yml" missed the
    # very convention this PR introduces: `alerts-chat-ssot.promtool-test.yml`
    # keeps the alerts- prefix of its sibling rule file, ends in "-test.yml", and
    # would have sailed through into Prometheus's rules directory.
    yaml = pytest.importorskip("yaml")
    misnamed = []
    for path in _deployed_rule_files():
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            # Not `continue`: unparseable YAML in this glob stops Prometheus
            # loading its whole config, and the only other check that would
            # catch it (promtool) skips wherever promtool is absent (#13927).
            pytest.fail(f"{path.name} is in the deployed rule glob and is not valid YAML: {exc}")
        if isinstance(doc, dict) and ("tests" in doc or "rule_files" in doc):
            misnamed.append(path.name)

    assert not misnamed, (
        f"{misnamed} matches the deployed rule glob ({_DEPLOYED_RULE_GLOB}) but is a "
        "promtool TEST file, not a rule file. Prometheus refuses to load its entire "
        "config — every alert goes away. Rename to *.promtool-test.yml"
    )


@needs_promtool
@pytest.mark.parametrize("rule_file", _deployed_rule_files(), ids=lambda p: p.name)
def test_deployed_rule_file_is_valid(rule_file: Path):
    result = _run("check", "rules", rule_file.name)
    assert result.returncode == 0, f"{rule_file.name} is not a valid rule file:\n{result.stdout}{result.stderr}"


@needs_promtool
@pytest.mark.parametrize("suite", _test_suites(), ids=lambda p: p.name)
def test_rule_behaviour(suite: Path):
    """The assertion that substring checks cannot make: the alerts fire."""
    result = _run("test", "rules", suite.name)
    assert result.returncode == 0, f"{suite.name} failed:\n{result.stdout}{result.stderr}"


def test_the_promtool_suite_is_not_empty():
    """A rules file with no behavioural test is how the dead alert shipped."""
    assert _test_suites(), "no *.promtool-test.yml suites found — rule behaviour is unverified"


# Rule files that predate the promtool convention and have no behavioural suite
# yet. Listed rather than skipped silently, so the gap is visible and shrinking
# is a matter of deleting lines. Spun out as its own issue — writing suites for
# them is not #13765's scope, but pretending they are covered would be the same
# mistake this file exists to stop.
_RULE_FILES_WITHOUT_A_SUITE: frozenset[str] = frozenset(
    {
        "alerts-chat-ssot.yml",
        "alerts-tts-throughput.yml",
    }
)


def _suite_param(path: Path):
    """Mark the known-uncovered rule files with a STRICT declarative xfail.

    Not `pytest.xfail()` inside the body: that is imperative — it raises before
    the assertion runs, so XPASS is unreachable and the entry can never be
    reported as obsolete. Someone adding chat-ssot.promtool-test.yml and
    forgetting to delete the frozenset line would see the gap reported as
    still-open forever. A guard that cannot report success is the exact defect
    this file exists to catch, so it must not be one.

    strict=True makes the XPASS a FAILURE that names the line to delete.
    """
    marks = (
        [pytest.mark.xfail(strict=True, reason="predates the promtool convention — see #13927")]
        if path.name in _RULE_FILES_WITHOUT_A_SUITE
        else []
    )
    return pytest.param(path, marks=marks, id=path.name)


@pytest.mark.parametrize("rule_file", [_suite_param(p) for p in _deployed_rule_files()])
def test_rule_file_has_a_behavioural_suite(rule_file: Path):
    """Validity is not behaviour. `promtool check rules` passes happily on an
    alert that can never fire — that is exactly what shipped here."""
    expected = rule_file.name.removeprefix("alerts-").removesuffix(".yml")
    suites = {p.name for p in _test_suites()}
    assert (
        f"{expected}.promtool-test.yml" in suites
    ), f"{rule_file.name} has no behavioural test; add {expected}.promtool-test.yml"


# The two tests below re-invoke pytest on THIS file to observe its own
# skip/fail behaviour from outside. Without this sentinel the child run collects
# them too and spawns another child, forever.
_NESTED = "AUTOBOT_PROMTOOL_SELFTEST_CHILD"


@pytest.mark.skipif(bool(os.environ.get(_NESTED)), reason="child of the promtool self-test")
class TestAMissingPromtoolIsLoudOnCI:
    """#13927: the skip and the pass were indistinguishable in a green check.

    Five of this file's seven checks skipped on every GitHub-hosted runner
    because nothing installed promtool, so Prometheus rule BEHAVIOUR was
    verified by nothing — while the check reported green. #13909 shipped a
    recording rule whose `and` operands were reversed, so the alert compared a
    byte count against 0.15 and could never fire; every Python test passed,
    because they asserted substrings of expr strings.

    Installing the binary is half the fix. This is the other half: if a future
    runner loses it, that must be a failure, not a return to silence.
    """

    def _run_in(self, env: dict) -> subprocess.CompletedProcess:
        merged = {**os.environ, **env, _NESTED: "1"}
        merged.pop("PATH", None)
        merged["PATH"] = "/nonexistent-bin"
        return subprocess.run(  # nosec B603  # fixed interpreter, repo-local target
            [sys.executable, "-m", "pytest", str(Path(__file__)), "-q", "-p", "no:cacheprovider"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[1]),
            env=merged,
            timeout=300,
        )

    def test_ci_without_promtool_fails_rather_than_skips(self):
        result = self._run_in({"CI": "true", "AUTOBOT_PROMTOOL": "/nonexistent/promtool"})

        assert result.returncode != 0, (
            "a CI run with no promtool reported success — rule behaviour was unverified "
            "and nothing said so, which is the exact condition #13927 exists to end"
        )
        assert "promtool not found" in (result.stdout + result.stderr)

    def test_a_developer_machine_without_promtool_still_skips(self):
        """The direction that must stay true. Turning every bare checkout red
        would make the failure meaningless — and a guard that only proves the
        CI case passes equally against a check that always fails."""
        env = {"AUTOBOT_PROMTOOL": "/nonexistent/promtool"}
        result = self._run_in({**env, "CI": ""})

        assert result.returncode == 0, "a local run without promtool must skip, not fail"
        assert "skipped" in (result.stdout + result.stderr)
