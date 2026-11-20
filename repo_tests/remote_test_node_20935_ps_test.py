# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20935: an absent `ps` on the node is an unknown parent, not a lost SSH session."""

from __future__ import annotations

import re
import subprocess

import pytest
from repo_tests._paths import repo_root

_TOOL = repo_root() / "tools/remote_test_node"


def _session_lost_status(ps_stub: str, parent: str) -> int:
    src = (_TOOL / "remote_job.sh").read_text(encoding="utf-8")
    func = re.search(r"^session_lost\(\) \{.*?^\}", src, re.S | re.M).group(0)
    script = f"{ps_stub}\nparent={parent}\n{func}\nsession_lost"
    return subprocess.run(["bash", "-c", script], check=False).returncode


@pytest.mark.parametrize(
    "ps_stub,parent,lost",
    [
        ("ps() { return 127; }", "100", False),  # ps missing: parent unknown, session kept
        ("ps() { echo ' 100'; }", "100", False),  # same parent: session alive
        ("ps() { echo ' 1'; }", "100", True),  # reparented: session lost
    ],
)
def test_session_lost_needs_a_positive_parent_change(ps_stub, parent, lost):
    assert (_session_lost_status(ps_stub, parent) == 0) is lost


def test_provision_requires_ps():
    prov = (_TOOL / "provision.sh").read_text(encoding="utf-8")
    assert "for tool in flock setsid git ps;" in prov
    assert "for tool in flock setsid git timeout ps;" in prov
    assert "procps-ng" in prov
