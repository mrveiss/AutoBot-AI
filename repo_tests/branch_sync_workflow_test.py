# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The branch sync pushes with AUTOBOT_PUSH_TOKEN only, no fallback; it never rebases or forces (#19548, #15306).

Ported from the parked-branch guard when #19548 folded
``auto-merge-base-into-parked-branches.yml`` and ``auto-update-pr-branches.yml``
into ``sync-branches-with-main.yml``. #15306's property still holds and is wider
now: every branch, PR or not, is checked out in some session's worktree, so its
history must never be rewritten. #19548 adds the token rule (owner decision,
2026-10-26): ``git push`` uses ``AUTOBOT_PUSH_TOKEN`` and nothing else, the job
fails at its first step when that secret is empty, and a ``PAT || GITHUB_TOKEN``
fallback is forbidden (#19542). ``GITHUB_TOKEN`` serves the REST calls only. The
PAT is never written to ``.git/config`` (no ``set-url``): the script takes it out of
its environment and hands it to ``git push`` alone (code review on PR #19636). The
zero-CI property moves to the ``[skip ci]`` merge message (branch_sync_19548_test).

WHY THIS STRIPS COMMENTS FIRST. The workflow's header explains at length why it
merges rather than rebases and why it never forces. A guard over the raw text
would match that prose and fail on the text documenting the correct behaviour.
Only executable shell and Python string constants are scanned.
"""

from __future__ import annotations

import ast
import re

import yaml
from repo_tests._paths import repo_root

from tools.lint._comment_syntax import code_text

_REPO_ROOT = repo_root()
_WORKFLOW = _REPO_ROOT / ".github/workflows/sync-branches-with-main.yml"
_SCRIPTS = [_REPO_ROOT / "pipeline-scripts/branch_sync.py", _REPO_ROOT / "pipeline-scripts/branch_sync_core.py"]
_RETIRED = (
    ".github/workflows/auto-update-pr-branches.yml",
    ".github/workflows/auto-merge-base-into-parked-branches.yml",
)

# `git rebase` as a command, not the substring.
_REBASE = re.compile(r"\bgit\s+(?:-\S+\s+)*rebase\b")
_FORCE_PUSH = re.compile(r"\bgit\s+push\b[^\n]*?(?:--force\b|--force-with-lease\b|\s-f\b|\s\+)")
_EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}", re.S)
_SECRET = re.compile(r"\bsecrets\.([A-Za-z_][A-Za-z0-9_]*)")
#: argv tokens that rewrite history or overwrite a remote ref.
_FORBIDDEN_ARGV = {"rebase", "--force", "--force-with-lease", "-f", "--force-if-includes", "reset"}

_PROTECTED = ("main", "release", "master", "Dev_new_gui")  # Dev_new_gui: temporary mirror; remove with #16461


def _spec() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _shell_bodies() -> list[str]:
    """Every `run:` script in the workflow, with shell comments removed."""
    bodies = []
    for job in _spec()["jobs"].values():
        for step in job.get("steps", []):
            if "run" in step:
                bodies.append(code_text(step["run"], name="x.sh"))
    return bodies


def _code_strings(path) -> list[str]:
    """Every string constant in a script except docstrings: the argv lives here."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
    ]


def test_the_workflow_and_script_exist_and_the_retired_ones_do_not() -> None:
    """The reach check, and AC 'one mechanism remains'."""
    assert _WORKFLOW.is_file(), f"{_WORKFLOW.relative_to(_REPO_ROOT)} is missing; update this guard, do not delete it"
    assert all(path.is_file() for path in _SCRIPTS)
    present = [rel for rel in _RETIRED if (_REPO_ROOT / rel).exists()]
    assert not present, f"retired by #19548 but back: {present}. Two sync mechanisms race on the same branches."


def test_never_rebases_or_force_pushes_in_shell() -> None:
    bodies = _shell_bodies()
    assert bodies and "branch_sync.py" in "\n".join(bodies), "no `run:` reaches the sync script; guard reads nothing"
    for body in bodies:
        for pattern in (_REBASE, _FORCE_PUSH):
            hit = pattern.search(body)
            assert hit is None, f"the sync workflow runs `{hit.group(0)}`: merge only, never force (#15306)"


def test_never_rebases_or_forces_in_the_script() -> None:
    """No argv token anywhere in the scripts can rewrite history or overwrite a ref."""
    strings = [value for path in _SCRIPTS for value in _code_strings(path)]
    assert "merge" in strings and "push" in strings, "the scan found no git argv; it is inspecting nothing"
    hits = sorted({value for value in strings if value.strip() in _FORBIDDEN_ARGV or value.startswith("+refs/")})
    assert not hits, f"forbidden git argv in the branch sync: {hits} (#19548 rule: merge only, plain push)"


_PAT = "${{ secrets.AUTOBOT_PUSH_TOKEN }}"
_REQUIRE, _SYNC = "Require AUTOBOT_PUSH_TOKEN", "Merge main"


def _steps() -> list[dict]:
    (job,) = _spec()["jobs"].values()
    return job["steps"]


def _step(prefix: str) -> dict:
    (step,) = [step for step in _steps() if str(step.get("name", "")).startswith(prefix)]
    return step


def test_no_secret_expression_has_a_fallback() -> None:
    """AC: every `${{ }}` naming a secret names exactly one, never `A || B` (#19542)."""
    text = _WORKFLOW.read_text(encoding="utf-8")
    expressions = _EXPRESSION.findall(code_text(text, name="x.yml"))
    secrets = [name for expression in expressions for name in _SECRET.findall(expression)]
    assert secrets, "no `secrets.` expression parsed; the token check is inspecting nothing"
    assert set(secrets) == {"AUTOBOT_PUSH_TOKEN", "GITHUB_TOKEN"}, f"unexpected secrets: {secrets}"
    fallback = [e for e in expressions if "secrets." in e and ("||" in e or "&&" in e or len(_SECRET.findall(e)) > 1)]
    assert not fallback, f"a token fallback is forbidden (#19542): {fallback}"


def test_the_pat_is_the_only_push_credential_and_reaches_nothing_else() -> None:
    """AUTOBOT_PUSH_TOKEN reaches the check and the sync step only, never .git/config; GITHUB_TOKEN does REST.

    Inside the sync step the script pops it before any git call and prepends it to
    the push argv alone: branch_sync_19548_test pins that by the argv each git call ran.
    """
    users = {
        step.get("name"): key for step in _steps() for key, value in (step.get("env") or {}).items() if value == _PAT
    }
    assert users == {_REQUIRE: "PUSH_TOKEN", _step(_SYNC)["name"]: "AUTOBOT_PUSH_TOKEN"}, f"the PAT reaches: {users}"
    joined = "\n".join(_shell_bodies())
    assert "set-url" not in joined and "@github.com" not in joined, "a token in a remote URL persists in .git/config"
    assert "extraheader" not in joined and "credential." not in joined, "the shell configures no git credential"
    sync_env = _step(_SYNC)["env"]
    assert sync_env["GITHUB_TOKEN"] == "${{ secrets.GITHUB_TOKEN }}", "REST calls use the run-scoped token"


def test_the_token_and_its_header_form_are_masked_before_the_script_runs() -> None:
    body = code_text(_step(_SYNC)["run"], name="x.sh")
    raw, header = (
        'echo "::add-mask::${AUTOBOT_PUSH_TOKEN}"',
        "printf 'x-access-token:%s' \"${AUTOBOT_PUSH_TOKEN}\" | base64 -w0",
    )
    assert raw in body and header in body, "both the token and its base64 header must be masked"
    assert body.index(header) < body.index("branch_sync.py"), "masking after the script starts is too late"


def test_a_missing_push_token_fails_the_job_before_anything_runs() -> None:
    first = _steps()[0]
    assert first.get("name") == _REQUIRE, "the token check must be the first step: fail loudly at the start"
    assert "if" not in first and not first.get("continue-on-error"), "the check must never be skippable"
    body = code_text(first["run"], name="x.sh")
    assert '[ -z "${PUSH_TOKEN}" ]' in body and "::error::AUTOBOT_PUSH_TOKEN" in body and "exit 1" in body


def test_the_checkout_is_main_and_persists_no_credential() -> None:
    checkout = next(step for step in _steps() if str(step.get("uses", "")).startswith("actions/checkout"))
    assert checkout["with"].get("persist-credentials") is False, "the PAT reaches the push argv only"
    assert checkout["with"].get("ref") == "main", "the default branch, never PR code (untrusted-checkout)"
    assert "token" not in checkout["with"], "the fetch needs no credential beyond the default"
    (job,) = _spec()["jobs"].values()
    assert job.get("if") == "github.ref == 'refs/heads/main'", "a dispatch from a branch must not run with the PAT"


def test_permissions_are_exactly_what_the_sync_needs() -> None:
    spec = _spec()
    assert spec.get("permissions") == {}, "workflow-level permissions must be empty; the job declares its own"
    (job,) = spec["jobs"].values()
    # contents: read -- the PAT pushes; GITHUB_TOKEN only reads the clone, lists PRs, labels and comments.
    assert job["permissions"] == {"contents": "read", "pull-requests": "write", "issues": "write"}
    assert job.get("timeout-minutes"), "a sync over ~150 branches needs an explicit timeout"
    assert job["runs-on"] == "ubuntu-latest", "never the singleton self-hosted runner (#13401)"


def test_triggers_are_main_pushes_a_schedule_and_dispatch() -> None:
    spec = _spec()
    triggers = spec.get("on", spec.get(True))  # PyYAML parses a bare `on:` as True
    assert set(triggers) == {"push", "schedule", "workflow_dispatch"}
    # A push trigger is safe only because it is scoped to main, which is never a target.
    assert triggers["push"] == {"branches": ["main"]}, "a push trigger wider than main would re-fire on sync pushes"


def test_runs_one_at_a_time_and_never_cancels_a_run_mid_push() -> None:
    concurrency = _spec().get("concurrency") or {}
    assert concurrency.get("group"), "no concurrency group: two main pushes would race on the same branches"
    assert concurrency.get("cancel-in-progress") is False, "a run cancelled mid-push leaves no record of what moved"


def test_full_history_is_fetched() -> None:
    (job,) = _spec()["jobs"].values()
    checkout = next(step for step in job["steps"] if str(step.get("uses", "")).startswith("actions/checkout"))
    assert checkout["with"]["fetch-depth"] == 0, "a shallow clone reports wrong behind-counts (#15306)"


def test_the_merge_commits_have_an_identity() -> None:
    joined = "\n".join(_shell_bodies())
    assert "git config user.name" in joined and "git config user.email" in joined


def test_protected_branches_are_never_push_targets() -> None:
    joined = "\n".join(_shell_bodies())
    for line in joined.splitlines():
        if "git push" in line:
            for protected in _PROTECTED:
                assert f"refs/heads/{protected}" not in line, f"pushes to `{protected}`: {line.strip()!r}"
