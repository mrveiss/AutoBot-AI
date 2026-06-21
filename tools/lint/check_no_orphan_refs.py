#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Orphan-ref audit for Vue composables (Issue #5349).

Detects the bug class behind #5277 (hardcodes panel fetched but not
rendered) and #5340 (refactoringSuggestions declared + exported but
never populated): a ``ref()`` / ``shallowRef()`` / ``reactive()``
declared in a composable, returned from it, and never assigned to
anywhere in the file.

What it flags
-------------

For each composable under ``autobot-frontend/src/composables/**/*.ts``:

1. Every ``const NAME = ref(...)`` / ``const NAME = shallowRef(...)``
   / ``const NAME = reactive(...)`` declaration.
2. Whether the composable's return object lists ``NAME``.
3. Whether any subsequent line in the file writes to ``NAME.value``
   (``NAME.value = ...``, ``NAME.value.push(...)``, etc.) or
   reassigns a property on the reactive object.

A ref that is *declared + returned + never written* is a dead data
flow — a panel consuming it will silently render nothing, which is
exactly the shape of #5340.

Limitations
-----------

- Heuristic (regex-based). Misses cross-file populators if a consumer
  imports and writes the ref (rare; composables typically own their
  state).
- Does not run the TypeScript compiler — fast but dumb.
- Does not check consumer-side (does any caller destructure the ref?)
  — that's a broader codebase grep, separate check.

Exit codes
----------
- ``0``: no orphans found.
- ``1``: orphans found (list printed to stderr).
- ``2``: usage error.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, NamedTuple

# Match `const NAME = ref(...)`, `= shallowRef(...)`, `= reactive(...)`,
# including across line breaks. NAME is captured.
_DECL_RE = re.compile(
    r"^[\t ]*const\s+(\w+)\s*=\s*(?:ref|shallowRef|reactive)\b",
    re.MULTILINE,
)


class OrphanRef(NamedTuple):
    file: Path
    name: str
    line: int


def _find_decls(source: str) -> List[tuple[str, int]]:
    """Return (name, line_number_1_indexed) for each reactive declaration."""
    decls: List[tuple[str, int]] = []
    for match in _DECL_RE.finditer(source):
        name = match.group(1)
        # Line number of the match (1-indexed).
        line = source.count("\n", 0, match.start()) + 1
        decls.append((name, line))
    return decls


def _is_returned(source: str, name: str) -> bool:
    """Does the composable's return object list ``name``?

    Scans the content of the first ``return { ... }`` block for the
    bare name or a ``name:`` alias key. Handles both one-line
    (``return { foo, bar }``) and multi-line return objects.
    """
    open_pos = source.find("return {")
    if open_pos < 0:
        return False
    # Extract the return-object contents by matching braces from
    # ``return {`` onward. Good enough for composables (single top-level
    # return); doesn't need to handle nested generics precisely.
    depth = 0
    start = source.find("{", open_pos)
    if start < 0:
        return False
    end = start
    for i in range(start, len(source)):
        ch = source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    body = source[start + 1 : end]
    # Match `name` as a bare token or `name:` (alias key).
    # Also exclude `.name` / `name.xxx` false positives by requiring
    # start-of-word AND terminator.
    pattern = rf"(?<![.\w]){re.escape(name)}\s*(?:[,:}}\n]|$)"
    return re.search(pattern, body) is not None


def _is_used_in_file(source: str, name: str) -> bool:
    """Is the ref referenced anywhere in the file beyond its declaration?

    A ref can be populated externally (v-model, template bindings on the
    consumer side, assignment from another composable's effect) — those
    writes don't show up as ``NAME.value = ...`` inside the composable
    file. The narrower signal for a TRUE orphan (#5340 pattern) is:
    the ref name never appears outside its own declaration line.

    If it appears anywhere else — even as a read, a watcher source, a
    computed() dep, or a return statement — treat it as live.
    """
    # Count all bare-word occurrences of NAME.
    # Exclude the declaration match itself by counting and requiring >1.
    matches = re.findall(rf"\b{re.escape(name)}\b", source)
    # Declaration itself contributes ≥1. The return statement contributes
    # another. If that's all, the ref is orphaned — no reads, no writes,
    # no uses. If ≥3, it's live.
    return len(matches) >= 3


def _is_written_cross_file(search_root: Path, composable_path: Path, name: str) -> bool:
    """Is the ref's ``.value`` written from any OTHER file in the tree?

    Handles two legitimate patterns that look like orphans from a single
    file's perspective:

    1. Dependency injection: ``useComposableA({ exportingReport })`` and
       composable B writes ``deps.exportingReport.value = ...`` (cross-file).
    2. External template write: ``<input @input=\"foo.silenceThreshold.value = x\">``
       inside a .vue consumer.

    A cross-file grep for ``.NAME.value\\s*=`` is enough to catch both.
    We exclude the composable's own file to avoid counting declaration-
    local writes we'd already have caught via ``_is_used_in_file``.
    """
    pattern = rf"\.{re.escape(name)}\.value\s*="
    compiled = re.compile(pattern)
    for path in search_root.rglob("*"):
        if path == composable_path:
            continue
        if path.suffix not in {".ts", ".vue"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if compiled.search(text):
            return True
    return False


def _scan_file(path: Path, search_root: Path) -> List[OrphanRef]:
    """Return every orphan ref declared in ``path``.

    Orphan = declared + returned + never referenced outside the
    declaration and return, AND never written via dependency injection
    or external template assignment. Matches the #5340 bug shape.
    """
    source = path.read_text(encoding="utf-8")
    orphans: List[OrphanRef] = []
    for name, line in _find_decls(source):
        if not _is_returned(source, name):
            # Not in the return object — either a fully-internal state
            # ref (fine) or dead code. Out of scope for this check.
            continue
        if _is_used_in_file(source, name):
            continue
        if _is_written_cross_file(search_root, path, name):
            # DI or external .vue write — legitimate.
            continue
        orphans.append(OrphanRef(file=path, name=name, line=line))
    return orphans


def main(argv: List[str]) -> int:
    if len(argv) > 2:
        print(f"Usage: {argv[0]} [root_dir]", file=sys.stderr)
        return 2
    root = Path(argv[1]) if len(argv) == 2 else Path.cwd()
    composables_dir = root / "autobot-frontend" / "src" / "composables"
    if not composables_dir.is_dir():
        print(
            f"error: composables directory not found: {composables_dir}",
            file=sys.stderr,
        )
        return 2

    src_root = root / "autobot-frontend" / "src"
    orphans: List[OrphanRef] = []
    for ts_file in composables_dir.rglob("*.ts"):
        # Skip test files and type-only files.
        if ts_file.name.endswith(".test.ts") or ts_file.name.endswith(".spec.ts"):
            continue
        orphans.extend(_scan_file(ts_file, src_root))

    if not orphans:
        return 0

    # Sort for deterministic output.
    orphans.sort(key=lambda o: (str(o.file), o.line))
    print(
        f"Found {len(orphans)} orphan ref(s) — declared + returned + never written:",
        file=sys.stderr,
    )
    for o in orphans:
        rel = o.file.relative_to(root) if o.file.is_relative_to(root) else o.file
        print(f"  {rel}:{o.line}  {o.name}", file=sys.stderr)
    print(
        "\nThis pattern is the cause of bugs like #5277 and #5340 — "
        "a panel consumes the ref but the ref is never populated, so "
        "data silently fails to render. Delete the orphan ref, or wire "
        "a populator.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
