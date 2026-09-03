# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15522 — ``asyncio.create_task`` calls whose result is thrown away.

The event loop holds only a WEAK reference to a task, so a call whose return
value is discarded can be garbage-collected before the coroutine runs. Observed
live on the SLM self-update path: one firing executed end to end, an identical
firing minutes later produced no executor call, no inventory file, no transient
unit and no log write — and the surface reported success either way, because
nothing awaits these tasks or attaches a done callback.

``autobot_shared.async_compat.fire_and_forget`` is the fix: it retains the task
until completion and logs a failure that would otherwise vanish. This file
ratchets the population that has NOT been converted yet. The census is exact
and may only SHRINK — a new discarded ``create_task`` fails here, and every
conversion must lower the census in the same commit. #15522 converted the three
``_ansible_self_update`` firings in ``api/code_sync.py``; #15524 tracks the rest.
"""

from __future__ import annotations

import ast
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOT = "autobot-slm-backend/"

# Floors. Evaluated BEFORE the substantive assertion so a sweep that collapsed
# to nothing fails by name instead of passing vacuously green.
MIN_FILES_SCANNED = 200
MIN_CREATE_TASK_SITES = 30

# #15524 converted the remaining twelve discarded sites: eight to
# ``fire_and_forget`` and four (performance_dashboard.py's broadcaster,
# blue_green.py's rollback, deployment.py's two launch sites) to a hard
# reference held by the owning object. Nothing discarded remains, so the
# shrink assertion below is now vacuous and only the growth guard bites.
KNOWN_DISCARDED_CREATE_TASK: dict[str, int] = {}


def _tracked_python_files() -> tuple[str, ...]:
    out = subprocess.run(  # nosec B603  # fixed argv, no shell
        ["git", "ls-files", f"{SCAN_ROOT}*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    )
    return tuple(line for line in out.stdout.splitlines() if line)


def _is_create_task(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "create_task"


def _census() -> tuple[dict[str, int], int, int]:
    """Return (discarded-per-file, total create_task sites, files parsed)."""
    discarded: dict[str, int] = {}
    total = parsed = 0
    for rel in _tracked_python_files():
        if "/tests/" in rel or rel.endswith("_test.py"):
            continue
        try:
            tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        parsed += 1
        for node in ast.walk(tree):
            if _is_create_task(node):
                total += 1
            if isinstance(node, ast.Expr) and _is_create_task(node.value):
                discarded[rel] = discarded.get(rel, 0) + 1
    return discarded, total, parsed


def test_the_sweep_reaches_the_population_it_claims():
    """Floor first: a collapsed sweep must fail by name, never pass green."""
    _, total, parsed = _census()
    assert parsed >= MIN_FILES_SCANNED, f"FIX THE SWEEP: only {parsed} files parsed under {SCAN_ROOT}"
    assert total >= MIN_CREATE_TASK_SITES, f"FIX THE SWEEP: only {total} create_task sites reached"


def test_the_census_is_pinned_and_may_only_shrink():
    discarded, total, parsed = _census()
    assert parsed >= MIN_FILES_SCANNED, f"FIX THE SWEEP: only {parsed} files parsed under {SCAN_ROOT}"
    assert total >= MIN_CREATE_TASK_SITES, f"FIX THE SWEEP: only {total} create_task sites reached"

    pinned = {rel: n for rel, n in KNOWN_DISCARDED_CREATE_TASK.items() if n}
    grown = {rel: n for rel, n in discarded.items() if n > KNOWN_DISCARDED_CREATE_TASK.get(rel, 0)}
    assert grown == {}, (
        "discarded asyncio.create_task calls added or regrown (file: count): "
        f"{grown}. Use autobot_shared.async_compat.fire_and_forget — a discarded "
        "task can be garbage-collected before it runs (#15522)."
    )
    shrunk = {rel: n for rel, n in pinned.items() if discarded.get(rel, 0) < n}
    assert shrunk == {}, f"census not lowered after converting (file: old count): {shrunk}"


def test_the_self_update_firings_are_retained():
    """The three #15522 sites, asserted by name so a revert cannot go quiet."""
    src = (REPO_ROOT / "autobot-slm-backend/api/code_sync.py").read_text(encoding="utf-8")
    assert src.count("_ansible_self_update(") >= 5, "FIX THE SWEEP: the self-update firings moved or vanished"
    assert "asyncio.create_task(_ansible_self_update(" not in src
    assert src.count("fire_and_forget(_ansible_self_update(") == 3
