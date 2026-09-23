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


# ---------------------------------------------------------------------------
# The checks as pure predicates over text, so each can be driven by a fixture as
# well as by the live tree (#17303 review).
#
# Reading only the live files proves what the repository looks like today and
# nothing about whether the check would NOTICE a change -- which is the same
# false-negative shape this whole area keeps producing. Every predicate below
# therefore has a positive and a negative case.
# ---------------------------------------------------------------------------


def _invokes_the_gate(workflow_text: str) -> bool:
    return "check_codeql_alert_ceiling.sh" in workflow_text


def _grants_security_events_read(workflow_text: str) -> bool:
    perms = (yaml.safe_load(workflow_text) or {}).get("permissions") or {}
    return perms.get("security-events") == "read"


def _gate_is_soft_failed(workflow_text: str) -> bool:
    if "check_codeql_alert_ceiling.sh" not in workflow_text:
        return False
    idx = workflow_text.index("check_codeql_alert_ceiling.sh")
    return "continue-on-error" in workflow_text[max(0, idx - 1200) : idx + 200]


def _ceiling_values(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]


_WF_OK = """permissions:
  contents: read
  security-events: read
jobs:
  quality:
    steps:
    - name: ceiling
      run: bash pipeline-scripts/check_codeql_alert_ceiling.sh
"""
_WF_NO_INVOCATION = _WF_OK.replace("bash pipeline-scripts/check_codeql_alert_ceiling.sh", "true")
_WF_NO_PERMISSION = _WF_OK.replace("  security-events: read\n", "")
_WF_SOFT_FAILED = _WF_OK.replace("    - name: ceiling\n", "    - name: ceiling\n      continue-on-error: true\n")


def test_the_invocation_predicate_distinguishes_wired_from_unwired():
    assert _invokes_the_gate(_WF_OK)
    assert not _invokes_the_gate(_WF_NO_INVOCATION)


def test_the_permission_predicate_distinguishes_granted_from_missing():
    assert _grants_security_events_read(_WF_OK)
    assert not _grants_security_events_read(_WF_NO_PERMISSION)


def test_the_soft_fail_predicate_distinguishes_blocking_from_decorative():
    assert not _gate_is_soft_failed(_WF_OK)
    assert _gate_is_soft_failed(_WF_SOFT_FAILED)


def test_the_ceiling_parser_distinguishes_one_value_from_none_or_many():
    assert _ceiling_values("# why\n9\n") == ["9"]
    assert _ceiling_values("# why only\n") == []
    assert _ceiling_values("# why\n9\n10\n") == ["9", "10"]


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
    assert _invokes_the_gate(_workflow_text()), (
        "the open-alert ceiling is no longer invoked from code-quality.yml — the backlog can grow again "
        "without anything going red"
    )


def test_the_workflow_grants_the_permission_the_gate_needs():
    """Without security-events: read the API call 401s, and the script fails
    closed — correct, but it would look like a broken gate rather than a missing
    permission, and the fix is one line here."""
    perms = (yaml.safe_load(_workflow_text()) or {}).get("permissions") or {}

    assert _grants_security_events_read(_workflow_text()), (
        "code-quality.yml no longer grants security-events: read, so the alert-ceiling "
        f"gate cannot read the alerts. Current permissions: {perms}"
    )


def test_the_gate_is_not_soft_failed():
    """`continue-on-error` on this step would make it decorative.

    Checked as text around the step rather than by parsing every job, because the
    failure being guarded against is somebody adding one line, and that line
    would be adjacent to the invocation.
    """
    assert not _gate_is_soft_failed(_workflow_text()), "the alert-ceiling step is soft-failed; it cannot block anything"
