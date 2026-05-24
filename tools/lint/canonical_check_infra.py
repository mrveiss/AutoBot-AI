#!/usr/bin/env python3
"""Canonical-check Infrastructure runner.

Mirrors canonical_check.py but operates on shell scripts, Ansible YAML, and
Dockerfiles. Rules receive only the file path (no AST) — they parse the text
themselves with appropriate tooling (regex, PyYAML, etc.).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.lint.canonical.context import Context, file_in_targets  # noqa: E402
from tools.lint.canonical.registry import discover_rules  # noqa: E402
from tools.lint.canonical.reporter import to_json, to_markdown, to_pretty  # noqa: E402

_RULES_PACKAGE = "tools.lint.canonical.infra_rules"
_INFRA_SUFFIXES = {".sh", ".yml", ".yaml"}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--files", nargs="*", help="Files to check (pre-commit mode)")
    g.add_argument("--all", action="store_true", help="Walk all TARGETS (audit mode)")
    p.add_argument("--explain", help="Print rule rationale and exit")
    p.add_argument("--format", choices=["pretty", "markdown", "json"], default="pretty")
    p.add_argument("--output", help="Write output to file instead of stdout")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    rules = discover_rules(_RULES_PACKAGE)

    if args.explain:
        rule = next((r for r in rules if r.RULE_ID == args.explain), None)
        if rule is None:
            print(f"unknown rule: {args.explain}", file=sys.stderr)
            return 2
        print(f"{rule.RULE_ID} ({rule.ISSUE}) [{rule.SEVERITY}]")
        print(rule.DESCRIPTION)
        print()
        print("Fix:")
        print(rule.FIX_HINT)
        return 0

    if not args.files and not args.all:
        print("error: --files or --all required", file=sys.stderr)
        return 2

    ctx = Context(repo_root=_REPO_ROOT)

    if args.all:
        all_targets = sorted({t for r in rules for t in r.TARGETS})
        files = list(ctx.iter_targets(all_targets, suffixes=_INFRA_SUFFIXES))
        # Dockerfiles too — extension-less, but add by name match
        for target in all_targets:
            base = _REPO_ROOT / target
            if base.exists():
                files.extend(p for p in base.rglob("Dockerfile*") if p.is_file())
    else:
        files = [Path(f) for f in (args.files or [])]

    diagnostics = []
    start = time.monotonic()
    for f in files:
        for rule in rules:
            if not file_in_targets(f, rule.TARGETS, repo_root=_REPO_ROOT):
                continue
            diagnostics.extend(rule.check(f))
    duration = time.monotonic() - start

    if args.format == "pretty":
        out = to_pretty(diagnostics)
        sink = sys.stderr
    elif args.format == "markdown":
        out = to_markdown(
            diagnostics,
            scan_meta={
                "scanned_files": len(files),
                "duration_seconds": duration,
                "rule_count": len(rules),
            },
        )
        sink = sys.stdout
    else:
        out = to_json(diagnostics)
        sink = sys.stdout

    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
    else:
        sink.write(out)
        if not out.endswith("\n"):
            sink.write("\n")

    blocking = sum(1 for d in diagnostics if d.severity == "block")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
