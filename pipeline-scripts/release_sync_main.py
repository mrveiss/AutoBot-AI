#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Open, or update, the ONE release-sync pull request into main — #16246.

``main`` is the default branch, so scheduled workflows run ``main``'s copy and
Dependabot reads ``main``'s dependencies, while every pull request targets
``Dev_new_gui``. The owner's decision on #16221 keeps ``main`` as the default and
syncs it from ``Dev_new_gui`` regularly. The ``Sync Dev_new_gui → main`` workflow
(``sync-main-to-dev.yml``) is the "regularly": it force-pushes ``Dev_new_gui`` to
the release branch ``release-sync-main`` and runs this tool, which brings one
sync pull request to the current state, and nothing more.

A SYNC PULL REQUEST is any open pull request into ``main`` from this
repository whose head is the release branch (``--head``) or ``Dev_new_gui``
itself (``--source``). A sync opened by hand from the trunk therefore counts
too, and is never duplicated.

WHAT IT DECIDES (``decide``). Given the open sync pull requests and the number
of commits ``main`` lacks:

* none open, commits to sync  -> open one
* one or more open            -> update the OLDEST; report the rest
  (its body is rewritten only if this tool wrote it: a hand-opened sync PR
  keeps the body its author wrote)
* none open, nothing to sync  -> do nothing

It never opens a second sync pull request. If duplicates exist it updates the
oldest, names the others, and exits 1 so the duplicate state is visible on the
run rather than accumulating silently.

IT NEVER MERGES. A sync pull request must merge with a merge commit: ``main``
already holds one commit ``Dev_new_gui`` lacks (#15326's merge commit), so a
fast-forward is impossible, and a squash would add another commit only ``main``
has, making every later sync re-conflict. That choice belongs to the owner at
merge time, so the body carries the instruction and this tool calls no merge
endpoint at all.

WHY THE WORKFLOW LIST DOES NOT COME FROM THE COMPARE. ``GET /compare`` returns at
most 300 changed files. Measured 11 Sep 2026: it reported 300 while
``git diff --name-only`` between the branches listed 1474, so a list built from
it silently drops workflows. The ``.github/workflows`` directory listing is
fetched on both refs instead; its blob SHAs say which files differ, and only
those files' contents are fetched.

Usage:
    pipeline-scripts/release_sync_main.py --head release-sync-main --source Dev_new_gui
    pipeline-scripts/release_sync_main.py --dry-run

Environment:
    GITHUB_TOKEN       required — API credential (pull-requests: write)
    GITHUB_REPOSITORY  required — "owner/repo"
    GITHUB_API_URL     API root (default https://api.github.com)
    GITHUB_SERVER_URL  web root for the compare link printed when Actions may not
                       open pull requests (set by Actions; unset, the warning names
                       the branch instead of linking)

Exit codes:
    0  the sync pull request was opened or updated, there was nothing to sync, or
       the repository does not let Actions open pull requests (a warning names
       the compare link; the branch push, the part that matters, has landed)
    1  more than one sync pull request is open: the oldest was updated, and the
       others are named for closing by hand
    2  missing configuration, or the API gave an unusable answer; nothing was
       written
"""

from __future__ import annotations

import argparse
import base64
import binascii
import os
import re
import sys
import urllib.parse
from pathlib import Path
from typing import AbstractSet, Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

# `pipeline-scripts` is not an importable package name, so the sibling module is
# reached by path — the idiom ci_red_cause.py uses. The HTTP client is REUSED:
# one transport, one place where a transport failure becomes a status code.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci_dispatch_watchdog import (  # noqa: E402
    DEFAULT_API_ROOT,
    GitHubApi,
    WatchdogApiError,
    WatchdogConfigError,
    WatchdogError,
)

# The one definition of "the release-sync PR", shared with the watchdog (#16272).
from release_sync_pull import RELEASE_SYNC_BASE, RELEASE_SYNC_HEAD, is_sync_pull  # noqa: E402

SYNC_TITLE = "release: sync main from Dev_new_gui"
DEFAULT_HEAD = RELEASE_SYNC_HEAD
DEFAULT_SOURCE = "Dev_new_gui"
DEFAULT_BASE = RELEASE_SYNC_BASE
OPENED_BY = ".github/workflows/sync-main-to-dev.yml"
# Leads every body this tool writes, and only a body carrying it is ever rewritten.
# A sync PR opened by hand keeps the body its author wrote, even one naming OPENED_BY.
BODY_MARKER = f"<!-- generated-by: {OPENED_BY} -->"
WORKFLOW_DIR = ".github/workflows"
WORKFLOW_SUFFIXES = (".yml", ".yaml")
TRACKING_ISSUE = "#16246"
# GitHub's maximum page size. A full page may not be the whole listing.
MAX_PULLS_PER_PAGE = 100
# GitHub's wording when "Allow GitHub Actions to create and approve pull
# requests" is off for the repository. Observed on this workflow 2026-08-10.
ACTIONS_PR_REFUSAL = "not permitted to create or approve pull requests"

ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_NOTHING = "nothing"

# What the sync does to one workflow's schedule on `main`.
STATE_ACTIVATES = "activates"
STATE_CHANGES = "changes"
STATE_STOPS = "stops"

STATE_WORDING = {
    STATE_ACTIVATES: "starts running on its schedule (no scheduled copy on `{base}` yet)",
    STATE_CHANGES: "already scheduled on `{base}`; the sync changes what runs",
    STATE_STOPS: "scheduled on `{base}` today; after the sync it no longer runs on a schedule",
}

# Top-level `on:` key, in any of the spellings YAML allows for it.
_ON_KEY_RE = re.compile(r"""^(?:on|"on"|'on')\s*:(?P<inline>.*)$""")
# A `schedule:` key, block form (`  schedule:`) or flow form (`{schedule: [...]}`).
_SCHEDULE_KEY_RE = re.compile(r"(?:^|[\s{,])schedule\s*:")
_CRON_RE = re.compile(r"\bcron\s*:\s*\S")


class SyncDecision(NamedTuple):
    """What one run does, and to which pull request."""

    action: str
    target: Optional[int]
    extras: Tuple[int, ...]
    reason: str


class ScheduledChange(NamedTuple):
    """One workflow whose scheduled behaviour on the base changes with the sync."""

    path: str
    state: str


class PullCreationRefused(WatchdogApiError):
    """The repository does not let GitHub Actions open pull requests."""


def decide(open_sync_pulls: Sequence[Dict[str, Any]], ahead_by: int) -> SyncDecision:
    """Choose create, update or nothing. Never create while any sync PR is open."""
    if ahead_by < 0:
        raise ValueError(f"ahead_by cannot be negative, got {ahead_by}")
    numbers = sorted(int(pull["number"]) for pull in open_sync_pulls)
    if numbers:
        oldest, extras = numbers[0], tuple(numbers[1:])
        reason = f"sync PR #{oldest} is open; its body is brought to {ahead_by} commits"
        if extras:
            listed = ", ".join(f"#{number}" for number in extras)
            reason += f"; {len(extras)} more open ({listed}), left untouched"
        return SyncDecision(ACTION_UPDATE, oldest, extras, reason)
    if ahead_by == 0:
        return SyncDecision(ACTION_NOTHING, None, (), "the base already holds every head commit")
    return SyncDecision(ACTION_CREATE, None, (), f"{ahead_by} commits to sync, no sync PR open")


def _uncommented(text: str) -> List[str]:
    """Non-blank lines with whole-line and trailing `#` comments removed."""
    lines: List[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        code = line.split(" #", 1)[0].rstrip()
        if code.strip():
            lines.append(code)
    return lines


def _on_block(lines: Sequence[str]) -> List[str]:
    """The `on:` value: its inline remainder plus every indented line under it."""
    for index, line in enumerate(lines):
        match = _ON_KEY_RE.match(line)
        if not match:
            continue
        block = [match.group("inline")]
        for follower in lines[index + 1 :]:
            if not follower[:1].isspace():
                break
            block.append(follower)
        return block
    return []


def declares_schedule(text: str) -> bool:
    """True when a workflow's `on:` block carries a `schedule` with a cron.

    Stdlib only, like the transport. Comments are stripped first because a
    disabled schedule is written as a commented-out block (`marker-tests.yml`),
    and reading it as live would list a workflow the sync does not activate.
    """
    block = "\n".join(_on_block(_uncommented(text)))
    return bool(_SCHEDULE_KEY_RE.search(block)) and bool(_CRON_RE.search(block))


def differing_workflows(head_blobs: Dict[str, str], base_blobs: Dict[str, str]) -> List[str]:
    """Workflow paths whose blob differs between the refs, or that exist on one only."""
    paths = set(head_blobs) | set(base_blobs)
    return sorted(path for path in paths if head_blobs.get(path) != base_blobs.get(path))


def schedule_transition(head_scheduled: Optional[bool], base_scheduled: Optional[bool]) -> Optional[str]:
    """How the sync changes one differing workflow's schedule. ``None`` = file absent.

    Returns ``None`` when neither copy is scheduled: the file differs, but the sync
    starts, changes and stops nothing on a schedule.
    """
    if head_scheduled:
        return STATE_CHANGES if base_scheduled else STATE_ACTIVATES
    return STATE_STOPS if base_scheduled else None


def _merge_section(base: str, source: str) -> List[str]:
    return [
        "## Merge with a merge commit",
        "",
        "**Merge with `gh pr merge --merge`. Never `--squash`, never rebase.**",
        "",
        f"`{base}` already holds a commit `{source}` lacks (the merge commit of #15326), so a",
        f"fast-forward is impossible. A squash would add a second commit only `{base}` has,",
        "and every later sync would re-conflict on the same files. The per-PR default here",
        "is `--squash`; this pull request is the exception. The workflow that opened it",
        "never merges; the merge is the owner's.",
    ]


def _schedule_section(scheduled: Sequence[ScheduledChange], base: str, source: str) -> List[str]:
    lines = ["## Scheduled workflows this sync activates or changes", ""]
    if not scheduled:
        return lines + [f"None: every scheduled workflow on `{source}` already matches `{base}`."]
    lines.append(f"Scheduled workflows run `{base}`'s copy, so merging this changes what runs:")
    lines.append("")
    for change in scheduled:
        wording = STATE_WORDING[change.state].format(base=base)
        lines.append(f"- `{change.path}` ({change.state}): {wording}")
    return lines


def _verification_section(ahead_by: int, base: str, source: str) -> List[str]:
    return [
        "## Verification",
        "",
        "- If no checks have run here, this was opened with the workflow's fallback token,",
        "  and GitHub starts no workflows for that token's events. Close and reopen it as a person.",
        f"- After the merge, `git rev-list --count origin/{base}..<merged {source} SHA>` is 0.",
        f"- Merging pushes to `{base}`, which runs `release.yml`.",
        f"- {ahead_by} commits at the time of this body; the workflow rewrites it each run.",
    ]


def build_body(ahead_by: int, scheduled: Sequence[ScheduledChange], source: str, base: str) -> str:
    """The sync PR's body, under the repository's PR template headings."""
    lines = [
        BODY_MARKER,
        "## Thinking Path",
        "",
        f"`{base}` is the default branch, so scheduled workflows run `{base}`'s copy and",
        f"Dependabot reads `{base}` (#16221). This carries the **{ahead_by} commits** on",
        f"`{source}` that `{base}` lacks.",
        "",
        *_merge_section(base, source),
        "",
        *_schedule_section(scheduled, base, source),
        "",
        *_verification_section(ahead_by, base, source),
        "",
        "## Model Used",
        "",
        f"None: opened by `{OPENED_BY}`.",
        "",
        "## Issue Link",
        "",
        f"Relates to {TRACKING_ISSUE}.",
    ]
    return "\n".join(lines) + "\n"


def _get(api: GitHubApi, path: str, context: str) -> Any:
    status, body = api.request("GET", path)
    if status != 200:
        raise WatchdogApiError(f"cannot read {context} (HTTP {status}): {body}")
    return body


def open_sync_pulls(api: GitHubApi, heads: AbstractSet[str], base: str) -> List[Dict[str, Any]]:
    """Open sync pull requests into *base*. Raises rather than returning [] or a partial list."""
    query = urllib.parse.urlencode({"state": "open", "base": base, "per_page": str(MAX_PULLS_PER_PAGE)})
    body = _get(api, f"/repos/{api.repository}/pulls?{query}", f"open PRs into {base}")
    if not isinstance(body, list):
        raise WatchdogApiError(f"open PRs into {base}: expected a list, got {type(body).__name__}")
    if len(body) >= MAX_PULLS_PER_PAGE:
        raise WatchdogApiError(f"{len(body)} open PRs into {base} fill a page; a sync PR may be on the next")
    return [pull for pull in body if is_sync_pull(pull, api.repository, heads, base)]


def commits_missing_from_base(api: GitHubApi, head: str, base: str) -> int:
    """How many commits *head* has that *base* lacks (the compare's ``ahead_by``)."""
    spec = f"{urllib.parse.quote(base, safe='')}...{urllib.parse.quote(head, safe='')}"
    body = _get(api, f"/repos/{api.repository}/compare/{spec}?per_page=1", "the compare")
    ahead = body.get("ahead_by") if isinstance(body, dict) else None
    if not isinstance(ahead, int) or ahead < 0:
        raise WatchdogApiError(f"the compare carried no usable ahead_by: {ahead!r}")
    return ahead


def workflow_blobs(api: GitHubApi, ref: str) -> Dict[str, str]:
    """Path -> blob SHA for every workflow file on *ref*."""
    query = urllib.parse.urlencode({"ref": ref})
    body = _get(api, f"/repos/{api.repository}/contents/{WORKFLOW_DIR}?{query}", f"workflows on {ref}")
    if not isinstance(body, list):
        raise WatchdogApiError(f"{WORKFLOW_DIR} on {ref} is not a directory listing")
    return {
        str(entry["path"]): str(entry["sha"])
        for entry in body
        if entry.get("type") == "file" and str(entry.get("name", "")).endswith(WORKFLOW_SUFFIXES)
    }


def workflow_text(api: GitHubApi, path: str, ref: str) -> str:
    """The decoded contents of one workflow file on *ref*."""
    query = urllib.parse.urlencode({"ref": ref})
    quoted = urllib.parse.quote(path)
    body = _get(api, f"/repos/{api.repository}/contents/{quoted}?{query}", f"{path} on {ref}")
    if not isinstance(body, dict) or body.get("encoding") != "base64":
        raise WatchdogApiError(f"{path} on {ref} came back without base64 content")
    try:
        return base64.b64decode(body.get("content") or "").decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise WatchdogApiError(f"{path} on {ref} could not be decoded: {exc}") from exc


def scheduled_changes(api: GitHubApi, head: str, base: str) -> List[ScheduledChange]:
    """Every workflow whose schedule on *base* the sync activates, changes or stops."""
    head_blobs, base_blobs = workflow_blobs(api, head), workflow_blobs(api, base)
    changes: List[ScheduledChange] = []
    for path in differing_workflows(head_blobs, base_blobs):
        on_head = declares_schedule(workflow_text(api, path, head)) if path in head_blobs else None
        on_base = declares_schedule(workflow_text(api, path, base)) if path in base_blobs else None
        state = schedule_transition(on_head, on_base)
        if state:
            changes.append(ScheduledChange(path, state))
    return changes


def is_actions_pr_refusal(reply: Any) -> bool:
    """True when a create-PR reply is the repository setting refusing Actions."""
    return ACTIONS_PR_REFUSAL in str(reply or "")


def refusal_hint(server: str, repository: str, base: str, head: str) -> str:
    """Where a person opens the pull request by hand: the compare page, or the branch."""
    if not server:
        return f"open a pull request from `{head}` into `{base}` by hand"
    return f"open it here: {server.rstrip('/')}/{repository}/compare/{base}...{head}?expand=1"


def create_pull(api: GitHubApi, head: str, base: str, body: str) -> int:
    payload = {"title": SYNC_TITLE, "head": head, "base": base, "body": body}
    status, reply = api.request("POST", f"/repos/{api.repository}/pulls", payload)
    if status == 201 and isinstance(reply, dict) and "number" in reply:
        return int(reply["number"])
    if is_actions_pr_refusal(reply):
        raise PullCreationRefused(f"Actions may not open pull requests here (HTTP {status})")
    raise WatchdogApiError(f"cannot open the sync PR (HTTP {status}): {reply}")


def update_pull_body(api: GitHubApi, number: int, body: str) -> None:
    status, reply = api.request("PATCH", f"/repos/{api.repository}/pulls/{number}", {"body": body})
    if status != 200:
        raise WatchdogApiError(f"cannot update the body of #{number} (HTTP {status}): {reply}")


def _open_pull(api: GitHubApi, head: str, base: str, body: str) -> str:
    """Open the sync PR, or say where to open it when the repository refuses Actions."""
    try:
        return f"opened #{create_pull(api, head, base, body)}"
    except PullCreationRefused:
        server = os.environ.get("GITHUB_SERVER_URL", "").strip()
        hint = refusal_hint(server, api.repository, base, head)
        _emit("::warning::Actions may not open PRs in this repository, so the sync PR was not opened.")
        _emit(f"::warning::The branch is pushed and ready: {hint}")
        return "the sync PR was not opened; see the warning above"


def apply_decision(
    api: GitHubApi,
    decision: SyncDecision,
    pulls: Sequence[Dict[str, Any]],
    body: str,
    head: str,
    base: str,
) -> str:
    """Perform the one write the decision calls for. Returns what was done."""
    if decision.action == ACTION_CREATE:
        return _open_pull(api, head, base, body)
    current = next((p.get("body") or "" for p in pulls if p.get("number") == decision.target), "")
    if BODY_MARKER not in current:
        return f"#{decision.target} was opened by hand; its body is left as written"
    if current == body:
        return f"#{decision.target} is already current; nothing written"
    update_pull_body(api, int(decision.target), body)
    return f"updated the body of #{decision.target}"


def _emit(text: str, *, err: bool = False) -> None:
    """The one place this module writes to a stream — a CI script's output is its product."""
    print(text, file=sys.stderr if err else sys.stdout)  # noqa: print


def run_sync(api: GitHubApi, head: str, base: str, dry_run: bool, source: Optional[str] = None) -> int:
    """Decide, build the body, and write at most one pull request."""
    source = source or head
    pulls = open_sync_pulls(api, {head, source}, base)
    ahead = commits_missing_from_base(api, head, base)
    decision = decide(pulls, ahead)
    _emit(f"release-sync: {decision.action}: {decision.reason}")
    if decision.action == ACTION_NOTHING:
        return 0
    body = build_body(ahead, scheduled_changes(api, head, base), source, base)
    if dry_run:
        _emit("release-sync: --dry-run, nothing written. The body would be:")
        _emit(body)
    else:
        _emit(f"release-sync: {apply_decision(api, decision, pulls, body, head, base)}")
    if decision.extras:
        listed = ", ".join(f"#{number}" for number in decision.extras)
        _emit(f"release-sync: duplicate sync PRs open, close by hand: {listed}", err=True)
        return 1
    return 0


def build_api() -> GitHubApi:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token:
        raise WatchdogConfigError("GITHUB_TOKEN is required")
    if "/" not in repository:
        raise WatchdogConfigError("GITHUB_REPOSITORY must be 'owner/repo'")
    api_root = os.environ.get("GITHUB_API_URL", DEFAULT_API_ROOT).strip() or DEFAULT_API_ROOT
    return GitHubApi(token, repository, api_root)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Open or update the one release-sync PR.")
    parser.add_argument("--head", default=DEFAULT_HEAD, help="the PR's head: the release branch")
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="the trunk the head copies")
    parser.add_argument("--base", default=DEFAULT_BASE, help="branch synced into")
    parser.add_argument("--dry-run", action="store_true", help="decide and print; write nothing")
    args = parser.parse_args(argv)
    try:
        return run_sync(build_api(), args.head, args.base, args.dry_run, args.source)
    except WatchdogError as exc:
        _emit(f"release-sync: {exc}", err=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
