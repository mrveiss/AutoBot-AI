#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Fail when a requirements file and one it includes pin the same package differently (#14228).

`autobot-backend/requirements.txt` ends with `-r ../requirements.txt`, so pip
sees both files as one requirement set. When the same distribution appears in
both with **different** specifiers, pip aborts:

    ERROR: Double requirement given: openpyxl>=3.1.5
    (from -r .../requirements.txt (line 25))
    (already in openpyxl>=3.1.0 (from -r /tmp/requirements-filtered.txt (line 30)))

That killed a live provisioning run. It had been latent for as long as the
include existed: `build-filtered-requirements.sh` rewrites the relative `-r` to
an absolute code_source path so it actually resolves (#11134), and only then do
the root file's pins reach pip.

**Identical duplicates are not flagged.** pip tolerates them — `aiosqlite`
appears in both files with the same specifier, on a line *before* the openpyxl
conflict, and did not error. They are redundant, not breaking, and failing on
them would turn a real bug into a tidiness campaign.

pip reports only the first conflict, so a one-at-a-time fix moves the failure to
the next package on the next deploy. This reports all of them at once.
"""

from __future__ import annotations

import argparse
import re
import subprocess  # nosec B404  # git plumbing, fixed argv, no shell
import sys
from pathlib import Path

# The scrubbed root resolver lives in ``autobot_shared`` and this script runs
# from a pre-commit virtualenv that does not have the repository installed, so
# the import path is bootstrapped from this file's own location -- the one
# derivation an inherited GIT_DIR cannot confuse (#15176).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autobot_shared.paths import (  # noqa: E402
    GitRepoRootUnavailable,
    git_repo_root,
    scrubbed_git_env,
)

_REQ = re.compile(r"([A-Za-z0-9_.\-]+)(\[[^\]]*\])?\s*([<>=!~].*)?$")
# pip accepts both spellings, and a guard that silently skips one reports clean
# on a file it never opened (#14228 review).
_INCLUDE = re.compile(r"^\s*(?:-r|--requirement)[\s=]+(\S+)")


def _repo_root() -> Path:
    """Absolute repo root, with the ambient git environment scrubbed first.

    Measured for #15176 before the scrub: run from ``repo_tests/`` with
    ``GIT_DIR`` exported (which is what a hook hands its children), this
    resolved the root to ``repo_tests/``. ``git ls-files`` still listed the
    requirements files, so the empty-scope guard below never fired, but every
    ``root / rel`` join then pointed at a path that does not exist, ``_closure``
    skipped each one as "not a file", and the check printed its success line
    having opened **no requirements file at all** -- with a planted
    ``openpyxl==3.0.0`` conflict standing.
    """
    try:
        return git_repo_root()
    except GitRepoRootUnavailable as exc:
        sys.exit(f"FATAL: cannot locate the repo root: {exc}")


def _declarations(path: Path) -> dict[str, tuple[int, str]]:
    """First declaration of each distribution in *path*, by canonical name."""
    found: dict[str, tuple[int, str]] = {}
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#")[0].strip()
        if not line or line.startswith("-"):
            continue
        match = _REQ.match(line)
        if match:
            found.setdefault(match.group(1).lower().replace("_", "-"), (lineno, line))
    return found


def _includes(path: Path) -> list[Path]:
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        match = _INCLUDE.match(raw.split("#")[0])
        if match:
            out.append((path.parent / match.group(1)).resolve())
    return out


def _closure(path: Path) -> list[Path]:
    """Every file pip would read when handed *path*, itself first.

    pip resolves the whole include graph into ONE requirement set, so a conflict
    two hops away aborts the install exactly like an adjacent one. Comparing a
    file only against its direct includes misses that, and misses two siblings
    of the same parent entirely -- `requirements-ci.txt` fans out to twelve
    children that never see each other pairwise (#14228 review).
    """
    seen: list[Path] = []
    queue = [path]
    while queue:
        current = queue.pop(0)
        if current in seen or not current.is_file():
            continue
        seen.append(current)
        queue.extend(_includes(current))
    return seen


def conflicts(root: Path) -> list[str]:
    """Every package pinned differently anywhere in one install's requirement set."""
    listing = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "*requirements*.txt"],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        # Same scrub as the root: an inherited GIT_DIR would enumerate one
        # checkout's index while *root* names another (#15176).
        env=scrubbed_git_env(),
    )
    if listing.returncode != 0:
        sys.exit(f"FATAL: git ls-files failed: {listing.stderr.strip()}")
    files = listing.stdout.split()
    if not files:
        sys.exit("FATAL: git ls-files listed no requirements files — refusing to report clean on an empty scope")

    def _label(path: Path) -> str:
        try:
            return path.relative_to(root).as_posix()
        except ValueError:  # pragma: no cover - include outside the repo
            return str(path)

    # The same conflict surfaces from every root whose closure reaches it; report
    # each distinct pair of declarations once.
    reported: set[tuple[str, str]] = set()
    found: list[str] = []
    for rel in files:
        declarations: dict[str, list[tuple[str, int, str]]] = {}
        for member in _closure(root / rel):
            for name, (lineno, spec) in _declarations(member).items():
                declarations.setdefault(name, []).append((_label(member), lineno, spec))

        for name, sites in sorted(declarations.items()):
            distinct = {spec for _, _, spec in sites}
            if len(distinct) < 2:
                continue  # absent, or declared identically: pip accepts those
            first = sites[0]
            for site in sites[1:]:
                if site[2] == first[2]:
                    continue
                key = tuple(sorted((f"{first[0]}:{first[1]}", f"{site[0]}:{site[1]}")))
                if key in reported:
                    continue
                reported.add(key)
                found.append(
                    f"{name}: {first[0]}:{first[1]}: '{first[2]}' " f"conflicts with {site[0]}:{site[1]}: '{site[2]}'"
                )
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filenames", nargs="*", help="ignored; every tracked requirements file is checked")
    parser.parse_args(argv)

    found = conflicts(_repo_root())
    if not found:
        print(
            "check-requirements-dupes: no package is pinned differently within any install's requirement set"
        )  # noqa: print
        return 0

    print(f"check-requirements-dupes: {len(found)} conflicting duplicate(s)\n")  # noqa: print
    for item in found:
        print(f"  FAIL  {item}")  # noqa: print
    print(  # noqa: print
        "\npip aborts on the FIRST of these, so fixing one at a time moves the\n"
        "failure to the next package on the next deploy. Keep one declaration —\n"
        "normally the stricter floor, in the file the other one includes.\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
