#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The test inventory's group_vars must be a copy of the single source (#14678).

`role_*_active` used to live in three tracked copies, kept byte-equal by a diff
guard. That guard worked, but enforcing copies is not a fix, and the issue it
was waiting on (#7095) was closed without the fix landing.

There is now one tracked definition, `inventory/group_vars/all.yml`
(`tools/lint/check_role_facts_single_source.py` enforces that). The test inventory needs
real files beside it (a tracked symlink is materialised as a plain-text path
string on `core.symlinks=false` checkouts and silently resolves zero
variables -- #14149), so CI copies the whole `group_vars/` directory first.

This asserts the copy actually happened and matches file for file. A stale or
missing copy would let the facts test pass against yesterday's definitions,
which is the same silent-divergence failure in a new place.
"""

import sys
from pathlib import Path

_ANSIBLE = Path(__file__).resolve().parents[2] / "autobot-slm-backend" / "ansible"
_SOURCE = _ANSIBLE / "inventory" / "group_vars"
_GENERATED = _ANSIBLE / "tests" / "inventory" / "group_vars"


def _files(root: Path) -> dict[str, Path]:
    return {p.relative_to(root).as_posix(): p for p in sorted(root.rglob("*")) if p.is_file() or p.is_symlink()}


def main() -> int:
    if not _SOURCE.is_dir():
        print(f"MISSING SOURCE: {_SOURCE}")
        return 1

    if not _GENERATED.is_dir():
        print(
            f"MISSING GENERATED COPY: {_GENERATED}\n"
            "  CI must copy inventory/group_vars/ there before running the facts test."
        )
        return 1

    source, generated = _files(_SOURCE), _files(_GENERATED)
    if not source:
        print(f"EMPTY SOURCE: {_SOURCE} has no files -- nothing to compare")
        return 1

    for rel, path in generated.items():
        if path.is_symlink():
            print(
                f"GENERATED COPY IS A SYMLINK: {path}\n"
                "  #14149: a tracked symlink becomes a plain-text path string on core.symlinks=false\n"
                "  checkouts, and the playbook then resolves zero variables. Copy the file instead."
            )
            return 1

    if set(source) != set(generated):
        print(
            "GENERATED COPY HAS A DIFFERENT FILE SET:\n"
            f"  missing: {sorted(set(source) - set(generated))}\n"
            f"  extra:   {sorted(set(generated) - set(source))}"
        )
        return 1

    stale = [rel for rel in source if source[rel].read_bytes() != generated[rel].read_bytes()]
    if stale:
        print(
            f"GENERATED COPY IS STALE: {stale}\n"
            "  Re-run the copy step; the facts test would otherwise assert against old definitions."
        )
        return 1

    print(f"test inventory group_vars matches the single source ({len(source)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
