# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for Portfolio → Program → Project → Sprint hierarchy (GH#8219)."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from llc.models.enums import SprintStatus
from llc.models.portfolio import LLCPortfolio
from llc.models.program import LLCProgram
from llc.models.project import LLCProject
from llc.models.sprint import LLCSprint
from llc.services.portfolio import PortfolioService
from llc.services.program import ProgramService
from llc.services.project import ProjectService
from llc.services.sprint import SprintService


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


def _make_sprint(project_id: uuid.UUID | None = None, name: str = "S1") -> LLCSprint:
    s = LLCSprint(
        project_id=project_id or _uuid(),
        name=name,
        status=SprintStatus.PLANNING.value,
    )
    s.id = _uuid()
    s.created_at = _now()
    s.updated_at = _now()
    return s


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
async def test_project_update_none_if_missing(project_svc: ProjectService) -> None:
    session = AsyncMock()
    with patch.object(project_svc, "get", AsyncMock(return_value=None)):
        result = await project_svc.update(session, _uuid(), status="archived")
    assert result is None


# ----------------------------------------------------------------- SprintService


@pytest.fixture
def sprint_svc() -> SprintService:
    return SprintService()


@pytest.mark.asyncio
async def test_sprint_create(sprint_svc: SprintService) -> None:
    session = AsyncMock()
    session.flush = AsyncMock()
    project_id = _uuid()
    sprint = await sprint_svc.create(session, project_id, "Sprint 1", capacity_points=40)
    assert sprint.project_id == project_id
    assert sprint.status == SprintStatus.PLANNING.value
    assert sprint.capacity_points == 40


@pytest.mark.asyncio
async def test_sprint_start(sprint_svc: SprintService) -> None:
    sprint = _make_sprint()
    sprint.status = SprintStatus.PLANNING.value
    session = AsyncMock()
    session.flush = AsyncMock()
    with patch.object(sprint_svc, "get", AsyncMock(return_value=sprint)):
        started = await sprint_svc.start(session, sprint.id)
    assert started.status == SprintStatus.ACTIVE.value
    assert started.start_date is not None


@pytest.mark.asyncio
async def test_sprint_start_invalid_status(sprint_svc: SprintService) -> None:
    sprint = _make_sprint()
    sprint.status = SprintStatus.ACTIVE.value
    session = AsyncMock()
    with patch.object(sprint_svc, "get", AsyncMock(return_value=sprint)):
        with pytest.raises(HTTPException) as exc:
            await sprint_svc.start(session, sprint.id)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_sprint_close(sprint_svc: SprintService) -> None:
    sprint = _make_sprint()
    sprint.status = SprintStatus.ACTIVE.value
    session = AsyncMock()
    session.flush = AsyncMock()
    with patch.object(sprint_svc, "get", AsyncMock(return_value=sprint)):
        closed = await sprint_svc.close(session, sprint.id, velocity_actual=35)
    assert closed.status == SprintStatus.CLOSED.value
    assert closed.velocity_actual == 35
    assert closed.end_date is not None


@pytest.mark.asyncio
async def test_sprint_close_invalid_status(sprint_svc: SprintService) -> None:
    sprint = _make_sprint()
    sprint.status = SprintStatus.PLANNING.value
    session = AsyncMock()
    with patch.object(sprint_svc, "get", AsyncMock(return_value=sprint)):
        with pytest.raises(HTTPException) as exc:
            await sprint_svc.close(session, sprint.id)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_sprint_close_not_found(sprint_svc: SprintService) -> None:
    session = AsyncMock()
    with patch.object(sprint_svc, "get", AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc:
            await sprint_svc.close(session, _uuid())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_sprint_delete(sprint_svc: SprintService) -> None:
    sprint = _make_sprint()
    session = AsyncMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    with patch.object(sprint_svc, "get", AsyncMock(return_value=sprint)):
        result = await sprint_svc.delete(session, sprint.id)
    assert result is True
