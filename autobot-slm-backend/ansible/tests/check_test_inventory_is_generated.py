#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The test inventory's group_vars must be a copy of the single source (#14678).

`role_*_active` used to live in three tracked copies, kept byte-equal by
`check_role_facts_synced.py`. That guard worked -- it caught two partial edits
during #14567 -- but enforcing three copies is not a fix, and the issue it was
waiting on (#7095) was closed without the fix landing.

There is now one tracked definition, `inventory/group_vars/all.yml`. The test
inventory needs a real file beside it (a tracked symlink is materialised as a
plain-text path string on `core.symlinks=false` checkouts and silently resolves
zero variables -- #14149), so CI copies it before running.

This asserts the copy actually happened and matches. A stale or missing copy
would let the facts test pass against yesterday's definitions, which is the
same silent-divergence failure in a new place.
"""

import sys
from pathlib import Path

_ANSIBLE = Path(__file__).resolve().parents[1]
_SOURCE = _ANSIBLE / "inventory" / "group_vars" / "all.yml"
_GENERATED = _ANSIBLE / "tests" / "inventory" / "group_vars" / "all.yml"


def main() -> int:
    if not _SOURCE.is_file():
        print(f"MISSING SOURCE: {_SOURCE}")
        return 1

    if not _GENERATED.is_file():
        print(
            f"MISSING GENERATED COPY: {_GENERATED}\n"
            "  CI must copy inventory/group_vars/all.yml there before running the facts test."
        )
        return 1

    if _GENERATED.is_symlink():
        print(
            f"GENERATED COPY IS A SYMLINK: {_GENERATED}\n"
            "  #14149: a tracked symlink becomes a plain-text path string on core.symlinks=false\n"
            "  checkouts, and the playbook then resolves zero variables. Copy the file instead."
        )
        return 1

    source = _SOURCE.read_text(encoding="utf-8")
    generated = _GENERATED.read_text(encoding="utf-8")
    if source != generated:
        print(
            "GENERATED COPY IS STALE:\n"
            f"  source:    {_SOURCE}\n"
            f"  generated: {_GENERATED}\n"
            "  Re-run the copy step; the facts test would otherwise assert against old definitions."
        )
        return 1

    print(f"test inventory group_vars matches the single source ({len(source.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
