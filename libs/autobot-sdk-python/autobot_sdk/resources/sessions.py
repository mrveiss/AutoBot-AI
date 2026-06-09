# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Session resource operations."""

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

    async def list(self, limit: int = 50, offset: int = 0) -> DataResponse[SessionList]:
        raw = await self._c.get("/chat/sessions", limit=limit, offset=offset)
        return DataResponse[SessionList].model_validate(raw)

    async def get(self, session_id: str) -> DataResponse[SessionMessages]:
        raw = await self._c.get(f"/chat/sessions/{session_id}")
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
