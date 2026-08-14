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

_REQ = re.compile(r"([A-Za-z0-9_.\-]+)(\[[^\]]*\])?\s*([<>=!~].*)?$")
_INCLUDE = re.compile(r"^\s*-r\s+(\S+)")


def _repo_root() -> Path:
    result = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0 or not result.stdout.strip():
        sys.exit(f"FATAL: cannot locate the repo root: {result.stderr.strip()}")
    return Path(result.stdout.strip())


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


def conflicts(root: Path) -> list[str]:
    """Every package a requirements file and its include pin differently."""
    listing = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "*requirements*.txt"], cwd=str(root), capture_output=True, text=True, encoding="utf-8"
    )
    if listing.returncode != 0:
        sys.exit(f"FATAL: git ls-files failed: {listing.stderr.strip()}")
    files = listing.stdout.split()
    if not files:
        sys.exit("FATAL: git ls-files listed no requirements files — refusing to report clean on an empty scope")

    found: list[str] = []
    for rel in files:
        path = root / rel
        own = _declarations(path)
        for inc in _includes(path):
            if not inc.is_file():
                continue
            for name, (inc_line, inc_spec) in _declarations(inc).items():
                if name not in own:
                    continue
                own_line, own_spec = own[name]
                if own_spec == inc_spec:
                    continue  # identical: redundant, but pip accepts it
                try:
                    inc_rel = inc.relative_to(root).as_posix()
                except ValueError:  # pragma: no cover - include outside the repo
                    inc_rel = str(inc)
                found.append(
                    f"{rel}:{own_line}: '{own_spec}' conflicts with {inc_rel}:{inc_line}: '{inc_spec}'"
                )
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filenames", nargs="*", help="ignored; every tracked requirements file is checked")
    parser.parse_args(argv)

    found = conflicts(_repo_root())
    if not found:
        print("check-requirements-dupes: no package is pinned differently by a file and its include")  # noqa: print
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
