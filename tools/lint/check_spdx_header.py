#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SPDX/Apache-2.0 license-header enforcement + backfill (#9840).

The Apache-2.0 relicense (#9826, PR #9830) applied the two-line header

    Copyright 2025-2026 mrveiss
    SPDX-License-Identifier: Apache-2.0

to first-party source files as a *point-in-time* sweep. Files merged in
during the PR's catch-up never got the header, and there was no hook to
stop new files from landing header-less. This check closes both gaps:

* As a pre-commit hook (default mode) it fails when a staged first-party
  source file is missing the SPDX header.
* With ``--fix`` it inserts the header idempotently, preserving any
  shebang / ``# -*- coding -*-`` line, and de-duplicates the legacy
  ``Copyright (c) <year> mrveiss`` line left by older tooling.

Comment style is chosen per extension (``#`` for .py/.sh, ``//`` for
.ts/.tsx/.js/.mjs, ``/* */`` for .css) so the inserted header is valid
in every target language.

Scope is intentionally identical to the original sweep: first-party
``.py/.ts/.tsx/.js/.mjs/.sh/.css`` files only, with vendored, generated,
``.vue``, workflow, and infrastructure paths excluded (see EXCLUDE_RE).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

COPYRIGHT_LINE = "Copyright 2025-2026 mrveiss"
SPDX_LINE = "SPDX-License-Identifier: Apache-2.0"

# Per-extension comment rendering of the two header lines.
HASH_EXTS = {".py", ".sh"}
SLASH_EXTS = {".ts", ".tsx", ".js", ".mjs"}
CSS_EXTS = {".css"}
TARGET_EXTS = HASH_EXTS | SLASH_EXTS | CSS_EXTS

# Paths excluded from the sweep — vendored, generated, build output, the
# infrastructure tree (which the relicense sweep skipped, matching the
# black/isort/flake8 excludes), and line-sensitive canonical-check fixtures.
EXCLUDE_RE = re.compile(
    r"(^|/)(?:"
    r"node_modules|"
    r"\.venv|venv|__pycache__|\.git|"
    r"dist|"
    r"_generated|generated|"
    r"fixtures"
    r")/"
    r"|^autobot-infrastructure/"
    r"|^\.github/workflows/"
    r"|^data/file_manager_root/"
    r"|\.min\.(?:js|css)$"
)

# A line that already carries an SPDX identifier — used to detect presence.
SPDX_PROBE = re.compile(r"SPDX-License-Identifier:\s*Apache-2\.0")
# Legacy copyright line emitted by older AutoBot tooling, any year form.
LEGACY_COPYRIGHT = re.compile(r"^\s*(#|//|\*|/\*)\s*Copyright \(c\) \d{4}(-\d{4})? mrveiss")


def _rendered_header(ext: str) -> list[str]:
    if ext in CSS_EXTS:
        return [f"/* {COPYRIGHT_LINE}", f"   {SPDX_LINE} */"]
    prefix = "#" if ext in HASH_EXTS else "//"
    return [f"{prefix} {COPYRIGHT_LINE}", f"{prefix} {SPDX_LINE}"]


def _is_preamble(line: str) -> bool:
    """Lines that must stay at the very top, above the header."""
    return line.startswith("#!") or "coding:" in line or "coding=" in line


def has_header(text: str) -> bool:
    # Only the top of the file counts — a match deep in the body is unrelated.
    head = "\n".join(text.splitlines()[:10])
    return bool(SPDX_PROBE.search(head))


def insert_header(text: str, ext: str) -> str:
    if has_header(text):
        return text
    lines = text.split("\n")
    header = _rendered_header(ext)

    idx = 0
    preamble: list[str] = []
    while idx < len(lines) and _is_preamble(lines[idx]):
        preamble.append(lines[idx])
        idx += 1

    # Drop the legacy "Copyright (c) <year> mrveiss" line if it sits in the
    # next few lines, so we don't end up with two copyright statements.
    body = lines[idx:]
    body = [ln for ln in body[:6] if not LEGACY_COPYRIGHT.match(ln)] + body[6:]

    rebuilt = preamble + header + body
    return "\n".join(rebuilt)


def in_scope(path: Path) -> bool:
    if path.suffix not in TARGET_EXTS:
        return False
    posix = path.as_posix()
    return not EXCLUDE_RE.search(posix)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    fix = "--fix" in args
    files = [a for a in args if a != "--fix"]

    missing: list[str] = []
    fixed: list[str] = []

    for raw in files:
        path = Path(raw)
        if not path.is_file() or not in_scope(path):
            continue
        text = path.read_text(encoding="utf-8")
        if has_header(text):
            continue
        if fix:
            path.write_text(insert_header(text, path.suffix), encoding="utf-8")
            fixed.append(raw)
        else:
            missing.append(raw)

    if fixed:
        for f in fixed:
            print(f"inserted SPDX header: {f}")
    if missing:
        print("Missing SPDX/Apache-2.0 license header (run with --fix or the")
        print("insert-license pre-commit hook to add it):")
        for f in missing:
            print(f"  {f}")
        print()
        print("Expected header (comment style per file type):")
        print(f"  {COPYRIGHT_LINE}")
        print(f"  {SPDX_LINE}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
