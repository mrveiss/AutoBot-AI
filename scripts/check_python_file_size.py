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
import sys

# Plain stdlib logging, deliberately (#1082). This is a pre-commit hook: it runs
# as a bare script on every commit, and `autobot_shared.logging_manager` would
# drag config loading into that path. The same trade is taken in
# `autobot_shared/user_management/password_epoch.py`, and it is what CLAUDE.md's
# pattern table allows for exactly this case.
logger = logging.getLogger(__name__)

# scripts/ is not a Python package; put the repository root on the path so
# the shared ratchet engine is importable when this runs as a bare hook.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tools.lint import file_size_engine as engine  # noqa: E402
from tools.lint._scan_helpers import configure_logging  # noqa: E402

MAX_LINES = 600

#: Repo-relative path of this hook, quoted in the messages that ask for an edit.
SELF_REL = "scripts/check_python_file_size.py"

#: The ratchet test holding RATCHET_BASELINE, the second copy of these numbers.
#: Every message that asks for an edit here names it too: a ceiling lowered in
#: one file alone leaves the other holding the old size (#14498).
RATCHET_REL = "repo_tests/python_file_size_ratchet_baseline.py"  # the DATA module, not the
#: test that re-exports it (#17377): a developer told to lower "the matching RATCHET_BASELINE
#: entry" in the test file opens a file whose RATCHET_BASELINE is one re-export line, with no
#: entries to edit -- the wrong-copy failure #17872 exists to prevent, emitted by the gate.

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


def _config() -> engine.GateConfig:
    """This gate's configuration, read from the module globals AT CALL TIME (#17377).

    Built per call rather than once at import: the ratchet tests point the gate at a
    synthetic tree by patching ``KNOWN_LARGE`` and friends, and a config bound at import
    would ignore those patches while the tests went on asserting against the real tree.
    """
    return engine.GateConfig(
        label="python-file-size",
        max_lines=MAX_LINES,
        self_rel=SELF_REL,
        ratchet_rel=RATCHET_REL,
        excluded_prefixes=EXCLUDED_PREFIXES,
        min_tracked_files=MIN_TRACKED_PY_FILES,
        known_large=KNOWN_LARGE,
        globs=("*.py",),
        summary_noun="files",
        commit_skips_excluded=False,
    )


# Thin delegations. Each exists because the ratchet and parity tests, or `main`, call it by
# this name; the behaviour is the engine's, shared with the shell and frontend gates.
def normalise(path: str) -> str:
    return engine.normalise(path)


def count_lines(path: pathlib.Path) -> int | None:
    return engine.count_lines(path)


def tracked_python_files(root: pathlib.Path) -> list[str]:
    return engine.tracked_files(_config(), root)


def verdict(rel: str, line_count: int) -> str | None:
    return engine.verdict(_config(), rel, line_count)


def unmeasured(rel: str) -> str:
    return engine.unmeasured(rel)


def _vanished_entry_problem(rel: str, root: pathlib.Path) -> str:
    return engine.vanished_entry_problem(_config(), rel, root)


def _reach_breach_problem(reached: int) -> str:
    return engine.reach_breach_problem(_config(), reached)


def _scan_tracked_files(root: pathlib.Path, tracked: list[str]) -> engine.ScanResult:
    return engine.scan_tracked_files(_config(), root, tracked)


def audit_ceilings() -> tuple[int, list[str]]:
    return engine.audit_ceilings(_config(), repo_root(), tracked_python_files, _scan_tracked_files)


def run_audit() -> int:
    return engine.run_audit(_config(), logger, audit_ceilings)


def main(argv: list[str]) -> int:
    """Audit the tree with ``--audit-ceilings``, otherwise rule on the paths given.

    Paths resolve against the caller's cwd (``pathlib.Path()``), as they always have here --
    the shell and frontend gates resolve against ``repo_root()``. Under pre-commit, which runs
    from the repo root, the two agree; the engine keeps each gate's choice.
    """
    configure_logging(logger)
    if "--audit-ceilings" in argv:
        return run_audit()
    return engine.check_paths(_config(), pathlib.Path(), argv, logger)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
