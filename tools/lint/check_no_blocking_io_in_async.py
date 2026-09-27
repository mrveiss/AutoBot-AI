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
  - ``subprocess.run/call/check_call/check_output/Popen``, ``sqlite3.connect``,
    ``time.sleep``, ``os.system`` — matched on ``(module, attr)`` after the name is
    resolved through the file's own imports, in both forms. ``import subprocess as
    sp`` then ``sp.run(...)`` is caught, and so is ``from time import sleep`` then
    a bare ``sleep(1)``; an argument named ``time`` with a ``sleep`` method is not.
    The from-import half was missed when the module-qualified half was added, which
    is the same failure this hook exists to catch, one level up: the fix covered
    one spelling of the class it named (#17647 review). See ``_MODULE_BLOCKING_CALLS``
    for why the module qualifier is load-bearing. Residue, stated: a local name
    that shadows a module the file *also* imports is read as the module.

## What the second group is about, and where it is not enforced

The ``requests``/``Path`` patterns are flagged everywhere. The stdlib group is
flagged in **production modules only**: a ``sqlite3.connect`` in an async test
body blocks the loop that test owns and nothing else, so enforcing it there
would buy no production latency and would gate 18 existing test files. That is
a deliberate narrowing of the question, not an oversight, so it is *counted*:
a full-repo run prints how many stdlib hits were skipped in test files. A
silent exemption and a clean tree read identically, which is the failure
``MEASUREMENT_DISCIPLINE.md`` calls "did not look" wearing "nothing found".
Test files stay fully in scope for ``requests.*`` and ``Path.*``.

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
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan_helpers import PY_FLOOR, enforce_reach, scan_python_files  # noqa: E402

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


#: Blocking stdlib calls by (module, attr). Added because the codebase-analytics
#: index reported 8 high-severity `performance_blocking_io_in_async` findings that
#: this guard passed clean over: it knew `requests.*` and `Path.read/write_*` and
#: nothing else, so a `subprocess.run(..., timeout=5)` on the event loop was
#: invisible. One endpoint held three such calls for up to twelve seconds.
#:
#: Matched on (module, attr) rather than attr alone: a bare `run` or `connect` is
#: any object's method, and flagging those would make the guard a nuisance rather
#: than a gate.
_MODULE_BLOCKING_CALLS = {
    ("subprocess", "run"): "subprocess.*",
    ("subprocess", "call"): "subprocess.*",
    ("subprocess", "check_call"): "subprocess.*",
    ("subprocess", "check_output"): "subprocess.*",
    ("subprocess", "Popen"): "subprocess.*",
    ("sqlite3", "connect"): "sqlite3.connect",
    ("time", "sleep"): "time.sleep",
    ("os", "system"): "os.system",
}

_GUIDANCE = {
    "requests.*": (
        "  → Replace with `httpx.AsyncClient`. Share a single client instance per\n"
        "    service via `lazy_singleton` (see `autobot_shared.lazy_singleton`).\n"
        "    Or use the existing `aiohttp` clients where already present.\n"
        "    See #7444 migration follow-ups."
    ),
    "subprocess.*": (
        "  → Wrap the one-shot call: `await asyncio.to_thread(subprocess.run, argv, ...)`.\n"
        "    A `timeout=N` bounds the child, not the event loop — the loop is blocked\n"
        "    for the whole N. See #7444 migration follow-ups."
    ),
    "sqlite3.connect": (
        "  → `await asyncio.to_thread(...)` around the connect AND the queries, and do\n"
        "    not hold the connection across an `await`: a slow peer then holds both the\n"
        "    loop and a database handle."
    ),
    "time.sleep": ("  → `await asyncio.sleep(n)`. `time.sleep` blocks every other task."),
    "os.system": (
        "  → `await asyncio.create_subprocess_exec(...)`, or\n"
        "    `await asyncio.to_thread(subprocess.run, argv)` with a fixed argv."
    ),
    "Path.read/write_text/bytes": (
        "  → Replace with `aiofiles` for streaming, or wrap a one-shot call:\n"
        "      content = await asyncio.to_thread(path.read_text, encoding='utf-8')\n"
        "    See #7444 migration follow-ups."
    ),
}


#: Kinds whose harm is scoped to the loop the calling module runs on. A test
#: body owns its loop, so these are not enforced in test files -- see the
#: module docstring. `requests.*` and `Path.*` are deliberately absent: those
#: stay enforced everywhere, which is the status quo this widening preserves.
_LOOP_ONLY_KINDS: frozenset[str] = frozenset({"subprocess.*", "sqlite3.connect", "time.sleep", "os.system"})


def _is_test_path(rel_posix: str) -> bool:
    """Return True for the repo's three test-path spellings.

    Keyed on the whole class, not one spelling: a predicate matching only
    ``*_test.py`` would let ``tests/test_x.py`` through, and this guard has
    already been bitten once by a detector narrower than the class it named.
    """
    name = rel_posix.rsplit("/", 1)[-1]
    return name.endswith("_test.py") or name.startswith("test_") or "/tests/" in f"/{rel_posix}"


def in_scope(violations: List[_Violation], rel_posix: str) -> tuple[List[_Violation], int]:
    """Split *violations* into (enforced, count skipped as loop-only-in-a-test)."""
    if not _is_test_path(rel_posix):
        return violations, 0
    kept = [v for v in violations if v.kind not in _LOOP_ONLY_KINDS]
    return kept, len(violations) - len(kept)


def imported_modules(tree: ast.AST) -> dict[str, str]:
    """Map each local name bound by an ``import`` to the module it names.

    ``import subprocess`` -> ``{"subprocess": "subprocess"}``; ``import
    subprocess as sp`` -> ``{"sp": "subprocess"}``; ``import os.path`` binds
    ``os``, which is what an ``os.system(...)`` call goes through.

    Collected from the whole file rather than the module level only, because a
    function-local ``import subprocess`` is exactly where a blocking call tends
    to be written. `from x import y` is deliberately absent: every pattern here
    is reached through a module attribute, so a bare imported name is not one of
    them.
    """
    modules: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules[alias.asname or alias.name.split(".")[0]] = alias.name.split(".")[0]
    return modules


def imported_callables(tree: ast.AST) -> dict[str, tuple[str, str]]:
    """Map each local name bound by ``from <mod> import <attr>`` to its ``(mod, attr)``.

    ``from time import sleep`` -> ``{"sleep": ("time", "sleep")}``; ``from
    subprocess import run as child_run`` -> ``{"child_run": ("subprocess", "run")}``.

    Needed because those calls are ``ast.Name`` nodes, not ``ast.Attribute`` ones, so
    the module-qualified matcher cannot see them at all -- it returns early on any
    call whose ``func`` is not an attribute. Resolving through this map is what keeps
    the check narrow: only a name this file bound from a blocking module counts, so
    an unrelated local ``sleep()`` or ``run()`` is still ignored.
    """
    callables: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            for alias in node.names:
                callables[alias.asname or alias.name] = (root, alias.name)
    return callables


class _AsyncBlockingIOVisitor(ast.NodeVisitor):
    """Walks the AST and records banned calls inside ``async def`` bodies."""

    def __init__(
        self,
        path: Path,
        source_lines: List[str],
        modules: dict[str, str] | None = None,
        callables: dict[str, tuple[str, str]] | None = None,
    ) -> None:
        self.path = path
        self.source_lines = source_lines
        #: local name -> imported module, from this file's own `import` statements.
        self.modules = modules or {}
        #: local name -> (module, attr), from this file's own `from ... import`s.
        self.callables = callables or {}
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
        # Pattern 0: a bare name bound by `from <blocking module> import <attr>`.
        # Checked first because these calls are never `ast.Attribute`, so the
        # module-qualified patterns below cannot reach them.
        if isinstance(node.func, ast.Name):
            pair = self.callables.get(node.func.id)
            if pair:
                kind = _MODULE_BLOCKING_CALLS.get(pair)
                if kind is None and pair[0] == "requests" and pair[1] in _REQUESTS_FORBIDDEN_ATTRS:
                    kind = "requests.*"
                if kind:
                    self._record(node, kind)
            return
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
            return
        # Pattern 3: blocking stdlib calls, matched on (module, attr) (#7444 follow-up).
        # The receiver name is resolved through this file's imports first, so an
        # alias is caught and a same-named local is not mistaken for the module.
        if isinstance(node.func.value, ast.Name):
            module = self.modules.get(node.func.value.id)
            if module is None:
                return
            kind = _MODULE_BLOCKING_CALLS.get((module, attr))
            if kind:
                self._record(node, kind)

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
    visitor = _AsyncBlockingIOVisitor(path, source.splitlines(), imported_modules(tree), imported_callables(tree))
    visitor.visit(tree)
    return visitor.violations


def main(argv: List[str]) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    files, full_repo = scan_python_files(argv, repo_root)
    # Vacuity floor (#14896): full-repo mode only -- pre-commit legitimately
    # hands this hook an argv with no Python in it.
    if enforce_reach(len(files), PY_FLOOR, hook=HOOK_ID, full_repo=full_repo):
        return 1
    # Restrict to backend roots — frontend tooling sometimes ships .py snippets
    # in test fixtures that aren't part of the backend async surface.
    backend_roots = ("autobot-backend", "autobot_shared", "autobot-slm-backend")
    files = [f for f in files if any(part in backend_roots for part in f.relative_to(repo_root).parts[:1])]

    all_violations: List[_Violation] = []
    skipped_in_tests = 0
    for path in files:
        enforced, skipped = in_scope(check_file(path), path.relative_to(repo_root).as_posix())
        all_violations.extend(enforced)
        skipped_in_tests += skipped

    if full_repo and skipped_in_tests:
        # Stated, not silent: the narrowing has a number attached so a reader
        # can tell "no stdlib hits" from "stdlib hits, not enforced here".
        print(  # noqa: print -- CLI diagnostic output on stderr
            f"[{HOOK_ID}] {skipped_in_tests} stdlib blocking call(s) in test files "
            "are out of scope (they block only the loop their own test owns).",
            file=sys.stderr,
        )

    if not all_violations:
        return 0

    print(
        f"\n[{HOOK_ID}] Found {len(all_violations)} blocking-I/O call(s) inside `async def` " "bodies (#7444):\n",
        file=sys.stderr,
    )  # noqa: print -- CLI diagnostic output on stderr, same as every other tools/lint/ checker
    for v in all_violations:
        print(v.format(), file=sys.stderr)  # noqa: print
    print(
        f"\nIf the call genuinely runs in a thread (rare), append " f"`# {NOQA_TOKEN}` to that line.\n",
        file=sys.stderr,
    )  # noqa: print
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
