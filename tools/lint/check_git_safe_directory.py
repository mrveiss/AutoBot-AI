#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression-prevention check for the #7150 git safe.directory migration.

Blocks new occurrences of `git -C {{ git_repo_root }}` (or with a literal
absolute path under /opt/autobot/code_source) in Ansible YAML that don't
also pass `-c safe.directory={{ git_repo_root }}`.

Why: when `code_source/` is owned by `autobot` (cloned by install.sh) and
the Ansible playbook runs as root via sudo, git 2.35+ aborts read-only
operations with rc=128 ("dubious ownership"). #7150 fixed 17 invocations
across 3 playbooks; #7219 found 7 more in update-all-nodes.yml that the
original sed missed because two files share the basename. Without this
guard, regressions are likely.

Acceptable forms:
  git -c safe.directory={{ git_repo_root }} -C {{ git_repo_root }} log -1
  git -c safe.directory=/opt/autobot/code_source -C ... ...

Blocked form:
  git -C {{ git_repo_root }} log -1
  git -C /opt/autobot/code_source ...

Exit:
  0 — clean
  1 — unguarded git command found
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

# `git -C <repo>` where <repo> is git_repo_root or /opt/autobot/code_source.
# Captures the flags between `git` and `-C` so we can check for `-c safe.directory`.
# No \b after the closing `}}` — those aren't word chars so the boundary doesn't match;
# rely on the literal terminator instead.
# #14181: the target group used to accept only the literal `{{ git_repo_root }}`
# or the literal path, which left the rule blind to every other Jinja name for
# the same directory. Three real unguarded sites were passing it that way --
# `{{ _code_source_dest }}` and `{{ code_source_dir | default(...) }}` in the
# update/deploy path, which is exactly where a `dubious ownership` rc=128 bites.
# The group now accepts any Jinja variable whose name contains `code_source` or
# `git_repo_root`, with an optional filter expression. Measured against the
# tracked tree: 22 matches, 19 of them already carrying `-c safe.directory`
# (the sites #7150's migration fixed), which is what says the widening targets
# the right shape rather than merely matching more.
#
# #14196: this used to run per physical line, which is blind to a command
# folded across a YAML `>-`/`|` block scalar — a real (fixed) instance dropped
# a guarded `git ... -C ...` invocation out of the checker's view entirely
# when it wrapped to a second line. `.yml`/`.yaml` are now parsed with PyYAML
# and every scalar's resolved *value* is matched instead of raw text, so a
# folded/literal command reads exactly as Ansible will evaluate it: one
# string, regardless of how many physical lines it was written across.
PATTERN = re.compile(
    r"\bgit\s+(?P<flags>[^\n]*?)-C\s+"
    r"(?:\{\{\s*[\w]*(?:code_source|git_repo_root)[\w]*\s*(?:\|[^}]*)?\}\}"
    r"|/opt/autobot/code_source(?=[\s/]))"
)
SAFE_FLAG = re.compile(r"-c\s+safe\.directory\s*=")

ALLOWLIST = frozenset(
    {
        "tools/lint/check_git_safe_directory.py",
        "tools/lint/check_git_safe_directory_test.py",
        # This hook's own registration: its `name:` and `description:` quote the
        # very pattern it looks for, so the rule matched its own documentation
        # (#14181). The file carries no Ansible tasks, so nothing is lost.
        ".pre-commit-config.yaml",
        "autobot-infrastructure/shared/config/.pre-commit-config.yaml",
    }
)


def iter_ansible_files(root: Path) -> Iterable[Path]:
    skip_dirs = {".git", "__pycache__", "node_modules", ".worktrees", "venv", ".venv"}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".yml", ".yaml"}:
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        yield path


def _iter_scalar_nodes(node: "yaml.Node") -> Iterable["yaml.ScalarNode"]:
    """Walk a composed YAML node tree, yielding every scalar node.

    Unlike the ansible-facts checker, no key context is needed here: a
    `git -C ...` invocation can live under `cmd:`, `command:`, a raw
    `- git ...` shell line, etc. — it is the string *content* that matters,
    not which key holds it.

    Mapping KEYS are scalars too and are yielded here alongside values --
    a walk that only descended into `value_node` would silently drop a
    dynamically-named key, the same coverage the line-based scanner had.

    PyYAML's `Composer` has no separate node type for an alias (`*anchor`):
    resolving one returns the *same* node object as its anchor definition
    (`yaml.AliasNode` does not exist), so a node reachable through more than
    one anchor/alias/merge-key site is revisited once per reachable path.
    That is a duplicate report for one physical scalar, not a missed one --
    harmless here, and there are currently zero YAML anchors in the tracked
    ansible tree.
    """
    if isinstance(node, yaml.ScalarNode):
        yield node
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            yield from _iter_scalar_nodes(item)
    elif isinstance(node, yaml.MappingNode):
        for key_node, value_node in node.value:
            if isinstance(key_node, yaml.ScalarNode):
                yield key_node
            yield from _iter_scalar_nodes(value_node)


def _yaml_violations(text: str) -> List[Tuple[int, str]]:
    try:
        documents = list(yaml.compose_all(text, Loader=yaml.SafeLoader))
    except yaml.YAMLError:
        # Malformed YAML is another hook's job (check-yaml); do not crash
        # pre-commit over a file this hook cannot parse.
        return []

    lines = text.splitlines()
    violations: List[Tuple[int, str]] = []
    for doc in documents:
        if doc is None:
            continue
        for node in _iter_scalar_nodes(doc):
            value = node.value
            match = PATTERN.search(value)
            if match and not SAFE_FLAG.search(match.group("flags")):
                lineno0 = node.start_mark.line
                snippet = lines[lineno0].strip()[:140] if 0 <= lineno0 < len(lines) else value.strip()[:140]
                violations.append((lineno0 + 1, snippet))
    return violations


def find_violations(path: Path) -> List[Tuple[int, str]]:
    try:
        rel = path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        rel = ""
    if rel in ALLOWLIST:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return _yaml_violations(text)


def main(paths: List[str]) -> int:
    if paths:
        targets = [Path(p) for p in paths]
        files = [p for p in targets if p.is_file() and p.suffix in {".yml", ".yaml"}]
    else:
        files = list(iter_ansible_files(REPO_ROOT / "autobot-slm-backend" / "ansible"))

    found = False
    for path in files:
        for lineno, snippet in find_violations(path):
            rel = path.relative_to(REPO_ROOT).as_posix() if path.is_absolute() else str(path)
            print(
                f"{rel}:{lineno}: unguarded `git -C {{{{ git_repo_root }}}}` (#7150) — "
                f"prepend `-c safe.directory={{{{ git_repo_root }}}}`\n  {snippet}",
                file=sys.stderr,
            )
            found = True

    if found:
        print(
            "\n--- BLOCKED ---\n"
            "On hosts where code_source is owned by a different user than the\n"
            "Ansible run-as user, git 2.35+ aborts with rc=128 'dubious ownership'.\n"
            "Use:  git -c safe.directory={{ git_repo_root }} -C {{ git_repo_root }} ...\n"
            "See #7150 (initial 17-site migration) and #7219 (lint guard).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
