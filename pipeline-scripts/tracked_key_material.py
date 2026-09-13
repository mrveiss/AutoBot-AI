#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fail when a tracked file holds raw key material, whatever it is named (#16275).

``.infra_encryption_key`` -- a 44-character Fernet key with no extension, at the
repository root -- was tracked in this public repository for eleven months. The
secret scanning of the day grepped three shapes inside three directories, so the
root was never read. Wiring detect-secrets over the whole tree (see
``.pre-commit-config.yaml`` and the ``secret-detection`` job in ``security.yml``)
closes the directory gap but not the shape gap: **detect-secrets 1.5.0 reports
nothing for that file**, measured, because its high-entropy plugins read quoted
strings and a bare key file has no quotes. This module checks the shape that
scanner cannot see.

What counts as key material
---------------------------
* A Fernet key: 44 characters of the url-safe base64 alphabet ending in one
  ``=``, which decodes to exactly 32 bytes and re-encodes to itself -- the only
  thing ``Fernet.generate_key()`` returns. The run must also mix upper and lower
  case. A single-case run is an identifier: a 43-character ``ENV_VAR_NAME``
  followed by ``=`` in an env template decodes cleanly too, and the two tracked
  env templates hold one each. A random key lacks one of the two cases with
  odds of about 4e-10.
* A PEM private-key header, for any algorithm.

A finding carries the path, the line and the kind -- never any part of the value.

Usage::

    git ls-files -z | python3 pipeline-scripts/tracked_key_material.py
    python3 pipeline-scripts/tracked_key_material.py FILE [FILE ...]

Exit 0 when clean; 1 on a finding or an exemption that no longer matches exactly;
2 when there was nothing to read, because an empty list is a broken
enumeration, not a clean tree.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable, Sequence

FERNET = "fernet-key"
PEM = "pem-private-key"

_B64_NEIGHBOUR = rb"A-Za-z0-9_\-+/="
_FERNET_RUN = re.compile(rb"(?<![" + _B64_NEIGHBOUR + rb"])[A-Za-z0-9_\-]{43}=(?![" + _B64_NEIGHBOUR + rb"])")
_PEM_HEADER = re.compile(rb"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----")
_LOWER = re.compile(rb"[a-z]")
_UPPER = re.compile(rb"[A-Z]")

#: The only files allowed to hold a match: the kind, the exact number of matching
#: lines, and why none of them is a key. Each header here is a format hint with
#: no key body after it. The count is exact in both directions: a second header
#: in an exempt file is a finding, and a fixed or deleted one fails until its
#: entry shrinks. Entries may only be removed.
EXEMPT: dict[str, tuple[str, int, str]] = {
    "autobot-backend/code_intelligence/precommit_analyzer_test.py": (
        PEM,
        2,
        "test fixture: proves the pre-commit analyzer blocks a private-key header;"
        " the key body is truncated to a few characters",
    ),
    "autobot-frontend/src/components/security/SecretsManager.vue": (
        PEM,
        2,
        "input placeholder showing the expected SSH-key format; the body is '...'",
    ),
    "autobot-slm-frontend/src/locales/en.json": (
        PEM,
        2,
        "i18n placeholder text for the SSH-key fields; the body is '...'",
    ),
    "docs/design/CHAT_INFRASTRUCTURE_ACCESS_DESIGN.md": (
        PEM,
        1,
        "design-doc example payload; the body is '...'",
    ),
}


@dataclass(frozen=True)
class Finding:
    """One matching line. Deliberately holds no part of the matched value."""

    path: str
    line: int
    kind: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.kind}"


def is_fernet_key(token: bytes) -> bool:
    """True when *token* is exactly the shape ``Fernet.generate_key()`` emits."""
    if not (_LOWER.search(token) and _UPPER.search(token)):
        return False
    try:
        raw = base64.urlsafe_b64decode(token)
    except (binascii.Error, ValueError):
        return False
    return len(raw) == 32 and base64.urlsafe_b64encode(raw) == token


def scan_bytes(path: str, data: bytes) -> list[Finding]:
    """Every key-material line in *data*, reported against *path*."""
    found = []
    for number, line in enumerate(data.splitlines(), start=1):
        if any(is_fernet_key(m.group(0)) for m in _FERNET_RUN.finditer(line)):
            found.append(Finding(path, number, FERNET))
        if _PEM_HEADER.search(line):
            found.append(Finding(path, number, PEM))
    return found


def scan_paths(root: Path, paths: Iterable[str]) -> tuple[list[Finding], list[str]]:
    """Scan each repo-relative path under *root*; return findings and paths read.

    A symlink is not read: git stores only its target path, and a tracked target
    is scanned under its own name. A path that is not a regular file (a gitlink,
    or one deleted since it was listed) has no content to scan.
    """
    found: list[Finding] = []
    read: list[str] = []
    for rel in paths:
        target = root / rel
        if target.is_symlink() or not target.is_file():
            continue
        found.extend(scan_bytes(rel, target.read_bytes()))
        read.append(rel)
    return found, read


def exemption_problems(findings: Sequence[Finding], read: Iterable[str]) -> list[str]:
    """Findings no exemption covers, plus exemptions that no longer match exactly.

    Exemptions are checked only for files that were read, so scanning a subset
    (a list of staged files) cannot report an unread fixture as stale.
    """
    counts: dict[tuple[str, str], int] = {}
    for finding in findings:
        counts[(finding.path, finding.kind)] = counts.get((finding.path, finding.kind), 0) + 1
    problems = [f.render() for f in findings if f.path not in EXEMPT or EXEMPT[f.path][0] != f.kind]
    read_set = set(read)
    for path, (kind, expected, _reason) in EXEMPT.items():
        actual = counts.get((path, kind), 0)
        if path in read_set and actual != expected:
            problems.append(
                f"{path}: exemption expects {expected} {kind} line(s), found {actual}"
                " -- a new match is a finding; a removed one means the entry must shrink"
            )
    return problems


def _read_nul_separated(stream: BinaryIO) -> list[str]:
    return [p.decode("utf-8", "surrogateescape") for p in stream.read().split(b"\0") if p]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail on raw key material in tracked files.")
    parser.add_argument("paths", nargs="*", help="files to scan; none reads `git ls-files -z` on stdin")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    args = parser.parse_args(argv)
    paths = args.paths or _read_nul_separated(sys.stdin.buffer)
    findings, read = scan_paths(args.root, paths)
    if not read:
        print("::error::no file was read -- a broken enumeration, not a clean tree", file=sys.stderr)  # noqa: print
        return 2
    problems = exemption_problems(findings, read)
    print(f"tracked_key_material: read {len(read)} of {len(paths)} listed paths")  # noqa: print
    for problem in problems:
        print(f"::error::{problem}")  # noqa: print
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
