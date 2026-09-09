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
from pathlib import Path
from typing import Iterable

# The grouping and pagination rules live in scripts/lib/check_run_status.py
# (#16120). They were proven here first; keeping a second copy means two
# implementations that must be kept in sync by hand, which is how the naive
# query gets written again by whoever reads only one of them.
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from check_run_status import (  # noqa: E402
    ACCEPTABLE,
    INCONCLUSIVE,
    RUNNING,
    SEVERITY,
    all_pages,
    latest_per_name,
    rank,
)

#: States a required context may hold and still not block a merge. `skipped` is a
#: Local aliases onto the shared vocabulary, so the rest of this module reads
#: unchanged. The definitions live in scripts/lib/check_run_status.py -- one
#: place where "what counts as green" is decided.
_ACCEPTABLE = ACCEPTABLE
_RUNNING = RUNNING
_INCONCLUSIVE = INCONCLUSIVE
_SEVERITY = SEVERITY
_rank = rank


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


def _unrequired(observed: dict[str, str], required_set: set[str]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
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


def _qualify(result: str, failing_unrequired: list, running_unrequired: list) -> str:
    """Green on the required contexts is not the same as clear to merge.

    Honest naming: the required contexts really are green, and the caller is not
    clear to merge. A verdict that read CONTEXTS-GREEN with three failing shards
    would be read at the label -- which is how #15972 nearly landed.
    """
    if failing_unrequired and result in ("CONTEXTS-GREEN", "GREEN-BUT-OTHERS-RUNNING"):
        return "GREEN-BUT-OTHERS-FAILING"
    if running_unrequired and result == "CONTEXTS-GREEN":
        return "GREEN-BUT-OTHERS-RUNNING"
    return result


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
    result = _qualify(result, failing_unrequired, running_unrequired)
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


def _all_pages(endpoint: str, key: str | None = None) -> list[dict]:
    """Shim onto the shared paginator (#16120), kept so callers here read the same."""
    return all_pages(endpoint, key)


def _required_contexts(protection: dict) -> tuple[list[str], list[str]]:
    """Required context names, plus those pinned to a specific app.

    `contexts` is the deprecated mirror of `checks`, and a protection rule can
    name a context that only counts when a PARTICULAR app publishes it. This
    tool matches on name alone, so it cannot enforce that pinning -- and the
    honest response is to name the ones it cannot verify rather than to report
    a green it did not earn. Reading only `contexts` would additionally MISS a
    requirement declared solely under `checks`, which is the mirror of the bug
    this tool exists for: a requirement invisible to the instrument reads as
    satisfied.
    """
    required_block = protection.get("required_status_checks", {})
    checks = required_block.get("checks", [])
    names = sorted({*required_block.get("contexts", []), *(c["context"] for c in checks)})
    app_pinned = sorted(c["context"] for c in checks if c.get("app_id") is not None)
    return names, app_pinned


def _fetch(pr: int, repo: str, base: str) -> dict:
    protection = json.loads(_gh("api", f"repos/{repo}/branches/{base}/protection"))
    required, app_pinned = _required_contexts(protection)
    # STATE FIRST. A merged or closed PR reports every required context green,
    # because its checks completed before it landed -- so the verdict is true and
    # useless. Read as clearance it says "ready to merge" about something already
    # merged; I did exactly that and told another session to merge alongside
    # three PRs that had landed hours earlier (#16040).
    #
    # This is the fourth state this tool could not see, and they are not four
    # bugs: pending contributing to no bucket, a conflicted PR producing no runs,
    # a superseded `cancelled`, and now a merged PR. One design property --
    # **a check that enumerates conditions is blind to the conditions it does not
    # enumerate, and every blind spot reads as success.** The corollary is what
    # this comment is for: assume there is a fifth.
    head_json = _gh("pr", "view", str(pr), "--repo", repo, "--json", "headRefOid,state")
    head_data = json.loads(head_json)
    head = head_data["headRefOid"]
    pr_state = head_data.get("state", "OPEN")
    # BOTH kinds, kept as SEPARATE sources. Some required contexts are legacy
    # commit statuses, and counting those as unreported is the mirror of the bug
    # this tool exists for -- but merging them into one list lets a green check
    # run hide a red status of the same name, which is that bug itself.
    # `/statuses` (plural) paginates; `/status` (singular) silently caps at 30,
    # and a required status past the cap reads as never-reported.
    runs = _all_pages(f"repos/{repo}/commits/{head}/check-runs?per_page=100", "check_runs")
    statuses = _all_pages(f"repos/{repo}/commits/{head}/statuses?per_page=100")
    return {
        "required": required,
        "app_pinned": app_pinned,
        "observed": latest_per_name(runs, statuses),
        "head": head,
        "pr_state": pr_state,
    }


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


#: Merge preconditions this tool does NOT examine, named in every verdict.
#:
#: Five states have now been found by discovering them one at a time: pending
#: contributing to no bucket, a conflicted PR producing no runs, a superseded
#: `cancelled`, a merged PR reading green, and a skip outranking a failure. Each
#: was fixed by adding a case. **Adding cases does not change the property that
#: produced them** -- a check that enumerates conditions is blind to the
#: conditions it does not enumerate, and every blind spot reads as success.
#:
#: So the verdict says what it did not look at. That does not make the tool
#: complete; it makes its incompleteness visible, which is the only part a
#: reader can act on. A verdict that cannot say "I do not know what I did not
#: examine" spends its blind spots as green (#16044).
#:
#: Add to this list when a precondition is identified, whether or not it is
#: implemented. An unimplemented check that is NAMED costs a reader one glance;
#: an unimplemented check that is silent costs them the incident.
NOT_EXAMINED = (
    "review threads — an unresolved thread blocks merge and is not read here",
    "base freshness — not required by protection (`strict` is false), but a stale "
    "branch may still fail a check it would pass rebased",
    "branch conflicts — a conflicted PR produces NO runs, which reads identically " "to 'CI has not started'",
    "app pinning — a required context can be pinned to one publisher; matched by name only",
)


def _report(pr: int, result: dict) -> None:
    """Render the verdict as text: every non-green context, none of them elided."""
    _emit(f"#{pr} {result['head'][:10]}  {result['verdict']}")
    if result.get("pr_state", "OPEN") != "OPEN":
        _emit("  its required contexts read green because they completed before it landed")
        return
    for context in result["never_reported"]:
        _emit(f"  never-reported  {context}")
    for entry in result["running"]:
        _emit(f"  running         {entry['context']} = {entry['state']}")
    for entry in result["not_green"]:
        _emit(f"  not-green       {entry['context']} = {entry['state']}")
    for entry in result["failing_unrequired"]:
        _emit(f"  FAILING (not required)  {entry['context']} = {entry['state']}")
    # Every one, with its state. The `[:3]` this replaces was the tool's own
    # defect in miniature: a display that silently drops rows reports a
    # shorter list of blockers than exists, which is exactly the reading
    # error -- "nothing else is running" -- that `running_unrequired` was
    # added to prevent. A cap here would need to announce itself; none does.
    for entry in result["running_unrequired"]:
        _emit(f"  running (not required)  {entry['context']} = {entry['state']}")
    # ONE line, not one per context. Every required context on this repository
    # pins an app_id, so a per-context notice would print ten identical rows on
    # every run and bury the rows that differ. A boundary stated once is read;
    # a boundary repeated on every line is skipped, which leaves it as
    # undeclared in practice as saying nothing.
    pinned = result.get("app_pinned", [])
    if pinned:
        _emit(f"  note: {len(pinned)} required context(s) pin an app_id; matched by name only")
    # Printed on EVERY verdict, including a green one. A boundary shown only on
    # failure is absent exactly when someone is about to act on the good news.
    _emit("  NOT EXAMINED by this tool:")
    for item in NOT_EXAMINED:
        _emit(f"    - {item}")


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
    result["pr_state"] = fetched.get("pr_state", "OPEN")
    # A closed or merged PR is not a mergeable one, whatever its contexts say.
    # Overriding AFTER `verdict()` rather than short-circuiting before the fetch
    # keeps the context detail in `--json` for anyone auditing why it looked green.
    if result["pr_state"] != "OPEN":
        result["verdict"] = f"NOT-OPEN ({result['pr_state']})"
    # Carried into the output rather than dropped: branch protection can require a
    # context only when a PARTICULAR app publishes it, and matching on name alone
    # cannot check that. Saying so is the difference between a verdict with a
    # stated boundary and one that quietly answers a narrower question.
    result["app_pinned"] = fetched.get("app_pinned", [])

    if args.json:
        _emit(json.dumps(result, indent=2))
    else:
        _report(args.pr, result)
    # PENDING and BLOCKED are both non-zero: neither is mergeable, and a caller
    # branching on the exit status alone must not read "wait" as "go".
    return 0 if result["verdict"] == "CONTEXTS-GREEN" else 1


if __name__ == "__main__":
    sys.exit(main())
