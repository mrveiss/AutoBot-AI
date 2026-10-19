# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Route guards for the service start/stop/restart family (#18359).

``service_name`` on ``/nodes/{node_id}/services/{service_name}/{start,stop,restart}`` and
``/fleet/services/{service_name}/{start,stop,restart}`` is a URL path parameter that ends up in
a remote ``systemctl`` command. Three layers, outermost first:

1. ``require_service_management`` -- admin/operator only (``Permission.SERVICE_MANAGEMENT``),
   the same dependency ``main.py`` mounts router-wide; repeated per route so the gate does not
   depend on how the router is mounted.
2. the name must be a valid systemd unit name (``validate_unit_name``, 422 otherwise);
3. on a node route, the node must already have a service record of that name (404 otherwise).

The executor (``services/service_restart.py``) validates and quotes again; this is the
user-facing refusal, that is the backstop.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.database import Service
from models.fleet_schemas import FleetServiceActionResponse
from models.schemas import ServiceActionResponse, ServiceLogsResponse
from services.auth import require_service_management
from services.database import get_db
from services.unit_names import validate_journal_since, validate_unit_name


def valid_service_name_or_422(service_name: str) -> str:
    """Dependency: ``service_name`` must be a valid systemd unit name."""
    try:
        return validate_unit_name(service_name)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="service_name is not a valid systemd unit name",
        ) from None


async def known_node_service_or_404(
    node_id: str,
    service_name: Annotated[str, Depends(valid_service_name_or_422)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> str:
    """Dependency: *node_id* must already have a service record named *service_name*."""
    result = await db.execute(
        select(Service.id).where(Service.node_id == node_id, Service.service_name == service_name).limit(1)
    )
    if result.first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found on node")
    return service_name


# Splatted into the route decorators (``@router.post(path, **NODE_SERVICE_ACTION_ROUTE)``): the
# response model plus the guard dependencies, in one place so the six routes cannot drift apart.
NODE_SERVICE_ACTION_ROUTE = {
    "response_model": ServiceActionResponse,
    "dependencies": [Depends(require_service_management), Depends(known_node_service_or_404)],
}
FLEET_SERVICE_ACTION_ROUTE = {
    # The fleet model: with the base one, FastAPI would strip ``diagnostics`` on the wire (#18714).
    "response_model": FleetServiceActionResponse,
    "dependencies": [Depends(require_service_management), Depends(valid_service_name_or_422)],
}


#: The route declares ``since`` too, but FastAPI documents the dependency's copy, so the
#: description lives here or the generated SLM types lose it (#18359).
SINCE_QUERY_DESCRIPTION = "Time period, e.g. '1h', '30m'"


def valid_since_or_422(since: str | None = Query(None, description=SINCE_QUERY_DESCRIPTION)) -> str | None:
    """Dependency: the optional ``since`` window must be an accepted ``journalctl --since`` form."""
    try:
        return validate_journal_since(since) if since else since
    except ValueError:
        raise HTTPException(status_code=422, detail="since is not an accepted journalctl time form") from None


# The logs route reads, not controls, so it keeps its router-level gate and takes only the validators;
# it holds no service-record lookup of its own, so there is no 404 here (the journal is read by name).
SERVICE_LOGS_ROUTE = {
    "response_model": ServiceLogsResponse,
    "dependencies": [Depends(valid_service_name_or_422), Depends(valid_since_or_422)],
}
