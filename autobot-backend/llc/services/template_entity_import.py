# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Library and built-in template import: projects and work items, via the one shared import (#20472)."""

import uuid
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from .portability import TemplateImportError
from .work_item_import import import_template_work


async def import_template_entities(
    session: AsyncSession, template_json: Dict[str, Any], company_id: uuid.UUID, counts: Dict[str, int]
) -> List[Dict[str, Any]]:
    """Create the template's projects and work items; update ``counts`` to what was created.

    Runs in a savepoint, and an invalid value in the template (a bad type or priority) rolls it back and
    raises ``TemplateImportError``, as ``PortabilityService.execute_import`` does. Returns the skipped items.
    """
    created: Dict[str, Any] = {"projects": [], "work_items": []}
    sp = await session.begin_nested()
    try:
        skipped_items = await import_template_work(session, template_json, company_id, created, {"work_items": []}, [])
        await sp.commit()
    except Exception as exc:
        await sp.rollback()
        raise TemplateImportError(f"Import rolled back: {exc}") from exc
    counts.update({key: len(ids) for key, ids in created.items()})
    return skipped_items
