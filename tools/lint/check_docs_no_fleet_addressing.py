#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15208 — no Markdown document under ``docs/`` may carry a literal fleet node address.

#3315 replaced the fleet's literal node addresses in ``docs/architecture/`` with the
role placeholders defined in ``docs/architecture/VM_ROLES.md``. Nothing stopped the
next document from writing a literal again, and nothing looked outside the folder that
sweep happened to target: the addressing survived for months in ``docs/archives/plans/``,
one directory across, together with the role-to-host and database-endpoint mappings that
make an address list into a network map.

WHY NO EXISTING GUARD SEES THIS. ``scripts/lib/hardcoded-value-rules.sh`` — the union
detector behind both ``pipeline-scripts/detect-hardcoded-values.sh`` and the
``pre-commit-hardcoded-values`` hook — scans ``HV_SCAN_EXTENSIONS`` only, and that list
is ``py|ts|vue|js|sh|yml|yaml``. Markdown is not in it, and the frontend
``no-hardcoded-vm-ip`` ESLint rule and ``check_no_hardcoded_ip_fallbacks.py`` are
narrower still (TypeScript literals, Python ``os.getenv`` fallbacks). Documentation had
no gate at all, which is exactly why the exposure aged rather than being caught.

THE PATTERN IS NOT COPIED. This module holds no address literal of its own; it parses
the ``HV_VM_IP`` assignment out of ``scripts/lib/hardcoded-value-rules.sh`` and reuses
it. One definition of "a fleet address" serves code and documentation, so a renumbered
fleet updates both guards at once — and a second, drifting copy of the range cannot come
into existence here. A missing or unparseable source aborts loudly, the same doctrine
that file applies to its own dependencies: an unread pattern and an empty one are
indistinguishable to every caller.

WHAT IS DELIBERATE STAYS, BY STRUCTURE NOT BY FILENAME. Some documents cite an address
on purpose — ``docs/developer/HARDCODING_PREVENTION.md`` documents the very regexes the
hardcoded-value hook and the ESLint rule match, and a counter-example with the literal
removed stops demonstrating anything. Those are exempted by an HTML comment placed in
the document, scoping the exemption to the block it introduces::

    <!-- fleet-addressing-exempt: documents the pattern the hook matches -->

    - Hardcoded VM IPs (`<the literal range>`)

A whole file may be exempted with ``fleet-addressing-exempt-file``. The exemption is a
*parsed Markdown block marker*, not a path in a list: it lives beside the text it
excuses, it states its reason there, it moves with the text, and it cannot silently
widen to cover a leak that lands later in the same file. A marker introducing a block
that carries no address is itself a finding — a stranded exemption is a stale claim.

REACH FLOOR. The audit reports how many Markdown files it reached and fails below
``DISCOVERY_FLOOR``. A sweep whose glob stops matching finds no offenders and reports
success, which is indistinguishable from a clean tree; #15208 exists because a sweep
that never looked at ``docs/archives/`` reported exactly that.
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import re
import sys
from typing import Iterable, NamedTuple

# Plain stdlib logging, deliberately (#1082). This runs as a bare script inside a lint
# job, and `autobot_shared.logging_manager` would drag config loading into it.
logger = logging.getLogger(__name__)

DOCS_DIR = "docs"
SELF_REL = "tools/lint/check_docs_no_fleet_addressing.py"
RULES_REL = "scripts/lib/hardcoded-value-rules.sh"
ROLES_DOC = "docs/architecture/VM_ROLES.md"

# docs/ held 811 Markdown files when this guard landed. The floor sits well below that
# so ordinary archival churn does not trip it, and well above zero so a broken glob does.
DISCOVERY_FLOOR = 600

#: What this guard reads, for tools/lint/check_code_quality_guard_reach.py
#: (#14550/#14551). The sweep covers every Markdown file under docs/; the two entries
#: are the real files standing for its two inputs — the archived tree #3315 never
#: reached, and the rule set the address pattern is parsed from. Both must be covered
#: by code-quality.yml's `backend` path filter: a PR touching only documentation would
#: otherwise skip the job, and a skipped required job satisfies branch protection —
#: so the guard could not fire on the change it exists to catch.
GUARD_INPUT_PATHS = ("docs/archives/_index.md", RULES_REL)

EXEMPT_BLOCK = "fleet-addressing-exempt"
EXEMPT_FILE = "fleet-addressing-exempt-file"

_HV_VM_IP_ASSIGNMENT = re.compile(r"^HV_VM_IP='(?P<pattern>[^']+)'", re.MULTILINE)
_MARKER_RE = re.compile(r"<!--\s*(?P<kind>fleet-addressing-exempt(?:-file)?)\s*:(?P<reason>[^>]*?)-->")
_FENCE_RE = re.compile(r"^\s*(?P<fence>```+|~~~+)")


class Finding(NamedTuple):
    """One offending line: repo-relative path, 1-based line number, and its text."""

    path: str
    lineno: int
    text: str


class Block(NamedTuple):
    """A Markdown block: its 1-based start line and its lines."""

    start: int
    lines: list[str]


def repo_root() -> pathlib.Path:
    """Repo root, derived from this file's location (``tools/lint/`` is two deep)."""
    return pathlib.Path(__file__).resolve().parents[2]


def fleet_address_pattern(base: pathlib.Path | None = None) -> re.Pattern[str]:
    """The canonical fleet-address regex, read from the shared hardcoded-value rules.

    Raises ``RuntimeError`` rather than falling back: a guard that cannot load its
    pattern must fail, not report a comfortable zero.
    """
    base = base or repo_root()
    source = base / RULES_REL
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"cannot read the canonical rule set at {RULES_REL}: {exc}") from exc
    match = _HV_VM_IP_ASSIGNMENT.search(text)
    if not match:
        raise RuntimeError(f"no HV_VM_IP assignment found in {RULES_REL} — the guard has no pattern to apply")
    return re.compile(match.group("pattern"))


def discover_markdown_files(base: pathlib.Path | None = None) -> list[pathlib.Path]:
    """Every tracked-shaped ``*.md`` under ``docs/``."""
    base = base or repo_root()
    docs = base / DOCS_DIR
    if not docs.is_dir():
        return []
    return sorted(p for p in docs.rglob("*.md") if p.is_file())


def split_blocks(lines: list[str]) -> list[Block]:
    """Split Markdown into blank-line-separated blocks, keeping fenced code whole."""
    blocks: list[Block] = []
    current: list[str] = []
    start = 1
    fence: str | None = None
    for index, line in enumerate(lines, start=1):
        fence = _next_fence_state(line, fence)
        if fence is None and not line.strip():
            if current:
                blocks.append(Block(start, current))
                current = []
            continue
        if not current:
            start = index
        current.append(line)
    if current:
        blocks.append(Block(start, current))
    return blocks


def _next_fence_state(line: str, fence: str | None) -> str | None:
    """Track whether *line* opens or closes a fenced code block."""
    match = _FENCE_RE.match(line)
    if not match:
        return fence
    marker = match.group("fence")
    if fence is None:
        return marker
    return None if marker[0] == fence[0] and len(marker) >= len(fence) else fence


def _marker_kind(block: Block) -> str | None:
    """The exemption kind a block declares, when the block is only that marker."""
    joined = "\n".join(block.lines).strip()
    match = _MARKER_RE.fullmatch(joined)
    return match.group("kind") if match else None


def scan_document(rel: str, text: str, pattern: re.Pattern[str]) -> tuple[list[Finding], list[str]]:
    """Findings and stranded-exemption problems for one document."""
    lines = text.split("\n")
    if _MARKER_RE.search(text) and any(_marker_kind(b) == EXEMPT_FILE for b in split_blocks(lines)):
        return [], _stranded_file(rel, lines, pattern)
    findings: list[Finding] = []
    problems: list[str] = []
    pending: str | None = None
    for block in split_blocks(lines):
        kind = _marker_kind(block)
        if kind is not None:
            pending = kind
            continue
        hits = _block_hits(rel, block, pattern)
        if pending == EXEMPT_BLOCK and not hits:
            problems.append(
                f"{rel}:{block.start}: stranded {EXEMPT_BLOCK} marker — "
                "the block it covers carries no address"
            )
        if pending != EXEMPT_BLOCK:
            findings.extend(hits)
        pending = None
    return findings, problems


def _stranded_file(rel: str, lines: list[str], pattern: re.Pattern[str]) -> list[str]:
    """A file-level exemption over a file with no address is a stale claim."""
    if any(pattern.search(line) for line in lines):
        return []
    return [f"{rel}: stranded {EXEMPT_FILE} marker — the file carries no address"]


def _block_hits(rel: str, block: Block, pattern: re.Pattern[str]) -> list[Finding]:
    """Every offending line inside one block."""
    return [
        Finding(rel, block.start + index, line.strip())
        for index, line in enumerate(block.lines)
        if pattern.search(line)
    ]


def check_paths(
    paths: Iterable[pathlib.Path], base: pathlib.Path, pattern: re.Pattern[str]
) -> tuple[list[Finding], list[str]]:
    """Scan the given Markdown files. An unreadable file is a problem, never a skip."""
    findings: list[Finding] = []
    problems: list[str] = []
    for path in paths:
        rel = str(path.relative_to(base)) if path.is_relative_to(base) else str(path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            problems.append(f"{rel}: unreadable ({exc}) — skipping it would let a leak hide behind an I/O error")
            continue
        hits, stranded = scan_document(rel, text, pattern)
        findings.extend(hits)
        problems.extend(stranded)
    return findings, problems


def _format_findings(findings: list[Finding]) -> str:
    """One ``path:line`` per finding. The matched text is deliberately not echoed."""
    return "\n".join(f"  {f.path}:{f.lineno}" for f in findings)


def _leak_problem(findings: list[Finding]) -> str:
    """The operator-facing message for a set of address findings."""
    files = len({f.path for f in findings})
    return (
        f"{len(findings)} line(s) across {files} document(s) carry a literal fleet node address:\n"
        + _format_findings(findings)
        + f"\n\nReplace each with the role placeholder for its node — see {ROLES_DOC} — as #3315 did "
        f"for docs/architecture/. Where the literal is a deliberate counter-example, introduce the "
        f"block with an inline <!-- {EXEMPT_BLOCK}: reason --> marker stating why (#15208)."
    )


def audit(base: pathlib.Path | None = None) -> tuple[int, list[str]]:
    """Sweep every Markdown file under ``docs/``. Returns (files reached, problems)."""
    base = base or repo_root()
    problems: list[str] = []
    pattern = fleet_address_pattern(base)
    files = discover_markdown_files(base)
    if len(files) < DISCOVERY_FLOOR:
        problems.append(
            f"discovery returned only {len(files)} Markdown file(s) under {DOCS_DIR}/ "
            f"(floor {DISCOVERY_FLOOR}) — the sweep broke, so a clean result below would assert nothing."
        )
    findings, scan_problems = check_paths(files, base, pattern)
    problems.extend(scan_problems)
    if findings:
        problems.append(_leak_problem(findings))
    return len(files), problems


def _selected_paths(paths: list[str], base: pathlib.Path) -> list[pathlib.Path]:
    """Resolve CLI paths to existing Markdown files."""
    resolved = [pathlib.Path(p) if pathlib.Path(p).is_absolute() else base / p for p in paths]
    return [p for p in resolved if p.suffix == ".md" and p.is_file()]


def configure_logging() -> None:
    """Attach a stderr handler so findings actually reach the developer."""
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def _run(args: argparse.Namespace, base: pathlib.Path) -> tuple[str, list[str]]:
    """Execute the requested scope, returning (scope description, problems)."""
    if args.audit:
        reached, problems = audit(base)
        return f"{reached} Markdown file(s) under {DOCS_DIR}/", problems
    selected = _selected_paths(args.paths, base)
    findings, problems = check_paths(selected, base, fleet_address_pattern(base))
    if findings:
        problems.append(_leak_problem(findings))
    return f"{len(selected)} given file(s)", problems


def main(argv: list[str]) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--audit", action="store_true", help=f"sweep every Markdown file under {DOCS_DIR}/")
    parser.add_argument("paths", nargs="*", help="Markdown files to check")
    args = parser.parse_args(argv)
    if not args.audit and not args.paths:
        parser.error("nothing to do — pass --audit or one or more paths")
    base = repo_root()
    try:
        scope, problems = _run(args, base)
    except RuntimeError as exc:
        logger.error("fleet-addressing audit ABORTED: %s (#15208).", exc)
        return 1
    if problems:
        logger.error("%s", "\n\n".join(problems))
        logger.error("\nfleet-addressing audit FAILED over %s (#15208).", scope)
        return 1
    logger.info("fleet-addressing audit clean over %s (#15208).", scope)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
