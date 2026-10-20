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
import functools
import logging
import pathlib
import sys

# tools/lint/ is not a Python package; make the sibling helper importable
# regardless of invocation mode (script / importlib from tests).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _exclude_anchoring as _shared
import _scan_helpers
from _scan_helpers import configure_logging  # noqa: E402
from _scan_helpers import project_root as repo_root  # noqa: E402

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
TRACKED_PY_FLOOR = _scan_helpers.TRACKED_PY_FLOOR  # canonical: one measured floor, was a local 3000 (#15928)

#: Mirror of ``flake8.utils.COMMA_SEPARATED_LIST_RE`` (defined once, in ``_exclude_anchoring``);
#: the test pins it to the real parser wherever flake8 is importable.
_SPLIT_RE = _shared._SPLIT_RE


split_exclude_value = _shared.split_exclude_value
read_exclude_entries = _shared.read_flake8_exclude
load_entries = functools.partial(_shared.load_entries, default_name=".flake8", reader=read_exclude_entries)
tracked_py_files = _shared.tracked_py_files

#: Entries flake8 matches against a basename, i.e. at any depth.
bare_entries = functools.partial(_shared.bare_entries, separators="/\\", skip_globs=False)

#: Bare entries that are not a sanctioned artifact name (shared decision, #14896).
unanchored_source_entries = functools.partial(
    _shared.unanchored_source_entries, bare_entries=bare_entries, artifact_names=ARTIFACT_DIR_NAMES
)


def _component_hits(entry: str, path: str) -> int:
    """How many directory components of *path* equal *entry*.

    ``fnmatch`` is not needed: flake8 compares a bare entry to a directory's
    basename, so a path component equal to the entry is exactly a hit.
    """
    return path.split("/")[:-1].count(entry)


#: Bare entries that prune tracked Python, mapped to how many files.
entries_covering_tracked_python = functools.partial(
    _shared.entries_covering_tracked_python, bare=bare_entries, hits_in_path=_component_hits
)


def missing_anchored_targets(entries: list[str], root: pathlib.Path | None = None) -> list[str]:
    """Anchored entries naming no directory — they exempt nothing, silently."""
    base = root if root is not None else repo_root()
    anchored = [entry for entry in entries if entry not in bare_entries(entries)]
    return [entry for entry in anchored if not (base / entry.rstrip("/")).is_dir()]


def _unanchored_finding(entries: list[str], _root: pathlib.Path) -> str | None:
    unanchored = unanchored_source_entries(entries)
    if not unanchored:
        return None
    return (
        f"unanchored exclude entries {sorted(unanchored)}: flake8 matches a "
        "separator-free entry against the basename, so each prunes every "
        "directory of that name at ANY depth. Write the path the entry was "
        "meant for (`autobot-backend/tests/`, not `tests`). A trailing `# "
        "comment` inside the value also lands here, one entry per word."
    )


def _describe_covered(covered: dict[str, int]) -> str:
    return (
        f"bare exclude entries cover tracked Python: {covered}. Those "
        f"files are silently unlinted. Either the entry is not an "
        f"artifact directory and must be anchored, or it does not "
        f"belong in ARTIFACT_DIR_NAMES in {SELF_REL}."
    )


def _missing_target_finding(entries: list[str], base: pathlib.Path) -> str | None:
    missing = missing_anchored_targets(entries, base)
    if not missing:
        return None
    return (
        f"exclude entries naming no directory: {sorted(missing)}. Remove "
        "them or fix the path — a dead entry cannot exclude and cannot warn."
    )


#: Apply the invariant to every entry in ``.flake8``; returns ``(entries_reached, problems)``.
audit_excludes = functools.partial(
    _shared.audit_excludes,
    config_name=".flake8",
    load=load_entries,
    key="exclude",
    before=(_unanchored_finding,),
    coverage=functools.partial(
        _shared.coverage_problem,
        covering=entries_covering_tracked_python,
        describe=_describe_covered,
        floor=TRACKED_PY_FLOOR,
    ),
    after=(_missing_target_finding,),
)


def run_audit() -> int:
    reached, problems = audit_excludes()
    if problems:
        logger.error("%s", "\n\n".join(problems))
        logger.error("\n.flake8 exclude audit FAILED over %d entries (#14419).", reached)
        return 1
    logger.info(".flake8 exclude audit clean over %d entries (#14419).", reached)
    return 0


def main(argv: list[str]) -> int:
    configure_logging(logger)
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
