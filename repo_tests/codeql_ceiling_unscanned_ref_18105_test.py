# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Zero CodEQL analyses has two causes, and the gate must tell them apart (#18105).

`check_codeql_alert_ceiling.sh` became ref-scoped and fail-closed in #18065, which
closed a real fail-open: a stale analysis of a previous commit, or another tool's
SARIF on the same ref, used to satisfy the gate.

It also made `code-quality` — a REQUIRED check — unpassable for a whole class of
PRs. `codeql.yml`'s `pull_request` trigger carries a `paths` filter, so a change
touching nothing CodeQL scans produces no analysis at all, and #18105 (a two-line
dependency bump) read `no CodeQL analysis for refs/pull/18105/merge` forever.

So the script now asks whether CodeQL reported a check for the commit, and the four
outcomes below are what this module pins. **Review on #18113 asked for exactly
this**: the first version of the guard asserted on message text, which still passes
if the branch logic is deleted and the comments remain.

The script is driven through its documented env inputs (`ALERT_REF`, `GITHUB_SHA`,
`CEILING_FILE`, `GITHUB_REPOSITORY`) against a stubbed ``gh`` on PATH, so no network
and no token are involved.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

_SCRIPT = repo_root() / "pipeline-scripts" / "check_codeql_alert_ceiling.sh"

#: A CodeQL analysis naming the commit under test.
_ANALYSIS_FOR_SHA = '[{"tool":{"name":"CodeQL"},"commit_sha":"deadbeef"}]'
#: No analyses at all — the shape both causes produce.
_NO_ANALYSES = "[]"

#: Checks on a commit CodeQL did NOT run for.
_CHECKS_WITHOUT_CODEQL = '{"check_runs":[{"name":"python-suite"},{"name":"code-quality"}]}'
#: Checks on a commit CodeQL DID run for — the workflow's own job name.
_CHECKS_WITH_CODEQL = '{"check_runs":[{"name":"Analyze (python)"},{"name":"python-suite"}]}'
#: GitHub's own code-scanning status check, which is not named by codeql.yml.
_CHECKS_WITH_PLATFORM_CODEQL = '{"check_runs":[{"name":"CodeQL"},{"name":"python-suite"}]}'

_GH_STUB = r"""#!/usr/bin/env bash
# Minimal `gh api` stand-in: applies --jq with real jq, serves canned bodies, and
# records every endpoint it was asked for so the test can assert ref scoping.
filter=""
endpoint=""
while [ $# -gt 0 ]; do
  case "$1" in
    --jq) filter="$2"; shift 2 ;;
    -e|--paginate|api) shift ;;
    *) endpoint="$1"; shift ;;
  esac
done
printf '%s\n' "$endpoint" >> "$GH_CALLS"
body=""
case "$endpoint" in
  *code-scanning/analyses*) body="$(cat "$FIX_ANALYSES")" ;;
  *check-runs*)
      if [ "${FIX_CHECKS_FAIL:-0}" = "1" ]; then exit 1; fi
      body="$(cat "$FIX_CHECKS")" ;;
  *code-scanning/alerts*) body="[]" ;;
  *) exit 1 ;;
esac
if [ -n "$filter" ]; then printf '%s' "$body" | jq -r "$filter"; else printf '%s' "$body"; fi
"""


def _run(tmp_path: Path, *, analyses: str, checks: str, checks_fail: bool = False):
    """Run the real script with a stubbed ``gh``; return (exit code, stdout+stderr, endpoints)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "gh"
    stub.write_text(_GH_STUB, encoding="utf-8")
    stub.chmod(0o755)

    (tmp_path / "analyses.json").write_text(analyses, encoding="utf-8")
    (tmp_path / "checks.json").write_text(checks, encoding="utf-8")
    ceiling = tmp_path / "ceiling.txt"
    # 0, not a slack value: the gate is BIDIRECTIONAL -- a count BELOW the ceiling fails
    # too, demanding it be lowered, because a ceiling left high re-licenses the alerts
    # just adjudicated. The stub serves an empty alert list, so the ceiling must be 0 or
    # every passing case here would fail for the opposite reason.
    ceiling.write_text("# test ceiling\n0\n", encoding="utf-8")
    calls = tmp_path / "calls.txt"
    calls.write_text("", encoding="utf-8")

    env = dict(os.environ)
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
            "CEILING_FILE": str(ceiling),
            "GITHUB_REPOSITORY": "owner/repo",
            "ALERT_REF": "refs/pull/18105/merge",
            "GITHUB_SHA": "deadbeef",
            "FIX_ANALYSES": str(tmp_path / "analyses.json"),
            "FIX_CHECKS": str(tmp_path / "checks.json"),
            "FIX_CHECKS_FAIL": "1" if checks_fail else "0",
            "GH_CALLS": str(calls),
        }
    )
    proc = subprocess.run(["bash", str(_SCRIPT)], capture_output=True, text=True, env=env, cwd=repo_root(), timeout=120)
    return proc.returncode, proc.stdout + proc.stderr, calls.read_text(encoding="utf-8")


def _alerts_endpoint(endpoints: str) -> str:
    for line in endpoints.splitlines():
        if "code-scanning/alerts" in line:
            return line
    return ""


def test_an_analysis_for_the_commit_counts_that_ref(tmp_path):
    """The ordinary scoped path: an analysis naming the commit scopes the count to it."""
    code, out, endpoints = _run(tmp_path, analyses=_ANALYSIS_FOR_SHA, checks=_CHECKS_WITHOUT_CODEQL)

    assert code == 0, f"a scanned ref under the ceiling must pass; got {code}\n{out}"
    assert "ref=refs/pull/18105/merge" in _alerts_endpoint(endpoints), (
        "the alert count was not scoped to the ref under test — this is the #18065 defect, "
        f"where the gate read the default branch instead. endpoints:\n{endpoints}"
    )


def test_no_analysis_and_no_codeql_check_falls_back_to_the_default_branch(tmp_path):
    """#18105: a change CodeQL does not scan must not fail a required check."""
    code, out, endpoints = _run(tmp_path, analyses=_NO_ANALYSES, checks=_CHECKS_WITHOUT_CODEQL)

    assert code == 0, f"an unscanned ref CodeQL never ran on must not fail; got {code}\n{out}"
    assert "CodeQL did not run for this ref" in out, "the fallback must say why it is not ref-scoped"
    assert "ref=refs/pull/18105/merge" not in _alerts_endpoint(endpoints), (
        "the fallback must count the default branch, not the unscanned ref — counting an "
        "unscanned ref is the fail-open this gate exists to prevent"
    )


@pytest.mark.parametrize(
    "checks,label",
    [(_CHECKS_WITH_CODEQL, "the workflow's own Analyze job"), (_CHECKS_WITH_PLATFORM_CODEQL, "GitHub's CodeQL check")],
)
def test_a_codeql_check_without_an_analysis_still_fails(tmp_path, checks, label):
    """The contrast: CodeQL ran and produced nothing for this commit — the #17303 fail-open.

    Both names must count, which is why the matcher is not just ``codeql``: the
    workflow publishes ``Analyze (<language>)`` and ``Detect changed languages``,
    while GitHub publishes a status check named ``CodeQL`` (#18113 review).
    """
    code, out, _ = _run(tmp_path, analyses=_NO_ANALYSES, checks=checks)

    assert code == 1, f"{label} present with no analysis must FAIL, not fall back; got {code}\n{out}"
    assert "the scan did not complete for this commit" in out


def test_an_errored_check_runs_api_fails_rather_than_guessing(tmp_path):
    """An undetermined answer is the one thing this gate may never read as clean."""
    code, out, _ = _run(tmp_path, analyses=_NO_ANALYSES, checks=_CHECKS_WITHOUT_CODEQL, checks_fail=True)

    assert code == 1, f"an errored check-runs API must fail, not fall back; got {code}\n{out}"
    assert "an undetermined answer is not a pass" in out


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))
