# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20935: an absent `ps` on the node is an unknown parent, not a lost SSH session."""

from __future__ import annotations

import re
import subprocess

import pytest
from repo_tests._paths import repo_root

_TOOL = repo_root() / "tools/remote_test_node"


def _session_lost_run(ps_stub: str, parent: str, calls: int = 1) -> subprocess.CompletedProcess:
    src = (_TOOL / "remote_job.sh").read_text(encoding="utf-8")
    func = re.search(r"^session_lost\(\) \{.*?^\}", src, re.S | re.M).group(0)
    script = f"{ps_stub}\nparent={parent}\n{func}\n" + "session_lost\n" * (calls - 1) + "session_lost"
    return subprocess.run(["bash", "-c", script], check=False, capture_output=True, text=True)


def _session_lost_status(ps_stub: str, parent: str) -> int:
    return _session_lost_run(ps_stub, parent).returncode


@pytest.mark.parametrize(
    "ps_stub,parent,lost",
    [
        ("ps() { return 127; }", "100", False),  # ps missing: parent unknown, session kept
        ("ps() { :; }", "100", False),  # ps present but silent (hidden /proc): unknown, session kept
        ("ps() { echo ' 100'; }", "100", False),  # same parent: session alive
        ("ps() { echo ' 1'; }", "100", True),  # reparented: session lost
    ],
)
def test_session_lost_needs_a_positive_parent_change(ps_stub, parent, lost):
    assert (_session_lost_status(ps_stub, parent) == 0) is lost


def test_a_silent_ps_is_logged_once_on_stderr_and_not_a_lost_session():
    done = _session_lost_run("ps() { :; }", "100", calls=3)
    assert done.returncode == 1  # the last of three polls still reports "not lost"
    assert done.stderr.count("ps gave no parent pid") == 1, done.stderr


def test_a_ps_that_answers_logs_nothing():
    assert _session_lost_run("ps() { echo ' 100'; }", "100", calls=3).stderr == ""


def test_provision_requires_ps():
    prov = (_TOOL / "provision.sh").read_text(encoding="utf-8")
    assert "for tool in flock setsid git ps;" in prov
    assert "for tool in flock setsid git timeout ps;" in prov
    assert "procps-ng" in prov
