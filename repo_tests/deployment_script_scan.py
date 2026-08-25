# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared scanning primitives for the deployment-script guards (#14518).

The inline-Python guards grew three layers — imports resolve, the calls they
make are the right ones, and what a failed check REPORTS is honest — and each
layer scans the same shell trees for the same two ``python3 -c`` shapes. The
block regexes and the tree walk live here so both guard modules read the
scripts through one extractor: a regex that stops matching must fail every
layer at once, never quietly narrow one of them.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts"

# Two real shapes, and the delimiter matters more than it looks. A naive
# `python3 -c "(.*?)"` stops at the first quote *inside* the Python (these blocks
# contain `database="main"`), and keying on what follows the closing quote —
# `2>`, `>`, `||` — silently broke the moment output suppression was removed from
# these very scripts, collapsing seven blocks into one unparseable blob that the
# SyntaxError branch then skipped. The guard went green while checking nothing.
#
# A multi-line block therefore closes on a quote that is alone at the start of a
# line, which is unambiguous regardless of what follows it.
PY_BLOCK_MULTILINE = re.compile(r'python3 -c "\n(.*?)\n"', re.S)
# ...and a single-line block cannot contain a quote or a newline at all.
PY_BLOCK_INLINE = re.compile(r'python3 -c "([^"\n]+)"')

# #15047 moved `validate_access_control.sh` off the two shapes above: the program
# now arrives as a QUOTED heredoc assigned to a variable, and a `run_python_check`
# helper runs it. Both shapes were invisible to the extractor, so the guard read
# one block — the helper's own `python3 -c "$1"` — for the entire script, and the
# discovery floors are what caught it.
PY_HEREDOC = re.compile(r"<<'PY'\n(.*?)\nPY\n", re.S)
PY_RUNNER_CALL = re.compile(r'run_python_check "([^"\n]*)"')

# The shapes the SHELL interpolates before python ever sees them. A `<<'PY'`
# heredoc is quoted, so a backtick inside it is a literal backtick and belongs
# nowhere near the command-substitution detector — which is exactly why moving a
# program into one is the fix for that class of defect.
PY_BLOCK_PATTERNS = (PY_BLOCK_MULTILINE, PY_BLOCK_INLINE, PY_RUNNER_CALL)

# `"$1"` inside the runner and `"${program}"` at each call site name a program
# defined elsewhere. Counting them as programs credits the guard with reading
# source it has not seen, and they never parse as Python.
_INDIRECTION = re.compile(r"^\$\{?\w+\}?$")


def shell_scripts() -> list[Path]:
    """Every deployment shell script, in a stable order."""
    return sorted(p for p in SCRIPT_DIR.rglob("*.sh"))


def python_programs(text: str) -> list[str]:
    """The source of every inline python program in ``text``, across all shapes.

    Shell indirections are dropped: what they name is extracted from wherever it
    is actually written, so keeping them would double-count and drag an
    unparseable ``$1`` through every parse floor.
    """
    programs: list[str] = []
    for pattern in (PY_BLOCK_MULTILINE, PY_BLOCK_INLINE, PY_RUNNER_CALL, PY_HEREDOC):
        programs += [m.group(1) for m in pattern.finditer(text) if not _INDIRECTION.match(m.group(1).strip())]
    return programs


def embedded_python(script: Path) -> list[str]:
    """The source of every inline python program in ``script``."""
    return python_programs(script.read_text(encoding="utf-8", errors="replace"))


def count_blocks(text: str) -> int:
    """How many shell-interpolated python invocation sites ``text`` contains."""
    return sum(len(pattern.findall(text)) for pattern in PY_BLOCK_PATTERNS)
