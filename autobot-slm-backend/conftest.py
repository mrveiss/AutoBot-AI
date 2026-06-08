# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Root conftest for autobot-slm-backend tests.

Stubs heavy dependencies in sys.modules before pytest imports any api/*
submodule.  The core problem: importing api/__init__.py runs all router
registrations which trigger config.Settings() (reads /etc/autobot/db-credentials.env,
inaccessible in dev) and FastAPI response-model validation against MagicMock
Pydantic types (raised at decoration time, not runtime).

Strategy: pre-populate sys.modules['api'] with a hollow module whose __path__
points to the real api/ directory.  Python's import machinery finds the hollow
module in sys.modules, skips api/__init__.py entirely, and still locates
submodules (api/nodes_execution_test.py, api/code_source_test.py) by searching
__path__.  Each test file then manages its own fine-grained stubs.

The external-dependency stubs (config, models, services, etc.) are still
needed for modules that those test files import directly.

Issue: #3499
"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Hollow api package — prevents api/__init__.py from executing
# ---------------------------------------------------------------------------
_API_DIR = str(Path(__file__).parent / "api")

_api_mod = types.ModuleType("api")
_api_mod.__path__ = [_API_DIR]  # type: ignore[assignment]
_api_mod.__package__ = "api"
_api_mod.__spec__ = None  # type: ignore[assignment]
sys.modules.setdefault("api", _api_mod)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _stub(name: str) -> MagicMock:
    """Return (or create) a MagicMock stub for *name* in sys.modules."""
    if name not in sys.modules:
        mod = MagicMock()
        mod.__name__ = name
        mod.__package__ = name.split(".")[0]
        mod.__spec__ = None
        sys.modules[name] = mod
    return sys.modules[name]  # type: ignore[return-value]


# ── config ───────────────────────────────────────────────────────────────────
# Settings() reads /etc/autobot/db-credentials.env at instantiation.
_stub("config").settings = MagicMock()

# ── sqlalchemy ────────────────────────────────────────────────────────────────
for _m in [
    "sqlalchemy",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
    "sqlalchemy.orm",
]:
    _stub(_m)

# ── models ────────────────────────────────────────────────────────────────────
# Both the parent package and each submodule must be in sys.modules so that
# "from models.database import Foo" resolves without hitting the real package.
for _m in [
    "models",
    "models.database",
    "models.schemas",
]:
    _stub(_m)

# ── services ──────────────────────────────────────────────────────────────────
for _m in [
    "services",
    "services.auth",
    "services.database",
    "services.blue_green",
    "services.code_distributor",
    "services.deployment",
    "services.drift_checker",
    "services.encryption",
    "services.fleet_sync_guard",
    "services.git_tracker",
    "services.playbook_executor",
    "services.reconciler",
    "services.replication",
    "services.role_registry",
    "services.service_categorizer",
    "services.service_orchestrator",
    "services.sync_orchestrator",
    "services.tls_credentials",
    "services.vnc_credentials",
]:
    _stub(_m)

# ── python-multipart ─────────────────────────────────────────────────────────
# FastAPI's ensure_multipart_is_installed() is called when any route uses
# UploadFile or Form parameters.  It checks for python_multipart.__version__
# at route-registration time (import time for the router module).  Stub it
# so that code_source_test.py can import code_source.py without the package
# being installed in the dev environment.  Issue: #3525
_pm_mod = types.ModuleType("python_multipart")
_pm_mod.__version__ = "9.9.99"  # type: ignore[attr-defined]  # high sentinel — immune to future FastAPI threshold bumps
sys.modules.setdefault("python_multipart", _pm_mod)

# ── user_management ───────────────────────────────────────────────────────────
for _m in [
    "user_management",
    "user_management.database",
    "user_management.models",
    "user_management.models.api_key",
    "user_management.models.user",
    "user_management.schemas",
    "user_management.schemas.api_key",
    "user_management.schemas.mfa",
    "user_management.schemas.sso",
    "user_management.schemas.user",
    "user_management.services",
    "user_management.services.api_key_service",
    "user_management.services.base_service",
    "user_management.services.mfa_service",
    "user_management.services.sso_service",
]:
    _stub(_m)
