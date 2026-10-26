# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Merge main into every open same-repo PR branch and every PR-less branch (#19548).

Run by ``.github/workflows/sync-branches-with-main.yml`` from a full clone of main.
``git push`` authenticates with ``AUTOBOT_PUSH_TOKEN`` and nothing else, as a
``-c http...extraheader`` on the push argv only: ``main`` takes the token out of
``os.environ`` before the first git call, so no other git command, and no file in
``.git/``, ever holds it. The REST calls use ``GITHUB_TOKEN``. Every merge is
``--no-ff`` and its commit ends with `` [skip ci]``, so a sync costs zero CI. A merge that changes
``.github/workflows/*`` is pushed like any other; only a push GitHub refuses for
lack of the ``workflow`` scope is labelled.

Merge only, never rebase, never force: a plain ``git push`` that fails because the
branch moved is skipped and retried on the next run. A conflict is aborted and
labelled, never resolved. The decisions live in ``branch_sync_core``; this module
is the git and REST plumbing around them.
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import os
import subprocess  # nosec B404  # TimeoutExpired only; git runs through git_probe
import sys
import time
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(1, str(Path(__file__).resolve().parent.parent))
import branch_sync_core as core  # noqa: E402
from github_api import GitHubApi, WatchdogError, build_api  # noqa: E402

from autobot_shared.git_probe import run_git  # noqa: E402  # scrubbed-env git (#15783)

WORK_BRANCH = "__sync_work"
PUSH_TOKEN_ENV = "AUTOBOT_PUSH_TOKEN"
PUSH_HEADER_KEY = "http.https://github.com/.extraheader"
DEFAULT_RETRY_AFTER_SECONDS = 60
MAX_RATE_LIMIT_RETRIES = 3
PAGE_SIZE = 100
LABEL_COLOURS = {core.LABEL_CONFLICT: "d93f0b", core.LABEL_WORKFLOW: "fbca04"}

Runner = Callable[[Sequence[str]], Tuple[int, str]]

#: The ONE marker-comment upsert (#12984): reads every page, matches a Bot author plus the marker.
UPSERT_SCRIPT = Path(__file__).resolve().parent.parent / ".github/actions/upsert-pr-comment/upsert_pr_comment.py"


def load_upsert() -> Callable[..., Tuple[str, int]]:
    """``upsert_pr_comment.upsert``, loaded by path: a second copy here is what #12984 removed."""
    spec = importlib.util.spec_from_file_location("upsert_pr_comment", UPSERT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("upsert_pr_comment", module)
    spec.loader.exec_module(module)
    return module.upsert


class SyncApiError(WatchdogError):
    """A REST call this run needed did not succeed."""


def git_output(args: Sequence[str]) -> Tuple[int, str]:
    """``git <args>`` via the shared runner, stdin closed so no command eats another's input.

    The per-call timeout is ``AUTOBOT_GIT_PROBE_TIMEOUT_SECONDS``, raised by the workflow
    for merges and pushes on a full clone. A timeout is a failed call, not a crash.
    """
    try:
        proc = run_git(list(args), strict=False, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired as exc:
        return 124, f"git {_verb(args)} timed out after {exc.timeout}s"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _verb(args: Sequence[str]) -> str:
    """The subcommand words of *args*, past any ``-c key=value`` pair: never a header."""
    start = 0
    while start < len(args) and args[start] == "-c":
        start += 2
    return " ".join(args[start : start + 2])


def push_auth(token: str) -> Tuple[str, ...]:
    """The ``-c`` pair that authenticates ONE ``git push`` with *token*; empty without one."""
    if not token:
        return ()
    basic = base64.b64encode(f"x-access-token:{token}".encode("utf-8")).decode("ascii")
    return ("-c", f"{PUSH_HEADER_KEY}=AUTHORIZATION: basic {basic}")


def take_push_token(environ: Dict[str, str]) -> str:
    """Remove the PAT from *environ*, so no git subprocess inherits it, and return it."""
    return environ.pop(PUSH_TOKEN_ENV, "").strip()


class Git:
    """The git commands the sync runs. ``run`` is injected so tests record the argv.

    ``auth`` is the ``push_auth`` pair; it is prepended to the push argv and nothing else.
    """

    def __init__(self, run: Runner = git_output, auth: Sequence[str] = ()) -> None:
        self._run, self._auth = run, tuple(auth)

    def out(self, *args: str) -> Optional[str]:
        returncode, output = self._run(args)
        return output.strip() if returncode == 0 else None

    def branches(self) -> List[str]:
        listed = self.out("for-each-ref", "--format=%(refname:lstrip=3)", "refs/remotes/origin")
        return [line for line in (listed or "").splitlines() if line]

    def behind(self, branch: str, base: str) -> Optional[int]:
        count = self.out("rev-list", "--count", f"origin/{branch}..origin/{base}")
        return int(count) if count and count.isdigit() else None

    def checkout(self, branch: str) -> bool:
        return self._run(["checkout", "--quiet", "-B", WORK_BRANCH, f"origin/{branch}"])[0] == 0

    def merge(self, branch: str, base: str) -> Tuple[int, str]:
        # --no-ff: a branch with no commits of its own would otherwise fast-forward to
        # main's head, make no merge commit, carry no [skip ci], and start full CI.
        return self._run(["merge", "--no-ff", "--no-edit", "-m", core.merge_message(branch, base), f"origin/{base}"])

    def unmerged(self) -> List[str]:
        return (self.out("diff", "--name-only", "--diff-filter=U") or "").splitlines()

    def abort(self) -> None:
        self._run(["merge", "--abort"])

    def changed(self, old: str, new: str) -> Optional[List[str]]:
        listed = self.out("diff", "--name-only", old, new)
        return None if listed is None else listed.splitlines()

    def push(self, branch: str) -> Tuple[int, str]:
        # Plain push: rejected, never overwritten, if the branch moved since the fetch.
        return self._run([*self._auth, "push", "origin", f"HEAD:refs/heads/{branch}"])

    def touching(self, since: str, ref: str, path: str) -> List[Tuple[str, str]]:
        listed = self.out("log", "--format=%h%x1f%s", f"{since}..{ref}", "--", path) or ""
        return [tuple(line.split("\x1f", 1)) for line in listed.splitlines() if "\x1f" in line]


def _rate_limited(status: int, headers: Dict[str, str], body: Any) -> bool:
    if status not in (403, 429):
        return False
    message = str(body.get("message", "")) if isinstance(body, dict) else ""
    return "retry-after" in headers or "rate limit" in message.lower()


class SyncApi:
    """REST calls with secondary-rate-limit ``Retry-After`` honoured, and pagination."""

    def __init__(
        self,
        api: GitHubApi,
        sleep: Callable[[float], None] = time.sleep,
        upsert: Optional[Callable[..., Tuple[str, int]]] = None,
    ) -> None:
        self.api, self._sleep, self._labels_ready = api, sleep, set()
        self.repo = api.repository
        self._upsert = upsert or load_upsert()

    def call(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Tuple[int, Any]:
        for _ in range(MAX_RATE_LIMIT_RETRIES):
            status, body = self.api.request(method, path, payload)
            headers = getattr(self.api, "last_headers", {}) or {}
            if not _rate_limited(status, headers, body):
                return status, body
            wait = headers.get("retry-after", "")
            self._sleep(int(wait) if wait.isdigit() else DEFAULT_RETRY_AFTER_SECONDS)
        return self.api.request(method, path, payload)

    def paginate(self, path: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for page in range(1, 1000):
            sep = "&" if "?" in path else "?"
            status, body = self.call("GET", f"{path}{sep}per_page={PAGE_SIZE}&page={page}")
            if status != 200 or not isinstance(body, list):
                raise SyncApiError(f"cannot list {path} (HTTP {status}): {body}")
            items += body
            if len(body) < PAGE_SIZE:
                return items
        raise SyncApiError(f"{path}: more than 1000 pages")

    def open_pulls(self) -> List[Dict[str, Any]]:
        return self.paginate(f"/repos/{self.repo}/pulls?state=open&sort=created&direction=asc")

    def _expect(self, ok: Sequence[int], method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        status, body = self.call(method, path, payload)
        if status not in ok:
            raise SyncApiError(f"{method} {path} (HTTP {status}): {body}")
        return body

    def ensure_label(self, name: str) -> None:
        if name in self._labels_ready:
            return
        quoted = urllib.parse.quote(name, safe="")
        if self.call("GET", f"/repos/{self.repo}/labels/{quoted}")[0] == 404:
            payload = {"name": name, "color": LABEL_COLOURS[name], "description": "Set by the branch sync (#19548)"}
            self._expect((201, 422), "POST", f"/repos/{self.repo}/labels", payload)
        self._labels_ready.add(name)

    def upsert_comment(self, pr: int, marker: str, body: str) -> None:
        try:
            self._upsert(self.api.api_root, self.repo, pr, self.api.token, marker, body)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            raise SyncApiError(f"cannot upsert the sync comment on #{pr}: {exc}") from exc

    def add_label(self, pr: int, name: str) -> None:
        self._expect((200,), "POST", f"/repos/{self.repo}/issues/{pr}/labels", {"labels": [name]})

    def remove_label(self, pr: int, name: str) -> None:
        quoted = urllib.parse.quote(name, safe="")
        self._expect((200, 404), "DELETE", f"/repos/{self.repo}/issues/{pr}/labels/{quoted}")


MARKERS = {
    core.CONFLICT: (core.LABEL_CONFLICT, core.MARKER_CONFLICT),
    core.WORKFLOW: (core.LABEL_WORKFLOW, core.MARKER_WORKFLOW),
}


class Syncer:
    """Syncs one target at a time and returns ``(outcome, detail)``."""

    def __init__(self, git: Git, gh: SyncApi, base: str = "main", dry_run: bool = False) -> None:
        self.git, self.gh, self.base, self.dry_run = git, gh, base, dry_run

    def flag(self, target: core.SyncTarget, outcome: str, body: str) -> None:
        """One label and one marker-deduped comment; a PR-less branch is reported only."""
        label, marker = MARKERS[outcome]
        if self.dry_run or target.pr is None or label in target.labels:
            return
        self.gh.ensure_label(label)
        self.gh.upsert_comment(target.pr, marker, body)
        self.gh.add_label(target.pr, label)

    def clear(self, target: core.SyncTarget) -> None:
        if self.dry_run or target.pr is None:
            return
        for label in core.labels_to_clear(target.labels):
            self.gh.remove_label(target.pr, label)

    def histories(self, branch: str, files: Sequence[str]) -> Tuple[str, List[core.FileHistory]]:
        since = self.git.out("merge-base", f"origin/{self.base}", f"origin/{branch}") or ""
        base_ref, branch_ref = f"origin/{self.base}", f"origin/{branch}"
        return since, [
            core.FileHistory(path, self.git.touching(since, base_ref, path), self.git.touching(since, branch_ref, path))
            for path in files
        ]

    def on_conflict(self, target: core.SyncTarget) -> Tuple[str, str]:
        files = self.git.unmerged()
        self.git.abort()
        since, histories = self.histories(target.branch, files)
        self.flag(target, core.CONFLICT, core.conflict_comment(target.branch, self.base, since, histories))
        return core.CONFLICT, f"{len(files)} file(s)"

    def on_workflow(self, target: core.SyncTarget, paths: Sequence[str]) -> Tuple[str, str]:
        self.flag(target, core.WORKFLOW, core.workflow_comment(target.branch, self.base, paths))
        return core.WORKFLOW, "push refused" + (": " + ", ".join(paths) if paths else "")

    def precheck(self, target: core.SyncTarget) -> Tuple[Optional[str], str, str]:
        local = self.git.out("rev-parse", "--verify", "--quiet", f"origin/{target.branch}") or ""
        if not local:
            return core.UNREACHABLE, "not fetched", local
        if target.pr and target.head_sha and local != target.head_sha:
            return core.HEAD_MOVED, "PR head differs from the fetched ref", local
        behind = self.git.behind(target.branch, self.base)
        if behind is None:
            return core.UNREACHABLE, "behind-count failed", local
        if behind == 0:
            self.clear(target)
            return core.CURRENT, "already up to date", local
        return None, f"{behind} behind", local

    def merge(self, target: core.SyncTarget, local: str) -> Tuple[str, str]:
        if not self.git.checkout(target.branch):
            return core.UNREACHABLE, "checkout failed"
        returncode, output = self.git.merge(target.branch, self.base)
        kind = core.classify_merge(returncode, output, self.git.unmerged() if returncode else [])
        if kind == core.CONFLICT:
            return self.on_conflict(target)
        if kind == core.ERROR:
            self.git.abort()
            return core.ERROR, "merge failed without a conflict: " + (output.strip().splitlines() or ["no output"])[0]
        changed = self.git.changed(local, "HEAD")
        if changed is None:
            return core.ERROR, "cannot diff the merge result"
        return self.push(target, core.workflow_changes(changed))

    def push(self, target: core.SyncTarget, workflows: Sequence[str] = ()) -> Tuple[str, str]:
        """Push the merge; a workflow-file delta is named, and labelled only if GitHub refuses it."""
        note = f"workflow files: {', '.join(workflows)}" if workflows else ""
        if self.dry_run:
            return core.SYNCED, "; ".join(filter(None, ("dry run: not pushed", note)))
        returncode, output = self.git.push(target.branch)
        kind = core.classify_push(returncode, output)
        if kind == core.WORKFLOW:
            return self.on_workflow(target, workflows)
        if kind == core.SYNCED:
            self.clear(target)
            return kind, note
        return kind, (output.strip().splitlines() or ["no output"])[-1]

    def sync(self, target: core.SyncTarget) -> Tuple[str, str]:
        try:
            outcome, detail, local = self.precheck(target)
            return (outcome, detail) if outcome else self.merge(target, local)
        except SyncApiError as exc:
            return core.ERROR, str(exc)


def _emit(text: str) -> None:
    """The run log is stdout, read by a person in the Actions UI."""
    print(text, flush=True)  # noqa: print


def render_summary(results: Dict[str, List[str]], dry_run: bool) -> str:
    order = (core.SYNCED, core.CURRENT, core.CONFLICT, core.WORKFLOW, core.HEAD_MOVED, core.FORK)
    order += (core.OTHER_BASE, core.POLICY, core.UNREACHABLE, core.ERROR)
    lines = ["## Branch sync with main (#19548)", ""]
    if dry_run:
        lines += ["**Dry run: nothing was pushed, labelled or commented.**", ""]
    lines += ["| outcome | count |", "|---|---:|"] + [f"| {key} | {len(results.get(key, []))} |" for key in order]
    for key in order:
        if results.get(key):
            lines += ["", f"### {key}", ""] + [f"- {item}" for item in results[key]]
    return "\n".join(lines) + "\n"


def run(git: Git, gh: SyncApi, base: str, dry_run: bool) -> Dict[str, List[str]]:
    plan = core.plan_run(gh.open_pulls(), git.branches(), gh.repo, base)
    results: Dict[str, List[str]] = {key: list(items) for key, items in plan.skipped.items()}
    syncer = Syncer(git, gh, base, dry_run)
    for target in plan.targets:
        outcome, detail = syncer.sync(target)
        _emit(f"{outcome:>18}  {target.name}  {detail}")
        results.setdefault(outcome, []).append(f"{target.name}{' — ' + detail if detail else ''}")
    git.out("checkout", "--quiet", "--detach")
    return results


def exit_code(results: Dict[str, List[str]]) -> int:
    """A conflict is a reportable outcome; an error means this job did not do its work."""
    if results.get(core.ERROR):
        _emit(f"::error::{len(results[core.ERROR])} branch(es) failed for a reason that is NOT a conflict.")
        return 1
    attempted = sum(len(results.get(k, [])) for k in (core.SYNCED, core.CURRENT, core.CONFLICT, core.UNREACHABLE))
    if attempted and not results.get(core.SYNCED) and not results.get(core.CURRENT):
        _emit("::warning::no branch merged and none was already current: the shape of a broken merge step (#15938).")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="main")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    token = take_push_token(os.environ)
    if not token and not args.dry_run:
        _emit(f"::error::{PUSH_TOKEN_ENV} is empty; the sync pushes with it and nothing else (#19548).")
        return 1
    gh = SyncApi(build_api())
    try:
        results = run(Git(auth=push_auth(token)), gh, args.base, args.dry_run)
    except SyncApiError as exc:
        # Fail closed: an empty PR list would make every PR branch look parked.
        _emit(f"::error::cannot list open pull requests; refusing to run: {exc}")
        return 1
    summary = render_summary(results, args.dry_run)
    _emit(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write(summary)
    return exit_code(results)


if __name__ == "__main__":
    sys.exit(main())
