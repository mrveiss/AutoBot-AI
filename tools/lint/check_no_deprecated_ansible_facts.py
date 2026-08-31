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
from typing import Iterable, List, Optional, Tuple

import yaml

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
# positives on inventory vars (host, user, become_*, etc.). Used for scalar
# values that only run through Jinja *inside* `{{ }}` (the common case, and
# the only case for `.j2` templates, which are not YAML).
PATTERN = re.compile(r"\{\{[^}]*?\bansible_([a-z][a-z0-9_]*)\b")

# Bare `ansible_X` with no requirement for surrounding `{{ }}`. Ansible
# evaluates `when:`/`failed_when:`/etc. as Jinja without braces, so a plain
# `ansible_hostname` inside one of those keys is a live reference even
# though it never matches PATTERN.
ATTR_PATTERN = re.compile(r"\bansible_([a-z][a-z0-9_]*)\b")

# #14181: Ansible evaluates `when:` and friends as Jinja **without** `{{ }}`, so
# a pattern anchored on `{{ }}` cannot see them. That is not academic --
# `deploy-base.yml` carried the same fact on the same task in all three forms,
# two inside `{{ }}` and one in a `when:`. Fixing only the reported two would
# have moved the ansible-core 2.24 breakage from the template to the
# conditional while the hook reported the file clean.
#
# #14196: line-based scanning of `when:` (and friends) is itself blind to two
# common shapes: a folded/literal block scalar (`when: >-`, `until: |`) whose
# value spans several physical lines, and the list-style condition form
# (`when:` on its own line followed by `- cond_a` / `- cond_b`, all ANDed).
# Both shapes are invisible to a per-line regex but are ordinary YAML, so
# `.yml`/`.yaml` files are now parsed with PyYAML and walked structurally
# instead (see `_iter_scalar_nodes`/`_yaml_violations` below). `.j2` templates
# are not YAML at all and keep the line-based path.
_BARE_EXPR_KEYS = frozenset({"when", "failed_when", "changed_when", "until", "that"})

# Retained for the .j2 (line-based) path only.
BARE_EXPR_PATTERN = re.compile(
    r"^\s*-?\s*(?:" + "|".join(sorted(_BARE_EXPR_KEYS)) + r")\s*:.*?\bansible_([a-z][a-z0-9_]*)\b"
)

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


def _iter_scalar_nodes(
    node: "yaml.Node", key_context: Optional[str]
) -> Iterable[Tuple[Optional[str], "yaml.ScalarNode"]]:
    """Walk a composed YAML node tree, yielding (key_context, scalar_node).

    `key_context` is the name of the mapping key whose value this scalar is,
    propagated through sequences (a list-style `when:` condition list is
    still "under" `when`) but reset to the new key on every nested mapping —
    a task nested inside a `block:` gets its own `when:`/`vars:`/etc.

    Mapping KEYS are scalars too (`{{ ansible_hostname }}_status: ok` is a
    dynamically-named var) and are yielded here as well -- a walk that only
    descended into `value_node` would silently drop them, which is exactly
    the coverage the line-based scanner had and this rewrite must not lose.
    A key is never itself a bare-expr value (Ansible templates a mapping key
    the same `{{ }}`-wrapped way as any other string, never bare), so it is
    always yielded with `key_context=None`, regardless of what key the
    enclosing mapping is nested under.

    PyYAML's `Composer` has no separate node type for an alias (`*anchor`):
    resolving one returns the *same* node object as its anchor definition
    (`yaml.AliasNode` does not exist), so a node reachable through more than
    one anchor/alias/merge-key site is revisited once per reachable path and
    yielded once per visit. That is a duplicate report for one physical
    scalar, not a missed one -- harmless for `.pre-commit` output, and there
    are currently zero YAML anchors in the tracked ansible tree. Not
    de-duplicated on purpose: a shared node can sit under different keys at
    different reachable paths (e.g. one alias site under `when:`, another
    not), and de-duplicating on node identity would silently drop whichever
    context-dependent check ran second.
    """
    if isinstance(node, yaml.ScalarNode):
        yield key_context, node
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            yield from _iter_scalar_nodes(item, key_context)
    elif isinstance(node, yaml.MappingNode):
        for key_node, value_node in node.value:
            if isinstance(key_node, yaml.ScalarNode):
                yield None, key_node
            new_key = key_node.value if isinstance(key_node, yaml.ScalarNode) else None
            yield from _iter_scalar_nodes(value_node, new_key)


def _snippet(lines: List[str], node: "yaml.ScalarNode") -> str:
    lineno0 = node.start_mark.line
    if 0 <= lineno0 < len(lines):
        return lines[lineno0].strip()[:120]
    return node.value.strip()[:120]


def _yaml_violations(text: str) -> List[Tuple[int, str, str]]:
    """Structural scan for `.yml`/`.yaml`: parses the document(s) and
    evaluates each scalar's *value*, so folded/literal blocks and
    list-style `when:` conditions are visible regardless of how they are
    laid out across physical lines.
    """
    try:
        documents = list(yaml.compose_all(text, Loader=yaml.SafeLoader))
    except yaml.YAMLError:
        # Malformed YAML is another hook's job (check-yaml); do not crash
        # pre-commit over a file this hook cannot parse.
        return []

    lines = text.splitlines()
    violations: List[Tuple[int, str, str]] = []
    for doc in documents:
        if doc is None:
            continue
        for key_context, node in _iter_scalar_nodes(doc, None):
            value = node.value
            pattern = ATTR_PATTERN if key_context in _BARE_EXPR_KEYS else PATTERN
            seen: set = set()
            for match in pattern.finditer(value):
                attr = match.group(1)
                if attr in FACT_ATTRS and attr not in seen:
                    seen.add(attr)
                    violations.append((node.start_mark.line + 1, attr, _snippet(lines, node)))
    return violations


def _line_based_violations(text: str) -> List[Tuple[int, str, str]]:
    """Line-by-line scan, used only for `.j2` templates (not valid YAML)."""
    violations: List[Tuple[int, str, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        seen_on_line: set = set()
        for pattern in (PATTERN, BARE_EXPR_PATTERN):
            for match in pattern.finditer(line):
                attr = match.group(1)
                if attr in FACT_ATTRS and attr not in seen_on_line:
                    seen_on_line.add(attr)
                    violations.append((lineno, attr, line.strip()[:120]))
    return violations


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
    if path.suffix == ".j2":
        return _line_based_violations(text)
    return _yaml_violations(text)


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
