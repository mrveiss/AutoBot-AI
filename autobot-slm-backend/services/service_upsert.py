# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ONE upsert of a discovered ``Service`` row (#19021).

Two ingest paths store services a node reports: the scan endpoint (``api/services.py``, Ansible
``service_facts``) and the heartbeat sync (``services/reconciler.py``, an agent heartbeat dict). They
differ in how they MAP their input to columns, not in what an upsert is. This module owns the shared
part -- the unit-name guard (#19005), the ``(node_id, service_name)`` lookup, the create-or-update
branch and the categorisation of a new row. A caller supplies only its own field mapping as two
callbacks, so a third ingest path gets the guard by construction instead of having to remember it.

Transaction ownership stays with the caller: this never commits or flushes, and opens no savepoint.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import Service
from services.service_categorizer import categorize_service
from services.unit_names import discovered_unit_name_ok

R = TypeVar("R")


@dataclass(frozen=True)
class ServiceUpsert(Generic[R]):
    """Outcome of one accepted upsert: the row, whether it was created, and the update callback's result."""

    service: Service
    created: bool
    update_result: R | None = None


async def upsert_service(
    db: AsyncSession,
    node_id: str,
    service_name: str,
    *,
    update: Callable[[Service], R],
    create: Callable[[str], Service],
) -> ServiceUpsert[R] | None:
    """Create or update the ``Service`` row for ``(node_id, service_name)``; ``None`` if the name is refused.

    ``update(existing_row)`` mutates an existing row and its return value is handed back as
    ``update_result``. ``create(category)`` builds the new row (``category`` is
    ``categorize_service(service_name)``); it is ``db.add``-ed here. Exactly one of the two runs.
    """
    if not discovered_unit_name_ok(node_id, service_name):  # #19005
        return None
    result = await db.execute(
        select(Service).where(
            Service.node_id == node_id,
            Service.service_name == service_name,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return ServiceUpsert(existing, False, update(existing))
    row = create(categorize_service(service_name))
    db.add(row)
    return ServiceUpsert(row, True)
