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


def _make_codebase_analytics_stubs() -> None:
    """Stub api.codebase_analytics so the LLC tests never touch its heavy __init__.

    ``api/codebase_analytics/__init__.py`` imports ``storage.py`` which pulls in
    ``knowledge.backends`` — unavailable in the unit-test venv.  We pre-populate
    sys.modules with thin stubs that expose only what the LLC repo-attach endpoints
    need (``source_service.create_github_source`` and ``source_storage.get_source``).
    The real functions are replaced by AsyncMock in each test fixture.
    """
    # knowledge.backends — pulled transitively by storage.py
    kb_backends = types.ModuleType("knowledge.backends")
    kb_backends.get_async_default_client = MagicMock()  # type: ignore[attr-defined]
    kb_backends.get_default_client = MagicMock()  # type: ignore[attr-defined]
    sys.modules.setdefault("knowledge.backends", kb_backends)

    # api.codebase_analytics.source_models
    src_models = types.ModuleType("api.codebase_analytics.source_models")
    src_models.SourceAccess = MagicMock()  # type: ignore[attr-defined]
    sys.modules.setdefault("api.codebase_analytics.source_models", src_models)

    # api.codebase_analytics.source_service (the one LLC code calls)
    src_svc = types.ModuleType("api.codebase_analytics.source_service")
    src_svc.create_github_source = AsyncMock()  # type: ignore[attr-defined]
    sys.modules.setdefault("api.codebase_analytics.source_service", src_svc)

    # api.codebase_analytics.source_storage
    src_storage = types.ModuleType("api.codebase_analytics.source_storage")
    src_storage.get_source = AsyncMock()  # type: ignore[attr-defined]
    src_storage.delete_source = AsyncMock()  # type: ignore[attr-defined]
    sys.modules.setdefault("api.codebase_analytics.source_storage", src_storage)

    # api.codebase_analytics (package) — must come after sub-modules
    pkg = types.ModuleType("api.codebase_analytics")
    pkg.__path__ = []  # type: ignore[attr-defined]
    pkg.__package__ = "api.codebase_analytics"
    pkg.source_service = src_svc  # type: ignore[attr-defined]
    pkg.source_storage = src_storage  # type: ignore[attr-defined]
    sys.modules.setdefault("api.codebase_analytics", pkg)


_make_codebase_analytics_stubs()


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

    We replace the stub AsyncMocks installed by _make_codebase_analytics_stubs()
    directly on the already-registered sys.modules entries so unittest.mock never
    needs to import api.codebase_analytics (which would trigger the heavy chain).
    """
    org = _FIXED_ORG_ID
    project = _make_mock_project(org)
    project_with_repo = _make_mock_project(org, code_source_id=_FAKE_SOURCE_ID)
    fake_src = _make_fake_code_source()

    fake_create = AsyncMock(return_value=fake_src)
    fake_get = AsyncMock(return_value=fake_src)

    # Patch directly on the stub modules (already in sys.modules).
    svc_mod = sys.modules["api.codebase_analytics.source_service"]
    storage_mod = sys.modules["api.codebase_analytics.source_storage"]
    orig_create = svc_mod.create_github_source
    orig_get = storage_mod.get_source
    svc_mod.create_github_source = fake_create  # type: ignore[attr-defined]
    storage_mod.get_source = fake_get  # type: ignore[attr-defined]
    # Also patch the package-level alias that lazy imports inside sprints.py will land on.
    pkg_mod = sys.modules["api.codebase_analytics"]
    pkg_mod.source_service = svc_mod  # type: ignore[attr-defined]

    app, _patch_kb = _build_llc_app(org, project, project_with_repo)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Stash references so the project fixtures can read them.
            client._test_project = project  # type: ignore[attr-defined]
            client._test_project_with_repo = project_with_repo  # type: ignore[attr-defined]
            yield client
    finally:
        svc_mod.create_github_source = orig_create  # type: ignore[attr-defined]
        storage_mod.get_source = orig_get  # type: ignore[attr-defined]
        _patch_kb.stop()


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
