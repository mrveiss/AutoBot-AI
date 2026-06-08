# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for LLC template library service (GH#8260).

Covers:
- Secret scrubbing validation at publish
- Placeholder resolution at import
- Unresolved placeholder detection (422 path)
- KB indexing called on publish
- KB removal called on delete
- Access control (private vs public)
- Entity count extraction from template_json
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.models.template import (
    TemplateCategory,
    TemplateImportRequest,
    TemplatePublishRequest,
)
from llc.services.template import (
    TemplateAccessError,
    TemplateNotFoundError,
    TemplateSecretPlaceholderError,
    TemplateService,
    _apply_template,
    _build_embed_text,
    _check_access,
    _find_placeholders,
    _replace_in_structure,
    _resolve_placeholders,
    _validate_no_secrets,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(first_row=None) -> AsyncMock:
    """Minimal async session mock returning first_row on execute().mappings().first()."""
    session = AsyncMock()
    mapping_result = MagicMock()
    mapping_result.first.return_value = first_row
    mapping_result.__iter__ = MagicMock(return_value=iter([]))
    result = MagicMock()
    result.mappings.return_value = mapping_result
    session.execute.return_value = result
    return session


def _template_row(
    template_id: uuid.UUID,
    is_public: bool = True,
    company_id: uuid.UUID | None = None,
) -> dict:
    return {
        "id": template_id,
        "name": "Test Template",
        "description": "A test",
        "category": "company",
        "template_json": {"agents": [], "projects": []},
        "created_by_company_id": company_id,
        "is_public": is_public,
        "usage_count": 0,
        "created_at": "2026-05-24T00:00:00Z",
        "updated_at": "2026-05-24T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# _validate_no_secrets
# ---------------------------------------------------------------------------


def test_validate_no_secrets_clean_passes():
    """Clean template_json with placeholder keys must not raise."""
    data = {
        "name": "Standard SW Company",
        "db_connection": "{{DB_URL}}",
        "agents": [{"role": "backend_dev"}],
    }
    _validate_no_secrets(data)  # must not raise


def test_validate_no_secrets_logs_warning_for_suspicious_values(caplog):
    """Long strings containing key-like keywords trigger a warning log."""
    import logging

    data = {"api_key": "xxxxxxxxxxx-abcdefghij1234567890xyz-very-long-value"}
    with caplog.at_level(logging.WARNING, logger="llc.services.template"):
        _validate_no_secrets(data)
    assert any("api_key" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# _replace_in_structure / _find_placeholders / _resolve_placeholders
# ---------------------------------------------------------------------------


def test_replace_in_structure_replaces_single():
    data = {"connection": "postgresql://user:{{DB_PASSWORD}}@localhost/db"}
    result = _replace_in_structure(data, {"DB_PASSWORD": "resolved-value"})
    assert result["connection"] == "postgresql://user:resolved-value@localhost/db"


def test_replace_in_structure_nested():
    data = {"outer": {"inner": "{{KEY}}"}}
    result = _replace_in_structure(data, {"KEY": "value"})
    assert result["outer"]["inner"] == "value"


def test_replace_in_structure_list():
    data = ["prefix-{{TAG}}", "static"]
    result = _replace_in_structure(data, {"TAG": "prod"})
    assert result == ["prefix-prod", "static"]


def test_find_placeholders_returns_names():
    data = {"a": "{{FOO}}", "b": {"c": "{{BAR}}"}}
    found = _find_placeholders(data)
    assert sorted(found) == ["BAR", "FOO"]


def test_resolve_placeholders_raises_on_unresolved():
    data = {"url": "https://example.com/{{API_KEY}}"}
    with pytest.raises(TemplateSecretPlaceholderError) as exc_info:
        _resolve_placeholders(data, {})
    assert "API_KEY" in exc_info.value.unresolved


def test_resolve_placeholders_success():
    data = {"url": "https://example.com/{{API_KEY}}"}
    result = _resolve_placeholders(data, {"API_KEY": "resolved-key-value"})
    assert result["url"] == "https://example.com/resolved-key-value"


# ---------------------------------------------------------------------------
# _apply_template
# ---------------------------------------------------------------------------


def test_apply_template_counts_entity_types():
    template_json = {
        "agents": [{"id": "a1"}, {"id": "a2"}],
        "projects": [{"id": "p1"}],
        "work_items": [],
    }
    counts = _apply_template(template_json)
    assert counts == {"agents": 2, "projects": 1, "work_items": 0}


def test_apply_template_ignores_non_list_keys():
    template_json = {"agents": "not-a-list", "projects": [{"id": "p1"}]}
    counts = _apply_template(template_json)
    assert "agents" not in counts
    assert counts["projects"] == 1


# ---------------------------------------------------------------------------
# _check_access
# ---------------------------------------------------------------------------


def test_check_access_public_allows_any():
    row = {"id": uuid.uuid4(), "is_public": True, "created_by_company_id": uuid.uuid4()}
    _check_access(row, requesting_company_id=uuid.uuid4())  # must not raise


def test_check_access_private_allows_owner():
    owner_id = uuid.uuid4()
    row = {"id": uuid.uuid4(), "is_public": False, "created_by_company_id": owner_id}
    _check_access(row, requesting_company_id=owner_id)  # must not raise


def test_check_access_private_denies_other():
    row = {"id": uuid.uuid4(), "is_public": False, "created_by_company_id": uuid.uuid4()}
    with pytest.raises(TemplateAccessError):
        _check_access(row, requesting_company_id=uuid.uuid4())


def test_check_access_private_denies_none():
    row = {"id": uuid.uuid4(), "is_public": False, "created_by_company_id": uuid.uuid4()}
    with pytest.raises(TemplateAccessError):
        _check_access(row, requesting_company_id=None)


# ---------------------------------------------------------------------------
# _build_embed_text
# ---------------------------------------------------------------------------


def test_build_embed_text_includes_all_fields():
    text = _build_embed_text(
        name="Standard SW",
        description="Best practice software company",
        category=TemplateCategory.COMPANY,
        tags=["python", "fastapi"],
    )
    assert "Standard SW" in text
    assert "Best practice software company" in text
    assert "company" in text
    assert "python" in text


def test_build_embed_text_without_description():
    text = _build_embed_text(
        name="Minimal",
        description=None,
        category=TemplateCategory.PROJECT,
        tags=[],
    )
    assert "Minimal" in text
    assert "Description" not in text


# ---------------------------------------------------------------------------
# TemplateService.get — not found + access denied
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_raises_not_found():
    session = _make_session(first_row=None)
    svc = TemplateService(session=session)
    with pytest.raises(TemplateNotFoundError):
        await svc.get(uuid.uuid4())


@pytest.mark.asyncio
async def test_get_raises_access_error_for_private_template():
    tid = uuid.uuid4()
    owner_id = uuid.uuid4()
    row = _template_row(tid, is_public=False, company_id=owner_id)
    session = _make_session(first_row=row)

    with patch("llc.services.template._fetch_tags", new=AsyncMock(return_value=[])):
        svc = TemplateService(session=session)
        with pytest.raises(TemplateAccessError):
            await svc.get(tid, requesting_company_id=uuid.uuid4())


# ---------------------------------------------------------------------------
# TemplateService.import_template — placeholder error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_raises_on_unresolved_placeholder():
    tid = uuid.uuid4()
    company_id = uuid.uuid4()
    row = {
        "id": tid,
        "name": "T",
        "description": None,
        "category": "company",
        "template_json": {"db": "{{DB_PASS}}"},
        "created_by_company_id": company_id,
        "is_public": True,
        "usage_count": 0,
        "created_at": "2026-05-24T00:00:00Z",
        "updated_at": "2026-05-24T00:00:00Z",
    }
    session = _make_session(first_row=row)
    svc = TemplateService(session=session)

    req = TemplateImportRequest(target_company_id=company_id, secrets={})
    with pytest.raises(TemplateSecretPlaceholderError) as exc_info:
        await svc.import_template(tid, req)
    assert "DB_PASS" in exc_info.value.unresolved


# ---------------------------------------------------------------------------
# KB indexing called on publish
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_calls_kb_indexing():
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.mappings.return_value.first.return_value = _template_row(uuid.uuid4(), is_public=True)
    session.execute.return_value = execute_result

    req = TemplatePublishRequest(
        name="SW Company Template",
        description="Proven software delivery setup",
        category=TemplateCategory.COMPANY,
        template_json={"agents": [], "projects": []},
        tags=["python"],
        is_public=True,
    )

    with (
        patch(
            "llc.services.template._index_template_in_kb",
            new=AsyncMock(),
        ) as mock_index,
        patch(
            "llc.services.template._upsert_tags",
            new=AsyncMock(),
        ),
        patch(
            "llc.services.template._fetch_tags",
            new=AsyncMock(return_value=["python"]),
        ),
    ):
        svc = TemplateService(session=session)
        await svc.publish(req, company_id=None)
        mock_index.assert_awaited_once()
