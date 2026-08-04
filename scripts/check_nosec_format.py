#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fail when a ``# nosec`` annotation puts prose where bandit expects test IDs (#13521).

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

Exit code:
  0 — every annotation is well-formed
  1 — at least one carries prose where IDs belong
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

_MAX_REPORTED = 15


def _tracked_python_files() -> list[Path]:
    # Fixed argv, no shell, no caller input.
    result = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", "*.py"], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    return [REPO_ROOT / line for line in result.stdout.splitlines() if line]


def find_malformed() -> list[str]:
    """Return one message per annotation bandit would mis-parse."""
    problems: list[str] = []
    for path in _tracked_python_files():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(lines, 1):
            if _MALFORMED.search(line) or _MALFORMED_BARE.search(line):
                problems.append(
                    f"{path.relative_to(REPO_ROOT)}:{lineno}: prose follows the test IDs — "
                    f"bandit reads each word as a test id. Use '# nosec <IDS>  # <prose>'."
                )
    return problems


def main() -> int:
    problems = find_malformed()
    for problem in problems[:_MAX_REPORTED]:
        print(problem)
    if len(problems) > _MAX_REPORTED:
        print(f"... and {len(problems) - _MAX_REPORTED} more")
    if problems:
        print(f"\n{len(problems)} malformed '# nosec' annotation(s) (#13521)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
