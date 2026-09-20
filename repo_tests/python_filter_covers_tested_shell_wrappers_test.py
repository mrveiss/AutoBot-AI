# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A shell wrapper with a python-suite test must be in `python-paths.yml` (#16249).

`pipeline-scripts/check-pre-commit-hook-pr.sh` is run by two python-suite tests,
and no pattern in `.github/filters/python-paths.yml` matched it. So a change
confined to the wrapper computed `python != 'true'`, the required-context shim
reported `python-suite` green, and the tests that exercise the change never ran
— a guard bypassable by touching the one file it exists to watch.

**Why the existing coverage guard cannot catch this, which the issue did not
record.** `python_filter_covers_its_guards_test.py` was built for exactly this
class, and two independent things stop it here:

1. it sweeps `repo_tests/` only, so tests living beside their subject are out of
   reach; and
2. `pipeline-scripts`, `scripts` and `tools` are all in its ``_NOT_A_READ`` set,
   whose stated premise is "trees whose contents no guard reads directly". That
   premise is false — `check-pre-commit-hook-pr_test.py` reads its own `.sh`
   directly — so even sweeping those directories would discard the finding.

Widening that guard was measured rather than guessed, and the numbers are why
this file exists instead. Against `main`, with the sweep reimplemented and
validated at 38 uncovered reads (equal to the recorded `MAX_UNCOVERED_READS`):

| Change | Uncovered reads |
|---|---|
| today | 38 |
| also sweep `pipeline-scripts/` | 58 |
| ...and drop `pipeline-scripts` from `_NOT_A_READ` | 63 |
| ...and drop `scripts` too | 77 |

Every option raises a count whose own rule is that it may only fall, and the
25 newly surfaced reads are mostly workflow and config files — a different
population from the one this issue is about. So the narrow invariant is asserted
directly here, where it is exact and costs the ratchet nothing.

This file deliberately does NOT generalise to "every shell script with a test".
It answers one question: is a wrapper that python-suite tests actually able to
trigger python-suite?
"""

from __future__ import annotations

import re
from pathlib import Path

# The matching semantics are imported, never re-implemented: two matchers that
# drift apart would disagree silently, and this file would then certify coverage
# the real gate does not grant. A rename breaks the import loudly instead.
from repo_tests._paths import repo_root
from repo_tests.python_filter_covers_its_guards_test import _filter_patterns, _is_covered

_REPO_ROOT = repo_root()
_WRAPPER_DIR = _REPO_ROOT / "pipeline-scripts"

#: A `source`/`.` line, captured whole. Deliberately NOT a pattern over the
#: quoted argument: the portable form nests quotes —
#: `source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../scripts/lib/x.sh"` —
#: so a `[^"]+` argument pattern stops at the first inner quote and silently
#: yields `$(cd `, which ends in no `.sh` and is dropped as if the line sourced
#: nothing. That is how this extractor read the two `${VAR}` wrappers correctly
#: and the portable one as empty on its first outing.
_SOURCE_LINE = re.compile(r"^\s*(?:source|\.)\s+(.+)$", re.MULTILINE)

#: The `.sh` argument within a source line. The LAST one wins: everything before
#: it in the portable form is the `$(...)` that computes the directory, and none
#: of that ends in `.sh`.
_SH_ARGUMENT = re.compile(r"([$\{\}A-Za-z0-9_./-]+\.sh)")

#: A leading `$VAR/` or `${VAR}/`, which the wrappers use for the repository root.
_ROOT_VARIABLE = re.compile(r"^\$\{?[A-Za-z_][A-Za-z0-9_]*\}?/")


def _tested_wrappers() -> dict[Path, list[str]]:
    """Every `pipeline-scripts/*.sh` that a sibling `*_test.py` names, to its tests."""
    tests = {path: path.read_text(encoding="utf-8", errors="replace") for path in _WRAPPER_DIR.glob("*_test.py")}
    found: dict[Path, list[str]] = {}
    for script in sorted(_WRAPPER_DIR.glob("*.sh")):
        readers = sorted(path.name for path, text in tests.items() if script.name in text)
        if readers:
            found[script] = readers
    return found


def _sourced_paths(script: Path) -> tuple[set[str], set[str]]:
    """Repo-relative paths *script* sources, and any argument that would not resolve.

    Two spellings are in use and both must be read, because missing either drops
    a real dependency silently:

    * ``"$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../scripts/lib/x.sh"`` —
      resolved against the script's own directory;
    * ``"${REPO_ROOT}/scripts/lib/x.sh"`` — resolved against the repository root.
      Every wrapper using this form assigns the variable
      ``$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)``, which for a script in
      ``pipeline-scripts/`` IS the repository root. Checked in each of them, not
      assumed from the variable's name.

    Unresolvable arguments are RETURNED, never skipped. A source line this cannot
    read is a dependency nobody is checking, and dropping it would make that
    indistinguishable from a script that sources nothing.
    """
    sourced: set[str] = set()
    unresolved: set[str] = set()
    for raw in _SOURCE_LINE.findall(script.read_text(encoding="utf-8", errors="replace")):
        arguments = _SH_ARGUMENT.findall(raw)
        if not arguments:
            continue
        # Leading `/` is the remainder of `...&& pwd)/../x.sh`, not an absolute
        # path: keeping it would resolve against the filesystem root.
        tail = arguments[-1].lstrip("/")
        if _ROOT_VARIABLE.match(tail):
            base, tail = _REPO_ROOT, _ROOT_VARIABLE.sub("", tail)
        else:
            base = script.parent
        resolved = (base / tail).resolve()
        try:
            relative = resolved.relative_to(_REPO_ROOT).as_posix()
        except ValueError:
            unresolved.add(raw)
            continue
        if not resolved.is_file():
            unresolved.add(raw)
            continue
        sourced.add(relative)
    return sourced, unresolved


def test_every_tested_wrapper_is_covered_by_the_filter():
    """The reported defect: a wrapper its own tests run, that cannot trigger them."""
    patterns = _filter_patterns()
    uncovered = {
        script.relative_to(_REPO_ROOT).as_posix(): readers
        for script, readers in _tested_wrappers().items()
        if not _is_covered(script.relative_to(_REPO_ROOT).as_posix(), patterns)
    }
    assert not uncovered, (
        "these shell wrappers are exercised by python-suite tests but match no pattern in "
        ".github/filters/python-paths.yml, so a change to one of them skips the tests that run it:\n  "
        + "\n  ".join(f"{path} — read by {', '.join(readers)}" for path, readers in sorted(uncovered.items()))
    )


def test_every_library_a_tested_wrapper_sources_is_covered():
    """A wrapper cannot run without what it sources, so the filter must reach that too."""
    patterns = _filter_patterns()
    uncovered: dict[str, str] = {}
    for script in _tested_wrappers():
        for sourced in _sourced_paths(script)[0]:
            if not _is_covered(sourced, patterns):
                uncovered[sourced] = script.relative_to(_REPO_ROOT).as_posix()
    assert not uncovered, (
        "these libraries are sourced by a tested wrapper but match no filter pattern:\n  "
        + "\n  ".join(f"{path} — sourced by {by}" for path, by in sorted(uncovered.items()))
    )


# ---------------------------------------------------------------------------
# Controls. Each assertion above passes trivially if its sweep finds nothing.
# ---------------------------------------------------------------------------


def test_the_sweep_finds_the_wrappers_that_have_tests():
    """Reach before findings — an empty sweep must fail here, not pass above."""
    found = _tested_wrappers()
    # Four, not three. The enumeration that seeded this change paired scripts to
    # tests by NAME and missed pr-queue-open-list.sh, whose test is spelled
    # pr_queue_open_list_test.py — a hyphen/underscore boundary that a name-based
    # sweep crosses silently. This floor ratchets up; lower it only alongside a
    # deliberate removal.
    assert len(found) >= 4, f"the sweep found only {sorted(p.name for p in found)}"
    names = {script.name for script in found}
    assert "check-pre-commit-hook-pr.sh" in names, "the wrapper this issue is about was not found"


def test_the_source_extractor_reads_both_spellings():
    """Pinned on the real wrappers, not fixtures, so extractor and scripts cannot drift.

    The exact sets matter in both directions: too few and a dependency goes
    unchecked, too many and the filter widens on a path nothing sources. The
    empty entry is load-bearing — it is the one that would catch an extractor
    that started matching prose.
    """
    expected = {
        "check-pre-commit-hook-pr.sh": {"scripts/lib/git-scope.sh"},
        "check_baseline_no_growth.sh": {"scripts/lib/git-scope.sh", "scripts/lib/hardcoded-value-rules.sh"},
        "detect-hardcoded-values.sh": {"scripts/lib/hardcoded-value-rules.sh"},
        "pr-queue-open-list.sh": set(),
    }
    for name, want in expected.items():
        script = _WRAPPER_DIR / name
        assert script.is_file(), f"{name} moved; re-point this guard rather than deleting it"
        assert _sourced_paths(script)[0] == want, name


def test_no_source_line_goes_unread():
    """An argument the extractor cannot resolve is a dependency nobody is checking."""
    unresolved = {
        script.name: args for script, _ in _tested_wrappers().items() if (args := _sourced_paths(script)[1])
    }
    assert not unresolved, f"source arguments that did not resolve to a repository file: {unresolved}"


def test_an_uncovered_path_is_reported_by_the_matcher():
    """The imported matcher must be able to say no, or both tests above are vacuous."""
    patterns = _filter_patterns()
    assert not _is_covered("pipeline-scripts/definitely-not-in-the-filter.sh", patterns)
    assert _is_covered("pipeline-scripts/check-pre-commit-hook-pr.sh", patterns)
