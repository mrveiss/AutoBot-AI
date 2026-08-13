#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Fail when a pre-commit hook could not RUN, as distinct from finding something (#14181).

`.github/workflows/enforce-precommit.yml` runs `pre-commit run --all-files` and
swallows the result with `|| { echo "::warning::…"; exit 0; }`. Its own comment
states the intent — *"The goal is to catch configuration errors, not necessarily
code issues"* — but it never implemented the distinction, so both outcomes are
discarded and the job reports success either way.

Measured on a real run: **20** hooks reported `Failed` (findings — formatting,
lint violations, the judgement call that step was right to avoid gating on) and
**5** could not execute at all, printing pre-commit's own
``Executable `X` is not executable``. Sixteen dormant hooks scrolled past under
a green check that way (#14181).

This reads pre-commit's output and fails only on the second class: a hook that
never ran tells you nothing about the code, and reporting success for it is the
fail-open this whole issue is about.

The tolerated set is imported from ``check_hook_exec_bits.py``'s
``_KNOWN_DORMANT`` rather than duplicated. A second copy of that list is a
second thing to go stale — and a stale exemption list is precisely what #14202
found. As each dormant hook is woken both guards tighten together, and when the
baseline empties this check becomes absolute with no further edit.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_hook_exec_bits import _KNOWN_DORMANT  # noqa: E402

# pre-commit's own wording for "I could not execute this entry".
_CANNOT_RUN = re.compile(r"Executable `([^`]+)` (?:is not executable|not found)")


def unrunnable_hooks(output: str) -> list[str]:
    """Every hook entry pre-commit reported it could not execute."""
    return sorted({match.group(1) for match in _CANNOT_RUN.finditer(output)})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logfile", nargs="?", help="pre-commit output; stdin when omitted")
    args = parser.parse_args(argv)

    output = Path(args.logfile).read_text(encoding="utf-8") if args.logfile else sys.stdin.read()

    unrunnable = unrunnable_hooks(output)
    tolerated = [hook for hook in unrunnable if hook in _KNOWN_DORMANT]
    blocking = [hook for hook in unrunnable if hook not in _KNOWN_DORMANT]

    if tolerated:
        print(  # noqa: print
            f"check-precommit-hooks-executed: {len(tolerated)} known-dormant hook(s) still cannot run, "
            "tracked in #14181:"
        )
        for hook in tolerated:
            print(f"  KNOWN  {hook}")  # noqa: print
        print()  # noqa: print

    if not blocking:
        print("check-precommit-hooks-executed: every other hook executed")  # noqa: print
        return 0

    print(f"check-precommit-hooks-executed: {len(blocking)} hook(s) could not run\n")  # noqa: print
    for hook in blocking:
        print(f"  FAIL   {hook}")  # noqa: print
    print(  # noqa: print
        "\nA hook that cannot execute reports nothing about the code, so a green\n"
        "check over it is a false clean bill of health. Usually the tracked exec\n"
        "bit: `core.fileMode=false` means chmod never reaches the index, so the\n"
        "mismatch is invisible locally. Fix with:\n"
        "  git update-index --chmod=+x <path>\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
