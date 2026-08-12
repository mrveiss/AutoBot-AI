#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Diff guard: role_*_active facts must stay byte-equal across all copies
until #7095 (single source of truth) lands.

Three consumers exist:
- inventory/group_vars/all.yml               canonical; loaded by static-inventory
                                              playbooks via Ansible's own group_vars
                                              auto-discovery
- playbooks/vars/role_active_facts.yml       loaded by playbooks via vars_files when
                                              invoked with dynamic temp inventories that
                                              lack a sibling group_vars/ (e.g. the SLM
                                              wizard, #7094)
- tests/inventory/group_vars/all.yml         the CI regression-test inventory's copy.
                                              Used to be a symlink to
                                              inventory/group_vars/all.yml; this repo's
                                              `core.symlinks=false` checkouts (WSL2)
                                              materialize a tracked symlink as a
                                              plain-text path string instead, so it is a
                                              real file now (#14149)

If any copy drifts, behavior diverges silently. This script extracts the
role_*_active definitions from each and compares them; exits non-zero on any
divergence so CI fails the PR.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GROUP_VARS = REPO / "autobot-slm-backend/ansible/inventory/group_vars/all.yml"
PLAYBOOK_VARS = REPO / "autobot-slm-backend/ansible/playbooks/vars/role_active_facts.yml"
TEST_GROUP_VARS = REPO / "autobot-slm-backend/ansible/tests/inventory/group_vars/all.yml"


def extract_facts(path: Path) -> dict:
    """Extract role_X_active blocks (key + multiline `>-` value) from a file.

    Returns dict mapping fact name → normalized whitespace value.
    """
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"(role_\w+_active:\s*>-(?:\n[ \t]+.*)*)")
    blocks = pattern.findall(text)
    return {re.match(r"(role_\w+_active)", b).group(1): re.sub(r"\s+", " ", b).strip() for b in blocks}


def compare(label_a: str, a: dict, label_b: str, b: dict) -> bool:
    """Print and return whether `a` and `b` diverge (True == diverged)."""
    diverged = False
    if set(a) != set(b):
        print("FACT KEYS DIVERGED:")
        print(f"  in {label_a} only: {sorted(set(a) - set(b))}")
        print(f"  in {label_b} only: {sorted(set(b) - set(a))}")
        diverged = True
    for k in sorted(set(a) & set(b)):
        if a[k] != b[k]:
            print(f"FACT {k!r} DIVERGED:")
            print(f"  {label_a}: {a[k]}")
            print(f"  {label_b}: {b[k]}")
            diverged = True
    return diverged


def main() -> int:
    canonical = extract_facts(GROUP_VARS)
    playbook = extract_facts(PLAYBOOK_VARS)
    test_inventory = extract_facts(TEST_GROUP_VARS)

    diverged = False
    diverged |= compare("inventory/group_vars", canonical, "playbooks/vars", playbook)
    diverged |= compare("inventory/group_vars", canonical, "tests/inventory/group_vars", test_inventory)

    if diverged:
        return 1

    print(f"OK — {len(canonical)} role_*_active facts identical across all three files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
