#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Canonical-check Infrastructure runner.

Mirrors canonical_check.py but operates on shell scripts, Ansible YAML, and
Dockerfiles. Rules receive only the file path (no AST) — they parse the text
themselves with appropriate tooling (regex, PyYAML, etc.).
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.lint._canonical_cli import canonical_main  # noqa: E402
from tools.lint.canonical.context import file_in_targets  # noqa: E402

_RULES_PACKAGE = "tools.lint.canonical.infra_rules"
_INFRA_SUFFIXES = {".sh", ".yml", ".yaml"}


def _collect_all(ctx, targets, repo_root):
    files = list(ctx.iter_targets(targets, suffixes=_INFRA_SUFFIXES))
    # Dockerfiles too — extension-less, but add by name match
    for target in targets:
        base = repo_root / target
        if base.exists():
            files.extend(p for p in base.rglob("Dockerfile*") if p.is_file())
    return files


def _select_files(files):
    return [Path(f) for f in files]


def _run_rules(rules, files, _ctx):
    diagnostics = []
    for f in files:
        for rule in rules:
            if not file_in_targets(f, rule.TARGETS, repo_root=_REPO_ROOT):
                continue
            diagnostics.extend(rule.check(f))
    return diagnostics


def main(argv: list[str] | None = None) -> int:
    return canonical_main(
        argv,
        description=__doc__,
        repo_root=_REPO_ROOT,
        rules_package=_RULES_PACKAGE,
        collect_all=_collect_all,
        select_files=_select_files,
        run_rules=_run_rules,
    )


if __name__ == "__main__":
    sys.exit(main())
