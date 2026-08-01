# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for the apply-secrets propagation path (#11719).

Covers:
- services.ansible_secrets._SECRET_TO_DEPENDENT_ROLES mapping (hf_token -> tts-worker)
- api.secrets._find_node_ids_for_roles: filters Node.roles JSON column in Python
- api.secrets.apply_secret: 422 when the key has no propagation mapping,
  404 when no node hosts a dependent role, success path runs the playbook
  limited to the matching node_ids
- api.secrets.get_dependent_roles_mapping: exposes the mapping to the frontend

Loads api/secrets.py directly via importlib with fine-grained stubs (mirrors
tests/api/test_fleet_health.py's pattern) instead of importing the package
normally: this dev host cannot read /etc/autobot/db-credentials.env, which
config.Settings() reads at import time via the real `api` package init.  Real
fastapi + pydantic are kept so FastAPI's response_model validation (run at
route-decoration time) sees genuine pydantic classes rather than MagicMocks —
models/schemas.py is real-loaded for the same reason.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from enum import Enum
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _run(coro):
    """Run an async route handler synchronously in tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


_STUB_MODULE_NAMES = [
    "sqlalchemy",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
    "models",
    "models.database",
    "models.schemas",
    "services",
    "services.auth",
    "services.database",
    "services.encryption",
    "services.ansible_secrets",
    "services.hf_token_validator",
    "services.system_secrets_vault",
    "services.playbook_executor",
    "autobot_shared",
    "autobot_shared.auth",
    "autobot_shared.auth.permissions",
]


class _NodeStatus(str, Enum):
    """Real-enough stand-in so models/schemas.py Literal/enum fields build (#11719)."""

    PENDING = "pending"
    ENROLLING = "enrolling"
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    ERROR = "error"
    MAINTENANCE = "maintenance"
    DECOMMISSIONED = "decommissioned"


class _Permission:
    SECURITY_MANAGE = "security:manage"


def _load_secrets_module():
    """Load api/secrets.py with real fastapi/pydantic + real models/schemas.py.

    autobot-slm-backend/conftest.py pre-stubs config/models/services module
    names as SHARED MagicMocks for the whole pytest session (dodging
    config.Settings() reading a permission-restricted /etc/autobot file at
    package-init time, #3499). Mutating those shared stubs' attributes here
    would leak into every other test file collected in the same session, so
    this swaps in throwaway per-load stand-ins and restores whatever was
    registered before on exit — see #11719.
    """
    import fastapi  # noqa: F401
    import pydantic  # noqa: F401
    import typing_extensions  # noqa: F401 — must stay real; fastapi's own compat layer uses it

    saved = {name: sys.modules.get(name) for name in _STUB_MODULE_NAMES}
    try:
        for name in _STUB_MODULE_NAMES:
            sys.modules[name] = MagicMock()

        sys.modules["autobot_shared.auth.permissions"].Permission = _Permission
        sys.modules["models.database"].Node = MagicMock()
        sys.modules["models.database"].SystemSecret = MagicMock()
        sys.modules["models.database"].NodeStatus = _NodeStatus
        sys.modules["services.ansible_secrets"]._SECRET_TO_DEPENDENT_ROLES = {"hf_token": ["tts-worker"]}

        # Real-load models/schemas.py so response_model=ApplySecretsResponse
        # (and SecretResponse etc.) validate against genuine pydantic
        # BaseModels — a MagicMock stand-in crashes FastAPI route decoration.
        schemas_spec = importlib.util.spec_from_file_location("models.schemas", _BACKEND_ROOT / "models" / "schemas.py")
        schemas_mod = importlib.util.module_from_spec(schemas_spec)
        schemas_mod.__package__ = "models"
        sys.modules["models.schemas"] = schemas_mod
        schemas_spec.loader.exec_module(schemas_mod)
        sys.modules["models"].schemas = schemas_mod

        spec = importlib.util.spec_from_file_location("_secrets_apply_test", _BACKEND_ROOT / "api" / "secrets.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


_secrets_mod = _load_secrets_module()

_FAKE_USER = {"username": "tester", "is_admin": True}


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    """Stand-in AsyncSession exposing only .execute(...).all() (#11719)."""

    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(self._rows)


class _FakeExecutor:
    """Stand-in PlaybookExecutor recording the call it received (#11719)."""

    calls: list = []
    result: dict = {"success": True, "output": "ok", "returncode": 0}

    async def execute_playbook(self, **kwargs):
        _FakeExecutor.calls.append(kwargs)
        return _FakeExecutor.result


@pytest.fixture(autouse=True)
def _reset_fake_executor():
    """Patch the *live* services.playbook_executor stub for one test, then restore it.

    _run_apply_secrets does `from services.playbook_executor import
    PlaybookExecutor` lazily at call time, so it resolves against whatever is
    in sys.modules at test-run time (the shared conftest.py stub) — not the
    throwaway stand-in used only while loading api/secrets.py (#11719).
    """
    pb_mod = sys.modules["services.playbook_executor"]
    original = getattr(pb_mod, "PlaybookExecutor", None)
    _FakeExecutor.calls = []
    _FakeExecutor.result = {"success": True, "output": "ok", "returncode": 0}
    pb_mod.PlaybookExecutor = _FakeExecutor
    yield
    if original is not None:
        pb_mod.PlaybookExecutor = original


# ---------------------------------------------------------------------------
# _SECRET_TO_DEPENDENT_ROLES mapping (services/ansible_secrets.py)
# ---------------------------------------------------------------------------


def test_secret_to_dependent_roles_maps_hf_token_to_tts_worker():
    spec = importlib.util.spec_from_file_location(
        "ansible_secrets_standalone", _BACKEND_ROOT / "services" / "ansible_secrets.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod._SECRET_TO_DEPENDENT_ROLES == {"hf_token": ["tts-worker"]}
    # autobot_internal_api_key is deliberately excluded (#11719 — no single
    # clean env-template+restart target across backend/nginx/agent).
    assert "autobot_internal_api_key" not in mod._SECRET_TO_DEPENDENT_ROLES


# ---------------------------------------------------------------------------
# _find_node_ids_for_roles
# ---------------------------------------------------------------------------


def test_find_node_ids_for_roles_matches_only_relevant_nodes():
    db = _FakeDB([("node-1", ["tts-worker", "redis"]), ("node-2", ["backend"])])
    result = _run(_secrets_mod._find_node_ids_for_roles(db, ["tts-worker"]))
    assert result == ["node-1"]


def test_find_node_ids_for_roles_no_matches():
    db = _FakeDB([("node-2", ["backend"])])
    result = _run(_secrets_mod._find_node_ids_for_roles(db, ["tts-worker"]))
    assert result == []


def test_find_node_ids_for_roles_handles_null_roles():
    """A node with roles=None (never assigned) must not crash the filter."""
    db = _FakeDB([("node-3", None)])
    result = _run(_secrets_mod._find_node_ids_for_roles(db, ["tts-worker"]))
    assert result == []


# ---------------------------------------------------------------------------
# GET /secrets/dependent-roles
# ---------------------------------------------------------------------------


def test_get_dependent_roles_mapping_returns_mapping():
    result = _run(_secrets_mod.get_dependent_roles_mapping(_FAKE_USER))
    assert result == {"mapping": {"hf_token": ["tts-worker"]}}


# ---------------------------------------------------------------------------
# POST /secrets/apply
# ---------------------------------------------------------------------------


def test_apply_secret_unknown_key_raises_422():
    payload = _secrets_mod.ApplySecretsRequest(key="not_a_real_secret")
    db = _FakeDB([])
    with pytest.raises(_secrets_mod.HTTPException) as exc_info:
        _run(_secrets_mod.apply_secret(payload, db, _FAKE_USER))
    assert exc_info.value.status_code == 422


def test_apply_secret_no_dependent_nodes_raises_404():
    payload = _secrets_mod.ApplySecretsRequest(key="hf_token")
    db = _FakeDB([("node-2", ["backend"])])  # no node runs tts-worker
    with pytest.raises(_secrets_mod.HTTPException) as exc_info:
        _run(_secrets_mod.apply_secret(payload, db, _FAKE_USER))
    assert exc_info.value.status_code == 404


def test_apply_secret_success_runs_playbook_limited_to_matching_nodes():
    payload = _secrets_mod.ApplySecretsRequest(key="hf_token")
    db = _FakeDB([("node-1", ["tts-worker"]), ("node-2", ["backend"])])

    result = _run(_secrets_mod.apply_secret(payload, db, _FAKE_USER))

    assert result.success is True
    assert result.key == "hf_token"
    assert result.dependent_roles == ["tts-worker"]
    assert result.target_node_ids == ["node-1"]
    assert len(_FakeExecutor.calls) == 1
    call = _FakeExecutor.calls[0]
    assert call["playbook_name"] == "apply-secrets.yml"
    assert call["limit"] == ["node-1"]
    assert call["extra_vars"] == {"apply_roles_csv": "tts-worker"}


def test_apply_secret_playbook_failure_propagates_success_false():
    _FakeExecutor.result = {"success": False, "output": "boom", "returncode": 1}
    payload = _secrets_mod.ApplySecretsRequest(key="hf_token")
    db = _FakeDB([("node-1", ["tts-worker"])])

    result = _run(_secrets_mod.apply_secret(payload, db, _FAKE_USER))

    assert result.success is False
    assert result.output == "boom"
    assert result.returncode == 1
