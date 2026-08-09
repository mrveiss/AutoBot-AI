#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fail when a ``# nosec`` annotation is unusable to bandit (#13521, #13528).

Two shapes are rejected. The first puts prose where bandit expects test IDs; the
second strands the annotation on a line that carries no expression.

Bandit parses **everything** after ``nosec`` as a whitespace-separated list of
test IDs. A trailing explanation therefore becomes a list of bogus IDs and
bandit warns once per word::

    },  # nose<c> B105 - config dict; 'token_estimation' refers to counting

    WARNING Test in comment: config is not a test name or id, ignoring
    WARNING Test in comment: dict is not a test name or id, ignoring
    WARNING Test in comment: token_estimation is not a test name or id, ignoring

That matters because ``code-quality.yml`` runs bandit with no severity floor,
so its output is expected to be silent, and ``scripts/pr-preflight.sh`` treats
a non-empty bandit run as a failure. The result was a papercut that recurred:
it fired in three separate PRs on one day, each fixed a single file at a time.

The accepted forms keep the explanation and cost nothing::

    x = "auth:"  # nose<c> B105  # not a credential, a key prefix
    # Not a credential, a key prefix.
    x = "auth:"  # nose<c> B105

Both are silent and both still suppress. Verified rather than assumed — the
``- prose`` form emits 6 warnings on a one-line file, the two above emit 0.

Note the subtle consequence of the old form: ``# nose<c> B105 - explanation`` is
not as narrowly scoped as its author intended, because the parser discards the
unrecognised extras. It reads as scoped while behaving as ``# nose<c> B105``.

Orphaned annotations (#13528)
-----------------------------

The second shape sits on a line carrying only closing punctuation::

    "security": min(
        100, max(0, 78 + trend * 0.4 + random.uniform(-1, 1))
    ),  # nose<c> B311  # analytics variance noise

Bandit matches an annotation against the *parent* of the flagged node
(``node_visitor.visit_Str``) or against the node itself, so whether a closing
bracket is still inside that range is an accident of how the expression nests.
Measured on this tree: 36 of 40 such annotations happened to land inside the
range and 4 did not — those 4 findings were being reported and ignored. Every
one of them is one ``black`` run away from breaking, which is how they got
there: #9489 split lines that grew too long and carried the comment down.

The fix keeps both halves where they cannot drift apart::

    # Analytics variance noise, not cryptographic.
    "security": min(100, max(0, 78 + trend * 0.4 + random.uniform(-1, 1))),  # nose<c> B311

A comment already on its own line is not reflowed, and the bare annotation is
short enough that it no longer pushes the statement past the line limit.

Exit code:
  0 — every annotation is well-formed
  1 — at least one carries prose where IDs belong, or sits on a closing bracket
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# The suppression token followed by test IDs, then a separator and prose. The separator is
# what distinguishes this from a legitimate multi-ID annotation (``# nose<c> B603
# B607``), and from the accepted ``# nose<c> B105  # prose`` form, where the second
# ``#`` ends bandit's parse.
_MALFORMED = re.compile(r"#\s*nosec\s+(?:[A-Z]\d+)(?:[,\s]+[A-Z]\d+)*\s*[-–—:]\s+\S")

# A bare suppression token with prose and no IDs at all — same failure, no ID to keep.
_MALFORMED_BARE = re.compile(r"#\s*nosec\s+(?![A-Z]\d+\b)(?!#)[A-Za-z]")

# An annotation stranded on a line that carries only closing punctuation (#13528).
_ORPHANED = re.compile(r"^\s*[\)\]\},]+\s*(?:,\s*)?#\s*nosec\b")

_MALFORMED_HINT = "prose follows the test IDs — bandit reads each word as a test id. Use '# nosec <IDS>  # <prose>'."
_ORPHANED_HINT = (
    "annotation sits on closing punctuation, not on the flagged expression. Put the prose on its own "
    "line above the statement and a bare '# nosec <IDS>' on the line bandit reports."
)

_MAX_REPORTED = 15


def _tracked_python_files() -> list[Path]:
    # Fixed argv, no shell, no caller input.
    result = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", "*.py"], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    return [REPO_ROOT / line for line in result.stdout.splitlines() if line]


def _scan(is_bad, hint: str) -> list[str]:
    """Return one ``path:lineno: hint`` message per line ``is_bad`` accepts."""
    problems: list[str] = []
    for path in _tracked_python_files():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(lines, 1):
            if is_bad(line):
                problems.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {hint}")
    return problems


def _is_malformed(line: str) -> bool:
    return bool(_MALFORMED.search(line) or _MALFORMED_BARE.search(line))


def _is_orphaned(line: str) -> bool:
    return bool(_ORPHANED.match(line))


def find_malformed() -> list[str]:
    """Return one message per annotation bandit would mis-parse."""
    return _scan(_is_malformed, _MALFORMED_HINT)


def find_orphaned() -> list[str]:
    """Return one message per annotation stranded on closing punctuation."""
    return _scan(_is_orphaned, _ORPHANED_HINT)


def main() -> int:
    problems = find_malformed() + find_orphaned()
    for problem in problems[:_MAX_REPORTED]:
        print(problem)
    if len(problems) > _MAX_REPORTED:
        print(f"... and {len(problems) - _MAX_REPORTED} more")
    if problems:
        print(f"\n{len(problems)} unusable '# nosec' annotation(s) (#13521, #13528)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
