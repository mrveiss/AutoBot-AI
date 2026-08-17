# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for api/nl_database.py's secret-resolution path (#14127).

`_resolve_db_url` imported ``get_secrets_manager`` from ``api.secrets`` -- a
name that has never existed there (``api.secrets`` exposes the
``SecretsManager`` *singleton*, ``secrets_manager``). Every call raised
``ImportError`` and every ImportError was caught by the function's own broad
``except Exception`` and turned into a generic 500 -- indistinguishable from
any other failure, and nothing noticed because this file had no test at all.

These tests exercise ``_resolve_db_url`` through the real import (no
conftest/fixture stubs ``api.secrets`` or ``get_secrets_manager`` -- see
``test_module_imports_in_a_realistic_subprocess`` below and
``repo_tests/test_ci_import_smoke_paths_14252.py`` for the module-path guard),
monkeypatching only the data layer (``secrets_manager.get_secret``) so a
reintroduced-bad-import regresses these back to a 500/ImportError instead of
silently passing.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

from api.nl_database import _resolve_db_url

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_DIR = _REPO_ROOT / "autobot-backend"
_FAKE_DB_URL = "postgresql://localhost/nl_database_test_db"


def test_module_imports_in_a_realistic_subprocess():
    """api.nl_database must import cleanly with a fresh interpreter and no
    fixture pre-stubbing ``api.secrets`` -- the failure mode that hid #14127
    (the broken import lived inside a function body, so even the existing
    module-level `test_startup_imports.py::test_api_module_imports` sweep
    never triggered it; only calling `_resolve_db_url` does).
    """
    # `autobot_shared.*` imports resolve off the repo ROOT (the package is
    # `autobot_shared/__init__.py`, not a `src`-layout); `autobot-backend` is
    # needed for the module's own first-party imports (api.*, models.*, ...).
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(_BACKEND_DIR), str(_REPO_ROOT), env.get("PYTHONPATH", "")])

    result = subprocess.run(
        [sys.executable, "-c", "import api.nl_database"],
        capture_output=True,
        text=True,
        cwd=str(_BACKEND_DIR),
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_resolve_db_url_returns_none_when_no_secret_id():
    assert await _resolve_db_url(None, request=None) is None


@pytest.mark.asyncio
async def test_resolve_db_url_returns_value_for_a_database_url_secret(monkeypatch):
    def fake_get_secret(secret_id: str, chat_id: str | None = None):
        assert secret_id == "secret-123"
        assert chat_id is None
        return {"type": "database_url", "value": _FAKE_DB_URL}

    monkeypatch.setattr("api.secrets.secrets_manager.get_secret", fake_get_secret)

    result = await _resolve_db_url("secret-123", request=None)

    assert result == _FAKE_DB_URL


@pytest.mark.asyncio
async def test_resolve_db_url_404s_when_secret_missing(monkeypatch):
    monkeypatch.setattr("api.secrets.secrets_manager.get_secret", lambda *a, **kw: None)

    with pytest.raises(HTTPException) as exc_info:
        await _resolve_db_url("missing-secret", request=None)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_resolve_db_url_400s_for_wrong_secret_type(monkeypatch):
    monkeypatch.setattr(
        "api.secrets.secrets_manager.get_secret",
        lambda *a, **kw: {"type": "api_key", "value": "not-a-db-url"},
    )

    with pytest.raises(HTTPException) as exc_info:
        await _resolve_db_url("wrong-type-secret", request=None)

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_resolve_db_url_500s_when_the_data_layer_raises(monkeypatch):
    """The broad `except Exception` boundary still applies to *real* data-layer
    failures (e.g. a decrypt error) -- only the import itself was ever broken.
    """

    def boom(*_a, **_kw):
        raise RuntimeError("decrypt failure")

    monkeypatch.setattr("api.secrets.secrets_manager.get_secret", boom)

    with pytest.raises(HTTPException) as exc_info:
        await _resolve_db_url("any-secret", request=None)

    assert exc_info.value.status_code == 500
