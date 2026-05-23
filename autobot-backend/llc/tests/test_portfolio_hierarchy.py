# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for Portfolio → Program → Project hierarchy services (GH#8219).

Sprint CRUD + lifecycle tests live in the sprint planning service tests
(GH#8220 / test_sprint_planning.py); the LLCSprint model is owned by that
migration chain (revision 20260523_032).
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from llc.models.portfolio import LLCPortfolio
from llc.models.program import LLCProgram
from llc.models.project import LLCProject
from llc.services.portfolio import PortfolioService
from llc.services.program import ProgramService
from llc.services.project import ProjectService


# ----------------------------------------------------------------- Helpers


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_portfolio(company_id: str = "co1", name: str = "P1") -> LLCPortfolio:
    p = LLCPortfolio(company_id=company_id, name=name, status="active")
    p.id = _uuid()
    p.created_at = _now()
    p.updated_at = _now()
    return p


def _make_program(portfolio_id: uuid.UUID | None = None, name: str = "Prog1") -> LLCProgram:
    p = LLCProgram(
        portfolio_id=portfolio_id or _uuid(),
        name=name,
        status="active",
    )
    p.id = _uuid()
    p.created_at = _now()
    p.updated_at = _now()
    return p


def _make_project(program_id: uuid.UUID | None = None, name: str = "Proj1") -> LLCProject:
    p = LLCProject(
        program_id=program_id or _uuid(),
        name=name,
        status="active",
    )
    p.id = _uuid()
    p.created_at = _now()
    p.updated_at = _now()
    return p


# ----------------------------------------------------------------- PortfolioService


@pytest.fixture
def portfolio_svc() -> PortfolioService:
    return PortfolioService()


@pytest.mark.asyncio
async def test_portfolio_create(portfolio_svc: PortfolioService) -> None:
    session = AsyncMock()
    session.flush = AsyncMock()
    portfolio = await portfolio_svc.create(session, "co1", "P1", description="desc")
    assert portfolio.company_id == "co1"
    assert portfolio.name == "P1"
    assert portfolio.description == "desc"
    assert portfolio.status == "active"


@pytest.mark.asyncio
async def test_portfolio_get_none(portfolio_svc: PortfolioService) -> None:
    session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)
    result = await portfolio_svc.get(session, _uuid())
    assert result is None


@pytest.mark.asyncio
async def test_portfolio_update(portfolio_svc: PortfolioService) -> None:
    p = _make_portfolio()
    session = AsyncMock()
    session.flush = AsyncMock()
    with patch.object(portfolio_svc, "get", AsyncMock(return_value=p)):
        updated = await portfolio_svc.update(session, p.id, name="New Name")
    assert updated is not None
    assert updated.name == "New Name"


@pytest.mark.asyncio
async def test_portfolio_delete_not_found(portfolio_svc: PortfolioService) -> None:
    session = AsyncMock()
    with patch.object(portfolio_svc, "get", AsyncMock(return_value=None)):
        result = await portfolio_svc.delete(session, _uuid())
    assert result is False


@pytest.mark.asyncio
async def test_portfolio_delete_ok(portfolio_svc: PortfolioService) -> None:
    p = _make_portfolio()
    session = AsyncMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    with patch.object(portfolio_svc, "get", AsyncMock(return_value=p)):
        result = await portfolio_svc.delete(session, p.id)
    assert result is True


# ----------------------------------------------------------------- ProgramService


@pytest.fixture
def program_svc() -> ProgramService:
    return ProgramService()


@pytest.mark.asyncio
async def test_program_create(program_svc: ProgramService) -> None:
    session = AsyncMock()
    session.flush = AsyncMock()
    portfolio_id = _uuid()
    prog = await program_svc.create(session, portfolio_id, "Prog1")
    assert prog.portfolio_id == portfolio_id
    assert prog.name == "Prog1"
    assert prog.status == "active"


@pytest.mark.asyncio
async def test_program_get_none(program_svc: ProgramService) -> None:
    session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)
    result = await program_svc.get(session, _uuid())
    assert result is None


@pytest.mark.asyncio
async def test_program_update(program_svc: ProgramService) -> None:
    prog = _make_program()
    session = AsyncMock()
    session.flush = AsyncMock()
    with patch.object(program_svc, "get", AsyncMock(return_value=prog)):
        updated = await program_svc.update(session, prog.id, status="archived")
    assert updated is not None
    assert updated.status == "archived"


@pytest.mark.asyncio
async def test_program_delete(program_svc: ProgramService) -> None:
    prog = _make_program()
    session = AsyncMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    with patch.object(program_svc, "get", AsyncMock(return_value=prog)):
        result = await program_svc.delete(session, prog.id)
    assert result is True


# ----------------------------------------------------------------- ProjectService


@pytest.fixture
def project_svc() -> ProjectService:
    return ProjectService()


@pytest.mark.asyncio
async def test_project_create_with_owner(project_svc: ProjectService) -> None:
    session = AsyncMock()
    session.flush = AsyncMock()
    program_id = _uuid()
    proj = await project_svc.create(
        session, program_id, "Proj1", owner_agent_id="agent-42"
    )
    assert proj.program_id == program_id
    assert proj.owner_agent_id == "agent-42"


@pytest.mark.asyncio
async def test_project_create_defaults(project_svc: ProjectService) -> None:
    session = AsyncMock()
    session.flush = AsyncMock()
    proj = await project_svc.create(session, _uuid(), "Proj2")
    assert proj.status == "active"
    assert proj.owner_agent_id is None


@pytest.mark.asyncio
async def test_project_update_none_if_missing(project_svc: ProjectService) -> None:
    session = AsyncMock()
    with patch.object(project_svc, "get", AsyncMock(return_value=None)):
        result = await project_svc.update(session, _uuid(), status="archived")
    assert result is None


@pytest.mark.asyncio
async def test_project_delete(project_svc: ProjectService) -> None:
    proj = _make_project()
    session = AsyncMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    with patch.object(project_svc, "get", AsyncMock(return_value=proj)):
        result = await project_svc.delete(session, proj.id)
    assert result is True


@pytest.mark.asyncio
async def test_project_delete_not_found(project_svc: ProjectService) -> None:
    session = AsyncMock()
    with patch.object(project_svc, "get", AsyncMock(return_value=None)):
        result = await project_svc.delete(session, _uuid())
    assert result is False
