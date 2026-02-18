#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for knowledge_audit.py RBAC enforcement (Issue #934).

Tests:
- Org admin check: authorized (admin / org_admin roles)
- Org admin check: unauthorized (regular user / missing role)
- Missing org_id guard
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(kb=None):
    """Build a minimal mock FastAPI app that returns kb from state."""
    app = MagicMock()
    return app


def _make_request(kb=None):
    """Build a minimal mock Request whose app returns kb."""
    request = MagicMock()
    request.app = _make_app(kb)
    return request


def _make_audit_log():
    """Return a mock KnowledgeAuditLog."""
    log = AsyncMock()
    log.get_organization_audit_log = AsyncMock(return_value=[])
    log.generate_compliance_report = AsyncMock(
        return_value={"total_events": 0, "events": []}
    )
    return log


def _make_kb(audit_log=None):
    """Return a mock knowledge base with an audit_log."""
    kb = MagicMock()
    kb.audit_log = audit_log or _make_audit_log()
    kb.aioredis_client = MagicMock()
    return kb


# ---------------------------------------------------------------------------
# get_organization_audit_log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_org_audit_log_admin_allowed():
    """Admin role can access org audit log."""
    from api.knowledge_audit import get_organization_audit_log

    user = {"user_id": "u1", "org_id": "org1", "role": "admin"}
    kb = _make_kb()

    with patch(
        "api.knowledge_audit.get_or_create_knowledge_base",
        new=AsyncMock(return_value=kb),
    ):
        result = await get_organization_audit_log(
            request=_make_request(kb), current_user=user
        )

    assert result["organization_id"] == "org1"
    assert "events" in result


@pytest.mark.asyncio
async def test_org_audit_log_org_admin_allowed():
    """org_admin role can access org audit log."""
    from api.knowledge_audit import get_organization_audit_log

    user = {"user_id": "u2", "org_id": "org1", "role": "org_admin"}
    kb = _make_kb()

    with patch(
        "api.knowledge_audit.get_or_create_knowledge_base",
        new=AsyncMock(return_value=kb),
    ):
        result = await get_organization_audit_log(
            request=_make_request(kb), current_user=user
        )

    assert result["organization_id"] == "org1"


@pytest.mark.asyncio
async def test_org_audit_log_regular_user_forbidden():
    """Regular user cannot access org audit log (403)."""
    from api.knowledge_audit import get_organization_audit_log
    from fastapi import HTTPException

    user = {"user_id": "u3", "org_id": "org1", "role": "user"}

    with pytest.raises(HTTPException) as exc_info:
        await get_organization_audit_log(request=_make_request(), current_user=user)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_org_audit_log_no_role_forbidden():
    """Missing role key defaults to empty string → 403."""
    from api.knowledge_audit import get_organization_audit_log
    from fastapi import HTTPException

    user = {"user_id": "u4", "org_id": "org1"}  # no "role" key

    with pytest.raises(HTTPException) as exc_info:
        await get_organization_audit_log(request=_make_request(), current_user=user)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_org_audit_log_no_org_id_bad_request():
    """User without org_id gets 400."""
    from api.knowledge_audit import get_organization_audit_log
    from fastapi import HTTPException

    user = {"user_id": "u5", "role": "admin"}  # no org_id

    with pytest.raises(HTTPException) as exc_info:
        await get_organization_audit_log(request=_make_request(), current_user=user)

    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# generate_compliance_report
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compliance_report_admin_allowed():
    """Admin can generate compliance report."""
    from datetime import datetime

    from api.knowledge_audit import ComplianceReportRequest, generate_compliance_report

    user = {"user_id": "u1", "org_id": "org1", "role": "admin"}
    report_req = ComplianceReportRequest(
        start_date=datetime(2026, 1, 1),
        end_date=datetime(2026, 1, 31),
    )
    kb = _make_kb()

    with patch(
        "api.knowledge_audit.get_or_create_knowledge_base",
        new=AsyncMock(return_value=kb),
    ):
        result = await generate_compliance_report(
            report_request=report_req,
            request=_make_request(kb),
            current_user=user,
        )

    assert result["total_events"] == 0


@pytest.mark.asyncio
async def test_compliance_report_regular_user_forbidden():
    """Regular user cannot generate compliance report (403)."""
    from datetime import datetime

    from api.knowledge_audit import ComplianceReportRequest, generate_compliance_report
    from fastapi import HTTPException

    user = {"user_id": "u3", "org_id": "org1", "role": "member"}
    report_req = ComplianceReportRequest(
        start_date=datetime(2026, 1, 1),
        end_date=datetime(2026, 1, 31),
    )

    with pytest.raises(HTTPException) as exc_info:
        await generate_compliance_report(
            report_request=report_req,
            request=_make_request(),
            current_user=user,
        )

    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# get_compliance_summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compliance_summary_org_admin_allowed():
    """org_admin can access compliance summary."""
    from api.knowledge_audit import get_compliance_summary

    user = {"user_id": "u1", "org_id": "org1", "role": "org_admin"}
    kb = _make_kb()

    with patch(
        "api.knowledge_audit.get_or_create_knowledge_base",
        new=AsyncMock(return_value=kb),
    ):
        result = await get_compliance_summary(
            request=_make_request(kb), current_user=user
        )

    assert "summary_period_days" in result
    assert result["summary_period_days"] == 30


@pytest.mark.asyncio
async def test_compliance_summary_regular_user_forbidden():
    """Regular user cannot access compliance summary (403)."""
    from api.knowledge_audit import get_compliance_summary
    from fastapi import HTTPException

    user = {"user_id": "u3", "org_id": "org1", "role": "viewer"}

    with pytest.raises(HTTPException) as exc_info:
        await get_compliance_summary(request=_make_request(), current_user=user)

    assert exc_info.value.status_code == 403
