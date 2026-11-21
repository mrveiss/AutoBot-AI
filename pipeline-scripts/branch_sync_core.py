# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pure decisions for the branch sync (#19548): no git, no network, no clock.

``branch_sync.py`` merges main into every open same-repo ``land-next`` PR branch,
pushing with ``AUTOBOT_PUSH_TOKEN``; every merge commit ends with
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
NEVER_TARGET = frozenset({"main", "release", "master", "develop", "HEAD"})

#: Never synced, PR or not:
#: ``rescued/`` -- a stash snapshot, not a line of work (#15306); merging base into it
#: destroys what it records and conflicts forever.
#: ``dependabot/`` -- Dependabot rebases its own branches; one foreign commit makes it
#: stop managing the PR (owner decision on #19568).
#: ``automation/`` -- bot-owned branches (e.g. ``automation/test-durations``) that their
#: own workflow regenerates from main; a sync commit there is noise (#19568 review).
#: ``train-`` -- merge-train branches. A train's whole point is the full CI run on its
#: own head; a ``[skip ci]`` sync supersedes that run and leaves the train with no
#: suite. Whoever builds the train merges main into it with CI (#19724).
EXCLUDED_PREFIXES = ("rescued/", "dependabot/", "automation/", "train-")

#: The cross-session PR coordinator adds this label when a PR is admitted to CI and removes it when the
#: slot is released (safe-merge also removes it on merge). It is the ONLY thing that selects a PR for the
#: push-to-main and scheduled syncs: "we sync only the ones that have next slot" (owner rule 2026-11-18).
LABEL_LAND_NEXT = "land-next"

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
NO_OPEN_PR = "no-open-pr"
NO_SLOT = "no-ci-slot"
PUSH_IN_PROGRESS = "push-in-progress"

#: A pre-push hook marks its branch under here while its gate runs (#20260).
PUSH_MARKER_PREFIX = "refs/push-gate/"


def merge_message(branch: str, base: str = "main") -> str:
    """The exact merge-commit subject, so a reviewer can tell a delta is merge-only.

    It ends with `` [skip ci]``: the push token is a PAT, whose pushes DO start
    workflow runs, and GitHub skips push and pull_request workflows for a head
    commit carrying it. That is what keeps a sync at zero CI (#19548).
    """
    return f"Merge {base} into {branch} (auto-sync) [skip ci]"


#: The one request that starts a suite on a synced head (#21577). The subject is fixed text plus the PR number
#: in the issue-reference position the commit-subject rule needs; it carries no skip marker and no trailer.
START_CI_SUBJECT = "chore(ci): start the suite on the synced head"
SKIP_MARKER = "[skip ci]"
SUITE_WORKFLOW_PATH = ".github/workflows/ci.yml"
#: A run that never produced a verdict does not count as "the suite already started".
RUNS_THAT_STARTED_NOTHING = frozenset({"cancelled", "skipped", "startup_failure"})
_PR_NUMBER = re.compile(r"[1-9][0-9]{0,8}")


def parse_pr_number(text: str) -> Optional[int]:
    """The pull request number in *text* (an untrusted dispatch input): ASCII digits only, else None."""
    return int(text) if _PR_NUMBER.fullmatch(text or "") else None


def start_ci_message(number: int) -> str:
    """The subject of the one empty commit that starts the suite; never the skip marker, never a trailer."""
    return f"{START_CI_SUBJECT} (#{number})"


def refuse_start_ci(pull: Dict[str, Any], repository: str, base: str, behind: Optional[int], local_head: str) -> str:
    """Why a suite may NOT be started for this PR, or "" when it may.

    Only an open, non-draft, same-repo PR into ``base`` whose branch is a sync target, is 0 behind ``base``
    and whose head is the commit this run fetched. A branch behind ``base`` is refused, not merged first:
    the ordinary sync merges it, then the request is made again.
    """
    head, number = pull.get("head") or {}, pull.get("number")
    if pull.get("state") != "open":
        return f"#{number} is not open"
    if _is_fork(pull, repository):
        return f"#{number} comes from a fork; nothing is ever pushed to a fork"
    if (pull.get("base") or {}).get("ref") != base:
        return f"#{number} does not target {base}"
    if pull.get("draft"):
        return f"#{number} is a draft; mark it ready for review first"
    if _policy_bucket(head.get("ref", "")):
        return f"#{number} is on branch {code(head.get('ref', ''))}, which the sync never writes to"
    if behind is None or behind > 0:
        count = "an unknown number of" if behind is None else str(behind)
        return f"#{number} is {count} commit(s) behind {base}: let the sync merge it first, then ask again"
    if not local_head or local_head != head.get("sha"):
        return f"#{number}: its head is not the commit this run fetched (the branch moved); ask again"
    return ""


def suite_already_started(runs: Sequence[Dict[str, Any]], sha: str) -> bool:
    """True when ``sha`` already has a ``pull_request`` run of the suite, in progress or completed.

    A run counts when it is for exactly ``sha``, of the suite workflow, started by ``pull_request``, and is
    not one that produced nothing (cancelled, skipped, failed to start). In progress has no conclusion yet.
    """
    return any(
        run.get("head_sha") == sha
        and run.get("event") == "pull_request"
        and str(run.get("path") or "").startswith(SUITE_WORKFLOW_PATH)
        and run.get("conclusion") not in RUNS_THAT_STARTED_NOTHING
        for run in runs
    )


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


def has_next_slot(target: SyncTarget) -> bool:
    """True when the PR carries ``land-next``: it holds a CI slot, so it is worth a sync (owner rule 2026-11-18).

    The label alone decides. A DRAFT that carries it is synced too: the coordinator only labels a PR it
    admitted to CI, and a draft it admitted is about to run there. Any other PR is not moved at all: a sync
    only puts a ``[skip ci]`` head on it and invalidates its reviews.
    """
    return LABEL_LAND_NEXT in target.labels


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
        elif not has_next_slot(target):
            plan.skip(NO_SLOT, target.name)
        else:
            plan.targets.append(target)
    return claimed


def plan_run(pulls: Sequence[Dict[str, Any]], branches: Iterable[str], repository: str, base: str = "main") -> Plan:
    """Every target for one run: same-repo PRs into ``base`` that carry ``land-next``, oldest first.

    Nothing else: a PR without the label is skipped as ``no-ci-slot`` (owner rule 2026-11-18, #21806).

    A branch with no open PR is skipped: merging main into one whose PR had closed made it look
    ahead of main forever with nothing of its own. A same-repo PR into another base is never merged
    into either: that would put main into a branch whose PR says it belongs elsewhere.
    """
    plan = Plan()
    claimed = _plan_pulls(plan, pulls, repository, base)
    for branch in sorted(set(branches) - claimed):
        plan.skip(_policy_bucket(branch) or NO_OPEN_PR, f"{code(branch)} (no PR)")
    return plan


def branches_being_pushed(ls_remote: str, now: float) -> set:
    """Branches holding a live push marker, from ``git ls-remote`` output (#20260).

    A marker is ``refs/push-gate/<branch>/<expiry epoch>``. An expired one, or one that does not
    parse, is ignored, so a hook that died cannot hold a branch back for longer than its limit.
    """
    live = set()
    for line in ls_remote.splitlines():
        ref = line.split("\t")[-1]
        branch, _, expiry = ref[len(PUSH_MARKER_PREFIX) :].rpartition("/")
        if ref.startswith(PUSH_MARKER_PREFIX) and branch and expiry.isdigit() and int(expiry) > now:
            live.add(branch)
    return live


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
