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

from tools.lint._comment_syntax import code_lines

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
    return [cl.text.strip() for cl in code_lines(text) if cl.text.strip()]


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
    values = _ceiling_values(_CEILING.read_text(encoding="utf-8"))

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


# ---------------------------------------------------------------------------
# The gate must count the REF UNDER TEST, not the default branch (#18065).
#
# Without a `ref` the alerts API answers for the default branch, so this gate
# counted main's backlog whatever the pull request contained — which made it
# unable to validate the one thing it demands. A PR that removed an alert still
# read main's count and still failed, so the only way to go green was to be
# merged already. Three fixes were attempted against a check that could not see
# any of them.
# ---------------------------------------------------------------------------

_SCRIPT_SRC = _SCRIPT.read_text(encoding="utf-8")


def test_the_alert_query_is_scoped_to_the_ref_under_test():
    """The `ref` must reach the alerts query, from GITHUB_REF or an override."""
    assert (
        'ALERT_REF="${ALERT_REF:-${GITHUB_REF:-}}"' in _SCRIPT_SRC
    ), "the gate does not derive a ref from GITHUB_REF; it will count the default branch"
    assert (
        'alerts_query="${alerts_query}&ref=${ALERT_REF}"' in _SCRIPT_SRC
    ), "the ref is derived but never appended to the alerts query"


def test_an_unscanned_ref_fails_closed_rather_than_counting_zero():
    """The whole point of this file: 'could not look' must not equal 'found nothing'.

    An empty alert list comes back BOTH for a clean scan and for a ref that was
    never scanned. Scoping to a ref therefore introduces a new way to read 0, and
    it has to be refused — otherwise a PR whose analysis has not run yet reports
    a clean backlog.
    """
    assert "code-scanning/analyses?ref=" in _SCRIPT_SRC, (
        "nothing verifies that an analysis EXISTS for the ref, so 0 alerts on an " "unscanned ref would read as a pass"
    )
    assert "was never scanned" in _SCRIPT_SRC, "the unscanned-ref path does not announce itself as a refusal"
    # The existence check must GUARD the query, not merely precede it in the file.
    guard = _SCRIPT_SRC.index("analyses_count")
    query = _SCRIPT_SRC.index('alerts_query="${alerts_query}&ref=')
    assert guard < query, "the analysis-existence check runs after the ref is already trusted"


def test_the_ref_scoping_still_counts_the_default_branch_when_no_ref_is_available():
    """A cron or manual run has no GITHUB_REF; it must still check something."""
    assert "no ref available — counting the default branch" in _SCRIPT_SRC, (
        "with no ref the gate must say what it is counting instead of silently " "scoping to nothing"
    )
