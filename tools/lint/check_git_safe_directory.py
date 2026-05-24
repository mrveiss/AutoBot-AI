#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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

REPO_ROOT = Path(__file__).resolve().parents[2]

# `git -C <repo>` where <repo> is git_repo_root or /opt/autobot/code_source.
# Captures the flags between `git` and `-C` so we can check for `-c safe.directory`.
# No \b after the closing `}}` — those aren't word chars so the boundary doesn't match;
# rely on the literal terminator instead.
PATTERN = re.compile(
    r"\bgit\s+(?P<flags>[^\n]*?)-C\s+" r"(?:\{\{\s*git_repo_root\s*\}\}|/opt/autobot/code_source(?=[\s/]))"
)
SAFE_FLAG = re.compile(r"-c\s+safe\.directory\s*=")

ALLOWLIST = frozenset(
    {
        "tools/lint/check_git_safe_directory.py",
        "tools/lint/check_git_safe_directory_test.py",
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
    violations: List[Tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        match = PATTERN.search(line)
        if match and not SAFE_FLAG.search(match.group("flags")):
            violations.append((lineno, line.strip()[:140]))
    return violations


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
