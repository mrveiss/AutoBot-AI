#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pre-commit hook: block synchronous blocking I/O calls inside ``async def`` bodies.

#7444: 159 production blocking-I/O call sites were found across the backend:

  - 55× `requests.get/post/put/...` inside async functions (canonical: `httpx.AsyncClient`)
  - 78× `Path(...).read_text()` / `.write_text()` / `.read_bytes()` / `.write_bytes()`
    inside async functions (canonical: `aiofiles` or `await asyncio.to_thread(...)`)

These block the event loop — under concurrent load this causes timeouts, request
stalls, and intermittent latency spikes. Already-suspected source of production
backend latency (per the umbrella issue #5060).

This hook is a fail-fast gate: it walks ``async def`` bodies via AST and flags
any direct call to one of the banned patterns. It does NOT migrate the existing
violations — those are tracked in 3 cluster follow-up issues. Pre-commit only
runs on changed files, so the gate stops NEW violations from landing while the
backlog of existing violations is migrated separately.

## Banned patterns

  - ``requests.get(...)``, ``requests.post(...)``, etc. — anywhere inside an
    ``async def``. The HTTP client must be ``httpx.AsyncClient`` or the
    project's existing ``aiohttp`` shared client.
  - ``<expr>.read_text(...)`` / ``.write_text(...)`` / ``.read_bytes(...)`` /
    ``.write_bytes(...)`` — these are sync filesystem calls (typically on
    ``pathlib.Path`` instances). Inside an async path, use ``aiofiles`` for
    streaming or ``await asyncio.to_thread(p.read_text)`` for one-shot reads.

## Allowlist

A line containing ``# noqa: ASYNC_BLOCKING_IO`` (case-insensitive) on the
violating call's line is exempt. Use sparingly with a justification comment —
e.g. when the call truly runs in a thread already (rare).

## Scope

  - ``autobot-backend/**/*.py``
  - ``autobot_shared/**/*.py``
  - ``autobot-slm-backend/**/*.py``

Excludes: ``__pycache__``, ``.worktrees``, ``.venv``, ``node_modules``, etc.
(via ``_scan_helpers.iter_python_files``).

## Exit codes

  - 0 — clean
  - 1 — violations found (printed to stderr with file:line and replacement guidance)

## Background

  - Umbrella: #5060 (correctness primitives)
  - This hook: #7444
  - Migration follow-ups (existing violations): filed alongside the hook PR
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan_helpers import iter_python_files  # noqa: E402

HOOK_ID = "no-blocking-io-in-async"

# `requests` library functions that perform sync HTTP. ``request`` is the
# generic dispatcher; the others are convenience wrappers. All block the
# event loop when called inside an ``async def``.
_REQUESTS_FORBIDDEN_ATTRS: frozenset[str] = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "request"}
)

# Sync I/O methods commonly called on ``pathlib.Path`` instances. We can't
# always prove the receiver is a Path at static-analysis time without type
# info, so we flag the method name everywhere — false positives are rare and
# the noqa allowlist handles them.
_PATH_FORBIDDEN_METHODS: frozenset[str] = frozenset({"read_text", "write_text", "read_bytes", "write_bytes"})

NOQA_TOKEN = "noqa: async_blocking_io"


class _Violation:
    __slots__ = ("path", "line", "col", "kind", "snippet")

    def __init__(self, path: Path, line: int, col: int, kind: str, snippet: str) -> None:
        self.path = path
        self.line = line
        self.col = col
        self.kind = kind
        self.snippet = snippet

    def format(self) -> str:
        guidance = _GUIDANCE.get(self.kind, "")
        return f"{self.path}:{self.line}:{self.col}: {self.kind}: {self.snippet}\n{guidance}"


_GUIDANCE = {
    "requests.*": (
        "  → Replace with `httpx.AsyncClient`. Share a single client instance per\n"
        "    service via `lazy_singleton` (see `autobot_shared.lazy_singleton`).\n"
        "    Or use the existing `aiohttp` clients where already present.\n"
        "    See #7444 migration follow-ups."
    ),
    "Path.read/write_text/bytes": (
        "  → Replace with `aiofiles` for streaming, or wrap a one-shot call:\n"
        "      content = await asyncio.to_thread(path.read_text, encoding='utf-8')\n"
        "    See #7444 migration follow-ups."
    ),
}


class _AsyncBlockingIOVisitor(ast.NodeVisitor):
    """Walks the AST and records banned calls inside ``async def`` bodies."""

    def __init__(self, path: Path, source_lines: List[str]) -> None:
        self.path = path
        self.source_lines = source_lines
        self.violations: List[_Violation] = []
        # Tracks whether the current node is nested inside an `async def`.
        # We don't ban inside sync `def` (those run synchronously by design).
        self._async_depth = 0

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._async_depth += 1
        try:
            self.generic_visit(node)
        finally:
            self._async_depth -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Sync functions nested inside async ones are NOT in async context —
        # they run synchronously when called. Reset depth for the sync sub-tree.
        saved = self._async_depth
        self._async_depth = 0
        try:
            self.generic_visit(node)
        finally:
            self._async_depth = saved

    def visit_Call(self, node: ast.Call) -> None:
        if self._async_depth > 0:
            self._maybe_record(node)
        self.generic_visit(node)

    def _maybe_record(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Attribute):
            return
        attr = node.func.attr
        # Pattern 1: requests.{get,post,...}
        if (
            attr in _REQUESTS_FORBIDDEN_ATTRS
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "requests"
        ):
            self._record(node, "requests.*")
            return
        # Pattern 2: <anything>.read_text() / write_text() / read_bytes() / write_bytes()
        if attr in _PATH_FORBIDDEN_METHODS:
            self._record(node, "Path.read/write_text/bytes")

    def _record(self, node: ast.Call, kind: str) -> None:
        line_idx = node.lineno - 1
        if 0 <= line_idx < len(self.source_lines):
            line_text = self.source_lines[line_idx]
            if NOQA_TOKEN in line_text.lower():
                return  # Allowlisted with explicit acknowledgment.
            snippet = line_text.strip()
        else:
            snippet = "<source line not available>"
        self.violations.append(
            _Violation(
                path=self.path,
                line=node.lineno,
                col=node.col_offset,
                kind=kind,
                snippet=snippet,
            )
        )


def check_file(path: Path) -> List[_Violation]:
    """Return any blocking-I/O-in-async violations found in ``path``."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        # Don't fail the hook on unparseable files — flake8 will catch them.
        return []
    visitor = _AsyncBlockingIOVisitor(path, source.splitlines())
    visitor.visit(tree)
    return visitor.violations


def main(argv: List[str]) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    files = list(iter_python_files(argv, repo_root))
    # Restrict to backend roots — frontend tooling sometimes ships .py snippets
    # in test fixtures that aren't part of the backend async surface.
    backend_roots = ("autobot-backend", "autobot_shared", "autobot-slm-backend")
    files = [f for f in files if any(part in backend_roots for part in f.relative_to(repo_root).parts[:1])]

    all_violations: List[_Violation] = []
    for path in files:
        all_violations.extend(check_file(path))

    if not all_violations:
        return 0

    print(
        f"\n[{HOOK_ID}] Found {len(all_violations)} blocking-I/O call(s) inside `async def` " "bodies (#7444):\n",
        file=sys.stderr,
    )
    for v in all_violations:
        print(v.format(), file=sys.stderr)
    print(
        f"\nIf the call genuinely runs in a thread (rare), append " f"`# {NOQA_TOKEN}` to that line.\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
