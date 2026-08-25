#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pre-commit hook: reject Python files exceeding MAX_LINES lines.

Extracted from orchestrator.py (#5060) to prevent god-module regressions.

Files in KNOWN_LARGE were already over the limit when the guard landed. Each
now carries a **ceiling** — the line count recorded when it was last measured —
so the exemption is a ratchet instead of a blank cheque (#14236).

Before the ceilings existed the entries were bare names, and the comment
promising they were "under active decomposition" was never checked by anything:
``orchestrator.py`` grew from the 779 lines noted beside it to 1114, and the
other two, which never had a recorded size at all, reached 4068 and 4063 —
6.8x the limit — while the hook reported all three clean. A measurement that
lives only in a comment is not an assertion.

The ratchet turns one way only:

* above its ceiling      -> fail; a grandfathered file may not grow
* below its ceiling      -> fail; lower the ceiling to the count just achieved
* at or below MAX_LINES  -> fail; delete the entry, the file is compliant

Every lowering is mirrored in ``RATCHET_BASELINE`` in the ratchet test, so the
shrink is locked in rather than left as headroom to regrow into (#14498).

A file the hook cannot open is a violation too, not a skip (#14975). ``None``
from ``count_lines`` means "never measured", which is a different thing from
"within the limit", and only the second one is what exit 0 reports.

``--audit-ceilings`` applies those rules to every entry regardless of what is
staged, so an entry cannot sit here exempting nothing after the file it names
has shrunk, moved, or been deleted. It reports how many entries it reached,
because a scan that has silently stopped matching otherwise passes having
asserted nothing.

Decomposing the grandfathered files is out of scope here — that is #5060's
campaign. This hook only stops them growing while it happens.
"""

from __future__ import annotations

import logging
import pathlib
import sys

# Plain stdlib logging, deliberately (#1082). This is a pre-commit hook: it runs
# as a bare script on every commit, and `autobot_shared.logging_manager` would
# drag config loading into that path. The same trade is taken in
# `autobot_shared/user_management/password_epoch.py`, and it is what CLAUDE.md's
# pattern table allows for exactly this case.
logger = logging.getLogger(__name__)

MAX_LINES = 600

#: Repo-relative path of this hook, quoted in the messages that ask for an edit.
SELF_REL = "scripts/check_python_file_size.py"

#: The ratchet test holding RATCHET_BASELINE, the second copy of these numbers.
#: Every message that asks for an edit here names it too: a ceiling lowered in
#: one file alone leaves the other holding the old size (#14498).
RATCHET_REL = "repo_tests/python_file_size_ratchet_test.py"

# Grandfathered files: over MAX_LINES before the guard existed, mapped to the
# line count recorded for each. THIS MAPPING ONLY SHRINKS — entries leave when
# the file reaches MAX_LINES, and a ceiling may be lowered but never raised.
# Never add an entry to make a new file pass; split the file instead.
# ``repo_tests/python_file_size_ratchet_test.py`` holds both directions, and its
# ``RATCHET_BASELINE`` is the second copy of these numbers: lower an entry here
# and lower it there in the same commit (#14498), or the lines just cut stay
# spendable in the gap between the two.
KNOWN_LARGE: dict[str, int] = {
    "autobot-backend/orchestrator.py": 1114,
    "autobot-backend/chat_workflow/manager.py": 4068,
    "autobot-backend/chat_workflow/tool_handler.py": 3694,
}


def repo_root() -> pathlib.Path:
    """Repo root derived from this file, never from the caller's cwd.

    A cwd-relative walk answers confidently and wrongly when the hook is run
    from a subdirectory.
    """
    return pathlib.Path(__file__).resolve().parents[1]


def normalise(path: str) -> str:
    """Forward-slash repo-relative form used as the KNOWN_LARGE key."""
    return str(path).replace("\\", "/")


def count_lines(path: pathlib.Path) -> int | None:
    """Line count for *path*, or None when it cannot be read."""
    try:
        with path.open(encoding="utf-8") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return None


def _grandfathered_verdict(rel: str, line_count: int, ceiling: int) -> str | None:
    """Violation message for a KNOWN_LARGE file, or None when it is at ceiling."""
    if line_count <= MAX_LINES:
        return (
            f"{rel}: {line_count} lines — now within the {MAX_LINES}-line limit. "
            f"Delete its KNOWN_LARGE entry in {SELF_REL}, and its RATCHET_BASELINE "
            f"entry in {RATCHET_REL}: an entry naming a compliant file exempts "
            "nothing while looking authoritative."
        )
    if line_count > ceiling:
        return (
            f"{rel}: {line_count} lines, over its recorded ceiling of {ceiling}. "
            "A grandfathered file may not grow (#14236) — the exemption freezes "
            "the size it was granted for, it does not license more."
        )
    if line_count < ceiling:
        return (
            f"{rel}: {line_count} lines, under its recorded ceiling of {ceiling}. "
            f"Lower the ceiling to {line_count} in {SELF_REL}, and the matching "
            f"RATCHET_BASELINE entry in {RATCHET_REL} — the ratchet only turns "
            "down, and an unlowered ceiling re-licenses the lines just cut."
        )
    return None


def verdict(rel: str, line_count: int) -> str | None:
    """Violation message for *rel* at *line_count* lines, or None if acceptable."""
    ceiling = KNOWN_LARGE.get(normalise(rel))
    if ceiling is not None:
        return _grandfathered_verdict(rel, line_count, ceiling)
    if line_count > MAX_LINES:
        return f"{rel}: {line_count} lines (max {MAX_LINES})"
    return None


def unmeasured(rel: str) -> str:
    """Violation message for an argument that could not be read at all.

    ``count_lines`` returns None for "missing", "unreadable" and "not a file"
    alike, and ``audit_ceilings`` already treats that None as a finding. This is
    the same verdict on the commit path, which used to skip past it: exit 0 is
    only entitled to mean *within the limit*, and a file that was never opened
    has not earned that (#14975).
    """
    return (
        f"{rel}: could not be read, so its size was never measured. This is not "
        "a size violation — check the path, its permissions, and whether it is a "
        "broken symlink. An unmeasured file is not a passing one."
    )


def audit_ceilings() -> tuple[int, list[str]]:
    """Check every KNOWN_LARGE entry against the file it names.

    Returns ``(entries_reached, problems)``. ``entries_reached`` is counted from
    reading the file off disk, not from the string lookup ``verdict`` uses, so a
    key that no longer matches anything cannot report a clean scan of nothing.
    """
    root = repo_root()
    reached = 0
    problems: list[str] = []
    for rel, ceiling in sorted(KNOWN_LARGE.items()):
        line_count = count_lines(root / rel)
        if line_count is None:
            problems.append(
                f"{rel}: unreadable under {root} — this entry (ceiling {ceiling}) "
                f"names a file that moved or was deleted. Remove it from {SELF_REL}."
            )
            continue
        reached += 1
        message = verdict(rel, line_count)
        if message is not None:
            problems.append(message)
    return reached, problems


def configure_logging() -> None:
    """Attach a stderr handler so findings actually reach the developer.

    Run as a bare script the module logger has no handler, and logging's
    ``lastResort`` fallback emits WARNING and above only — the informational
    "all live" line would vanish silently. Findings themselves are logged at
    ERROR precisely so they survive even when this was never called.
    """
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


def run_audit() -> int:
    """``--audit-ceilings``: repo-wide drift check over KNOWN_LARGE."""
    reached, problems = audit_ceilings()
    expected = len(KNOWN_LARGE)
    if reached != expected:
        problems.append(
            f"reach check: read {reached} of {expected} KNOWN_LARGE entries — the "
            "scan did not reach every entry, so its verdict covers nothing."
        )
    if problems:
        logger.error("%s", "\n".join(problems))
        return 1
    logger.info("python-file-size ceilings: %d entries, all live and at size.", expected)
    return 0


def main(argv: list[str]) -> int:
    configure_logging()
    if "--audit-ceilings" in argv:
        return run_audit()

    violations = []
    for arg in argv:
        rel = normalise(arg)
        line_count = count_lines(pathlib.Path(arg))
        if line_count is None:
            violations.append(unmeasured(rel))
            continue
        message = verdict(rel, line_count)
        if message is not None:
            violations.append(message)

    if violations:
        logger.error("%s", "\n".join(violations))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
