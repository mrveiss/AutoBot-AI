# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for PortabilityService — company template and snapshot export (GH#8245)."""

import json
import uuid
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.services.portability import PortabilityService, _scrub_adapter_config


# ------------------------------------------------------------------
# Unit tests for _scrub_adapter_config
# ------------------------------------------------------------------


def test_scrub_replaces_known_secret_keys():
    config = {"api_key": "sk-secret-123", "model": "gpt-4", "timeout": 30}
    result = _scrub_adapter_config(config, {})
    assert result["api_key"] == "{{API_KEY}}"
    assert result["model"] == "gpt-4"
    assert result["timeout"] == 30


def test_scrub_uses_bound_secret_name_when_available():
    config = {"api_key": "my_openai_key", "endpoint": "https://api.openai.com"}
    secret_map = {"my_openai_key": "my_openai_key"}
    result = _scrub_adapter_config(config, secret_map)
    assert result["api_key"] == "{{my_openai_key}}"


def test_scrub_falls_back_to_uppercased_key():
    config = {"token": "bearer-xyz"}
    result = _scrub_adapter_config(config, {})
    assert result["token"] == "{{TOKEN}}"


def test_scrub_leaves_non_secret_keys_intact():
    config = {"base_url": "https://example.com", "retries": 3, "stream": True}
    result = _scrub_adapter_config(config, {})
    assert result == {"base_url": "https://example.com", "retries": 3, "stream": True}


def test_scrub_empty_config():
    assert _scrub_adapter_config({}, {}) == {}


def test_scrub_skips_empty_string_values():
    config = {"api_key": "", "model": "gpt-4"}
    result = _scrub_adapter_config(config, {})
    # Empty string is falsy — should NOT be replaced with placeholder
    assert result["api_key"] == ""
    assert result["model"] == "gpt-4"


def test_scrub_multiple_secret_keys():
    config = {
        "api_key": "key1",
        "token": "tok1",
        "password": "pass1",
        "host": "db.local",
    }
    result = _scrub_adapter_config(config, {})
    assert "{{" in result["api_key"]
    assert "{{" in result["token"]
    assert "{{" in result["password"]
    assert result["host"] == "db.local"


# ------------------------------------------------------------------
# PortabilityService integration-style tests (mocked session)
# ------------------------------------------------------------------


def _make_service(session: AsyncMock | None = None) -> PortabilityService:
    if session is None:
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
    return PortabilityService(session=session)


def _mock_execute_mapping(rows: list) -> AsyncMock:
    """Return a mock that .execute() → .mappings().first() or .all()."""
    result = MagicMock()
    result.mappings.return_value.first.return_value = rows[0] if rows else None
    result.mappings.return_value.all.return_value = rows
    result.__iter__ = MagicMock(return_value=iter(rows))
    return result


@pytest.fixture
def company_id() -> uuid.UUID:
    return uuid.UUID("12345678-1234-5678-1234-567812345678")


@pytest.mark.asyncio
async def test_export_template_returns_schema_version(company_id):
    svc = _make_service()
    cid = str(company_id)

    async def _fake_execute(stmt, params=None):
        mock = MagicMock()
        mock.mappings.return_value.first.return_value = {
            "id": company_id,
            "name": "Test Co",
            "slug": "test-co",
            "description": None,
            "issue_prefix": "TC",
            "budget_monthly_cents": 0,
            "brand_color": None,
            "require_approval_for_hires": False,
            "parent_org_id": None,
            "llc_status": "active",
            "created_at": None,
        }
        mock.mappings.return_value.all.return_value = []
        mock.__iter__ = MagicMock(return_value=iter([]))
        return mock

    svc.session.execute = _fake_execute

    with patch("llc.services.portability.get_async_redis_client", return_value=AsyncMock(return_value=None)):
        result = await svc.export_template(company_id)

    assert result["schema_version"] == "1.0"
    assert result["export_kind"] == "template"
    assert "company" in result
    assert "agents" in result
    assert "goals" in result
    assert "routines" in result
    assert "portfolios" in result
    assert "projects" in result
    assert "seed_work_items" in result
    assert "artifact_id" in result


@pytest.mark.asyncio
async def test_export_snapshot_includes_work_items_and_sprints(company_id):
    svc = _make_service()

    async def _fake_execute(stmt, params=None):
        mock = MagicMock()
        mock.mappings.return_value.first.return_value = {
            "id": company_id,
            "name": "Test Co",
            "slug": "test-co",
            "description": None,
            "issue_prefix": None,
            "budget_monthly_cents": 0,
            "brand_color": None,
            "require_approval_for_hires": False,
            "parent_org_id": None,
            "llc_status": "active",
            "created_at": None,
        }
        mock.mappings.return_value.all.return_value = []
        mock.__iter__ = MagicMock(return_value=iter([]))
        return mock

    svc.session.execute = _fake_execute

    with patch("llc.services.portability.get_async_redis_client", return_value=AsyncMock(return_value=None)):
        result = await svc.export_snapshot(company_id)

    assert result["export_kind"] == "snapshot"
    assert "work_items" in result
    assert "sprints" in result
    assert "kb_collection_names" in result


@pytest.mark.asyncio
async def test_export_template_no_snapshot_keys(company_id):
    svc = _make_service()

    async def _fake_execute(stmt, params=None):
        mock = MagicMock()
        mock.mappings.return_value.first.return_value = {
            "id": company_id,
            "name": "Acme",
            "slug": "acme",
            "description": None,
            "issue_prefix": None,
            "budget_monthly_cents": 0,
            "brand_color": None,
            "require_approval_for_hires": False,
            "parent_org_id": None,
            "llc_status": "active",
            "created_at": None,
        }
        mock.mappings.return_value.all.return_value = []
        mock.__iter__ = MagicMock(return_value=iter([]))
        return mock

    svc.session.execute = _fake_execute

    with patch("llc.services.portability.get_async_redis_client", return_value=AsyncMock(return_value=None)):
        result = await svc.export_template(company_id)

    assert "work_items" not in result
    assert "sprints" not in result
    assert "kb_collection_names" not in result


@pytest.mark.asyncio
async def test_export_stores_artifact_in_redis(company_id):
    svc = _make_service()

    async def _fake_execute(stmt, params=None):
        mock = MagicMock()
        mock.mappings.return_value.first.return_value = {
            "id": company_id,
            "name": "Co",
            "slug": "co",
            "description": None,
            "issue_prefix": None,
            "budget_monthly_cents": 0,
            "brand_color": None,
            "require_approval_for_hires": False,
            "parent_org_id": None,
            "llc_status": "active",
            "created_at": None,
        }
        mock.mappings.return_value.all.return_value = []
        mock.__iter__ = MagicMock(return_value=iter([]))
        return mock

    svc.session.execute = _fake_execute

    redis_mock = AsyncMock()
    redis_mock.set = AsyncMock()
    redis_mock.keys = AsyncMock(return_value=[])

    with patch("llc.services.portability.get_async_redis_client", new=AsyncMock(return_value=redis_mock)):
        result = await svc.export_template(company_id)

    redis_mock.set.assert_called_once()
    call_kwargs = redis_mock.set.call_args
    key = call_kwargs[0][0]
    assert str(company_id) in key
    assert key.startswith("llc:export:")


@pytest.mark.asyncio
async def test_export_adds_artifact_row_to_session(company_id):
    svc = _make_service()

    async def _fake_execute(stmt, params=None):
        mock = MagicMock()
        mock.mappings.return_value.first.return_value = {
            "id": company_id,
            "name": "Co",
            "slug": "co",
            "description": None,
            "issue_prefix": None,
            "budget_monthly_cents": 0,
            "brand_color": None,
            "require_approval_for_hires": False,
            "parent_org_id": None,
            "llc_status": "active",
            "created_at": None,
        }
        mock.mappings.return_value.all.return_value = []
        mock.__iter__ = MagicMock(return_value=iter([]))
        return mock

    svc.session.execute = _fake_execute

    with patch("llc.services.portability.get_async_redis_client", return_value=AsyncMock(return_value=None)):
        await svc.export_template(company_id)

    svc.session.add.assert_called_once()
    artifact = svc.session.add.call_args[0][0]
    from llc.models.export import LLCExportArtifact

    assert isinstance(artifact, LLCExportArtifact)
    assert artifact.export_kind == "template"
    assert artifact.company_id == company_id
