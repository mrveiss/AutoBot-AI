#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Answer "is this PR mergeable on its required contexts?" (#15995).

A status histogram cannot answer it. `pending=0, fail=0` is produced by three
different states:

    fully green                        -> mergeable
    CI has not started                 -> not mergeable, and nothing is wrong
    the branch conflicts with base     -> not mergeable, and something is wrong

A context that never ran contributes to no bucket, so its absence is invisible to
a count. Both non-green cases were observed on 2026-09-07: a PR read `pd=0 F=0`
with all ten required contexts unreported, and the cause turned out to be a merge
conflict -- for which `mergeStateStatus` reported `UNKNOWN` rather than `DIRTY`.

So the verdict is computed against the **required-contexts list read from branch
protection**, never a list carried here: a hardcoded population is one protection
change away from being wrong, and wrong in the direction that reports success.

Two reporting rules the exit code alone cannot carry, hence `--json`:

* `never-reported` and `not-green` are separate outputs. One means CI has not run,
  the other means it ran and disagreed with you. A single BLOCKED conflates a PR
  that needs waiting with one that needs work.
* the verdict names what it measured. This says `CONTEXTS-GREEN`, never
  `MERGEABLE`: it does not look at review threads, base-freshness, or conflicts,
  and a verdict labelled with more scope than it measured is read at the label.
  (#15994 was merged past three unresolved threads by an author whose own gate
  printed MERGEABLE having checked only contexts.)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Iterable

#: States a required context may hold and still not block a merge. `skipped` is a
#: real conclusion here: several contexts are published by path-filtered shims.
_ACCEPTABLE = frozenset({"success", "skipped", "neutral"})

#: Not a verdict -- the check is still running. Kept apart from `not_green` for the
#: same reason `never_reported` is: **a PR that needs waiting and a PR that needs
#: work are different problems**, and a reader who cannot tell them apart treats
#: both as "come back later" or both as "something is broken". The first version of
#: this tool put `pending` in `not_green`, committing the exact conflation it exists
#: to prevent, and it was caught by running it rather than by reading it.
_RUNNING = frozenset({"pending", "in_progress", "queued", "waiting", "requested"})


def latest_per_name(runs: Iterable[dict]) -> dict[str, str]:
    """Conclusion of the most recently *started* run for each context name.

    A superseded run is a real state, just not the current one: re-pushing leaves
    `cancelled` entries behind a later `success` for the same name, and taking the
    last element of an unordered API response reports a green context as failed.
    Sorting by `started_at` is what makes the answer current rather than arbitrary.
    """
    newest: dict[str, tuple[str, str]] = {}
    for run in runs:
        name = run.get("name") or run.get("context")
        if not name:
            continue
        started = run.get("started_at") or run.get("created_at") or ""
        state = run.get("conclusion") or run.get("state") or "pending"
        previous = newest.get(name)
        if previous is None or started >= previous[0]:
            newest[name] = (started, state)
    return {name: state for name, (_started, state) in newest.items()}


def _split_required(
    required: Iterable[str], observed: dict[str, str]
) -> tuple[list[str], list[dict[str, str]], list[dict[str, str]], list[str]]:
    """Sort every required context into never-reported / running / not-green / green."""
    never: list[str] = []
    running: list[dict[str, str]] = []
    not_green: list[dict[str, str]] = []
    green: list[str] = []
    for context in sorted(required):
        state = observed.get(context)
        if state is None:
            never.append(context)
        elif state in _ACCEPTABLE:
            green.append(context)
        elif state in _RUNNING:
            running.append({"context": context, "state": state})
        else:
            not_green.append({"context": context, "state": state})
    return never, running, not_green, green


def _required_result(never: list, running: list, not_green: list) -> str:
    """The verdict from the required contexts alone, before unrequired checks weigh in."""
    if not never and not running and not not_green:
        return "CONTEXTS-GREEN"
    if not_green or never:
        # `never` BLOCKS rather than pends, and the distinction is the whole point.
        # A context that has not reported is ambiguous between "has not started
        # yet" and "will never start" -- a branch conflicting with base produces
        # ZERO required contexts and waits forever. Only looking distinguishes
        # them, so the verdict must send someone to look.
        return "BLOCKED"
    # Every required context is running and none has disagreed: the answer is not
    # yet knowable. Distinct from BLOCKED so a caller can tell "wait" from "act"
    # without parsing lists.
    return "PENDING"


def _unrequired(
    observed: dict[str, str], required_set: set[str]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Checks outside branch protection, split into failing and still-running.

    A NON-REQUIRED check that is still running is not absent. Reporting only the
    failing ones made a PR read CONTEXTS-GREEN while eight `python-suite` shards
    were pending -- including the shard that had turned base red an hour earlier.
    An unfinished check cannot have failed yet, which is exactly why it must not
    be read as having passed.
    """

    def pick(predicate) -> list[dict[str, str]]:
        return sorted(
            (
                {"context": name, "state": state}
                for name, state in observed.items()
                if name not in required_set and predicate(state)
            ),
            key=lambda entry: entry["context"],
        )

    failing = pick(lambda state: state not in _ACCEPTABLE and state not in _RUNNING)
    return failing, pick(lambda state: state in _RUNNING)


def verdict(required: Iterable[str], observed: dict[str, str]) -> dict:
    """Split required contexts into never-reported, running, not-green, and green.

    Also reports checks that are FAILING BUT NOT REQUIRED. GitHub will merge past
    those, and this tool answering only "are the required contexts green" is a
    narrower question than "is this safe to merge" -- a distinction that nearly
    landed #15972 with three failing `python-suite` shards, because `python-suite`
    is not in branch protection's list. A failing test is a failing test whether or
    not a protection rule happens to name it, so it is surfaced rather than
    silently excluded from a verdict a reader will treat as a merge decision.
    """
    # Materialise ONCE. `required` is typed Iterable, and this function reads it
    # twice; a generator would be exhausted by the first read, so `set(required)`
    # would come back empty and every required context would be reclassified as
    # unrequired -- the failure mode this whole tool exists to catch, in the tool.
    required = list(required)
    never, running, not_green, green = _split_required(required, observed)
    result = _required_result(never, running, not_green)
    failing_unrequired, running_unrequired = _unrequired(observed, set(required))
    if running_unrequired and result == "CONTEXTS-GREEN" and not failing_unrequired:
        result = "GREEN-BUT-OTHERS-RUNNING"
    if failing_unrequired and result in ("CONTEXTS-GREEN", "GREEN-BUT-OTHERS-RUNNING"):
        # Honest naming: the required contexts really are green. The caller is not
        # clear to merge, and the verdict must not read as though they were.
        result = "GREEN-BUT-OTHERS-FAILING"
    return {
        "verdict": result,
        "never_reported": never,
        "running": running,
        "not_green": not_green,
        "green": green,
        "failing_unrequired": failing_unrequired,
        "running_unrequired": running_unrequired,
    }


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout


def _fetch(pr: int, repo: str, base: str) -> dict:
    protection = json.loads(_gh("api", f"repos/{repo}/branches/{base}/protection"))
    required = protection.get("required_status_checks", {}).get("contexts", [])
    head_json = _gh("pr", "view", str(pr), "--repo", repo, "--json", "headRefOid")
    head = json.loads(head_json)["headRefOid"]
    # Union of both kinds: some required contexts are legacy commit statuses, and
    # counting those as unreported is the mirror of the bug this tool exists for.
    runs_json = _gh("api", "--paginate", f"repos/{repo}/commits/{head}/check-runs")
    runs = json.loads(runs_json).get("check_runs", [])
    statuses = json.loads(_gh("api", f"repos/{repo}/commits/{head}/status")).get("statuses", [])
    return {"required": required, "observed": latest_per_name([*runs, *statuses]), "head": head}


def _emit(line: str) -> None:
    """Write one line of the verdict to stdout.

    stdout IS this tool's interface -- the verdict is read by `$(...)` in a
    sweep and by eye in a terminal, so a merge gate that logged its answer
    instead of printing it would not be a gate. The no-print rule is right for
    production code and wrong here, so the suppression lives once, in the only
    function that writes, rather than once per call site: one decision a
    reviewer can weigh, not a pattern that spreads by copy.
    """
    print(line)  # noqa: print


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pr", type=int)
    parser.add_argument("--repo", default="mrveiss/AutoBot-AI")
    parser.add_argument("--base", default="Dev_new_gui")
    parser.add_argument("--json", action="store_true", help="emit the full verdict as JSON")
    args = parser.parse_args(argv)

    fetched = _fetch(args.pr, args.repo, args.base)
    result = verdict(fetched["required"], fetched["observed"])
    result["head"] = fetched["head"]

    if args.json:
        _emit(json.dumps(result, indent=2))
    else:
        _emit(f"#{args.pr} {fetched['head'][:10]}  {result['verdict']}")
        for context in result["never_reported"]:
            _emit(f"  never-reported  {context}")
        for entry in result["running"]:
            _emit(f"  running         {entry['context']} = {entry['state']}")
        for entry in result["not_green"]:
            _emit(f"  not-green       {entry['context']} = {entry['state']}")
        for entry in result["failing_unrequired"]:
            _emit(f"  FAILING (not required)  {entry['context']} = {entry['state']}")
        for entry in result["running_unrequired"][:3]:
            _emit(f"  running (not required)  {entry['context']}")
    # PENDING and BLOCKED are both non-zero: neither is mergeable, and a caller
    # branching on the exit status alone must not read "wait" as "go".
    return 0 if result["verdict"] == "CONTEXTS-GREEN" else 1


if __name__ == "__main__":
    sys.exit(main())
