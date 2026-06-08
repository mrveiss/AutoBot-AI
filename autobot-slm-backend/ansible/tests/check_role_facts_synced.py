#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Diff guard: role_*_active facts must stay byte-equal across the two
copies until #7095 (single source of truth) lands.

Two consumers exist:
- inventory/group_vars/all.yml   (loaded by static-inventory playbooks)
- playbooks/vars/role_active_facts.yml  (loaded by playbooks via vars_files
                                          when invoked with dynamic temp
                                          inventories that lack a sibling
                                          group_vars/, e.g. the SLM wizard)

If the two files drift, behavior diverges silently. This script extracts
the role_*_active definitions from each and compares them; exits non-zero
on any divergence so CI fails the PR.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GROUP_VARS = REPO / "autobot-slm-backend/ansible/inventory/group_vars/all.yml"
PLAYBOOK_VARS = REPO / "autobot-slm-backend/ansible/playbooks/vars/role_active_facts.yml"


def extract_facts(path: Path) -> dict:
    """Extract role_X_active blocks (key + multiline `>-` value) from a file.

    Returns dict mapping fact name → normalized whitespace value.
    """
    text = path.read_text()
    pattern = re.compile(r"(role_\w+_active:\s*>-(?:\n[ \t]+.*)*)")
    blocks = pattern.findall(text)
    return {re.match(r"(role_\w+_active)", b).group(1): re.sub(r"\s+", " ", b).strip() for b in blocks}


def main() -> int:
    a = extract_facts(GROUP_VARS)
    b = extract_facts(PLAYBOOK_VARS)
    if set(a) != set(b):
        print(f"FACT KEYS DIVERGED:")
        print(f"  in group_vars only:    {sorted(set(a) - set(b))}")
        print(f"  in playbooks/vars only: {sorted(set(b) - set(a))}")
        return 1
    for k in sorted(a):
        if a[k] != b[k]:
            print(f"FACT {k!r} DIVERGED:")
            print(f"  group_vars: {a[k]}")
            print(f"  playbooks:  {b[k]}")
            return 1
    print(f"OK — {len(a)} role_*_active facts identical across both files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
