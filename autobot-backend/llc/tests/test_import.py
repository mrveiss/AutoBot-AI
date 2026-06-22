# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for PortabilityService import functionality (GH#8246)."""

import uuid
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.services.portability import PortabilityService
from llc.services.portability import TemplateImportError as LLCImportError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCHEMA_VERSION = "1.0"


def _template(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "company": {
            "name": "Acme Corp",
            "slug": "acme-corp",
            "issue_prefix": "ACM",
            "budget_monthly_cents": 0,
            "require_approval_for_hires": False,
        },
        "agents": [],
        "goals": [],
        "projects": [],
        "work_items": [],
    }
    base.update(overrides)
    return base


def _make_svc() -> PortabilityService:
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.begin_nested = AsyncMock(return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))
    return PortabilityService(session=session)


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_validate_schema_wrong_version() -> None:
    svc = _make_svc()
    with pytest.raises(LLCImportError, match="schema_version"):
        svc._validate_schema({"schema_version": "2.0"})


def test_validate_schema_missing_version() -> None:
    svc = _make_svc()
    with pytest.raises(LLCImportError, match="schema_version"):
        svc._validate_schema({})


def test_validate_schema_ok() -> None:
    svc = _make_svc()
    svc._validate_schema({"schema_version": "1.0"})  # no exception


# ---------------------------------------------------------------------------
# preview_import — no collision
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_no_collision() -> None:
    svc = _make_svc()
    # all selects return empty
    svc.session.execute.return_value.scalar.return_value = None
    svc.session.execute.return_value = MagicMock(
        scalar=MagicMock(return_value=None), __iter__=MagicMock(return_value=iter([]))
    )

    tmpl = _template(
        agents=[{"name": "Bob", "adapter_config": {}}],
        goals=[{"title": "Goal 1"}],
    )

    with (
        patch.object(svc, "_prefix_exists", return_value=False),
        patch.object(svc, "_agent_names_exist", return_value=[]),
        patch.object(svc, "_goal_titles_exist", return_value=[]),
    ):
        result = await svc.preview_import(tmpl)

    assert result["collisions"] == []
    assert result["will_create"]["agents"] == 1
    assert result["will_create"]["goals"] == 1
    assert result["warnings"] == []


# ---------------------------------------------------------------------------
# preview_import — with collisions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_with_collisions() -> None:
    svc = _make_svc()
    tmpl = _template(
        agents=[{"name": "Alice"}],
        goals=[{"title": "Existing Goal"}],
    )
    # Agent and goal collision checks are scoped to target_company_id (new-company
    # imports have no pre-existing namespace).  Pass a target company so the
    # checks run and populate the collisions list.
    target_company_id = uuid.uuid4()

    with (
        patch.object(svc, "_prefix_exists", return_value=True),
        patch.object(svc, "_agent_names_exist", return_value=["Alice"]),
        patch.object(svc, "_goal_titles_exist", return_value=["Existing Goal"]),
    ):
        result = await svc.preview_import(tmpl, target_company_id=target_company_id)

    types = {c["type"] for c in result["collisions"]}
    assert "issue_prefix" in types
    assert "agent_name" in types
    assert "goal_title" in types


# ---------------------------------------------------------------------------
# preview_import — secret placeholder warning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_secret_placeholder_warning() -> None:
    svc = _make_svc()
    tmpl = _template(
        agents=[{"name": "Bot", "adapter_config": {"token": "{{MY_SECRET}}"}}],
    )

    with (
        patch.object(svc, "_prefix_exists", return_value=False),
        patch.object(svc, "_agent_names_exist", return_value=[]),
        patch.object(svc, "_goal_titles_exist", return_value=[]),
    ):
        result = await svc.preview_import(tmpl)

    assert any("MY_SECRET" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# _resolve_secrets
# ---------------------------------------------------------------------------


def test_resolve_secrets_replaces_placeholder() -> None:
    svc = _make_svc()
    config = {"token": "{{MY_TOKEN}}", "url": "https://example.com"}
    warnings: list = []
    resolved = svc._resolve_secrets(config, {"MY_TOKEN": "abc123"}, "TestAgent", warnings)
    assert resolved["token"] == "abc123"
    assert warnings == []


def test_resolve_secrets_unresolved_warns() -> None:
    svc = _make_svc()
    config = {"token": "{{MISSING}}"}
    warnings: list = []
    resolved = svc._resolve_secrets(config, {}, "TestAgent", warnings)
    assert resolved["token"] == "{{MISSING}}"
    assert any("MISSING" in w for w in warnings)


# ---------------------------------------------------------------------------
# _next_available_prefix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_next_available_prefix_appends_2() -> None:
    svc = _make_svc()
    call_count = 0

    async def _prefix_exists(prefix: str) -> bool:
        nonlocal call_count
        call_count += 1
        return prefix == "ACM"  # ACM taken, ACM2 free

    with patch.object(svc, "_prefix_exists", side_effect=_prefix_exists):
        result = await svc._next_available_prefix("ACM")

    assert result == "ACM2"


# ---------------------------------------------------------------------------
# execute_import — schema error rolls back
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_import_bad_schema_raises() -> None:
    svc = _make_svc()
    with pytest.raises(LLCImportError, match="schema_version"):
        await svc.execute_import({"schema_version": "99.0"})


# ---------------------------------------------------------------------------
# execute_import — happy path (mocked entity creation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_import_happy_path() -> None:
    svc = _make_svc()
    tmpl = _template(
        goals=[{"title": "G1", "level": "objective", "status": "draft"}],
        projects=[{"name": "P1", "description": "desc"}],
        work_items=[{"title": "W1", "type": "epic", "is_seed": True}],
    )

    company_id = uuid.uuid4()

    with (
        patch.object(svc, "_resolve_or_create_company", return_value=company_id),
        patch.object(svc, "_import_agent", return_value=str(uuid.uuid4())),
        patch.object(svc, "_import_goal", return_value=uuid.uuid4()),
        patch.object(svc, "_import_project", return_value=uuid.uuid4()),
        patch.object(svc, "_import_work_item", return_value=uuid.uuid4()),
    ):
        sp_mock = AsyncMock()
        sp_mock.commit = AsyncMock()
        sp_mock.rollback = AsyncMock()
        svc.session.begin_nested = AsyncMock(return_value=sp_mock)

        result = await svc.execute_import(tmpl)

    assert result["company_id"] == str(company_id)
    assert len(result["created_entities"]["goals"]) == 1
    assert len(result["created_entities"]["projects"]) == 1
    assert len(result["created_entities"]["work_items"]) == 1


# ---------------------------------------------------------------------------
# execute_import — rollback on failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_import_rollback_on_failure() -> None:
    svc = _make_svc()
    tmpl = _template()

    with patch.object(svc, "_resolve_or_create_company", side_effect=Exception("DB boom")):
        sp_mock = AsyncMock()
        sp_mock.commit = AsyncMock()
        sp_mock.rollback = AsyncMock()
        svc.session.begin_nested = AsyncMock(return_value=sp_mock)

        with pytest.raises(LLCImportError, match="rolled back"):
            await svc.execute_import(tmpl)

    sp_mock.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# execute_import — target_company_id not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_import_target_company_not_found() -> None:
    svc = _make_svc()
    tmpl = _template()
    missing_id = uuid.uuid4()

    sp_mock = AsyncMock()
    sp_mock.commit = AsyncMock()
    sp_mock.rollback = AsyncMock()
    svc.session.begin_nested = AsyncMock(return_value=sp_mock)

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    svc.session.execute = AsyncMock(return_value=result_mock)

    with pytest.raises(LLCImportError, match="not found"):
        await svc.execute_import(tmpl, target_company_id=missing_id)


# ---------------------------------------------------------------------------
# execute_import — skips non-seed work items
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_import_skips_non_seed_work_items() -> None:
    svc = _make_svc()
    tmpl = _template(
        work_items=[
            {"title": "Epic seed", "type": "epic", "is_seed": True},
            {"title": "Task not seed", "type": "task", "is_seed": False},
        ]
    )

    company_id = uuid.uuid4()
    created: list[str] = []

    async def fake_import_work_item(item, cid):  # noqa: ANN001
        created.append(item["title"])
        return uuid.uuid4()

    with (
        patch.object(svc, "_resolve_or_create_company", return_value=company_id),
        patch.object(svc, "_import_work_item", side_effect=fake_import_work_item),
    ):
        sp_mock = AsyncMock()
        sp_mock.commit = AsyncMock()
        sp_mock.rollback = AsyncMock()
        svc.session.begin_nested = AsyncMock(return_value=sp_mock)

        await svc.execute_import(tmpl)

    assert created == ["Epic seed"]
