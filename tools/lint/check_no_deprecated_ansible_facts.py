#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression-prevention check for the #7180 ansible_facts migration.

Blocks new occurrences of `{{ ansible_X }}` (X being an auto-injected
fact attribute like `default_ipv4`, `hostname`, `distribution_release`).
Such references will silently become undefined when ansible-core 2.24
removes the `INJECT_FACTS_AS_VARS` default.

Use `{{ ansible_facts['X'] }}` (or `ansible_facts.X` when surrounding
quotes would collide) instead.

Connection/inventory variables (`ansible_user`, `ansible_host`,
`ansible_become_*`, `ansible_python_interpreter`, `ansible_ssh_*`,
`ansible_connection`, `ansible_port`, `ansible_password`) are NOT
auto-injected facts and are intentionally excluded.

This hook covers regression of #7180 (84 files mass-replaced).

Exit code:
  0 — clean
  1 — banned patterns found (commit blocked)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]

# Auto-injected fact attributes deprecated by INJECT_FACTS_AS_VARS removal.
# Connection vars (host, user, become_*, ssh_*, python_interpreter, etc.)
# are NOT facts — they're inventory variables and remain valid.
FACT_ATTRS = frozenset(
    {
        "date_time",
        "iso8601",
        "iso8601_basic",
        "iso8601_basic_short",
        "default_ipv4",
        "default_ipv6",
        "all_ipv4_addresses",
        "all_ipv6_addresses",
        "interfaces",
        "hostname",
        "fqdn",
        "nodename",
        "domain",
        "distribution",
        "distribution_release",
        "distribution_version",
        "distribution_major_version",
        "distribution_file_variety",
        "os_family",
        "kernel",
        "kernel_version",
        "architecture",
        "machine",
        "env",
        "mounts",
        "devices",
        "serial",
        "processor_count",
        "processor_cores",
        "processor_threads_per_core",
        "processor_vcpus",
        "memtotal_mb",
        "memfree_mb",
        "swaptotal_mb",
        "swapfree_mb",
        "memory_mb",
        "product_name",
        "product_serial",
        "product_uuid",
        "product_version",
        "system",
        "system_vendor",
        "bios_version",
        "bios_date",
        "virtualization_type",
        "virtualization_role",
        "pkg_mgr",
        "service_mgr",
        "lsb",
        "selinux",
        "apparmor",
        "fips",
        "user_dir",
        "user_gid",
        "user_uid",
        "user_gecos",
        "user_shell",
        "is_chroot",
        "play_role_names",
        "play_hosts",
        "play_batch",
        "python",
        "python_version",
    }
)

# `{{ ansible_X.Y }}`, `{{ ansible_X[0] }}`, `{{ ansible_X|filter }}`, `{{ ansible_X }}`
# Captures the attribute name; we filter against FACT_ATTRS to avoid false
# positives on inventory vars (host, user, become_*, etc.).
PATTERN = re.compile(r"\{\{[^}]*?\bansible_([a-z][a-z0-9_]*)\b")

# Files allowed to contain the banned patterns (the hook itself + tests).
ALLOWLIST = frozenset(
    {
        "tools/lint/check_no_deprecated_ansible_facts.py",
        "tools/lint/check_no_deprecated_ansible_facts_test.py",
    }
)


def iter_ansible_files(root: Path) -> Iterable[Path]:
    """Yield .yml/.yaml/.j2 files under root, skipping vendored/cached dirs."""
    skip_dirs = {".git", "__pycache__", "node_modules", ".worktrees", "venv", ".venv"}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".yml", ".yaml", ".j2"}:
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        yield path


def find_violations(path: Path) -> List[Tuple[int, str, str]]:
    """Return (line_number, attribute, snippet) tuples for each violation."""
    try:
        rel = path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        # Path outside repo (e.g. tempfile during tests) — no allowlist match
        rel = ""
    if rel in ALLOWLIST:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    violations: List[Tuple[int, str, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in PATTERN.finditer(line):
            attr = match.group(1)
            if attr in FACT_ATTRS:
                violations.append((lineno, attr, line.strip()[:120]))
    return violations


def main(paths: List[str]) -> int:
    if paths:
        targets = [Path(p) for p in paths]
        files = [p for p in targets if p.is_file() and p.suffix in {".yml", ".yaml", ".j2"}]
    else:
        # Scan the whole ansible tree if invoked with no args (manual run).
        files = list(iter_ansible_files(REPO_ROOT / "autobot-slm-backend" / "ansible"))

    found = False
    for path in files:
        for lineno, attr, snippet in find_violations(path):
            rel = path.relative_to(REPO_ROOT).as_posix() if path.is_absolute() else str(path)
            print(
                f"{rel}:{lineno}: deprecated `ansible_{attr}` (#7180) — "
                f"use `ansible_facts['{attr}']` instead\n  {snippet}",
                file=sys.stderr,
            )
            found = True

    if found:
        print(
            "\n--- BLOCKED ---\n"
            "ansible-core 2.24 will remove INJECT_FACTS_AS_VARS, breaking these references.\n"
            "Replace `{{ ansible_X }}` with `{{ ansible_facts['X'] }}` (or "
            "`ansible_facts.X` if surrounding quotes would collide).\n"
            "See #7180 for the migration that landed 84 files.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
