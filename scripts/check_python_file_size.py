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

``--audit-ceilings`` applies those rules to every ``*.py`` file the tree walk
below reaches, not just the ones already in KNOWN_LARGE (#14547). Before this,
``audit_ceilings`` iterated ``KNOWN_LARGE.items()``, so it could re-verify a
file someone remembered to list, never discover one nobody did. A repo-wide
walk found 509 files already over MAX_LINES with no entry at all — no audit
could ever have caught them, because none of them had ever been added.
``autobot-slm-backend/services/reconciler.py`` was the one that surfaced the
gap, at over 2000 lines and absent from KNOWN_LARGE entirely. Grandfathering
all 509 at their measured size, rather than leaving the walk unable to run
until each is individually triaged, is what makes turning the walk on
possible at all — splitting them is #5060's campaign, not this one's. The
audit reports how many files it reached, because a walk that has silently
stopped covering the tree otherwise passes having asserted nothing about
most of it.

``KNOWN_LARGE`` itself now lives in ``python_file_size_known_large.py``
alongside this file, not inline here: 512 entries would put this hook over
its own MAX_LINES, and a guard cannot ask everything else to split without
doing the same to its own data.

Decomposing the grandfathered files is out of scope here — that is #5060's
campaign. This hook only stops them growing while it happens.
"""

from __future__ import annotations

import importlib.util
import logging
import pathlib
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
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

#: Repo-relative path prefixes the guard does not cover, mirrored from this
#: hook's own entry in ``.pre-commit-config.yaml`` (its ``exclude:``,
#: currently ``^(\.worktrees/|autobot-infrastructure/|autobot-backend/code_analysis/)``).
#: The tree walk in ``audit_ceilings`` runs independently of pre-commit — it
#: is the ``--audit-ceilings`` / CI path, not the staged-file path through
#: ``main`` — so without this it would flag files pre-commit was never
#: configured to gate. Widening or narrowing this hook's scope means editing
#: both in the same commit, or the two disagree about what "in scope" means;
#: ``test_excluded_prefixes_mirror_the_pre_commit_config`` in the ratchet
#: test parses the YAML independently to catch exactly that drift.
EXCLUDED_PREFIXES = (
    ".worktrees/",
    "autobot-infrastructure/",
    "autobot-backend/code_analysis/",
)

#: Floor for the tree walk in ``audit_ceilings``, the production analogue of
#: the ratchet test's own floor over its independent enumeration (#14547): a
#: walk that silently stopped reaching most of the tree would report on
#: almost nothing and call that a clean run.
MIN_TRACKED_PY_FILES = 3000


def _load_known_large() -> dict[str, int]:
    """Load KNOWN_LARGE from its sibling data module, by path.

    Loaded by path rather than a plain ``import`` so this still resolves when
    the hook itself is loaded via ``importlib.util`` (as the ratchet test
    does), not only when it is run directly as
    ``python3 scripts/check_python_file_size.py``.
    """
    path = pathlib.Path(__file__).resolve().parent / "python_file_size_known_large.py"
    spec = importlib.util.spec_from_file_location("_python_file_size_known_large", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.KNOWN_LARGE


# Grandfathered files: over MAX_LINES with no active decomposition under way,
# mapped to the line count recorded for each. THIS MAPPING ONLY SHRINKS —
# entries leave when the file reaches MAX_LINES, and a ceiling may be lowered
# but never raised. Never add an entry to make a new file pass; split the
# file instead. See ``python_file_size_known_large.py`` for the full dict and
# ``repo_tests/python_file_size_ratchet_baseline.py`` for its mirror: lower
# an entry in both in the same commit (#14498), or the lines just cut stay
# spendable in the gap between the two.
KNOWN_LARGE: dict[str, int] = _load_known_large()


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
    """Line count for *path*, or None when it cannot be read.

    ``UnicodeDecodeError`` is not an ``OSError``, and is raised lazily while
    the generator below is consumed, still inside this ``try`` — a non-UTF-8
    ``.py`` file must not crash the whole audit over one unrelated file.
    """
    try:
        with path.open(encoding="utf-8") as handle:
            return sum(1 for _ in handle)
    except (OSError, UnicodeDecodeError):
        return None


def tracked_python_files(root: pathlib.Path) -> list[str]:
    """In-scope, git-tracked ``*.py`` paths under *root*, relative to it.

    Git-tracked so the walk can only ever see what pre-commit could have
    staged — a stray local file (an accidental venv, a scratch script) can't
    masquerade as a repo file this way. ``EXCLUDED_PREFIXES`` mirrors the
    exclude patterns already carved out for this hook in
    ``.pre-commit-config.yaml``, so the audit's scope and the staged-file
    scope stay the same set of files (#14547).
    """
    out = subprocess.run(  # nosec B603 B607  # fixed argv, no shell, no caller input
        ["git", "ls-files", "*.py"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return [line for line in out.stdout.splitlines() if line.strip() and not line.startswith(EXCLUDED_PREFIXES)]


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


def _vanished_entry_problem(rel: str, root: pathlib.Path) -> str:
    """Message for a KNOWN_LARGE entry the tree walk never reached."""
    return (
        f"{rel}: not found by the tracked-file walk under {root} — this entry "
        f"(ceiling {KNOWN_LARGE[rel]}) names a file that moved or was deleted. "
        f"Remove it from {SELF_REL}, and its RATCHET_BASELINE entry in {RATCHET_REL}."
    )


def unmeasured(rel: str) -> str:
    """Violation message for an argument that could not be read at all.

    ``count_lines`` returns None for "missing", "unreadable", "not a file" and
    "not UTF-8" alike, and ``audit_ceilings`` already treats that None as a
    finding — the walk (#14547) skips such a file rather than counting it
    toward its reach floor, for the same reason. This is
    the same verdict on the commit path, which used to skip past it: exit 0 is
    only entitled to mean *within the limit*, and a file that was never opened
    has not earned that (#14975).
    """
    return (
        f"{rel}: could not be read, so its size was never measured. This is not "
        "a size violation — check the path, its permissions, whether it is a "
        "broken symlink, and whether it decodes as UTF-8. An unmeasured file "
        "is not a passing one."
    )


def _scan_tracked_files(root: pathlib.Path, tracked: list[str]) -> tuple[int, set[str], list[str]]:
    """Rule on every readable file in *tracked*. Returns (reached, seen, problems).

    ``reached`` counts files actually read off disk, not ``len(tracked)`` —
    one this hook that cannot be opened (see ``count_lines``: OSError or a
    non-UTF-8 decode failure) must not inflate the floor check in
    ``run_audit`` without ever having been ruled on.
    """
    seen: set[str] = set()
    problems: list[str] = []
    reached = 0
    for rel in sorted(tracked):
        line_count = count_lines(root / rel)
        if line_count is None:
            continue
        reached += 1
        seen.add(normalise(rel))
        message = verdict(rel, line_count)
        if message is not None:
            problems.append(message)
    return reached, seen, problems


def audit_ceilings() -> tuple[int, list[str]]:
    """Rule on every in-scope tracked Python file, not just KNOWN_LARGE's keys.

    Walking the tree (#14547) instead of ``KNOWN_LARGE.items()`` is the
    actual fix: a dict-only scan can only ever re-check a file someone
    already added to it, so a file that grows past MAX_LINES without ever
    being added stays invisible to every audit run forever — which is
    exactly how ``reconciler.py`` reached 2000+ lines unnoticed. Entries the
    walk never reaches are still reported, the same as before a rename or
    deletion left them stranded.
    """
    root = repo_root()
    reached, seen, problems = _scan_tracked_files(root, tracked_python_files(root))
    for rel in sorted(set(KNOWN_LARGE) - seen):
        problems.append(_vanished_entry_problem(rel, root))
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
    """``--audit-ceilings``: walk the tree and apply the ratchet to it.

    ``reached`` is checked against a floor, not against ``len(KNOWN_LARGE)``:
    the walk is meant to reach the whole tree (#14547), not just the
    grandfathered files, so a run that silently stopped covering most of it
    would otherwise pass having asserted almost nothing.
    """
    reached, problems = audit_ceilings()
    if reached < MIN_TRACKED_PY_FILES:
        problems.append(
            f"reach check: the tree walk reached {reached} files, under the "
            f"{MIN_TRACKED_PY_FILES}-file floor — it stopped covering most of "
            "the tree, so this run's verdict covers almost nothing."
        )
    if problems:
        logger.error("%s", "\n".join(problems))
        return 1
    logger.info(
        "python-file-size ceilings: %d files scanned, %d grandfathered, all live and at size.",
        reached,
        len(KNOWN_LARGE),
    )
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
