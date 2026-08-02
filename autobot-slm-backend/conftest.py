# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

import ast
import importlib
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
# Warning modules the xdist controller must still be able to import (#13312)
# ---------------------------------------------------------------------------
# pytest-xdist rebuilds every worker warning in the CONTROLLER process by
# importing the warning class's module
# (xdist.workermanage.unserialize_warning_message).  The controller loads this
# conftest too, so the stubs above make ``sqlalchemy`` a non-package there and
# ``import sqlalchemy.exc`` — home of SAWarning — raises ModuleNotFoundError.
# xdist has no guard for that: the node goes down and the whole session ends in
# an INTERNALERROR, losing every result.
#
# Whether it fires is pure scheduling luck (``--dist loadscope`` hands scopes to
# whichever worker is free), which is why it stayed latent until the code-sync
# tests stopped spending ~780s on dead health-poll wait and changed the
# distribution.  Keep the REAL warning module in sys.modules so the import
# resolves, while the stub still shadows the package for the tests.
#
# This is a whitelist of exactly one: any other warning module under a stubbed
# package — ``sqlalchemy.orm.exc`` is the obvious next one — still raises the
# identical ModuleNotFoundError in the controller.  Add it here when a worker
# starts emitting from it rather than rediscovering the INTERNALERROR.
_REAL_WARNING_MODULES = ("sqlalchemy.exc",)


def _import_real_module(name: str):
    """Import *name* for real, leaving the surrounding stub tree untouched."""
    root = name.split(".")[0]
    saved = {m: mod for m, mod in sys.modules.items() if m == root or m.startswith(f"{root}.")}
    for stale in saved:
        del sys.modules[stale]
    try:
        return importlib.import_module(name)
    except Exception:
        # Deliberately broad: this runs at conftest import, so anything escaping
        # here (a C-extension load failure, a version guard, an env assertion)
        # takes the entire session down — strictly worse than skipping the
        # preload and leaving the original xdist crash possible.
        return None
    finally:
        for m in [m for m in sys.modules if m == root or m.startswith(f"{root}.")]:
            del sys.modules[m]
        sys.modules.update(saved)


def _preserve_real_warning_modules() -> None:
    """Re-register the real warning modules on top of the stubbed parents."""
    for name in _REAL_WARNING_MODULES:
        real = _import_real_module(name)
        if real is None:
            continue
        sys.modules[name] = real
        # Bind onto the stub parent too: ``from sqlalchemy.exc import X`` reads
        # sys.modules while ``patch("sqlalchemy.exc.X")`` resolves via
        # getattr(sys.modules["sqlalchemy"], "exc").  Without this the two see
        # different objects — the divergence _stub()'s own docstring (#9780)
        # exists to prevent.
        parent, _, child = name.rpartition(".")
        if parent in sys.modules:
            setattr(sys.modules[parent], child, real)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _stub(name: str) -> MagicMock:
    """Return (or create) a MagicMock stub for *name* in sys.modules.

    Also binds the stub onto its parent package stub as an attribute so the two
    ways of reaching a submodule converge on the SAME object (#9780):

    - ``from services.encryption import encrypt_data`` reads
      ``sys.modules["services.encryption"]``.
    - ``unittest.mock.patch("services.encryption.encrypt_data")`` resolves the
      target via ``getattr(sys.modules["services"], "encryption")``.

    Without the parent binding the latter auto-creates a *different* child mock,
    so ``patch("services.encryption.x")`` silently patches an object the code
    under test never reads (a false-green / confusing-failure trap). Use
    ``patch.object(sys.modules["services.encryption"], ...)`` if you must target
    a stubbed submodule on an older conftest.
    """
    if name not in sys.modules:
        # unsafe=True: module stubs must expose arbitrary names, including
        # ones starting with `assert` (e.g. services.fleet_sync_guard.
        # assert_no_running_sync) which safe mocks block as typo-protection
        # and turn into collection-time ImportError (#10023).
        mod = MagicMock(unsafe=True)
        mod.__name__ = name
        mod.__package__ = name.split(".")[0]
        mod.__spec__ = None
        sys.modules[name] = mod
    mod = sys.modules[name]
    parent_name, _, child = name.rpartition(".")
    if parent_name and parent_name in sys.modules:
        setattr(sys.modules[parent_name], child, mod)
    return mod  # type: ignore[return-value]


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

_preserve_real_warning_modules()

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
# The services.* modules api/code_sync.py and api/setup_wizard.py import are
# AST-derived from their sources (#11575, #11794) — a hand-maintained list rots
# the moment either module gains a new `from services.X import ...` (exactly
# how #11481 broke, and the same anti-pattern behind the #11461 schema-list
# rot).  Pattern mirrors the schema-name derivation in
# tests/api/test_collect_outdated_node_ids.py.  Both files are stubbed because
# their test modules (tests/api/*, api/setup_wizard_sanitize_test.py,
# tests/api/test_setup_wizard_node_roles.py) import them at collection time.
_CODE_SYNC_SERVICE_MODULES: frozenset = frozenset()
for _src in ("code_sync.py", "setup_wizard.py"):
    _src_ast = ast.parse((Path(__file__).parent / "api" / _src).read_text(encoding="utf-8"))
    _CODE_SYNC_SERVICE_MODULES |= {
        _node.module
        for _node in ast.walk(_src_ast)
        if isinstance(_node, ast.ImportFrom) and _node.module and _node.module.startswith("services.")
    } | {
        _alias.name
        for _node in ast.walk(_src_ast)
        if isinstance(_node, ast.Import)
        for _alias in _node.names
        if _alias.name.startswith("services.")
    }
del _src_ast

# services.* modules NOT imported by code_sync.py but stubbed for other api/*
# modules under test.  These have their own consumers and are not exposed to
# the code_sync rot source above.
_EXTRA_SERVICE_MODULES = (
    "services.blue_green",
    "services.code_status",
    "services.deployment",
    "services.encryption",
    "services.reconciler",
    "services.replication",
    "services.role_registry",
    "services.service_categorizer",
    "services.service_orchestrator",
    "services.tls_credentials",
    "services.vnc_credentials",
)

# Parent package first so each child stub binds onto it (see _stub docstring).
for _m in ("services", *sorted(_CODE_SYNC_SERVICE_MODULES | set(_EXTRA_SERVICE_MODULES))):
    _stub(_m)

# ── services.ssh_utils — REAL module, not a stub (#11793) ─────────────────────
# api/code_sync.py imports it, so the AST-derived loop above just stubbed it —
# but its ``_ssh_key_usable()`` gate must stay real under test: a MagicMock is
# truthy, which would silently re-add ``-i <key>`` at every migrated ssh build
# site.  The module is dependency-light (os/logging/pathlib only), so real-load
# it via its file spec (the ``services`` parent is a MagicMock, not a package,
# so a normal import cannot traverse it) and re-bind it onto the parent stub
# so ``patch("services.ssh_utils.X")`` resolves to the same object.
import importlib.util as _importlib_util  # noqa: E402

_ssh_utils_spec = _importlib_util.spec_from_file_location(
    "services.ssh_utils", Path(__file__).parent / "services" / "ssh_utils.py"
)
_ssh_utils_mod = _importlib_util.module_from_spec(_ssh_utils_spec)
sys.modules["services.ssh_utils"] = _ssh_utils_mod
_ssh_utils_spec.loader.exec_module(_ssh_utils_mod)
setattr(sys.modules["services"], "ssh_utils", _ssh_utils_mod)

# ── python-multipart ─────────────────────────────────────────────────────────
# FastAPI's ensure_multipart_is_installed() is called when any route uses
# UploadFile or Form parameters.  It checks for python_multipart.__version__
# at route-registration time (import time for the router module).  Stub it
# so that code_source_test.py can import code_source.py without the package
# being installed in the dev environment.  Issue: #3525
_pm_mod = types.ModuleType("python_multipart")
_pm_mod.__version__ = "9.9.99"  # type: ignore[attr-defined]  # high sentinel — immune to future FastAPI threshold bumps
# Legacy `multipart` shim re-exports `from python_multipart import __all__` (#10023).
_pm_mod.__all__ = []  # type: ignore[attr-defined]
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
    # user_management/services/__init__.py is executed for real when pytest
    # imports test modules inside that package (user_management/services/
    # sso_e2e_test.py, sso_secrets_test.py); its from-imports must resolve via
    # sys.modules or the whole package fails to collect (#11794).
    "user_management.services.organization_service",
    "user_management.services.team_service",
    "user_management.services.user_service",
]:
    _stub(_m)
