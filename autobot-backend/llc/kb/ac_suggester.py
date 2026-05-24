# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""AC suggester — RAG over company policies + past PBIs (GH#8240).

On PBI/Story creation, suggests draft acceptance criteria by running parallel
RAG queries over company standards and similar completed items, then asking
the LLM to synthesise 3-6 testable ACs.

Results are cached in Redis for 5 minutes, keyed by sha256(title+description),
to avoid repeated LLM calls for identical inputs during rapid backlog grooming.
"""

import asyncio
import hashlib
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# #8240: suggestion cache TTL (seconds).
# Override via AUTOBOT_AC_SUGGESTER_CACHE_TTL for environments where 5 min
# is too short (low-traffic dev) or too long (high-churn grooming sessions).
_DEFAULT_CACHE_TTL = 300


def _resolve_cache_ttl() -> int:
    raw = os.environ.get("AUTOBOT_AC_SUGGESTER_CACHE_TTL")
    if raw is None:
        return _DEFAULT_CACHE_TTL
    try:
        val = int(raw)
        if val > 0:
            return val
    except ValueError:
        pass
    logger.warning(
        "Invalid AUTOBOT_AC_SUGGESTER_CACHE_TTL=%r — using default %d s",
        raw,
        _DEFAULT_CACHE_TTL,
    )
    return _DEFAULT_CACHE_TTL


_CACHE_TTL: int = _resolve_cache_ttl()

_SYSTEM_PROMPT = (
    "You are a product manager helping write acceptance criteria for a new work item. "
    "Based on the company standards and similar completed work items provided, "
    "propose 3-6 specific, testable acceptance criteria as a bullet list. "
    "Each criterion must start with '- '. Be concise and specific."
)

_USER_PROMPT_TEMPLATE = """\
New work item:
Title: {title}
Description: {description}

Company standards / policies (top matches):
{policies}

Similar completed work items:
{past_items}

Propose 3-6 acceptance criteria for this work item as a bullet list."""


class AcSuggester:
    """RAG-backed acceptance-criteria suggester for new work items (GH#8240).

    Parallel ChromaDB queries:
      - ``company:{company_id}`` — top-3 policy/standards docs matching the title
      - ``project:{project_id}`` filtered by type=pbi AND status=done — top-3 similar items

    Combined context is sent to the LLM (LLMType.RAG) to produce draft ACs.
    Suggestions are advisory; the caller decides which to accept.
    """

    async def suggest(
        self,
        company_id: str,
        project_id: str,
        item_title: str,
        item_description: str,
    ) -> Dict[str, Any]:
        """Return suggested ACs and the source document IDs used.

        Args:
            company_id: Tenant company identifier.
            project_id: Project the work item belongs to.
            item_title: Title of the new work item.
            item_description: Description of the new work item.

        Returns:
            ``{"suggestions": List[str], "sources": List[str]}``
            where ``suggestions`` are the proposed AC strings and ``sources``
            are the ChromaDB document IDs used as context.
        """
        cache_key = self._cache_key(item_title, item_description)
        cached = await self._get_cached(cache_key)
        if cached is not None:
            logger.debug("AC suggestion cache hit for key=%s", cache_key[:16])
            return cached

        query = f"{item_title} {item_description}".strip()
        policies, past_items = await asyncio.gather(
            self._query_policies(company_id, query),
            self._query_past_items(project_id, query),
        )

        suggestions = await self._call_llm(item_title, item_description, policies, past_items)
        sources = [c["id"] for c in policies + past_items if c.get("id")]

        result: Dict[str, Any] = {"suggestions": suggestions, "sources": sources}
        await self._set_cached(cache_key, result)
        return result

    async def _query_policies(self, company_id: str, query: str) -> List[Dict[str, Any]]:
        """Query ``company:{company_id}`` for top-3 policy/standards matches."""
        try:
            from utils.async_chromadb_client import get_async_chromadb_client

            client = await get_async_chromadb_client()
            try:
                collection = await client.get_collection(f"company:{company_id}")
            except Exception:
                return []
            count = await collection.count()
            if count == 0:
                return []
            results = await collection.query(
                query_texts=[query],
                n_results=min(3, count),
                include=["documents", "metadatas"],
            )
            return _zip_results(results)
        except Exception:
            logger.exception("Failed to query policies for company_id=%s", company_id)
            return []

    async def _query_past_items(self, project_id: str, query: str) -> List[Dict[str, Any]]:
        """Query ``project:{project_id}`` for top-3 completed similar PBIs."""
        try:
            from utils.async_chromadb_client import get_async_chromadb_client

            client = await get_async_chromadb_client()
            try:
                collection = await client.get_collection(f"project:{project_id}")
            except Exception:
                return []
            count = await collection.count()
            if count == 0:
                return []
            results = await collection.query(
                query_texts=[query],
                n_results=min(3, count),
                where={"$and": [{"type": {"$eq": "pbi"}}, {"status": {"$eq": "done"}}]},
                include=["documents", "metadatas"],
            )
            return _zip_results(results)
        except Exception:
            logger.exception("Failed to query past items for project_id=%s", project_id)
            return []

    async def _call_llm(
        self,
        title: str,
        description: str,
        policies: List[Dict[str, Any]],
        past_items: List[Dict[str, Any]],
    ) -> List[str]:
        """Send assembled context to LLM and parse bullet-list response."""
        try:
            from llm_shared.types import LLMType
            from services.llm_service import get_llm_service

            user_msg = _USER_PROMPT_TEMPLATE.format(
                title=title,
                description=description or "(no description)",
                policies=_format_chunks(policies) or "(none available)",
                past_items=_format_chunks(past_items) or "(none available)",
            )
            svc = get_llm_service()
            response = await svc.chat(
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                llm_type=LLMType.RAG,
            )
            return _parse_bullet_list((response.content or "").strip())
        except Exception:
            logger.exception("LLM call failed in AcSuggester — returning empty suggestions")
            return []

    @staticmethod
    def _cache_key(title: str, description: str) -> str:
        digest = hashlib.sha256(f"{title}{description}".encode("utf-8")).hexdigest()
        return f"llc:ac_suggestions:{digest}"

    async def _get_cached(self, key: str) -> Optional[Dict[str, Any]]:
        try:
            from autobot_shared.redis_client import get_async_redis_client

            redis = await get_async_redis_client()
            if redis is None:
                return None
            raw = await redis.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            logger.debug("Cache read error for key=%s", key[:16])
            return None

    async def _set_cached(self, key: str, value: Dict[str, Any]) -> None:
        try:
            from autobot_shared.redis_client import get_async_redis_client

            redis = await get_async_redis_client()
            if redis is None:
                return
            await redis.setex(key, _CACHE_TTL, json.dumps(value))
        except Exception:
            logger.debug("Failed to write AC suggestion cache for key=%s", key[:16])


def _zip_results(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    ids = results.get("ids", [[]])[0]
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    return [
        {"id": doc_id, "document": doc, "metadata": meta}
        for doc_id, doc, meta in zip(ids, docs, metas)
    ]


def _format_chunks(chunks: List[Dict[str, Any]]) -> str:
    return "\n\n".join(c["document"] for c in chunks if c.get("document"))


def _parse_bullet_list(raw: str) -> List[str]:
    """Extract bullet items from LLM response. Handles -, *, • prefixes."""
    items = []
    for line in raw.splitlines():
        stripped = line.strip()
        for prefix in ("- ", "* ", "• "):
            if stripped.startswith(prefix):
                text = stripped[len(prefix):].strip()
                if text:
                    items.append(text)
                break
    return items


__all__ = ["AcSuggester"]
