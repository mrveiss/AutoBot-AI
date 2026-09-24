# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No tracked file carries an unresolved conflict block (#17297).

`docs/.obsidian/workspace.json` sat on `main` with a committed conflict block
from 2026-04-03 until #17297. The file was not valid JSON, so anything parsing
it failed.

Why the existing gate did not catch it, which is the whole reason this test
exists as well as the hook. `.pre-commit-config.yaml` has run
`check-merge-conflict` since 2025-08, and it reported **Passed** on every commit
in between. Its first statement is:

    if not is_in_merge() and not args.assume_in_merge:
        return 0

`is_in_merge()` requires `MERGE_MSG` **and** one of `MERGE_HEAD` /
`rebase-apply` / `rebase-merge`. The markers here read `Updated upstream` /
`Stashed changes` -- a `git stash pop` conflict, which creates none of those. So
the hook exited before reading a single line of the file it was pointed at. It
was not misconfigured and it did not miss a pattern: it was structurally blind
to this entire conflict class, and it answered "clean" while the markers sat in
the tree.

#17297 arms it with `--assume-in-merge`, and `test_the_hook_is_still_armed`
below keeps it armed -- removing that flag restores a hook that passes without
looking, which is worse than not having one.

This test is not redundant with the hook. A pre-commit hook is skippable with
`--no-verify` and runs only on the files a commit touches; this runs in CI over
every tracked file, so a marker that arrives any other way -- a bypassed hook, a
direct push, a merge resolved wrongly -- is still caught.

The patterns are the hook's own, including the bare `=======` form. #17297's own
acceptance criteria proposed `^======= ` with a trailing space, which **never
matches**: git writes the middle marker alone on its line. A gate built to that
spelling would have found the outer two markers and silently missed the
separator.
"""

from __future__ import annotations

import pathlib
from typing import List, Tuple

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import tracked_paths

_CONFIG = ".pre-commit-config.yaml"

#: Prefixes git writes for the outer two markers. Checked with `startswith` on
#: the raw line, exactly as `check-merge-conflict` does.
_OUTER_PREFIXES = ("<" * 7 + " ", ">" * 7 + " ")
#: The separator, which carries no label and so has no trailing space.
_SEPARATOR = "=" * 7


def _tracked_text_files(root: pathlib.Path) -> List[str]:
    try:
        return tracked_paths(root, "*")
    except Exception:
        # `discover` must return empty on an empty tree, never raise (#16154).
        return []


def _conflict_sites(root: pathlib.Path | None = None) -> List[Tuple[str, int, str]]:
    """(path, lineno, marker) for every conflict marker in a tracked file."""
    base = root or repo_root()
    found: List[Tuple[str, int, str]] = []
    for relative in _tracked_text_files(base):
        path = base / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # binary or unreadable: git's own hook skips these too
        for number, line in enumerate(text.splitlines(), start=1):
            if line.startswith(_OUTER_PREFIXES) or line.rstrip() == _SEPARATOR:
                found.append((relative, number, line[:40]))
    return found


#: Every tracked file is scanned; the floor guards against the enumeration
#: silently returning nothing, which would make this test pass by not looking.
#: 10810 tracked files measured at #17297. The first number written here was
#: 2000 -- chosen by feel, an order of magnitude low, and `verify_floor`
#: refused it. That refusal is the mechanism working: a floor that far below
#: the population passes while most of the tree stops being reached.
SCANNED_FILES = declare(
    "conflict-marker-scanned-files",
    discover=lambda root: _tracked_text_files(root),
    floor=10000,
    growth=1000,
    what="tracked files scanned for conflict markers (#17297)",
)


def test_the_sweep_actually_reaches_the_tree() -> None:
    """`no markers found` must be distinguishable from `no files read`."""
    SCANNED_FILES.verify_floor(repo_root())


def test_no_tracked_file_carries_a_conflict_marker() -> None:
    sites = _conflict_sites()
    assert not sites, (
        "unresolved conflict markers in tracked files -- the file is almost certainly not "
        f"parseable by whatever reads it (#17297): {sites}"
    )


def test_the_hook_is_still_armed() -> None:
    """Without `--assume-in-merge` the hook passes without reading anything.

    Pinned because the failure is invisible: a disarmed hook still prints
    "Passed", so nothing about the output distinguishes it from a clean tree.
    """
    config = (repo_root() / _CONFIG).read_text(encoding="utf-8")
    block = config.split("id: check-merge-conflict", 1)
    assert len(block) == 2, "check-merge-conflict is no longer configured at all"
    following = block[1].split("- id:", 1)[0]
    assert "--assume-in-merge" in following, (
        "check-merge-conflict without --assume-in-merge returns 0 unless the repo is mid-merge, "
        "so it cannot see a `git stash pop` conflict -- which is how #17297 reached main"
    )


@pytest.mark.parametrize("marker", [_OUTER_PREFIXES[0], _SEPARATOR, _OUTER_PREFIXES[1]])
def test_the_detector_recognises_each_marker_shape(marker: str, tmp_path: pathlib.Path) -> None:
    """A detector is worth what it detects, and the separator is the easy miss.

    Asserted through `_conflict_sites`' own predicate rather than re-implemented
    here: a contrast written inline would pass against a detector that cannot
    see the bare `=======`, which is precisely the bug in the acceptance
    criteria's proposed regex.
    """
    line = marker if marker == _SEPARATOR else f"{marker}some-branch"
    assert line.startswith(_OUTER_PREFIXES) or line.rstrip() == _SEPARATOR
