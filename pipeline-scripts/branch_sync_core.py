# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pure decisions for the branch sync (#19548): no git, no network, no clock.

``branch_sync.py`` merges main into every open same-repo PR branch and every
PR-less branch, pushing with ``AUTOBOT_PUSH_TOKEN``; every merge commit ends with
`` [skip ci]`` so a sync starts no push or pull_request workflow run.
Every judgement it makes lives here, so each one is pinned by a fixture test
rather than trusted: which branches are targets, how a merge or a push ended,
which workflow files a merge changes, and what the one PR comment says.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from autobot_shared.git_refs import is_safe_ref  # noqa: E402  # the one argv ref validator (#18125)

#: Never a target, whatever else changes: the base and the protected trunks.
#: Dev_new_gui: temporary mirror of main for the live updater; remove with #16461.
NEVER_TARGET = frozenset({"main", "release", "master", "develop", "HEAD", "Dev_new_gui"})

#: Never synced, PR or not:
#: ``rescued/`` -- a stash snapshot, not a line of work (#15306); merging base into it
#: destroys what it records and conflicts forever.
#: ``dependabot/`` -- Dependabot rebases its own branches; one foreign commit makes it
#: stop managing the PR (owner decision on #19568).
#: ``automation/`` -- bot-owned branches (e.g. ``automation/test-durations``) that their
#: own workflow regenerates from main; a sync commit there is noise (#19568 review).
EXCLUDED_PREFIXES = ("rescued/", "dependabot/", "automation/")

LABEL_CONFLICT = "sync-conflict"
LABEL_WORKFLOW = "sync-needs-workflow-token"
SYNC_LABELS = (LABEL_CONFLICT, LABEL_WORKFLOW)
MARKER_CONFLICT = "<!-- autobot-branch-sync:conflict -->"
MARKER_WORKFLOW = "<!-- autobot-branch-sync:workflow-token -->"
WORKFLOW_DIR = ".github/workflows/"

#: Item-count caps for the conflict comment (GitHub's body limit is 65536). The
#: count is capped and the omission stated; no subject or path is truncated.
MAX_FILES_LISTED = 40
MAX_COMMITS_PER_SIDE = 15

# A branch name is interpolated into git argv and API paths, so it must pass the
# shared validator: no leading '-', no '..' (the retired #14022 workflow's rule).
_ISSUE_REF = re.compile(r"#\d+")

# Outcome names. The summary rows and the tests use these, never literals.
SYNCED, CURRENT, CONFLICT, WORKFLOW = "synced", "up-to-date", "conflict", "workflow-push-refused"
HEAD_MOVED, FORK, ERROR, UNREACHABLE = "head-moved", "fork-skipped", "error", "unreachable"
OTHER_BASE, POLICY = "other-base", "excluded-by-policy"


def merge_message(branch: str, base: str = "main") -> str:
    """The exact merge-commit subject, so a reviewer can tell a delta is merge-only.

    It ends with `` [skip ci]``: the push token is a PAT, whose pushes DO start
    workflow runs, and GitHub skips push and pull_request workflows for a head
    commit carrying it. That is what keeps a sync at zero CI (#19548).
    """
    return f"Merge {base} into {branch} (auto-sync) [skip ci]"


def classify_merge(returncode: int, output: str, unmerged: Sequence[str]) -> str:
    """``synced`` / ``conflict`` / ``error`` for one ``git merge``.

    A failure WITHOUT a conflict is a defect in this job, never information about
    the branch. Filing it as a conflict is how #15938 reported eleven unmergeable
    branches, green, from a workflow that had never merged anything.
    """
    if returncode == 0:
        return SYNCED
    if unmerged or any(line.startswith("CONFLICT") for line in output.splitlines()):
        return CONFLICT
    return ERROR


def workflow_changes(paths: Iterable[str]) -> List[str]:
    """The paths under ``.github/workflows/``: a push of these needs the token's ``workflow`` scope."""
    return sorted({path for path in paths if path.startswith(WORKFLOW_DIR)})


def classify_push(returncode: int, output: str) -> str:
    """``synced`` / ``workflow-push-refused`` / ``head-moved`` / ``error`` for one push."""
    if returncode == 0:
        return SYNCED
    lowered = output.lower()
    if "workflow" in lowered and ("refusing to allow" in lowered or "without `workflows` permission" in lowered):
        return WORKFLOW
    if any(word in lowered for word in ("non-fast-forward", "fetch first", "[rejected]", "stale info")):
        return HEAD_MOVED
    return ERROR


@dataclass
class SyncTarget:
    """One branch to sync. ``pr`` is None for a PR-less (parked) branch."""

    branch: str
    pr: Optional[int] = None
    head_sha: str = ""
    labels: Tuple[str, ...] = ()
    draft: bool = False

    @property
    def name(self) -> str:
        return f"#{self.pr} {code(self.branch)}" if self.pr else f"{code(self.branch)} (no PR)"


@dataclass
class Plan:
    targets: List[SyncTarget] = field(default_factory=list)
    skipped: Dict[str, List[str]] = field(default_factory=dict)

    def skip(self, bucket: str, item: str) -> None:
        self.skipped.setdefault(bucket, []).append(item)


def _is_fork(pull: Dict[str, Any], repository: str) -> bool:
    repo = (pull.get("head") or {}).get("repo") or {}
    return repo.get("full_name") != repository


def _pr_target(pull: Dict[str, Any]) -> SyncTarget:
    head = pull.get("head") or {}
    labels = tuple(sorted(label.get("name", "") for label in pull.get("labels") or []))
    return SyncTarget(head.get("ref", ""), int(pull["number"]), head.get("sha", ""), labels, bool(pull.get("draft")))


def _policy_bucket(branch: str) -> Optional[str]:
    if branch in NEVER_TARGET or branch.startswith(EXCLUDED_PREFIXES):
        return POLICY
    if not is_safe_ref(branch):
        return UNREACHABLE
    return None


def oldest_first(pulls: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """PRs by ``created_at`` ascending, then number: a run cut short still caught up the oldest (owner rule)."""
    return sorted(pulls, key=lambda pull: (pull.get("created_at") or "", int(pull["number"])))


def _plan_pulls(plan: Plan, pulls: Sequence[Dict[str, Any]], repository: str, base: str) -> set:
    claimed = set()
    for pull in oldest_first(pulls):
        target = _pr_target(pull)
        if _is_fork(pull, repository):
            plan.skip(FORK, f"#{target.pr}")
            continue
        claimed.add(target.branch)
        bucket = _policy_bucket(target.branch)
        if bucket:
            plan.skip(bucket, target.name)
        elif (pull.get("base") or {}).get("ref") != base:
            plan.skip(OTHER_BASE, target.name)
        else:
            plan.targets.append(target)
    return claimed


def plan_run(pulls: Sequence[Dict[str, Any]], branches: Iterable[str], repository: str, base: str = "main") -> Plan:
    """Every target for one run: same-repo PRs into ``base`` oldest first, then PR-less branches.

    A same-repo PR into another base is never merged into AND never treated as
    parked: either would put main into a branch whose PR says it belongs elsewhere.
    """
    plan = Plan()
    claimed = _plan_pulls(plan, pulls, repository, base)
    for branch in sorted(set(branches) - claimed):
        bucket = _policy_bucket(branch)
        if bucket:
            plan.skip(bucket, f"{code(branch)} (no PR)")
        else:
            plan.targets.append(SyncTarget(branch))
    return plan


def labels_to_clear(labels: Iterable[str]) -> List[str]:
    """The sync labels a branch that is now 0 behind must lose."""
    return [label for label in SYNC_LABELS if label in set(labels)]


def code(text: str) -> str:
    """``text`` as inline code that a backtick inside it cannot break (git allows them in refs)."""
    if "`" not in text:
        return f"`{text}`"
    return f"`` {text.replace('``', '` `')} ``"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _commit_rows(side: str, commits: Sequence[Tuple[str, str]]) -> List[str]:
    rows = []
    for sha, subject in commits[:MAX_COMMITS_PER_SIDE]:
        refs = ", ".join(dict.fromkeys(_ISSUE_REF.findall(subject))) or "none"
        rows.append(f"| {side} | `{sha}` | {_cell(subject)} | {refs} |")
    if len(commits) > MAX_COMMITS_PER_SIDE:
        rows.append(f"| {side} | | {len(commits) - MAX_COMMITS_PER_SIDE} more commit(s) not listed | |")
    if not commits:
        rows.append(f"| {side} | | no commit touched this file since the merge base | |")
    return rows


@dataclass
class FileHistory:
    """Commits that touched one conflicted file since the merge base, per side."""

    path: str
    on_base: List[Tuple[str, str]]
    on_branch: List[Tuple[str, str]]


def _file_section(history: FileHistory, base: str) -> List[str]:
    return [
        f"#### {code(history.path)}",
        "",
        "| side | commit | subject | issue refs |",
        "|---|---|---|---|",
        *_commit_rows(base, history.on_base),
        *_commit_rows("this branch", history.on_branch),
        "",
    ]


def conflict_comment(branch: str, base: str, merge_base: str, files: Sequence[FileHistory]) -> str:
    """The one ``sync-conflict`` comment: both sides' intent for every conflicted file."""
    lines = [
        MARKER_CONFLICT,
        f"### Auto-sync: merging {code(base)} into {code(branch)} conflicts",
        "",
        f"The sync aborted the merge and pushed nothing. Conflicts are information, so it never "
        f"resolves one itself. Below, for each conflicted file, are the commits that touched it on "
        f"each side since the merge base `{merge_base[:10]}`. Merge {code(base)} in yourself and push; "
        f"the label clears on the first run that finds this branch 0 behind.",
        "",
    ]
    for history in files[:MAX_FILES_LISTED]:
        lines += _file_section(history, base)
    if len(files) > MAX_FILES_LISTED:
        lines.append(f"{len(files) - MAX_FILES_LISTED} more conflicted file(s) not listed.")
    return "\n".join(lines).rstrip() + "\n"


def workflow_comment(branch: str, base: str, paths: Sequence[str]) -> str:
    """The one ``sync-needs-workflow-token`` comment."""
    listed = "\n".join(f"- {code(path)}" for path in paths) or "- (no workflow path in the merge delta)"
    return (
        f"{MARKER_WORKFLOW}\n### Auto-sync: {code(base)} not merged into {code(branch)}\n\n"
        f"The merge is clean, but GitHub refused the push: the sync's `AUTOBOT_PUSH_TOKEN` lacks the "
        f"`workflow` scope that a push changing workflow files needs (#19548). Nothing was pushed. "
        f"Workflow files in the merge:\n\n{listed}\n\n"
        f"This branch catches up once an owner grants the token that scope, on the author's next push "
        f"(merge {code(base)} in first), or in its train. The label clears on the next successful sync.\n"
    )
