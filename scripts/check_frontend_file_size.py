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
import sys

# Plain stdlib logging, deliberately (#1082). This runs as a bare script on
# every commit, and `autobot_shared.logging_manager` would drag config loading
# into that path — the same trade `check_python_file_size.py` takes.
logger = logging.getLogger(__name__)

# scripts/ is not a package; put the repo root on the path so the shared
# ratchet engine is importable when this runs as a bare hook.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tools.lint import file_size_engine as engine  # noqa: E402
from tools.lint._scan_helpers import configure_logging  # noqa: E402

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


def repo_root() -> pathlib.Path:
    """Repo root derived from this file, never from the caller's cwd."""
    return pathlib.Path(__file__).resolve().parents[1]


def _config() -> engine.GateConfig:
    """This gate's configuration, read from the module globals AT CALL TIME (#17377)."""
    return engine.GateConfig(
        label="frontend-file-size",
        max_lines=MAX_LINES,
        self_rel=SELF_REL,
        ratchet_rel=RATCHET_REL,
        excluded_prefixes=EXCLUDED_PREFIXES,
        min_tracked_files=MIN_TRACKED_FRONTEND_FILES,
        known_large=KNOWN_LARGE,
        globs=TRACKED_GLOBS,
        summary_noun="file(s)",
        commit_skips_excluded=True,
    )


# Thin delegations. Each exists because the ratchet and parity tests, or `main`, call it by
# this name; the behaviour is the engine's, shared with the Python and shell gates.
def normalise(path: str) -> str:
    return engine.normalise(path)


def count_lines(path: pathlib.Path) -> int | None:
    return engine.count_lines(path)


def tracked_frontend_files(root: pathlib.Path) -> list[str]:
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
    return engine.audit_ceilings(_config(), repo_root(), tracked_frontend_files, _scan_tracked_files)


def run_audit() -> int:
    return engine.run_audit(_config(), logger, audit_ceilings)


def check_paths(paths: list[str]) -> int:
    """The commit path: rule on the staged files pre-commit passed in."""
    return engine.check_paths(_config(), repo_root(), paths, logger)


def main(argv: list[str] | None = None) -> int:
    """Entry point for both the hook path and ``--audit-ceilings``."""
    configure_logging(logger)
    parser = argparse.ArgumentParser(description="Reject oversized .ts/.vue files (#17885).")
    parser.add_argument("--audit-ceilings", action="store_true", help="walk every tracked .ts/.vue file")
    parser.add_argument("paths", nargs="*", help="staged files, as pre-commit passes them")
    args = parser.parse_args(argv)
    if args.audit_ceilings:
        return run_audit()
    return check_paths(args.paths)


if __name__ == "__main__":
    sys.exit(main())
