# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Knowledge resource operations."""

from __future__ import annotations

from typing import Any

from ..client import AutoBotClient
from ..models import DataResponse, KnowledgeAddResult, KnowledgeSearchResult, KnowledgeStats


class KnowledgeResource:
    def __init__(self, client: AutoBotClient) -> None:
        self._c = client

    async def stats(self) -> DataResponse[KnowledgeStats]:
        raw = await self._c.get("/knowledge_base/stats")
        return DataResponse[KnowledgeStats].model_validate(raw)

    async def add_text(self, text: str, category: str | None = None, source: str | None = None) -> DataResponse[KnowledgeAddResult]:
        body: dict[str, Any] = {"text": text}
        if category:
            body["category"] = category
        if source:
            body["source"] = source
        raw = await self._c.post("/knowledge_base/add_text", body)
        return DataResponse[KnowledgeAddResult].model_validate(raw)

    async def search(self, query: str, limit: int = 10, category: str | None = None) -> DataResponse[KnowledgeSearchResult]:
        raw = await self._c.get("/knowledge_base/search", query=query, limit=limit, category=category)
        return DataResponse[KnowledgeSearchResult].model_validate(raw)

    async def get_entries(self, limit: int = 50, offset: int = 0, category: str | None = None) -> DataResponse[KnowledgeSearchResult]:
        raw = await self._c.get("/knowledge_base/entries", limit=limit, offset=offset, category=category)
        return DataResponse[KnowledgeSearchResult].model_validate(raw)
