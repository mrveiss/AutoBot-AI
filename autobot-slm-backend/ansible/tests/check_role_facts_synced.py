#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Diff guard: role_*_active facts must stay byte-equal across the two
copies #14678 left tracked -- see _ROLE_FACTS_FILES below for why the third
(#7095) never fully collapsed to one.

Two consumers exist:
- inventory/group_vars/all.yml               canonical; loaded by static-inventory
                                              playbooks via Ansible's own group_vars
                                              auto-discovery, and by every dynamic
                                              inventory builder, which links this
                                              directory beside its temp inventory
                                              (#11781, #14286)
- playbooks/vars/role_active_facts.yml       loaded via vars_files by deploy.yml only.
                                              deploy.yml's two callers
                                              (services/deployment.py,
                                              services/blue_green.py) invoke it with a
                                              bare `-i "<host>,"` inventory string, which
                                              gives Ansible no directory to discover
                                              group_vars from, so this is load-bearing
                                              there (#14678)

`tests/inventory/group_vars/all.yml`, the CI regression-test inventory's copy, is no
longer a third tracked copy -- it is generated from the canonical file at CI time and
gitignored (`check_test_inventory_is_generated.py` asserts the copy happened).

If either remaining copy drifts, behavior diverges silently. This script extracts the
role_*_active definitions from each and compares them; exits non-zero on any
divergence so CI fails the PR.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GROUP_VARS = REPO / "autobot-slm-backend/ansible/inventory/group_vars/all.yml"
PLAYBOOK_VARS = REPO / "autobot-slm-backend/ansible/playbooks/vars/role_active_facts.yml"


#: Keys that must stay identical across the copies but are NOT `role_*_active`
#: folded scalars, so the pattern below cannot find them.
#:
#: #14152 review: the guard's own comments claimed the files were kept
#: "byte-identical", but the regex only ever matched `role_\w+_active:` with a
#: `>-` value. `chromadb_service_owner` is a single-line double-quoted scalar
#: and was silently outside the comparison in all three files — so editing it
#: canonically and forgetting the duplicates would have reported OK while the
#: test inventory diverged. That is precisely the drift this guard exists to
#: catch, and the overstated comment is what made the gap invisible.
_EXTRA_SCALAR_KEYS = ("chromadb_service_owner",)


def extract_facts(path: Path) -> dict:
    """Extract the shared facts (key + value) that must match across copies.

    Returns dict mapping fact name → normalized whitespace value.
    """
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"(role_\w+_active:\s*>-(?:\n[ \t]+.*)*)")
    blocks = pattern.findall(text)
    facts = {re.match(r"(role_\w+_active)", b).group(1): re.sub(r"\s+", " ", b).strip() for b in blocks}

    # Single-line scalars the folded-block pattern cannot see. A key that is
    # absent from one copy and present in another must NOT compare equal, so
    # missing keys are recorded explicitly rather than skipped — an absent key
    # comparing clean is the same "empty reads as identical" failure.
    for key in _EXTRA_SCALAR_KEYS:
        match = re.search(rf"^{re.escape(key)}:.*$", text, re.MULTILINE)
        facts[key] = re.sub(r"\s+", " ", match.group(0)).strip() if match else "<ABSENT>"

    return facts


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


#: #14201: `tests/inventory/group_vars/all.yml`'s header once said it was kept
#: "byte-identical" to a sibling copy. It never was — three different files,
#: three different hashes — and the only thing this script actually enforces
#: is the role_*_active fragment (+ chromadb_service_owner) compared above. A
#: header claim with no check behind it is exactly how that happened, so any
#: of these three files' headers claiming whole-file byte-identity again is
#: itself a failure here, independent of whether the fragments still match.
#: Deliberately whole-file (not per-fragment): a fragment-level claim like
#: "these definitions are kept identical" is accurate and must NOT trip this.
_BYTE_IDENTITY_CLAIM = re.compile(r"byte[- ]identical", re.IGNORECASE)

# #14678: down to the two TRACKED copies. The test inventory's copy is now
# generated from `inventory/group_vars/all.yml` at CI time and gitignored, so
# it cannot drift by hand -- `check_test_inventory_is_generated.py` asserts the
# copy is present, is a real file (not a symlink, #14149) and matches.
#
# The remaining pair cannot be collapsed yet: deploy.yml's only two callers,
# `services/deployment.py` and `services/blue_green.py`, invoke it with a bare
# `-i "<host>,"` inventory string, which gives Ansible no directory to discover
# group_vars in, so deploy.yml's `vars_files` load is load-bearing on that path.
# Removing it needs those callers to write a real inventory first -- tracked as
# its own follow-up (#15348) so it doesn't block the rest of #14678.
_ROLE_FACTS_FILES = {
    "inventory/group_vars/all.yml": GROUP_VARS,
    "playbooks/vars/role_active_facts.yml": PLAYBOOK_VARS,
}


def _leading_comment_block(path: Path) -> str:
    """Return the leading `#`/blank-line header of a YAML file, stopping at
    the first substantive line (the `---` document marker or real content).
    """
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#"):
            lines.append(line)
            continue
        break
    return "\n".join(lines)


def check_no_false_byte_identity_claims() -> bool:
    """Return True (and print) if a header claims whole-file byte-identity
    the actual file contents do not back.

    Scoped to exactly the three files in `_ROLE_FACTS_FILES` -- a
    regression guard for this specific, known trio (#14201), not a
    general repo-wide scanner for the phrase. A different pair of files
    making the same mistake elsewhere would not be caught here.
    """
    contents = {label: path.read_bytes() for label, path in _ROLE_FACTS_FILES.items()}
    found_false_claim = False
    for label, path in _ROLE_FACTS_FILES.items():
        header = _leading_comment_block(path)
        if not _BYTE_IDENTITY_CLAIM.search(header):
            continue
        matches_a_sibling = any(contents[label] == contents[other] for other in _ROLE_FACTS_FILES if other != label)
        if not matches_a_sibling:
            print(
                f"HEADER CLAIM ERROR: {label}'s header claims byte-identity to a sibling, "
                "but no two of the three role-facts files are a whole-file byte match. "
                "Only the role_*_active fragment (+ chromadb_service_owner) is kept in "
                "sync, by this script — correct the header instead of restoring the "
                "claim (#14201)."
            )
            found_false_claim = True
    return found_false_claim


def main() -> int:
    canonical = extract_facts(GROUP_VARS)
    playbook = extract_facts(PLAYBOOK_VARS)

    diverged = False
    diverged |= compare("inventory/group_vars", canonical, "playbooks/vars", playbook)
    diverged |= check_no_false_byte_identity_claims()

    if diverged:
        return 1

    print(f"OK — {len(canonical)} shared facts identical across both tracked copies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
