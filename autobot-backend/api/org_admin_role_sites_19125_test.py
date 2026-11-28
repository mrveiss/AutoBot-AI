# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#19125: every converted org-admin role gate admits the admin family and refuses the rest.

One case per gate site (knowledge_organization x2, knowledge_audit x3,
chat_sessions x2). ``superadmin`` and ``admin`` (and ``org_admin``, which these
sites also admit) must clear the role gate; ``operator`` and ``user`` must not.
A reverted literal ``"admin"`` comparison fails the superadmin case.
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api import chat_sessions, knowledge_audit, knowledge_organization

_ADMITTED = ["admin", "superadmin", "org_admin"]
_REFUSED = ["operator", "user"]


def _user(role: str) -> dict:
    return {"username": "u", "role": role, "org_id": "org-1"}


async def _outcome(coro) -> str:
    """'admitted' when the role gate was cleared (a later 503/success), else 'refused'."""
    try:
        await coro
    except HTTPException as exc:
        return "admitted" if exc.status_code == 503 else "refused"
    except Exception:  # noqa: BLE001 - ValidationError from the chat gates is the refusal
        return "refused"
    return "admitted"


def _kb_unavailable(module):
    return patch.object(module, "get_or_create_knowledge_base", new=AsyncMock(return_value=None))


async def _knowledge_org_update(role):
    with _kb_unavailable(knowledge_organization):
        return await _outcome(knowledge_organization.update_organization_policy(MagicMock(), MagicMock(), _user(role)))


async def _knowledge_org_cleanup(role):
    with _kb_unavailable(knowledge_organization):
        return await _outcome(knowledge_organization.cleanup_organization_knowledge(MagicMock(), _user(role), 30))


async def _audit_log(role):
    with _kb_unavailable(knowledge_audit):
        return await _outcome(knowledge_audit.get_organization_audit_log(MagicMock(), _user(role), MagicMock()))


async def _audit_report(role):
    report = MagicMock(organization_id="org-1")
    with _kb_unavailable(knowledge_audit):
        return await _outcome(knowledge_audit.generate_compliance_report(report, MagicMock(), _user(role)))


async def _audit_summary(role):
    with _kb_unavailable(knowledge_audit):
        return await _outcome(knowledge_audit.get_compliance_summary(MagicMock(), _user(role), 30))


async def _chat_list_org(role):
    validator = MagicMock(get_org_sessions=AsyncMock(return_value=[]))
    history = MagicMock(list_sessions_fast=AsyncMock(return_value=[]))
    return await _outcome(chat_sessions._list_org_sessions(_user(role), validator, history, "req"))


async def _chat_clear_checkpoints(role):
    graph = types.ModuleType("chat_workflow.graph")
    graph.delete_thread_checkpoints = AsyncMock()
    with patch.dict(sys.modules, {"chat_workflow.graph": graph}):
        return await _outcome(chat_sessions.clear_session_checkpoints("s1", _user(role)))


_SITES = [
    _knowledge_org_update,
    _knowledge_org_cleanup,
    _audit_log,
    _audit_report,
    _audit_summary,
    _chat_list_org,
    _chat_clear_checkpoints,
]


@pytest.mark.asyncio
@pytest.mark.parametrize("site", _SITES, ids=lambda s: s.__name__.lstrip("_"))
@pytest.mark.parametrize("role", _ADMITTED)
async def test_the_admin_family_clears_the_role_gate(site, role):
    assert await site(role) == "admitted"


@pytest.mark.asyncio
@pytest.mark.parametrize("site", _SITES, ids=lambda s: s.__name__.lstrip("_"))
@pytest.mark.parametrize("role", _REFUSED)
async def test_other_roles_are_refused(site, role):
    assert await site(role) == "refused"
