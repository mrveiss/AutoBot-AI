# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Session resource operations.

Paths are written without the ``/api`` root — ``AutoBotClient`` adds it.
The chat-sessions router registers with an empty mount prefix, so these
paths need nothing beyond that root (#15053).

``list()`` used to send ``limit`` and ``offset``. ``GET /chat/sessions`` accepts
neither -- it declares ``scope`` and ``team_id`` and returns the caller's whole
list -- so FastAPI dropped both and the caller's paging silently did not apply
(#15119, the same shape the issue reported for ``knowledge.get_entries`` and the
two analytics methods). The two parameters the route does take are offered
instead. ``get()`` gains the route's real ``page``/``per_page``, which the SDK
could not reach at all.
"""

from __future__ import annotations

from typing import Any

from ..client import AutoBotClient
from ..models import (
    DataResponse,
    SessionCreate,
    SessionDelete,
    SessionList,
    SessionMessages,
    SessionUpdate,
)


class SessionsResource:
    def __init__(self, client: AutoBotClient) -> None:
        self._c = client

    async def list(self, scope: str | None = None, team_id: str | None = None) -> DataResponse[SessionList]:
        """Chat sessions visible to the caller.

        ``scope`` is ``"user"`` (the route's default), ``"org"``, ``"team"`` or
        ``"shared"``; ``team_id`` is required when ``scope="team"``. The route
        is not paginated, which is why there is no ``limit`` or ``offset`` here
        (#15119).
        """
        raw = await self._c.get("/chat/sessions", scope=scope, team_id=team_id)
        return DataResponse[SessionList].model_validate(raw)

    async def get(
        self, session_id: str, page: int | None = None, per_page: int | None = None
    ) -> DataResponse[SessionMessages]:
        """One session's messages, page by page.

        ``page``/``per_page`` are the route's own parameter names; omitting
        either leaves the route's default in force rather than restating it
        here, so the two cannot drift apart.
        """
        raw = await self._c.get(f"/chat/sessions/{session_id}", page=page, per_page=per_page)
        return DataResponse[SessionMessages].model_validate(raw)

    async def create(
        self, title: str | None = None, metadata: dict[str, Any] | None = None
    ) -> DataResponse[SessionCreate]:
        body: dict[str, Any] = {}
        if title:
            body["title"] = title
        if metadata:
            body["metadata"] = metadata
        raw = await self._c.post("/chat/sessions", body)
        return DataResponse[SessionCreate].model_validate(raw)

    async def update(self, session_id: str, **fields: Any) -> DataResponse[SessionUpdate]:
        raw = await self._c.put(f"/chat/sessions/{session_id}", fields)
        return DataResponse[SessionUpdate].model_validate(raw)

    async def delete(self, session_id: str) -> DataResponse[SessionDelete]:
        raw = await self._c.delete(f"/chat/sessions/{session_id}")
        return DataResponse[SessionDelete].model_validate(raw)
