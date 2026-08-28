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

None of these four routes returns a ``DataResponse`` envelope -- each returns
its document flat. Parsing them as ``DataResponse[X]`` succeeded anyway,
because every envelope field carries a default, and handed the caller
``success=True, data=None`` with no exception and no log line (#15116). Three of
them carry a top-level ``message``, which bound to the *envelope's* ``message``
and made the empty result read as a populated one. They are parsed as what they
are.
"""

from __future__ import annotations

from typing import Any

from ..client import AutoBotClient
from ..defaults import DEFAULT_OFFSET, DEFAULT_PAGE_SIZE, DEFAULT_SEARCH_LIMIT
from ..models import KnowledgeAddResult, KnowledgeEntries, KnowledgeSearchResult, KnowledgeStats


class KnowledgeResource:
    def __init__(self, client: AutoBotClient) -> None:
        self._c = client

    async def stats(self) -> KnowledgeStats:
        raw = await self._c.get("/knowledge_base/stats")
        return KnowledgeStats.model_validate(raw)

    async def add_text(self, text: str, category: str | None = None, source: str | None = None) -> KnowledgeAddResult:
        body: dict[str, Any] = {"text": text}
        if category:
            body["category"] = category
        if source:
            body["source"] = source
        raw = await self._c.post("/knowledge_base/add_text", body)
        return KnowledgeAddResult.model_validate(raw)

    async def search(self, query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> KnowledgeSearchResult:
        """Search the knowledge base.

        The route takes its arguments in a JSON body, and names the result cap
        ``max_results``. It has no category filter — use :meth:`get_entries`,
        whose route does.
        """
        body: dict[str, Any] = {"query": query, "max_results": limit}
        raw = await self._c.post("/knowledge_base/search", body)
        return KnowledgeSearchResult.model_validate(raw)

    async def get_entries(
        self, limit: int = DEFAULT_PAGE_SIZE, offset: int = DEFAULT_OFFSET, category: str | None = None
    ) -> KnowledgeEntries:
        """Stored entries, newest first.

        The response has its own shape -- ``entries``/``next_cursor``/``count``/
        ``has_more`` -- sharing no field with the search route, which the SDK
        modelled it with (#15118).
        """
        raw = await self._c.get("/knowledge_base/entries", limit=limit, offset=offset, category=category)
        return KnowledgeEntries.model_validate(raw)
