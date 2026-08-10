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

_PROMTOOL = shutil.which("promtool") or "/opt/prometheus/promtool"
_HAVE_PROMTOOL = Path(_PROMTOOL).is_file()

needs_promtool = pytest.mark.skipif(
    not _HAVE_PROMTOOL,
    reason="promtool not installed; install-prometheus-stack.sh provides it",
)


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # nosec B603 - fixed binary, repo-local paths
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
    misnamed = [p.name for p in _deployed_rule_files() if p.name.endswith(".test.yml")]
    assert not misnamed, (
        f"{misnamed} matches the deployed rule glob but is a promtool test file — "
        "Prometheus will fail to start. Rename to *.promtool-test.yml"
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


@needs_promtool
def test_the_promtool_suite_is_not_empty():
    """A rules file with no behavioural test is how the dead alert shipped."""
    assert _test_suites(), "no *.promtool-test.yml suites found — rule behaviour is unverified"
