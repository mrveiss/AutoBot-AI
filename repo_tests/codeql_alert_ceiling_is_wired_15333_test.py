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


# ---------------------------------------------------------------------------
# CONTRAST PAIR, driving the SCRIPT with stubbed API responses (#18065).
#
# The assertions above read source text, so they would pass on a script that
# computed `analyses_count` and then ignored it. These run the real thing with a
# fake `gh` on PATH and assert the exit status, which is what CI acts on.
# ---------------------------------------------------------------------------

import os
import pathlib
import stat
import subprocess


def _fake_gh(tmp_path, *, analyses: str, alerts: str, alerts_unscoped: str | None = None) -> pathlib.Path:
    """A `gh` answering the two endpoints this gate calls, and nothing else.

    It DISTINGUISHES a ref-scoped alerts query from an unscoped one. That is the
    whole point: with one canned answer the stub cannot tell whether `&ref=`
    reached the URL, so dropping it would go unnoticed and only a source-text
    assertion would have caught it. `alerts_unscoped` is what the default branch
    would answer, so forgetting the ref makes the gate read the wrong backlog —
    exactly the defect this scoping fixes.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    unscoped = alerts_unscoped if alerts_unscoped is not None else alerts
    script = bin_dir / "gh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        'for a in "$@"; do\n'
        '  case "$a" in\n'
        f"    *code-scanning/analyses*) printf '%s' '{analyses}'; exit 0 ;;\n"
        f"    *code-scanning/alerts*ref=*) printf '%s' '{alerts}'; exit 0 ;;\n"
        f"    *code-scanning/alerts*)   printf '%s' '{unscoped}'; exit 0 ;;\n"
        "  esac\n"
        "done\n"
        "echo '[]'\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return bin_dir


def _run_gate(
    tmp_path, *, analyses: str, alerts: str, sha: str = "cafe1234", alerts_unscoped: str | None = None
) -> int:
    bin_dir = _fake_gh(tmp_path, analyses=analyses, alerts=alerts, alerts_unscoped=alerts_unscoped)
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["ALERT_REF"] = "refs/pull/1/merge"
    env["GITHUB_SHA"] = sha
    return subprocess.run(
        ["bash", str(_SCRIPT)],
        cwd=_SCRIPT.parents[1],
        env=env,
        capture_output=True,
        text=True,
    ).returncode


_CODEQL_AT_SHA = '[{"tool":{"name":"CodeQL"},"commit_sha":"cafe1234"}]'
_NO_ALERTS = "[]"


def test_the_gate_passes_with_a_codeql_analysis_of_the_commit_and_no_alerts(tmp_path):
    """SHOULD NOT trip: the scan is CodeQL's, names this commit, and found nothing."""
    assert _run_gate(tmp_path, analyses=_CODEQL_AT_SHA, alerts=_NO_ALERTS) == 0


def test_the_gate_stops_when_no_analysis_exists_for_the_ref(tmp_path):
    """SHOULD trip: 0 alerts from an unscanned ref is 'could not look', not 'clean'."""
    assert _run_gate(tmp_path, analyses="[]", alerts=_NO_ALERTS) == 1


def test_the_gate_stops_on_a_stale_analysis_of_an_earlier_commit(tmp_path):
    """SHOULD trip: a PR ref keeps its analyses when a new commit lands.

    This is the fail-open the first version of the ref scoping had — 'an analysis
    exists for this ref' was satisfied by a scan of the PREVIOUS commit.
    """
    stale = '[{"tool":{"name":"CodeQL"},"commit_sha":"0000dead"}]'
    assert _run_gate(tmp_path, analyses=stale, alerts=_NO_ALERTS) == 1


def test_the_gate_stops_on_another_tools_analysis(tmp_path):
    """SHOULD trip: any tool can upload SARIF to the same ref."""
    other = '[{"tool":{"name":"Semgrep"},"commit_sha":"cafe1234"}]'
    assert _run_gate(tmp_path, analyses=other, alerts=_NO_ALERTS) == 1


def test_the_gate_still_fails_when_the_scan_is_valid_but_alerts_exceed_the_ceiling(tmp_path):
    """SHOULD trip: the ref scoping must not have disabled the actual ceiling."""
    two = '[{"number":1},{"number":2}]'
    assert _run_gate(tmp_path, analyses=_CODEQL_AT_SHA, alerts=two) == 1


def test_the_gate_reads_the_REF_alerts_not_the_default_branch(tmp_path):
    """The scoping itself, behaviourally.

    The PR ref is clean; the default branch carries two. A gate that forgets
    `&ref=` reads the two and fails, so passing here means the ref really reached
    the query. This replaces a source-text assertion that `&ref=` appears in the
    file — which proved the string was present, not that it was used.
    """
    rc = _run_gate(
        tmp_path,
        analyses=_CODEQL_AT_SHA,
        alerts="[]",  # the ref under test: clean
        alerts_unscoped='[{"number":1},{"number":2}]',  # the default branch: 2
    )
    assert rc == 0, "the gate counted the default branch instead of the ref under test"
