# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Context Generator Cognifier - prepend LLM-generated context to each chunk.

Issue #1498: Contextual Retrieval - +35% RAG retrieval accuracy.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

from knowledge.pipeline.base import BaseCognifier, PipelineContext
from knowledge.pipeline.registry import TaskRegistry
from llm_interface_pkg import LLMInterface

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

_SUMMARY_PROMPT = (
    "You are summarizing a document for a retrieval system.\n"
    "Produce a concise 3-5 sentence summary covering the main topic, key facts,\n"
    "and scope of the document. Do not include opinions or speculation.\n\n"
    "Document:\n{doc_text}"
)

_CHUNK_PROMPT = (
    "Document summary: {doc_summary}\n\n"
    "Here is a chunk from this document:\n"
    "<chunk>{chunk_text}</chunk>\n\n"
    "Write a single concise sentence (max 30 words) that situates this chunk"
    " within the document context. The sentence will be prepended to the chunk"
    " to improve retrieval. Output only the sentence."
)

_DOC_TEXT_LIMIT = 4000
_CACHE_KEY_PREFIX = "context:summary:"


@TaskRegistry.register_cognifier("add_context")
class ContextGeneratorCognifier(BaseCognifier):
    """Prepend LLM-generated context sentences to each chunk (Issue #1498)."""

    def __init__(self, model=None, ttl_days=None):
        self.model = model or os.getenv("CONTEXT_MODEL", "llama3.2:3b")
        days = ttl_days or int(os.getenv("CONTEXT_SUMMARY_TTL_DAYS", "30"))
        self.ttl_seconds = days * 86400
        self.llm = LLMInterface()

    async def process(self, context: PipelineContext) -> PipelineContext:
        if not self._is_enabled() or not context.chunks:
            return context
        doc_text = "\n\n".join(c.content for c in context.chunks)
        doc_id = str(context.document_id or "")
        doc_summary = await self._get_or_create_summary(doc_text, doc_id)
        for chunk in context.chunks:
            await self._enrich_chunk(chunk, doc_summary)
        logger.info(
            "Enriched %d chunks with context (model=%s)",
            len(context.chunks),
            self.model,
        )
        return context

    async def _get_or_create_summary(self, doc_text: str, doc_id: str) -> str:
        cache_key = f"{_CACHE_KEY_PREFIX}{doc_id}"
        redis = get_redis_client(async_client=False, database="knowledge")
        cached = await asyncio.to_thread(redis.get, cache_key)
        if cached:
            return json.loads(cached).get("summary", "")
        summary = await self._call_llm_for_summary(doc_text)
        payload = json.dumps(
            {
                "summary": summary,
                "model": self.model,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        await asyncio.to_thread(redis.setex, cache_key, self.ttl_seconds, payload)
        return summary

    async def _call_llm_for_summary(self, doc_text: str) -> str:
        prompt = _SUMMARY_PROMPT.format(doc_text=doc_text[:_DOC_TEXT_LIMIT])
        try:
            response = await self.llm.chat_completion(
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content.strip()
        except Exception as e:  # noqa: BLE001
            logger.error("Context summary LLM call failed: %s", e)
            return ""

    async def _enrich_chunk(self, chunk, doc_summary: str) -> None:
        original = chunk.content
        ctx_text = await self._generate_chunk_context(doc_summary, original)
        if ctx_text:
            chunk.content = f"{ctx_text}\n\n{original}"
        chunk.metadata["contextual_text"] = ctx_text
        chunk.metadata["original_chunk"] = original
        chunk.metadata["has_context"] = bool(ctx_text)
        chunk.metadata["context_model"] = self.model
        chunk.metadata["context_generated_at"] = datetime.now(timezone.utc).isoformat()

    async def _generate_chunk_context(self, doc_summary: str, chunk_text: str) -> str:
        if not doc_summary:
            return ""
        prompt = _CHUNK_PROMPT.format(doc_summary=doc_summary, chunk_text=chunk_text)
        try:
            response = await self.llm.chat_completion(
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content.strip()
        except Exception as e:  # noqa: BLE001
            logger.error("Chunk context LLM call failed: %s", e)
            return ""

    @staticmethod
    def _is_enabled() -> bool:
        return os.getenv("CONTEXT_ENABLED", "false").lower() == "true"
