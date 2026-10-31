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
# the canonical git-env scrub is importable when this runs as a bare hook.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from autobot_shared.paths import project_root as repo_root  # noqa: E402, F401  # read via GUARD (live namespace)
from tools.lint._file_size_guard import (  # noqa: E402, F401  # names read via GUARD (live namespace)
    FileSizeGuard,
    count_lines,
    git_tracked,
    load_known_large,
    normalise,
    unmeasured,
)
from tools.lint._scan_helpers import configure_logging  # noqa: E402

MAX_LINES = 600

#: Repo-relative path of this hook, quoted in the messages that ask for an edit.
SELF_REL = "scripts/check_python_file_size.py"

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


# Grandfathered files: over MAX_LINES with no active decomposition under way,
# mapped to the line count recorded for each. THIS MAPPING ONLY SHRINKS —
# entries leave when the file reaches MAX_LINES, and a ceiling may be lowered
# but never raised. Never add an entry to make a new file pass; split the
# file instead. See ``python_file_size_known_large.py`` for the full dict, the ONE
# place a ceiling is recorded (#19544): ``python_file_size_ratchet_test.py`` checks it
# against the same table at the base commit, so no second copy is kept.
KNOWN_LARGE: dict[str, int] = load_known_large(__file__, "python_file_size_known_large.py")


#: In-scope, git-tracked ``*.py`` paths under *root*, relative to it.
def tracked_python_files(root: pathlib.Path) -> list[str]:
    """In-scope tracked paths under *root*; EXCLUDED_PREFIXES is read at call time, not bound at import."""
    return git_tracked(root, ("*.py",), EXCLUDED_PREFIXES)


GUARD = FileSizeGuard(
    globals(),
    floor_name="MIN_TRACKED_PY_FILES",
    tracked_name="tracked_python_files",
    summary="python-file-size ceilings: %d files scanned, %d grandfathered, all live and at size.",
)
_grandfathered_verdict = GUARD.grandfathered_verdict
verdict = GUARD.verdict
_vanished_entry_problem = GUARD.vanished_entry_problem
_report_unmeasured = GUARD.report_unmeasured
_scan_tracked_files = GUARD.scan_tracked_files
audit_ceilings = GUARD.audit_ceilings
_reach_breach_problem = GUARD.reach_breach_problem
run_audit = GUARD.run_audit


def main(argv: list[str]) -> int:
    """Entry point: ``--audit-ceilings`` anywhere in *argv*, else rule on each path as given."""
    configure_logging(logger)
    if "--audit-ceilings" in argv:
        return run_audit()
    findings = [GUARD.rule_on(normalise(arg), pathlib.Path(arg)) for arg in argv]
    return GUARD.emit([message for message in findings if message is not None])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
