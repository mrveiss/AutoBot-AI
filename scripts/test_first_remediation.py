#!/usr/bin/env python3
"""
Test-first remediation loop.

Workflow per issue:
  1. Pull issue from GitHub
  2. Create isolated git worktree
  3. Write a failing pytest that reproduces the bug (committed separately)
  4. Iterate code edits via claude CLI until the test passes
  5. Verify no regressions in the broader suite
  6. Open PR with two commits: failing-test commit + fix commit
  7. On 5 failed iterations: post a structured failure report to the issue

Usage:
  python3 scripts/test_first_remediation.py               # picks oldest open bug
  python3 scripts/test_first_remediation.py 1234 5678     # specific issue numbers
  python3 scripts/test_first_remediation.py --dry-run 1234  # print plan, no edits
"""

import argparse
import asyncio
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = "mrveiss/AutoBot-AI"
MAX_FIX_ITERATIONS = 5
WORKTREE_BASE = Path(__file__).parent.parent / ".worktrees"
BLOCKED_COMMANDS = ("rm -rf", "rsync --delete", "git reset --hard", "git clean -fd")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@dataclass
class RemediationResult:
    issue_number: int
    success: bool
    iterations: int
    pr_url: str | None = None
    failure_report: str | None = None
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, check=check)


REPO_ROOT = Path(__file__).parent.parent


def create_worktree(issue_number: int) -> Path:
    branch = f"issue-{issue_number}"
    worktree_path = WORKTREE_BASE / branch
    _run(["git", "worktree", "add", str(worktree_path), "-b", branch, "origin/Dev_new_gui"], cwd=REPO_ROOT)
    _run(["git", "-C", str(worktree_path), "branch", "--unset-upstream"])
    return worktree_path


def cleanup_worktree(worktree_path: Path) -> None:
    branch = worktree_path.name
    subprocess.run(
        ["git", "worktree", "remove", str(worktree_path), "--force"],
        capture_output=True,
        cwd=REPO_ROOT,
    )
    subprocess.run(
        ["git", "branch", "-D", branch],
        capture_output=True,
        cwd=REPO_ROOT,
    )


def git_commit(worktree: Path, message: str, files: list[str] | None = None) -> None:
    if files:
        _run(["git", "-C", str(worktree), "add", *files])
    else:
        _run(["git", "-C", str(worktree), "add", "-u"])
    _run(["git", "-C", str(worktree), "commit", "-m", message])


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def run_pytest(worktree: Path, test_path: str | None = None) -> tuple[bool, str]:
    cmd = ["python3", "-m", "pytest", "-x", "--tb=short", "-q", "--no-header"]
    if test_path:
        cmd.append(test_path)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=worktree)
    return result.returncode == 0, result.stdout + result.stderr


def run_pytest_baseline(worktree: Path) -> set[str]:
    """Run full suite without -x; return set of FAILED test node IDs."""
    cmd = ["python3", "-m", "pytest", "--tb=no", "-q", "--no-header"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=worktree)
    failures: set[str] = set()
    for line in (result.stdout + result.stderr).splitlines():
        if line.startswith("FAILED "):
            failures.add(line.split()[1])
    return failures


def has_new_failures(worktree: Path, baseline: set[str]) -> tuple[bool, str]:
    """Return (has_regressions, output). True only if failures grew beyond baseline."""
    cmd = ["python3", "-m", "pytest", "--tb=short", "-q", "--no-header"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=worktree)
    output = result.stdout + result.stderr
    if result.returncode == 0:
        return False, output
    current: set[str] = set()
    for line in output.splitlines():
        if line.startswith("FAILED "):
            current.add(line.split()[1])
    new = current - baseline
    return bool(new), output if new else f"[baseline failures only, no regressions]\n{output}"


# ---------------------------------------------------------------------------
# GitHub helpers
# ---------------------------------------------------------------------------


def fetch_issue(number: int) -> dict:
    r = _run(["gh", "issue", "view", str(number), "-R", REPO, "--json", "number,title,body,labels"])
    return json.loads(r.stdout)


def pick_oldest_bug_issue() -> dict:
    r = _run(
        [
            "gh",
            "issue",
            "list",
            "-R",
            REPO,
            "--label",
            "bug",
            "--state",
            "open",
            "--limit",
            "1",
            "--json",
            "number,title,body,labels",
            "--jq",
            ".[0]",
        ]
    )
    data = r.stdout.strip()
    if not data:
        raise SystemExit("No open bug issues found")
    return json.loads(data)


def create_pr(worktree: Path, issue_number: int, title: str) -> str:
    _run(["git", "push", "-u", "origin", f"issue-{issue_number}"], cwd=worktree)
    r = _run(
        [
            "gh",
            "pr",
            "create",
            "--title",
            f"fix(#{issue_number}): {title[:60]}",
            "--body",
            (
                f"Closes #{issue_number}\n\n"
                "## Approach\n"
                "Test-first remediation: failing repro test committed first, "
                "then production fix. Two separate commits make the regression "
                "vs fix history explicit."
            ),
            "--base",
            "Dev_new_gui",
        ],
        cwd=worktree,
    )
    return r.stdout.strip()


def post_failure_comment(issue_number: int, report: str) -> None:
    body = (
        f"⚠️ **Auto-remediation failed** after {MAX_FIX_ITERATIONS} iterations.\n\n"
        "```\n"
        f"{report[-3000:]}\n"
        "```\n\n"
        "Manual intervention required."
    )
    subprocess.run(
        ["gh", "issue", "comment", str(issue_number), "-R", REPO, "-b", body],
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Claude CLI agent
# ---------------------------------------------------------------------------


def _is_destructive(cmd: str) -> bool:
    return any(blocked in cmd for blocked in BLOCKED_COMMANDS)


def claude_write_test(issue: dict, worktree: Path) -> str | None:
    """Ask claude CLI to write a failing repro test. Returns path or None."""
    test_file = f"autobot-backend/tests/test_issue_{issue['number']}_repro.py"
    prompt = (
        f"Working directory: {worktree}\n"
        f"GitHub Issue #{issue['number']}: {issue['title']}\n\n"
        f"Issue body:\n{issue.get('body', 'No description provided')}\n\n"
        "Task: Write a pytest test that FAILS on the current code, reproducing this bug.\n"
        f"Write it to: {test_file}\n"
        "Rules:\n"
        "- Use existing test helpers/fixtures from autobot-backend/tests/\n"
        "- Import from autobot-backend/ or autobot_shared/ only\n"
        "- The test must assert the CORRECT behaviour (which currently fails)\n"
        "- No mocking of the root cause itself\n"
        "Do NOT add any other files. Write only the test."
    )
    result = subprocess.run(
        ["claude", "--print", prompt],
        capture_output=True,
        text=True,
        cwd=str(worktree),
    )
    if result.returncode != 0:
        return None
    full_path = worktree / test_file
    return test_file if full_path.exists() else None


def claude_fix(issue: dict, worktree: Path, test_file: str, iteration: int, last_output: str) -> None:
    """Ask claude CLI to fix the production code for one iteration."""
    prompt = (
        f"Working directory: {worktree}\n"
        f"GitHub Issue #{issue['number']}: {issue['title']}\n"
        f"Fix attempt {iteration}/{MAX_FIX_ITERATIONS}\n\n"
        f"Failing test: {test_file}\n"
        f"Last pytest output:\n{last_output[-2000:]}\n\n"
        "Task: Fix the production code so the test passes.\n"
        "Rules:\n"
        f"- Edit files in autobot-backend/ or autobot_shared/ only\n"
        f"- Do NOT modify {test_file}\n"
        "- Fix the root cause, not the symptom\n"
        f"- Never run: {', '.join(BLOCKED_COMMANDS)}\n"
        "- Do NOT commit anything"
    )
    subprocess.run(
        ["claude", "--print", prompt],
        capture_output=True,
        text=True,
        cwd=str(worktree),
    )


# ---------------------------------------------------------------------------
# Core loop
# ---------------------------------------------------------------------------


async def remediate_issue(issue: dict, dry_run: bool = False) -> RemediationResult:
    issue_number = issue["number"]
    title = issue["title"]
    worktree: Path | None = None

    if dry_run:
        print(f"[dry-run] Would create worktree for issue-{issue_number}")
        print(f"[dry-run] Would write test: autobot-backend/tests/test_issue_{issue_number}_repro.py")
        print(f"[dry-run] Would iterate up to {MAX_FIX_ITERATIONS} fix attempts")
        print(f"[dry-run] Would open PR to Dev_new_gui on success")
        return RemediationResult(issue_number, False, 0, notes=["dry-run: no changes made"])

    try:
        worktree = create_worktree(issue_number)

        # Phase 1: write failing test
        test_file = claude_write_test(issue, worktree)
        if not test_file:
            return RemediationResult(
                issue_number,
                False,
                0,
                failure_report="claude failed to produce a test file",
            )

        passed, output = run_pytest(worktree, test_file)
        if passed:
            return RemediationResult(
                issue_number,
                False,
                0,
                failure_report=f"Repro test passed before any fix — test does not reproduce the bug:\n{output}",
            )

        # Commit the failing test (first commit)
        git_commit(worktree, f"test(#{issue_number}): add failing repro test", [test_file])

        # Snapshot pre-existing failures so the regression check only catches new ones.
        baseline_failures = run_pytest_baseline(worktree)

        # Phase 2: iterate fixes
        for iteration in range(1, MAX_FIX_ITERATIONS + 1):
            claude_fix(issue, worktree, test_file, iteration, output)

            passed, output = run_pytest(worktree, test_file)
            if not passed:
                # Revert production file changes only, keep test
                _run(["git", "-C", str(worktree), "checkout", "--", "."])
                _run(["git", "-C", str(worktree), "restore", "--staged", "."])
                # Re-stage the test file (checkout wiped it from index)
                _run(["git", "-C", str(worktree), "checkout", "HEAD", "--", test_file])
                continue

            # Target passes — check for regressions beyond the pre-fix baseline
            regressed, regression_output = has_new_failures(worktree, baseline_failures)
            if regressed:
                _run(["git", "-C", str(worktree), "checkout", "--", "."])
                _run(["git", "-C", str(worktree), "checkout", "HEAD", "--", test_file])
                output = f"Regression detected:\n{regression_output}"
                continue

            # Both green — commit fix and open PR
            git_commit(worktree, f"fix(#{issue_number}): {title[:60]}")
            pr_url = create_pr(worktree, issue_number, title)
            return RemediationResult(issue_number, True, iteration, pr_url=pr_url)

        # Exhausted iterations
        report = f"Not fixed after {MAX_FIX_ITERATIONS} iterations.\nLast output:\n{output}"
        post_failure_comment(issue_number, report)
        return RemediationResult(issue_number, False, MAX_FIX_ITERATIONS, failure_report=report)

    finally:
        if worktree:
            cleanup_worktree(worktree)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main(issue_numbers: list[int], dry_run: bool) -> None:
    if issue_numbers:
        issues = [fetch_issue(n) for n in issue_numbers]
    else:
        issues = [pick_oldest_bug_issue()]

    results: list[RemediationResult] = []
    for issue in issues:
        print(f"\n{'='*60}")
        print(f"Issue #{issue['number']}: {issue['title']}")
        print("=" * 60)
        result = await remediate_issue(issue, dry_run=dry_run)
        results.append(result)
        status = "✅ FIXED" if result.success else "❌ FAILED"
        print(f"{status} in {result.iterations} iteration(s) — PR: {result.pr_url or 'none'}")
        if result.failure_report:
            print(f"Report:\n{result.failure_report[:400]}")

    succeeded = sum(1 for r in results if r.success)
    print(f"\n{'='*60}")
    print(f"Convergence: {succeeded}/{len(results)} issues fixed")
    for r in results:
        symbol = "✅" if r.success else "❌"
        print(f"  {symbol} #{r.issue_number}: {r.iterations} iter | PR: {r.pr_url or '—'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test-first remediation loop")
    parser.add_argument(
        "issues",
        nargs="*",
        type=int,
        metavar="ISSUE_NUMBER",
        help="GitHub issue numbers (omit to pick oldest open bug)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print plan without creating worktrees or making changes"
    )
    args = parser.parse_args()
    asyncio.run(main(args.issues, dry_run=args.dry_run))
