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

import sys
import types
import uuid  # noqa: F401 — used in fixture helpers below
from datetime import datetime, timezone  # noqa: F401 — used in fixture helpers below
from pathlib import Path
from typing import AsyncGenerator, Dict  # noqa: F401 — used in fixture type hints below
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: F401 — used in fixtures below

import pytest  # noqa: F401 — used for @pytest.fixture decorator below
from httpx import ASGITransport, AsyncClient  # noqa: F401 — used in fixtures below


def _make_knowledge_stub() -> types.ModuleType:
    """Return a thin module stub for the ``knowledge`` package."""
    mod = types.ModuleType("knowledge")
    mod.__path__ = []  # type: ignore[attr-defined]
    mod.__package__ = "knowledge"
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


# The ``knowledge`` module imports lazily but fails when attributes are accessed
# because chromadb → opentelemetry has a broken dependency in the dev venv.
# Unconditionally replace with a stub so every lazy ``from knowledge import X``
# receives our mock instead of triggering the broken chain.
sys.modules["knowledge"] = _make_knowledge_stub()
_make_knowledge_submodule_stubs()


def _make_services_stub() -> types.ModuleType:
    """Return a thin stub for the ``services`` package hierarchy."""
    services_mod = types.ModuleType("services")
    services_mod.__path__ = []  # type: ignore[attr-defined]
    services_mod.__package__ = "services"

    llm_mod = types.ModuleType("services.llm_service")
    llm_mod.__package__ = "services"
    llm_mod.get_llm_service = MagicMock(return_value=MagicMock())  # type: ignore[attr-defined]

    services_mod.llm_service = llm_mod  # type: ignore[attr-defined]
    sys.modules["services"] = services_mod
    sys.modules["services.llm_service"] = llm_mod
    return services_mod


def _make_agents_stub() -> None:
    """Stub the ``agents`` package to avoid the knowledge/chromadb import chain.

    ``autobot_agent_adapter`` imports ``from agents.base_agent import AgentRequest``
    at module level.  Loading ``agents/__init__.py`` eagerly pulls in
    ``kb_librarian_agent`` → ``knowledge_base`` → ``knowledge`` → chromadb chain.
    We short-circuit that by pre-populating sys.modules before any test module
    triggers the import.
    """
    agents_mod = types.ModuleType("agents")
    agents_mod.__path__ = []  # type: ignore[attr-defined]
    agents_mod.__package__ = "agents"
    sys.modules["agents"] = agents_mod

    agents_base = types.ModuleType("agents.base_agent")
    agents_base.AgentRequest = MagicMock  # type: ignore[attr-defined]
    agents_base.AgentResponse = MagicMock  # type: ignore[attr-defined]
    sys.modules["agents.base_agent"] = agents_base


# ``services.llm_service`` is imported at module level by llc/kb/handoff_brief.py
# (merged to Dev_new_gui after issue-8238).  Stub it so the test collection
# phase does not fail when the full service stack is absent.
_make_services_stub()

# ``agents.base_agent`` is imported by autobot_agent_adapter (GH#8502).
# Stub it before any test module can trigger the agents/__init__.py chain.
_make_agents_stub()


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
    return proj


def _make_fake_code_source(source_id: str = _FAKE_SOURCE_ID, repo: str = _FAKE_SOURCE_REPO) -> MagicMock:
    """Return a MagicMock resembling a CodeSource."""
    src = MagicMock()
    src.id = source_id
    src.repo = repo
    src.branch = "main"
    src.clone_path = f"/opt/autobot/data/code-sources/{source_id}/"
    src.status = "configured"
    src.error_message = None
    return src


def _build_llc_app(
    org_id: uuid.UUID,
    project: MagicMock | None,
    project_with_repo: MagicMock | None,
):
    """Build a FastAPI app wired to the sprints router with mocked dependencies."""
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from fastapi import FastAPI  # noqa: PLC0415
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
        froms = (
            stmt.get_final_froms() if hasattr(stmt, "get_final_froms") else (getattr(stmt, "froms", None) or [])
        )
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
