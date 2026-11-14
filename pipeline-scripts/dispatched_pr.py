#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pull request a ``workflow_dispatch`` run stands for (#21577).

The branch sync leaves a pull request's head on a ``[skip ci]`` merge commit, and GitHub starts
no ``push`` / ``pull_request`` workflow for it. ``ci.yml``, ``no-commit-trailers.yml`` and
``pr-blocking-findings.yml`` therefore accept ``workflow_dispatch`` on the branch: the run is not
skipped by the marker and its check runs attach to the branch head, which is the commit a pull
request's required contexts are read from.

A dispatch carries no ``pull_request`` payload. This module is the ONE place that turns the
dispatched branch into the facts those workflows read from the payload, or REFUSES:

* the ref must be a branch, and not the default branch, ``release`` or a ``train-*`` branch;
* exactly one open pull request, from this repository, has the branch as its head, and its head
  is the dispatched commit;
* its base is the default branch (stacked and release pull requests are judged by their own
  event, not here);
* it is not a draft (the gates refuse a draft: ``draft: mark ready for review``);
* GitHub has a current test merge of it: the commit a ``pull_request`` run checks out, whose
  first parent is the base tip and whose second is the head. The suite scopes itself with
  ``HEAD^1`` / ``HEAD^2``, so a dispatched run checks out THAT commit (``checkout_ref``), never
  the branch head: a sync merge as the head would make ``HEAD^1`` the branch's own previous tip.

The hold for dependabot and the release promotion pull request is NOT decided here; ``ci.yml``'s
``hold`` step is its one definition and reads the facts this module outputs.

Everything untrusted (branch name, labels) arrives through the environment and leaves through
``$GITHUB_OUTPUT`` as single-line values.
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404  # gh, argv list, no shell
import sys
import time
from typing import Any, Callable

#: Merge-test polling: GitHub computes the test merge lazily, on the first read after a push.
MERGE_POLLS = int(os.environ.get("DISPATCH_MERGE_POLLS", "12"))
MERGE_POLL_SECONDS = int(os.environ.get("DISPATCH_MERGE_POLL_SECONDS", "10"))
RELEASE_BRANCH = "release"
TRAIN_PREFIX = "train-"

Api = Callable[..., Any]


class Refusal(Exception):
    """The dispatch does not stand for a pull request the suite may run; the message says why."""


def gh_api(path: str, **query: str) -> Any:
    """GET *path* through the ``gh`` CLI (token from ``GH_TOKEN``); a failure is a refusal, never an empty answer."""
    argv = ["gh", "api", "-X", "GET", path]
    for key, value in query.items():
        argv += ["-f", f"{key}={value}"]
    done = subprocess.run(argv, capture_output=True, text=True, check=False)  # nosec B603  # argv list, no shell
    if done.returncode != 0:
        detail = (done.stderr.strip().splitlines() or ["no output"])[0]
        raise Refusal(f"the GitHub API read of {path} failed ({detail}); an unreadable pull request does not pass")
    return json.loads(done.stdout)


def check_ref(ref_name: str, ref_type: str, default_branch: str) -> None:
    """Refuse anything but a feature branch: a dispatch there would run as something else."""
    if ref_type != "branch":
        raise Refusal(f"'{ref_name}' is a {ref_type or 'ref of unknown type'}, not a branch")
    if ref_name in (default_branch, RELEASE_BRANCH) or ref_name.startswith(TRAIN_PREFIX):
        raise Refusal(
            f"'{ref_name}' is the default, release or a merge-train branch: those run the suite on their own events,"
            " not by dispatch"
        )


def pick_pull(pulls: list[dict], repo: str, ref_name: str) -> dict:
    """The one open pull request from this repository whose head branch is *ref_name*."""
    own = [
        pull
        for pull in pulls
        if pull["head"]["ref"] == ref_name and (pull["head"].get("repo") or {}).get("full_name") == repo
    ]
    if not own:
        raise Refusal(f"no open pull request from this repository has '{ref_name}' as its head branch")
    if len(own) > 1:
        raise Refusal(f"{len(own)} open pull requests have '{ref_name}' as their head; refusing to guess which one")
    return own[0]


def refuse_unready_pull(pull: dict, sha: str, default_branch: str) -> None:
    """Refuse a pull request whose state the gates would not judge as a ready one."""
    if pull["state"] != "open":
        raise Refusal(f"pull request #{pull['number']} is not open")
    if pull["head"]["sha"] != sha:
        raise Refusal(f"the branch moved: dispatched {sha[:10]}, the pull request head is {pull['head']['sha'][:10]}")
    if pull["base"]["ref"] != default_branch:
        raise Refusal(f"pull request #{pull['number']} targets '{pull['base']['ref']}', not '{default_branch}'")
    if pull.get("draft"):
        raise Refusal(f"draft: pull request #{pull['number']} is a draft; mark it ready for review")


def current_merge(pull: dict, base_tip: str, parents_of: Callable[[str], list[str]]) -> str | None:
    """The test merge commit when current (parents: base tip, head); None while GitHub has not made it."""
    if pull.get("mergeable") is False:
        raise Refusal(f"pull request #{pull['number']} conflicts with its base; resolve it first")
    merge_sha = pull.get("merge_commit_sha")
    if pull.get("mergeable") is None or not merge_sha:
        return None
    if parents_of(merge_sha) != [base_tip, pull["head"]["sha"]]:
        return None
    return str(merge_sha)


def wait_for_merge(
    repo: str, number: int, sha: str, default_branch: str, api: Api, sleep: Callable
) -> tuple[dict, str, str]:
    """(pull request, its current test merge commit, the base tip) once GitHub has computed it."""

    def parents_of(merge_sha: str) -> list[str]:
        return [parent["sha"] for parent in api(f"repos/{repo}/commits/{merge_sha}")["parents"]]

    for attempt in range(MERGE_POLLS):
        pull = api(f"repos/{repo}/pulls/{number}")
        refuse_unready_pull(pull, sha, default_branch)
        base_tip = api(f"repos/{repo}/git/ref/heads/{default_branch}")["object"]["sha"]
        merge = current_merge(pull, base_tip, parents_of)
        if merge:
            return pull, merge, base_tip
        if attempt + 1 < MERGE_POLLS:
            sleep(MERGE_POLL_SECONDS)
    raise Refusal(f"no current test merge of pull request #{number} after {MERGE_POLLS} reads; dispatch again")


def outputs_for(pull: dict, merge_sha: str, base_tip: str) -> dict[str, str]:
    """The facts the workflows read from a ``pull_request`` payload, under the names they use."""
    return {
        "number": str(pull["number"]),
        "author": pull["user"]["login"],
        "head_ref": pull["head"]["ref"],
        "head_repo": pull["head"]["repo"]["full_name"],
        "head_sha": pull["head"]["sha"],
        "base_ref": pull["base"]["ref"],
        "base_sha": base_tip,
        "commits": str(pull["commits"]),
        "labels": json.dumps([label["name"] for label in pull.get("labels", [])]),
        "checkout_ref": merge_sha,
    }


def resolve_dispatched_pull(env: dict[str, str], api: Api = gh_api, sleep: Callable = time.sleep) -> dict[str, str]:
    """The outputs for the dispatched branch, or a :class:`Refusal`."""
    repo, ref_name, sha = env["REPO"], env["REF_NAME"], env["SHA"]
    default_branch = env["DEFAULT_BRANCH"]
    check_ref(ref_name, env.get("REF_TYPE", "branch"), default_branch)
    owner = repo.split("/")[0]
    pulls = api(f"repos/{repo}/pulls", state="open", head=f"{owner}:{ref_name}", per_page="100")
    number = pick_pull(pulls, repo, ref_name)["number"]
    pull, merge_sha, base_tip = wait_for_merge(repo, number, sha, default_branch, api, sleep)
    return outputs_for(pull, merge_sha, base_tip)


def write_outputs(outputs: dict[str, str], path: str) -> None:
    """Append ``key=value`` lines to the step-output file; a multi-line value could forge a second output."""
    with open(path, "a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            if "\n" in value or "\r" in value:
                raise Refusal(f"the {key} value spans lines and cannot be written as a step output")
            handle.write(f"{key}={value}\n")


def main() -> int:
    """Resolve the dispatched branch from the environment; print the refusal as an error annotation and exit 1."""
    try:
        outputs = resolve_dispatched_pull(dict(os.environ))
        write_outputs(outputs, os.environ["GITHUB_OUTPUT"])
    except Refusal as refusal:
        message = str(refusal).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        sys.stdout.write(f"::error title=dispatch refused::{message}\n")
        return 1
    merge = outputs["checkout_ref"][:10]
    sys.stdout.write(f"dispatch stands for pull request #{outputs['number']}; test merge {merge}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
