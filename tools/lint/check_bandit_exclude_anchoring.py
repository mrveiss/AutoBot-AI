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
*tracked* directory anywhere in the repo. Re-including them surfaced 3 real
bandit findings (B608 x1, B311 x2), both reviewed and suppressed at the call
site with a specific-ID ``# nosec`` and a reason.

ABSENT FROM ``git ls-files`` IS NOT ABSENT. bandit walks the filesystem, not
the git index, so a name can be dead weight for the git-tracked measurement
above and still real on disk. Checked against the filesystem instead: ``venv``
is a real, gitignored, ~26k-file dependency tree at the repo root, present the
moment anyone runs ``bandit -c .bandit -r .`` locally instead of naming the
three CI trees, and ``logs`` is a real, gitignored, ``.gitignore``-documented
runtime log directory that exists **inside** ``autobot-backend/`` and
``autobot-slm-backend/`` — the trees CI actually scans. Both are restored,
anchored. ``temp``, ``reports`` and ``archive`` really are absent everywhere
on disk (confirmed with ``find``, not just ``git ls-files``), so those three
stay dropped.

The invariant:

* a bare (separator-free) entry is allowed only if it covers **no tracked
  Python anywhere in the repo**, tested with bandit's own substring rule —
  not a path-component or basename rule, because bandit uses neither. This is
  the divergence from #14419's flake8 guard: ``venv`` passes a
  component-based check (no directory literally named ``venv`` holds tracked
  Python) but FAILS bandit's substring check (2 tracked files carry "venv"
  only inside their filename, e.g. ``check_venv_producers.py``), so a bare
  ``venv`` cannot pass this guard even though flake8's component-based guard
  could keep it bare — it is restored ANCHORED (``/venv/``) instead;
* every other entry is anchored by wrapping it in ``/``, requiring a path
  separator on both sides. bandit never rewrites an entry the way flake8
  does (flake8 turns a separator-containing entry into an absolute path
  prefix naming one location) — a bandit entry stays a substring test, so
  ``/tests/`` still matches every ``tests/`` directory at any depth, which is
  the intent, while no longer matching ``repo_tests/`` or
  ``run_unit_tests.py``. The same anchored form matches ``./venv/...`` when
  bandit is invoked as ``-r .`` from the repo root — the realistic
  local-footgun case ``/venv/`` guards against.

A SECOND DIVERGENCE FROM #14419: an anchored entry here is not required to
name a directory that currently exists, unlike flake8's
``missing_anchored_targets`` check. ``/venv/`` and ``/logs/`` name gitignored,
not-guaranteed-to-exist runtime directories — a CI runner or a fresh clone
legitimately has neither, and failing the guard for that would be exactly the
kind of false failure this fix is trying to prevent elsewhere.

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
TRACKED_PY_FLOOR = _scan_helpers.TRACKED_PY_FLOOR  # canonical: one measured floor, was a local 3000 (#15928)


read_exclude_entries = _shared.read_bandit_exclude_dirs
load_entries = functools.partial(_shared.load_entries, default_name=".bandit", reader=read_exclude_entries)
tracked_py_files = _shared.tracked_py_files


def is_glob_pattern(entry: str) -> bool:
    """Entries bandit only ever matches via ``fnmatch``, never substring.

    bandit's substring test is ``x in path`` on the *literal* entry string.
    An entry containing ``*`` never appears literally in a real filesystem
    path, so its whole exclusion power comes from ``_matches_glob_list`` —
    unaffected by #14489, and not a "bare directory name" in the sense this
    guard cares about.
    """
    return "*" in entry


#: Entries bandit's substring test can match at any depth: no ``/``, no ``*``.
bare_entries = functools.partial(_shared.bare_entries, separators="/", skip_globs=True)

#: Bare entries that are not a sanctioned artifact name (shared decision, #14896).
unanchored_source_entries = functools.partial(
    _shared.unanchored_source_entries, bare_entries=bare_entries, artifact_names=ARTIFACT_DIR_NAMES
)


def _substring_hits(entry: str, path: str) -> int:
    """1 when bandit's OWN matcher (``entry in path``) excludes *path*.

    Deliberately a substring test, not a path-component test. bandit does not
    use component matching for a bare entry, so a component-based check would
    pass ``venv`` as safe while bandit's real matcher still excludes
    ``check_venv_producers.py`` through its filename.
    """
    return int(entry in path)


#: Bare entries that cover tracked Python under bandit's OWN matcher.
entries_covering_tracked_python = functools.partial(
    _shared.entries_covering_tracked_python, bare=bare_entries, hits_in_path=_substring_hits
)


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


def _unanchored_finding(entries: list[str], _root: pathlib.Path) -> str | None:
    unanchored = unanchored_source_entries(entries)
    if not unanchored:
        return None
    return (
        f"unanchored exclude_dirs entries {sorted(unanchored)}: bandit tests each as a raw "
        "substring of the full path, with no component boundary, so each of these excludes "
        "any file whose path merely contains the string, at any depth (#14489). Write the "
        "path the entry was meant for wrapped in `/` (`/tests/`, not `tests`)."
    )


def _bad_anchor_finding(entries: list[str], _root: pathlib.Path) -> str | None:
    bad_anchor = unanchored_path_entries(entries)
    if not bad_anchor:
        return None
    return (
        f"exclude_dirs entries missing a leading or trailing `/`: {sorted(bad_anchor)}. bandit "
        "never rewrites an entry into an absolute path the way flake8 does — without a "
        "separator on BOTH sides this still matches as an unbounded substring (`tests/` matches "
        "`repo_tests/foo.py`)."
    )


def _describe_covered(covered: dict[str, int]) -> str:
    return (
        f"bare exclude_dirs entries cover tracked Python: {covered}. Those files are "
        f"silently unscanned for security findings. Either the entry is not an artifact "
        f"directory and must be wrapped in `/`, or it does not belong in "
        f"ARTIFACT_DIR_NAMES in {SELF_REL}."
    )


#: Apply the invariant to every entry in ``.bandit``; returns ``(entries_reached, problems)``.
audit_excludes = functools.partial(
    _shared.audit_excludes,
    config_name=".bandit",
    load=load_entries,
    key="exclude_dirs",
    before=(_unanchored_finding, _bad_anchor_finding),
    coverage=functools.partial(
        _shared.coverage_problem,
        covering=entries_covering_tracked_python,
        describe=_describe_covered,
        floor=TRACKED_PY_FLOOR,
    ),
    after=(),
)


def run_audit() -> int:
    reached, problems = audit_excludes()
    if problems:
        logger.error("%s", "\n\n".join(problems))
        logger.error("\n.bandit exclude_dirs audit FAILED over %d entries (#14489).", reached)
        return 1
    logger.info(".bandit exclude_dirs audit clean over %d entries (#14489).", reached)
    return 0


def main(argv: list[str]) -> int:
    configure_logging(logger)
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
