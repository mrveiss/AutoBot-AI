# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Knowledge resource operations.

Paths are written without the ``/api`` root — ``AutoBotClient`` adds it.

``/knowledge_base/search`` is served by POST only; the SDK asked for it with
GET, which answers 405 even once the prefix is right (#15053). The verb is
part of the route, so it is corrected here rather than left to 404's quieter
cousin.
"""

from __future__ import annotations

from typing import Any

from ..client import AutoBotClient
from ..defaults import DEFAULT_OFFSET, DEFAULT_PAGE_SIZE, DEFAULT_SEARCH_LIMIT
from ..models import DataResponse, KnowledgeAddResult, KnowledgeSearchResult, KnowledgeStats


class KnowledgeResource:
    def __init__(self, client: AutoBotClient) -> None:
        self._c = client

    async def stats(self) -> DataResponse[KnowledgeStats]:
        raw = await self._c.get("/knowledge_base/stats")
        return DataResponse[KnowledgeStats].model_validate(raw)

    async def add_text(
        self, text: str, category: str | None = None, source: str | None = None
    ) -> DataResponse[KnowledgeAddResult]:
        body: dict[str, Any] = {"text": text}
        if category:
            body["category"] = category
        if source:
            body["source"] = source
        raw = await self._c.post("/knowledge_base/add_text", body)
        return DataResponse[KnowledgeAddResult].model_validate(raw)

    async def search(self, query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> DataResponse[KnowledgeSearchResult]:
        """Search the knowledge base.

        The route takes its arguments in a JSON body, and names the result cap
        ``max_results``. It has no category filter — use :meth:`get_entries`,
        whose route does.
        """
        body: dict[str, Any] = {"query": query, "max_results": limit}
        raw = await self._c.post("/knowledge_base/search", body)
        return DataResponse[KnowledgeSearchResult].model_validate(raw)

    async def get_entries(
        self, limit: int = DEFAULT_PAGE_SIZE, offset: int = DEFAULT_OFFSET, category: str | None = None
    ) -> DataResponse[KnowledgeSearchResult]:
        raw = await self._c.get("/knowledge_base/entries", limit=limit, offset=offset, category=category)
        return DataResponse[KnowledgeSearchResult].model_validate(raw)
