# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every tracked hook and installer must be mode ``100755`` in the index (#14909).

``.git/hooks/pre-push`` was a dangling symlink into a worktree deleted in April,
so the protected-branch push guard had not executed for anyone in this checkout.
Repointing it was not enough: ``tools/git-hooks/pre-push``, ``pre-commit`` and
``install_hooks.sh`` were all tracked ``100644``, and **git silently skips a hook
that is not executable**. The installer meant to set this up was itself
non-executable.

The reason it stayed invisible is the interesting half. ``core.fileMode=false``
is set repo-wide, so a plain ``chmod +x`` never reaches the index: the working
file becomes executable, ``git status`` stays clean, and the tracked mode remains
``100644`` for every other clone. Every local check therefore agrees that the
hook is fine while a fresh clone gets an inert one. Only the *index* mode is the
truth, which is what this guard reads — via ``git ls-files -s``, never via
``os.access`` or ``stat``, both of which would report the locally-patched
working file and pass on a repository that is still broken.

The rule is derived, not enumerated: **a tracked file that declares a shebang
claims it can be executed, so its mode must agree with its own first line.** The
converse is asserted too, because a file that is executable without a shebang is
handed to whatever ``sh`` happens to be (``slm-post-commit`` carried its
``#!/bin/bash`` on line 4, under the copyright header, where it is a comment).

Reach floors are asserted throughout: an empty glob reports "no offenders"
while having checked nothing, which is the same shape of bug as the one under
guard. Extensionless files are asserted specifically — the whole of #14891 was
a walk that saw only ``*.sh``.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Directories whose contents git or a developer executes directly, plus the
# canonical installer that copies them into place.
_HOOK_DIRS = (
    "tools/git-hooks",
    "autobot-infrastructure/shared/scripts/hooks",
)
_INSTALLERS = ("scripts/install-git-hooks.sh",)

# Files that must be present and executable. Named individually so a walk that
# reaches files but not *these* files still fails (#14909's three offenders,
# plus one extensionless infra hook and one that is only reachable once the
# walk stops filtering on `.sh`).
_REQUIRED = {
    "tools/git-hooks/pre-push",
    "tools/git-hooks/pre-commit",
    "tools/git-hooks/install_hooks.sh",
    "scripts/install-git-hooks.sh",
    "autobot-infrastructure/shared/scripts/hooks/pre-commit-branch-guard",
    "autobot-infrastructure/shared/scripts/hooks/pre-commit-worktree-branch-guard",
}


def _tracked_modes() -> dict[str, str]:
    """``{path: index mode}`` for every tracked file in the hook directories.

    ``git ls-files -s`` is the only reading of the mode that is not lying under
    ``core.fileMode=false``.
    """
    result = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "ls-files", "-s", "--", *_HOOK_DIRS, *_INSTALLERS],
        capture_output=True,
        text=True,
        check=True,
    )
    modes: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        meta, path = line.split("\t", 1)
        modes[path] = meta.split()[0]
    return modes


def _first_line(rel: str) -> str:
    """First line of a tracked file, or "" when it cannot be read as text."""
    path = _REPO_ROOT / rel
    if not path.is_file():
        return ""
    try:
        with path.open("rb") as handle:
            return handle.readline(512).decode("utf-8", "replace").rstrip("\r\n")
    except OSError:  # pragma: no cover - failure output only
        return ""


_MODES = _tracked_modes()
_SHEBANGED = {rel for rel in _MODES if _first_line(rel).startswith("#!")}


def test_the_sweep_actually_reached_the_hook_directories() -> None:
    """Discovery floor. An empty listing asserts nothing while reading as clean.

    Four independent floors, because any one of them can be satisfied by a sweep
    that is still broken: the file count catches a path list that stopped
    matching, the shebang count catches a reader that returns "" for everything
    (which would make every later assertion vacuously true), the named set
    catches a sweep that reaches files but not the ones this guard is about, and
    the extensionless count catches the #14891 trap of a walk that only ever
    sees ``*.sh``.
    """
    assert len(_MODES) >= 46, (
        f"only {len(_MODES)} tracked files under {_HOOK_DIRS} — the path list is "
        "no longer reaching the hook directories"
    )
    # Floors sit AT the measured count rather than below it for headroom, so a
    # retired hook has to come here and say so. Measured on this branch:
    # 46 tracked, 25 shebanged, 22 of them extensionless.
    assert len(_SHEBANGED) >= 25, (
        f"only {len(_SHEBANGED)} files declare a shebang — the reader has regressed "
        "and every assertion below would pass having checked nothing"
    )
    missing = sorted(_REQUIRED - set(_MODES))
    assert not missing, f"these hooks are no longer tracked at all: {missing}"

    extensionless = {rel for rel in _SHEBANGED if not Path(rel).suffix}
    assert len(extensionless) >= 22, (
        f"only {len(extensionless)} extensionless executables found — the sweep has "
        "narrowed to files with a suffix, which is exactly the gap #14891 closed"
    )


def test_every_shebanged_hook_is_tracked_executable() -> None:
    """A file that declares an interpreter must be tracked ``100755`` (#14909).

    Git will not run a hook whose mode is ``100644``. Under ``core.fileMode=false``
    a local ``chmod +x`` fixes the working file and leaves the index untouched,
    so this is checked against ``git ls-files -s`` and repaired with
    ``git update-index --chmod=+x <path>``.
    """
    assert _SHEBANGED, "no shebanged files found — this test would pass vacuously"
    offenders = sorted(rel for rel in _SHEBANGED if _MODES[rel] != "100755")
    assert not offenders, (
        "these files declare a shebang but are tracked non-executable, so git "
        "silently skips them and a fresh clone gets an inert hook. A plain "
        "`chmod +x` will NOT fix this (core.fileMode=false) — use "
        "`git update-index --chmod=+x <path>` (#14909):\n  " + "\n  ".join(offenders)
    )


def test_the_three_hooks_that_were_inert_are_executable() -> None:
    """The specific regression, pinned by name.

    The derived rule above would still pass if the shebang were removed from all
    three at once; naming them means the fix cannot be undone quietly.
    """
    for rel in sorted(_REQUIRED):
        assert rel in _MODES, f"{rel} is not tracked — the guard's subject vanished"
        assert _MODES[rel] == "100755", (
            f"{rel} is tracked {_MODES[rel]}, so it cannot run. This is the #14909 "
            "regression: fix with `git update-index --chmod=+x`, not `chmod`"
        )


def test_no_executable_hook_relies_on_a_missing_shebang() -> None:
    """The converse: mode ``100755`` without a shebang is interpreter roulette.

    ``execve`` fails with ENOEXEC on a file that has no ``#!`` line, and git falls
    back to running it under ``sh`` — so a bash-only hook silently changes
    meaning. ``slm-post-commit`` carried its ``#!/bin/bash`` on line 4, below the
    copyright header, where it is a comment (#14909).
    """
    executables = {rel for rel, mode in _MODES.items() if mode == "100755"}
    assert executables, "no executable files found — this test would pass vacuously"
    offenders = sorted(rel for rel in executables if not _first_line(rel).startswith("#!"))
    assert not offenders, (
        "these files are executable but their first line is not a shebang, so the "
        "kernel refuses them and git falls back to `sh` — a bash-only script then "
        "changes meaning silently. Move the `#!` line to line 1:\n  "
        + "\n  ".join(offenders)
    )


def _matches(pattern: str, path: str) -> bool:
    """Does one dorny/paths-filter glob select this path?

    Written out rather than reached for through `fnmatch`, which flattens `**`
    and `*` into the same "any characters" and would therefore claim a match
    the real filter does not make.
    """
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.fullmatch("".join(out), path) is not None


def test_the_python_filter_reaches_the_inputs_these_guards_read() -> None:
    """A guard the required check never runs is not a guard (#14909).

    `python-suite` is gated by `.github/filters/python-paths.yml`, and a PR whose
    diff misses every pattern in it takes a shim's green instead of the suite.
    Everything this module asserts on is a shell script or a file MODE — no
    Python at all — so without an explicit entry, flipping `pre-push` back to
    `100644` would be reported green by the very check written to catch it. The
    filter's own header names this shape; this is the same one, for the hooks.

    Asserted by evaluating the patterns against real paths, not by looking for
    the strings: an entry that is present but does not match is worth nothing.
    """
    filters = _REPO_ROOT / ".github" / "filters" / "python-paths.yml"
    assert filters.is_file(), f"{filters} is missing — the gate's subject vanished"
    patterns = yaml.safe_load(filters.read_text(encoding="utf-8"))["python"]
    assert len(patterns) >= 10, f"only {len(patterns)} patterns — the filter was gutted"

    # Subjects are DERIVED from the tracked surface these guards read, not a
    # hand-picked sample. A sample can cover 100% on the day it is written and
    # go stale in silence — the review note that prompted this pointed out that
    # the three paths named here happened to sit under one directory, so a new
    # extensionless script elsewhere under autobot-infrastructure/ would have
    # matched nothing and taken the shim's green.
    roots = ("autobot-infrastructure", "tools/git-hooks", "scripts/install-git-hooks.sh")
    listed = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "ls-files", "--", *roots],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    # `**/*.py` already covers the Python files by construction; what has to be
    # named explicitly is everything else.
    subjects = sorted(path for path in listed if not path.endswith(".py"))
    assert len(subjects) >= 500, (
        f"only {len(subjects)} non-Python files under {roots} — the listing "
        "regressed and this test would pass having checked almost nothing"
    )
    unreachable = [
        subject
        for subject in subjects
        if not any(_matches(pattern, subject) for pattern in patterns)
    ]
    assert not unreachable, (
        "changing these files matches no pattern in the python filter, so "
        "python-suite is reported green by the shim and the guards in this "
        "module never run against the change (#14909):\n  " + "\n  ".join(unreachable)
    )
