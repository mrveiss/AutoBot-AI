"""
AutoBot User Backend - Test Configuration
Provides pytest fixtures for colocated tests.

Issue: #734 - Colocate tests with source files
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss
"""

import asyncio
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
    sys.modules[name] = mod
    return mod


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
        sys.modules[_svc_mod] = _svc_stub
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

    # Load llm_shared.types (enums only) so models.py can do `from .types import`
    import importlib.util as _ilu2

    def _load_llm_sub(name: str, filename: str) -> None:
        """Load a llm_shared sub-module from its actual source file."""
        _spec = _ilu2.spec_from_file_location(name, str(backend_root / "llm_shared" / filename))
        if _spec and _spec.loader:
            _mod = _ilu2.module_from_spec(_spec)
            _mod.__package__ = "llm_shared"
            sys.modules[name] = _mod
            _spec.loader.exec_module(_mod)  # type: ignore[union-attr]

    try:
        _load_llm_sub("llm_shared.types", "types.py")
    except Exception:
        sys.modules["llm_shared.types"] = _make_pkg_stub("llm_shared.types")

    # Load llm_shared.models from its actual source file so that LLMRequest
    # and LLMResponse are real instantiatable dataclasses (tests call them).
    try:
        _load_llm_sub("llm_shared.models", "models.py")
    except Exception as _models_exc:
        # Fall back to a MagicMock stub if models.py has import issues
        _models_stub = _make_pkg_stub("llm_shared.models")
        _models_stub.LLMRequest = MagicMock()  # type: ignore[attr-defined]
        _models_stub.LLMResponse = MagicMock()  # type: ignore[attr-defined]
        _models_stub.ChatMessage = MagicMock()  # type: ignore[attr-defined]
        _models_stub.LLMSettings = MagicMock()  # type: ignore[attr-defined]
        sys.modules["llm_shared.models"] = _models_stub

    # Load llm_shared.semantic_cache (Issue #8168) — pure Python + numpy,
    # no heavy deps at import time.
    try:
        _load_llm_sub("llm_shared.semantic_cache", "semantic_cache.py")
        _sc_mod = sys.modules.get("llm_shared.semantic_cache")
        if _sc_mod and hasattr(_sc_mod, "SemanticLLMCache"):
            _llm_stub.SemanticLLMCache = _sc_mod.SemanticLLMCache  # type: ignore[attr-defined]
    except Exception:
        _llm_stub.SemanticLLMCache = MagicMock()  # type: ignore[attr-defined]
        sys.modules["llm_shared.semantic_cache"] = _make_pkg_stub("llm_shared.semantic_cache")

# auth_middleware stub — the real module pulls in the full config/Redis chain
# at import time (config.manager, error_catalog, etc.) which fails in the dev
# venv.  Tests that exercise openai_compat patch _get_user directly and never
# call get_current_user, so a lightweight stub is safe here.
if "auth_middleware" not in sys.modules:
    _auth_stub = types.ModuleType("auth_middleware")
    _auth_stub.__path__ = []  # type: ignore[attr-defined]
    _auth_stub.__package__ = "auth_middleware"
    _auth_stub.get_current_user = MagicMock()  # type: ignore[attr-defined]
    _auth_stub.__getattr__ = lambda attr: MagicMock()  # type: ignore[attr-defined]
    sys.modules["auth_middleware"] = _auth_stub

# autobot_shared.redis_client stub — provides get_async_redis_client as a
# proper coroutine returning None so that rate-limiters and other callers that
# do ``redis = await get_async_redis_client()`` fall back to in-process logic
# instead of awaiting a MagicMock (which raises TypeError).
if "autobot_shared.redis_client" not in sys.modules:
    import asyncio as _asyncio_stub

    _redis_client_mod = types.ModuleType("autobot_shared.redis_client")

    async def _get_async_redis_client_stub(*_a, **_k):
        return None

    _redis_client_mod.get_async_redis_client = _get_async_redis_client_stub  # type: ignore[attr-defined]
    _redis_client_mod.__getattr__ = lambda attr: MagicMock()  # type: ignore[attr-defined]
    sys.modules["autobot_shared.redis_client"] = _redis_client_mod

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
# which cascades through agent_loop → tools → code_intelligence — a chain of
# modules with Python-3.10-incompatible annotations or missing config keys.
# Stub these modules so the lightweight types-only tests (workflow_planning_test,
# workflow_integration_test) can collect without needing the full backend stack.
for _causal_mod in [
    "orchestration.causal_error_recovery",
    "orchestration.causal_error_analyzer",
    "orchestration.causal_validator",
    "agent_loop",
    "agent_loop.loop",
    "agent_loop.think_tool",
    "tools.parallel",
    "tools.parallel.executor",
    "code_intelligence",
]:
    if _causal_mod not in sys.modules:
        sys.modules[_causal_mod] = _make_pkg_stub(_causal_mod)

# code_intelligence submodule stubs — code_intelligence itself is stubbed above
# (its __init__ has Python-3.10-incompatible annotations), so submodule imports
# from api/*.py need their own stubs with the right symbol names.
_ci_anti_stub = _make_pkg_stub("code_intelligence.anti_pattern_detector")
_ci_anti_stub.AntiPatternDetector = MagicMock()  # type: ignore[attr-defined]
_ci_anti_stub.AntiPatternSeverity = MagicMock()  # type: ignore[attr-defined]
_ci_anti_stub.AntiPatternResult = MagicMock()  # type: ignore[attr-defined]
sys.modules["code_intelligence.anti_pattern_detector"] = _ci_anti_stub

_ci_merge_stub = _make_pkg_stub("code_intelligence.merge_conflict_resolver")
_ci_merge_stub.ConflictBlock = MagicMock()  # type: ignore[attr-defined]
_ci_merge_stub.ConflictParser = MagicMock()  # type: ignore[attr-defined]
_ci_merge_stub.ConflictSeverity = MagicMock()  # type: ignore[attr-defined]
_ci_merge_stub.MergeConflictResolver = MagicMock()  # type: ignore[attr-defined]
_ci_merge_stub.ResolutionStrategy = MagicMock()  # type: ignore[attr-defined]
_ci_merge_stub.analyze_repository = MagicMock()  # type: ignore[attr-defined]
sys.modules["code_intelligence.merge_conflict_resolver"] = _ci_merge_stub

for _ci_sub in [
    "code_intelligence.performance_analyzer",
    "code_intelligence.redis_optimizer",
    "code_intelligence.security_analyzer",
    "code_intelligence.code_evolution_miner",
    "code_intelligence.bug_predictor",
    "code_intelligence.llm_pattern_analyzer",
    "code_intelligence.log_pattern_miner",
    "code_intelligence.multi_language_scanner",
    "code_intelligence.pattern_analysis",
    "code_intelligence.precommit_analyzer",
    "code_intelligence.shell_analyzer",
    "code_intelligence.test_pattern_analyzer",
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

# Ensure CausalErrorRecovery / RecoveryPlan / get_recovery_recommender are
# resolvable from the stub so orchestration/__init__.py's wildcard import
# (`from .causal_error_recovery import CausalErrorRecovery, ...`) succeeds.
_cer_stub = sys.modules.get("orchestration.causal_error_recovery") or _make_pkg_stub(
    "orchestration.causal_error_recovery"
)
_cer_stub.CausalErrorRecovery = MagicMock()  # type: ignore[attr-defined]
_cer_stub.RecoveryPlan = MagicMock()  # type: ignore[attr-defined]
_cer_stub.get_recovery_recommender = MagicMock()  # type: ignore[attr-defined]
sys.modules["orchestration.causal_error_recovery"] = _cer_stub

_cea_stub = sys.modules.get("orchestration.causal_error_analyzer") or _make_pkg_stub(
    "orchestration.causal_error_analyzer"
)
_cea_stub.CausalErrorAnalysis = MagicMock()  # type: ignore[attr-defined]
sys.modules["orchestration.causal_error_analyzer"] = _cea_stub

_al_stub = sys.modules.get("agent_loop") or _make_pkg_stub("agent_loop")
_al_stub.AgentLoop = MagicMock()  # type: ignore[attr-defined]
sys.modules["agent_loop"] = _al_stub
sys.modules.setdefault("agent_loop.loop", _make_pkg_stub("agent_loop.loop"))
sys.modules.setdefault("agent_loop.think_tool", _make_pkg_stub("agent_loop.think_tool"))

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
    import importlib.util as _ilu

    _infra_path = str(backend_root / "models" / "infrastructure.py")
    _spec = _ilu.spec_from_file_location("models.infrastructure", _infra_path)
    if _spec and _spec.loader:
        # Create a lightweight 'models' namespace package to hold the sub-module
        _models_pkg = _make_pkg_stub("models")
        _models_pkg.__path__ = [str(backend_root / "models")]
        _infra_mod = _ilu.module_from_spec(_spec)
        _infra_mod.__package__ = "models"
        sys.modules["models.infrastructure"] = _infra_mod
        _spec.loader.exec_module(_infra_mod)  # type: ignore[union-attr]
        setattr(_models_pkg, "infrastructure", _infra_mod)


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
