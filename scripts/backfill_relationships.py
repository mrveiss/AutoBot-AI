# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Turn umbrella checklists into native sub-issue and ``blocked_by`` edges (#15439).

``CLAUDE.md`` states that relationships are native, not prose -- every parent and
child a GitHub sub-issue, every blocker a ``blocked_by`` edge. The checklists
have always carried that information; nothing in the repository could read them,
so the graph and the prose drifted apart and #15444's nine mis-parented issues
were the visible half of it.

Three passes, each safe to run repeatedly:

``plan``
    Read every umbrella body through :mod:`child_ref` and print the edges that
    are missing. Touches nothing.
``apply``
    Create the missing edges and record each one in the manifest.
``reconcile``
    Diff live state against the checklists in both directions. Removes only
    edges the manifest says this tool created.

**Provenance is the whole safety property of the reconcile pass.** A hand-made
parent-child link is somebody's deliberate decision and this tool must never
remove one, so an edge is deletable only if it appears in the manifest. No
manifest means no deletions -- the pass fails closed rather than guessing, on
the same principle as the required-context shims: an unknown state is not an
absent one.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

# `pipeline-scripts` is not an importable package name, so the sibling module is
# reached by path -- the idiom ci_red_cause.py documents. The HTTP client is
# REUSED rather than re-written: one transport, one place a failure becomes a
# status code. #15411 tracks extracting it; until then this is the one client.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline-scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci_dispatch_watchdog import GitHubApi  # noqa: E402

from child_ref import blockers, child_ref  # noqa: E402

# Plain stdlib logging, deliberately (#1082): this runs as a bare script, where
# autobot_shared.logging_manager would pull in config a CLI does not have.
logger = logging.getLogger(__name__)

DEFAULT_MANIFEST = Path(".backlog") / "relationship-manifest.json"
PAGE_SIZE = 100
# GitHub caps pagination; a body claiming more children than this needs looking
# at by a person rather than a wider loop.
MAX_PAGES = 20


class BackfillError(RuntimeError):
    """Raised when the API disagrees with itself and the run must not continue."""


def _paginate(api: GitHubApi, path: str) -> List[Dict[str, Any]]:
    """Read every page of a list endpoint.

    A single ``per_page=100`` read looks complete and silently truncates: the
    caller sees a short list, not an error. Every list read here pages to
    exhaustion for that reason.
    """
    items: List[Dict[str, Any]] = []
    for page in range(1, MAX_PAGES + 1):
        joiner = "&" if "?" in path else "?"
        status, body = api.request("GET", f"{path}{joiner}per_page={PAGE_SIZE}&page={page}")
        if status == 404:
            return []
        if status >= 400 or not isinstance(body, list):
            raise BackfillError(f"GET {path} page {page} returned {status}")
        items.extend(body)
        if len(body) < PAGE_SIZE:
            return items
    raise BackfillError(f"GET {path} exceeded {MAX_PAGES} pages")


def sub_issues(api: GitHubApi, number: int) -> List[int]:
    """Return an issue's sub-issues, cross-checked against the summary total.

    ``sub_issues_summary.total`` is GitHub's own count. Comparing the paginated
    read against it turns a truncated page from a wrong answer into a loud one --
    the failure mode that matters, because a short list reads as "this umbrella
    holds fewer children" and not as "the read failed".
    """
    listed = _paginate(api, f"/repos/{api.repository}/issues/{number}/sub_issues")
    numbers = [int(item["number"]) for item in listed if "number" in item]

    status, issue = api.request("GET", f"/repos/{api.repository}/issues/{number}")
    if status >= 400 or not isinstance(issue, dict):
        raise BackfillError(f"GET issue #{number} returned {status}")
    summary = issue.get("sub_issues_summary") or {}
    total = summary.get("total")
    if isinstance(total, int) and total != len(numbers):
        raise BackfillError(
            f"#{number}: read {len(numbers)} sub-issues but "
            f"sub_issues_summary.total is {total} -- refusing to act on a partial read"
        )
    return numbers


def blocked_by(api: GitHubApi, number: int) -> List[int]:
    """Return the open and closed issues #``number`` declares it waits on."""
    listed = _paginate(api, f"/repos/{api.repository}/issues/{number}/dependencies/blocked_by")
    return [int(item["number"]) for item in listed if "number" in item]


def claimed_edges(body: str) -> Tuple[List[int], Dict[int, List[int]]]:
    """Read a body into the children it claims and the blockers each declares."""
    children: List[int] = []
    deps: Dict[int, List[int]] = {}
    for row in (body or "").splitlines():
        owned = child_ref(row)
        if owned is None:
            continue
        if owned not in children:
            children.append(owned)
        row_blockers = [b for b in blockers(row) if b != owned]
        if row_blockers:
            deps[owned] = row_blockers
    return children, deps


class Manifest:
    """The record of edges this tool created, and the only deletion warrant."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.children: Set[Tuple[int, int]] = set()
        self.dependencies: Set[Tuple[int, int]] = set()
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.children = {(int(p), int(c)) for p, c in raw.get("children", [])}
            self.dependencies = {(int(i), int(b)) for i, b in raw.get("dependencies", [])}

    def record_child(self, parent: int, child: int) -> None:
        self.children.add((parent, child))

    def record_dependency(self, issue: int, blocker: int) -> None:
        self.dependencies.add((issue, blocker))

    def created_child(self, parent: int, child: int) -> bool:
        return (parent, child) in self.children

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "children": sorted(list(pair) for pair in self.children),
            "dependencies": sorted(list(pair) for pair in self.dependencies),
        }
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def plan(api: GitHubApi, umbrellas: Sequence[int]) -> List[str]:
    """Report the edges the checklists claim and the graph does not hold."""
    lines: List[str] = []
    for number in umbrellas:
        status, issue = api.request("GET", f"/repos/{api.repository}/issues/{number}")
        if status >= 400 or not isinstance(issue, dict):
            lines.append(f"#{number}: unreadable (status {status})")
            continue
        claimed, deps = claimed_edges(issue.get("body") or "")
        live = set(sub_issues(api, number))
        missing = [c for c in claimed if c not in live]
        extra = sorted(live - set(claimed))
        for child in missing:
            lines.append(f"#{number} -> #{child}  ADD sub-issue")
        for child in extra:
            lines.append(f"#{number} -> #{child}  UNCLAIMED (checklist does not name it)")
        for child, needs in deps.items():
            held = set(blocked_by(api, child))
            for blocker in needs:
                if blocker not in held:
                    lines.append(f"#{child} blocked_by #{blocker}  ADD dependency")
    return lines


def apply(api: GitHubApi, umbrellas: Sequence[int], manifest: Manifest) -> List[str]:
    """Create the missing edges, recording each so reconcile may undo it."""
    done: List[str] = []
    for number in umbrellas:
        status, issue = api.request("GET", f"/repos/{api.repository}/issues/{number}")
        if status >= 400 or not isinstance(issue, dict):
            continue
        claimed, deps = claimed_edges(issue.get("body") or "")
        live = set(sub_issues(api, number))
        for child in claimed:
            if child in live:
                continue
            status, _ = api.request(
                "POST",
                f"/repos/{api.repository}/issues/{number}/sub_issues",
                {"sub_issue_id": child},
            )
            if status < 300:
                manifest.record_child(number, child)
                done.append(f"#{number} -> #{child}  added")
            else:
                done.append(f"#{number} -> #{child}  FAILED ({status})")
        for child, needs in deps.items():
            held = set(blocked_by(api, child))
            for blocker in needs:
                if blocker in held:
                    continue
                status, _ = api.request(
                    "POST",
                    f"/repos/{api.repository}/issues/{child}/dependencies/blocked_by",
                    {"issue_id": blocker},
                )
                if status < 300:
                    manifest.record_dependency(child, blocker)
                    done.append(f"#{child} blocked_by #{blocker}  added")
                else:
                    done.append(f"#{child} blocked_by #{blocker}  FAILED ({status})")
    manifest.save()
    return done


def reconcile(
    api: GitHubApi, umbrellas: Sequence[int], manifest: Manifest, remove: bool
) -> List[str]:
    """Diff live state against the checklists in both directions.

    Deletion is gated on provenance: an edge absent from the manifest was made
    by a person and is reported, never removed. That asymmetry is deliberate --
    a missing edge costs a re-run, a wrongly deleted one destroys a decision
    nobody recorded anywhere else.
    """
    lines: List[str] = []
    for number in umbrellas:
        status, issue = api.request("GET", f"/repos/{api.repository}/issues/{number}")
        if status >= 400 or not isinstance(issue, dict):
            continue
        claimed, _ = claimed_edges(issue.get("body") or "")
        for child in sorted(set(sub_issues(api, number)) - set(claimed)):
            if not manifest.created_child(number, child):
                lines.append(
                    f"#{number} -> #{child}  KEPT (not in manifest -- made by hand)"
                )
                continue
            if not remove:
                lines.append(f"#{number} -> #{child}  would remove (manifest-owned)")
                continue
            status, _ = api.request(
                "DELETE",
                f"/repos/{api.repository}/issues/{number}/sub_issue",
                {"sub_issue_id": child},
            )
            lines.append(
                f"#{number} -> #{child}  removed"
                if status < 300
                else f"#{number} -> #{child}  REMOVE FAILED ({status})"
            )
        for child in claimed:
            if child not in set(sub_issues(api, number)):
                lines.append(f"#{number} -> #{child}  MISSING (run apply)")
    return lines


def _umbrella_numbers(api: GitHubApi, explicit: Sequence[int]) -> List[int]:
    if explicit:
        return list(explicit)
    labelled = _paginate(api, f"/repos/{api.repository}/issues?labels=umbrella&state=all")
    return [int(item["number"]) for item in labelled if "pull_request" not in item]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("plan", "apply", "reconcile"))
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--issue", type=int, action="append", default=[])
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--remove",
        action="store_true",
        help="reconcile only: actually delete manifest-owned edges the checklist dropped",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not token or not args.repo:
        logger.error("GH_TOKEN and --repo (or GITHUB_REPOSITORY) are required")
        return 2

    api = GitHubApi(token=token, repository=args.repo)
    manifest = Manifest(args.manifest)
    try:
        numbers = _umbrella_numbers(api, args.issue)
        if args.mode == "plan":
            lines = plan(api, numbers)
        elif args.mode == "apply":
            lines = apply(api, numbers, manifest)
        else:
            lines = reconcile(api, numbers, manifest, args.remove)
    except BackfillError as exc:
        logger.error("refusing to continue: %s", exc)
        return 1

    for line in lines:
        logger.info("%s", line)
    logger.info("%d edge(s) reported over %d umbrella(s)", len(lines), len(numbers))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
