# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Library and built-in template import: projects and work items, via the one portability implementation (#20472)."""

import uuid
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from .portability import PortabilityService


async def import_template_entities(
    session: AsyncSession, template_json: Dict[str, Any], company_id: uuid.UUID, counts: Dict[str, int]
) -> List[Dict[str, Any]]:
    """Create the template's projects and work items; update ``counts`` to what was created.

    Uses the same project and work-item import as ``PortabilityService.execute_import`` so the hierarchy
    rules, parent remapping and skip reporting are one implementation. Returns the skipped items with reasons.
    """
    svc = PortabilityService(session=session)
    created: Dict[str, Any] = {"projects": [], "work_items": []}
    skipped: Dict[str, Any] = {"work_items": []}
    project_ids = await svc._import_projects(template_json, company_id, created)
    skipped_items = await svc._import_seed_items(template_json, company_id, project_ids, created, skipped, [])
    counts.update({key: len(ids) for key, ids in created.items()})
    return skipped_items
