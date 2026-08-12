#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Guard: the role-facts test inventory must actually inherit group_vars (#14149).

`tests/inventory/group_vars/all.yml` used to be a symlink to the canonical
`inventory/group_vars/all.yml`. This repo runs with `core.symlinks=false` on
some checkouts (WSL2 — see docs/developer/BACKEND_DEBUGGING.md), and git
cannot create a real symlink there: a tracked symlink is materialized as a
plain-text file whose entire content is the target path string. Ansible then
loads a bare YAML scalar instead of a mapping for that group_vars file.

Nothing in the existing test suite asserted the test inventory actually has
content — `ansible-playbook -i tests/inventory/test_role_facts.yml ...`
passed on every CI run because GitHub-hosted Linux runners keep
`core.symlinks=true` by default, so the symlink round-trips there even
though it silently breaks on the checkouts where it does not.

This check loads the test inventory the same way `ansible-inventory --list`
does and asserts a known key from the canonical group_vars file
(`role_backend_active`) is present and non-empty for a synthetic host. Run
from the ansible directory:

    python3 tests/check_test_inventory_group_vars.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ANSIBLE_DIR = Path(__file__).resolve().parents[1]
INVENTORY = "tests/inventory/test_role_facts.yml"
KNOWN_HOST = "test-single-host-slm-and-backend"
KNOWN_KEY = "role_backend_active"


def main() -> int:
    # log_path in ansible.cfg points at /var/log/autobot/ansible.log, which
    # this check must never require write access to.
    env = dict(os.environ)
    with tempfile.TemporaryDirectory() as tmp:
        env["ANSIBLE_LOG_PATH"] = str(Path(tmp) / "ansible.log")
        result = subprocess.run(
            ["ansible-inventory", "--list", "-i", INVENTORY],
            cwd=ANSIBLE_DIR,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    if result.returncode != 0:
        print(f"ansible-inventory --list -i {INVENTORY} exited {result.returncode}")
        print("--- stdout ---")
        print(result.stdout)
        print("--- stderr ---")
        print(result.stderr)
        print(
            "\nThe test inventory's group_vars/all.yml failed to load as a mapping. "
            "If this is a symlink, core.symlinks=false checkouts materialize it as a "
            "plain-text path string instead of YAML content (#14149)."
        )
        return 1

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(f"ansible-inventory --list produced non-JSON output: {exc}")
        print(result.stdout)
        return 1

    hostvars = data.get("_meta", {}).get("hostvars", {}).get(KNOWN_HOST, {})
    value = hostvars.get(KNOWN_KEY)

    if not value:
        print(
            f"{KNOWN_HOST!r} is missing {KNOWN_KEY!r} (or it is empty) after loading "
            f"{INVENTORY} — the test inventory did not inherit group_vars."
        )
        print(f"hostvars keys seen: {sorted(hostvars)}")
        return 1

    print(f"OK — {INVENTORY} resolves {KNOWN_KEY!r} for {KNOWN_HOST!r}: {value!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
