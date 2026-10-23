# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Owner scoping for the security-assessment memory-graph entities (#18825).

Assessments are admin-gated, org-sensitive platform data written on nobody's personal
behalf. They are stamped ``OwnerScope.system()`` -- invisible to every user-scoped read
(Graph-RAG, chat context) -- and read back through the explicit unscoped sentinel, which is
safe only because every caller of this service sits behind an admin check.
"""

from typing import Any, Dict, List

from autobot_memory_graph.owner_scope import UNSCOPED_ALL_USERS, OwnerScope

_PLATFORM_OWNER = OwnerScope.system()


class PlatformGraphAccess:
    """Mixin: owner-stamped writes and explicitly unscoped reads against ``self._memory_graph``."""

    async def _create_platform_entity(self, **fields: Any) -> Dict[str, Any]:
        """Create an entity owned by the platform (never visible to a user-scoped read)."""
        return await self._memory_graph.create_entity(owner=_PLATFORM_OWNER, **fields)

    async def _search_all_owners(self, **query: Any) -> List[Dict[str, Any]]:
        """Admin-gated read across owners -- the unscoped sentinel is deliberate (see module doc)."""
        return await self._memory_graph.search_entities(owner=UNSCOPED_ALL_USERS, **query)

    async def _related_all_owners(self, **query: Any) -> List[Dict[str, Any]]:
        """Admin-gated traversal across owners -- the unscoped sentinel is deliberate."""
        return await self._memory_graph.get_related_entities(owner=UNSCOPED_ALL_USERS, **query)
