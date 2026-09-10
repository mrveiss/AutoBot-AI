# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""One answer to "what is the current state of each check on this SHA?" (#16120).

``GET /repos/{owner}/{repo}/commits/{sha}/check-runs`` answers a different
question than every caller asks it. It reports **what runs exist**; callers want
**what the state is**. Four ways that gap has produced a wrong verdict in this
repo, each silent and each in a different direction:

1. **Ungrouped reads invent failures.** The response carries every run on record,
   superseded ones included. Grouping one real response by name gave
   ``code-quality: failure, skipped`` and ``python-suite: failure, skipped`` --
   three of five reported failures had a later run. A phantom red costs the same
   investigation as a real one.

2. **``per_page=100`` without pagination hides them.** Measured on one PR: 100
   runs on a single page, 111 paginated. The eleven dropped were concealing a
   genuinely not-green required context (``cancelled startup-import-smoke``).

3. **A skip can land after a failure.** Two workflows publishing one context name
   -- a path-filtered shim writing ``skipped`` after a real ``failure`` -- make
   newest-wins report green while the merge button stays red (#16040).

4. **``gh pr list --json statusCheckRollup`` reports superseded commits.** The
   rollup retains runs from earlier head SHAs, so a PR whose current head is
   clean can be reported as failing. Observed twice on 2026-09-09, on #16106 and
   #16149, by two sessions independently.

(1) and (3) invent reds, (2) and (4) hide them. All four are invisible without
comparing against a second reading, which is why this is one helper rather than
advice.

Use :func:`check_run_status` unless you specifically need the raw runs.
"""

from __future__ import annotations

import json
import subprocess
from typing import Iterable

#: A conclusion that does not block. `skipped` and `neutral` are here because
#: several contexts are published by path-filtered shims that legitimately
#: decline to run.
ACCEPTABLE = frozenset({"success", "skipped", "neutral"})

#: Not a verdict -- still running. Kept apart from failing because **a PR that
#: needs waiting and a PR that needs work are different problems**, and a reader
#: who cannot tell them apart treats both as "come back later".
RUNNING = frozenset({"pending", "in_progress", "queued", "waiting", "requested"})

#: "This publisher declined to run here" -- acceptable as a FINAL answer for a
#: context nothing else reported, never as an override of one that did.
INCONCLUSIVE = frozenset({"skipped", "neutral"})

#: Precedence when two SOURCES report one context name. Lower is worse; the
#: worst observation wins, so a green never stands in for a red.
SEVERITY = {"failing": 0, "running": 1, "acceptable": 2}


def rank(state: str) -> str:
    """Coarse class of a conclusion: acceptable, running, or failing."""
    if state in ACCEPTABLE:
        return "acceptable"
    return "running" if state in RUNNING else "failing"


def _latest_within(observations: Iterable[dict]) -> dict[str, str]:
    """Conclusion of the most recently *started* observation for each name.

    A superseded run is a real state, just not the current one. Taking the last
    element of an unordered response reports a green context as failed; sorting
    by ``started_at`` is what makes the answer current rather than arbitrary.

    A skip never overrides a conclusive result (#16040) -- newest-wins is right
    for supersession and wrong for two publishers sharing one context name.
    """
    newest: dict[str, tuple[str, str]] = {}
    for run in observations:
        name = run.get("name") or run.get("context")
        if not name:
            continue
        started = run.get("started_at") or run.get("created_at") or ""
        state = run.get("conclusion") or run.get("state") or "pending"
        previous = newest.get(name)
        if previous is None:
            newest[name] = (started, state)
            continue
        if state in INCONCLUSIVE and previous[1] not in INCONCLUSIVE:
            continue
        if previous[1] in INCONCLUSIVE and state not in INCONCLUSIVE:
            newest[name] = (started, state)
            continue
        if started >= previous[0]:
            newest[name] = (started, state)
    return {name: state for name, (_started, state) in newest.items()}


def latest_per_name(*sources: Iterable[dict]) -> dict[str, str]:
    """Current state per context name: newest WITHIN a source, worst ACROSS them.

    The two rules answer different failures and neither substitutes for the
    other. *Newest within* handles supersession. *Worst across* handles masking:
    GitHub evaluates check runs and legacy commit statuses as separate
    requirements, so one dict keyed by name alone lets a passing observation of
    one kind hide a failing observation of the other.

    Called with one source it behaves as a plain latest-per-name, so a caller
    that has only check runs does not have to know about any of this.
    """
    merged: dict[str, str] = {}
    for observations in sources:
        for name, state in _latest_within(observations).items():
            current = merged.get(name)
            if current is None or SEVERITY[rank(state)] < SEVERITY[rank(current)]:
                merged[name] = state
    return merged


def latest_runs(observations: Iterable[dict]) -> list[dict]:
    """The surviving run OBJECT per name, applying the same rules as
    :func:`latest_per_name`.

    :func:`latest_per_name` answers "what is the state", which is enough for a
    gate. A caller that must then INSPECT the run -- read its job id, its steps,
    its url -- needs the object that won, not its conclusion. Returning the
    conclusion and making the caller re-find its run is how a caller ends up
    re-deriving the grouping, or skipping it.
    """
    winners: dict[str, dict] = {}
    for run in observations:
        name = run.get("name") or run.get("context")
        if not name:
            continue
        previous = winners.get(name)
        if previous is None:
            winners[name] = run
            continue
        state = run.get("conclusion") or run.get("state") or "pending"
        prev_state = previous.get("conclusion") or previous.get("state") or "pending"
        if state in INCONCLUSIVE and prev_state not in INCONCLUSIVE:
            continue
        if prev_state in INCONCLUSIVE and state not in INCONCLUSIVE:
            winners[name] = run
            continue
        started = run.get("started_at") or run.get("created_at") or ""
        prev_started = previous.get("started_at") or previous.get("created_at") or ""
        if started >= prev_started:
            winners[name] = run
    return list(winners.values())


def all_pages(endpoint: str, key: str | None = None) -> list[dict]:
    """Every page of a paginated endpoint, flattened.

    ``--paginate`` alone concatenates one JSON document PER PAGE, which
    ``json.loads`` rejects outright -- so a tool using it works only while every
    list fits in one page and then dies, rather than degrading, the day it does
    not. ``--slurp`` makes the pages one array.
    """
    raw = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", endpoint],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    pages = json.loads(raw)
    if key is None:
        return [item for page in pages for item in page]
    return [item for page in pages for item in page.get(key, [])]


def check_runs_for(repository: str, sha: str) -> list[dict]:
    """Every check run on ``sha``, across all pages. Raw, ungrouped."""
    endpoint = f"/repos/{repository}/commits/{sha}/check-runs?per_page=100"
    return all_pages(endpoint, key="check_runs")


def check_run_status(repository: str, sha: str) -> dict[str, str]:
    """Current state of each check on ``sha`` -- paginated and latest-per-name.

    This is the function to call. It answers "what is the state of each check",
    which is the question callers actually have, rather than "what runs exist".

    Returns a mapping of context name to conclusion. A name absent from the
    result was **never reported**, which is a different state from reported and
    not green -- see :func:`split_by_state`.
    """
    return latest_per_name(check_runs_for(repository, sha))


def split_by_state(observed: dict[str, str], expected: Iterable[str]) -> dict[str, list[str]]:
    """Sort expected context names into never_reported / running / failing / green.

    ``never_reported`` is kept apart deliberately. A context nothing published is
    not a passing context and not a failing one; collapsing it into either is how
    a merge gate reports a green it did not earn.
    """
    buckets: dict[str, list[str]] = {
        "never_reported": [],
        "running": [],
        "failing": [],
        "green": [],
    }
    for name in sorted(expected):
        state = observed.get(name)
        if state is None:
            buckets["never_reported"].append(name)
        elif rank(state) == "running":
            buckets["running"].append(name)
        elif rank(state) == "acceptable":
            buckets["green"].append(name)
        else:
            buckets["failing"].append(name)
    return buckets
