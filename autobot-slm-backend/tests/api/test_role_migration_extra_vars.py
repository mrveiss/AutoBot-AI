# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""run_role_full_procedure must pass role_name, not deploy_role (#11782, #12083).

ansible/playbooks/deploy_role.yml hard-fails ("role_name parameter is
required") when role_name is undefined and derives deploy_role from it, so
the endpoint must supply role_name for any Migrate/Redeploy to run.

Loads api/roles.py directly via importlib with fine-grained stubs (mirrors
tests/api/test_apply_secrets.py) — the shared conftest stubs config/models/
services for the whole session, so we swap throwaway stand-ins and restore.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_BACKEND_ROOT = Path(__file__).resolve().parents[2]

_STUB_MODULE_NAMES = [
    "sqlalchemy",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
    "models",
    "models.database",
    "services",
    "services.auth",
    "services.database",
    "services.role_registry",
    "services.playbook_executor",
]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _load_roles_module():
    import fastapi  # noqa: F401
    import pydantic  # noqa: F401
    import typing_extensions  # noqa: F401

    saved = {name: sys.modules.get(name) for name in _STUB_MODULE_NAMES}
    try:
        for name in _STUB_MODULE_NAMES:
            sys.modules[name] = MagicMock()
        spec = importlib.util.spec_from_file_location("_roles_migration_test", _BACKEND_ROOT / "api" / "roles.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


_roles_mod = _load_roles_module()


def test_migration_passes_role_name_not_deploy_role():
    role = MagicMock()
    role.name = "tts-worker"
    role.ansible_playbook = "playbooks/deploy_role.yml"

    fake_exec = MagicMock()
    fake_exec.execute_playbook = AsyncMock(return_value={"success": True, "output": "ok", "returncode": 0})

    # run_role_full_procedure does a local `from services.playbook_executor import
    # PlaybookExecutor`, so install a stub module exposing it for the call.
    stub_pe = MagicMock()
    stub_pe.PlaybookExecutor = MagicMock(return_value=fake_exec)
    with patch.dict(sys.modules, {"services.playbook_executor": stub_pe}):
        _run(_roles_mod.run_role_full_procedure(role, "00-SLM-Manager"))

    kwargs = fake_exec.execute_playbook.call_args.kwargs
    assert kwargs["extra_vars"] == {"role_name": "tts-worker"}
    assert "deploy_role" not in kwargs["extra_vars"]
    assert kwargs["limit"] == ["00-SLM-Manager"]


def test_run_role_full_procedure_never_raises_on_generic_exception():
    """#12096 review: execute_playbook() runs pre-flight steps BEFORE its own
    try/except (_update_code_source, fetch_deploy_secrets), so infra failures
    there previously escaped the narrower `except FileNotFoundError`. Any
    exception must now surface as success=False, error="execution_error"
    instead of propagating — run_role_full_procedure's "never raises" contract
    must hold for BOTH callers (this endpoint and update-all's per-role loop).
    """
    role = MagicMock()
    role.name = "backend"
    role.ansible_playbook = "playbooks/deploy_role.yml"

    fake_exec = MagicMock()
    fake_exec.execute_playbook = AsyncMock(side_effect=RuntimeError("git fetch failed"))

    stub_pe = MagicMock()
    stub_pe.PlaybookExecutor = MagicMock(return_value=fake_exec)
    with patch.dict(sys.modules, {"services.playbook_executor": stub_pe}):
        result = _run(_roles_mod.run_role_full_procedure(role, "00-SLM-Manager"))

    assert result["success"] is False
    assert result["error"] == "execution_error"
    assert result["role"] == "backend"


def test_migrate_role_endpoint_maps_execution_error_to_handled_500():
    """The interactive Migrate endpoint turns a never-raised execution_error
    into a handled HTTPException(500) — never an unhandled trace (#12096 review).
    """
    import fastapi

    role = MagicMock()
    role.name = "backend"
    role.ansible_playbook = "playbooks/deploy_role.yml"

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = role
    db = MagicMock()
    db.execute = AsyncMock(return_value=scalar_result)

    migrate_req = MagicMock()
    migrate_req.target_node_id = "00-SLM-Manager"

    async def fake_full_procedure(role_arg, node_id):
        return {"success": False, "role": role_arg.name, "error": "execution_error"}

    raised = None
    with patch.object(_roles_mod, "run_role_full_procedure", side_effect=fake_full_procedure):
        try:
            _run(_roles_mod.migrate_role("backend", migrate_req, db, {}))
        except fastapi.HTTPException as exc:
            raised = exc

    assert raised is not None
    assert raised.status_code == 500
