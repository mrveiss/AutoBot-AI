# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Self-model API: read the entities, and accept the backend's producer observations (#22277).

Nested onto ``nodes_router`` in ``api/__init__.py`` (the move ``api/capability_profile.py`` made)
so it inherits that router's include-level auth. Writing further requires the backend's internal service key
(``require_internal_api_key``) and a known producer ``source``. The read side is what the backend's chat tool
queries; the write side takes only ``declared`` / ``probed_*`` claims -- ``absent`` and ``stale`` are derived
here, never asserted.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from autobot_shared.auth.internal_api_key import require_internal_api_key
from autobot_shared.self_model_constants import PRODUCER_SOURCES
from models.self_model import self_model_entities as entities
from services.auth import get_current_user
from services.database import get_db
from services.self_model_reconcile import (
    KINDS,
    OBSERVED_STATUSES,
    STATUSES,
    Observation,
    entity_key,
    unavailable_because,
)
from services.self_model_store import (
    apply_observations,
    load_rows,
    node_ids_by_host,
    revision,
    rows_for_response,
    sweep_stale,
)

router = APIRouter(prefix="/self-model", tags=["self-model"])

MAX_ENTITIES = 500
DEFAULT_ENTITIES = 100
MAX_OBSERVATIONS = 20000
MAX_HOSTS = 100


class ParentRef(BaseModel):
    kind: str
    name: str


class ObservationIn(BaseModel):
    kind: str
    name: str = Field(min_length=1, max_length=255)
    status: str
    parent: Optional[ParentRef] = None
    node_id: Optional[str] = None
    version: Optional[str] = None
    attrs: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        if value not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        return value

    @field_validator("status")
    @classmethod
    def _claimable_status(cls, value: str) -> str:
        if value not in OBSERVED_STATUSES:
            raise ValueError(f"a producer may claim only {OBSERVED_STATUSES}")
        return value

    def to_observation(self) -> Observation:
        parent = entity_key(self.parent.kind, self.parent.name) if self.parent else None
        return Observation(self.kind, self.name, self.status, parent, self.node_id, self.version, self.attrs)


class ObservationBatch(BaseModel):
    """One producer's complete claim about the entities of ``scope_kinds``."""

    source: str = Field(min_length=1, max_length=64)
    scope_kinds: List[str]
    observations: List[ObservationIn] = Field(max_length=MAX_OBSERVATIONS)

    @field_validator("source")
    @classmethod
    def _known_source(cls, value: str) -> str:
        if value not in PRODUCER_SOURCES:
            raise ValueError(f"source must be one of {PRODUCER_SOURCES}")
        return value


class IngestResult(BaseModel):
    upserted: int
    changed: int
    revision: int


@router.post("/observations", response_model=IngestResult, dependencies=[Depends(require_internal_api_key)])
async def post_observations(
    batch: ObservationBatch,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IngestResult:
    """Fold a producer's batch into the model; entities it owns and no longer lists become ``absent``."""
    now = datetime.now(timezone.utc)
    observed = [item.to_observation() for item in batch.observations]
    plan = await apply_observations(db, batch.source, batch.scope_kinds, observed, now)
    return IngestResult(upserted=len(plan.upserts), changed=len(plan.history), revision=await revision(db))


def _filters(kind: Optional[str], name: Optional[str], node_id: Optional[str], status: Optional[str]) -> list:
    conditions = []
    if kind:
        conditions.append(entities.c.kind == kind)
    if name:
        escaped = name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(entities.c.name.ilike(f"%{escaped}%", escape="\\"))
    if node_id:
        conditions.append(entities.c.node_id == node_id)
    if status:
        conditions.append(entities.c.status == status)
    return conditions


@router.get("/entities")
async def list_entities(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    kind: Annotated[Optional[str], Query(pattern="^(" + "|".join(KINDS) + ")$")] = None,
    name: Annotated[Optional[str], Query(max_length=255)] = None,
    node_id: Optional[str] = None,
    status: Annotated[Optional[str], Query(pattern="^(" + "|".join(STATUSES) + ")$")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_ENTITIES)] = DEFAULT_ENTITIES,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Dict[str, Any]:
    """Entities matching the filters, each with its status, ``last_seen`` and whether its commands are present.

    ``total`` counts every match; ``offset`` pages through them, so a caller can tell a short page from a full set.
    """
    await sweep_stale(db, datetime.now(timezone.utc))
    found = await load_rows(db, *_filters(kind, name, node_id, status))
    rows = rows_for_response(found.values())[offset : offset + limit]
    needing = {entity_key("node", r["node_id"]) for r in rows if r["node_id"] and r["attrs"].get("requires")}
    commands = await load_rows(db, entities.c.parent_key.in_(needing)) if needing else {}
    for row in rows:
        missing = unavailable_because(row, commands)
        row["available"] = not missing
        row["unavailable_because"] = missing
    return {"revision": await revision(db), "total": len(found), "entities": rows}


@router.get("/node-ids")
async def node_ids(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    hosts: Annotated[str, Query(min_length=1, max_length=4096, description="Comma-separated host addresses")],
) -> Dict[str, str]:
    """The SLM node id of each given host address that is a managed node (the mapping ``rename_hosts`` applies).

    A backend fact names its host by address; the self-model keys its entities by node id. This is the one
    translation, so a fact's link to a ``command`` entity cannot disagree with the entity the SLM wrote.
    """
    wanted = {h.strip() for h in hosts.split(",") if h.strip()}
    if len(wanted) > MAX_HOSTS:
        raise HTTPException(status_code=422, detail=f"at most {MAX_HOSTS} hosts per request")
    return await node_ids_by_host(db, wanted)
