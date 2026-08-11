# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
AutoBot User Backend - Test Configuration
Provides pytest fixtures for colocated tests.

Issue: #734 - Colocate tests with source files
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss
"""

import asyncio
import functools
import os
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from autobot_shared.ssot_config import config

# Ensure autobot-backend and autobot_shared are importable
project_root = Path(__file__).parent.parent
backend_root = Path(__file__).parent
shared_root = project_root / "autobot_shared"
sys.path.insert(0, str(project_root))
# Insert shared_root before backend_root so that backend_root ends up at
# position 0 (highest priority).  This ensures bare `models.*` imports in
# autobot-backend code resolve to autobot-backend/models/, not the similarly-
# named package in autobot_shared/.
sys.path.insert(0, str(shared_root))
sys.path.insert(0, str(backend_root))


def _make_pkg_stub(name: str) -> types.ModuleType:
    """Create a minimal package stub that Python's import machinery accepts.

    A bare MagicMock() cannot serve as a package because the importer
    requires ``__path__`` to be set for submodule resolution (e.g. when the
    code does ``from sqlalchemy.dialects.postgresql import ARRAY``).  We
    create a real ModuleType with ``__path__ = []`` so the dotted import chain
    succeeds while leaving every attribute access as a MagicMock via
    ``__getattr__``.
    """
    mod = types.ModuleType(name)
    mod.__path__ = []  # marks this as a package to the import system
    mod.__package__ = name
    mock_attr = MagicMock()

    def _getattr(attr: str) -> MagicMock:  # noqa: ANN001
        return mock_attr

    mod.__getattr__ = _getattr  # type: ignore[attr-defined]
    mod.pytest_plugins = []  # prevent MagicMock __getattr__ leaking into pytest plugin scan
    # Prevent _get_first_non_fixture_func from picking up MagicMock as setup/teardown hooks
    mod.setUpModule = None  # type: ignore[attr-defined]
    mod.setup_module = None  # type: ignore[attr-defined]
    mod.tearDownModule = None  # type: ignore[attr-defined]
    mod.teardown_module = None  # type: ignore[attr-defined]
    sys.modules[name] = mod
    return mod


def _real_load_and_bind(name: str, path: Path) -> None:
    """Real-load module *name* from *path*, overwriting any stub, and ALWAYS
    bind it as an attribute on its parent package module (#11661 — merged
    ``_load_real_mod`` + ``_real_load_service``).

    The parent bind is load-bearing (#11532/#11618): ``unittest.mock.patch``
    resolves ``"pkg.mod.NAME"`` via ``getattr(sys.modules["pkg"], "mod")``.
    When ``pkg`` is a MagicMock package stub, its catch-all ``__getattr__``
    returns a mock singleton, so without the setattr patch() silently patches
    the wrong object while the real module's globals stay untouched (inert
    patch).  Falls back to a package stub if the real file can't be loaded in
    this environment.
    """
    import importlib.util as _rlb_ilu

    # #12839: never re-execute a module that is ALREADY real-loaded from this
    # same file. Re-executing builds a second set of class objects and swaps
    # them into sys.modules, while every module that imported the first set
    # keeps referencing it — so `isinstance(x, Cls)` fails against an object
    # whose repr says it IS a Cls. That is what broke test_claim_classifier:
    # services.claim_classifier imported .knowledge_grounding_models at
    # collection, then _real_load_light_services re-executed the same file.
    # Re-execution is only needed to replace a *stub*, so an already-real module
    # is left alone and only the parent bind below is (re)applied.
    _existing = sys.modules.get(name)
    if _existing is not None and getattr(_existing, "__file__", None) == str(path):
        parent, _, child = name.rpartition(".")
        if parent and parent in sys.modules:
            setattr(sys.modules[parent], child, _existing)
        return

    spec = _rlb_ilu.spec_from_file_location(name, str(path))
    if not spec or not spec.loader:
        return
    mod = _rlb_ilu.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules[name] = _make_pkg_stub(name)
        return
    parent, _, child = name.rpartition(".")
    if parent and parent in sys.modules:
        setattr(sys.modules[parent], child, mod)


# Stub chromadb before it is imported. chromadb hangs at import time on
# machines without a local Chroma server (it fires gRPC keep-alive probes via
# opentelemetry), AND the version of opentelemetry-exporter-otlp-proto-grpc in
# this venv removed ReadableLogRecord causing an ImportError on older installs.
# Tests never hit a real Chroma cluster — every test that touches the knowledge
# stack either mocks at the fixture level or is in the agents/ integration suite
# that runs against a stub InMemoryClient.  A package-level stub is safe. (#MVA-1119)
for _chromadb_mod in [
    "chromadb",
    "chromadb.api",
    "chromadb.api.models",
    "chromadb.api.models.Collection",
    "chromadb.auth",
    "chromadb.auth.token_authn",
    "chromadb.config",
    "chromadb.telemetry",
    "chromadb.telemetry.opentelemetry",
]:
    if _chromadb_mod not in sys.modules:
        sys.modules[_chromadb_mod] = _make_pkg_stub(_chromadb_mod)

# Stub optional heavy dependencies that may not be installed in the dev venv.
# These are only needed at runtime on the target VM; tests use mocks.
# Simple (leaf) modules that don't need submodule resolution:
_SIMPLE_STUBS = [
    "prometheus_client",
    "xxhash",
    "torch",
    "torch.nn",
    "torch.cuda",
    "asyncpg",
    "psycopg2",
    "alembic",
]
for _mod in _SIMPLE_STUBS:
    if _mod not in sys.modules:
        try:
            import importlib

            importlib.import_module(_mod)
        except ImportError:
            sys.modules[_mod] = MagicMock()

# #13162: a machine without torch has no CUDA either, and the stub must say so.
# A bare MagicMock returns a truthy MagicMock from ``torch.cuda.is_available()``,
# which sends production code down the GPU branch — where it formats MagicMock
# device properties ("unsupported format string passed to MagicMock.__format__")
# and compares MagicMock device capability against an int. Attribute access on
# the parent stub auto-creates its own ``cuda`` child, so the ``torch.cuda``
# sys.modules entry must be that same object or the two disagree.
_torch_stub = sys.modules.get("torch")
if isinstance(_torch_stub, MagicMock):
    _torch_stub.cuda.is_available.return_value = False
    _torch_stub.cuda.device_count.return_value = 0
    _torch_stub.cuda.get_device_capability.return_value = (0, 0)
    sys.modules["torch.cuda"] = _torch_stub.cuda

# Celery stub — issue #4455. When celery isn't installed in the dev venv,
# provide a tiny shim so modules that do ``@celery_app.task`` import cleanly.
# The real package is used on production nodes; tests never rely on Beat.
try:
    import celery as _celery_real  # noqa: F401
except ImportError:
    _celery_stub = types.ModuleType("celery")

    class _StubCelery:
        def __init__(self, *args, **kwargs) -> None:
            self.conf = types.SimpleNamespace(
                update=lambda **_k: None,
                beat_schedule={},
            )

        def task(self, *_args, **_kwargs):
            def decorator(fn):
                fn.update_state = lambda *a, **k: None
                return fn

            return decorator

        def autodiscover_tasks(self, *_args, **_kwargs) -> None:
            return None

    _celery_stub.Celery = _StubCelery
    sys.modules["celery"] = _celery_stub

    _schedules_stub = types.ModuleType("celery.schedules")

    class _StubCrontab:
        def __init__(self, **fields) -> None:
            def _parse(v):
                try:
                    return {int(v)}
                except (TypeError, ValueError):
                    return set()

            self.minute = _parse(fields.get("minute", 0))
            self.hour = _parse(fields.get("hour", 0))

    _schedules_stub.crontab = _StubCrontab
    sys.modules["celery.schedules"] = _schedules_stub

# celery_app stub — issue #7766.  The production celery_app.py pulls in the
# full Redis / config dependency chain which causes a circular import in the
# test environment.  We inject a lightweight in-process Celery app so that
# ``from celery_app import celery_app`` in task modules succeeds and the
# ``@celery_app.task`` decorators register tasks on a real (but isolated) app.
#
# Strategy: use the real celery package if it is installed (it is in the dev
# venv — see the ``try`` block above); otherwise use the stub _StubCelery.
# Either way the resulting object must support .task() as a decorator and must
# maintain a .tasks dict so that test_task_registration.py can introspect it.
if "celery_app" not in sys.modules:
    _celery_app_mod = types.ModuleType("celery_app")
    try:
        import celery as _cel_pkg  # noqa: F401

        _test_app = _cel_pkg.Celery("test_autobot", broker="memory://", backend="cache+memory://")
        # GH#12522: ``store_eager_result`` is bound onto each task class at
        # *finalize* time (Task.from_config), and ``Task.bind`` only reads the
        # conf value while the attribute is still ``None``. Any test that
        # introspects ``celery_app.tasks`` (celery_beat_registration_test,
        # analytics_cache_population_test, batch_job_tasks_test) finalizes this
        # shared session app first, freezing ``store_eager_result=False`` before
        # an eager-result test's fixture can flip the runtime conf -- a later
        # ``AsyncResult`` then reads the stale PROGRESS meta and reports
        # "running". Setting it at creation binds every task with terminal-result
        # storage regardless of which test file finalizes the app first.
        _test_app.conf.task_store_eager_result = True
    except (ImportError, Exception):
        # Fall back to the stub Celery that is already in sys.modules["celery"]
        _StubCeleryClass = sys.modules["celery"].Celery
        _test_app = _StubCeleryClass("test_autobot")
    _celery_app_mod.celery_app = _test_app  # type: ignore[attr-defined]
    sys.modules["celery_app"] = _celery_app_mod

# services.llm_api_key_service and services.llm_cost_tracker stubs —
# services/__init__.py pulls in the full npu_client / Redis stack at import
# time. The tests mock these via patch() so a lightweight stub is safe.
for _svc_mod in [
    "services",
    "services.llm_api_key_service",
    "services.llm_cost_tracker",
    "services.llm_service",
    "services.tool_output_filter",
    "services.personality_service",
]:
    if _svc_mod not in sys.modules:
        _svc_stub = _make_pkg_stub(_svc_mod)
        # Prevent pytest from calling __getattr__("pytest_plugins") which would
        # return a MagicMock and cause a UsageError during test collection.
        _svc_stub.pytest_plugins = []  # type: ignore[attr-defined]
        sys.modules[_svc_mod] = _svc_stub

# ---------------------------------------------------------------------------
# autobot_shared.redis_client stand-in (#13446)
# ---------------------------------------------------------------------------
# Backend unit tests must never open a Redis socket. ``get_async_redis_client()``
# spends the client's full retry budget before giving up — 60s per call, 121s for
# the 56 Redis-agnostic tests in tests/services/test_claim_verifier.py.
#
# The stand-in used to be installed 400 lines below, and only ``if
# "autobot_shared.redis_client" not in sys.modules``, which made "does this unit
# test talk to a live Redis" a function of who imported first: collection order,
# and under ``-n auto --dist loadscope`` whichever files the worker was handed.
# This file also defeated its own guard — the real-load of
# services.tool_output_filter directly below reaches
# autobot_shared.logging_manager -> config.registry._get_redis(), which imports
# the genuine module, so the guard could never fire on this path.
#
# It is now installed unconditionally, and released again, for exactly the four
# windows that belong to this directory (the #13359 pattern): this file's own
# real-loads, pytest_configure's real-loads, the collection of each backend test
# module, and the run of each backend test. Outside them the genuine module is
# put back, because autobot_shared/'s own tests exercise it for real in the same
# CI invocation (#13084) and several of them install their own stub only ``if it
# is not already there`` — leaving the key empty flips those on.
_REDIS_CLIENT_KEY = "autobot_shared.redis_client"


def _import_real_redis_client() -> types.ModuleType | None:
    """Import the genuine module once, before the first window opens.

    Importing it opens no socket — that only happens when something *calls*
    ``get_redis_client()``, and every such call site this directory reaches runs
    inside a window, where the stand-in answers None. Having it loaded gives the
    stand-in something to delegate to, and gives each window the module the rest
    of the session expects to find rather than an empty key.
    """
    import importlib as _rc_il

    try:
        return _rc_il.import_module(_REDIS_CLIENT_KEY)
    except Exception:  # bare env without the redis package — stand-in only
        return None


def _make_redis_client_standin(real: types.ModuleType | None) -> types.ModuleType:
    """Build the socket-free ``autobot_shared.redis_client`` stand-in.

    Only the two connection factories are replaced. Everything else — the
    ``RedisConnectionManager`` class, the enums, the statistics dataclasses —
    delegates to *real*, because backend tests do use them: e.g.
    monitoring/redis_prometheus_metrics_test.py drives the genuine
    ``RedisConnectionManager`` with a mocked metrics manager, and a MagicMock in
    its place turns every assertion into a tautology.

    Built once and reused by every window so ``mock.patch`` targets keep their
    identity across them (#13359).
    """
    mod = types.ModuleType(_REDIS_CLIENT_KEY)

    async def _get_async_redis_client(*_a, **_k):
        # A coroutine returning None, so callers take their documented "Redis
        # unavailable" branch instead of awaiting a MagicMock (TypeError).
        return None

    def _get_redis_client(*_a, **_k):
        # A real callable returning None, NOT a MagicMock:
        # config.registry._fetch_from_redis() treats any truthy client as usable
        # and would hand that MagicMock straight back as a config *value*.
        return None

    def _delegate(attr: str):
        # Dunders are answered by the module object itself or not at all — a
        # MagicMock __path__ would make the import system treat this as a
        # package.
        if not attr.startswith("__") and real is not None:
            try:
                return getattr(real, attr)
            except AttributeError:
                pass
        if attr.startswith("__"):
            raise AttributeError(attr)
        return MagicMock()

    # Carry the genuine signature and docstring across, so introspection keeps
    # working: utils/redis_consolidation_test.py asserts get_redis_client's
    # parameter defaults and the "CANONICAL" line in its docstring.
    # ``update_wrapper`` also sets ``__wrapped__``, which is what makes
    # ``inspect.signature`` report the real one.
    for _name, _fn in (
        ("get_async_redis_client", _get_async_redis_client),
        ("get_redis_client", _get_redis_client),
    ):
        _genuine = getattr(real, _name, None) if real is not None else None
        setattr(mod, _name, _fn if _genuine is None else functools.update_wrapper(_fn, _genuine))
    mod.__getattr__ = _delegate  # type: ignore[attr-defined]
    return mod


class _ScopedRedisClient:
    """Own ``sys.modules["autobot_shared.redis_client"]`` for this directory only.

    Re-entrant: the snapshot is taken on the outermost enter and put back when
    the last holder leaves, so a nested window (pytest_configure inside the
    import window) cannot restore early. Every caller installs and removes from
    the same ``try/finally``.
    """

    def __init__(self) -> None:
        self._holders: set[str] = set()
        self._snapshot: tuple | None = None

    def enter(self, holder: str) -> None:
        """Install the stand-in if *holder* is the first to ask for it."""
        first = not self._holders
        self._holders.add(holder)
        if not first:
            return
        pkg = sys.modules.get("autobot_shared")
        self._snapshot = (
            _REDIS_CLIENT_KEY in sys.modules,
            sys.modules.get(_REDIS_CLIENT_KEY),
            pkg is not None and "redis_client" in pkg.__dict__,
            getattr(pkg, "redis_client", None),
        )
        self._bind(_REDIS_CLIENT_STANDIN)

    def exit(self, holder: str) -> None:
        """Put the previous module back once the last holder is done."""
        self._holders.discard(holder)
        if not self._holders:
            self._restore()

    def restore_all(self) -> None:
        """Unconditionally release the stand-in (session-teardown safety net)."""
        self._holders.clear()
        self._restore()

    def _restore(self) -> None:
        snapshot, self._snapshot = self._snapshot, None
        if snapshot is None:
            return
        had_mod, prior_mod, had_attr, prior_attr = snapshot
        if had_mod:
            sys.modules[_REDIS_CLIENT_KEY] = prior_mod
        else:
            sys.modules.pop(_REDIS_CLIENT_KEY, None)
        pkg = sys.modules.get("autobot_shared")
        if pkg is None:
            return
        if had_attr:
            pkg.redis_client = prior_attr  # type: ignore[attr-defined]
        else:
            pkg.__dict__.pop("redis_client", None)

    @staticmethod
    def _bind(mod: types.ModuleType) -> None:
        """Install *mod* and bind it on the parent package.

        The parent bind is load-bearing: ``patch("autobot_shared.redis_client.X")``
        resolves through ``getattr(autobot_shared, "redis_client")`` (#11661),
        which a bare ``sys.modules`` assignment never sets.
        """
        sys.modules[_REDIS_CLIENT_KEY] = mod
        pkg = sys.modules.get("autobot_shared")
        if pkg is not None:
            pkg.redis_client = mod  # type: ignore[attr-defined]


_REDIS_CLIENT_STANDIN = _make_redis_client_standin(_import_real_redis_client())
_SCOPED_REDIS = _ScopedRedisClient()

# Window 1 of 4 — every module-level real-load below binds whichever
# ``get_async_redis_client`` it finds into its own globals and keeps it for the
# rest of the session. Closed at the end of this file's module-level code.
_SCOPED_REDIS.enter("conftest-import")

# #11248: tool_output_filter is lightweight (stdlib + yaml + autobot_shared; Redis
# is only touched lazily inside methods, not at import), so its unit tests exercise
# the *real* pure helper (_strip_ansi). Load it real — overwriting the package stub
# above — so those tests don't get a MagicMock. Other tests that patch this module
# still work (patch targets a real module just as well).
_real_load_and_bind("services.tool_output_filter", backend_root / "services" / "tool_output_filter.py")

# npu_pipeline — stub the package and its sub-modules so that the __init__.py
# import chain (which pulls in Redis/config) doesn't break test collection.
# pytest_plugins must be explicitly set to [] so that pytest doesn't call
# __getattr__("pytest_plugins") on the stub which returns a MagicMock and
# triggers a UsageError. (MVA-1096/1097)
_NPU_PKG_DIR = backend_root / "services" / "npu_pipeline"
for _npu_mod in [
    "services.npu_pipeline",
    "services.npu_pipeline.shard_planner",
    "services.npu_pipeline.plan_cache",
    "services.npu_pipeline.invalidation",
    "services.npu_pipeline.dispatcher",
]:
    if _npu_mod not in sys.modules:
        _npu_stub = _make_pkg_stub(_npu_mod)
        _npu_stub.pytest_plugins = []  # type: ignore[attr-defined]
        if _npu_mod == "services.npu_pipeline":
            _npu_stub.__path__ = [str(_NPU_PKG_DIR)]
        sys.modules[_npu_mod] = _npu_stub
# Give the services stub the real __path__ so submodule imports (e.g.
# from services.audit_logger import ...) can find real files on disk.
# services/__init__.py is already bypassed (in sys.modules as a stub),
# so the npu_client / Redis chain it imports won't re-execute. (#MVA-1119)
if "services" in sys.modules:
    sys.modules["services"].__path__ = [str(backend_root / "services")]  # type: ignore[attr-defined]
# services.npu_profile_suggester (GH#6738) — pure-logic module with no heavy deps.
# Load from the real file so test_npu_profile_suggester.py can import it directly
# without being blocked by the services package stub above.  #11731: routed
# through _real_load_and_bind so the module is also bound on the services stub
# (patch("services.npu_profile_suggester.X") resolves via getattr(parent, child)).
if "services.npu_profile_suggester" not in sys.modules:
    _real_load_and_bind(
        "services.npu_profile_suggester",
        backend_root / "services" / "npu_profile_suggester.py",
    )
# services.npu_client (#12114 / demonstrated by #12407) — the embedding client is
# imported almost exclusively via lazy, function-level ``from services.npu_client
# import ...`` calls in production code, so it is essentially never bound on the
# ``services`` package stub at collection time.  Any test that is the first to do
# ``patch("services.npu_client.<name>")`` therefore silently patches the stub's
# catch-all MagicMock (an INERT patch) unless some earlier-collected module happened
# to import it — making test outcomes depend on collection ORDER (#12407 had to work
# around this with ``patch.object(npu_client_module, ...)``).  Real-load and bind it
# here — light deps only (stdlib + aiohttp + autobot_shared; prometheus_client is
# stubbed) — so the real module is always present and string-form patch() targets
# the real globals.  Mirrors the #11248 tool_output_filter / #11731 npu_profile_suggester
# pattern the module docstring recommends.
if "services.npu_client" not in sys.modules:
    _real_load_and_bind("services.npu_client", backend_root / "services" / "npu_client.py")
# Provide the SUPPORTED_LANGUAGES symbol consumed by api.schemas_agent
if not hasattr(sys.modules.get("services.personality_service", object()), "SUPPORTED_LANGUAGES"):
    sys.modules["services.personality_service"].SUPPORTED_LANGUAGES = {}  # type: ignore[attr-defined]
# Make the specific symbols resolvable
_svc_key_stub = sys.modules["services.llm_api_key_service"]
_svc_key_stub.LLMApiKeyRecord = MagicMock()  # type: ignore[attr-defined]
_svc_key_stub.get_llm_api_key_service = MagicMock()  # type: ignore[attr-defined]
_svc_cost_stub = sys.modules["services.llm_cost_tracker"]


# Provide a minimal cost-tracker stub whose calculate_cost() returns 0.0 so
# that the ``response_cost > 0`` guard in openai_compat.py works correctly in
# tests that don't patch get_cost_tracker themselves.
class _StubCostTracker:
    def calculate_cost(self, *_a, **_k) -> float:
        return 0.0


_svc_cost_stub.get_cost_tracker = lambda: _StubCostTracker()  # type: ignore[attr-defined]

# llm_shared stub — llm_shared/__init__.py re-exports the entire provider stack
# which pulls in Redis clients, config loaders, and optional heavy deps (torch,
# sentence-transformers) that are not installed in the dev venv.  Tests that
# exercise openai_compat patch get_provider_registry directly via
# ``patch("api.openai_compat.get_provider_registry", ...)``, so a lightweight
# top-level stub is safe.  llm_shared.models (LLMRequest / LLMResponse) is
# loaded separately because tests instantiate those classes directly.
if "llm_shared" not in sys.modules:
    _llm_stub = _make_pkg_stub("llm_shared")
    _llm_stub.get_provider_registry = MagicMock()  # type: ignore[attr-defined]
    _llm_stub.ProviderRegistry = MagicMock()  # type: ignore[attr-defined]
    _llm_stub.AdapterBase = MagicMock()  # type: ignore[attr-defined]
    _llm_stub.AdapterRegistry = MagicMock()  # type: ignore[attr-defined]
    _llm_stub.get_adapter_registry = MagicMock()  # type: ignore[attr-defined]
    _llm_stub.BaseProvider = MagicMock()  # type: ignore[attr-defined]
    _llm_stub.CachedResponse = MagicMock()  # type: ignore[attr-defined]
    _llm_stub.LLMResponseCache = MagicMock()  # type: ignore[attr-defined]
    _llm_stub.get_llm_cache = MagicMock()  # type: ignore[attr-defined]
    _llm_stub.TORCH_AVAILABLE = False  # type: ignore[attr-defined]
    _llm_stub.HardwareDetector = MagicMock()  # type: ignore[attr-defined]
    _llm_stub.LLMType = MagicMock()  # type: ignore[attr-defined]
    _llm_stub.ProviderType = MagicMock()  # type: ignore[attr-defined]
    _llm_stub.StreamingManager = MagicMock()  # type: ignore[attr-defined]
    sys.modules["llm_shared"] = _llm_stub

    # Sub-package stubs for dotted imports used by openai_compat and its deps.
    # llm_shared.types is needed by models.py (from .types import ...), so
    # load it from the real file before models.py is loaded.
    for _llm_sub in [
        "llm_shared.adapters",
        "llm_shared.providers",
        "llm_shared.tiered_routing",
        "llm_shared.tiered_routing.tier_router",
        "llm_shared.optimization",
        "llm_shared.cache",
    ]:
        if _llm_sub not in sys.modules:
            sys.modules[_llm_sub] = _make_pkg_stub(_llm_sub)
        # #11796: bind each sub-package stub as an attribute on its parent.
        # Without this, unittest.mock's dotted-name resolution (and
        # ``import llm_shared.X.Y as m``) walks getattr() through the parent
        # stub's catch-all __getattr__, gets the mock singleton instead of
        # the stub/real module in sys.modules, and string-form patch()
        # silently patches the wrong object (same trap _real_load_and_bind's
        # parent bind guards against).
        _llm_parent, _, _llm_child = _llm_sub.rpartition(".")
        setattr(sys.modules[_llm_parent], _llm_child, sys.modules[_llm_sub])

    # Give llm_shared.tiered_routing the real __path__ so submodule imports
    # (e.g. from llm_shared.tiered_routing.complexity_router import ...) can
    # find real files on disk.  The tiered_routing submodules only depend on
    # autobot_shared.logging_manager and lightweight config — no heavy deps.
    _tr_real_path = str(backend_root / "llm_shared" / "tiered_routing")
    sys.modules["llm_shared.tiered_routing"].__path__ = [_tr_real_path]  # type: ignore[attr-defined]

    # #11796: same for providers/ and optimization/ — submodules not stubbed
    # or real-loaded below stay importable from disk (and importlib.reload()
    # of a real-loaded provider can re-find its spec via the parent __path__).
    sys.modules["llm_shared.providers"].__path__ = [  # type: ignore[attr-defined]
        str(backend_root / "llm_shared" / "providers")
    ]
    sys.modules["llm_shared.optimization"].__path__ = [  # type: ignore[attr-defined]
        str(backend_root / "llm_shared" / "optimization")
    ]

    # GH#8998: Register real fallback_chain and model_fallback_coordinator modules
    # so tests inside llm_shared/ can import them without the full heavy __init__.py chain.
    # Load in dependency order: types → models → optimization.rate_limiter → fallback_chain → coordinator.
    # #11661: real-loads go through the canonical _real_load_and_bind helper so
    # every loaded module is also bound on its parent package stub (patch()
    # resolves via getattr(parent, child) — see the helper docstring).
    _llm_root = backend_root / "llm_shared"

    _real_load_and_bind("llm_shared.types", _llm_root / "types.py")
    _real_load_and_bind("llm_shared.models", _llm_root / "models.py")
    # #12714: thread-safe lazy torch loader shared by 9 call sites (flash_attention,
    # ssm_kernels, kv_cache, layer_inference, ai_hardware_accelerator,
    # multimodal_processor + vision/voice, incremental_trainer). No deps beyond
    # stdlib threading — safe to real-load unconditionally, early.
    _real_load_and_bind("llm_shared.torch_loader", _llm_root / "torch_loader.py")
    # #11520: canonical JSON parser and schema-typed extraction helper — lightweight,
    # no heavy deps; load real so tests importing them don't hit the stub.
    _real_load_and_bind("llm_shared.json_utils", _llm_root / "json_utils.py")
    _real_load_and_bind("llm_shared.structured_ops", _llm_root / "structured_ops.py")
    _real_load_and_bind("llm_shared.optimization.rate_limiter", _llm_root / "optimization" / "rate_limiter.py")
    _real_load_and_bind("llm_shared.fallback_chain", _llm_root / "fallback_chain.py")
    # #11519: provider degradation store — load real BEFORE model_fallback_coordinator
    # and provider_registry which import it at module level.
    _real_load_and_bind("llm_shared.provider_degradation", _llm_root / "provider_degradation.py")
    # #11995: PROVIDER_FALLBACK event emission helper — load real BEFORE
    # model_fallback_coordinator, which imports it at module level. events.bus
    # / events.event_types are unstubbed lightweight modules, safe to import here.
    _real_load_and_bind("llm_shared.fallback_events", _llm_root / "fallback_events.py")
    _real_load_and_bind("llm_shared.model_fallback_coordinator", _llm_root / "model_fallback_coordinator.py")
    # #9017: reasoning_effort utility is imported by chat_workflow.manager at module level;
    # load the real file so tests that import manager don't hit the providers MagicMock stub.
    _real_load_and_bind(
        "llm_shared.providers.reasoning_effort",
        _llm_root / "providers" / "reasoning_effort.py",
    )
    # #9037: per-run credential primitives (ContextVar + RunCredentialContext) live
    # in the lightweight run_credentials module; load it real so tests importing
    # them don't hit the llm_shared MagicMock stub.
    _real_load_and_bind("llm_shared.run_credentials", _llm_root / "run_credentials.py")
    # #10551: provider auth abstraction — load real so tests can import the
    # strategy classes without hitting the llm_shared MagicMock stub.
    _real_load_and_bind("llm_shared.provider_auth", _llm_root / "provider_auth.py")
    # #11762: credential redaction — was never real-loaded, so its co-located
    # tests silently failed collection and a redaction bug went unnoticed.
    _real_load_and_bind("llm_shared.credential_redaction", _llm_root / "credential_redaction.py")
    # #10551: base_provider — load real so BaseProvider tests can instantiate it.
    # #10917: base_provider's real load (added in #10551) silently failed because
    # the llm_shared stub has an empty __path__, so its relative imports
    # (`from .cross_worker_rate_limiter`, `.observability`, `.rate_limit_backoff`)
    # couldn't resolve on disk. Pre-load those transitive light deps in dependency
    # order — all bare-env-importable (observability guards its langfuse/langsmith
    # SDK imports inside methods and does not import otel_observer at top level) —
    # so base_provider (and then provider_registry) load real.
    _real_load_and_bind("llm_shared.cross_worker_rate_limiter", _llm_root / "cross_worker_rate_limiter.py")
    _real_load_and_bind("llm_shared.observability", _llm_root / "observability" / "__init__.py")
    _real_load_and_bind("llm_shared.rate_limit_backoff", _llm_root / "rate_limit_backoff.py")
    # #11541: pre-request cumulative token budget gate — base_provider imports it
    # at module level (`from .token_budget import get_token_budget_gate`); light
    # dep (autobot_shared.env_utils/logging_manager/singleton_factory + .models),
    # load real before base_provider so the gate isn't a MagicMock stub.
    _real_load_and_bind("llm_shared.token_budget", _llm_root / "token_budget.py")
    _real_load_and_bind("llm_shared.base_provider", _llm_root / "base_provider.py")
    _real_load_and_bind("llm_shared.model_param_registry", _llm_root / "model_param_registry.py")
    _real_load_and_bind("llm_shared.provider_registry", _llm_root / "provider_registry.py")
    # #11796: concrete provider modules + profiler — their test modules
    # (tests/llm_interface_pkg/*) import them at collection time, but the
    # llm_shared.providers / llm_shared.optimization pkg stubs have an empty
    # __path__, so without explicit real-loads those imports fail and the
    # files error out of every whole-dir collection.  All are light imports
    # (stdlib + the llm_shared seams real-loaded above + jinja2).
    # Dependency order: cache_utils → openai_compatible → concrete providers.
    _real_load_and_bind("llm_shared.providers.cache_utils", _llm_root / "providers" / "cache_utils.py")
    _real_load_and_bind(
        "llm_shared.providers.openai_compatible",
        _llm_root / "providers" / "openai_compatible.py",
    )
    _real_load_and_bind("llm_shared.providers.anthropic", _llm_root / "providers" / "anthropic.py")
    _real_load_and_bind("llm_shared.providers.groq", _llm_root / "providers" / "groq.py")
    _real_load_and_bind("llm_shared.providers.openai", _llm_root / "providers" / "openai.py")
    _real_load_and_bind("llm_shared.providers.custom_openai", _llm_root / "providers" / "custom_openai.py")
    _real_load_and_bind(
        "llm_shared.providers.chat_template_loader",
        _llm_root / "providers" / "chat_template_loader.py",
    )
    # vllm.py guards its heavy `from vllm import ...` in try/except, and
    # ollama_provider only needs aiohttp + light autobot_shared seams.
    _real_load_and_bind("llm_shared.providers.vllm", _llm_root / "providers" / "vllm.py")
    _real_load_and_bind(
        "llm_shared.providers.ollama_provider",
        _llm_root / "providers" / "ollama_provider.py",
    )
    # #11837: providers.ollama (the canonical Ollama provider, #11517) imports
    # `from ..streaming import StreamingManager` at module level, but the
    # llm_shared stub's empty __path__ can't resolve streaming.py on disk, so
    # the colocated providers/ollama_test.py errored out of every collection.
    # streaming.py is light (stdlib + autobot_shared.logging_manager); load it
    # first, then the provider itself.
    _real_load_and_bind("llm_shared.streaming", _llm_root / "streaming.py")
    _real_load_and_bind("llm_shared.providers.ollama", _llm_root / "providers" / "ollama.py")
    _real_load_and_bind("llm_shared.optimization.profiler", _llm_root / "optimization" / "profiler.py")
    # Re-export the real classes onto the top-level stub so
    # `from llm_shared import ProviderRegistry, BaseProvider` resolves to the real
    # ones for tests that exercise them (tests/test_provider_registry.py, #10917).
    _pr_mod = sys.modules.get("llm_shared.provider_registry")
    if _pr_mod is not None and hasattr(_pr_mod, "ProviderRegistry"):
        _llm_stub.ProviderRegistry = _pr_mod.ProviderRegistry  # type: ignore[attr-defined]
    _bp_mod = sys.modules.get("llm_shared.base_provider")
    if _bp_mod is not None and hasattr(_bp_mod, "BaseProvider"):
        _llm_stub.BaseProvider = _bp_mod.BaseProvider  # type: ignore[attr-defined]

    # #11840: Real-load llm_shared.optimization.model_inspector — it is light
    # (transformers/accelerate are lazily imported inside functions, so the
    # bare env just gets the formula/None fallbacks).  It was previously
    # stubbed here, which silently fed MagicMocks to its own colocated
    # optimization/model_inspector_test.py (never-run-test-files pattern).
    _real_load_and_bind(
        "llm_shared.optimization.model_inspector",
        _llm_root / "optimization" / "model_inspector.py",
    )

    # #11618: Real-load llm_shared.hardware so patch("llm_shared.hardware.X") in
    # test_hardware.py targets the real module globals instead of the MagicMock
    # package stub.  Deps: autobot_shared.logging_manager (already patched) and
    # llm_shared.optimization.model_inspector (real-loaded just above).
    _real_load_and_bind("llm_shared.hardware", _llm_root / "hardware.py")
    _hw_mod = sys.modules.get("llm_shared.hardware")
    if _hw_mod is not None:
        # Parent bind (so patch("llm_shared.hardware.X") targets the real
        # module) now happens inside _real_load_and_bind (#11661); only the
        # top-level re-exports remain here.
        if hasattr(_hw_mod, "HardwareDetector"):
            _llm_stub.HardwareDetector = _hw_mod.HardwareDetector  # type: ignore[attr-defined]
        if hasattr(_hw_mod, "TORCH_AVAILABLE"):
            _llm_stub.TORCH_AVAILABLE = _hw_mod.TORCH_AVAILABLE  # type: ignore[attr-defined]

    # #12438: Real-load llm_shared.pricing — auto-refresh pricing sources (GH#6480).
    # Self-contained aside from autobot_shared.logging_manager (already patched)
    # and autobot_shared.redis_client (real module); the llm_shared stub's empty
    # __path__ otherwise breaks every provider-source import and its colocated
    # services/pricing_refresh_test.py. Dependency order: sources → redis_store
    # → per-provider sources → package __init__.
    _real_load_and_bind("llm_shared.pricing.sources", _llm_root / "pricing" / "sources.py")
    _real_load_and_bind("llm_shared.pricing.redis_store", _llm_root / "pricing" / "redis_store.py")
    _real_load_and_bind("llm_shared.pricing.anthropic_source", _llm_root / "pricing" / "anthropic_source.py")
    _real_load_and_bind("llm_shared.pricing.openai_source", _llm_root / "pricing" / "openai_source.py")
    _real_load_and_bind("llm_shared.pricing.google_source", _llm_root / "pricing" / "google_source.py")
    _real_load_and_bind("llm_shared.pricing.deepseek_source", _llm_root / "pricing" / "deepseek_source.py")
    _real_load_and_bind("llm_shared.pricing.vertexai_source", _llm_root / "pricing" / "vertexai_source.py")
    _real_load_and_bind("llm_shared.pricing", _llm_root / "pricing" / "__init__.py")
    # The submodule real-loads above ran before "llm_shared.pricing" existed in
    # sys.modules, so _real_load_and_bind's own parent-bind was a no-op for them
    # (and __init__.py's "from llm_shared.pricing.X import Y" doesn't re-trigger
    # it either, since those submodules were already sys.modules-cached). Bind
    # them explicitly now so patch("llm_shared.pricing.redis_store.X") resolves
    # via getattr(llm_shared.pricing, "redis_store") instead of raising
    # AttributeError.
    _pricing_pkg = sys.modules["llm_shared.pricing"]
    for _pricing_sub in (
        "sources",
        "redis_store",
        "anthropic_source",
        "openai_source",
        "google_source",
        "deepseek_source",
        "vertexai_source",
    ):
        setattr(_pricing_pkg, _pricing_sub, sys.modules[f"llm_shared.pricing.{_pricing_sub}"])

    # llm_shared.cache — provide symbols consumed by services.llm_service
    _cache_stub = sys.modules["llm_shared.cache"]
    _cache_stub.CachedResponse = MagicMock()  # type: ignore[attr-defined]
    _cache_stub.LLMResponseCache = MagicMock()  # type: ignore[attr-defined]
    _cache_stub.get_llm_cache = MagicMock()  # type: ignore[attr-defined]

    # llm_shared.adapters.registry — provide get_adapter_registry for api.adapters
    if "llm_shared.adapters.registry" not in sys.modules:
        _adapters_registry_stub = _make_pkg_stub("llm_shared.adapters.registry")
        _adapters_registry_stub.get_adapter_registry = MagicMock()  # type: ignore[attr-defined]
        _adapters_registry_stub.AdapterRegistry = MagicMock()  # type: ignore[attr-defined]
        sys.modules["llm_shared.adapters.registry"] = _adapters_registry_stub

    # Provide a real tiered_router.get_tiered_router MagicMock
    _tr_stub = sys.modules.get("llm_shared.tiered_routing.tier_router") or _make_pkg_stub(
        "llm_shared.tiered_routing.tier_router"
    )
    _tr_stub.get_tiered_router = MagicMock()  # type: ignore[attr-defined]
    sys.modules["llm_shared.tiered_routing.tier_router"] = _tr_stub

    # Stub llm_shared.model_param_registry — provides symbols needed by
    # long_context_router and other tiered_routing modules.  Tests that need
    # real behaviour mock list_long_context_candidates via patch().
    if "llm_shared.model_param_registry" not in sys.modules:
        _mpr_stub = _make_pkg_stub("llm_shared.model_param_registry")
        _mpr_stub.list_long_context_candidates = MagicMock(return_value=[])  # type: ignore[attr-defined]
        _mpr_stub.get_architecture_family = MagicMock(return_value="transformer")  # type: ignore[attr-defined]
        _mpr_stub.resolve_model_name = MagicMock(side_effect=lambda m: m)  # type: ignore[attr-defined]
        _mpr_stub.get_model_kwargs = MagicMock(return_value={})  # type: ignore[attr-defined]
        _mpr_stub.ArchitectureFamily = MagicMock()  # type: ignore[attr-defined]
        sys.modules["llm_shared.model_param_registry"] = _mpr_stub

    # #11730: llm_shared.types and llm_shared.models are load-once — they were
    # already real-loaded above via _real_load_and_bind.  The former
    # _load_llm_sub helper (third near-identical loader) re-loaded them here,
    # creating SECOND module copies: everything loaded in between
    # (fallback_chain, model_fallback_coordinator, base_provider,
    # provider_registry, …) held classes from the first copy while later test
    # imports got the second, breaking isinstance checks.  Nothing depends on
    # reload semantics — the re-load ran once, immediately after the first
    # load, inside the same conftest pass.  Only semantic_cache still loads
    # here (its first and only load), through the canonical helper.

    # Load llm_shared.semantic_cache (Issue #8168) — pure Python + numpy,
    # no heavy deps at import time.  On load failure _real_load_and_bind
    # installs a pkg stub whose __getattr__ yields a MagicMock, so the
    # SemanticLLMCache re-export below stays mock-backed as before.
    _real_load_and_bind("llm_shared.semantic_cache", _llm_root / "semantic_cache.py")
    _sc_mod = sys.modules.get("llm_shared.semantic_cache")
    if _sc_mod is not None and hasattr(_sc_mod, "SemanticLLMCache"):
        _llm_stub.SemanticLLMCache = _sc_mod.SemanticLLMCache  # type: ignore[attr-defined]

# auth_middleware stub — the real module pulls in the full config/Redis chain
# at import time (config.manager, error_catalog, etc.) which fails in the dev
# venv.  Every name exported here must be a real callable with a real
# signature, because routers capture them in ``Depends(...)`` at import time.
if "auth_middleware" not in sys.modules:
    from fastapi import Request as _FastAPIRequest

    _auth_stub = types.ModuleType("auth_middleware")
    _auth_stub.__path__ = []  # type: ignore[attr-defined]
    _auth_stub.__package__ = "auth_middleware"

    # get_current_user must be a real callable, not a bare MagicMock (#13253).
    # ``inspect.signature(MagicMock())`` is ``(*args, **kwargs)``; FastAPI's
    # get_dependant() does not skip VAR_POSITIONAL/VAR_KEYWORD parameters, so
    # both become REQUIRED query parameters. Every request to any router that
    # declares ``Depends(get_current_user)`` then fails validation with
    # ``422 {'loc': ['query', 'args'], 'msg': 'Field required'}`` before the
    # handler ever runs — same failure mode as #10472 below.
    # The ``request`` parameter is annotated ``Request`` so FastAPI injects it
    # instead of treating it as a request field, and defaults to None so
    # direct ``get_current_user()`` call sites keep working.
    def _get_current_user_stub(request: _FastAPIRequest = None) -> dict:  # type: ignore[assignment] # noqa: E301
        return {
            "username": "test-user",
            "user_id": "test-user",
            "role": "admin",
            "auth_method": "stub",
        }

    _auth_stub.get_current_user = _get_current_user_stub  # type: ignore[attr-defined]

    # check_admin_permission must be a proper no-arg callable so FastAPI can
    # inspect its signature at route-registration time without producing spurious
    # (*args, **kwargs) query parameters (#10472).
    def _check_admin_permission_stub():  # noqa: E301
        return True

    _auth_stub.check_admin_permission = _check_admin_permission_stub  # type: ignore[attr-defined]

    # require_device_jwt is a dependency FACTORY (GH#9493/#11736) invoked at
    # module import time — it must return a no-arg callable so FastAPI can
    # inspect the signature at route registration without producing spurious
    # (*args, **kwargs) query parameters (same rationale as above, #10472).
    def _require_device_jwt_stub(min_scope: str = "read"):  # noqa: E301
        def _device_jwt_dep():
            return {
                "username": "device:stub-device",
                "user_id": "stub-user",
                "role": "device",
                "device_id": "00000000-0000-0000-0000-000000000000",
                "scope": min_scope,
                "auth_method": "device_jwt",
            }

        return _device_jwt_dep

    _auth_stub.require_device_jwt = _require_device_jwt_stub  # type: ignore[attr-defined]
    _auth_stub.__getattr__ = lambda attr: MagicMock()  # type: ignore[attr-defined]
    sys.modules["auth_middleware"] = _auth_stub

# autobot_shared.redis_management stubs — the real package tries to open
# sockets at import time; tests must not do that.
for _redis_sub in [
    "autobot_shared.redis_management",
    "autobot_shared.redis_management.types",
    "autobot_shared.redis_management.connection_manager",
    "autobot_shared.redis_management.cache_wrapper",
    "autobot_shared.redis_management.config",
    "autobot_shared.redis_management.statistics",
]:
    if _redis_sub not in sys.modules:
        _redis_stub = types.ModuleType(_redis_sub)
        _redis_stub.__path__ = []
        _redis_stub.__package__ = _redis_sub.rpartition(".")[0]
        _redis_stub.DATABASE_MAPPING = {  # type: ignore[attr-defined]
            "celery_broker": 0,
            "celery_results": 1,
        }
        _redis_stub.__getattr__ = lambda attr: MagicMock()  # type: ignore[attr-defined]
        sys.modules[_redis_sub] = _redis_stub

# autobot_shared.logging_manager.get_logger stub — issue #7766.
# get_logger() tries to open a log file which requires the config/Redis stack
# and hangs in the test environment.  Patch it to return a stdlib logger so
# that task modules that call ``logger = get_logger(__name__)`` at module load
# time proceed instantly.
try:
    import logging as _stdlib_logging

    import autobot_shared.logging_manager as _lm_mod

    if not getattr(_lm_mod, "_get_logger_patched_for_tests", False):
        _lm_mod.get_logger = lambda name, *_a, **_k: _stdlib_logging.getLogger(name)
        _lm_mod._get_logger_patched_for_tests = True  # type: ignore[attr-defined]
except Exception:
    pass


# orchestration.causal_error_recovery / causal_error_analyzer stubs (#7431).
# orchestration/__init__.py imports CausalErrorRecovery from causal_error_recovery,
# which cascades through agent_loop → code_intelligence — a chain of
# modules with Python-3.10-incompatible annotations or missing config keys.
# Stub these modules so the lightweight types-only tests can collect without
# needing the full backend stack.
#
# ``orchestration.causal_validator`` is deliberately NOT on this list (#13162).
# It has none of the heavy chain the entries below are here for — its only
# imports are ``autobot_shared.logging_manager``, ``orchestration.causal_models``
# (stdlib dataclasses/enum only) and ``orchestration.dag_executor``, both of
# which every consumer already real-imports. Stubbing it handed
# ``orchestration/test_causal_executor.py`` a MagicMock ``CausalValidator``, so
# ``validate_workflow()`` returned a mock whose ``.valid`` was truthy, whose
# ``errors()``/``warnings()`` had ``len() == 0`` and iterated empty — the whole
# TestCausalValidator class asserted against mock defaults instead of the real
# validator (2 tests failed outright, 3 silently asserted nothing, and
# ``test_validate_no_issues_linear_workflow`` passed for the wrong reason).
# Same class of harness bug as ``code_intelligence.merge_conflict_resolver``
# below (#13111).
for _causal_mod in [
    "orchestration.causal_error_recovery",
    "orchestration.causal_error_analyzer",
    "agent_loop",
    "agent_loop.loop",
    "agent_loop.think_tool",
    "code_intelligence",
]:
    if _causal_mod not in sys.modules:
        sys.modules[_causal_mod] = _make_pkg_stub(_causal_mod)

# ``agent_loop.tool_output_spill`` is deliberately real-imported despite its
# parent package being stubbed above (#13692). Same reasoning the comment gives
# for ``orchestration.causal_validator``: it has none of the heavy chain the
# stub exists for — stdlib plus ``autobot_shared.logging_manager`` only. Leaving
# it behind the stub's empty ``__path__`` would hand its tests a MagicMock and
# have them assert against mock defaults, which is the #13111/#13162 bug.
if "agent_loop.tool_output_spill" not in sys.modules:
    import importlib.util as _ilu

    _spill_path = Path(__file__).parent / "agent_loop" / "tool_output_spill.py"
    if _spill_path.exists():
        _spec = _ilu.spec_from_file_location("agent_loop.tool_output_spill", _spill_path)
        if _spec and _spec.loader:
            _spill_mod = _ilu.module_from_spec(_spec)
            sys.modules["agent_loop.tool_output_spill"] = _spill_mod
            _spec.loader.exec_module(_spill_mod)
            sys.modules["agent_loop"].tool_output_spill = _spill_mod

# code_intelligence.code_generation.diff real-load (#12438) — tools/parallel/executor.py
# imports the real DiffGenerator (self-contained: stdlib difflib only) to build CODE_DIFF
# artifacts. code_intelligence itself is stubbed above (its __init__ has Python-3.10-
# incompatible annotations), so real-load this leaf submodule bypassing that __init__.
# NOTE: tools.parallel / tools.parallel.executor are intentionally NOT in the stub list
# above — they are self-contained aside from this one dependency and executor_artifacts_test.py
# needs the real ParallelToolExecutor/DiffGenerator behaviour.
if "code_intelligence.code_generation" not in sys.modules:
    sys.modules["code_intelligence.code_generation"] = _make_pkg_stub("code_intelligence.code_generation")
_real_load_and_bind(
    "code_intelligence.code_generation.diff",
    backend_root / "code_intelligence" / "code_generation" / "diff.py",
)

# code_intelligence.shared.scoring real-load (#12686) — api/analytics_code.py,
# api/code_intelligence.py, api/analytics_reporting.py, and services/analytics_service.py
# import get_grade_from_score from code_intelligence.shared.scoring at module level
# (canonicalized 5 duplicate score->grade forks onto this shared helper). scoring.py is
# self-contained (stdlib only: math, typing), so real-load this leaf submodule bypassing
# code_intelligence.shared's own __init__ (which pulls ASTCache/FileListCache — heavier
# deps not needed here), same pattern as code_intelligence.code_generation.diff above.
if "code_intelligence.shared" not in sys.modules:
    sys.modules["code_intelligence.shared"] = _make_pkg_stub("code_intelligence.shared")
_real_load_and_bind(
    "code_intelligence.shared.scoring",
    backend_root / "code_intelligence" / "shared" / "scoring.py",
)

# code_intelligence.fingerprinting.* real-load (#13509) — services/knowledge/code_indexer.py
# imports compute_graph_shape_fingerprint/shape_matches to decide whether a changed file
# produced the same graph nodes/edges (skip re-embedding) or a different shape (rebuild).
#
# Real-loaded rather than stubbed, and the distinction is the whole point: a MagicMock
# compute_graph_shape_fingerprint returns a Mock, shape_matches rejects it as a non-str,
# and every file re-embeds. That is the correct fail-open, so the stub produces a GREEN
# test suite for a feature that never once ran — the saving under test is invisible.
#
# graph_shape is stdlib-only (hashlib, typing) plus logging_manager, so this bypasses
# code_intelligence/__init__ exactly like diff and scoring above.
# NOTE: a `_make_pkg_stub` here would be wrong — its ``__path__`` is empty, so the package
# would stop resolving its OTHER submodules and code_fingerprinting's real-load would die on
# `code_intelligence.fingerprinting.detector`. The real directory is used instead, which keeps
# every sibling importable while graph_shape is the only leaf executed eagerly.
if "code_intelligence.fingerprinting" not in sys.modules:
    _fp_pkg = types.ModuleType("code_intelligence.fingerprinting")
    _fp_pkg.__path__ = [str(backend_root / "code_intelligence" / "fingerprinting")]
    _fp_pkg.__package__ = "code_intelligence.fingerprinting"
    sys.modules["code_intelligence.fingerprinting"] = _fp_pkg
    # The namespace bind is load-bearing, same as in code_intelligence/conftest.py:
    # `import code_intelligence.fingerprinting.X as m` binds via getattr on the PARENT,
    # not via sys.modules. Without this, that walks the code_intelligence stub's catch-all
    # __getattr__ and hands back a MagicMock, while `from ... import f` in the same file
    # resolves through sys.modules to the real function — two different objects, so
    # monkeypatching the module has no effect on the function under test.
    if "code_intelligence" in sys.modules:
        sys.modules["code_intelligence"].fingerprinting = _fp_pkg
_real_load_and_bind(
    "code_intelligence.fingerprinting.graph_shape",
    backend_root / "code_intelligence" / "fingerprinting" / "graph_shape.py",
)

# code_intelligence.shared.process_offload real-load (#12866) — api/code_intelligence.py
# imports run_directory_scan/run_isolated at module level to run whole-tree scans in a
# separate process instead of a GIL-bound thread. Same situation as scoring above: the
# package is stubbed, so without this the module import fails outright and every
# api.code_intelligence import test breaks.
#
# Real-loaded rather than stubbed on purpose. A MagicMock here would hand callers a mock
# that never runs the scan and never populates analyzer.results — the endpoints would
# "pass" while returning empty findings, which is the #13111 / #13162 harness-bug shape.
# The module is self-contained: stdlib (asyncio, multiprocessing, concurrent.futures) plus
# autobot_shared.logging_manager, which every consumer already real-imports.
_real_load_and_bind(
    "code_intelligence.shared.process_offload",
    backend_root / "code_intelligence" / "shared" / "process_offload.py",
)

# code_intelligence submodule stubs — code_intelligence itself is stubbed above
# (its __init__ has Python-3.10-incompatible annotations), so submodule imports
# from api/*.py need their own stubs with the right symbol names.
_ci_anti_stub = _make_pkg_stub("code_intelligence.anti_pattern_detector")
_ci_anti_stub.AntiPatternDetector = MagicMock()  # type: ignore[attr-defined]
_ci_anti_stub.AntiPatternSeverity = MagicMock()  # type: ignore[attr-defined]
_ci_anti_stub.AntiPatternResult = MagicMock()  # type: ignore[attr-defined]
sys.modules["code_intelligence.anti_pattern_detector"] = _ci_anti_stub

# code_intelligence.merge_conflict_resolver real-load (#13111) — this module used
# to be a MagicMock package stub here, which poisoned TWO test files:
#   * code_intelligence/merge_conflict_resolver_test.py (its own unit tests), and
#   * api/merge_conflict_resolution_test.py — api/merge_conflict_resolution.py binds
#     ConflictBlock/ConflictParser/MergeConflictResolver/... into its module globals
#     at import time, so every TestClient endpoint test dispatched into mocked types.
# The api/ consumer is why this real-load lives HERE and not in
# code_intelligence/conftest.py: pytest collects api/ before code_intelligence/, so a
# subdirectory-conftest fix would land after api/merge_conflict_resolution.py has
# already bound the stub's mocks.
# Safe to real-load: merge_conflict_resolver.py is self-contained (stdlib ast/re/
# dataclasses/enum/pathlib/typing plus autobot_shared.logging_manager, which is
# patched to a stdlib logger above). Same pattern as code_intelligence.code_generation.diff
# and code_intelligence.shared.scoring — it bypasses code_intelligence/__init__.py, which
# stays stubbed. _real_load_and_bind falls back to a package stub if the load ever fails,
# so import-time behaviour for api/*.py is never worse than the old hand-written stub.
_real_load_and_bind(
    "code_intelligence.merge_conflict_resolver",
    backend_root / "code_intelligence" / "merge_conflict_resolver.py",
)

# NOTE (#13111): every entry below that also owns a colocated ``<name>_test.py`` is
# real-loaded again by code_intelligence/conftest.py, which runs after this file and
# repairs code_intelligence.__path__ so the real submodules resolve. The stubs here
# must stay: api/*.py imports several of these at module level and is collected
# BEFORE code_intelligence/, so removing an entry would turn an api-side import into
# a collection error. Add a matching _load_real_submodule() call over there whenever a
# new colocated test file is added for a stubbed submodule — otherwise that test
# silently asserts against MagicMock attributes instead of real behaviour.
#
# NOTE: "code_intelligence.test_pattern_analyzer" is intentionally NOT in this
# list (#12437). Stubbing it here would poison sys.modules before pytest ever
# collects code_intelligence/test_pattern_analyzer.py itself: with
# --import-mode=importlib, pytest's import_path() returns whatever is already
# in sys.modules[module_name] rather than re-importing, so the real test file
# would never execute — pytest would instead try to treat the MagicMock-backed
# stub module as the test module, and accessing its (mocked) `pytestmark`
# attribute raises TypeError during collection. Nothing else in the codebase
# imports this submodule (code_intelligence/__init__.py does, but that package
# is itself fully stubbed above and never executes its real __init__), so
# leaving it unstubbed is safe.
for _ci_sub in [
    "code_intelligence.performance_analyzer",
    "code_intelligence.redis_optimizer",
    "code_intelligence.security",  # real package loaded by code_intelligence/conftest.py (#9856)
    "code_intelligence.security_analyzer",
    "code_intelligence.code_evolution_miner",
    "code_intelligence.bug_predictor",
    "code_intelligence.llm_pattern_analyzer",
    "code_intelligence.log_pattern_miner",
    "code_intelligence.multi_language_scanner",
    "code_intelligence.pattern_analysis",
    "code_intelligence.precommit_analyzer",
    "code_intelligence.shell_analyzer",
    "code_intelligence.typescript_analyzer",
    "code_intelligence.vue_analyzer",
    "code_intelligence.doc_generator",
    "code_intelligence.llm_code_generator",
    "code_intelligence.code_fingerprinting",
    "code_intelligence.code_review_engine",
    "code_intelligence.base_analyzer",
    "code_intelligence.conversation_flow_analyzer",
]:
    if _ci_sub not in sys.modules:
        sys.modules[_ci_sub] = _make_pkg_stub(_ci_sub)

# cross_language_patterns stub — endpoints/cross_language_patterns.py imports
# CrossLanguagePatternDetector at module level; without this stub, all
# api.codebase_analytics colocated tests fail to collect (#11129).
if "code_intelligence.cross_language_patterns" not in sys.modules:
    _ci_clp_stub = _make_pkg_stub("code_intelligence.cross_language_patterns")
    _ci_clp_stub.CrossLanguagePatternDetector = MagicMock()  # type: ignore[attr-defined]
    sys.modules["code_intelligence.cross_language_patterns"] = _ci_clp_stub


def _stub_symbols(name: str, **symbols) -> types.ModuleType:
    """Return the ``sys.modules`` entry for *name*, decorating it ONLY if it is a stub.

    #13162: these three blocks used to read
    ``sys.modules.get(name) or _make_pkg_stub(name)`` and then assign MagicMocks
    unconditionally. When the real module was already imported — anything loaded
    earlier in this conftest can pull ``orchestration/__init__.py``, whose line
    ``from .causal_error_recovery import CausalErrorRecovery, RecoveryPlan, ...``
    imports the genuine module — that assignment silently REPLACED real classes
    in a real module's globals. The module then keeps executing its own code
    against mocks: ``recommend_recovery()`` runs for real, logs a real pattern
    hash, and returns ``RecoveryPlan(...)`` — a MagicMock. Callers see
    ``plan.error_type`` as a mock and ``plan.causal_chain.encode()`` blows up in
    ``hashlib.md5`` with "object supporting the buffer API required".

    A module loaded from a file has ``__file__``; the package stubs built by
    ``_make_pkg_stub`` never do. Decorating only the latter keeps the stub
    contract (orchestration's import must resolve) without ever mutating real code.
    """
    existing = sys.modules.get(name)
    if existing is not None and getattr(existing, "__file__", None) is not None:
        return existing  # real module — never overwrite its symbols
    stub = existing if existing is not None else _make_pkg_stub(name)
    for _sym_name, _sym_value in symbols.items():
        setattr(stub, _sym_name, _sym_value)
    sys.modules[name] = stub
    return stub


# Ensure CausalErrorRecovery / RecoveryPlan / get_recovery_recommender are
# resolvable from the stub so orchestration/__init__.py's wildcard import
# (`from .causal_error_recovery import CausalErrorRecovery, ...`) succeeds.
_stub_symbols(
    "orchestration.causal_error_recovery",
    CausalErrorRecovery=MagicMock(),
    RecoveryPlan=MagicMock(),
    get_recovery_recommender=MagicMock(),
)

_stub_symbols("orchestration.causal_error_analyzer", CausalErrorAnalysis=MagicMock())

_al_stub = _stub_symbols("agent_loop", AgentLoop=MagicMock())
# Give the injected stub a REAL __path__ so the package's light submodules
# (types, belief_state, pre_action_verifier, slack_hook, …) resolve on-demand from
# disk for the in-package agent_loop/ tests (#11153) — WITHOUT running agent_loop/
# __init__.py, which pulls the heavy agent_loop.loop → tools → code_intelligence
# cascade. The heavy submodules stay explicitly stubbed just below, so importing
# them still hits the stub (sys.modules wins over the on-disk file).
_al_stub.__path__ = [str(backend_root / "agent_loop")]  # type: ignore[attr-defined]
sys.modules["agent_loop"] = _al_stub


def _try_real_load_agent_loop_heavy():
    """#11153: agent_loop.loop / think_tool real-import cleanly on py3.12+ (the
    py3.10 annotation incompatibility that motivated stubbing them is gone). Attempt
    a real load so the in-package agent_loop/ tests exercise real code; fall back to
    a stub if the environment can't satisfy the import (missing dev-venv deps). Loop
    tolerates the stubbed code_intelligence at import time (verified: full-suite
    collection drops from 294 to 287 errors, +108 tests collected, no regressions)."""
    import importlib as _al_il

    for _al_mod in ("agent_loop.loop", "agent_loop.think_tool"):
        try:
            sys.modules.pop(_al_mod, None)
            sys.modules[_al_mod] = _al_il.import_module(_al_mod)
        except Exception:
            sys.modules[_al_mod] = _make_pkg_stub(_al_mod)


_try_real_load_agent_loop_heavy()

# Package stubs for SQLAlchemy and alembic sub-packages (need __path__ so
# dotted sub-module imports like ``sqlalchemy.dialects.postgresql`` resolve).
_PKG_STUBS = [
    "sqlalchemy",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
    "sqlalchemy.orm",
    "sqlalchemy.orm.declarative",
    "sqlalchemy.dialects",
    "sqlalchemy.dialects.postgresql",
    "sqlalchemy.types",
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "sqlalchemy.sql",
    "sqlalchemy.sql.sqltypes",
    "alembic.op",
    "alembic.context",
]
for _pkg in _PKG_STUBS:
    try:
        import importlib as _il

        _il.import_module(_pkg)
    except ImportError:
        if _pkg not in sys.modules:
            _make_pkg_stub(_pkg)

# Fix metaclass conflict (#4300): when SQLAlchemy is not installed the stubs
# above make sqlalchemy.orm a MagicMock namespace module.  Every attribute
# access returns the same MagicMock instance, so ``DeclarativeBase`` becomes a
# MagicMock *instance*.  Inheriting from a MagicMock instance gives the
# subclass metaclass ``MagicMock`` (not ``type``).  Then any model that does
# ``class Foo(SomePlainMixin, DeclarativeBase)`` raises:
#   TypeError: metaclass conflict: the metaclass of a derived class must be a
#   (non-strict) subclass of the metaclasses of all its bases
# because ``MagicMock`` and ``type`` are incompatible metaclasses.
#
# Fix: patch the ORM stub so that ``DeclarativeBase`` and
# ``declarative_base`` are real Python classes/callables that produce
# ``type``-metaclassed base classes.  All other ORM attributes remain as
# MagicMock so the rest of the stub still works.
#
# Detection: real sqlalchemy.orm is a real ModuleType whose __dict__ contains
# the actual class objects; our stub's __dict__ only has __getattr__ and a few
# dunder attrs.  Check isinstance to distinguish a real module from the stub.
if "sqlalchemy.orm" in sys.modules:
    _orm_mod = sys.modules["sqlalchemy.orm"]
    # The stub module has __getattr__ set on the module object directly; real
    # sqlalchemy.orm does not.  Use that as the distinguishing signal.
    _is_stub = "__getattr__" in vars(_orm_mod)
    if _is_stub:

        class _DeclarativeBase:
            """Minimal SQLAlchemy DeclarativeBase stub with correct metaclass."""

            type_annotation_map: dict = {}

        def _declarative_base(**kwargs):
            """Minimal declarative_base() stub that returns a type-metaclassed class."""
            return _DeclarativeBase

        _orm_mod.DeclarativeBase = _DeclarativeBase  # type: ignore[attr-defined]
        _orm_mod.declarative_base = _declarative_base  # type: ignore[attr-defined]

# Pre-register models.infrastructure directly so that ``from models.infrastructure
# import ...`` succeeds without triggering models/__init__.py (which requires the
# full SQLAlchemy stack that is not installed in the dev/CI venv).
# This must run AFTER the sqlalchemy stubs above so that any subsequent import of
# models/__init__.py itself (if forced by other test files) has sqlalchemy stubs
# already in place.
if "models" not in sys.modules:
    # Create a lightweight 'models' namespace package to hold the sub-module,
    # then real-load infrastructure.py onto it (#11661: canonical helper; it
    # also performs the parent bind this block previously did by hand).
    _models_pkg = _make_pkg_stub("models")
    _models_pkg.__path__ = [str(backend_root / "models")]
    _real_load_and_bind("models.infrastructure", backend_root / "models" / "infrastructure.py")


# -- Requirements.txt enforcement (Issue #5032 / #5044) --------------------
# Tests that use optional parsers like bs4 declare `pytest.importorskip(...)`
# so they skip gracefully. But a silent skip of ~10% of the suite looks like
# a passing run to an inattentive reviewer. This session hook reads
# requirements.txt and reports which declared deps are not installed, so the
# developer sees a clear "run pip install -r requirements.txt" hint at the
# top of every test run instead of silent skip messages buried further down.
#
# Uses importlib.metadata.distribution() to check installed-ness by dist name
# (the exact name from requirements.txt) — no module-name translation needed,
# and no __init__.py side-effects like find_spec() would cause.


# End of window 1 (#13446) — nothing below this line runs at import time.
_SCOPED_REDIS.exit("conftest-import")


def _parse_requirements(path: Path) -> list[str]:
    """Return package names declared in a requirements.txt file."""
    names: list[str] = []
    if not path.exists():
        return names
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip().split("#", 1)[0].strip()
        if not line or line.startswith("-"):  # skip comments, blanks, -r/-e flags
            continue
        # Strip version specifiers and extras
        for sep in ("==", ">=", "<=", "~=", ">", "<", "!=", "["):
            if sep in line:
                line = line.split(sep, 1)[0].strip()
        if line:
            names.append(line)
    return names


def pytest_report_header(config) -> list[str]:
    """Report missing requirements.txt deps in the pytest session header.

    Does NOT fail the session — stubs in this conftest and `pytest.importorskip`
    calls in test files still handle graceful degradation. Purpose is to
    surface the root cause when tests silently skip due to missing deps.
    """
    from importlib import metadata as _im

    req_file = backend_root / "requirements.txt"
    declared = _parse_requirements(req_file)
    if not declared:
        return []

    missing: list[str] = []
    for dist in declared:
        try:
            _im.distribution(dist)
        except _im.PackageNotFoundError:
            missing.append(dist)

    if not missing:
        return [f"requirements.txt: all {len(declared)} deps installed"]

    preview = ", ".join(missing[:8]) + ("..." if len(missing) > 8 else "")
    return [
        f"requirements.txt: {len(missing)}/{len(declared)} deps NOT installed ({preview})",
        "    Run: pip install -r autobot-backend/requirements.txt",
        "    Tests using these deps will skip; see importorskip messages below.",
    ]


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_data_dir() -> Path:
    """Get test data directory."""
    return Path(__file__).parent / "tests" / "fixtures" / "data"


@pytest.fixture
def temp_dir(tmp_path) -> Path:
    """Provide temporary directory for test files."""
    return tmp_path


@pytest.fixture
def mock_llm():
    """Minimal LLM mock — tests attach .return_value / .side_effect as needed.

    Extracted from 4+ inline duplicates (#5432). Tests that need richer
    response-mock setup define their own local fixture which overrides this.
    """
    return AsyncMock()


@pytest.fixture
def single_use_fake_redis():
    """Synchronous in-memory Redis stub for single-use OAuth-state tests (#11699).

    Backs ``set(ex=)`` / ``get`` / ``getdel`` / ``delete`` with an
    introspectable ``.store`` dict.  Consolidates the byte-identical
    ``_FakeRedis`` copies that lived in the connector- and provider-auth OAuth
    endpoint tests (they exercise the ``client_setex`` / ``client_getdel`` /
    ``client_get`` single-use-state helpers now in autobot_shared.redis_client).
    """

    class _SingleUseFakeRedis:
        def __init__(self) -> None:
            self.store: dict = {}

        def set(self, key, value, ex=None):
            self.store[key] = value
            return True

        def get(self, key):
            return self.store.get(key)

        def getdel(self, key):
            return self.store.pop(key, None)

        def delete(self, key):
            return 1 if self.store.pop(key, None) is not None else 0

    return _SingleUseFakeRedis()


@pytest.fixture(autouse=True)
def set_test_environment():
    """
    Set TEST environment variables for all tests.
    Prevents tests from affecting production data.
    """
    original_env = dict(os.environ)

    config.test_mode = "true"
    config.env = "test"

    yield

    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture(autouse=True)
def _reset_synthesis_schema_cache():
    """Clear the rag_service synthesis-schema singleton around every test (#12531).

    ``services.rag_service._SYNTHESIS_SCHEMA_CACHE`` is a module-level singleton guarded
    by ``if ... is None``: the first test that triggers a real load permanently caches
    the on-disk schema, so later tests that patch ``load_synthesis_schema`` are silently
    ignored. Resetting before and after each test keeps the cache from leaking across the
    process regardless of which test populated it.
    """
    try:
        import services.rag_service as _rag
    except Exception:
        yield
        return
    _rag.reset_synthesis_schema_cache()
    yield
    _rag.reset_synthesis_schema_cache()


# #12438: Modules deliberately handled elsewhere in this conftest — skip them in
# the generalized real-load loop so it doesn't clobber their configured stubs or
# double-load the ones already loaded via _real_load_and_bind above.
_SERVICES_REAL_LOAD_SKIP = frozenset(
    {
        "__init__",
        "llm_service",  # deliberate heavy stub (Redis/npu chain — see block near L206)
        "personality_service",  # deliberate stub carrying SUPPORTED_LANGUAGES symbol
        "llm_api_key_service",  # real-loaded in pytest_configure below
        "llm_cost_tracker",  # real-loaded in pytest_configure below
        "tool_output_filter",  # real-loaded at import time (#11248)
        "npu_client",  # real-loaded at import time (#12114)
        "npu_profile_suggester",  # real-loaded at import time (#11731)
    }
)


def _real_load_light_services() -> None:
    """#12438: Real-load every light ``services/*.py`` submodule tests import at
    module level, generalizing the one-at-a-time #12114/#11248/#11731 real-loads.

    conftest stubs the whole ``services`` package as a MagicMock, so any
    module-level ``from services.<mod> import ...`` errored collection with
    ``No module named 'services.<mod>'`` even though the file exists on disk.
    ``_real_load_and_bind`` already falls back to a package stub on any import
    failure, so heavy or side-effectful modules stay stubbed automatically — no
    hand-listing needed.  Runs from pytest_configure, after every stub is set.
    """
    services_dir = backend_root / "services"
    for svc_path in sorted(services_dir.glob("*.py")):
        name = svc_path.stem
        if name in _SERVICES_REAL_LOAD_SKIP or name.startswith("test_") or name.endswith(("_test", "_examples")):
            continue
        _real_load_and_bind(f"services.{name}", svc_path)


def pytest_configure(config):  # noqa: ANN001
    """#11248/#11532: real-load lightweight service modules whose unit tests need the
    real helpers, AFTER every module-level stub above is in place.

    These modules import ``autobot_shared.redis_client`` / ``logging_manager`` /
    ``singleton_factory`` at module top — all stubbed/patched during conftest import —
    so they can only be real-loaded once conftest import has fully completed.
    pytest_configure runs after that and before collection, so real symbols
    (LLMApiKeyRecord, MODEL_PRICING, _check_pricing_staleness, …) are in place when
    test modules are imported.  Each overwrites the services-package MagicMock stub.

    #11532: ``services.llm_cost_tracker`` was stubbed at conftest-import time.
    Tests that called ``patch("services.llm_cost_tracker.PRICING_VERSION", ...)``
    were patching the *stub* module object while ``_check_pricing_staleness``
    executed in the *real* module's globals — the patch was completely inert.
    Real-loading here ensures ``sys.modules["services.llm_cost_tracker"]`` is the
    same object as ``_check_pricing_staleness.__globals__`` so patch() is effective.
    """
    # Window 2 of 4 (#13446): these modules import autobot_shared.redis_client at
    # module top — the paragraph above says so — and bind what they find there
    # for the rest of the session.
    _SCOPED_REDIS.enter("configure")
    try:
        _real_load_and_bind("services.llm_api_key_service", backend_root / "services" / "llm_api_key_service.py")
        _real_load_and_bind("services.llm_cost_tracker", backend_root / "services" / "llm_cost_tracker.py")
        _real_load_light_services()
    finally:
        _SCOPED_REDIS.exit("configure")


# #12463: cascade hardening for manually-installed stub modules.
#
# CPython's import machinery already removes a module from ``sys.modules``
# itself when its ``exec_module()`` raises mid-import — a genuinely
# half-built REAL module does NOT persist in the cache, so it does not need
# this hook. What DOES persist and poison later collectors is a module a
# test file installed by hand (e.g. ``sys.modules["x"] = types.ModuleType(...)``
# or ``sys.modules["x"] = MagicMock()``) *before* the surrounding collection
# failed for some other reason — that manual assignment bypasses the normal
# import protocol entirely, so nothing ever cleans it up. The next file that
# needs the real ``x`` gets the abandoned stub instead of a fresh import
# attempt, and fails with a confusing, unrelated-looking error (``cannot
# import name X from Y`` / ``No module named Y.Z``).
#
# This hook does NOT mask the real failure — the file whose collection
# actually failed still reports its own (correct) error via the normal
# CollectReport. It only prevents that failure from poisoning other files'
# imports of the same stub: on a FAILED Module collection, any module newly
# present in sys.modules is evicted ONLY if it looks like a manual/uninitialized
# stub rather than a healthy, fully-imported real module — see
# ``_looks_like_uninitialized_stub`` — so a real module that happened to
# import cleanly earlier in the same (later-failing) file is left alone and
# is not re-executed (double-running its import-time side effects) by a
# subsequent file's fresh import.
#
# Keyed by nodeid (not a plain stack) because ``pytest_collectreport`` fires
# for every collector level (Dir/Package/Module/...), not just Module — a
# stack would pop the wrong snapshot for non-Module reports interleaved
# between a Module's collectstart and its own collectreport.
_module_collect_snapshots: dict = {}


def _looks_like_uninitialized_stub(mod) -> bool:  # noqa: ANN001
    """True if *mod* was never legitimately finished importing.

    A module the real import system completed has a real ``ModuleSpec``
    whose ``_initializing`` flag is ``False`` by the time ``exec_module()``
    returns. A module installed by hand (``sys.modules[name] = MagicMock()``
    / ``types.ModuleType(name)`` never passed through ``exec_module``) either
    has no ``__spec__`` at all or one still flagged ``_initializing`` (import
    machinery normally clears that flag on success; a manual stand-in never
    sets it, so it reads as truthy-missing via ``getattr(..., False)`` — the
    only way this is ``True`` is a bare ``ModuleSpec()`` some hand-rolled
    stub constructed itself, which is exactly the anti-pattern being
    targeted here).
    """
    spec = getattr(mod, "__spec__", None)
    return spec is None or getattr(spec, "_initializing", False)


def pytest_collectstart(collector) -> None:  # noqa: ANN001
    """Snapshot sys.modules before a Module collector imports its file."""
    if type(collector).__name__ == "Module":
        _module_collect_snapshots[collector.nodeid] = set(sys.modules.keys())


def pytest_collectreport(report) -> None:  # noqa: ANN001
    """On a failed Module collection, evict any uninitialized-stub module it left behind."""
    before = _module_collect_snapshots.pop(report.nodeid, None)
    if before is None:
        return
    if report.failed:
        for _name in set(sys.modules.keys()) - before:
            _mod = sys.modules.get(_name)
            if _mod is not None and not _looks_like_uninitialized_stub(_mod):
                continue  # healthy real module — leave it cached, don't re-run its import
            sys.modules.pop(_name, None)


# ---------------------------------------------------------------------------
# Windows 3 and 4 of the redis_client stand-in (#13446)
# ---------------------------------------------------------------------------


@pytest.hookimpl(hookwrapper=True)
def pytest_make_collect_report(collector):  # noqa: ANN001, ANN201
    """Window 3: hold the stand-in around this directory's own module imports.

    Directory-scoped — pytest dispatches this through ``collector.ihook``, so it
    fires only for nodes whose conftest chain includes this file — and it wraps
    exactly ``collector.collect()``, the call in which a ``Module`` node imports
    its test file, and with it every production module that binds
    ``get_async_redis_client`` into its own globals at import time.

    ``pytest_collectstart``/``pytest_collectreport`` cannot serve here:
    ``pytest_collectreport`` never fires for a ``Dir`` or ``Package`` node, so a
    pair keyed on one would install the stand-in and never restore it (#13359).
    """
    holder = f"collect:{collector.nodeid}"
    _SCOPED_REDIS.enter(holder)
    try:
        yield
    finally:
        _SCOPED_REDIS.exit(holder)


def _is_backend_item(item) -> bool:  # noqa: ANN001
    """True when *item* lives under autobot-backend/.

    ``pytest_runtest_protocol`` is NOT directory-scoped, unlike
    ``pytest_make_collect_report``: ``Session.pytest_runtestloop`` dispatches it
    through ``item.config.hook``, the global relay, so a hookwrapper defined in
    any conftest wraps every item in the session (#13359). Without this check
    the stand-in would be live while autobot_shared/'s own Redis tests run.
    """
    path = getattr(item, "path", None)
    return path is not None and backend_root in Path(str(path)).parents


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):  # noqa: ANN001, ANN201
    """Window 4: hold the stand-in for setup, call and teardown of each test here.

    Needed on top of window 3 because several callers import the client lazily
    inside a function — ``config.registry._get_redis()`` does ``from
    autobot_shared.redis_client import get_redis_client`` on every call — so the
    name is resolved when the test runs, not when its module was imported.
    """
    if not _is_backend_item(item):
        yield
        return
    holder = f"run:{item.nodeid}"
    _SCOPED_REDIS.enter(holder)
    try:
        yield
    finally:
        _SCOPED_REDIS.exit(holder)


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ANN001
    """Safety net: never let the stand-in outlive the session.

    Every window restores from a ``finally``, but a ``BaseException`` unwinding
    past pytest's hook machinery (KeyboardInterrupt during collection, a worker
    crash) could still strand the holders set.
    """
    _SCOPED_REDIS.restore_all()
