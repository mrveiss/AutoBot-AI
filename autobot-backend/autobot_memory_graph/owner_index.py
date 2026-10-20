# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Index the entity owner fields as RediSearch TAGs (#18825).

``FT.CREATE`` in ``semantic_search`` is skipped when ``memory_entity_idx`` already exists,
so the owner fields are added with ``FT.ALTER ... SCHEMA ADD``. That only extends the
index definition (RediSearch re-indexes existing documents); it rewrites no stored
entity. A deployment whose index lacks the fields degrades to the scan fallback, which
applies the same owner filter in Python, so reads fail closed either way.
"""

from typing import Any

from autobot_shared.logging_manager import get_logger

from .owner_scope import OWNER_ORG_FIELD, OWNER_USER_FIELD

logger = get_logger(__name__)

ENTITY_INDEX_NAME = "memory_entity_idx"


async def ensure_owner_fields(redis_client: Any) -> None:
    """Add the owner TAG fields to the entity index; idempotent, never raises."""
    for field in (OWNER_USER_FIELD, OWNER_ORG_FIELD):
        try:
            await redis_client.execute_command(
                "FT.ALTER", ENTITY_INDEX_NAME, "SCHEMA", "ADD", f"$.{field}", "AS", field, "TAG"
            )
            logger.info("Indexed %s on %s", field, ENTITY_INDEX_NAME)
        except Exception as exc:
            if "duplicate" in str(exc).lower():
                continue
            logger.warning("Could not index %s on %s: %s", field, ENTITY_INDEX_NAME, exc)
