# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""fix-architecture-issues.sh reports a failed Redis stop, not just an absent
unit (#16071 AC4).

The script stops BOTH `redis-server` and `redis-stack-server` deliberately
(a node provisioned before #16060/#16071 may still carry the legacy apt
package) -- that dual-stop is a declared, tested exemption in
`redis_unit_is_the_stack_unit_16071_test.py::_LEGACY_CLEANUP`, not the
defect. The defect was `2>/dev/null || true` on each stop: it discarded
"unit not installed on this host" (expected, nothing to do) and "unit
exists but the stop failed" (a real problem) identically.

Not executed here -- a real `systemctl stop` needs a live systemd host,
and this repo never runs its own scripts locally (evidence comes from CI
or a sanctioned hook). These are static/structural checks on the script
text, the same evidence shape as the ansible YAML guards in this session.
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

_SCRIPT = "autobot-infrastructure/shared/scripts/vm-management/fix-architecture-issues.sh"


def _text() -> str:
    return (repo_root() / _SCRIPT).read_text(encoding="utf-8")


def test_script_exists():
    assert (repo_root() / _SCRIPT).is_file(), f"{_SCRIPT} missing or moved"


def test_no_blanket_swallow_on_a_redis_unit_stop():
    """The exact defect: a `stop <unit> ... || true` line can't tell an
    absent unit from a real failure. None should remain for either name."""
    offenders = [
        line.strip()
        for line in _text().splitlines()
        if re.search(r"systemctl\s+stop\s+redis(-stack)?-server", line) and "|| true" in line
    ]
    assert not offenders, f"still discards the stop result: {offenders}"


def test_checks_unit_existence_before_stopping():
    """AC4's fix: skip a unit that was never installed, rather than
    attempting (and then swallowing the failure of) stopping it. The script
    loops a single variable-driven check over both unit names rather than
    writing the check out twice, so this asserts the loop covers both names
    AND that the check itself is present, rather than checking each name
    against a check that is actually parameterised by shell variable."""
    text = _text()
    assert re.search(
        r'list-unit-files\s+"\$\{unit\}\.service"', text
    ), "no existence check gates the per-unit stop loop"
    assert re.search(
        r"for\s+unit\s+in\s+redis-server\s+redis-stack-server\b", text
    ), "the existence-gated loop no longer covers both redis unit names"


def test_a_real_stop_failure_is_reported_not_swallowed():
    """The other half of AC4: once a unit is confirmed present, a failed
    stop must surface (via error()), not disappear into `|| true`."""
    text = _text()
    assert re.search(
        r"if\s+!\s+sudo\s+systemctl\s+stop\s+\"?\$\{?unit\}?\"?", text
    ), 'expected an `if ! sudo systemctl stop "$unit"` guard so a real failure is caught'
    assert "Failed to stop" in text, "a failed stop is no longer reported"
