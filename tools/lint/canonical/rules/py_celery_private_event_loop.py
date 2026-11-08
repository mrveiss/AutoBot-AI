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
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from autobot_shared.testfile_names import is_test_filename
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


def alias_table(tree: ast.AST) -> dict[str, str]:
    """Map each locally bound import name to the dotted path it stands for."""
    table: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                table[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for a in node.names:
                table[a.asname or a.name] = f"{node.module}.{a.name}"
    return table


def resolve(node: ast.AST, table: dict[str, str]) -> str | None:
    """Dotted name of ``node`` with its leading import alias expanded."""
    dotted = _dotted(node)
    if dotted is None:
        return None
    head, _, rest = dotted.partition(".")
    full = table.get(head, head)
    return f"{full}.{rest}" if rest else full


def task_functions(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Every function decorated as a Celery task."""
    found: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            name = _dotted(dec.func if isinstance(dec, ast.Call) else dec) or ""
            if name.endswith(_TASK_DECORATORS):
                found.append(node)
                break
    return found


def is_task_module(tree: ast.AST) -> bool:
    """True when the module defines a function decorated as a Celery task."""
    return bool(task_functions(tree))


def in_scope(rel: str, tree: ast.AST) -> bool:
    if is_test_filename(rel, include_js=False) or "/tests/" in rel:
        return False
    return rel.startswith(SCOPE_DIRS) or is_task_module(tree)


def private_loop_calls(tree: ast.AST) -> list[tuple[ast.Call, str]]:
    """Every call that creates or drives a private loop, with its canonical name."""
    table = alias_table(tree)
    found: list[tuple[ast.Call, str]] = []
    for node in ast.walk(tree):
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
