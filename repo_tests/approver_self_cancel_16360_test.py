# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A job that approves its own push's parked runs must not be cancelled by them (#16360).

``auto-fix-generated-types.yml`` pushes regenerated types to the PR branch; every
run at the new head is parked (the push is a bot's), and its own
``approve-parked-runs`` job releases them. The released Auto-fix run joined the
same concurrency group -- ``${{ github.workflow }}-${{ github.head_ref }}`` with
``cancel-in-progress: true`` -- and cancelled the run the approver lives in. On
#16351 the released run started at 15:23:12Z and the approver was cancelled at
15:23:15Z; whether everything was approved first is a race.

The fix separates group MEMBERSHIP for runs a bot's push caused, so it holds
whichever run's ``cancel-in-progress`` GitHub applies (undocumented). "A bot" is
any ``[bot]`` actor except dependabot (#16363 review): AUTOBOT_PUSH_TOKEN may be
an app identity. The group is evaluated below for each kind of actor rather than
matched as text. A cancelled approver cannot report from inside its sweep, so the
job also hands an interrupted sweep to the watchdog.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from repo_tests._paths import repo_root

yaml = pytest.importorskip("yaml", reason="PyYAML needed to parse the workflows")

WORKFLOW_DIR = repo_root() / ".github" / "workflows"
APPROVER_COMMAND = "ci_dispatch_watchdog.py --check dispatch"
AUTOFIX = WORKFLOW_DIR / "auto-fix-generated-types.yml"
# Whitespace-tolerant: the guard is about the expression, not its spacing.
_BOT_ACTOR = re.compile(r"endsWith\(\s*github\.actor\s*,\s*'\[bot\]'\s*\)")
_EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}", re.S)
_PRE_FIX_GROUP = "${{ github.workflow }}-${{ github.head_ref }}"


def _triggers(doc: dict) -> set[str]:
    # PyYAML reads the bare key `on:` as the boolean True.
    raw = doc.get("on", doc.get(True, {})) or {}
    if isinstance(raw, str):
        return {raw}
    return set(raw)


def _approver_workflows() -> list[Path]:
    return [
        path for path in sorted(WORKFLOW_DIR.glob("*.y*ml")) if APPROVER_COMMAND in path.read_text(encoding="utf-8")
    ]


def _cancels_its_group_on_pull_request(doc: dict) -> bool:
    """A pull_request-triggered workflow whose group cancels the run already in progress."""
    if "pull_request" not in _triggers(doc):
        return False
    concurrency = doc.get("concurrency")
    if not isinstance(concurrency, dict):
        return False  # the string form never cancels an in-progress run
    return concurrency.get("cancel-in-progress") not in (False, None, "false")


def _group(doc: dict) -> str:
    concurrency = doc.get("concurrency")
    return concurrency.get("group", "") if isinstance(concurrency, dict) else str(concurrency or "")


# --- the group, evaluated rather than matched --------------------------------
# Just enough of GitHub's expression language to render THIS group for a given
# actor: string literals, `github.*` lookups, ==, !=, &&, ||, endsWith(), format().
# Any other construct raises, so a reworded group fails loudly instead of being
# evaluated wrong.


def _call(name: str, args: list) -> object:
    if name == "endsWith":
        return str(args[0]).lower().endswith(str(args[1]).lower())
    if name == "format":
        return re.sub(r"\{(\d+)\}", lambda m: str(args[1 + int(m.group(1))]), args[0])
    raise ValueError(f"unsupported function {name}()")


def _eval(node: ast.AST, github: SimpleNamespace) -> object:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id == "github":
        return github
    if isinstance(node, ast.Attribute):
        return getattr(_eval(node.value, github), node.attr)
    if isinstance(node, ast.BoolOp):  # && and || return an operand, like GitHub's
        result: object = None
        for operand in node.values:
            result = _eval(operand, github)
            if (not result) if isinstance(node.op, ast.And) else result:
                return result
        return result
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], (ast.Eq, ast.NotEq)):
        # GitHub compares strings case-insensitively.
        left, right = (str(_eval(side, github)).lower() for side in (node.left, node.comparators[0]))
        return (left == right) if isinstance(node.ops[0], ast.Eq) else (left != right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
        return _call(node.func.id, [_eval(arg, github) for arg in node.args])
    raise ValueError(f"unsupported expression: {ast.dump(node)[:120]}")


def _render(group: str, actor: str) -> str:
    head = SimpleNamespace(sha="abc123")
    github = SimpleNamespace(
        workflow="Auto-fix Generated Types",
        head_ref="issue-1",
        actor=actor,
        event=SimpleNamespace(pull_request=SimpleNamespace(head=head)),
    )

    def one(match: re.Match) -> str:
        source = match.group(1).strip().replace("&&", " and ").replace("||", " or ")
        value = _eval(ast.parse(source, mode="eval").body, github)
        return "" if value in (None, False) else str(value)

    return _EXPRESSION.sub(one, group)


# --- tests --------------------------------------------------------------------


def test_the_scan_finds_the_approver_this_issue_is_about():
    names = {path.name for path in _approver_workflows()}
    assert "auto-fix-generated-types.yml" in names, f"approver scan found only {sorted(names)}"


def test_the_pre_fix_group_put_a_bot_run_in_the_approvers_group():
    """Known positive for the evaluator: the #16351 group is one group for everyone."""
    assert _render(_PRE_FIX_GROUP, "github-actions[bot]") == _render(_PRE_FIX_GROUP, "mrveiss")
    assert not _BOT_ACTOR.search(_PRE_FIX_GROUP)


@pytest.mark.parametrize(
    "actor,own_group",
    [
        ("mrveiss", False),  # a human push: the PR's shared group, superseding as before
        ("github-actions[bot]", True),  # the GITHUB_TOKEN fallback push (#16351)
        ("autobot-push-app[bot]", True),  # AUTOBOT_PUSH_TOKEN as a GitHub App identity (#16363 review)
        ("dependabot[bot]", False),  # never parked; its rebases keep superseding each other
    ],
)
def test_the_group_separates_exactly_the_runs_a_parked_bot_push_caused(actor: str, own_group: bool):
    group = _group(yaml.safe_load(AUTOFIX.read_text(encoding="utf-8")))
    rendered, human = _render(group, actor), _render(group, "mrveiss")

    assert (rendered != human) is own_group, f"{actor}: {rendered!r} vs human {human!r}"
    if own_group:
        assert rendered == f"{human}-regen-abc123"


@pytest.mark.parametrize("path", _approver_workflows(), ids=lambda path: path.name)
def test_an_approver_that_cancels_in_its_group_puts_bot_caused_runs_in_their_own(path: Path):
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if _cancels_its_group_on_pull_request(doc):
        assert _BOT_ACTOR.search(_group(doc)), (
            f"{path.name} approves parked runs from a pull_request run whose concurrency group cancels the run in "
            f"progress. A run its own push parks would, once approved, join that group and cancel the approver "
            f"(#16360). Put runs a bot caused in a group of their own: key `concurrency.group` on "
            f"`endsWith(github.actor, '[bot]')`."
        )


def test_the_watchdog_never_cancels_a_sweep_in_flight():
    """Why only auto-fix needs the discriminator: the watchdog's own group never cancels."""
    doc = yaml.safe_load((WORKFLOW_DIR / "ci-dispatch-watchdog.yml").read_text(encoding="utf-8"))
    assert doc["concurrency"]["cancel-in-progress"] is False


def _approver_job() -> dict:
    return yaml.safe_load(AUTOFIX.read_text(encoding="utf-8"))["jobs"]["approve-parked-runs"]


def test_an_interrupted_approval_is_handed_to_the_watchdog_on_the_same_base():
    """A cancelled approver cannot report from inside the sweep; a cancelled() step still runs."""
    job = _approver_job()
    handoff = [step for step in job["steps"] if str(step.get("if", "")).strip() == "cancelled()"]
    assert len(handoff) == 1, "approve-parked-runs needs exactly one `if: cancelled()` step (#16360)"
    assert "gh workflow run ci-dispatch-watchdog.yml" in handoff[0]["run"]
    assert "::error" in handoff[0]["run"]
    # One base branch for the sweep and the dispatch, set once at job level.
    assert job.get("env", {}).get("WATCHDOG_BASE_BRANCH"), "WATCHDOG_BASE_BRANCH must be a job-level env"
    assert '--ref "$WATCHDOG_BASE_BRANCH"' in handoff[0]["run"]


def test_the_approval_result_reaches_the_job_summary_and_keeps_its_exit_code():
    steps = _approver_job()["steps"]
    sweep = next(step for step in steps if APPROVER_COMMAND in str(step.get("run", "")))
    assert "set -o pipefail" in sweep["run"] and "| tee" in sweep["run"], "the tee must not discard the exit code"
    summary = [step for step in steps if str(step.get("if", "")).strip() == "always()"]
    assert summary and "GITHUB_STEP_SUMMARY" in summary[0]["run"]
