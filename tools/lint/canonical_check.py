#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Canonical-check Python runner.

Two modes:
    --files <paths>   pre-commit mode: scan staged files only.
    --all             audit mode: walk every TARGETS directory.

Output:
    --format pretty    (default; stderr) terse violations grouped by file.
    --format markdown  (stdout) full audit report.
    --format json      (stdout) machine-readable diagnostic array.

Exit code:
    0   no BLOCK violations.
    1   one or more BLOCK violations.
    2   CLI / explain error.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make tools/ importable when invoked via shebang from anywhere
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.lint._canonical_cli import canonical_main  # noqa: E402
from tools.lint.canonical.registry import run_rules  # noqa: E402

_RULES_PACKAGE = "tools.lint.canonical.rules"


def _collect_all(ctx, targets, _repo_root):
    return list(ctx.iter_targets(targets, suffixes={".py"}))


def _select_files(files):
    return [Path(f) for f in files if f.endswith(".py")]


def main(argv: list[str] | None = None) -> int:
    return canonical_main(
        argv,
        description=__doc__,
        repo_root=_REPO_ROOT,
        rules_package=_RULES_PACKAGE,
        collect_all=_collect_all,
        select_files=_select_files,
        run_rules=run_rules,
    )


if __name__ == "__main__":
    sys.exit(main())
