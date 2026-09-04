#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Report where the `umbrella` label and the native sub-issue relation disagree (#15440).

#15440's own title search could not tell an umbrella from an issue *about*
umbrellas (it matched #15440 itself), and it only ever found children recorded
as checklist rows (#15439's ``child_ref.py``), not the native GitHub sub-issue
relation. This reads that relation instead, in both directions:

* an issue that **holds sub-issues but lacks the label** -- AC2's finding, the
  one a title search cannot see because these issues need not mention
  "umbrella" anywhere in their title;
* an issue that **carries the label but holds no sub-issues** -- #15442's
  population, reported here because building the first check produces it for
  free, but left for that issue to fix.

## Why this reads ``sub_issues_summary`` and never calls ``/sub_issues``

``GET /repos/{owner}/{repo}/issues`` -- the plain, paginated issue *list* --
already carries a ``sub_issues_summary: {total, completed, percent_completed}``
per item, alongside ``labels``. That summary is GitHub's own aggregate over the
same native sub-issue graph ``/issues/{n}/sub_issues`` would return; it is not
a separate, weaker signal. This check only ever needs "is that total non-zero",
never the members of the child set, so one paginated list read answers both
directions for every issue in one pass -- no per-issue call, no N+1, no GraphQL
batching needed to avoid one. Verified against the live repository (2026-09-04):
774 open issues paged in 8 requests of 100, the full closed history in 78 more,
both trivial next to GitHub's 5000/hour authenticated ceiling.

## Why this is a script, not a pytest test

``scripts/`` is collected by ``ci.yml``'s pytest invocation, but this tool is
deliberately NOT a ``test_*.py``/``*_test.py`` module (see the sibling
``umbrella_label_drift_test.py`` for what actually runs there, against a fake
transport). Three reasons, not one:

* it needs a GitHub token the sandboxed unit-test run does not have;
* it queries live, mutable upstream state -- a label someone adds between two
  PRs changes this tool's answer without either PR having touched a line of
  code, which is exactly the kind of external flakiness a PR gate must not
  have;
* on this repository's ~8500 issues, even the cheap one-paginated-read design
  above is not "per-PR gate" cheap at CI's actual concurrency, and gating on
  outcomes a single PR cannot fix is a check nobody can act on.

It runs the same way ``backfill_relationships.py`` does (#15439): on demand or
on a schedule, as a CLI, reporting only -- it never edits a label. Labelling is
a write to shared state and stays a human decision.

## Where this lives, and why

``pipeline-scripts/`` is excluded from every Docker build context; ``scripts/``
ships. This tool needs the shared ``GitHubApi`` transport that already lives in
``pipeline-scripts/ci_dispatch_watchdog.py`` (reused, not re-implemented, for
the same reason ``backfill_relationships.py`` reuses it: one transport, one
place a failure becomes a status code -- #15411 tracks extracting it). That
makes this a shipped module importing an excluded one unless it is carved out
of the build context the same way ``backfill_relationships.py`` was for the
identical reason (#14127's ``test_no_shipped_module_imports_a_dockerignored_file``
catches exactly this); see the matching ``.dockerignore`` entry.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

# `pipeline-scripts` is not an importable package name, so the sibling module is
# reached by path -- the idiom `backfill_relationships.py` documents.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline-scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci_dispatch_watchdog import GitHubApi  # noqa: E402

# Plain stdlib logging, deliberately (#1082): this runs as a bare script, where
# autobot_shared.logging_manager would pull in config a CLI does not have.
logger = logging.getLogger(__name__)

UMBRELLA_LABEL = "umbrella"
PAGE_SIZE = 100
# 774 open issues page in 8 requests, the full ~7700-issue closed history in
# ~78 more -- both comfortably under this ceiling. Past it, the read is larger
# than the repository actually is and something about the response is wrong;
# a loud failure beats a silently truncated population, on the same principle
# `backfill_relationships.py`'s own MAX_PAGES documents.
MAX_PAGES = 200


class DriftError(RuntimeError):
    """Raised when a page read fails outright and the run must not report a partial population."""


@dataclass(frozen=True)
class Drift:
    """One population in each direction the label and the native relation can disagree."""

    missing_label: List[int]
    label_without_children: List[int]


def _paginate_issues(api: GitHubApi, state: str) -> Iterator[Dict[str, Any]]:
    """Yield every non-PR issue in ``state``, reading the list endpoint to exhaustion.

    The issue list endpoint also returns pull requests; those carry no
    ``sub_issues_summary`` worth reading and are filtered out here rather than
    by the caller.
    """
    for page in range(1, MAX_PAGES + 1):
        query = f"state={state}&per_page={PAGE_SIZE}&page={page}"
        status, body = api.request("GET", f"/repos/{api.repository}/issues?{query}")
        if status >= 400 or not isinstance(body, list):
            raise DriftError(f"GET issues page {page} (state={state}) returned {status}")
        for item in body:
            if "pull_request" not in item:
                yield item
        if len(body) < PAGE_SIZE:
            return
    raise DriftError(f"issue list exceeded {MAX_PAGES} pages (state={state}) -- refusing a partial read")


def _holds_sub_issues(issue: Dict[str, Any]) -> bool:
    """True if the native relation records at least one child for this issue."""
    summary = issue.get("sub_issues_summary") or {}
    total = summary.get("total")
    return isinstance(total, int) and total > 0


def _has_label(issue: Dict[str, Any], label: str) -> bool:
    return any(entry.get("name") == label for entry in issue.get("labels") or [])


def classify(issues: Iterable[Dict[str, Any]], label: str = UMBRELLA_LABEL) -> Drift:
    """Split a stream of issue payloads into the two drift directions."""
    missing_label: List[int] = []
    label_without_children: List[int] = []
    for issue in issues:
        number = issue.get("number")
        if not isinstance(number, int):
            continue
        has_children = _holds_sub_issues(issue)
        labelled = _has_label(issue, label)
        if has_children and not labelled:
            missing_label.append(number)
        elif labelled and not has_children:
            label_without_children.append(number)
    return Drift(missing_label=sorted(missing_label), label_without_children=sorted(label_without_children))


def scan(api: GitHubApi, states: Sequence[str], label: str = UMBRELLA_LABEL) -> Drift:
    """Classify every issue across every requested state in one merged population."""
    missing: List[int] = []
    without_children: List[int] = []
    for state in states:
        partial = classify(_paginate_issues(api, state), label)
        missing.extend(partial.missing_label)
        without_children.extend(partial.label_without_children)
    return Drift(missing_label=sorted(missing), label_without_children=sorted(without_children))


def _report_lines(drift: Drift, label: str) -> List[str]:
    lines = [f"{len(drift.missing_label)} issue(s) hold sub-issues but lack the `{label}` label:"]
    lines.extend(f"  #{n}" for n in drift.missing_label)
    lines.append(f"{len(drift.label_without_children)} issue(s) carry `{label}` but hold no sub-issues:")
    lines.extend(f"  #{n}" for n in drift.label_without_children)
    return lines


# Exit codes. A caller gating on "non-zero" must still be able to tell an
# actionable finding from a run that never read anything: a cron job that
# alerts on drift would otherwise page on a rate-limit exactly as it pages on
# an unlabelled umbrella, and the two need opposite responses. `scan` refuses
# to report a partial population, so EXIT_READ_FAILED means NOTHING was
# measured -- it is never a weaker form of EXIT_DRIFT_FOUND.
EXIT_CLEAN = 0
EXIT_DRIFT_FOUND = 1
EXIT_USAGE = 2
EXIT_READ_FAILED = 3


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--state", choices=("open", "closed", "all"), default="open")
    parser.add_argument("--label", default=UMBRELLA_LABEL)
    parser.add_argument("--json", action="store_true", help="emit machine-readable output instead of a report")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not token or not args.repo:
        logger.error("GH_TOKEN and --repo (or GITHUB_REPOSITORY) are required")
        return EXIT_USAGE

    api = GitHubApi(token=token, repository=args.repo)
    states = ("open", "closed") if args.state == "all" else (args.state,)
    try:
        drift = scan(api, states, args.label)
    except DriftError as exc:
        logger.error("refusing to report a partial population: %s", exc)
        return EXIT_READ_FAILED

    if args.json:
        payload = {"missing_label": drift.missing_label, "label_without_children": drift.label_without_children}
        logger.info("%s", json.dumps(payload))
    else:
        for line in _report_lines(drift, args.label):
            logger.info("%s", line)

    return EXIT_DRIFT_FOUND if drift.missing_label else EXIT_CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
