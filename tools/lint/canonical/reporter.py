# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Output formatters: pretty (terminal), markdown (audit), JSON (artifact)."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from tools.lint.canonical.diagnostic import Diagnostic


def to_pretty(diagnostics: Sequence[Diagnostic]) -> str:
    if not diagnostics:
        return "canonical-check: 0 violations\n"

    by_severity: dict[str, int] = defaultdict(int)
    for d in diagnostics:
        by_severity[d.severity] += 1

    lines = [
        f"canonical-check: {len(diagnostics)} violations "
        f"(block={by_severity['block']}, warn={by_severity['warn']}, audit={by_severity['audit']})"
    ]

    grouped: dict[str, list[Diagnostic]] = defaultdict(list)
    for d in diagnostics:
        grouped[str(d.file)].append(d)

    for file_str in sorted(grouped):
        for d in sorted(grouped[file_str], key=lambda x: (x.line, x.col)):
            lines.append(f"  {file_str}:{d.line}  {d.rule_id}  ({d.issue}) [{d.severity}]")
            lines.append(f"    {d.message}")
    lines.append("")
    return "\n".join(lines)


def to_json(diagnostics: Sequence[Diagnostic]) -> str:
    return json.dumps([d.to_dict() for d in diagnostics], indent=2, sort_keys=True)


def to_markdown(
    diagnostics: Sequence[Diagnostic],
    *,
    scan_meta: dict[str, Any],
) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"# Canonical-style audit — {today}",
        f"{scan_meta.get('rule_count', 0)} rules · scanned "
        f"{scan_meta.get('scanned_files', 0)} files in "
        f"{scan_meta.get('duration_seconds', 0):.1f}s",
        "",
    ]

    if not diagnostics:
        lines.append("**no violations** — all rules clean.")
        lines.append("")
        return "\n".join(lines)

    by_sev: dict[str, list[Diagnostic]] = defaultdict(list)
    for d in diagnostics:
        by_sev[d.severity].append(d)

    by_rule: dict[str, list[Diagnostic]] = defaultdict(list)
    for d in diagnostics:
        by_rule[d.rule_id].append(d)

    top_rules = {
        sev: max(
            ((rid, len([d for d in ds if d.rule_id == rid])) for rid in {d.rule_id for d in ds}),
            key=lambda x: x[1],
            default=("—", 0),
        )
        for sev, ds in by_sev.items()
    }

    lines += [
        "## Summary",
        "| Severity | Total | Top rule |",
        "|---|---|---|",
    ]
    for sev in ("block", "warn", "audit"):
        ds = by_sev.get(sev, [])
        rule_id, rule_n = top_rules.get(sev, ("—", 0))
        lines.append(f"| {sev} | {len(ds)} | {rule_id} ({rule_n}) |")
    lines.append("")

    lines.append("## By rule")
    for rid in sorted(by_rule, key=lambda r: -len(by_rule[r])):
        ds = by_rule[rid]
        sev = ds[0].severity
        issue = ds[0].issue
        files = sorted({str(d.file) for d in ds})
        lines.append(f"### {rid} ({issue}) — {len(ds)} violations in {len(files)} files ({sev})")
        for f in files[:5]:
            n = sum(1 for d in ds if str(d.file) == f)
            lines.append(f"- {f} — {n} violations")
        if len(files) > 5:
            lines.append(f"- … +{len(files) - 5} more files")
        lines.append("")

    return "\n".join(lines)
