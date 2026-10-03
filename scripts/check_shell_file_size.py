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
import sys

# Plain stdlib logging, deliberately (#1082). This runs as a bare script on
# every commit, and `autobot_shared.logging_manager` would drag config loading
# into that path — the same trade `check_python_file_size.py` takes.
logger = logging.getLogger(__name__)

# scripts/ is not a package; put the repo root on the path so the canonical
# git-env scrub is importable when this runs as a bare hook.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tools.lint import file_size_engine as engine  # noqa: E402
from tools.lint.file_size_engine import GateConfig  # noqa: E402

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
    "install.sh": 1277,  # #17875: +12 for three first-run fixes; single-file installer cannot be split
    "scripts/lib/hardcoded-value-rules.sh": 842,
    "scripts/pr-preflight.sh": 818,
}


def repo_root() -> pathlib.Path:
    """Repo root derived from this file, never from the caller's cwd."""
    return pathlib.Path(__file__).resolve().parents[1]


def _config() -> GateConfig:
    """This gate's configuration, read from the module globals AT CALL TIME.

    Built per call rather than once at import, deliberately (#17377): the ratchet tests point
    the gate at a synthetic tree by patching these module attributes, and a config bound at
    import would ignore every one of those patches while the tests went on asserting against
    the real tree. Reading them here keeps the module's attributes the configuration surface,
    so the extraction changes where the LOGIC lives without changing where the KNOBS are.
    """
    return GateConfig(
        label="shell-file-size",
        max_lines=MAX_LINES,
        self_rel=SELF_REL,
        ratchet_rel=RATCHET_REL,
        excluded_prefixes=EXCLUDED_PREFIXES,
        min_tracked_files=MIN_TRACKED_SH_FILES,
        known_large=KNOWN_LARGE,
        glob="*.sh",
    )


# Thin delegations. Each exists because the ratchet tests and `main` call it by this name;
# the behaviour is the engine's, shared with the Python gate.
def normalise(path: str) -> str:
    return engine.normalise(path)


def count_lines(path: pathlib.Path) -> int | None:
    return engine.count_lines(path)


def tracked_shell_files(root: pathlib.Path) -> list[str]:
    return engine.tracked_files(_config(), root)


def verdict(rel: str, line_count: int) -> str | None:
    return engine.verdict(_config(), rel, line_count)


def unmeasured(rel: str) -> str:
    return engine.unmeasured(rel)


def _report_unmeasured(rel: str, seen: set[str], problems: list[str]) -> None:
    engine.report_unmeasured(rel, seen, problems)


def _vanished_entry_problem(rel: str, root: pathlib.Path) -> str:
    return engine.vanished_entry_problem(_config(), rel, root)


def _reach_breach_problem(reached: int) -> str:
    return engine.reach_breach_problem(_config(), reached)


def _scan_tracked_files(root: pathlib.Path, tracked: list[str]) -> tuple[int, set[str], list[str]]:
    return engine.scan_tracked_files(_config(), root, tracked)


def audit_ceilings() -> tuple[int, list[str]]:
    # This module's own collaborators are passed in, so a test patching them is obeyed.
    return engine.audit_ceilings(_config(), repo_root(), enumerate_files=tracked_shell_files, scan=_scan_tracked_files)


def configure_logging() -> None:
    engine.configure_logging(logger)


def run_audit() -> int:
    return engine.run_audit(_config(), repo_root(), logger, audit=audit_ceilings)


def check_paths(paths: list[str]) -> int:
    return engine.check_paths(_config(), repo_root(), paths, logger)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reject oversized shell files (#17353).")
    parser.add_argument("paths", nargs="*", help="staged files, as pre-commit passes them")
    parser.add_argument("--audit-ceilings", action="store_true", help="rule on the whole tree")
    args = parser.parse_args(argv)
    configure_logging()
    return run_audit() if args.audit_ceilings else check_paths(args.paths)


if __name__ == "__main__":
    sys.exit(main())
