#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pre-commit hook: reject shell files exceeding MAX_LINES lines (#17353).

Shell had no size gate of any kind. Python has had one since #5060, with a
ratchet since #14236, so `.py` files cannot grow past a recorded ceiling —
while `scripts/lib/hardcoded-value-rules.sh`, the rule set BOTH the repo-wide
scan and the pre-commit hook read, went 787 -> 842 lines in a single PR with
nothing to say about it. The gate that can say no shapes the change; the one
that does not exist does not.

The ratchet has the same three-way semantics as the Python one, and turns one
way only:

* above its ceiling      -> fail; a grandfathered file may not grow
* below its ceiling      -> fail; lower the ceiling to the count just achieved
* at or below MAX_LINES  -> fail; delete the entry, the file is compliant

"Below its ceiling -> fail" is the part that looks wrong and is not: an
unlowered ceiling re-licenses the lines just cut, so a shrink that is not
recorded is a shrink that can be spent again.

A file that cannot be read is a violation, not a skip. `count_lines` returns
None for missing, unreadable, not-a-file and not-UTF-8 alike, and None means
"never measured" — which is a different claim from "within the limit", and only
the second one is what exit 0 is entitled to report.

DELIBERATE DIVERGENCE FROM THE PYTHON GATE — the exclusions.
`check_python_file_size.py` excludes `autobot-infrastructure/`. Inheriting that
here would drop 6 of the 10 oversized shell files, including four of the five
that motivated this gate, and the gate would ship green having checked almost
nothing. Python can afford that exclusion because little Python lives there.
Shell cannot: infrastructure is WHERE SHELL LIVES, and deployment scripts are
the code with the least type checking and the most operational consequence.
So this gate excludes `.worktrees/` only. See ARCHITECTURE_EXCEPTIONS.md.

Splitting the grandfathered files is not this hook's job. It only stops them
growing while that happens.
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
import sys

# Plain stdlib logging, deliberately (#1082). This runs as a bare script on
# every commit, and `autobot_shared.logging_manager` would drag config loading
# into that path — the same trade `check_python_file_size.py` takes.
logger = logging.getLogger(__name__)

# scripts/ is not a package; put the repo root on the path so the canonical
# git-env scrub is importable when this runs as a bare hook.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from autobot_shared.paths import scrubbed_git_env  # noqa: E402

MAX_LINES = 600

#: Repo-relative path of this hook, quoted in every message that asks for an edit.
SELF_REL = "scripts/check_shell_file_size.py"

#: The ratchet test holding RATCHET_BASELINE, the second copy of these numbers.
#: A ceiling lowered in one file alone leaves the other holding the old size,
#: and the gap between them is spendable (#14498).
RATCHET_REL = "repo_tests/shell_file_size_ratchet_baseline.py"

#: Prefixes this gate does not cover, mirrored from its own `exclude:` in
#: `.pre-commit-config.yaml`. The tree walk runs independently of pre-commit,
#: so without this it would flag files pre-commit was never configured to gate.
#: Narrower than the Python gate's on purpose — see the module docstring.
EXCLUDED_PREFIXES = (".worktrees/",)

#: Floor for the tree walk: a walk that silently stopped reaching the tree
#: would report on almost nothing and call that a clean run. 216 tracked `.sh`
#: files at the time of writing; this is the "did not look" tripwire, not a
#: target (MEASUREMENT_DISCIPLINE.md).
MIN_TRACKED_SH_FILES = 180

#: Grandfathered files: over MAX_LINES when this gate landed, mapped to the
#: line count recorded for each. THIS MAPPING ONLY SHRINKS. Never add an entry
#: to make a new file pass — split the file. Mirrored in RATCHET_REL; lower an
#: entry in both in the same commit.
#:
#: Ten entries, not the 509 the Python gate had to carry, which is why they sit
#: inline here rather than in a sibling data module.
KNOWN_LARGE: dict[str, int] = {
    "autobot-infrastructure/autobot-slm-backend/scripts/bootstrap-slm.sh": 652,
    "autobot-infrastructure/shared/scripts/bulletproof-frontend/zero-downtime-update.sh": 614,
    "autobot-infrastructure/shared/scripts/cleanup-disk-space.sh": 838,
    "autobot-infrastructure/shared/scripts/deployment/validate_access_control.sh": 659,
    "autobot-infrastructure/shared/scripts/install-bare-metal.sh": 882,
    "autobot-infrastructure/shared/scripts/install-slm.sh": 822,
    "autobot-slm-backend/ansible/deploy.sh": 718,
    "install.sh": 1265,
    "scripts/lib/hardcoded-value-rules.sh": 842,
    "scripts/pr-preflight.sh": 818,
}


def configure_logging() -> None:
    """Send findings to stdout as plain lines, once."""
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def repo_root() -> pathlib.Path:
    """Repo root derived from this file, never from the caller's cwd."""
    return pathlib.Path(__file__).resolve().parents[1]


def normalise(path: str) -> str:
    """Forward-slash repo-relative form used as the KNOWN_LARGE key."""
    return str(path).replace("\\", "/")


def count_lines(path: pathlib.Path) -> int | None:
    """Line count for *path*, or None when it cannot be read.

    ``UnicodeDecodeError`` is not an ``OSError`` and is raised lazily as the
    generator is consumed — still inside this ``try``, so one undecodable file
    cannot abort the whole audit.
    """
    try:
        with path.open(encoding="utf-8") as handle:
            return sum(1 for _ in handle)
    except (OSError, UnicodeDecodeError):
        return None


def tracked_shell_files(root: pathlib.Path) -> list[str]:
    """In-scope, git-tracked ``*.sh`` paths under *root*, relative to it.

    Git-tracked so the walk can only see what pre-commit could have staged; a
    stray local script cannot masquerade as a repo file.
    """
    out = subprocess.run(  # nosec B603 B607  # fixed argv, no shell, no caller input
        ["git", "ls-files", "*.sh"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        # An inherited GIT_DIR outranks `cwd=` and would enumerate another
        # checkout's index while *root* names this one (#14896).
        env=scrubbed_git_env(),
    )
    return [line for line in out.stdout.splitlines() if line.strip() and not line.startswith(EXCLUDED_PREFIXES)]


def _grandfathered_verdict(rel: str, line_count: int, ceiling: int) -> str | None:
    """Violation message for a KNOWN_LARGE file, or None when it is at ceiling."""
    if line_count <= MAX_LINES:
        return (
            f"{rel}: {line_count} lines — now within the {MAX_LINES}-line limit. "
            f"Delete its KNOWN_LARGE entry in {SELF_REL} and its RATCHET_BASELINE "
            f"entry in {RATCHET_REL}: an entry naming a compliant file exempts "
            "nothing while looking authoritative."
        )
    if line_count > ceiling:
        return (
            f"{rel}: {line_count} lines, over its recorded ceiling of {ceiling}. "
            "A grandfathered file may not grow — the exemption freezes the size "
            "it was granted for, it does not license more."
        )
    if line_count < ceiling:
        return (
            f"{rel}: {line_count} lines, under its recorded ceiling of {ceiling}. "
            f"Lower the ceiling to {line_count} in {SELF_REL} and the matching "
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
        return (
            f"{rel}: {line_count} lines (max {MAX_LINES}). Split it — do not add "
            f"a KNOWN_LARGE entry in {SELF_REL}, which grandfathers what already "
            "existed and is not a way in for new files."
        )
    return None


def unmeasured(rel: str) -> str:
    """Violation message for a file that could not be read at all."""
    return (
        f"{rel}: could not be read, so its size was never measured. This is not "
        "a size violation — check the path, its permissions, whether it is a "
        "broken symlink, and whether it decodes as UTF-8. An unmeasured file "
        "is not a passing one."
    )


def _vanished_entry_problem(rel: str, root: pathlib.Path) -> str:
    """Message for a KNOWN_LARGE entry the tree walk never reached."""
    return (
        f"{rel}: not found by the tracked-file walk under {root} — this entry "
        f"(ceiling {KNOWN_LARGE[rel]}) names a file that moved or was deleted. "
        f"Remove it from {SELF_REL} and its RATCHET_BASELINE entry in {RATCHET_REL}."
    )


def _scan_tracked_files(root: pathlib.Path, tracked: list[str]) -> tuple[int, set[str], list[str]]:
    """Rule on every readable file in *tracked*. Returns (reached, seen, problems).

    ``reached`` counts files actually read off disk, not ``len(tracked)``: a
    file this hook could not open must not inflate the floor check in
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
    """Rule on every in-scope tracked shell file, not just KNOWN_LARGE's keys.

    Walking the tree rather than ``KNOWN_LARGE.items()`` is the point: a
    dict-only scan can only re-check a file someone already added, so a file
    that grows past MAX_LINES without ever being added stays invisible to
    every run forever. Entries the walk never reaches are still reported.
    """
    root = repo_root()
    reached, seen, problems = _scan_tracked_files(root, tracked_shell_files(root))
    for rel in sorted(set(KNOWN_LARGE) - seen):
        problems.append(_vanished_entry_problem(rel, root))
    return reached, problems


def run_audit() -> int:
    """``--audit-ceilings``: walk the tree, and assert the walk actually reached it."""
    reached, problems = audit_ceilings()
    if reached < MIN_TRACKED_SH_FILES:
        logger.info(
            "shell size audit reached only %d tracked file(s), below the floor of %d. "
            "The walk is not covering the tree, so a clean result here would assert "
            "nothing. Check EXCLUDED_PREFIXES in %s and that `git ls-files` works "
            "from the repo root.",
            reached,
            MIN_TRACKED_SH_FILES,
            SELF_REL,
        )
        return 1
    for problem in problems:
        logger.info("%s", problem)
    logger.info("shell size audit: %d file(s) reached, %d problem(s).", reached, len(problems))
    return 1 if problems else 0


def check_paths(paths: list[str]) -> int:
    """The commit path: rule on the staged files pre-commit passed in."""
    root = repo_root()
    problems: list[str] = []
    for raw in paths:
        rel = normalise(raw)
        if rel.startswith(EXCLUDED_PREFIXES):
            continue
        line_count = count_lines(root / rel)
        if line_count is None:
            problems.append(unmeasured(rel))
            continue
        message = verdict(rel, line_count)
        if message is not None:
            problems.append(message)
    for problem in problems:
        logger.info("%s", problem)
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for both the hook path and ``--audit-ceilings``."""
    configure_logging()
    parser = argparse.ArgumentParser(description="Reject oversized shell files (#17353).")
    parser.add_argument("--audit-ceilings", action="store_true", help="walk every tracked .sh file")
    parser.add_argument("paths", nargs="*", help="staged files, as pre-commit passes them")
    args = parser.parse_args(argv)
    if args.audit_ceilings:
        return run_audit()
    return check_paths(args.paths)


if __name__ == "__main__":
    sys.exit(main())
