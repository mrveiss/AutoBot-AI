# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Glob-declared guard inputs, which the concrete-literal checker cannot see (#15900).

`python_filter_covers_its_guards_test.py` records a guard's input only when that
input resolves to a **concrete file**::

    if not (_REPO_ROOT / candidate).is_file():
        return  # a prefix or a glob, not a file this guard reads

So a guard declaring ``".github/workflows/*.yml"`` contributes nothing. Its
dependency is real; its detection is not — and the checker's green therefore
means "no guard reads an uncovered file *by concrete literal*" while its name
claims the general property.

**Why this is a separate record rather than an expansion of that one.** #15900
costed the obvious fix: teaching `_record` to expand globs turns 27 uncovered
entries into roughly 86, because `.github/workflows/` alone holds 64 files.
`MAX_UNCOVERED_READS` only ever goes down, so expansion forces either a 59-entry
cap raise or widening the filter to `.github/workflows/**` — twelve shards on
almost every pull request. That is a CI-spend decision, and it was being made by
an accident of implementation rather than deliberately.

Recording the **declarations** costs none of that. There are 14 of them across 5
guards, against 59+ expansions, and they are the thing a reader needs: *which
guard depends on which tree*. An undetectable dependency and an absent one are
indistinguishable, and this makes them distinguishable without spending a shard.

The population is **discovered** — every quoted repo-relative string containing
`*` — not a list of the four the issue named. That is how the fifth was found:
`scripts/lib/*.sh` is a real uncovered dependency of
`comment_line_number_citations_test.py` that #15900 does not mention.
"""

from __future__ import annotations

import re

import pytest

from repo_tests._paths import repo_root
from repo_tests.python_filter_covers_its_guards_test import _filter_patterns, _is_covered
from tools.lint._scan_helpers import tracked_paths

REPO_ROOT = repo_root()

#: A repo-relative path mentioned in a guard, containing a glob. Anchored on a
#: quote for the same reason the sibling checker is: an unquoted match picks up
#: prose and import paths, which are not reads of the tree.
_QUOTED_GLOB = re.compile(r"""["']([A-Za-z0-9_.*-]+/[A-Za-z0-9_./*-]+)["']""")

#: Glob declarations whose tree the python filter does NOT cover, with the guard
#: that declares each and why it is accepted for now.
#:
#: THIS ONLY SHRINKS. An entry leaves when the filter covers its tree, or when a
#: cheaper route runs that guard on its own trigger. Never add one to make a new
#: uncovered dependency pass — that is the decision this record exists to keep
#: visible rather than to rubber-stamp.
GLOB_DECLARED_UNCOVERED: dict[str, str] = {
    ".github/actions/**": (
        "code_quality_guard_reach_test.py — asserts the filter itself names this tree; "
        "covering it would run twelve shards on every action edit (#15900)"
    ),
    ".github/actions/*/action.yml": (
        "python_version_declaration_drift_test.py — Python-version drift across composite "
        "actions; the guard does not run when an action changes its Python version"
    ),
    ".github/workflows/*.yml": (
        "comment_line_number_citations_test.py, python_version_declaration_drift_test.py — "
        "64 workflow files; covering the tree is the twelve-shard trade #15900 declines to "
        "make wholesale"
    ),
    ".github/workflows/*.yaml": ("python_version_declaration_drift_test.py — the `.yaml` spelling of the same tree"),
    "scripts/lib/*.sh": (
        "comment_line_number_citations_test.py — NOT named in #15900; found by discovering "
        "the population rather than listing the known cases"
    ),
}

#: Floor on guards PARSED, not on declarations found. A findings floor is
#: satisfied by finding nothing, which is also what a collapsed sweep reports.
_MIN_GUARDS_PARSED = 180


def glob_declarations_in(source: str) -> set[str]:
    """Repo-relative glob declarations mentioned in *source*."""
    found = set()
    for match in _QUOTED_GLOB.finditer(source):
        candidate = match.group(1)
        if "*" not in candidate:
            continue
        tree = candidate.split("/", 1)[0]
        if not (REPO_ROOT / tree).is_dir():
            continue  # not a path into this tree
        found.add(candidate)
    return found


def _probe_path(glob: str) -> str:
    """A concrete path the *glob* would match, for the filter's own matcher."""
    return glob.replace("**/", "").replace("**", "x").replace("*", "x")


def _declared() -> tuple[dict[str, set[str]], int]:
    """Every glob declaration in `repo_tests`, and the number of guards parsed."""
    declarations: dict[str, set[str]] = {}
    parsed = 0
    for rel in tracked_paths(REPO_ROOT, "repo_tests/*.py"):
        try:
            source = (REPO_ROOT / rel).read_text(encoding="utf-8")
        except OSError:
            continue
        parsed += 1
        for glob in glob_declarations_in(source):
            declarations.setdefault(glob, set()).add(rel)
    return declarations, parsed


def test_every_uncovered_glob_declaration_is_recorded() -> None:
    """A glob into a tree the filter misses must be written down, not silent."""
    declarations, parsed = _declared()
    assert parsed >= _MIN_GUARDS_PARSED, (
        f"the sweep parsed {parsed} guards, below the floor of {_MIN_GUARDS_PARSED} — "
        "a shrunken population reports 'no uncovered globs' for the same reason a covered tree does"
    )
    patterns = _filter_patterns()
    uncovered = {g for g in declarations if not _is_covered(_probe_path(g), patterns)}

    unrecorded = sorted(uncovered - set(GLOB_DECLARED_UNCOVERED))
    assert not unrecorded, (
        "these guards declare a glob into a tree the python filter does not cover, and the "
        "dependency is recorded nowhere — so the guard silently does not run when that tree "
        "changes (#15900):\n  " + "\n  ".join(f"{g}  <- {', '.join(sorted(declarations[g]))}" for g in unrecorded)
    )


def test_the_record_only_shrinks() -> None:
    """A resolved entry must be deleted, so the record cannot rot into a wish list."""
    declarations, _ = _declared()
    patterns = _filter_patterns()
    uncovered = {g for g in declarations if not _is_covered(_probe_path(g), patterns)}

    stale = sorted(set(GLOB_DECLARED_UNCOVERED) - uncovered)
    assert not stale, (
        "these entries are no longer uncovered — the filter reaches them now, or the guard "
        "stopped declaring them. Delete them from GLOB_DECLARED_UNCOVERED:\n  " + "\n  ".join(stale)
    )


def test_every_record_entry_names_the_guard_that_depends_on_it() -> None:
    """The record is for a reader, so each reason must name a guard file.

    An entry saying only "accepted" records that a decision happened and not what
    it was about, which is the state #15900 describes as indistinguishable from
    an absent dependency.
    """
    for glob, reason in GLOB_DECLARED_UNCOVERED.items():
        assert "_test.py" in reason, f"{glob}: the reason names no guard — {reason!r}"


def test_the_detector_reports_a_glob_declaration() -> None:
    """Positive control: the shape this guard exists to see."""
    assert glob_declarations_in('paths = (".github/workflows/*.yml",)') == {".github/workflows/*.yml"}


@pytest.mark.parametrize(
    "source",
    [
        'x = "a concrete/file.yml"',
        'x = "not_a_path"',
        'x = "no-such-tree-here/*.yml"',
    ],
    ids=["concrete-file", "bare-word", "unknown-tree"],
)
def test_the_detector_ignores_what_is_not_a_glob_into_this_tree(source: str) -> None:
    """The contrasts. Without them, "detect globs" is satisfied by reporting every string.

    A concrete literal is the SIBLING checker's job and must not be duplicated
    here; a bare word is not a path; a path into a directory this repository does
    not have is prose, not a read.
    """
    assert glob_declarations_in(source) == set()
