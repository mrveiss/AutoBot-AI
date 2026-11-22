# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Redis session access shared by the session migration scripts (#18557).

``migrate_sessions_user_attribution``, ``cleanup_orphaned_sessions``,
``backfill_activity_user_ids`` and ``validate_migration`` each carried their own
copy of ``connect_redis`` (and the first three of ``get_all_sessions``; the first
two of ``get_session_data``). This sibling module hosts them once. It is imported
by name, not as a package member, because every script here is run directly and so
has its own directory on ``sys.path``; each caller puts ``autobot_shared`` on the
path first, exactly as it already did for its own imports.
"""

import json
import logging
from typing import Dict, List, Optional

from autobot_shared.redis_client import get_async_redis_client


class RedisConnectMixin:
    """``connect_redis``. Host classes own ``self.redis_client``.

    Log records keep the host script's logger name (``type(self).__module__``),
    so output is unchanged. Three layers, because the scripts need different
    subsets: connect only (``validate_migration``), plus listing
    (``backfill_activity_user_ids``), plus single-session reads (the other two).
    """

    redis_client = None

    @property
    def _log(self) -> logging.Logger:
        return logging.getLogger(type(self).__module__)

    async def connect_redis(self) -> None:
        """Connect to Redis database"""
        try:
            self.redis_client = await get_async_redis_client(database="main")
            await self.redis_client.ping()
            self._log.info("Connected to Redis successfully")
        except Exception as e:
            self._log.error("Failed to connect to Redis: %s", e)
            raise


class SessionListMixin(RedisConnectMixin):
    """``get_all_sessions`` over ``chat:session:*``."""

    async def get_all_sessions(self) -> List[str]:
        """Get all session IDs from Redis.

        Returns:
            List of session IDs
        """
        try:
            keys = await self.redis_client.keys("chat:session:*")
            session_ids = [key.decode("utf-8").split(":", 2)[2] for key in keys]
            self._log.info("Found %s sessions", len(session_ids))
            return session_ids
        except Exception as e:
            self._log.error("Failed to get sessions: %s", e)
            return []


class SessionDataMixin(SessionListMixin):
    """``get_session_data`` for one ``chat:session:<id>`` key."""

    # Level at which a failed single-session read is logged; a caller scanning
    # many possibly-stale keys lowers it so one bad key is not an error line.
    SESSION_READ_FAILURE_LEVEL = logging.ERROR

    async def get_session_data(self, session_id: str) -> Optional[Dict]:
        """Get session data from Redis.

        Args:
            session_id: Session ID to retrieve

        Returns:
            Session data dictionary or None
        """
        try:
            data = await self.redis_client.get(f"chat:session:{session_id}")
            if not data:
                return None
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            return json.loads(data)
        except Exception as e:
            self._log.log(self.SESSION_READ_FAILURE_LEVEL, "Failed to get session %s: %s", session_id, e)
            return None
