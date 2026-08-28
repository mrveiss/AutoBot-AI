#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every pytest root named in marker-tests.yml must collect something (#15161).

`marker_suite_report.py` (#14930) answers "did the selection still match
tests?" per *invocation*. That is one level too coarse: an invocation names
several roots, and its floor is cleared by whichever root still works.

#15161 came within one invocation shape of demonstrating it. The conftest of
`autobot-infrastructure/shared/tests` imported `autobot-user-backend/`, a
directory renamed away by 00ae80e10c, and aborted collection of the whole tree
whenever pytest was rooted at it. In `marker-tests.yml` it survived only
because that invocation also names `libs`, which moves rootdir to the
repository root, whose pytest.ini happens to carry `autobot-backend` on
`pythonpath`. Nothing about the infra floor was doing that work: with the tree
collecting nothing, `--min-collected 1` and `--min-passed infra=10` are both
cleared by `libs` alone and the report is green over a root contributing zero.

This script closes that gap at the root level, and asks the weaker but
un-fakeable question: **does pytest reach any test at all under this path?**

* COLLECTION, not selection. `-m "integration or slow or distributed or
  performance"` legitimately matches nothing under some roots (`tools`,
  `scripts`), so a per-root *selection* floor would be false. A root that
  collects zero items, by contrast, is never legitimate — it is either a
  broken conftest or a path that no longer holds tests, and both are defects.
* ONE pytest process over every root, so the run costs a single collection pass
  and the node ids come back relative to the repository root.
* The roots are DERIVED from the workflow, never listed here. A root added to
  `marker-tests.yml` is checked the moment it is added; a root renamed at one
  end breaks this instead of quietly narrowing what is checked.

What it deliberately does NOT own: a collection *error* inside a root that
still yields tests. Those already fail the workflow's own pytest steps, whose
`|| [ $? -eq 5 ]` tolerates only "nothing collected" and nothing else. Folding
them in here would give one condition two owners and two verdicts. The count
this script reports is what pytest actually reached, so a root eroded by errors
shows a falling number rather than a hidden one.

Exit status is 0 only when pytest started, reached at least one test overall,
and every named root contributed at least one item.
"""

from __future__ import annotations

import argparse
import re
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "marker-tests.yml"

# A collect-only node id at verbosity < 0: `path/to/module.py::Class::test_x`.
# Anchored on the `.py::` boundary so pytest's headers, warnings and error
# blocks cannot be mistaken for collected items.
_NODEID = re.compile(r"^(?P<path>[^\s]+\.py)::")


# pytest's own exit status for "I could not start" — the one code that means
# this check inspected nothing rather than inspecting a broken tree.
PYTEST_USAGE_ERROR = 4


class CollectionFloorError(RuntimeError):
    """A root collected nothing, or pytest could not collect at all."""


def command_tokens(run: str) -> List[str]:
    """A shell `run:` block flattened to tokens, line continuations removed."""
    return run.replace("\\\n", " ").split()


def roots_in(tokens: Sequence[str], repo_root: Path) -> List[str]:
    """The existing paths an invocation names as test roots.

    A bare token that exists as a path and is not the value of the option before
    it — `-n auto` and `--dist loadscope` name no path, but `-m pytest` would
    read as one if the preceding option were ignored.
    """
    return [
        token
        for index, token in enumerate(tokens)
        if not token.startswith("-")
        and not (index and tokens[index - 1].startswith("-"))
        and (repo_root / token).exists()
    ]


def workflow_roots(workflow: Path, repo_root: Path = REPO_ROOT) -> List[str]:
    """Every root named by every pytest invocation in the workflow, deduplicated.

    Parsed off the raw text rather than the YAML tree: this file only needs the
    `python -m pytest ...` command lines, and reading them directly keeps the
    script free of a YAML dependency in a step that runs before the test
    requirements are necessarily installed.
    """
    text = workflow.read_text(encoding="utf-8")
    seen: Dict[str, None] = {}
    for block in re.findall(r"python -m pytest(?:.|\n)*?(?=\n\s*\n|\Z)", text):
        tokens = command_tokens(block)
        if tokens[:3] != ["python", "-m", "pytest"]:
            continue
        for root in roots_in(tokens[3:], repo_root):
            seen.setdefault(root, None)
    return list(seen)


def collect(roots: Sequence[str], repo_root: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    """One `--collect-only` pass over every root, node ids on stdout.

    `-q -q` is required, not cosmetic: pytest prints the *tree* form of
    `--collect-only` at verbosity >= 0, and the repository's `addopts` already
    carries `--verbose`, so a single `-q` only cancels it back to the tree.
    Node ids appear only below zero.

    `--continue-on-collection-errors` so the node ids of every root are emitted
    even when one module fails to import. Without it pytest raises Interrupted
    at the first error batch, and a root listed after the broken one would read
    as empty for a reason that has nothing to do with that root.
    """
    return subprocess.run(  # nosec B603
        [
            sys.executable,
            "-m",
            "pytest",
            *roots,
            "--collect-only",
            "-q",
            "-q",
            "-p",
            "no:cacheprovider",
            "--continue-on-collection-errors",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )


def nodeids(stdout: str) -> List[str]:
    """The collected node ids in pytest's `-q -q --collect-only` output."""
    return [line.strip() for line in stdout.splitlines() if _NODEID.match(line.strip())]


def counts_by_root(collected: Iterable[str], roots: Sequence[str]) -> Dict[str, int]:
    """Node ids attributed to the longest root that prefixes them.

    Longest-first because the roots overlap by construction:
    `autobot-infrastructure/shared/scripts/hooks` lives under no other root
    today, but `libs` and a future `libs/<pkg>` would, and the shorter root must
    not absorb the longer one's items and hide that it collects nothing.
    """
    tally = {root: 0 for root in roots}
    ordered = sorted(roots, key=len, reverse=True)
    for nodeid in collected:
        path = nodeid.split("::", 1)[0]
        for root in ordered:
            if path == root or path.startswith(f"{root}/"):
                tally[root] += 1
                break
    return tally


def check(result: subprocess.CompletedProcess, roots: Sequence[str]) -> Dict[str, int]:
    """Raise unless pytest collected cleanly and every root contributed an item."""
    if not roots:
        raise CollectionFloorError(
            "no pytest root was derived from the workflow — this check would inspect "
            "nothing, which must never read as a pass"
        )
    if result.returncode == PYTEST_USAGE_ERROR:
        raise CollectionFloorError(
            "pytest could not start (usage error), so this check inspected nothing:\n"
            + "\n".join((result.stdout + result.stderr).splitlines()[-25:])
        )
    collected = nodeids(result.stdout)
    if not collected:
        raise CollectionFloorError(
            "pytest collected no test at all across every named root; an empty result must "
            "never read as a clean one:\n" + "\n".join((result.stdout + result.stderr).splitlines()[-25:])
        )
    tally = counts_by_root(collected, roots)
    empty = sorted(root for root, count in tally.items() if count == 0)
    if empty:
        raise CollectionFloorError(
            "these roots are named by marker-tests.yml and collect NO tests, so the "
            "invocation that names them reports on nothing while reading as clean "
            "(#15161):\n  " + "\n  ".join(empty)
        )
    return tally


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "roots",
        nargs="*",
        help="roots to check; default is every root named by the workflow (CI passes none)",
    )
    parser.add_argument("--workflow", type=Path, default=DEFAULT_WORKFLOW)
    args = parser.parse_args(argv)

    roots = args.roots or workflow_roots(args.workflow)
    print(f"Checking {len(roots)} pytest root(s) named by {args.workflow.name}:")
    for root in roots:
        print(f"  {root}")

    try:
        tally = check(collect(roots), roots)
    except CollectionFloorError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    width = max(len(root) for root in roots)
    for root, count in tally.items():
        print(f"  {root:<{width}}  {count:>6} collected")
    print(f"OK: every named root collects at least one test ({sum(tally.values())} in total).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
