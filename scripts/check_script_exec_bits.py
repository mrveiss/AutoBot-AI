#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fail when a shell script's mode disagrees with how the docs invoke it (#13355).

The rule is **agreement, not uniformity**. Both of these are correct:

* ``scripts/format.sh`` is mode 644 and documented as ``bash scripts/format.sh``
* ``scripts/start-services.sh`` is mode 755 and documented as
  ``scripts/start-services.sh start``

What is not correct is a script the docs tell you to run directly while its
mode forbids it — the reader gets ``Permission denied`` on a copy-pasted
command and reasonably concludes the tool is broken rather than the bit
missing. That is how ``scripts/pr-preflight.sh`` shipped in #13347 and had to
be fixed in #13348.

A direct invocation is a documented occurrence of ``scripts/<name>.sh`` that is
not preceded by ``bash``/``sh`` and is not a bare mention (prose naming the
file, a ``shellcheck source=`` directive, or a path inside a longer sentence
without arguments). Anything ambiguous is left alone: this checker only fires
when a line *runs* the script, so a false positive would need the docs to show
a command that genuinely cannot work.

Exit code:
  0 — every documented direct invocation targets an executable script
  1 — at least one disagreement
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_GLOBS = ("docs/**/*.md", "*.md", ".github/**/*.yml", ".github/**/*.yaml")

# Historical records, not instructions. A changelog entry or a finished session
# handoff describes what someone once ran; nobody copy-pastes from them, and
# rewriting history to satisfy a mode check would be worse than the mismatch.
_ARCHIVAL = ("CHANGELOG.md", ".session/")

# Enough to act on without burying the summary — one wrong mode can appear on
# a hundred lines, as start-services.sh does.
_MAX_REPORTED = 15

# A line that RUNS the script, as opposed to naming it. Two accepted shapes:
#
#   1. the path followed by whitespace and at least one argument character that
#      is not a closing quote — ``scripts/start-services.sh start``
#   2. the path standing alone at the start of a line (a code block), allowing a
#      leading prompt or indentation — ``$ scripts/cleanup-worktrees.sh``
#
# A bare backtick-wrapped mention (``see `scripts/format.sh` for the wrapper``)
# matches neither, which is the point: the first draft of this checker flagged
# six such mentions and would have taught everyone to ignore it.
#
# Shape 1 accepts either a flag (``--dry-run``, ``-v``) or a plain argument
# after the whitespace. The list-item form ``` `script.sh` - description ```
# cannot reach it, because the closing backtick occupies the position the
# whitespace would need; the dash exclusion is only for unquoted prose such as
# ``script.sh - does a thing``.
_INVOCATION_WITH_ARGS = re.compile(r"(?<![\w/.-])(?:\./)?(scripts/[\w./-]+\.sh)[ \t]+(?:-{1,2}\w|[^\s`\"'\-,.)])")
_INVOCATION_ALONE = re.compile(r"^\s*(?:[$#>]\s+)?(?:\./)?(scripts/[\w./-]+\.sh)\s*$")
# Lines where the script is handed to an interpreter rather than executed.
_INTERPRETED = re.compile(r"(?:^|[\s`\"'|(&;])(?:bash|sh|zsh|source|\.)\s+(?:\./)?scripts/")
# ``# shellcheck source=scripts/lib/x.sh`` is a directive, not an invocation.
_DIRECTIVE = re.compile(r"shellcheck\s+source=")


def _tracked_files(patterns: Iterable[str]) -> list[Path]:
    out: list[Path] = []
    for pattern in patterns:
        # Fixed argv, no shell, and `pattern` is a module constant — not input.
        result = subprocess.run(  # nosec B603 B607
            ["git", "ls-files", pattern], cwd=REPO_ROOT, capture_output=True, text=True, check=False
        )
        out.extend(REPO_ROOT / line for line in result.stdout.splitlines() if line)
    return out


def _is_executable(path: Path) -> bool:
    # Fixed argv, no shell; the path comes from git ls-files output, not a caller.
    result = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", "-s", str(path.relative_to(REPO_ROOT))],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    # "100755 <sha> 0\t<path>" — read the mode git records, not the working tree,
    # because that is what a fresh clone gets.
    return result.stdout.startswith("100755")


def find_disagreements() -> list[str]:
    """Return one message per documented direct invocation of a non-executable script."""
    problems: list[str] = []
    for doc in _tracked_files(DOC_GLOBS):
        rel_doc = str(doc.relative_to(REPO_ROOT))
        if any(rel_doc.startswith(prefix) or rel_doc == prefix for prefix in _ARCHIVAL):
            continue
        try:
            lines = doc.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(lines, 1):
            if _INTERPRETED.search(line) or _DIRECTIVE.search(line):
                continue
            hits = {m.group(1) for m in _INVOCATION_WITH_ARGS.finditer(line)}
            alone = _INVOCATION_ALONE.match(line)
            if alone:
                hits.add(alone.group(1))
            for rel in sorted(hits):
                script = REPO_ROOT / rel
                if not script.is_file() or _is_executable(script):
                    continue
                problems.append(
                    f"{doc.relative_to(REPO_ROOT)}:{lineno}: runs {rel} directly, "
                    f"but it is mode 644 — either 'git update-index --chmod=+x {rel}' "
                    f"or document it as 'bash {rel}'"
                )
    return problems


def main() -> int:
    problems = find_disagreements()
    for problem in problems[:_MAX_REPORTED]:
        print(problem)
    if len(problems) > _MAX_REPORTED:
        print(f"... and {len(problems) - _MAX_REPORTED} more (one wrong mode often appears on many lines)")
    if problems:
        scripts = sorted({p.split("runs ", 1)[1].split(" ", 1)[0] for p in problems})
        print(f"\n{len(problems)} documented invocation(s) across {len(scripts)} script(s): {', '.join(scripts)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
