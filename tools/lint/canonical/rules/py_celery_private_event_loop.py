# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""py-celery-private-event-loop — task modules must not create their own event loop.

Celery tasks reach process-wide singletons (the async engine, async Redis pools, a
cached aiosqlite connection) that are bound to the loop that first used them. A
private loop per task closes on return, so the next task reuses a pool whose
transports belong to a dead loop: ``RuntimeError('Event loop is closed')`` (#20887).
Task code drives its coroutine through ``autobot_shared.worker_loop.run_in_worker_loop``.

Scope is the union of (a) files under ``autobot-backend/{tasks,workers,llc/scheduler}/``
and (b) any file defining a Celery task (``@shared_task``, ``@celery_app.task``,
``@app.task``), so a task defined elsewhere is still covered.

``ALLOWLIST`` is the complete list of modules allowed a private loop (owner decision
2026-11-06). It is exactly three entries; do not add a fourth, migrate the caller. The
exemption covers non-task code only (a CLI ``main()``): a call inside a function decorated
as a Celery task is flagged even in an allowlisted module.

Known limit: execution order is not modelled. A ``global`` name bound by an import inside a
function resolves module-wide, but a module-level import of the same name wins, so a function
that rebinds it to a *different* target via ``global`` is not followed.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

from tools.lint.canonical.context import Context
from tools.lint.canonical.diagnostic import Diagnostic

RULE_ID = "py-celery-private-event-loop"
ISSUE = "#20887"
SEVERITY = "block"
TARGETS = ["autobot-backend", "autobot_shared"]
DESCRIPTION = "Private event loop in a Celery task module — use run_in_worker_loop"
FIX_HINT = (
    "Run the coroutine on the worker's persistent loop:\n"
    "    from autobot_shared.worker_loop import run_in_worker_loop\n"
    "    return run_in_worker_loop(_async_body())"
)

# Exactly three modules (repo-relative posix paths), each a private engine/loop on purpose.
ALLOWLIST: frozenset[str] = frozenset(
    {
        # CLI / updater entry point: runs as its own process, not inside a worker loop.
        "autobot-backend/services/pricing_refresh.py",
        # Hydrates the vault cache on a private engine in a thread, before any worker loop exists.
        "autobot-backend/services/provider_key_process_init.py",
        # Alembic baseline CLI: one-shot process.
        "autobot-backend/migrations/baseline.py",
    }
)

SCOPE_DIRS = ("autobot-backend/tasks/", "autobot-backend/workers/", "autobot-backend/llc/scheduler/")
BANNED_DOTTED = frozenset(
    {
        "asyncio.run",
        "asyncio.new_event_loop",
        "asyncio.get_event_loop",
        "asyncio.set_event_loop",
        "asyncio.Runner",
        "anyio.run",
        "asgiref.sync.async_to_sync",
        "autobot_shared.async_compat.run_or_schedule",
    }
)
BANNED_ATTR = "run_until_complete"
_TASK_DECORATORS = ("shared_task", "celery_app.task", "app.task")
_WAIVER = re.compile(r"#\s*canonical:\s*ignore\s+py-celery-private-event-loop\b")


def _rel(file_path: Path, ctx: Context) -> str:
    try:
        return file_path.resolve().relative_to(ctx.repo_root.resolve()).as_posix()
    except ValueError:
        return file_path.as_posix()


def _dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


_FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef)
_NEW_SCOPES = (*_FUNCS, ast.ClassDef, ast.Lambda)


def _bind(node: ast.AST, table: dict[str, str]) -> None:
    if isinstance(node, ast.Import):
        for a in node.names:
            table[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
    elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
        for a in node.names:
            table[a.asname or a.name] = f"{node.module}.{a.name}"


def _scan_scope(body: list[ast.stmt]) -> tuple[dict[str, str], set[str]]:
    """Import bindings made directly in one scope's body (nested scopes excluded), and the
    names that body declares ``global``/``nonlocal``."""
    table: dict[str, str] = {}
    outer: set[str] = set()
    stack: list[ast.AST] = list(reversed(body))
    while stack:
        node = stack.pop()
        _bind(node, table)
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            outer.update(node.names)
        if not isinstance(node, _NEW_SCOPES):
            stack.extend(reversed(list(ast.iter_child_nodes(node))))
    return table, outer


def _own_imports(body: list[ast.stmt]) -> dict[str, str]:
    """Import bindings that belong to one scope.

    A name declared ``global``/``nonlocal`` is bound in an outer scope, not here, so it is
    left to resolve through the enclosing table (``alias_table`` hoists a ``global`` name an
    import binds into the module table).
    """
    table, outer = _scan_scope(body)
    return {k: v for k, v in table.items() if k not in outer}


def _global_imports(tree: ast.AST) -> dict[str, str]:
    """Imports that bind a ``global``-declared name inside a function: module-level bindings.

    Order-insensitive on purpose: the rule does not model execution order, so the name
    resolves module-wide once any function imports it (a use before the import runs would be
    a NameError anyway).
    """
    found: dict[str, str] = {}
    for fn in ast.walk(tree):
        if isinstance(fn, _FUNCS):
            table, outer = _scan_scope(fn.body)
            found.update({k: v for k, v in table.items() if k in outer and _declared_global(fn, k)})
    return found


def _declared_global(fn: ast.AST, name: str) -> bool:
    """True when ``fn``'s own body declares ``name`` with ``global`` (not ``nonlocal``)."""
    stack: list[ast.AST] = list(getattr(fn, "body", []))
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Global) and name in node.names:
            return True
        if not isinstance(node, _NEW_SCOPES):
            stack.extend(ast.iter_child_nodes(node))
    return False


def alias_table(tree: ast.AST) -> dict[str, str]:
    """Map each name bound by an import at module scope (or ``global`` in a function) to its dotted path."""
    return {**_global_imports(tree), **_own_imports(getattr(tree, "body", []))}


def _param_names(a: ast.arguments) -> set[str]:
    names = [x.arg for x in (*a.posonlyargs, *a.args, *a.kwonlyargs)]
    names += [x.arg for x in (a.vararg, a.kwarg) if x is not None]
    return set(names)


def _children(node: ast.AST, seen: dict[str, str], inherited: dict[str, str]) -> list[tuple[ast.AST, dict, dict]]:
    """Children of ``node`` paired with (visible table, table nested functions inherit).

    ``seen`` is the table visible at ``node``; ``inherited`` is what a function defined here
    would close over (a class body's imports are visible to the class body only).
    """
    if isinstance(node, _FUNCS):
        outer = [*node.decorator_list, node.args, node.returns]
        params = _param_names(node.args)
        inner = {**{k: v for k, v in inherited.items() if k not in params}, **_own_imports(node.body)}
        return [(p, seen, inherited) for p in outer if p is not None] + [(s, inner, inner) for s in node.body]
    if isinstance(node, ast.ClassDef):
        head = [*node.decorator_list, *node.bases, *node.keywords]
        cls = {**inherited, **_own_imports(node.body)}
        return [(h, seen, inherited) for h in head] + [(s, cls, inherited) for s in node.body]
    if isinstance(node, ast.Lambda):
        shadow = _param_names(node.args)
        keep = {k: v for k, v in seen.items() if k not in shadow}
        kept = {k: v for k, v in inherited.items() if k not in shadow}
        return [(node.args, seen, inherited), (node.body, keep, kept)]
    return [(c, seen, inherited) for c in ast.iter_child_nodes(node)]


def scoped_nodes(node: ast.AST, table: dict[str, str]) -> Iterator[tuple[ast.AST, dict[str, str]]]:
    """Yield every node under ``node`` with the import table visible in its lexical scope (#21082).

    A function body sees the enclosing tables plus its own imports; a sibling function's
    imports never leak. A class body sees its own imports, which its methods do not
    inherit. Decorators and defaults are evaluated in the enclosing scope. Iterative, so a
    deeply nested expression cannot raise ``RecursionError`` in the lint run.
    """
    stack: list[tuple[ast.AST, dict[str, str], dict[str, str]]] = [(node, table, table)]
    while stack:
        cur, seen, inherited = stack.pop()
        yield cur, seen
        stack.extend(reversed(_children(cur, seen, inherited)))


def resolve(node: ast.AST, table: dict[str, str]) -> str | None:
    """Dotted name of ``node`` with its leading import alias expanded."""
    dotted = _dotted(node)
    if dotted is None:
        return None
    head, _, rest = dotted.partition(".")
    full = table.get(head, head)
    return f"{full}.{rest}" if rest else full


def _is_task_decorator(name: str) -> bool:
    """Match whole dotted components, so ``webapp.task`` is not mistaken for ``app.task``."""
    return any(name == d or name.endswith("." + d) for d in _TASK_DECORATORS)


def task_functions(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Every function decorated as a Celery task, decorator aliases resolved per scope."""
    found: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node, table in scoped_nodes(tree, alias_table(tree)):
        if not isinstance(node, _FUNCS):
            continue
        for dec in node.decorator_list:
            name = resolve(dec.func if isinstance(dec, ast.Call) else dec, table) or ""
            if _is_task_decorator(name):
                found.append(node)
                break
    return found


def is_task_module(tree: ast.AST) -> bool:
    """True when the module defines a function decorated as a Celery task."""
    return bool(task_functions(tree))


def in_scope(rel: str, tree: ast.AST) -> bool:
    if rel.endswith("_test.py") or "/tests/" in rel or Path(rel).name.startswith("test_"):
        return False
    return rel.startswith(SCOPE_DIRS) or is_task_module(tree)


def private_loop_calls(tree: ast.AST) -> list[tuple[ast.Call, str]]:
    """Every call that creates or drives a private loop, with its canonical name."""
    found: list[tuple[ast.Call, str]] = []
    for node, table in scoped_nodes(tree, alias_table(tree)):
        if not isinstance(node, ast.Call):
            continue
        name = resolve(node.func, table)
        if name in BANNED_DOTTED:
            found.append((node, name))
        elif isinstance(node.func, ast.Attribute) and node.func.attr == BANNED_ATTR:
            found.append((node, BANNED_ATTR))
    return found


def _task_lines(tree: ast.AST) -> set[int]:
    """Line numbers covered by Celery task bodies (the part an allowlisted module may not exempt)."""
    return {n for fn in task_functions(tree) for n in range(fn.lineno, (fn.end_lineno or fn.lineno) + 1)}


def check(file_path: Path, tree: ast.AST, ctx: Context) -> list[Diagnostic]:
    rel = _rel(file_path, ctx)
    if not in_scope(rel, tree):
        return []
    exempt_lines = None if rel not in ALLOWLIST else _task_lines(tree)
    if exempt_lines is not None and not exempt_lines:
        return []
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[Diagnostic] = []
    for node, name in private_loop_calls(tree):
        if exempt_lines is not None and node.lineno not in exempt_lines:
            continue
        idx = node.lineno - 1
        if 0 <= idx < len(lines) and _WAIVER.search(lines[idx]):
            continue
        out.append(
            Diagnostic(
                rule_id=RULE_ID,
                issue=ISSUE,
                severity=SEVERITY,
                file=file_path,
                line=node.lineno,
                col=node.col_offset,
                message=f"{name}() in a Celery task module — use run_in_worker_loop",
                snippet=(lines[idx].strip()[:120] if 0 <= idx < len(lines) else ""),
                fix_hint=FIX_HINT,
            )
        )
    return out
