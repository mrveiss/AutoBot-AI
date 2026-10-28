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
    "autobot-infrastructure/autobot-slm-backend/scripts/bootstrap-slm.sh": 651,
    "autobot-infrastructure/shared/scripts/bulletproof-frontend/zero-downtime-update.sh": 614,
    "autobot-infrastructure/shared/scripts/cleanup-disk-space.sh": 838,
    "autobot-infrastructure/shared/scripts/deployment/validate_access_control.sh": 659,
    "autobot-infrastructure/shared/scripts/install-bare-metal.sh": 882,
    "autobot-infrastructure/shared/scripts/install-slm.sh": 822,
    "autobot-slm-backend/ansible/deploy.sh": 712,
    # #17929: +41 for the /dev/tty prompt helper. The documented `curl | sudo bash`
    # aborted silently at the password prompt -- stdin is the script pipe, `read`
    # got EOF, `set -e` killed it. The file is delivered BY curl, so it cannot
    # source a helper and cannot be split; the exemption's own reason still holds.
    "install.sh": 1169,  # #18653: the uninstaller moved to scripts/uninstall.sh; single-file installer cannot be split
    "scripts/lib/hardcoded-value-rules.sh": 842,
    "scripts/pr-preflight.sh": 815,
}


#: In-scope, git-tracked ``*.sh`` paths under *root*, relative to it.
def tracked_shell_files(root: pathlib.Path) -> list[str]:
    """In-scope tracked paths under *root*; EXCLUDED_PREFIXES is read at call time, not bound at import."""
    return git_tracked(root, ("*.sh",), EXCLUDED_PREFIXES)


GUARD = FileSizeGuard(
    globals(),
    floor_name="MIN_TRACKED_SH_FILES",
    tracked_name="tracked_shell_files",
    summary="shell-file-size ceilings: %d file(s) scanned, %d grandfathered, all live and at size.",
)
_grandfathered_verdict = GUARD.grandfathered_verdict
verdict = GUARD.verdict
_vanished_entry_problem = GUARD.vanished_entry_problem
_report_unmeasured = GUARD.report_unmeasured
_scan_tracked_files = GUARD.scan_tracked_files
audit_ceilings = GUARD.audit_ceilings
_reach_breach_problem = GUARD.reach_breach_problem
run_audit = GUARD.run_audit
check_paths = GUARD.check_paths


def main(argv: list[str] | None = None) -> int:
    """Entry point for both the hook path and ``--audit-ceilings``."""
    configure_logging(logger)
    parser = argparse.ArgumentParser(description="Reject oversized shell files (#17353).")
    parser.add_argument("--audit-ceilings", action="store_true", help="walk every tracked .sh file")
    parser.add_argument("paths", nargs="*", help="staged files, as pre-commit passes them")
    args = parser.parse_args(argv)
    if args.audit_ceilings:
        return run_audit()
    return GUARD.check_paths(args.paths)


if __name__ == "__main__":
    sys.exit(main())
