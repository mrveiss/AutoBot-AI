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

# HONEST STATUS: no CI job installs promtool, so on a GitHub-hosted runner every
# check below skips and this file protects nothing there. That is the gap this
# file was written to close, one layer down — an unexecuted test is not a test.
# Installing it in the workflow is a repo-wide CI change with its own blast
# radius, tracked separately rather than bundled into a metrics PR. Locally, and
# on any host with the Prometheus stack, these run for real.
needs_promtool = pytest.mark.skipif(
    not _HAVE_PROMTOOL,
    reason=(
        "promtool not on PATH or at AUTOBOT_PROMTOOL — rule BEHAVIOUR is unverified here. "
        "Install via autobot-infrastructure/shared/scripts/install-prometheus-stack.sh"
    ),
)


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
