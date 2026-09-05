# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for ``require_reporting_line_write`` (#15765).

The permission gates every path that changes a reporting relationship (#15738:
a permission that exists and gates nothing is the defect). The escalation case
below is the one that matters most: the check must never be satisfiable by
hierarchy position, or restructuring becomes self-granting -- become someone's
manager, gain authority over them, restructure further (#15765's design note).
"""

import uuid

import pytest
from fastapi import HTTPException, status

from api.user_management.dependencies import require_reporting_line_write
from user_management.services import TenantContext


def _context() -> TenantContext:
    return TenantContext(user_id=uuid.uuid4(), is_platform_admin=False)


@pytest.mark.asyncio
async def test_a_caller_holding_the_permission_passes():
    """``admin`` holds every ``Permission`` member, ``admin.reporting_line.write``
    included (``roles_are_canonical_test.test_admin_holds_every_permission_from_its_own_entry``),
    so a caller whose role is ``admin`` is the explicit-grant case."""
    context = _context()
    current_user = {"role": "admin"}

    result = await require_reporting_line_write(context=context, current_user=current_user)

    assert result is context


@pytest.mark.asyncio
async def test_a_caller_without_the_permission_is_rejected():
    current_user = {"role": "user"}

    with pytest.raises(HTTPException) as exc_info:
        await require_reporting_line_write(context=_context(), current_user=current_user)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_a_manager_with_no_explicit_grant_is_rejected():
    """The escalation case: hierarchy position must not be derivable into the grant.

    ``current_user`` here carries manager-shaped signal -- a caller who manages
    other people, attested by a hierarchy-flavoured field a buggy implementation
    might consult -- and still holds no platform role that grants
    ``admin.reporting_line.write``. The permission must deny exactly as it would
    for anyone else with no grant, proving this is a positive rejection, not an
    accidental one: the dependency's own signature (``context``, ``current_user``)
    carries no subject id and no DB session, so there is no reporting-line table
    it could consult even if it wanted to -- the hierarchy is structurally
    unreachable from here, not merely unconsulted by convention.
    """
    manager_current_user = {
        "role": "user",
        "manages": [str(uuid.uuid4()), str(uuid.uuid4())],
        "is_manager": True,
    }

    with pytest.raises(HTTPException) as exc_info:
        await require_reporting_line_write(context=_context(), current_user=manager_current_user)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


def test_the_dependency_has_no_pathway_to_reporting_line_data():
    """Structural proof backing the escalation test above.

    No subject/target user id and no DB session are accepted, so there is
    nothing in scope from which a reporting-line lookup could be performed --
    the escalation this guards against is closed by construction, not by an
    implementation choice that a later edit could quietly undo.
    """
    import inspect

    params = set(inspect.signature(require_reporting_line_write).parameters)

    assert params == {"context", "current_user"}, (
        f"require_reporting_line_write gained a parameter ({params}) that could carry a "
        "subject id or a session -- re-check it cannot be used to derive the grant from hierarchy"
    )
