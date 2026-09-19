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
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from api.user_management.dependencies import (
    get_current_user,
    get_db_session,
    require_platform_admin,
    require_reporting_line_write,
)
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
    carries no subject id, so there is no reporting-line row it could key a lookup
    on even if it wanted to -- the hierarchy is structurally unreachable from
    here, not merely unconsulted by convention.

    This docstring used to add "and no DB session" to that list, which #15805
    corrected: ``context`` reached one transitively. Only the wording changed --
    the assertions below are byte-identical to #15765's, because the escalation
    guarantee they encode is exactly what must survive that correction.
    """
    manager_current_user = {
        "role": "user",
        "manages": [str(uuid.uuid4()), str(uuid.uuid4())],
        "is_manager": True,
    }

    with pytest.raises(HTTPException) as exc_info:
        await require_reporting_line_write(context=_context(), current_user=manager_current_user)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


def test_the_dependency_accepts_no_subject_id():
    """Structural proof backing the escalation test above.

    What a signature can prove is that **no subject/target user id** is in
    scope: there is no id a reporting-line lookup could be keyed on, so the
    escalation is closed by construction rather than by an implementation choice
    a later edit could quietly undo.

    What it cannot prove is that no DB session is reachable, and this test used
    to claim it did (#15805). ``context`` reaches one transitively --
    ``require_reporting_line_write`` -> ``_tenant_context_for_reporting_line_write``
    -> ``get_tenant_context`` -> ``get_db_session`` -- so a parameter absent from
    a signature is not absent from the dependency graph one hop down. Whether a
    session is *acquired* before the refusal is a behavioural property, measured
    by counting acquisitions in
    ``test_an_unauthorised_reporting_line_caller_acquires_no_session`` below. It
    cannot be read off this signature at all, which is why asserting the shape
    here and the effect there are two different jobs.
    """
    import inspect

    params = set(inspect.signature(require_reporting_line_write).parameters)

    assert params == {"context", "current_user"}, (
        f"require_reporting_line_write gained a parameter ({params}) that could carry a "
        "subject id -- re-check it cannot be used to derive the grant from hierarchy"
    )


# ---------------------------------------------------------------------------
# #15805 -- the refusal must not cost a database session.
#
# Every assertion below is on an EFFECT: how many times the session dependency
# was entered for one request, and what the caller actually received. Inspecting
# the ``Dependant`` tree would prove the wiring and nothing about the behaviour,
# and asserting a bare 403 would prove almost nothing either -- ``403`` is what
# a missing org membership, a missing role and a missing grant all return, so
# each refusal is pinned to its own detail string.
# ---------------------------------------------------------------------------

_UNUSABLE_SESSION = object()
"""Stands in for the session. Nothing on these paths may touch it: the requests
below carry no ``X-Organization-Id`` header and no ``company_id`` param, so
``get_tenant_context`` never runs its membership query."""


def _app_gated_by(gate, current_user: dict):
    """Mount *gate* on one route and count session acquisitions for a request.

    Returns ``(client, acquisitions)``. ``acquisitions`` grows by one every time
    ``get_db_session`` is entered, which is precisely the cost #15805 is about.
    """
    acquisitions: list[str] = []

    async def _counted_session():  # noqa: ANN202
        acquisitions.append("acquired")
        yield _UNUSABLE_SESSION

    app = FastAPI()
    app.dependency_overrides[get_db_session] = _counted_session
    app.dependency_overrides[get_current_user] = lambda: current_user

    @app.get("/gated")
    async def _gated(context: TenantContext = Depends(gate)):  # noqa: ANN202
        return {"user_id": str(context.user_id), "is_platform_admin": context.is_platform_admin}

    return TestClient(app, raise_server_exceptions=False), acquisitions


def test_an_unauthorised_reporting_line_caller_acquires_no_session():
    """The defect #15805 records: a 403 that costs a connection from the pool."""
    user_id = uuid.uuid4()
    client, acquisitions = _app_gated_by(require_reporting_line_write, {"role": "user", "user_id": str(user_id)})

    response = client.get("/gated")

    assert response.status_code == status.HTTP_403_FORBIDDEN, response.text
    assert response.json()["detail"] == "admin.reporting_line.write permission required", response.text
    assert acquisitions == [], f"the refusal acquired {len(acquisitions)} session(s); it must acquire none"


def test_an_authorised_reporting_line_caller_still_gets_its_session_and_context():
    """The other half of the pair: refusing early must not starve the happy path.

    Without this, deleting tenant resolution outright would satisfy the test
    above -- 'no session acquired' is trivially true for a dependency that
    resolves nothing. The echoed ``user_id`` is what shows a real
    ``TenantContext`` reached the route, not merely that a 200 was produced.
    """
    user_id = uuid.uuid4()
    client, acquisitions = _app_gated_by(require_reporting_line_write, {"role": "admin", "user_id": str(user_id)})

    response = client.get("/gated")

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()["user_id"] == str(user_id), response.text
    assert acquisitions == ["acquired"], f"expected exactly one session acquisition, got {len(acquisitions)}"


def test_an_unauthorised_platform_admin_caller_acquires_no_session():
    """``require_platform_admin`` shares the shape (#15805 acceptance criterion 5).

    ``TenantContext.is_platform_admin`` is derived from the JWT alone, so this
    gate is decidable from claims for exactly the same reason.
    """
    user_id = uuid.uuid4()
    client, acquisitions = _app_gated_by(require_platform_admin, {"role": "user", "user_id": str(user_id)})

    response = client.get("/gated")

    assert response.status_code == status.HTTP_403_FORBIDDEN, response.text
    assert response.json()["detail"] == "Platform admin privileges required", response.text
    assert acquisitions == [], f"the refusal acquired {len(acquisitions)} session(s); it must acquire none"


def test_an_authorised_platform_admin_still_gets_its_session_and_context():
    user_id = uuid.uuid4()
    client, acquisitions = _app_gated_by(require_platform_admin, {"role": "admin", "user_id": str(user_id)})

    response = client.get("/gated")

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json() == {"user_id": str(user_id), "is_platform_admin": True}, response.text
    assert acquisitions == ["acquired"], f"expected exactly one session acquisition, got {len(acquisitions)}"
