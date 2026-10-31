# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The open-alert ceiling must be wired into a REQUIRED check (#15333, #17300).

The ceiling itself is enforced at runtime by
`pipeline-scripts/check_codeql_alert_ceiling.sh`, which needs the GitHub API and
so cannot run here. What this guard checks is the thing a static test *can*
prove and that quietly breaks: that the script is still invoked from
`_gate-code-quality.yml`, still has the permission it needs, and that the ceiling file
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

import pytest
import yaml
from repo_tests._paths import repo_root

from tools.lint._comment_syntax import code_lines

_ROOT = repo_root()
_WORKFLOW = _ROOT / ".github" / "workflows" / "_gate-code-quality.yml"
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
        "the open-alert ceiling is no longer invoked from _gate-code-quality.yml — the backlog can grow again "
        "without anything going red"
    )


def test_the_workflow_grants_the_permission_the_gate_needs():
    """Without security-events: read the API call 401s, and the script fails
    closed — correct, but it would look like a broken gate rather than a missing
    permission, and the fix is one line here."""
    perms = (yaml.safe_load(_workflow_text()) or {}).get("permissions") or {}

    assert _grants_security_events_read(_workflow_text()), (
        "_gate-code-quality.yml no longer grants security-events: read, so the alert-ceiling "
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

#: Check-runs on a commit CodeQL never ran for -- the paths filter excluded it (#18105).
_CHECKS_WITHOUT_CODEQL = '{"total_count":2,"check_runs":[{"name":"python-suite"},{"name":"code-quality"}]}'
#: codeql.yml's own job name.
_CHECKS_WORKFLOW_JOB = '{"total_count":2,"check_runs":[{"name":"Analyze (python)"},{"name":"python-suite"}]}'
#: The same job as ci.yml publishes it since #18208: "<caller job> / <job>".
_CHECKS_CALLEE_JOB = '{"total_count":2,"check_runs":[{"name":"run-codeql / Analyze (python)"},{"name":"python-suite"}]}'
#: ci.yml's `run-codeql` caller when no language matched: SKIPPED, and still a check run. The matcher
#: must not read it as "CodeQL ran" or every dependency-only PR fails closed again (#18105).
_CHECKS_SKIPPED_CALLER = '{"total_count":2,"check_runs":[{"name":"run-codeql"},{"name":"python-suite"}]}'
#: GitHub's code-scanning status check, which the CodeQL body does not name.
_CHECKS_PLATFORM = '{"total_count":2,"check_runs":[{"name":"CodeQL"},{"name":"python-suite"}]}'


# ---------------------------------------------------------------------------
# CONTRAST PAIR, driving the SCRIPT with stubbed API responses (#18065).
#
# The assertions above read source text, so they would pass on a script that
# computed `analyses_count` and then ignored it. These run the real thing with a
# fake `gh` on PATH and assert the exit status, which is what CI acts on.
# ---------------------------------------------------------------------------

import json
import os
import pathlib
import stat
import subprocess


def _fake_gh(
    tmp_path,
    *,
    analyses: str,
    alerts: str,
    alerts_unscoped: str | None = None,
    checks: str = _CHECKS_WITHOUT_CODEQL,
    checks_fail: bool = False,
    analyses_seq: list[str] | None = None,
    checks_seq: list[str] | None = None,
    checks_sha: str | None = None,
) -> pathlib.Path:
    """A `gh` answering the two endpoints this gate calls, and nothing else.

    ``analyses_seq`` / ``checks_seq`` (#18123) answer successive calls in turn, the last one
    repeating: that is how a CodeQL run moves from in progress to uploaded between two reads.
    An answer of ``ERROR`` makes that call fail. ``checks_sha`` (#18123 review) is the commit
    the check runs attach to: any other commit's listing is empty, as it is for a PR's merge
    commit on GitHub, where the runs sit on the head.

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

    def _sequence(name: str, answers: list[str]) -> str:
        """Write one file per answer; return bash that prints the next one (the last repeats)."""
        for i, answer in enumerate(answers):
            (tmp_path / f"{name}.{i}").write_text(answer, encoding="utf-8")
        counter, last = tmp_path / f"{name}.n", len(answers) - 1
        return (
            f"n=$(cat '{counter}' 2>/dev/null || echo 0); [ \"$n\" -gt {last} ] && n={last}; "
            f"echo $((n + 1)) > '{counter}'; f='{tmp_path}/{name}.'\"$n\"; "
            f'[ "$(cat "$f")" = ERROR ] && exit 1; cat "$f"'
        )

    pages_of = lambda c: c if c.lstrip().startswith("[") else f"[{c}]"  # noqa: E731
    checks_file = tmp_path / "checks.json"
    checks_file.write_text(pages_of(checks), encoding="utf-8")
    analyses_answer = _sequence("analyses", analyses_seq or [analyses])
    checks_answer = _sequence("checks", [pages_of(c) for c in checks_seq]) if checks_seq else f"cat '{checks_file}'"
    if checks_sha:
        empty = '[{"total_count":0,"check_runs":[]}]'
        checks_answer = (
            f"case \" $* \" in *'commits/{checks_sha}/'*) {checks_answer} ;; *) printf '%s' '{empty}' ;; esac"
        )
    script.write_text(
        "#!/usr/bin/env bash\n"
        # The check-runs call is read by scripts/lib/check_run_status.py with
        'JQF=""; prev=""\n' 'for a in "$@"; do [ "$prev" = "--jq" ] && JQF="$a"; prev="$a"; done\n'
        # `--paginate --slurp`, so the stub answers with a JSON ARRAY of pages. A `checks`
        # that is already an array is the page list; a single page document is wrapped.
        # The matcher itself stays real (#18105, #19085).
        'for a in "$@"; do\n'
        '  case "$a" in\n'
        f"    *code-scanning/analyses*) {analyses_answer}; exit 0 ;;\n"
        f"    *check-runs*) {'exit 1' if checks_fail else 'true'}\n"
        # Like the real CLI: only `--paginate` reaches later pages. Without it the answer is
        # page 1 alone, so a single-page read is genuinely blind to a CodeQL run on page 2.
        '      case " $* " in *" --paginate "*) ' + checks_answer + " ;;\n"
        f"        *) jq -c '.[0]' '{checks_file}' | {{ if [ -n \"$JQF\" ]; then jq -r \"$JQF\"; else cat; fi; }} ;; esac\n"
        "      exit 0 ;;\n"
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
    tmp_path,
    *,
    analyses: str,
    alerts: str,
    sha: str = "cafe1234",
    alerts_unscoped: str | None = None,
    checks: str = _CHECKS_WITHOUT_CODEQL,
    checks_fail: bool = False,
    analyses_seq: list[str] | None = None,
    checks_seq: list[str] | None = None,
    wait_s: int = 0,
    checks_sha: str | None = None,
    check_sha_env: str | None = None,
) -> int:
    return _gate(**locals()).returncode


def _gate(
    tmp_path,
    *,
    analyses: str,
    alerts: str,
    sha: str = "cafe1234",
    alerts_unscoped: str | None = None,
    checks: str = _CHECKS_WITHOUT_CODEQL,
    checks_fail: bool = False,
    analyses_seq: list[str] | None = None,
    checks_seq: list[str] | None = None,
    wait_s: int = 0,
    checks_sha: str | None = None,
    check_sha_env: str | None = None,
) -> subprocess.CompletedProcess:
    bin_dir = _fake_gh(
        tmp_path,
        analyses=analyses,
        alerts=alerts,
        alerts_unscoped=alerts_unscoped,
        checks=checks,
        checks_fail=checks_fail,
        analyses_seq=analyses_seq,
        checks_seq=checks_seq,
        checks_sha=checks_sha,
    )
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["AUTOBOT_CHECK_RUNS_RETRY_DELAY"] = "0"
    env["ALERT_REF"] = "refs/pull/1/merge"
    env["GITHUB_SHA"] = sha
    env["CODEQL_WAIT_S"] = str(wait_s)
    env["CODEQL_POLL_S"] = "1"
    if check_sha_env:
        env["CODEQL_CHECK_SHA"] = check_sha_env
    return subprocess.run(
        ["bash", str(_SCRIPT)],
        cwd=_SCRIPT.parents[1],
        env=env,
        capture_output=True,
        text=True,
    )


_CODEQL_AT_SHA = '[{"tool":{"name":"CodeQL"},"commit_sha":"cafe1234"}]'
_NO_ALERTS = "[]"


def test_the_gate_passes_with_a_codeql_analysis_of_the_commit_and_no_alerts(tmp_path):
    """SHOULD NOT trip: the scan is CodeQL's, names this commit, and found nothing."""
    assert _run_gate(tmp_path, analyses=_CODEQL_AT_SHA, alerts=_NO_ALERTS) == 0


def test_nothing_scanned_the_ref_and_codeql_never_ran_falls_back_to_the_default_branch(tmp_path):
    """SHOULD NOT trip (#18105): CodeQL does not run on a change it does not scan.

    This case used to fail, and it made `code-quality` — a REQUIRED check —
    unpassable for every dependency-only and docs-only PR. codeql.yml's
    `pull_request` trigger carries a `paths` filter, so #18105 (a two-line
    requirements bump) read `no CodeQL analysis for refs/pull/18105/merge` forever,
    on a change that cannot grow the backlog.

    The ceiling is still enforced — against the default branch, which such a PR
    cannot have changed. That is weaker than a per-ref scan and it is the correct
    trade against a check that can never pass.
    """
    assert _run_gate(tmp_path, analyses="[]", alerts=_NO_ALERTS, checks=_CHECKS_WITHOUT_CODEQL) == 0


@pytest.mark.parametrize(
    "checks,label",
    [
        (_CHECKS_WORKFLOW_JOB, "the body's own Analyze job"),
        (_CHECKS_CALLEE_JOB, "the Analyze job as ci.yml's run-codeql publishes it (#18208)"),
        (_CHECKS_PLATFORM, "GitHub's CodeQL status check"),
    ],
)
def test_a_codeql_check_without_any_analysis_still_trips(tmp_path, checks, label):
    """SHOULD trip: the contrast for the case above — CodeQL ran and produced nothing.

    Both names are asserted because each is what the other's absence would hide. A
    matcher that only looked for "codeql" would miss `Analyze (python)`; one that only
    looked for the workflow's jobs would miss the status check GitHub publishes itself.
    """
    assert _run_gate(tmp_path, analyses="[]", alerts=_NO_ALERTS, checks=checks) == 1, label


def test_a_skipped_run_codeql_caller_is_not_evidence_that_codeql_ran(tmp_path):
    """SHOULD NOT trip (#18208): ci.yml's skipped `run-codeql` job is not a CodeQL run.

    The old pattern matched 'codeql' anywhere in a check name, which would count the skipped
    caller and turn "touches nothing CodeQL scans" back into the #18105 failure.
    """
    assert _run_gate(tmp_path, analyses="[]", alerts=_NO_ALERTS, checks=_CHECKS_SKIPPED_CALLER) == 0


def _paged_checks(codeql_page: int, *, declared_total: int | None = None) -> str:
    """130 check runs over two pages of 100/30, CodeQL's `Analyze (python)` on `codeql_page`."""
    names = [f"job-{i}" for i in range(130)]
    names[10 if codeql_page == 1 else 120] = "Analyze (python)"
    runs = [{"name": n} for n in names]
    total = 130 if declared_total is None else declared_total
    return json.dumps(
        [{"total_count": total, "check_runs": runs[:100]}, {"total_count": total, "check_runs": runs[100:]}]
    )


def test_codeql_on_page_two_of_the_check_runs_is_seen_not_called_absent(tmp_path):
    """SHOULD trip (#19085): CodeQL ran, past run 100, and produced no analysis for the commit.

    A single-page read counted 0 here and took the "did not run" branch -> exit 0, enforcing
    the ceiling against the default branch. Seeing it must take the `CodeQL reported N
    check(s)` failure instead. The page-1 twin pins that the count is the same either way.
    """
    assert _run_gate(tmp_path, analyses="[]", alerts=_NO_ALERTS, checks=_paged_checks(2)) == 1
    assert _run_gate(tmp_path, analyses="[]", alerts=_NO_ALERTS, checks=_paged_checks(1)) == 1


def test_a_check_runs_listing_that_does_not_add_up_fails_closed(tmp_path):
    """SHOULD trip (#19085): total_count says 131, 130 were read -- an incomplete read is no verdict."""
    short = _paged_checks(2, declared_total=131).replace("Analyze (python)", "job-x")
    assert _run_gate(tmp_path, analyses="[]", alerts=_NO_ALERTS, checks=short) == 1


def test_a_complete_two_page_listing_without_codeql_takes_the_did_not_run_branch(tmp_path):
    """SHOULD NOT trip: the contrast for the two cases above -- same 130 runs, correct total, no CodeQL.

    Proves the multi-page read itself succeeds, so their exit 1 comes from CodeQL being
    seen and from the miscount respectively, not from the paging.
    """
    complete = _paged_checks(2).replace("Analyze (python)", "job-x")
    assert _run_gate(tmp_path, analyses="[]", alerts=_NO_ALERTS, checks=complete) == 0


def test_an_errored_check_runs_api_trips_rather_than_guessing(tmp_path):
    """SHOULD trip: an undetermined answer is the one thing this gate may not call clean."""
    assert _run_gate(tmp_path, analyses="[]", alerts=_NO_ALERTS, checks_fail=True) == 1


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


# ---------------------------------------------------------------------------
# #18123: the gate raced the CodeQL upload. While CodeQL is still running for the commit it
# waits; it fails only on a run that FINISHED without an analysis, or one still running when
# the wait runs out. The four states the issue names, plus the timeout.
# ---------------------------------------------------------------------------

_SEMGREP_AT_SHA = '[{"tool":{"name":"Semgrep"},"commit_sha":"cafe1234"}]'
_SEMGREP_AND_CODEQL_AT_SHA = (
    '[{"tool":{"name":"Semgrep"},"commit_sha":"cafe1234"},{"tool":{"name":"CodeQL"},"commit_sha":"cafe1234"}]'
)
_CODEQL_RUNNING = '{"total_count":1,"check_runs":[{"name":"Analyze (python)","status":"in_progress"}]}'
_CODEQL_DONE = '{"total_count":1,"check_runs":[{"name":"Analyze (python)","status":"completed"}]}'


def test_a_codeql_run_still_in_progress_is_waited_for_not_failed(tmp_path):
    """State 1 (#18120's evidence): Semgrep has uploaded, CodeQL is still running. The gate
    used to fail here and pass on a re-run; now it waits for the upload and then judges it."""
    done = _gate(
        tmp_path,
        analyses="",
        alerts=_NO_ALERTS,
        analyses_seq=[_SEMGREP_AT_SHA, _SEMGREP_AND_CODEQL_AT_SHA],
        checks_seq=[_CODEQL_RUNNING, _CODEQL_DONE],
        wait_s=60,
    )
    assert done.returncode == 0, done.stderr
    assert "CodeQL still running for cafe1234" in done.stdout


def test_the_wait_reads_check_runs_on_the_pr_head_not_the_merge_commit(tmp_path):
    """#18123 review, CRITICAL: on pull_request GITHUB_SHA is the merge commit (analyses are
    recorded there), but check runs attach to the HEAD. Read on the merge commit, the pending
    count was always 0, so there was no wait and the race stayed."""
    kwargs = dict(
        analyses="",
        alerts=_NO_ALERTS,
        sha="merge111",
        analyses_seq=[_SEMGREP_AT_SHA, _SEMGREP_AND_CODEQL_AT_SHA.replace("cafe1234", "merge111")],
        checks_seq=[_CODEQL_RUNNING, _CODEQL_DONE],
        checks_sha="head2222",
        wait_s=60,
    )
    (tmp_path / "head").mkdir()
    (tmp_path / "merge").mkdir()
    on_head = _gate(tmp_path / "head", check_sha_env="head2222", **kwargs)
    on_merge = _gate(tmp_path / "merge", **kwargs)

    assert on_head.returncode == 0 and "CodeQL still running for head2222" in on_head.stdout, on_head.stderr
    assert on_merge.returncode == 1, "without the head SHA the run is invisible and the race returns"


def test_a_finished_codeql_run_with_no_analysis_still_fails_closed(tmp_path):
    """State 2: the run completed and nothing names the commit -- #17303's fail-closed, unchanged."""
    done = _gate(tmp_path, analyses=_SEMGREP_AT_SHA, alerts=_NO_ALERTS, checks=_CODEQL_DONE, wait_s=60)
    assert done.returncode == 1
    assert "a stale scan of an earlier commit, or another tool's SARIF" in done.stderr
    assert "still running" not in done.stdout + done.stderr, "a finished run must not be waited on"


def test_a_codeql_run_still_going_when_the_wait_runs_out_fails(tmp_path):
    """The bound: a timeout is not a verdict, so it fails rather than passing unscanned."""
    done = _gate(tmp_path, analyses=_SEMGREP_AT_SHA, alerts=_NO_ALERTS, checks=_CODEQL_RUNNING, wait_s=0)
    assert done.returncode == 1
    assert "CodeQL is still running for cafe1234" in done.stderr and "not a verdict" in done.stderr


def test_waiting_does_not_launder_a_stale_or_foreign_analysis(tmp_path):
    """States 3 and 4 (#17303, #18105): the run finishes, and what is there is a stale CodeQL
    scan or another tool's SARIF. Both still fail after the wait."""
    stale = '[{"tool":{"name":"CodeQL"},"commit_sha":"0000dead"}]'
    for name, analyses in (("stale", stale), ("foreign", _SEMGREP_AT_SHA)):
        (tmp_path / name).mkdir()
        done = _gate(
            tmp_path / name,
            analyses=analyses,
            alerts=_NO_ALERTS,
            checks_seq=[_CODEQL_RUNNING, _CODEQL_DONE],
            wait_s=60,
        )
        assert done.returncode == 1, analyses
        assert "CodeQL still running" in done.stdout, "it waited first"
        assert "is not a scan of this commit" in done.stderr, analyses


@pytest.mark.parametrize("which", ["checks", "analyses"])
def test_an_api_error_in_the_middle_of_the_wait_fails_closed(tmp_path, which):
    """A read that errors on the SECOND poll is still an undetermined answer, never a pass."""
    seqs = {
        "checks": dict(analyses_seq=[_SEMGREP_AT_SHA], checks_seq=[_CODEQL_RUNNING, "ERROR"]),
        "analyses": dict(analyses_seq=[_SEMGREP_AT_SHA, "ERROR"], checks_seq=[_CODEQL_RUNNING]),
    }[which]
    done = _gate(tmp_path, analyses="", alerts=_NO_ALERTS, wait_s=60, **seqs)
    assert done.returncode == 1
    assert "CodeQL still running" in done.stdout, "the error came mid-wait, after one poll"
    assert (
        "could not determine whether a CodeQL run" if which == "checks" else "could not read code-scanning analyses"
    ) in done.stderr


@pytest.mark.parametrize("poll", ["0", "-5", "x"])
def test_a_non_positive_poll_interval_is_refused(tmp_path, poll):
    bin_dir = _fake_gh(tmp_path, analyses=_SEMGREP_AT_SHA, alerts=_NO_ALERTS, checks=_CODEQL_RUNNING)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "ALERT_REF": "refs/pull/1/merge"}
    env.update(GITHUB_SHA="cafe1234", CODEQL_POLL_S=poll, AUTOBOT_CHECK_RUNS_RETRY_DELAY="0")
    done = subprocess.run(["bash", str(_SCRIPT)], cwd=_SCRIPT.parents[1], env=env, capture_output=True, text=True)
    assert done.returncode == 1 and "CODEQL_POLL_S" in done.stderr
