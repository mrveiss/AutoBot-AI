#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pre-commit hook: reject frontend files exceeding MAX_LINES lines (#17885).

`.ts` and `.vue` had **no length measurement of any kind** — not per file, not
per function. Python has had a size gate since #5060 and shell since #17353,
each with two checked-in ceiling records, a ratchet test and a parity test
between the records (#17872). The frontend had none of it, so a frontend file
did not pass a size rule: nothing asked. `SecretsManager.vue` stood at 2947
lines, 4.9x the limit an equivalent `.py` file would have been refused at, and
no instrument in the tree had an opinion about it.

THE CEILINGS WERE MEASURED, NOT CHOSEN. The first walk found 184 of 1779
in-scope tracked files over MAX_LINES; each is grandfathered at the size it
was measured at, in ``scripts/frontend_file_size_known_large.py``. MAX_LINES
itself is inherited from the two existing gates rather than picked for this
one — a third value would have made "600" mean three things.

The ratchet has the same three-way semantics as the other two gates, and turns
one way only:

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

GENERATED OUTPUT IS EXCLUDED BY PREFIX, NOT BY SPECIAL CASE. The two
``src/types/generated/`` trees hold OpenAPI-derived clients — 178894 and 26584
lines — which no human edits and no split would help. They are named in
``EXCLUDED_PREFIXES`` below and mirrored in this hook's ``exclude:`` in
``.pre-commit-config.yaml``; the ratchet test parses that YAML independently
and asserts the two agree, so the exclusion is a recorded decision rather than
an ``if`` buried in the walk.

FUNCTION LENGTH IS DELIBERATELY NOT HERE. `function-length-check` stays
Python-only, and the reason is recorded at that hook in
`.pre-commit-config.yaml` rather than inferred from this gate's silence.

Splitting the grandfathered files is not this hook's job. It only stops them
growing while that happens.
"""

from __future__ import annotations

import argparse
import importlib.util
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
SELF_REL = "scripts/check_frontend_file_size.py"

#: The DATA module holding RATCHET_BASELINE, the second copy of these numbers.
#: A ceiling lowered in one file alone leaves the other holding the old size,
#: and the gap between them is spendable (#14498). Names the data module, not a
#: test that re-exports it: a developer told to lower "the matching
#: RATCHET_BASELINE entry" must open a file with entries in it (#17872).
RATCHET_REL = "repo_tests/frontend_file_size_ratchet_baseline.py"

#: Repo-relative path prefixes this gate does not cover, mirrored from its own
#: `exclude:` in `.pre-commit-config.yaml`. The tree walk runs independently of
#: pre-commit, so without this it would flag files pre-commit was never
#: configured to gate. ``test_excluded_prefixes_mirror_the_pre_commit_config``
#: parses the YAML independently to catch exactly that drift.
#:
#: The two ``types/generated/`` trees are OpenAPI-derived clients, regenerated
#: from the backend schema and never hand-edited. Excluding them is the only
#: judgement in this file, and it is recorded here rather than applied as a
#: special case inside the walk.
EXCLUDED_PREFIXES = (
    ".worktrees/",
    "autobot-frontend/src/types/generated/",
    "autobot-slm-frontend/src/types/generated/",
)

#: Suffixes this gate measures. `.vue` is in because a single-file component is
#: where frontend length actually accumulates — 152 of the 184 oversized files
#: are `.vue`, so a `.ts`-only gate would have reported on a sixth of the
#: problem and called it coverage.
TRACKED_GLOBS = ("*.ts", "*.vue")

#: Floor for the tree walk: a walk that silently stopped reaching the tree
#: would report on almost nothing and call that a clean run. 1779 in-scope
#: tracked files at the time of writing; this is the "did not look" tripwire,
#: not a target (MEASUREMENT_DISCIPLINE.md).
MIN_TRACKED_FRONTEND_FILES = 1500


def _load_known_large() -> dict[str, int]:
    """Load KNOWN_LARGE from its sibling data module, by path.

    Loaded by path rather than a plain ``import`` so this still resolves when
    the hook itself is loaded via ``importlib.util`` (as the ratchet and parity
    tests do), not only when it is run directly.
    """
    path = pathlib.Path(__file__).resolve().parent / "frontend_file_size_known_large.py"
    spec = importlib.util.spec_from_file_location("_frontend_file_size_known_large", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.KNOWN_LARGE


#: Grandfathered files: over MAX_LINES when this gate landed, mapped to the
#: line count measured for each. THIS MAPPING ONLY SHRINKS. Never add an entry
#: to make a new file pass — split the file. Mirrored in RATCHET_REL; lower an
#: entry in both in the same commit.
KNOWN_LARGE: dict[str, int] = _load_known_large()


def configure_logging() -> None:
    """Attach a stderr handler so findings actually reach the developer.

    Run as a bare script the module logger has no handler, and logging's
    ``lastResort`` fallback emits WARNING and above only -- the informational
    "all live" line would vanish silently. Findings themselves are logged at
    ERROR precisely so they survive even when this was never called, which is
    why the levels below are not interchangeable with INFO.
    """
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


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


def tracked_frontend_files(root: pathlib.Path) -> list[str]:
    """In-scope, git-tracked ``*.ts``/``*.vue`` paths under *root*, relative to it.

    Git-tracked so the walk can only see what pre-commit could have staged; a
    stray local file cannot masquerade as a repo file, and an untracked
    ``node_modules`` cannot drown the measurement.
    """
    out = subprocess.run(  # nosec B603 B607  # fixed argv, no shell, no caller input
        ["git", "ls-files", *TRACKED_GLOBS],
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
    """Violation message for an argument that could not be read at all.

    ``count_lines`` returns None for "missing", "unreadable", "not a file" and
    "not UTF-8" alike, and ``audit_ceilings`` already treats that None as a
    finding -- the walk skips such a file rather than counting it toward its
    reach floor, for the same reason. This is the same verdict on the commit
    path: exit 0 is only entitled to mean *within the limit*, and a file that
    was never opened has not earned that (#14975).
    """
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


def _report_unmeasured(rel: str, seen: set[str], problems: list[str]) -> None:
    """Report a file that could not be read, and record it as SEEN but not REACHED.

    NOT a skip (#14975). ``seen`` answers "did the walk find this path", which it did,
    so the ``KNOWN_LARGE - seen`` pass in ``audit_ceilings`` must not ALSO call it
    moved-or-deleted -- that message is wrong for a file that exists and cannot be read,
    and reporting both tells the developer two stories about one file. ``reached`` stays
    exclusive, so an unmeasured file cannot prop up the floor check in ``run_audit``
    without having been ruled on (#17377).
    """
    problems.append(unmeasured(rel))
    seen.add(normalise(rel))


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
            _report_unmeasured(rel, seen, problems)
            continue
        reached += 1
        seen.add(normalise(rel))
        message = verdict(rel, line_count)
        if message is not None:
            problems.append(message)
    return reached, seen, problems


def audit_ceilings() -> tuple[int, list[str]]:
    """Rule on every in-scope tracked frontend file, not just KNOWN_LARGE's keys.

    Walking the tree rather than ``KNOWN_LARGE.items()`` is the point: a
    dict-only scan can only re-check a file someone already added, so a file
    that grows past MAX_LINES without ever being added stays invisible to
    every run forever. Entries the walk never reaches are still reported.
    """
    root = repo_root()
    reached, seen, problems = _scan_tracked_files(root, tracked_frontend_files(root))
    for rel in sorted(set(KNOWN_LARGE) - seen):
        problems.append(_vanished_entry_problem(rel, root))
    return reached, problems


def _reach_breach_problem(reached: int) -> str:
    """The reach-breach finding, worded identically in all three gates (#17377)."""
    return (
        f"reach check: the tree walk reached {reached} tracked file(s), under the "
        f"{MIN_TRACKED_FRONTEND_FILES}-file floor — it stopped covering the tree, so this "
        f"run's verdict covers almost nothing. Check EXCLUDED_PREFIXES in {SELF_REL} "
        "and that `git ls-files` works from the repo root."
    )


def run_audit() -> int:
    """``--audit-ceilings``: walk the tree, and assert the walk actually reached it."""
    reached, problems = audit_ceilings()
    if reached < MIN_TRACKED_FRONTEND_FILES:
        # Collected, not returned on. A run that is BOTH under-reaching and carrying
        # violations used to report only the reach -- and the reach breach is the more
        # alarming of the two precisely because it explains the other, so suppressing
        # the violations hid the evidence of what the short walk missed.
        problems.append(_reach_breach_problem(reached))
    if problems:
        logger.error("%s", "\n".join(problems))
        return 1
    logger.info(
        "frontend-file-size ceilings: %d file(s) scanned, %d grandfathered, all live and at size.",
        reached,
        len(KNOWN_LARGE),
    )
    return 0


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
    if problems:
        # ERROR, not INFO: this is the COMMIT path, so a finding here blocks a push.
        # Logged below `lastResort`'s WARNING threshold it would vanish on any path
        # that never called `configure_logging`, leaving a hook that refuses the push
        # and says nothing about why.
        logger.error("%s", "\n".join(problems))
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for both the hook path and ``--audit-ceilings``."""
    configure_logging()
    parser = argparse.ArgumentParser(description="Reject oversized .ts/.vue files (#17885).")
    parser.add_argument("--audit-ceilings", action="store_true", help="walk every tracked .ts/.vue file")
    parser.add_argument("paths", nargs="*", help="staged files, as pre-commit passes them")
    args = parser.parse_args(argv)
    if args.audit_ceilings:
        return run_audit()
    return check_paths(args.paths)


if __name__ == "__main__":
    sys.exit(main())
