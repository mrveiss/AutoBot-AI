#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Fail when `autobot_ssh_key_path` can be undefined at run time (#14226).

The variable lived only in `inventory/group_vars/all.yml`. `group_vars` is
loaded from the inventory in use, so any play run against an inventory without
that directory — a DB-driven or otherwise dynamic one, cf. #7094 — left it
undefined and aborted `roles/common`:

    fatal: [node_00_SLM_Manager]: 'autobot_ssh_key_path' is undefined
    ... roles/common/tasks/main.yml': line 102

Observed on a live /opt/autobot provisioning run, failing every host in the
play. Four other sites already guarded the same value with
`| default('/etc/autobot/ssh/autobot_key')`, including one labelled canonical
(#12429) — so the value had two spellings and the unguarded one is what runs
under a dynamic inventory.

Two rules, because roles and plays resolve variables differently:

* A **role** may use the variable bare **iff** its own `defaults/main.yml`
  defines it. Role defaults are the lowest precedence, so `group_vars` still
  wins wherever it is loaded; the role simply stops depending on that.
* A **playbook** has no role defaults to fall back on, so every use must carry
  an explicit `| default(...)`.

Files under `inventory/` are exempt: `group_vars/all.yml` is loaded alongside
them by definition.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404  # git plumbing, fixed argv, no shell
import sys
from pathlib import Path

# The scrubbed root resolver lives in ``autobot_shared``; this script is run
# directly, so the import path is bootstrapped from this file's own location
# -- the one derivation an inherited GIT_DIR cannot confuse (#15176).
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from autobot_shared.paths import (  # noqa: E402
    GitRepoRootUnavailable,
    git_repo_root,
    scrubbed_git_env,
)

VAR = "autobot_ssh_key_path"
_GUARDED = re.compile(rf"{VAR}\s*\|\s*default\(")


def _repo_root() -> Path:
    """Absolute repo root, with the ambient git environment scrubbed first.

    Measured for #15176 before the scrub: run from ``repo_tests/`` with
    ``GIT_DIR`` exported, this resolved the root to ``repo_tests/`` and died
    with an uncaught ``FileNotFoundError`` on the first
    ``roles/*/defaults/main.yml`` read — loud, but blaming a missing role
    default rather than the root it was joined to.
    """
    try:
        return git_repo_root()
    except GitRepoRootUnavailable as exc:
        sys.exit(f"FATAL: cannot locate the repo root: {exc}")


def _tracked_yaml(root: Path) -> list[str]:
    result = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "autobot-slm-backend/ansible/*.yml", "autobot-slm-backend/ansible/*.yaml"],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        # Same scrub as the root: an inherited GIT_DIR would enumerate one
        # checkout's index while *root* names another (#15176).
        env=scrubbed_git_env(),
    )
    if result.returncode != 0:
        sys.exit(f"FATAL: git ls-files failed: {result.stderr.strip()}")
    files = result.stdout.split()
    if not files:
        sys.exit("FATAL: git ls-files listed no ansible YAML — refusing to report clean on an empty scope")
    return files


def _role_of(rel: str) -> str | None:
    parts = rel.split("/")
    if "roles" in parts:
        i = parts.index("roles")
        if i + 1 < len(parts):
            return "/".join(parts[: i + 2])
    return None


def violations(root: Path) -> list[str]:
    """Every bare use that has no default available to it."""
    roles_with_default: set[str] = set()
    files = _tracked_yaml(root)

    for rel in files:
        if not rel.endswith("defaults/main.yml"):
            continue
        text = (root / rel).read_text(encoding="utf-8")
        if re.search(rf"^{VAR}\s*:", text, re.M):
            role = _role_of(rel)
            if role:
                roles_with_default.add(role)

    found: list[str] = []
    for rel in files:
        if "/inventory/" in rel or rel.endswith("defaults/main.yml"):
            continue
        for lineno, line in enumerate((root / rel).read_text(encoding="utf-8").splitlines(), 1):
            if VAR not in line or _GUARDED.search(line):
                continue
            role = _role_of(rel)
            if role and role in roles_with_default:
                continue  # the role supplies its own default
            where = "playbook" if role is None else f"role {role} (no defaults entry)"
            found.append(f"{rel}:{lineno}: bare `{VAR}` in a {where}")
    return found


def main() -> int:
    root = _repo_root()
    found = violations(root)
    if not found:
        print(f"check-ssh-key-path: every `{VAR}` use has a default available")  # noqa: print
        return 0
    print(f"check-ssh-key-path: {len(found)} unguarded use(s)\n")  # noqa: print
    for item in found:
        print(f"  FAIL  {item}")  # noqa: print
    print(  # noqa: print
        "\nA play run against an inventory without group_vars/ aborts on these.\n"
        "Either add the variable to the role's defaults/main.yml, or use\n"
        f"`{VAR} | default('/etc/autobot/ssh/autobot_key')` in a playbook.\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
