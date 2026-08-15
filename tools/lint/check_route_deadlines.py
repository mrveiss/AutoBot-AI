#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every covered route carries a deadline, or is declared unbounded WITH A REASON (#14015).

#13602: `/api/analytics/codebase/report` held the socket open past 180s and
logged nothing. Not a slow endpoint — a handler that never ran. Four of the five
analyses it fans out to wrapped themselves in `asyncio.wait_for`; the fifth did
not, and once the eight shared executor workers were busy that submission queued
and never started.

The defect is the PATTERN, not that one omission. When bounding is opt-in and
per-call-site, an unbounded path is invisible: it looks exactly like every other
handler until it hangs. `report.py` alone carried three different timeout
constants, so nothing about the file made the gap visible either.

Only a check that covers every member by construction catches an omission. This
is that check. A route in a covered module must either carry `@bounded(...)` or
appear in UNBOUNDED_BY_DESIGN with a stated reason — so an unbounded route is a
declaration a reviewer can see and argue with, never a default nobody chose.

Exit codes:
    0  every covered route is bounded or explicitly declared
    1  at least one route is silently unbounded, or a declaration is stale
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Coverage is deliberately narrow to start: the surface where #13602's hang
# actually lived. Widening it is adding a path here — and the moment one is
# added, every unbounded route under it fails this check until it is either
# bounded or declared. That is the intended way to grow coverage: the gap is
# enumerated, never silent.
COVERED_PACKAGES = ("autobot-backend/api/codebase_analytics/endpoints",)

_ROUTE_DECORATORS = {"get", "post", "put", "delete", "patch", "head", "options"}

# Routes deliberately left unbounded, each with the reason. A bare name is not
# accepted — the reason is the point, because "we chose this" and "nobody
# noticed" are otherwise indistinguishable, which is the whole subject of #13852.
UNBOUNDED_BY_DESIGN: dict[str, str] = {}


def _err(message: str) -> None:
    """Write to stderr without `print`.

    This file is a CLI checker whose whole output contract is text on a stream,
    but the repo bans newly-added builtin-print calls (#1082) and the escape is
    a per-line `# noqa: print`. Ten of those would be noise; one helper is not.
    """
    sys.stderr.write(message + "\n")


def _out(message: str) -> None:
    """Write to stdout without `print` — see :func:`_err`."""
    sys.stdout.write(message + "\n")


def _is_route(decorator: ast.expr) -> bool:
    """True for `@router.get(...)` and friends."""
    func = decorator.func if isinstance(decorator, ast.Call) else decorator
    return isinstance(func, ast.Attribute) and func.attr in _ROUTE_DECORATORS


def _is_bounded(decorator: ast.expr) -> bool:
    """True for `@bounded(...)` — call form only.

    A bare `@bounded` would be a decorator applied without a deadline, which is
    a different thing and not what this enforces.
    """
    return isinstance(decorator, ast.Call) and (
        (isinstance(decorator.func, ast.Name) and decorator.func.id == "bounded")
        or (isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "bounded")
    )


def _module_timeout_ceiling(tree: ast.Module) -> float:
    """Largest module-level ``*_TIMEOUT`` constant declared in this file.

    Heuristic on purpose. Proving which internal budget a given route can reach
    needs call-graph analysis; what is cheap and catches the real shape is
    noticing that a file declares a 240s budget somewhere and then bounds one of
    its own routes at 60s.

    That shape is not hypothetical — review of #14243 found it on three routes:
    /analysis (60s outer over a 180s internal), /env-analysis (60s over 240s),
    and /report (180s outer under its own 195s fan-out ceiling, so the generic
    message would have beaten the one that names the analysis).
    """
    ceiling = 0.0
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not (isinstance(target, ast.Name) and target.id.endswith("_TIMEOUT")):
                continue
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, (int, float)):
                ceiling = max(ceiling, float(node.value.value))
    return ceiling


def _module_constants(tree: ast.Module) -> dict[str, float]:
    """Module-level numeric constants, for resolving derived deadlines."""
    values: dict[str, float] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        if not isinstance(node.value.value, (int, float)) or isinstance(node.value.value, bool):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                values[target.id] = float(node.value.value)
    return values


def _resolve(node: ast.expr, constants: dict[str, float]) -> float | None:
    """Evaluate a deadline expression built from literals and known constants.

    Handles the shapes a deadline is actually written in — a literal, a named
    constant, and additive arithmetic over them. Anything else returns None and
    is left alone rather than guessed at.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        # An unresolvable name contributes ZERO, not None. ROUTE_DEADLINE_GRACE
        # is imported, so it is not a module constant here — returning None
        # would make every derived deadline unresolvable and silently skip the
        # very routes this check exists for. Zero under-estimates the deadline,
        # so the error is toward flagging, which is the safe direction: a false
        # flag is argued down in review, a missed one ships a 504.
        return constants.get(node.id, 0.0)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
        left, right = _resolve(node.left, constants), _resolve(node.right, constants)
        if left is None or right is None:
            return None
        return left + right if isinstance(node.op, ast.Add) else left - right
    return None


def _literal_deadline(decorator: ast.expr, constants: dict[str, float] | None = None) -> float | None:
    """The deadline in seconds, resolving named constants and additive arithmetic.

    An earlier version exempted every computed expression on the reasoning that
    deriving from a budget beats guessing past it. Review of #14243 showed that
    the exemption assumes the arithmetic is right: `@bounded(TIMEOUT - 170.0)`
    resolves to 10s under a 195s ceiling and passed the checker unchallenged.

    Deriving is still the right pattern — it is the ONLY thing that stays correct
    when the budget moves. But "derived" and "correct" are different claims, and
    a check that conflates them is the shape this whole issue is about.
    """
    if not (isinstance(decorator, ast.Call) and decorator.args):
        return None
    return _resolve(decorator.args[0], constants or {})


def _routes_in(path: Path) -> list[tuple[str, bool, float | None]]:
    """Every route handler in *path*, with whether it is bounded."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    constants = _module_constants(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not any(_is_route(d) for d in node.decorator_list):
            continue
        deadline = next((_literal_deadline(d, constants) for d in node.decorator_list if _is_bounded(d)), None)
        found.append((node.name, any(_is_bounded(d) for d in node.decorator_list), deadline))
    return found


def main() -> int:
    unbounded: list[str] = []
    too_tight: list[str] = []
    seen: set[str] = set()
    total = 0

    for package in COVERED_PACKAGES:
        root = _REPO_ROOT / package
        if not root.is_dir():
            _err(f"[route-deadlines] covered package missing: {package}")
            return 1
        for source in sorted(root.rglob("*.py")):
            if source.name.endswith("_test.py") or source.name.startswith("test_"):
                continue
            try:
                ceiling = _module_timeout_ceiling(ast.parse(source.read_text(encoding="utf-8")))
            except (OSError, SyntaxError):
                ceiling = 0.0
            for name, is_bounded, deadline in _routes_in(source):
                total += 1
                seen.add(name)
                if is_bounded and deadline is not None and ceiling and deadline < ceiling:
                    too_tight.append(
                        f"{source.relative_to(_REPO_ROOT)}::{name} "
                        f"bounded at {deadline:.0f}s under a {ceiling:.0f}s budget declared in the same file"
                    )
                if is_bounded or name in UNBOUNDED_BY_DESIGN:
                    continue
                unbounded.append(f"{source.relative_to(_REPO_ROOT)}::{name}")

    if total == 0:
        # An empty result reads as a clean result. If the matcher stops matching
        # — a rename, a refactor to a different router idiom — this check would
        # silently pass over everything.
        _err("[route-deadlines] found 0 routes in the covered packages — the matcher is broken")
        return 1

    stale = sorted(set(UNBOUNDED_BY_DESIGN) - seen)
    if stale:
        _err(
            "[route-deadlines] declared unbounded but no longer present "
            f"(remove from UNBOUNDED_BY_DESIGN): {', '.join(stale)}"
        )
        return 1

    if too_tight:
        _err(f"[route-deadlines] {len(too_tight)} route(s) bounded BELOW their own file's budget:")
        for route in too_tight:
            _err(f"  {route}")
        _err(
            "\nA route bound under a budget it can reach turns a slow success into a guaranteed "
            "504. Derive it instead: @bounded(THAT_TIMEOUT + ROUTE_DEADLINE_GRACE)."
        )
        return 1

    if unbounded:
        _err(f"[route-deadlines] {len(unbounded)} of {total} routes have no deadline:")
        for route in unbounded:
            _err(f"  {route}")
        _err(
            "\nAdd @bounded(seconds=...) from autobot_shared.error_boundaries, or add the "
            "handler to UNBOUNDED_BY_DESIGN with the reason it must not have one.\n"
            "#13602: an unbounded handler held the socket open past 180s and logged nothing."
        )
        return 1

    declared = len(UNBOUNDED_BY_DESIGN)
    _out(f"[route-deadlines] {total - declared} of {total} routes bounded, {declared} declared unbounded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
