#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14489 — every ``.bandit`` ``exclude_dirs`` entry must mean the path it was written for.

bandit's matcher (``bandit/core/manager.py``, ``_is_file_included``) tests every
``exclude_dirs`` entry with ``x in path for x in excluded_path_strings`` — a raw
**substring** test against the full candidate path, with no path-component
boundary at all. That is broader than flake8's #14419 defect (flake8 at least
compares against ``os.path.basename()``, so it matches whole components): a
bare bandit entry excludes any path that merely *contains* the string
anywhere, including mid-filename.

Measured against ``bandit -c .bandit -r autobot-backend/ autobot-slm-backend/
autobot_shared/`` — the exact invocation ``code-quality.yml`` and
``security.yml`` run — with ``git ls-files`` as ground truth: the pre-fix bare
entries ``temp``, ``logs``, ``reports``, ``archive`` and ``venv`` silently
excluded 34 tracked production files that none of them named as a real
directory anywhere in the repo. Re-including them surfaced 3 real bandit
findings (B608 x1, B311 x2), both reviewed and suppressed at the call site
with a specific-ID ``# nosec`` and a reason.

The invariant:

* a bare (separator-free) entry is allowed only if it covers **no tracked
  Python anywhere in the repo**, tested with bandit's own substring rule —
  not a path-component or basename rule, because bandit uses neither. This is
  the divergence from #14419's flake8 guard: ``venv`` passes a
  component-based check (no directory literally named ``venv`` holds tracked
  Python) but FAILS bandit's substring check (2 tracked files carry "venv"
  only inside their filename, e.g. ``check_venv_producers.py``), so it must
  be dropped here even though flake8 could keep it;
* every other entry is anchored by wrapping it in ``/``, requiring a path
  separator on both sides. bandit never rewrites an entry the way flake8
  does (flake8 turns a separator-containing entry into an absolute path
  prefix naming one location) — a bandit entry stays a substring test, so
  ``/tests/`` still matches every ``tests/`` directory at any depth, which is
  the intent, while no longer matching ``repo_tests/`` or
  ``run_unit_tests.py``.

WHY THIS IS A SCRIPT AND NOT ONLY A TEST. The guard has to run in a check that
can block a merge, and the direction of this failure is what makes that
matter: re-adding a bare name excludes *more* files, so bandit reports
*fewer* findings and the required ``code-quality`` job goes greener. Nothing
about the required checks would otherwise notice. ``code-quality.yml``
therefore calls this module with ``--audit-excludes``, the same shape as
``check_flake8_exclude_anchoring.py --audit-excludes`` (#14419).
``repo_tests/bandit_exclude_anchoring_test.py`` imports these functions
rather than restating them, so the decision has one definition.

The audit reports how many entries it reached, because a scan that has
silently stopped matching otherwise passes having asserted nothing.
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
import sys

import yaml

# Plain stdlib logging, deliberately (#1082) — see check_flake8_exclude_anchoring.py.
logger = logging.getLogger(__name__)

#: Repo-relative path of this checker, quoted in the messages that ask for an edit.
SELF_REL = "tools/lint/check_bandit_exclude_anchoring.py"

#: Bare names allowed to match at any depth. Each names a build/VCS/runtime
#: artifact directory that covers no tracked Python anywhere in the repo,
#: tested with bandit's own substring rule (:func:`entries_covering_tracked_python`).
#: THIS SET ONLY SHRINKS. Adding a name here does not buy silence: the audit
#: re-proves the "no tracked Python" half on every run.
ARTIFACT_DIR_NAMES = frozenset({"node_modules", ".venv", "__pycache__"})

#: Floor for the tracked-Python enumeration. An enumeration that returns
#: nothing must not read as "no bare entry covers any source".
TRACKED_PY_FLOOR = 3000


def repo_root() -> pathlib.Path:
    """Repo root derived from this file, never from the caller's cwd.

    A cwd-relative walk answers confidently and wrongly when run from a
    subdirectory.
    """
    return pathlib.Path(__file__).resolve().parents[2]


def read_exclude_entries(config_text: str) -> list[str]:
    """Parsed ``exclude_dirs`` entries of a bandit config given as YAML text.

    PyYAML because that is what ``bandit.core.config.BanditConfig`` uses to
    read ``.bandit`` — this must read what bandit reads, and a hand-rolled
    parser could drift from bandit's own YAML rules (e.g. comment stripping)
    in a way that hides an entry from the audit.
    """
    parsed = yaml.safe_load(config_text) or {}
    entries = parsed.get("exclude_dirs") or []
    return [str(entry) for entry in entries]


def load_entries(config_path: pathlib.Path | None = None) -> list[str]:
    """Exclude entries of the repo's ``.bandit`` (or a given config)."""
    path = config_path if config_path is not None else repo_root() / ".bandit"
    return read_exclude_entries(path.read_text(encoding="utf-8"))


def is_glob_pattern(entry: str) -> bool:
    """Entries bandit only ever matches via ``fnmatch``, never substring.

    bandit's substring test is ``x in path`` on the *literal* entry string.
    An entry containing ``*`` never appears literally in a real filesystem
    path, so its whole exclusion power comes from ``_matches_glob_list`` —
    unaffected by #14489, and not a "bare directory name" in the sense this
    guard cares about.
    """
    return "*" in entry


def bare_entries(entries: list[str]) -> list[str]:
    """Entries bandit's substring test can match at any depth: no ``/``, no ``*``."""
    return [entry for entry in entries if "/" not in entry and not is_glob_pattern(entry)]


def unanchored_source_entries(entries: list[str]) -> list[str]:
    """Bare entries that are not a sanctioned artifact name.

    The decision the guard turns on, kept separate so callers can put a
    synthetic list through it instead of asserting on the config's text.
    """
    return [entry for entry in bare_entries(entries) if entry not in ARTIFACT_DIR_NAMES]


def tracked_py_files(root: pathlib.Path | None = None) -> list[str]:
    """Every tracked ``*.py`` path, enumerated by git rather than by bandit."""
    completed = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "*.py"],
        cwd=root if root is not None else repo_root(),
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in completed.stdout.splitlines() if line.strip()]


def entries_covering_tracked_python(entries: list[str], tracked: list[str]) -> dict[str, int]:
    """Bare entries that cover tracked Python under bandit's OWN matcher.

    Deliberately a substring test (``entry in path``), not a path-component
    test. bandit does not use component matching for a bare entry, so a
    component-based check here would pass ``venv`` as safe while bandit's
    real matcher still excludes ``check_venv_producers.py`` through its
    filename. Verifying against the wrong predicate is how a guard for this
    exact bug would itself fail open.
    """
    counts: dict[str, int] = {}
    for entry in bare_entries(entries):
        hits = sum(1 for path in tracked if entry in path)
        if hits:
            counts[entry] = hits
    return counts


def unanchored_path_entries(entries: list[str]) -> list[str]:
    """Path-separator entries not wrapped on both sides, e.g. ``tests/``.

    ``tests/`` (no leading ``/``) still matches ``repo_tests/foo.py`` as a raw
    substring — ``"tests/" in "repo_tests/foo.py"`` is True. Only
    ``/tests/`` requires a path separator on both sides.
    """
    return [
        entry
        for entry in entries
        if "/" in entry and not is_glob_pattern(entry) and not (entry.startswith("/") and entry.endswith("/"))
    ]


def audit_excludes(root: pathlib.Path | None = None) -> tuple[int, list[str]]:
    """Apply the invariant to every entry in ``.bandit``.

    Returns ``(entries_reached, problems)``. ``entries_reached`` is counted
    from the parsed list so a config whose ``exclude_dirs`` has gone missing
    or empty cannot report a clean scan of nothing.
    """
    base = root if root is not None else repo_root()
    problems: list[str] = []

    entries = load_entries(base / ".bandit")
    if not entries:
        return 0, [f"{base / '.bandit'} parsed to zero exclude_dirs entries — the guard checked nothing."]

    unanchored = unanchored_source_entries(entries)
    if unanchored:
        problems.append(
            f"unanchored exclude_dirs entries {sorted(unanchored)}: bandit tests each as a raw "
            "substring of the full path, with no component boundary, so each of these excludes "
            "any file whose path merely contains the string, at any depth (#14489). Write the "
            "path the entry was meant for wrapped in `/` (`/tests/`, not `tests`)."
        )

    bad_anchor = unanchored_path_entries(entries)
    if bad_anchor:
        problems.append(
            f"exclude_dirs entries missing a leading or trailing `/`: {sorted(bad_anchor)}. bandit "
            "never rewrites an entry into an absolute path the way flake8 does — without a "
            "separator on BOTH sides this still matches as an unbounded substring (`tests/` matches "
            "`repo_tests/foo.py`)."
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
                f"bare exclude_dirs entries cover tracked Python: {covered}. Those files are "
                f"silently unscanned for security findings. Either the entry is not an artifact "
                f"directory and must be wrapped in `/`, or it does not belong in "
                f"ARTIFACT_DIR_NAMES in {SELF_REL}."
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
        logger.error("\n.bandit exclude_dirs audit FAILED over %d entries (#14489).", reached)
        return 1
    logger.info(".bandit exclude_dirs audit clean over %d entries (#14489).", reached)
    return 0


def main(argv: list[str]) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--audit-excludes",
        action="store_true",
        help="apply the anchoring invariant to every .bandit exclude_dirs entry",
    )
    args = parser.parse_args(argv)
    if not args.audit_excludes:
        parser.error("nothing to do — pass --audit-excludes")
    return run_audit()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
