# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the migration runner's CLI exit code (#14326).

Before this fix ``python3 -m migrations.runner`` exited 0 unconditionally --
``__main__`` printed a checkmark or a cross per migration and never called
``sys.exit`` on failure. The dedicated slm-migration-gate.yml workflow (real
Postgres, real runner invocation) was therefore green whether the runner
worked or not -- see #14326 for the live run where ``seed_agents`` failed
with ``No module named 'autobot_shared'`` and the job still passed.

Two layers, same reasoning as runner_deferral_test.py: importing
migrations.runner pulls in psycopg2, which is not part of the generic test
environment (autobot-slm-backend/requirements.txt is not installed by the
`python -m pytest autobot-slm-backend ...` job in ci.yml -- only the
dedicated slm-migration-gate.yml workflow installs it). The always-on
assertions below read the source with ``ast``; the behavioural assertions on
the extracted ``_exit_code_for`` helper are skipped, not failed, when
psycopg2 is genuinely absent (repo policy: optional test deps use
``pytest.importorskip``).
"""

from __future__ import annotations

import ast
import importlib.util
import sys as _sys
from pathlib import Path

import pytest

_RUNNER_PATH = Path(__file__).with_name("runner.py")


def _source() -> str:
    return _RUNNER_PATH.read_text(encoding="utf-8")


def _tree() -> ast.Module:
    return ast.parse(_source())


def _main_block() -> ast.If:
    return next(
        node
        for node in _tree().body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
    )


def _sys_exit_calls(node: ast.AST) -> list[ast.Call]:
    return [
        call
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "exit"
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "sys"
    ]


# ---------------------------------------------------------------------------
# Structural assertions -- no import, so these run regardless of whether
# psycopg2 is installed in this environment.
# ---------------------------------------------------------------------------


def test_main_block_calls_sys_exit():
    """The defect: __main__ fell off the end with an implicit 0, always."""
    exit_calls = _sys_exit_calls(_main_block())
    assert exit_calls, "__main__ never calls sys.exit -- a failed migration cannot fail the process"


def test_main_block_exit_argument_is_computed_not_a_constant():
    """`sys.exit(0)` unconditionally would satisfy the previous test while
    reproducing the exact defect. The argument must be derived from the run
    (a Call, e.g. ``_exit_code_for(results)``), not a hardcoded Constant.
    """
    exit_calls = _sys_exit_calls(_main_block())
    assert exit_calls, "__main__ never calls sys.exit"
    args_with_calls = [call for call in exit_calls if call.args and isinstance(call.args[0], ast.Call)]
    assert args_with_calls, "sys.exit() in __main__ must be driven by a computed value, not a hardcoded constant"


def test_exit_code_helper_returns_nonzero_on_any_failure_structurally():
    """`_exit_code_for` must inspect every element's success flag, not just
    the first or the last -- an ``any()``/``all()`` over the full sequence,
    not indexing.
    """
    tree = _tree()
    func = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_exit_code_for")
    calls = {node.func.id for node in ast.walk(func) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert "any" in calls, "_exit_code_for must scan every result, not special-case one entry"


def test_migrations_list_reaches_the_last_entry_after_seed_agents():
    """Regression for the reachability half of #14326.

    ``seed_agents`` sits mid-list; ``add_role_permission_audit_log_timestamps``
    is last. ``run_all_migrations`` breaks on the first failure, so if
    ``seed_agents`` cannot import (the ``autobot_shared`` gap) nothing after
    it, including the newest migration, was ever exercised by the gate.
    """
    migrations_assign = next(
        node
        for node in _tree().body
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "MIGRATIONS" for t in node.targets)
    )
    names = [elt.value for elt in migrations_assign.value.elts if isinstance(elt, ast.Constant)]

    assert "seed_agents" in names
    assert names[-1] == "add_role_permission_audit_log_timestamps"
    assert names.index("seed_agents") < names.index("add_role_permission_audit_log_timestamps")


# ---------------------------------------------------------------------------
# Behavioural assertions -- require importing the real module (psycopg2).
# ---------------------------------------------------------------------------

psycopg2 = pytest.importorskip("psycopg2")


def _load_runner():
    """Load runner.py standalone, matching runner_deferral_test.py's `_load`.

    `migrations.runner` does `from migrations import utils`, an absolute
    import resolved through sys.path (pytest's rootdir), independent of the
    throwaway name given to this module below.
    """
    spec = importlib.util.spec_from_file_location("_runner_14326", _RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    _sys.modules["_runner_14326"] = module
    try:
        spec.loader.exec_module(module)
    finally:
        _sys.modules.pop("_runner_14326", None)
    return module


@pytest.fixture
def runner():
    return _load_runner()


def test_exit_code_is_nonzero_when_any_migration_failed(runner):
    results = [("m1", True, "ok"), ("m2", False, "boom"), ("m3", True, "ok")]
    assert runner._exit_code_for(results) == 1


def test_exit_code_is_zero_when_every_migration_succeeded(runner):
    results = [("m1", True, "ok"), ("m2", True, "ok")]
    assert runner._exit_code_for(results) == 0


def test_exit_code_is_zero_for_no_pending_migrations(runner):
    assert runner._exit_code_for([]) == 0


def test_a_single_failure_among_many_successes_still_fails(runner):
    """The invariant, not just today's one reported case (#14326).

    27 successes and one failure anywhere in the list must still be
    non-zero -- proof the gate reacts to ANY migration breaking, not only
    the specific seed_agents/autobot_shared failure already fixed.
    """
    results = [(f"m{i}", True, "ok") for i in range(27)] + [("m28", False, "boom")]
    assert runner._exit_code_for(results) == 1
