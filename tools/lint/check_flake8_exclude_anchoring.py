#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14419 — every ``.flake8`` exclude entry must mean the path it was written for.

flake8 normalises an exclude entry containing a path separator into an absolute
path rooted at the config file's directory and matches it against a candidate's
absolute path. An entry with **no** separator is matched against the candidate's
*basename*, so a bare name prunes every directory of that name at any depth.

Written as bare names, the list pruned 973 tracked ``*.py`` files no entry was
written for — three production packages called ``monitoring``, the
``autobot-backend/tools/`` tool-registry subsystem, and the SDK's
``autobot_sdk/resources/`` among them. Nothing reported them as unlinted.

The invariant:

* a bare entry is allowed only if it is a listed build/VCS/runtime artifact
  directory **and** covers no tracked Python — so the allowlist cannot become
  the new hiding place;
* every other entry must be anchored, and must name a directory that exists —
  an entry stranded by a rename exempts nothing while looking authoritative.

WHY THIS IS A SCRIPT AND NOT ONLY A TEST. The guard has to run in a check that
can block a merge, and the direction of this failure is what makes that matter:
re-adding a bare name lints *fewer* files, so a lint job reports **fewer**
violations and goes greener. Nothing about the required checks would notice.
``.github/workflows/code-quality.yml`` therefore calls this module with
``--audit-excludes``, the same shape as ``check_python_file_size.py
--audit-ceilings`` and ``check_extension_import_boundaries.py
--audit-baseline``. ``repo_tests/flake8_exclude_anchoring_test.py`` imports
these functions rather than restating them, so the decision has one definition.

The audit reports how many entries it reached, because a scan that has silently
stopped matching otherwise passes having asserted nothing.
"""

from __future__ import annotations

import argparse
import configparser
import logging
import pathlib
import re
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
import sys

# Plain stdlib logging, deliberately (#1082). This runs as a bare script inside
# a lint job, and `autobot_shared.logging_manager` would drag config loading
# into that path. Same trade as `scripts/check_python_file_size.py` and
# `autobot_shared/user_management/password_epoch.py`; it is what CLAUDE.md's
# pattern table allows for exactly this case.
logger = logging.getLogger(__name__)

#: Repo-relative path of this checker, quoted in the messages that ask for an edit.
SELF_REL = "tools/lint/check_flake8_exclude_anchoring.py"

#: Bare names allowed to match at any depth. Each names a build, VCS or runtime
#: artifact directory holding no tracked Python, so matching by name prunes
#: artifacts and never source. THIS SET ONLY SHRINKS. Adding a name here does
#: not buy silence: :func:`entries_covering_tracked_python` re-proves the "no
#: tracked Python" half on every run, and keeps failing the day someone adds a
#: Python file under a directory a listed name matches.
ARTIFACT_DIR_NAMES = frozenset(
    {
        ".git",
        ".tox",
        "__pycache__",
        "node_modules",
        "venv",
        ".venv",
        "build",
        "dist",
        "*.egg-info",
        "temp",
        "logs",
        "reports",
        "archive",
        "archives",
        "backups",
    }
)

#: Floor for the tracked-Python enumeration. An enumeration that returns nothing
#: must not read as "no bare entry covers any source".
TRACKED_PY_FLOOR = 3000

#: Mirror of ``flake8.utils.COMMA_SEPARATED_LIST_RE``. Reimplemented rather than
#: imported so this runs wherever Python does — a guard that skips itself when a
#: dependency is missing reports clean. The test pins the mirror to the real
#: parser wherever flake8 is importable.
_SPLIT_RE = re.compile(r"[,\s]")


def repo_root() -> pathlib.Path:
    """Repo root derived from this file, never from the caller's cwd.

    A cwd-relative walk answers confidently and wrongly when run from a
    subdirectory.
    """
    return pathlib.Path(__file__).resolve().parents[2]


def split_exclude_value(value: str) -> list[str]:
    """Split an ``exclude`` option exactly as flake8 does."""
    return [item for item in (piece.strip() for piece in _SPLIT_RE.split(value)) if item]


def read_exclude_entries(config_text: str) -> list[str]:
    """Parsed ``exclude`` entries of a flake8 config given as text.

    ``RawConfigParser`` because that is what ``flake8.options.config.load_config``
    uses; interpolation would change what a ``%`` in the value means, and this
    must read what flake8 reads.
    """
    parser = configparser.RawConfigParser()
    parser.read_string(config_text)
    return split_exclude_value(parser["flake8"]["exclude"])


def load_entries(config_path: pathlib.Path | None = None) -> list[str]:
    """Exclude entries of the repo's ``.flake8`` (or a given config)."""
    path = config_path if config_path is not None else repo_root() / ".flake8"
    return read_exclude_entries(path.read_text(encoding="utf-8"))


def bare_entries(entries: list[str]) -> list[str]:
    """Entries flake8 matches against a basename, i.e. at any depth."""
    return [entry for entry in entries if "/" not in entry and "\\" not in entry]


def unanchored_source_entries(entries: list[str]) -> list[str]:
    """Bare entries that are not a sanctioned artifact name.

    The decision the guard turns on, kept separate so callers can put a
    synthetic list through it instead of asserting on the config's text.
    """
    return [entry for entry in bare_entries(entries) if entry not in ARTIFACT_DIR_NAMES]


def tracked_py_files(root: pathlib.Path | None = None) -> list[str]:
    """Every tracked ``*.py`` path, enumerated by git rather than by flake8."""
    completed = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "*.py"],
        cwd=root if root is not None else repo_root(),
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in completed.stdout.splitlines() if line.strip()]


def entries_covering_tracked_python(entries: list[str], tracked: list[str]) -> dict[str, int]:
    """Bare entries that prune tracked Python, mapped to how many files.

    ``fnmatch`` is not needed: flake8 compares a bare entry to a directory's
    basename, so a path component equal to the entry is exactly a hit.
    """
    counts: dict[str, int] = {}
    wanted = set(bare_entries(entries))
    for path in tracked:
        for component in path.split("/")[:-1]:
            if component in wanted:
                counts[component] = counts.get(component, 0) + 1
    return counts


def missing_anchored_targets(entries: list[str], root: pathlib.Path | None = None) -> list[str]:
    """Anchored entries naming no directory — they exempt nothing, silently."""
    base = root if root is not None else repo_root()
    anchored = [entry for entry in entries if entry not in bare_entries(entries)]
    return [entry for entry in anchored if not (base / entry.rstrip("/")).is_dir()]


def audit_excludes(root: pathlib.Path | None = None) -> tuple[int, list[str]]:
    """Apply the invariant to every entry in ``.flake8``.

    Returns ``(entries_reached, problems)``. ``entries_reached`` is counted from
    the parsed list so a config whose ``exclude`` has gone missing or empty
    cannot report a clean scan of nothing.
    """
    base = root if root is not None else repo_root()
    problems: list[str] = []

    entries = load_entries(base / ".flake8")
    if not entries:
        return 0, [f"{base / '.flake8'} parsed to zero exclude entries — the guard checked nothing."]

    unanchored = unanchored_source_entries(entries)
    if unanchored:
        problems.append(
            f"unanchored exclude entries {sorted(unanchored)}: flake8 matches a "
            "separator-free entry against the basename, so each prunes every "
            "directory of that name at ANY depth. Write the path the entry was "
            "meant for (`autobot-backend/tests/`, not `tests`). A trailing `# "
            "comment` inside the value also lands here, one entry per word."
        )

    tracked = tracked_py_files(base)
    if len(tracked) < TRACKED_PY_FLOOR:
        problems.append(
            f"git ls-files returned only {len(tracked)} Python files (floor "
            f"{TRACKED_PY_FLOOR}) — the enumeration broke, so the coverage "
            "check below asserted nothing."
        )
    else:
        covered = entries_covering_tracked_python(entries, tracked)
        if covered:
            problems.append(
                f"bare exclude entries cover tracked Python: {covered}. Those "
                f"files are silently unlinted. Either the entry is not an "
                f"artifact directory and must be anchored, or it does not "
                f"belong in ARTIFACT_DIR_NAMES in {SELF_REL}."
            )

    missing = missing_anchored_targets(entries, base)
    if missing:
        problems.append(
            f"exclude entries naming no directory: {sorted(missing)}. Remove "
            "them or fix the path — a dead entry cannot exclude and cannot warn."
        )

    return len(entries), problems


def configure_logging() -> None:
    """Attach a stderr handler so findings actually reach the developer.

    Run as a bare script the module logger has no handler, and logging's
    last-resort path drops anything below WARNING.
    """
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def run_audit() -> int:
    reached, problems = audit_excludes()
    if problems:
        logger.error("%s", "\n\n".join(problems))
        logger.error("\n.flake8 exclude audit FAILED over %d entries (#14419).", reached)
        return 1
    logger.info(".flake8 exclude audit clean over %d entries (#14419).", reached)
    return 0


def main(argv: list[str]) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--audit-excludes",
        action="store_true",
        help="apply the anchoring invariant to every .flake8 exclude entry",
    )
    args = parser.parse_args(argv)
    if not args.audit_excludes:
        parser.error("nothing to do — pass --audit-excludes")
    return run_audit()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
