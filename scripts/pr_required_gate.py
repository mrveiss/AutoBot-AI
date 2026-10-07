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
    RUNNING,
    all_pages,
    check_runs_for,
    latest_per_name,
)

#: Local aliases onto the shared vocabulary, so the rest of this module reads
#: unchanged. The definitions live in scripts/lib/check_run_status.py -- one
#: place where "what counts as green" is decided. Only the two this module still
#: reads are aliased; the rest were used solely by the grouping logic that moved.
_ACCEPTABLE = ACCEPTABLE
_RUNNING = RUNNING

#: Verdict reserved for a PR that is not open. Carried as a name because it is
#: the one verdict that takes a detail suffix -- `NOT-OPEN (MERGED)` -- and a
#: suffixed string is not a member of :data:`VERDICTS` by equality.
NOT_OPEN = "NOT-OPEN"

#: Verdict reserved for a PR that is still a draft. This is the SIXTH blind
#: spot (the module docstring said to assume one), and it is the first that was
#: found by the verdict being believed: this gate reported `CONTEXTS-GREEN` on
#: #17962 -- 29 success, 23 skipped, 0 failures -- and the merge API answered
#: `405 Pull Request is still a draft`.
#:
#: The reason it reads green is that draft is how this repository PARKS a run:
#: `ci.yml` and `code-quality.yml` gate their heavy jobs on
#: `github.event.pull_request.draft == false`, so on a draft the required
#: contexts publish `skipped` -- and `skipped` is in
#: :data:`~scripts.lib.check_run_status.ACCEPTABLE` because a path-filtered
#: shim declining to run is genuinely not a blocker. Same conclusion string,
#: opposite meaning: one says "this job had nothing to do here", the other says
#: "this job has not been allowed to start yet". Nothing in a check-run
#: conclusion distinguishes them, which is why draft is read from the PR and
#: not inferred from the contexts.
DRAFT = "DRAFT"

#: Verdict for "branch protection named no required contexts at all". The
#: SEVENTH blind spot, and the one that proves the point made at :func:`_fetch`:
#: `verdict([], {})` returned `CONTEXTS-GREEN` and exit 0, because zero
#: contexts trivially satisfies "none is failing". A gate whose requirement
#: list failed to load therefore cleared every PR, and the output said GREEN
#: with no row to contradict it.
#:
#: It is reachable without anything breaking: this tool reads CLASSIC branch
#: protection, and a repository that moves its required checks into a RULESET
#: keeps a valid protection object with an empty `contexts`. Measured on this
#: repository on 2026-10-07: classic protection carries all 11, and the two
#: active rulesets declare no `required_status_checks` -- so the list is read
#: from the right place TODAY. That is a fact about configuration, not about
#: this code, and it is exactly the kind of fact that changes without the code
#: changing. Hence a verdict rather than a comment.
NO_REQUIREMENTS = "NO-REQUIREMENTS"

#: THE verdict vocabulary -- every string this tool can print as a verdict
#: (#16044 AC3/AC4).
#:
#: The tool's history is five blind spots found one at a time, each fixed by
#: adding a case, and the module docstring says to assume a sixth. What that
#: history makes cheap is adding a case **without saying so**: a new
#: `return "GREEN-SOMETHING"` reads as a refinement of an existing green and
#: joins the merge-clearing answers unannounced. A reader cannot tell the set
#: apart from the literals unless the set is written down.
#:
#: So the set is declared, :func:`declared` is the only producer, and
#: `pr_required_gate_test.py` fails on any verdict string that reaches the
#: output without passing through here. Adding a condition is therefore a
#: two-line diff -- the branch and its entry -- rather than one line absorbed
#: into a function nobody re-reads.
VERDICTS = frozenset(
    {
        "CONTEXTS-GREEN",
        "GREEN-BUT-OTHERS-RUNNING",
        "GREEN-BUT-OTHERS-FAILING",
        "PENDING",
        "BLOCKED",
        NOT_OPEN,
        DRAFT,
        NO_REQUIREMENTS,
    }
)

#: The subset that means "nothing this tool examined objects". Named rather than
#: inferred from the `GREEN` substring: `GREEN-BUT-OTHERS-FAILING` contains it
#: and is the opposite of clearance, so matching on the word is how a failing
#: verdict gets counted as a passing one.
CLEARING_VERDICTS = frozenset({"CONTEXTS-GREEN"})

#: Exit status for "this tool could not reach a verdict at all" -- deliberately
#: NOT 1. Every verdict in :data:`VERDICTS` that is not clearing exits 1, so an
#: operational failure exiting 1 too is indistinguishable from `BLOCKED`, and
#: the wrapper said "NOT clear to merge ... verdict above" when there was no
#: verdict above. That is this tool's own thesis turned on itself: an error
#: wearing the shape of a measurement.
#:
#: 2 rather than a new verdict on purpose. `pr-merge-gate.sh` already exits 2
#: for "could not ask" (gh unqueryable, detached HEAD, no open PR), so the
#: caller's vocabulary is already 0=green / 1=judged-and-not-green /
#: 2=unknown. An operational failure is the ABSENCE of a verdict, so it must
#: not enter :data:`VERDICTS` -- a reader who sees it listed there would
#: reasonably ask which contexts produced it.
EXIT_GATE_ERROR = 2

#: What a failed `gh` or a malformed response actually raises. Named and narrow:
#: a bare `except Exception` here would convert a genuine bug in the verdict
#: logic into a tidy "could not reach a verdict", which is the same substitution
#: of a plausible answer for a real one that the narrow list avoids.
GATE_ERRORS = (subprocess.CalledProcessError, json.JSONDecodeError, KeyError, OSError)


def declared(verdict: str, detail: str = "") -> str:
    """Stamp a verdict, refusing one that is not in :data:`VERDICTS`.

    Every verdict string this module emits is produced here, which is what makes
    the set above the whole set rather than a list of the ones someone
    remembered. An undeclared verdict raises at the moment it is produced: a
    gate that invented a state is not a gate whose exit code should be read.
    """
    if verdict not in VERDICTS:
        raise ValueError(
            f"undeclared verdict {verdict!r} -- add it to VERDICTS (#16044), " f"or use one of {sorted(VERDICTS)}"
        )
    return f"{verdict} ({detail})" if detail else verdict


def base_verdict(verdict: str) -> str:
    """The declared token inside a verdict string, detail suffix stripped."""
    return verdict.split(" (", 1)[0]


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


def _required_result(never: list, running: list, not_green: list, required_count: int) -> str:
    """The verdict from the required contexts alone, before unrequired checks weigh in."""
    # BEFORE the green branch, because it is the green branch that it defeats.
    # With no requirements, all three lists are empty and "nothing is failing"
    # is true of nothing -- the one arrangement where the happy path is reached
    # by the requirement list having failed to load.
    if required_count == 0:
        return declared(NO_REQUIREMENTS)
    if not never and not running and not not_green:
        return declared("CONTEXTS-GREEN")
    if not_green or never:
        # `never` BLOCKS rather than pends, and the distinction is the whole point.
        # A context that has not reported is ambiguous between "has not started
        # yet" and "will never start" -- a branch conflicting with base produces
        # ZERO required contexts and waits forever. Only looking distinguishes
        # them, so the verdict must send someone to look.
        return declared("BLOCKED")
    # Every required context is running and none has disagreed: the answer is not
    # yet knowable. Distinct from BLOCKED so a caller can tell "wait" from "act"
    # without parsing lists.
    return declared("PENDING")


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
        return declared("GREEN-BUT-OTHERS-FAILING")
    if running_unrequired and result == "CONTEXTS-GREEN":
        return declared("GREEN-BUT-OTHERS-RUNNING")
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
    result = _required_result(never, running, not_green, len(required))
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
    #
    # The fifth was a draft PR (see :data:`DRAFT`), and it is read on the next
    # line from the same call rather than in a second one. Worth stating because
    # the prediction above was correct and still did not prevent it: knowing a
    # blind spot exists does not locate it. What located this one was a verdict
    # being ACTED on -- the gate said green and the merge API said draft. So the
    # cheapest detector for the sixth is not more enumeration here, it is keeping
    # every clearing verdict falsifiable by something downstream that can say no.
    head_json = _gh("pr", "view", str(pr), "--repo", repo, "--json", "headRefOid,state,isDraft")
    head_data = json.loads(head_json)
    head = head_data["headRefOid"]
    pr_state = head_data.get("state", "OPEN")
    # Defaulting to True would fail closed, which is the safer direction for a
    # merge gate -- but it would also report DRAFT for every PR the moment the
    # field is renamed, and a gate that blocks everything gets switched off
    # rather than fixed. False keeps the old behaviour on a missing field and
    # the absence is visible: `is_draft` is reported, so a reader sees the
    # claim being made. The field is part of `gh pr view`'s documented schema.
    is_draft = bool(head_data.get("isDraft", False))
    # BOTH kinds, kept as SEPARATE sources. Some required contexts are legacy
    # commit statuses, and counting those as unreported is the mirror of the bug
    # this tool exists for -- but merging them into one list lets a green check
    # run hide a red status of the same name, which is that bug itself.
    # `/statuses` (plural) paginates; `/status` (singular) silently caps at 30,
    # and a required status past the cap reads as never-reported.
    # The check-runs endpoint is spelled ONCE, in the shared helper (#16120).
    # This line used to build it here -- importing the grouping rules and then
    # hand-rolling the query they are about, which is the shape the helper
    # exists to remove. `/statuses` has no helper because nothing else reads
    # it; it stays on the shared paginator.
    runs = check_runs_for(repo, head)
    statuses = _all_pages(f"repos/{repo}/commits/{head}/statuses?per_page=100")
    return {
        "required": required,
        "app_pinned": app_pinned,
        "observed": latest_per_name(runs, statuses),
        "head": head,
        "pr_state": pr_state,
        "is_draft": is_draft,
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
    if base_verdict(result["verdict"]) == NO_REQUIREMENTS:
        _emit("  branch protection named NO required contexts, so there was nothing")
        _emit("  to check. This is not a pass. Either protection is misconfigured, or")
        _emit("  the requirements moved to a ruleset, which this tool does not read.")
        return
    if result.get("is_draft", False):
        _emit("  it is a DRAFT: the heavy jobs are gated on `draft == false`, so the")
        _emit("  required contexts below read `skipped` because they have not been")
        _emit("  allowed to run -- not because they had nothing to do. Mark it ready")
        _emit("  for review, let the suite run, and read the verdict again.")
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
    parser.add_argument("--base", default="main")
    parser.add_argument("--json", action="store_true", help="emit the full verdict as JSON")
    args = parser.parse_args(argv)

    try:
        fetched = _fetch(args.pr, args.repo, args.base)
    except GATE_ERRORS as exc:
        # NOT a verdict, and deliberately not phrased as one: no `declared()`
        # call, nothing assigned to result["verdict"], and the word GREEN does
        # not appear. The contract test's escape detector watches `return
        # "<string>"` and `result["verdict"] = "<string>"`; this path uses
        # neither, because what it reports is that no verdict exists.
        _emit(f"#{args.pr} GATE-ERROR  could not reach a verdict: {type(exc).__name__}: {exc}")
        _emit("  This is NOT 'not clear to merge' -- nothing was measured. Re-run,")
        _emit("  or check `gh auth status` and that the PR and base branch exist.")
        return EXIT_GATE_ERROR
    result = verdict(fetched["required"], fetched["observed"])
    result["head"] = fetched["head"]
    result["pr_state"] = fetched.get("pr_state", "OPEN")
    # A closed or merged PR is not a mergeable one, whatever its contexts say.
    # Overriding AFTER `verdict()` rather than short-circuiting before the fetch
    # keeps the context detail in `--json` for anyone auditing why it looked green.
    result["is_draft"] = fetched.get("is_draft", False)
    if result["pr_state"] != "OPEN":
        result["verdict"] = declared(NOT_OPEN, result["pr_state"])
    # AFTER the state override and never before it: a closed draft is both, and
    # `NOT-OPEN (CLOSED)` is the more final answer -- telling someone to undraft
    # a PR that is closed sends them to the wrong fix. `elif` rather than a
    # combined condition so the precedence is visible instead of implied.
    elif result["is_draft"]:
        result["verdict"] = declared(DRAFT)
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
    return 0 if base_verdict(result["verdict"]) in CLEARING_VERDICTS else 1


if __name__ == "__main__":
    sys.exit(main())
