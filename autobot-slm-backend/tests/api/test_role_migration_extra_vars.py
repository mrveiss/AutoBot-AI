# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""_run_role_migration must pass role_name, not deploy_role (#11782).

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

    # _run_role_migration does a local `from services.playbook_executor import
    # PlaybookExecutor`, so install a stub module exposing it for the call.
    stub_pe = MagicMock()
    stub_pe.PlaybookExecutor = MagicMock(return_value=fake_exec)
    with patch.dict(sys.modules, {"services.playbook_executor": stub_pe}):
        _run(_roles_mod._run_role_migration(role, "00-SLM-Manager"))

    kwargs = fake_exec.execute_playbook.call_args.kwargs
    assert kwargs["extra_vars"] == {"role_name": "tts-worker"}
    assert "deploy_role" not in kwargs["extra_vars"]
    assert kwargs["limit"] == ["00-SLM-Manager"]
