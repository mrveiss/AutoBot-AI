# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""_run_post_sync_steps dispatches to venv_reconcile correctly (#15063).

Separate module from test_drift_resolve.py / test_code_sync_deploy_bugs.py —
both are ratchet-grandfathered at their current line count and may not grow
(#14236); this stays a normal, uncapped file instead of pushing either over.

Same import shims as test_worker_component_resolve_12450.py: stub the
conflicting multipart package and swap benign dicts in for MagicMock schema
names so api.code_sync imports under the conftest stub regime.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

if "multipart" in sys.modules and not hasattr(sys.modules["multipart"], "multipart"):
    sys.modules.pop("multipart", None)
_mp_stub = types.ModuleType("multipart")
_mp_stub.multipart = types.ModuleType("multipart.multipart")  # type: ignore[attr-defined]
sys.modules.setdefault("multipart", _mp_stub)
sys.modules.setdefault("multipart.multipart", _mp_stub.multipart)  # type: ignore[attr-defined]

_code_sync_src = (_BACKEND_ROOT / "api" / "code_sync.py").read_text(encoding="utf-8")
_SCHEMA_NAMES = tuple(
    sorted(
        alias.name
        for node in ast.walk(ast.parse(_code_sync_src))
        if isinstance(node, ast.ImportFrom) and node.module == "models.schemas"
        for alias in node.names
    )
)
_schemas_stub = sys.modules.get("models.schemas")
if isinstance(_schemas_stub, MagicMock):
    for _name in _SCHEMA_NAMES:
        setattr(_schemas_stub, _name, dict)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_backend_reconciles_with_component_pip_paths() -> None:
    """A pip backend reconciles AFTER a successful install, with the SAME
    (req_path, pip_bin) pair `_COMPONENT_PIP_PATHS` names for it — never a
    second, independently-hardcoded path (#15063)."""
    import api.code_sync as cs

    reconcile_mock = AsyncMock()
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=True)))
        stack.enter_context(patch("api.code_sync._snapshot_component", AsyncMock(return_value=None)))
        stack.enter_context(patch("api.code_sync._deploy_constraints_dir", AsyncMock()))
        stack.enter_context(patch("api.code_sync._deploy_repo_root_requirements", AsyncMock()))
        stack.enter_context(patch("api.code_sync._ensure_target_python_installed", AsyncMock()))
        stack.enter_context(patch("api.code_sync._ensure_venv_python", AsyncMock(return_value=False)))
        stack.enter_context(patch("api.code_sync._install_pip_deps_for_component", AsyncMock(return_value=True)))
        stack.enter_context(patch("api.code_sync.reconcile_component", reconcile_mock))
        stack.enter_context(patch("api.code_sync._run_alembic_migrations", AsyncMock(return_value=True)))
        stack.enter_context(patch("api.code_sync._ensure_autobot_shared_symlink", AsyncMock()))
        stack.enter_context(patch("api.code_sync._restart_component_services", AsyncMock()))
        stack.enter_context(patch("api.code_sync._wait_component_healthy", AsyncMock(return_value=True)))
        _, steps, pip_ok = _run(
            cs._run_post_sync_steps(
                "autobot-backend",
                "/opt/autobot/code_source/autobot-backend",
                "/opt/autobot/autobot-backend",
            )
        )

    assert pip_ok is True
    reconcile_mock.assert_awaited_once()
    called_component, called_req, called_pip, called_steps = reconcile_mock.call_args.args
    assert called_component == "autobot-backend"
    assert (called_req, called_pip) == cs._COMPONENT_PIP_PATHS["autobot-backend"]
    assert called_steps is steps


def test_worker_explicit_list_component_refuses_reconciliation() -> None:
    """npu-worker has no requirements file — reconciliation must refuse and
    report, never silently pass through as "nothing to do" (#15063 AC4)."""
    import api.code_sync as cs

    reconcile_mock = AsyncMock()
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)))
        stack.enter_context(patch("api.code_sync._snapshot_component", AsyncMock(return_value=None)))
        stack.enter_context(patch("api.code_sync._install_pip_deps_for_component", AsyncMock(return_value=True)))
        stack.enter_context(patch("api.code_sync.reconcile_component", reconcile_mock))
        stack.enter_context(patch("api.code_sync._restart_component_services", AsyncMock()))
        stack.enter_context(patch("api.code_sync._wait_component_healthy", AsyncMock(return_value=True)))
        stack.enter_context(patch("api.code_sync._rollback_component", AsyncMock()))
        _, steps, pip_ok = _run(
            cs._run_post_sync_steps(
                "autobot-npu-worker",
                "/opt/autobot/code_source/autobot-npu-worker",
                "/opt/autobot/autobot-npu-worker",
            )
        )

    assert pip_ok is True
    reconcile_mock.assert_not_awaited()
    assert any("autobot-npu-worker" in s and "refused" in s for s in steps)


def test_ai_stack_reconciles_with_its_own_requirements_ai_paths() -> None:
    """ai-stack is the one worker with a real requirements file — it must
    reconcile against `_WORKER_COMPONENT_PIP`'s (requirements-ai.txt,
    venv/bin/pip) pair, not the backend `_COMPONENT_PIP_PATHS` map
    (#15063, #12450)."""
    import api.code_sync as cs

    reconcile_mock = AsyncMock()
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)))
        stack.enter_context(patch("api.code_sync._snapshot_component", AsyncMock(return_value=None)))
        stack.enter_context(patch("api.code_sync._install_pip_deps_for_component", AsyncMock(return_value=True)))
        stack.enter_context(patch("api.code_sync.reconcile_component", reconcile_mock))
        stack.enter_context(patch("api.code_sync._restart_component_services", AsyncMock()))
        stack.enter_context(patch("api.code_sync._wait_component_healthy", AsyncMock(return_value=True)))
        stack.enter_context(patch("api.code_sync._rollback_component", AsyncMock()))
        _, steps, pip_ok = _run(
            cs._run_post_sync_steps(
                "autobot-ai-stack",
                "/opt/autobot/code_source/autobot-ai-stack",
                "/opt/autobot/autobot-ai-stack",
            )
        )

    assert pip_ok is True
    reconcile_mock.assert_awaited_once()
    called_component, called_req, called_pip, _steps = reconcile_mock.call_args.args
    assert called_component == "autobot-ai-stack"
    assert (called_req, called_pip) == cs._WORKER_COMPONENT_PIP["autobot-ai-stack"]


def test_backend_pip_failure_never_calls_reconcile() -> None:
    """A failed install must short-circuit before reconciliation ever runs —
    removal candidates from a possibly-unfinished ADD are not safe to act on
    (#15063)."""
    import api.code_sync as cs

    reconcile_mock = AsyncMock()
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=True)))
        stack.enter_context(patch("api.code_sync._snapshot_component", AsyncMock(return_value=None)))
        stack.enter_context(patch("api.code_sync._deploy_constraints_dir", AsyncMock()))
        stack.enter_context(patch("api.code_sync._deploy_repo_root_requirements", AsyncMock()))
        stack.enter_context(patch("api.code_sync._ensure_target_python_installed", AsyncMock()))
        stack.enter_context(patch("api.code_sync._ensure_venv_python", AsyncMock(return_value=False)))
        stack.enter_context(patch("api.code_sync._install_pip_deps_for_component", AsyncMock(return_value=False)))
        stack.enter_context(patch("api.code_sync.reconcile_component", reconcile_mock))
        stack.enter_context(patch("api.code_sync._rollback_component", AsyncMock()))
        _, _steps, pip_ok = _run(
            cs._run_post_sync_steps(
                "autobot-backend",
                "/opt/autobot/code_source/autobot-backend",
                "/opt/autobot/autobot-backend",
            )
        )

    assert pip_ok is False
    reconcile_mock.assert_not_awaited()


def test_worker_pip_failure_never_calls_reconcile() -> None:
    """Same guard on the worker branch (ai-stack's requirements-ai.txt install
    failing must not be followed by a reconcile against its own venv)."""
    import api.code_sync as cs

    reconcile_mock = AsyncMock()
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)))
        stack.enter_context(patch("api.code_sync._snapshot_component", AsyncMock(return_value=None)))
        stack.enter_context(patch("api.code_sync._install_pip_deps_for_component", AsyncMock(return_value=False)))
        stack.enter_context(patch("api.code_sync.reconcile_component", reconcile_mock))
        stack.enter_context(patch("api.code_sync._rollback_component", AsyncMock()))
        _, _steps, pip_ok = _run(
            cs._run_post_sync_steps(
                "autobot-ai-stack",
                "/opt/autobot/code_source/autobot-ai-stack",
                "/opt/autobot/autobot-ai-stack",
            )
        )

    assert pip_ok is False
    reconcile_mock.assert_not_awaited()
