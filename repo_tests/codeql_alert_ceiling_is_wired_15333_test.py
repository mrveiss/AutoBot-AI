# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The open-alert ceiling must be wired into a REQUIRED check (#15333, #17300).

The ceiling itself is enforced at runtime by
`pipeline-scripts/check_codeql_alert_ceiling.sh`, which needs the GitHub API and
so cannot run here. What this guard checks is the thing a static test *can*
prove and that quietly breaks: that the script is still invoked from
`code-quality.yml`, still has the permission it needs, and that the ceiling file
still parses.

Why that matters more than it sounds. The whole defect class this addresses is a
gate that stops running and reports nothing — `CLAUDE_CODE_OAUTH_TOKEN` and
`CONVENTIONS_DENYLIST` are both unset in this repository, so two other security
jobs have never executed once and emit a `::notice::` instead of failing. A
ceiling that is deleted from the workflow would go equally quiet.

`code-quality` specifically, because it is in branch protection's required
contexts and CodeQL itself is not: an alert has to be adjudicated before a PR
can merge, which is the step that was missing when 111 alerts accumulated and an
arbitrary file write hid among them.
"""

from __future__ import annotations

import yaml
from repo_tests._paths import repo_root

_ROOT = repo_root()
_WORKFLOW = _ROOT / ".github" / "workflows" / "code-quality.yml"
_SCRIPT = _ROOT / "pipeline-scripts" / "check_codeql_alert_ceiling.sh"
_CEILING = _ROOT / "pipeline-scripts" / "codeql_alert_ceiling.txt"


def _workflow_text() -> str:
    return _WORKFLOW.read_text(encoding="utf-8")


def test_the_checker_script_exists_and_is_executable():
    assert _SCRIPT.exists(), "the ceiling checker is gone; the gate cannot run"
    assert (
        _SCRIPT.stat().st_mode & 0o111
    ), f"{_SCRIPT.name} is not executable, so the workflow step would fail to run it"


def test_the_ceiling_file_holds_exactly_one_number():
    """A ceiling that stops parsing makes the checker fail closed — but it should
    not get that far, and the failure would be reported as a tooling error rather
    than as a backlog that grew."""
    values = [
        ln.strip() for ln in _CEILING.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")
    ]

    assert len(values) == 1, f"expected one bare number in {_CEILING.name}, found {values}"
    assert values[0].isdigit(), f"ceiling {values[0]!r} is not a number"


def test_the_gate_is_invoked_from_the_code_quality_workflow():
    """Invoked from code-quality, which IS a required status check.

    Moving it to codeql.yml would look equivalent and would not be: that workflow
    is not in branch protection's required contexts, so its verdict cannot block
    a merge.
    """
    assert "check_codeql_alert_ceiling.sh" in _workflow_text(), (
        "the open-alert ceiling is no longer invoked from code-quality.yml — the backlog can grow again "
        "without anything going red"
    )


def test_the_workflow_grants_the_permission_the_gate_needs():
    """Without security-events: read the API call 401s, and the script fails
    closed — correct, but it would look like a broken gate rather than a missing
    permission, and the fix is one line here."""
    data = yaml.safe_load(_workflow_text())
    perms = data.get("permissions") or {}

    assert perms.get("security-events") == "read", (
        "code-quality.yml no longer grants security-events: read, so the alert-ceiling "
        f"gate cannot read the alerts. Current permissions: {perms}"
    )


def test_the_gate_is_not_soft_failed():
    """`continue-on-error` on this step would make it decorative.

    Checked as text around the step rather than by parsing every job, because the
    failure being guarded against is somebody adding one line, and that line
    would be adjacent to the invocation.
    """
    text = _workflow_text()
    idx = text.index("check_codeql_alert_ceiling.sh")
    window = text[max(0, idx - 1200) : idx + 200]

    assert "continue-on-error" not in window, "the alert-ceiling step is soft-failed; it cannot block anything"
