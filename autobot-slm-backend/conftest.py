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

# #13139: models/schemas_secrets.py must be REAL, not stubbed. It carries
# response_model classes, and FastAPI rejects a MagicMock as a response field
# ("Invalid args for response field!") the moment a test builds the app. It
# imports only pydantic, so loading it by path is safe -- this deliberately
# bypasses models/__init__.py, which is what the stubs above exist to avoid.
_schemas_secrets_path = Path(__file__).parent / "models" / "schemas_secrets.py"
if not _schemas_secrets_path.is_file():
    raise RuntimeError("conftest: models/schemas_secrets.py is named here but does not exist")
import importlib.util as _ss_importlib_util  # noqa: E402  -- the shared alias is bound later

_ss_spec = _ss_importlib_util.spec_from_file_location("models.schemas_secrets", _schemas_secrets_path)
_ss_mod = _ss_importlib_util.module_from_spec(_ss_spec)
_ss_spec.loader.exec_module(_ss_mod)
sys.modules["models.schemas_secrets"] = _ss_mod
setattr(sys.modules["models"], "schemas_secrets", _ss_mod)

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
    "services.replication_jobs",
    "services.role_registry",
    "services.service_categorizer",
    "services.service_orchestrator",
    "services.service_restart",
    "services.tls_credentials",
    "services.vnc_credentials",
)

# Parent package first so each child stub binds onto it (see _stub docstring).
for _m in ("services", *sorted(_CODE_SYNC_SERVICE_MODULES | set(_EXTRA_SERVICE_MODULES))):
    _stub(_m)

# ── services.* modules that must be REAL, not stubs ──────────────────────────
# ``services`` itself is a MagicMock, not a package, so a normal import cannot
# traverse it — each of these is loaded from its file spec and re-bound onto
# the parent stub so ``patch("services.x.Y")`` resolves to the same object.
#
# Each entry earns its place by a failure that a MagicMock made invisible:
#
#   ssh_utils          #11793 — ``_ssh_key_usable()`` is a gate, and a MagicMock
#                      is truthy, so every migrated ssh build site silently
#                      re-added ``-i <key>``.
#   deploy_artifacts   #14231 — pure data, and a MagicMock iterates as EMPTY, so
#                      every ``for pattern in HOST_STATE_EXCLUDES`` loop ran zero
#                      times and the rsync chokepoint's protections vanished
#                      under test while looking perfectly healthy.
#   inventory_builder  #14307 — same emptiness, one layer up: a group set that
#                      iterates as empty is indistinguishable from the inventory
#                      bug being present. Its co-located test passed only when
#                      ``tests/services/conftest.py`` happened to be collected
#                      first in the same shard, which pytest-split decides.
#   a2a_card_fetcher   #14307 — co-located test, same shard-order dependency.
#   hf_token_validator #14307 — ditto.
#   service_extra_data #14307 — ditto; pure data, so the emptiness failure mode
#                      is deploy_artifacts' verbatim.
#   provision_progress #14856 — ``is_stale()`` is a guard, and a MagicMock is
#                      truthy: under a stub, every "running" provision state
#                      would look stale, silently turning "override an
#                      abandoned run" into "always override", which is
#                      exactly the regression the counterweight test exists
#                      to catch. Needs ``ansible_utils`` (also real-loaded,
#                      above) for ``_extract_failure_summary``.
#   journal_fetch      #15620 — ``fetch_service_journal()`` is awaited by
#                      ``api/services.py``, and a bare MagicMock is not
#                      awaitable. It also exports ``JournalFetchTimeout``,
#                      which that module names in an ``except`` clause — and
#                      ``except <MagicMock>`` raises TypeError rather than
#                      catching, so the stub would turn the very distinction
#                      this module exists to draw back into a crash.
#   process_divergence #15323 — ``compute_process_divergence()`` is awaited by
#                      ``api/code_sync.py``; a bare MagicMock is not
#                      awaitable, and this module's whole job is to never
#                      collapse "cannot tell" into "healthy" — a stub cannot
#                      exercise that guarantee.
#
# All of them are dependency-light (stdlib plus at most yaml/httpx/autobot_shared),
# which is the bar for being loadable here at all. Not a count: the list has
# outgrown "eight" twice already (#15462), and a stale number reads as a rule.
import importlib.util as _importlib_util  # noqa: E402

_REAL_SERVICE_MODULES = (
    "ssh_utils",
    "deploy_artifacts",
    "inventory_builder",
    "a2a_card_fetcher",
    "hf_token_validator",
    "service_extra_data",
    "ansible_utils",
    "provision_progress",
    "process_divergence",
    "journal_fetch",
    # #15462: has a co-located test that imports it, so it must be real-loaded
    # here or it resolves to a MagicMock depending on shard order
    # (tests/test_real_service_modules_14307.py enforces this).
    "frontend_bundle_health",
    # #15462: build/publish logic extracted out of api/code_sync.py (grandfathered
    # line-count ceiling, #14236) into this module; its own tests import it
    # directly and need the real coroutines, not MagicMocks.
    "slm_frontend_build",
)

# The placeholder a failed real-load falls back to (#15563). Loaded by path for
# the same reason the modules below are: `autobot-slm-backend` is deliberately
# NOT on pytest.ini's `pythonpath` (#13084 — `api`/`services`/`models` collide
# with autobot-backend), so there is no import that reaches it. Kept in its own
# file rather than inline here so the contract test can exercise the SAME object
# without re-executing this conftest's global stub installation.
_placeholder_path = Path(__file__).parent / "tests" / "realload_placeholder.py"
if not _placeholder_path.is_file():
    raise RuntimeError("conftest: tests/realload_placeholder.py is named here but does not exist")
_ph_spec = _importlib_util.spec_from_file_location("_realload_placeholder", _placeholder_path)
_ph_mod = _importlib_util.module_from_spec(_ph_spec)
_ph_spec.loader.exec_module(_ph_mod)
_unavailable_module = _ph_mod.unavailable_module

for _name in _REAL_SERVICE_MODULES:
    _path = Path(__file__).parent / "services" / f"{_name}.py"
    if not _path.is_file():
        raise RuntimeError(f"conftest: services/{_name}.py is named here but does not exist")
    _spec = _importlib_util.spec_from_file_location(f"services.{_name}", _path)
    _mod = _importlib_util.module_from_spec(_spec)
    sys.modules[f"services.{_name}"] = _mod
    try:
        _spec.loader.exec_module(_mod)
    except ImportError as _exc:
        # A third-party dependency this module needs is absent here (#14326).
        # Bind a placeholder that raises ImportError naming BOTH this module and
        # that dependency on any attribute access.
        #
        # Not a MagicMock (#14307): it is truthy and iterates empty, so a missing
        # dependency becomes a silently wrong result instead of an error.
        #
        # Not a deletion either (#15563). Deleting the name does NOT produce the
        # "plain ImportError naming it" this comment used to promise: `services`
        # is itself a MagicMock(unsafe=True) for most of the suite and fabricates
        # the attribute on demand, so `patch("services.x.y")` and
        # `getattr(services, "x")` hand back an auto-created mock — the #14307
        # trap again. Where the parent has been swapped for a real-path package
        # (tests/services/conftest.py) the deletion degrades instead into
        # "module 'services' has no attribute 'x'. Did you mean: 'x_test'?",
        # which names the stub package and points at the co-located test file
        # rather than at the missing dependency; two separate investigations read
        # that hint and filed the wrong cause.
        #
        # The placeholder keeps the original tolerance: only a test that actually
        # touches the module fails, and it fails naming the dependency, while
        # unrelated tests in the same directory still run. Eager real-loading
        # otherwise imposes every listed module's dependencies on every
        # environment that loads this conftest — the deliberately-minimal
        # migration gate hit exactly that, first with `yaml` (inventory_builder)
        # and then `aiohttp` (a2a_card_fetcher), taking down tests unrelated to
        # either.
        _mod = _unavailable_module(f"services.{_name}", _exc)
        sys.modules[f"services.{_name}"] = _mod
        print(f"conftest: services.{_name} not real-loaded ({_exc}) — bound as an unavailable-module placeholder")
    # Bound for BOTH paths: the placeholder has to be reachable through the
    # parent, or the MagicMock parent fabricates a child mock over it.
    setattr(sys.modules["services"], _name, _mod)

# ── python-multipart ─────────────────────────────────────────────────────────
# FastAPI's ensure_multipart_is_installed() is called when any route uses
# UploadFile or Form parameters.  It checks for python_multipart.__version__
# at route-registration time (import time for the router module).  Stub it
# so that code_source_test.py can import code_source.py without the package
# being installed in the dev environment.  Issue: #3525
#
# #15531: probe for the real package FIRST. This stub carries only
# ``__version__``/``__all__`` — it has no ``.multipart`` submodule — so
# inserting it where the real ``python_multipart`` IS installed shadows the
# working package for the whole session and breaks starlette's
# ``from python_multipart.multipart import parse_options_header``. ``setdefault``
# does not protect against that: nothing has imported the real package this
# early, so the key is absent and the crippled stub always won. Only the import
# probe can tell "absent" from "not yet imported".
try:
    import python_multipart as _real_python_multipart  # noqa: F401
except Exception:  # noqa: BLE001 — any import failure means "genuinely absent"
    _pm_mod = types.ModuleType("python_multipart")
    # High sentinel version, immune to future FastAPI threshold bumps.
    _pm_mod.__version__ = "9.9.99"  # type: ignore[attr-defined]
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
