# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The CLI shared by ``canonical_check.py`` and ``canonical_check_infra.py`` (#14896).

The two runners were 112 lines each and identical except for the rules package,
which suffixes ``--all`` walks, how ``--files`` is filtered, and how a rule is
applied to a file. Those four are the parameters of :func:`canonical_main`;
everything else -- argument parsing, ``--explain``, the files-or-all exit ``2``,
the output sinks and ``--output``, the exit code -- lives here once.

Importers must already have the repository root on ``sys.path`` (both scripts
do, from their own location) because this imports ``tools.lint.canonical``.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Callable, Sequence

from tools.lint.canonical.context import Context
from tools.lint.canonical.registry import discover_rules
from tools.lint.canonical.reporter import to_json, to_markdown, to_pretty

CollectAll = Callable[[Context, list, Path], list]
SelectFiles = Callable[[Sequence[str]], list]
RunRules = Callable[[list, list, Context], list]


def parse_args(argv: list[str], description: str | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=description, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--files", nargs="*", help="Files to check (pre-commit mode)")
    g.add_argument("--all", action="store_true", help="Walk all TARGETS (audit mode)")
    p.add_argument("--explain", help="Print rule rationale and exit")
    p.add_argument("--format", choices=["pretty", "markdown", "json"], default="pretty")
    p.add_argument("--output", help="Write output to file instead of stdout")
    return p.parse_args(argv)


def explain(rules: list, rule_id: str) -> int:
    """Print one rule's rationale; ``2`` when no rule has that id."""
    rule = next((r for r in rules if r.RULE_ID == rule_id), None)
    if rule is None:
        print(f"unknown rule: {rule_id}", file=sys.stderr)
        return 2
    print(f"{rule.RULE_ID} ({rule.ISSUE}) [{rule.SEVERITY}]")
    print(rule.DESCRIPTION)
    print()
    print("Fix:")
    print(rule.FIX_HINT)
    return 0


def _render(fmt: str, diagnostics: list, meta: dict) -> tuple[str, object]:
    """``(text, sink)`` for the chosen ``--format``."""
    if fmt == "pretty":
        return to_pretty(diagnostics), sys.stderr
    if fmt == "markdown":
        return to_markdown(diagnostics, scan_meta=meta), sys.stdout
    return to_json(diagnostics), sys.stdout


def _emit(out: str, sink: object, output_path: str | None) -> None:
    if output_path:
        Path(output_path).write_text(out, encoding="utf-8")
        return
    sink.write(out)  # type: ignore[attr-defined]
    if not out.endswith("\n"):
        sink.write("\n")  # type: ignore[attr-defined]


def canonical_main(
    argv: list[str] | None,
    *,
    description: str | None,
    repo_root: Path,
    rules_package: str,
    collect_all: CollectAll,
    select_files: SelectFiles,
    run_rules: RunRules,
) -> int:
    """Run one canonical-check CLI; the keyword arguments are what differs per runner."""
    args = parse_args(sys.argv[1:] if argv is None else argv, description)
    rules = discover_rules(rules_package)
    if args.explain:
        return explain(rules, args.explain)
    if not args.files and not args.all:
        print("error: --files or --all required", file=sys.stderr)
        return 2
    ctx = Context(repo_root=repo_root)
    if args.all:
        files = collect_all(ctx, sorted({t for r in rules for t in r.TARGETS}), repo_root)
    else:
        files = select_files(args.files or [])
    start = time.monotonic()
    diagnostics = run_rules(rules, files, ctx)
    meta = {"scanned_files": len(files), "duration_seconds": time.monotonic() - start, "rule_count": len(rules)}
    out, sink = _render(args.format, diagnostics, meta)
    _emit(out, sink, args.output)
    return 1 if any(d.severity == "block" for d in diagnostics) else 0
