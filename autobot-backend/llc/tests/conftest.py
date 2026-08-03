# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC tests conftest — stubs heavy optional dependencies for unit tests.

The ``knowledge`` module (and its chromadb/opentelemetry chain) is not
importable in the dev/CI environment.  We install a lightweight sys.modules
stub so that any test module that lazily imports ``knowledge.get_knowledge_base``
receives a safe AsyncMock instead of an ImportError.

Tests that need specific behaviour override it with ``patch("knowledge.get_knowledge_base")``.

Fixtures for project-repo API tests (#11129):
  llc_client         — AsyncClient wired to the sprints router with auth/org overrides
  a_project          — dict with ``id``/``company_id`` of a mock project (no source)
  a_project_with_repo — dict with ``id``/``company_id`` of a mock project already linked
"""

import importlib
import sys
import types
import uuid  # noqa: F401 — used in fixture helpers below
from datetime import datetime, timezone  # noqa: F401 — used in fixture helpers below
from pathlib import Path
from typing import AsyncGenerator, Dict  # noqa: F401 — used in fixture type hints below
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: F401 — used in fixtures below

import pytest  # noqa: F401 — used for @pytest.fixture decorator below
from httpx import ASGITransport, AsyncClient  # noqa: F401 — used in fixtures below

# #13084: real-load the in-memory adapter classes BEFORE ``knowledge`` is
# stubbed below. They are dependency-light (no chromadb import at module
# level — verified: only ``get_default_client``/``get_async_default_client``
# lazily import the chromadb chain), so importing them here is safe and lets
# the ``knowledge.backends`` stub re-export the REAL classes instead of
# omitting them, which previously shadowed the real
# ``knowledge.backends.InMemoryClient`` for any test collected afterward in
# the same session (see _make_knowledge_submodule_stubs).
from knowledge.backends.async_memory_adapter import (  # noqa: E402
    AsyncInMemoryClient,
    AsyncInMemoryCollection,
)
from knowledge.backends.memory_adapter import (  # noqa: E402
    InMemoryClient,
    InMemoryCollection,
)

_SESSION_STUB_KEYS = (
    "knowledge",
    "knowledge.embedding_cache",
    "knowledge.utils",
    "agents",
    "agents.base_agent",
)


def _snapshot_session_stub_keys() -> dict:
    """Capture the pre-stub sys.modules state for every key this file stubs.

    Issue #13084: these stubs were previously installed unconditionally at
    module import time with no restore, so once ``llc/tests/`` was collected
    in a full-suite run they permanently shadowed the REAL ``knowledge``/
    ``services``/``agents`` packages for the rest of the session — breaking
    genuine consumers collected later (e.g.
    ``services/research/quarantine_boundary_test.py``'s
    ``from knowledge.backends import InMemoryClient``, which fails only in a
    full run, never in isolation). ``None`` means the key was absent before
    this file ran.
    """
    return {key: sys.modules.get(key) for key in _SESSION_STUB_KEYS}


# #13107: __file__ = .../autobot-backend/llc/tests/conftest.py → parents[2]
# = .../autobot-backend, matching the same on-disk-path derivation already
# used by _shield_codebase_analytics_package below.
_KNOWLEDGE_DIR = str(Path(__file__).parents[2] / "knowledge")
_AGENTS_DIR = str(Path(__file__).parents[2] / "agents")


def _make_knowledge_stub() -> types.ModuleType:
    """Return a thin module stub for the ``knowledge`` package.

    #13107: ``__path__`` points at the REAL on-disk ``knowledge/`` directory
    instead of ``[]`` — the "hollow package" pattern already used for
    ``api`` in ``autobot-slm-backend/conftest.py`` and for
    ``api.codebase_analytics`` later in this same file. Python's import
    machinery uses ``__path__`` only to locate a submodule NOT already
    present in ``sys.modules``, so submodules this file explicitly stubs
    (``knowledge.embedding_cache``, ``knowledge.utils``,
    ``knowledge.backends`` — see ``_make_knowledge_submodule_stubs``) are
    unaffected: their ``sys.modules`` entry is found first and wins.

    An empty ``__path__`` previously blocked EVERY other real
    ``knowledge.X`` submodule too, not just the ones this file omits —
    e.g. ``knowledge.facts`` — breaking any test collected afterward in the
    same session that needs one (reproduced via
    ``services/research/quarantine_boundary_test.py``). ``knowledge/*``
    mixin modules (``facts.py``, ``documents.py``, etc.) do not import
    chromadb/llama_index at module level — only ``knowledge/_composed.py``
    does, and it is reached exclusively via ``knowledge/__init__.py``'s
    PEP 562 ``__getattr__``, which this stub module never defines, so
    resolving a real submodule here can never trigger the heavy chain.
    """
    mod = types.ModuleType("knowledge")
    mod.__path__ = [_KNOWLEDGE_DIR]  # type: ignore[attr-defined]
    mod.__package__ = "knowledge"
    mod.__spec__ = None  # type: ignore[attr-defined]
    mod.get_knowledge_base = AsyncMock(return_value=MagicMock())
    mod.KnowledgeBase = MagicMock  # type: ignore[attr-defined]
    return mod


def _make_knowledge_submodule_stubs() -> None:
    """Stub knowledge sub-packages imported by knowledge_base.py."""
    ec = types.ModuleType("knowledge.embedding_cache")
    ec.EmbeddingCache = MagicMock  # type: ignore[attr-defined]
    ec.get_embedding_cache = AsyncMock(return_value=MagicMock())  # type: ignore[attr-defined]
    sys.modules["knowledge.embedding_cache"] = ec

    ku = types.ModuleType("knowledge.utils")
    ku.sanitize_metadata_for_chromadb = MagicMock(return_value={})  # type: ignore[attr-defined]
    sys.modules["knowledge.utils"] = ku

    # codebase_analytics/storage.py does ``from knowledge.backends import
    # get_async_default_client, get_default_client`` at module level. Without a
    # backends stub, the bare ``knowledge`` stub above shadows the real package and
    # any cross-suite run (llc tests collected before analytics tests) fails to
    # collect them with ModuleNotFoundError: No module named 'knowledge.backends' (#11256).
    #
    # #13084: only ``get_default_client``/``get_async_default_client`` need
    # mocking (they lazily import the heavy chromadb chain). The in-memory
    # adapter classes (real-loaded at module top, before ``knowledge`` is
    # stubbed) are a REAL, separate consumer's public API — a previous
    # version of this stub omitted them, which silently shadowed the real
    # ``knowledge.backends.InMemoryClient`` for any test collected afterward
    # in the same session (reproduced via
    # ``services/research/quarantine_boundary_test.py``, which fails only in
    # a full-suite run, never in isolation, because collection-time imports
    # happen before any fixture teardown could restore this stub). Re-exporting
    # the real classes here means no restore is even needed for this key.
    kb = types.ModuleType("knowledge.backends")
    kb.get_default_client = MagicMock(return_value=MagicMock())  # type: ignore[attr-defined]
    kb.get_async_default_client = AsyncMock(return_value=MagicMock())  # type: ignore[attr-defined]
    kb.InMemoryClient = InMemoryClient  # type: ignore[attr-defined]
    kb.InMemoryCollection = InMemoryCollection  # type: ignore[attr-defined]
    kb.AsyncInMemoryClient = AsyncInMemoryClient  # type: ignore[attr-defined]
    kb.AsyncInMemoryCollection = AsyncInMemoryCollection  # type: ignore[attr-defined]
    sys.modules["knowledge.backends"] = kb


# #13084: snapshot BEFORE stubbing so the package-scoped fixture below can
# restore these exact keys once every test under llc/tests/ has run — the
# stub is required for this package's own collection/tests but must not
# outlive it (see _snapshot_session_stub_keys docstring).
_PRE_STUB_MODULES = _snapshot_session_stub_keys()

# The ``knowledge`` module imports lazily but fails when attributes are accessed
# because chromadb → opentelemetry has a broken dependency in the dev venv.
# Unconditionally replace with a stub so every lazy ``from knowledge import X``
# receives our mock instead of triggering the broken chain.
sys.modules["knowledge"] = _make_knowledge_stub()
_make_knowledge_submodule_stubs()


def _make_services_stub() -> types.ModuleType:
    """Return a thin stub for the ``services`` package hierarchy.

    #12463: guarded per-name so this never *unconditionally* overwrites a
    module the root ``autobot-backend/conftest.py`` already set up. That
    root conftest stubs ``services``/``services.llm_service`` with a real
    on-disk ``__path__`` plus a catch-all ``__getattr__`` fallback (so
    ``services.mesh_brain`` / ``services.agents`` / any attribute resolves),
    and real-loads ``services.slm_client`` from disk in ``pytest_configure``
    (giving it ``_SERVICE_JWT_TTL_HOURS`` etc). Blindly replacing those with
    this file's narrower stand-ins — which lack the catch-all and the real
    ``__path__`` — poisoned ``sys.modules`` for the rest of the pytest
    session: every later-collected file needing an attribute or submodule
    not on this file's short hand list failed with a confusing, unrelated-
    looking ``ImportError``/``ModuleNotFoundError``.

    The parent-package bind (``services_mod.llm_service = ...``) below is
    still required EVERY time, even when reusing an already-present
    ``sys.modules`` entry: ``unittest.mock.patch("services.llm_service.X")``
    resolves the dotted path via ``getattr(sys.modules["services"],
    "llm_service")`` — NOT via ``sys.modules["services.llm_service"]``
    directly (mirrors the root conftest's own ``_real_load_and_bind`` /
    #11532 note). The root conftest's stub loop never does this bind for
    ``services.llm_service``, so skipping it here left ``patch()`` silently
    resolving the *package's* generic catch-all mock instead of the real
    submodule — an inert patch (#12463).
    """
    if "services" not in sys.modules:
        services_mod = types.ModuleType("services")
        services_mod.__path__ = []  # type: ignore[attr-defined]
        services_mod.__package__ = "services"
        sys.modules["services"] = services_mod
    services_mod = sys.modules["services"]

    if "services.llm_service" not in sys.modules:
        llm_mod = types.ModuleType("services.llm_service")
        llm_mod.__package__ = "services"
        llm_mod.get_llm_service = MagicMock(return_value=MagicMock())  # type: ignore[attr-defined]
        sys.modules["services.llm_service"] = llm_mod
    services_mod.llm_service = sys.modules["services.llm_service"]  # type: ignore[attr-defined]

    if "services.slm_client" not in sys.modules:
        slm_mod = types.ModuleType("services.slm_client")
        slm_mod.__package__ = "services"
        slm_mod.get_slm_client = MagicMock(return_value=None)  # type: ignore[attr-defined]
        sys.modules["services.slm_client"] = slm_mod
    services_mod.slm_client = sys.modules["services.slm_client"]  # type: ignore[attr-defined]

    return services_mod


def _make_agents_stub() -> None:
    """Register a hollow ``agents`` package that never runs ``__init__.py``.

    ``autobot_agent_adapter`` imports ``from agents.base_agent import AgentRequest``
    at module level.  Loading ``agents/__init__.py`` eagerly pulls in
    ``kb_librarian_agent`` → ``knowledge_base`` → ``knowledge`` → chromadb chain.
    We short-circuit that by pre-populating sys.modules before any test module
    triggers the import.

    ``__path__`` points at the REAL on-disk ``agents/`` directory — the same
    "hollow package" pattern already used for ``knowledge`` above (#13107) and
    for ``api.codebase_analytics`` below.  Python consults ``__path__`` only to
    locate a submodule that is not already in ``sys.modules``, and it never
    executes the parent's ``__init__.py`` for a package object that is already
    registered, so the heavy chain stays untouched while every real
    ``agents.X`` submodule remains importable.

    An empty ``__path__`` blocked every other real submodule too — notably
    ``agents.agent_client``, which ``autobot-backend/orchestrator.py`` imports
    at module level.  Because collection-time imports all happen before any
    fixture teardown could restore the pre-stub state, that shadowing broke
    *collection* of files gathered after this package in the same session
    (reproduced: ``orchestration/plan_steps_e2e_test.py`` fails with
    ``ModuleNotFoundError: No module named 'agents.agent_client'`` in a
    combined run, never in isolation) — #13162.

    ``agents/base_agent.py`` is dependency-light (autobot_shared + constants +
    protocols, no knowledge/chromadb import at module level), so it is
    real-loaded through the same ``__path__`` rather than replaced by a mock:
    ``agents/agent_client.py`` does ``from .base_agent import AgentHealth,
    BaseAgent, ...``, names a hand-written stub module did not carry.
    """
    agents_mod = types.ModuleType("agents")
    agents_mod.__path__ = [_AGENTS_DIR]  # type: ignore[attr-defined]
    agents_mod.__package__ = "agents"
    agents_mod.__spec__ = None  # type: ignore[attr-defined]
    sys.modules["agents"] = agents_mod

    importlib.import_module("agents.base_agent")


# ``services.llm_service`` is imported at module level by llc/kb/handoff_brief.py
# (merged to Dev_new_gui after issue-8238).  Stub it so the test collection
# phase does not fail when the full service stack is absent.
_make_services_stub()

# ``agents.base_agent`` is imported by autobot_agent_adapter (GH#8502).
# Stub it before any test module can trigger the agents/__init__.py chain.
_make_agents_stub()

# Everything this file installs, captured once so the package-scoped fixture
# below can RE-install it on every entry into this package — not just remove it
# on the way out (#13162). CI runs ``-n auto --dist loadscope``, which groups by
# module, not by package: a worker interleaves llc/tests modules with modules
# from elsewhere, so the package fixture tears down and sets up repeatedly. The
# installs above run once, at import time, so a teardown that only restored the
# pre-stub state left every LATER llc/tests module running against the REAL
# ``knowledge`` package (reproduced by ordering test_heartbeat_context.py,
# knowledge/pipeline/cognifiers/cognifiers_test.py, test_sprint_close.py in one
# run: ``test_kb_summarizer_stub_is_called`` then tries to reach a live Redis
# and fails with "Failed to initialize knowledge base").
_INSTALLED_STUBS = {key: sys.modules[key] for key in _SESSION_STUB_KEYS if key in sys.modules}


def _shield_codebase_analytics_package() -> None:
    """Register a lightweight package stub for api.codebase_analytics in sys.modules.

    Problem: api/codebase_analytics/__init__.py eagerly imports routes.py which
    chains through tasks/__init__.py → services.audit.audit — a path broken by
    the services stub above.  Any test that does
    ``from api.codebase_analytics import source_service`` or
    ``from api.codebase_analytics.source_models import SourceType``
    would trigger __init__.py and explode.

    Fix: register a package stub whose __path__ points to the real on-disk
    directory.  Python's import machinery uses __path__ to locate submodules on
    the filesystem, so ``from api.codebase_analytics.source_models import SourceType``
    loads the REAL source_models.py without ever executing __init__.py.  The heavy
    router/tasks chain is never touched.

    The stub is intentionally minimal (no attributes from __init__.py's __all__).
    The llc_client fixture installs per-test stubs for source_service and
    source_storage on top of this, and removes them at teardown so the real
    submodules remain available when analytics tests run afterward.
    """
    if "api.codebase_analytics" in sys.modules:
        return  # real package already loaded — leave it intact
    # __file__ = .../autobot-backend/llc/tests/conftest.py → parents[2] = .../autobot-backend
    _pkg_dir = Path(__file__).parents[2] / "api" / "codebase_analytics"
    pkg = types.ModuleType("api.codebase_analytics")
    pkg.__path__ = [str(_pkg_dir)]  # type: ignore[attr-defined]
    pkg.__package__ = "api.codebase_analytics"
    sys.modules["api.codebase_analytics"] = pkg
    # Expose as an attribute on the parent ``api`` package so that
    # ``mock.patch("api.codebase_analytics.<submodule>.<attr>")`` — whose dotted
    # lookup runs ``getattr(api, "codebase_analytics")`` — resolves to this shield
    # (#11129 P2). Without it, patching a lazily-imported analytics helper raises
    # ``AttributeError: module 'api' has no attribute 'codebase_analytics'``.
    importlib.import_module("api").codebase_analytics = pkg  # type: ignore[attr-defined]


_shield_codebase_analytics_package()


# ---------------------------------------------------------------------------
# Scoped stubs for the two functions LLC route-handlers call lazily (#11129)
# ---------------------------------------------------------------------------

_LLC_ANALYTICS_STUB_KEYS = (
    "api.codebase_analytics.source_service",
    "api.codebase_analytics.source_storage",
)


def _install_source_stubs(fake_create: AsyncMock, fake_get: AsyncMock) -> dict:
    """Install thin stubs for source_service and source_storage submodules.

    Returns a snapshot mapping each key to its previous sys.modules value
    (None if absent) so _remove_source_stubs can restore exactly the prior state.

    Only source_service and source_storage are stubbed.  source_models is never
    touched — the real module is always importable and analytics tests import
    SourceType from it.  The package stub installed by _shield_codebase_analytics_package
    already allows submodule lookup without running __init__.py.
    """
    snapshot = {k: sys.modules.get(k) for k in _LLC_ANALYTICS_STUB_KEYS}

    src_svc = types.ModuleType("api.codebase_analytics.source_service")
    src_svc.create_github_source = fake_create  # type: ignore[attr-defined]
    sys.modules["api.codebase_analytics.source_service"] = src_svc

    src_storage = types.ModuleType("api.codebase_analytics.source_storage")
    src_storage.get_source = fake_get  # type: ignore[attr-defined]
    src_storage.delete_source = AsyncMock()  # type: ignore[attr-defined]
    sys.modules["api.codebase_analytics.source_storage"] = src_storage

    # Keep the package-level reference in sync so
    # ``from api.codebase_analytics import source_service`` resolves to the stub.
    pkg = sys.modules["api.codebase_analytics"]
    pkg.source_service = src_svc  # type: ignore[attr-defined]
    pkg.source_storage = src_storage  # type: ignore[attr-defined]

    return snapshot


def _remove_source_stubs(snapshot: dict) -> None:
    """Restore sys.modules to the state captured by _install_source_stubs.

    Entries that were absent before the test are deleted (not kept as stubs)
    so that subsequent test files (e.g. analytics tests) import the real modules.
    Also cleans up the package-level aliases installed by _install_source_stubs.
    """
    for key, prior in snapshot.items():
        if prior is None:
            sys.modules.pop(key, None)
        else:
            sys.modules[key] = prior

    pkg = sys.modules.get("api.codebase_analytics")
    if pkg is not None:
        pkg.__dict__.pop("source_service", None)  # type: ignore[union-attr]
        pkg.__dict__.pop("source_storage", None)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Project-repo API fixtures (#11129)
# ---------------------------------------------------------------------------

_FIXED_ORG_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_FIXED_USER_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_FAKE_SOURCE_ID = "src-test-0001"
_FAKE_SOURCE_REPO = "acme/site"


def _make_mock_project(company_id: uuid.UUID, code_source_id: str | None = None) -> MagicMock:
    """Return a MagicMock that satisfies LLCProject attribute access.

    All attributes that appear in ProjectResponse must be set explicitly to prevent
    MagicMock from auto-creating non-None MagicMock objects that fail Pydantic validation.
    """
    proj = MagicMock()
    proj.id = uuid.uuid4()
    proj.company_id = company_id
    proj.program_id = None
    proj.goal_id = None
    proj.name = "Test Project"
    proj.description = None
    proj.status = "backlog"
    proj.lead_agent_id = None
    proj.lead_user_id = None
    proj.target_date = None
    proj.auto_rollover = None
    proj.code_source_id = code_source_id
    proj.code_source = None  # Optional field — must be None not a MagicMock
    proj.active_sprint_name = None  # Optional[str] — must be None not a MagicMock
    proj.open_work_item_count = 0
    proj.created_at = datetime.now(timezone.utc)
    proj.updated_at = datetime.now(timezone.utc)
    # Pin lifecycle fields (#11129 P2) so model_validate doesn't auto-vivify Mocks.
    proj.lifecycle_state = "active"
    proj.archived_at = None
    proj.disposal_scheduled_at = None
    proj.disposal_approval_id = None
    return proj


def _make_fake_code_source(source_id: str = _FAKE_SOURCE_ID, repo: str = _FAKE_SOURCE_REPO) -> MagicMock:
    """Return a MagicMock resembling a CodeSource."""
    from api.codebase_analytics.source_models import SourceStatus  # noqa: PLC0415

    src = MagicMock()
    src.id = source_id
    src.repo = repo
    src.branch = "main"
    src.clone_path = f"/opt/autobot/data/code-sources/{source_id}/"
    src.status = SourceStatus.CONFIGURED  # use enum so .value works in _project_source_summary
    src.error_message = None
    return src


def _build_llc_app(
    org_id: uuid.UUID,
    project: MagicMock | None,
    project_with_repo: MagicMock | None,
):
    """Build a FastAPI app wired to the sprints router with mocked dependencies."""
    from fastapi import FastAPI  # noqa: PLC0415

    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.sprints import router as sprints_router  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415
    from user_management.services import TenantContext  # noqa: PLC0415

    app = FastAPI()
    app.include_router(sprints_router, prefix="/api/llc")

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.delete = AsyncMock()
    mock_session.add = MagicMock()

    # Collect all known projects so execute() can route correctly.
    all_projects_by_id: Dict[uuid.UUID, MagicMock] = {}
    projects_with_repo = []
    if project is not None:
        all_projects_by_id[project.id] = project
    if project_with_repo is not None:
        all_projects_by_id[project_with_repo.id] = project_with_repo
        projects_with_repo.append(project_with_repo)

    async def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        froms = stmt.get_final_froms() if hasattr(stmt, "get_final_froms") else (getattr(stmt, "froms", None) or [])
        entity = None
        is_list = False
        if froms:
            tbl = froms[0]
            name = getattr(tbl, "name", "") or getattr(tbl, "__tablename__", "")
            if "project" in name:
                stmt_str = str(stmt)
                # with-repos list query: filtering by code_source_id IS NOT NULL
                if "IS NOT NULL" in stmt_str and "code_source_id" in stmt_str:
                    is_list = True
                    entity = projects_with_repo
                else:
                    # Single-entity lookup: extract the bound param UUIDs and match.
                    try:
                        params = stmt.compile().params
                        param_uuids = {str(v) for v in params.values()}
                    except Exception:
                        param_uuids = set()
                    matched = None
                    for pid, proj in all_projects_by_id.items():
                        if str(pid) in param_uuids:
                            matched = proj
                            break
                    entity = matched  # None when UUID not in known set → 404

        if is_list:
            scalars_mock = MagicMock()
            scalars_mock.all = MagicMock(return_value=entity or [])
            result.scalars = MagicMock(return_value=scalars_mock)
        else:
            result.scalar_one_or_none = MagicMock(return_value=entity)
            scalars_mock = MagicMock()
            scalars_mock.all = MagicMock(return_value=list(all_projects_by_id.values()))
            result.scalars = MagicMock(return_value=scalars_mock)
        return result

    mock_session.execute = _execute

    async def _fake_refresh(obj, *a, **kw):
        # After commit, the ORM row should already have all fields set by the handler.
        pass

    mock_session.refresh = _fake_refresh

    async def _fake_session():
        yield mock_session

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_FIXED_USER_ID), "user_id": str(_FIXED_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=org_id, user_id=_FIXED_USER_ID, is_platform_admin=False
    )

    _patch_kb = patch("llc.kb.collections.KbCollectionManager.ensure_collection", new=AsyncMock(return_value=None))
    _patch_kb.start()

    return app, _patch_kb


@pytest.fixture(scope="package", autouse=True)
def _restore_session_stubs_after_package():
    """Install the module-level ``knowledge``/``agents`` stubs for the lifetime
    of this package, and restore the pre-stub state afterwards (#13084/#13162).

    The stubs installed above at import time are required for llc/tests/
    itself to collect (chromadb/opentelemetry are unavailable in dev/CI), but
    were previously left in ``sys.modules`` for the rest of the pytest
    session with no restore — shadowing the REAL ``knowledge.backends``
    package for any test collected afterward in the same worker (reproduced:
    ``services/research/quarantine_boundary_test.py``'s
    ``from knowledge.backends import InMemoryClient`` fails only in a
    full-suite run, never in isolation). Restoring here — rather than a
    session-scoped hook — ties the fix to exactly the lifetime that needs
    the stub.

    Setup re-installs rather than assuming the import-time install is still in
    place: with ``--dist loadscope`` this fixture is entered once per contiguous
    run of llc/tests modules, so on every entry after the first the previous
    teardown has already handed ``sys.modules`` back to the real packages.
    """
    for key, stub in _INSTALLED_STUBS.items():
        sys.modules[key] = stub
    yield
    for key, prior in _PRE_STUB_MODULES.items():
        if prior is None:
            sys.modules.pop(key, None)
        else:
            sys.modules[key] = prior


@pytest.fixture
async def llc_client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client wired to the sprints router; patches CodeSource calls.

    Installs thin stubs for source_service.create_github_source and
    source_storage.get_source for the duration of each test, then removes them
    on teardown.  Removal (rather than leaving stubs in sys.modules forever)
    ensures that analytics test files collected later in the same pytest session
    always import the real api.codebase_analytics submodules.
    """
    org = _FIXED_ORG_ID
    project = _make_mock_project(org)
    project_with_repo = _make_mock_project(org, code_source_id=_FAKE_SOURCE_ID)
    fake_src = _make_fake_code_source()

    fake_create = AsyncMock(return_value=fake_src)
    fake_get = AsyncMock(return_value=fake_src)

    snapshot = _install_source_stubs(fake_create, fake_get)
    app, _patch_kb = _build_llc_app(org, project, project_with_repo)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Stash references so the project fixtures can read them.
            client._test_project = project  # type: ignore[attr-defined]
            client._test_project_with_repo = project_with_repo  # type: ignore[attr-defined]
            yield client
    finally:
        _patch_kb.stop()
        _remove_source_stubs(snapshot)


@pytest.fixture
async def a_project(llc_client: AsyncClient) -> Dict:
    """Return a dict representation of the test project (no repo attached)."""
    proj = llc_client._test_project  # type: ignore[attr-defined]
    return {"id": proj.id, "company_id": proj.company_id}


@pytest.fixture
async def a_project_with_repo(llc_client: AsyncClient) -> Dict:
    """Return a dict representation of the test project that already has a repo linked."""
    proj = llc_client._test_project_with_repo  # type: ignore[attr-defined]
    return {"id": proj.id, "company_id": proj.company_id}
