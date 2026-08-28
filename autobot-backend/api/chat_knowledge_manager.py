#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Chat knowledge manager — the object itself and its request lifecycle.

Split out of ``api/chat_knowledge.py`` (#15160). That module is the HTTP
surface for ``/api/chat-knowledge/*``; this one owns the manager the surface
depends on:

    - ``ChatKnowledgeContext`` / ``ChatFileAssociation`` — its stored records.
    - ``ChatKnowledgeManager`` — the behaviour.
    - Its lifecycle on ``request.app.state``: where it is cached, how it is
      resolved, and what is recorded when it cannot be built.
    - ``probe_chat_knowledge`` — the health probe, which classifies exactly
      that lifecycle state and so belongs beside it rather than beside the
      routes.

Keeping the lifecycle in one place is what #15160 was about. The bug was a
module-level ``chat_knowledge_manager = None`` that nothing ever assigned:
six handlers dereferenced it and returned 500 on every call, while the probe
read the same dead global and reported ``idle`` for the life of the process.
There is one home for this manager — ``app.state`` — and one way in,
:func:`get_chat_knowledge_manager_instance`.
"""

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List

from fastapi import HTTPException, Request

from api.schemas_knowledge import FileAssociationType, KnowledgeDecision
from api.system_health import ComponentHealth, register_health_probe
from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger
from chat_history import ChatHistoryManager
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER
from knowledge_base import KnowledgeBase
from services.llm_service import get_llm_service
from type_defs.common import Metadata

logger = get_logger(__name__)


# O(1) lookup optimization constants (Issue #326)
TROUBLESHOOTING_KEYWORDS = {"error", "bug", "issue", "problem"}
DOCUMENTATION_KEYWORDS = {"config", "setup", "install", "guide"}


# Canonical ``app.state`` keys for the lazily-created manager (#15160). There is
# deliberately NO module-level ``chat_knowledge_manager`` global: the previous one
# was never assigned, so six handlers and the health probe all read ``None`` for
# the lifetime of the process.
MANAGER_STATE_KEY = "chat_knowledge_manager"
# Records the reason a construction attempt failed so the health probe can report
# "down" instead of an indefinite "idle" that hides a real outage (#15160).
MANAGER_ERROR_STATE_KEY = "chat_knowledge_manager_error"


def peek_chat_knowledge_manager(request: Request | None):
    """Return the cached manager without ever constructing one.

    Side-effect free by design: the health probe must observe the real state,
    not create it (``ChatKnowledgeManager.__init__`` builds a KnowledgeBase and
    an LLM service, far beyond the aggregator's per-probe budget).
    """
    if request is None:
        return None
    return getattr(request.app.state, MANAGER_STATE_KEY, None)


async def get_chat_knowledge_manager_instance(request: Request = None):
    """Resolve the chat knowledge manager, caching it on ``request.app.state``.

    ``request.app.state`` is the single home for this manager — the same place
    ``ResourceFactory.get_all_cached_resources`` already reports it from — so
    every handler and the health probe read one source of truth.

    Raises ``HTTPException(503)`` when the manager cannot be produced: a handler
    must surface an honest "dependency unavailable" rather than dereference
    ``None`` and collapse into an opaque 500 (#15160).
    """
    cached = peek_chat_knowledge_manager(request)
    if cached is not None:
        logger.debug("Using pre-initialized chat knowledge manager from app.state")
        return cached

    logger.info("Creating new ChatKnowledgeManager instance (expensive operation)")
    try:
        new_manager = ChatKnowledgeManager()
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        if request is not None:
            setattr(request.app.state, MANAGER_ERROR_STATE_KEY, detail)
        logger.error("ChatKnowledgeManager construction failed: %s", detail)
        raise HTTPException(status_code=503, detail="Chat knowledge manager unavailable") from exc

    if request is not None:
        setattr(request.app.state, MANAGER_STATE_KEY, new_manager)
        setattr(request.app.state, MANAGER_ERROR_STATE_KEY, None)
        logger.info("Cached new chat knowledge manager in app.state for future requests")

    return new_manager


@dataclass
class ChatKnowledgeContext:
    """Knowledge context for a specific chat session (Issue #688: added user_id)."""

    chat_id: str
    topic: str | None = None
    keywords: List[str] = field(default_factory=list)
    summary: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    temporary_knowledge: List[Metadata] = field(default_factory=list)
    persistent_knowledge_ids: List[str] = field(default_factory=list)
    file_associations: List[Metadata] = field(default_factory=list)
    metadata: Metadata = field(default_factory=dict)
    # Issue #688: Track user ownership for chat-derived facts
    user_id: str | None = None


@dataclass
class ChatFileAssociation:
    """File associated with a chat session"""

    file_id: str
    chat_id: str
    file_path: str
    file_name: str
    association_type: FileAssociationType
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Metadata = field(default_factory=dict)
    content_hash: str | None = None
    size_bytes: int | None = None


class ChatKnowledgeManager:
    """Manager for chat-specific knowledge and file associations"""

    def __init__(self):
        """Initialize manager with knowledge base and storage paths."""
        self.knowledge_base = KnowledgeBase()
        self.chat_history_manager = ChatHistoryManager()
        self.llm_interface = get_llm_service()

        # In-memory storage (should be persisted to database in production)
        self.chat_contexts: Dict[str, ChatKnowledgeContext] = {}
        self.file_associations: Dict[str, List[ChatFileAssociation]] = {}
        self.pending_decisions: Dict[str, List[Metadata]] = {}

        # Initialize storage directory using centralized path management
        from utils.paths_manager import ensure_data_directory, get_data_path

        ensure_data_directory()
        self.storage_dir = str(get_data_path("chat_knowledge"))
        os.makedirs(self.storage_dir, exist_ok=True)

        logger.info("ChatKnowledgeManager initialized")

    async def create_or_update_context(
        self,
        chat_id: str,
        topic: str | None = None,
        keywords: List[str] | None = None,
        user_id: str | None = None,
    ) -> ChatKnowledgeContext:
        """Create or update knowledge context for a chat (Issue #688: added user_id)."""
        if chat_id in self.chat_contexts:
            context = self.chat_contexts[chat_id]
            if topic:
                context.topic = topic
            if keywords:
                context.keywords.extend(keywords)
                context.keywords = list(set(context.keywords))  # Remove duplicates
            if user_id:
                context.user_id = user_id
            context.updated_at = datetime.now(tz=timezone.utc)
        else:
            context = ChatKnowledgeContext(
                chat_id=chat_id,
                topic=topic,
                keywords=keywords or [],
                user_id=user_id,
            )
            self.chat_contexts[chat_id] = context

        logger.info(
            "Context updated for chat %s: topic='%s', keywords=%s, user_id=%s",
            chat_id,
            topic,
            keywords,
            user_id,
        )
        return context

    async def associate_file(
        self,
        chat_id: str,
        file_path: str,
        association_type: FileAssociationType,
        metadata: Metadata | None = None,
    ) -> ChatFileAssociation:
        """Associate a file with a chat session"""
        file_id = str(uuid.uuid4())

        # Get file info
        file_name = os.path.basename(file_path)
        # Issue #358 - avoid blocking
        file_exists = await asyncio.to_thread(os.path.exists, file_path)
        size_bytes = await asyncio.to_thread(os.path.getsize, file_path) if file_exists else None

        association = ChatFileAssociation(
            file_id=file_id,
            chat_id=chat_id,
            file_path=file_path,
            file_name=file_name,
            association_type=association_type,
            size_bytes=size_bytes,
            metadata=metadata or {},
        )

        # Store association
        if chat_id not in self.file_associations:
            self.file_associations[chat_id] = []
        self.file_associations[chat_id].append(association)

        # Update context
        if chat_id in self.chat_contexts:
            self.chat_contexts[chat_id].file_associations.append(
                {
                    "file_id": file_id,
                    "file_name": file_name,
                    "type": association_type.value,
                    "path": file_path,
                }
            )

        logger.info(f"File associated with chat {chat_id}: {file_name} ({association_type.value})")
        return association

    async def add_temporary_knowledge(self, chat_id: str, content: str, metadata: Metadata | None = None) -> str:
        """Add temporary knowledge to chat context"""
        knowledge_id = str(uuid.uuid4())

        knowledge_item = {
            "id": knowledge_id,
            "content": content,
            "metadata": metadata or {},
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "status": "temporary",
        }

        if chat_id not in self.chat_contexts:
            await self.create_or_update_context(chat_id)

        self.chat_contexts[chat_id].temporary_knowledge.append(knowledge_item)

        logger.info("Temporary knowledge added to chat %s: %s", chat_id, knowledge_id)
        return knowledge_id

    async def get_knowledge_for_decision(self, chat_id: str) -> List[Metadata]:
        """Get temporary knowledge items pending decision"""
        if chat_id not in self.chat_contexts:
            return []

        context = self.chat_contexts[chat_id]
        pending_items = []

        for item in context.temporary_knowledge:
            if item.get("status") == "temporary":
                pending_items.append(
                    {
                        "id": item["id"],
                        "content": item["content"],
                        "metadata": item.get("metadata", {}),
                        "created_at": item["created_at"],
                        "suggested_action": self._suggest_knowledge_action(item["content"]),
                    }
                )

        return pending_items

    def _suggest_knowledge_action(self, content: str) -> str:
        """Suggest action for knowledge based on content analysis"""
        # Simple heuristics for suggestions
        content_lower = content.lower()

        if any(keyword in content_lower for keyword in TROUBLESHOOTING_KEYWORDS):  # O(1) lookup (Issue #326)
            return KnowledgeDecision.ADD_TO_KB  # Useful for troubleshooting
        elif any(keyword in content_lower for keyword in DOCUMENTATION_KEYWORDS):  # O(1) lookup (Issue #326)
            return KnowledgeDecision.ADD_TO_KB  # Useful for documentation
        elif len(content) < 50:
            return KnowledgeDecision.DELETE  # Too short to be useful
        else:
            return KnowledgeDecision.KEEP_TEMPORARY  # Keep for this session

    async def apply_knowledge_decision(self, chat_id: str, knowledge_id: str, decision: KnowledgeDecision) -> bool:
        """Apply user decision for temporary knowledge"""
        if chat_id not in self.chat_contexts:
            return False

        context = self.chat_contexts[chat_id]

        # Find the knowledge item
        item = None
        for k in context.temporary_knowledge:
            if k["id"] == knowledge_id:
                item = k
                break

        if not item:
            return False

        if decision == KnowledgeDecision.ADD_TO_KB:
            # Add to permanent knowledge base
            try:
                # Issue #547: Include source_session_id for orphan cleanup
                # Issue #688: Include ownership metadata for chat-derived facts
                metadata = {
                    **item.get("metadata", {}),
                    "source": f"chat_{chat_id}",
                    "source_session_id": chat_id,  # Issue #547: Track source session
                    "original_id": knowledge_id,
                    "source_type": "chat",  # Issue #688: Mark as chat-derived
                    "category": "chat_knowledge",  # Issue #688: Category for chat facts
                }

                # Issue #688: Add user ownership if available from context
                if hasattr(context, "user_id") and context.user_id:
                    metadata["owner_id"] = context.user_id
                    metadata["visibility"] = "private"  # Default visibility

                kb_id = await self.knowledge_base.add_content(
                    content=item["content"],
                    metadata=metadata,
                )

                # Track in context
                context.persistent_knowledge_ids.append(kb_id)
                item["status"] = "persistent"
                item["kb_id"] = kb_id

                logger.info("Knowledge %s added to KB as %s", knowledge_id, kb_id)

            except Exception as e:
                logger.error("Failed to add knowledge to KB: %s", e)
                return False

        elif decision == KnowledgeDecision.KEEP_TEMPORARY:
            item["status"] = "session_only"
            logger.info("Knowledge %s kept as session-only", knowledge_id)

        elif decision == KnowledgeDecision.DELETE:
            context.temporary_knowledge.remove(item)
            logger.info("Knowledge %s deleted", knowledge_id)

        return True

    def _build_compiled_knowledge_dict(
        self, chat_id: str, title: str | None, context, messages: list, summary: str
    ) -> dict:
        """Helper for compile_chat_to_knowledge. Ref: #1088."""
        return {
            "chat_id": chat_id,
            "title": title or context.topic if context else f"Chat Session {chat_id}",
            "summary": summary,
            "message_count": len(messages),
            "keywords": context.keywords if context else [],
            "file_associations": self.file_associations.get(chat_id, []),
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "metadata": {
                "original_chat_id": chat_id,
                "compilation_date": datetime.now(tz=timezone.utc).isoformat(),
                "message_stats": {
                    "total": len(messages),
                    "user": len([m for m in messages if m.get("role") == "user"]),
                    "assistant": len([m for m in messages if m.get("role") == "assistant"]),
                },
            },
        }

    def _build_chat_kb_metadata(self, base_metadata: dict, chat_id: str, context) -> dict:
        """Helper for compile_chat_to_knowledge. Ref: #1088."""
        # Issue #547: Include source_session_id for orphan cleanup
        # Issue #688: Include ownership metadata for chat-compiled knowledge
        kb_metadata = {
            **base_metadata,
            "source_session_id": chat_id,  # Issue #547: Track source session
            "source_type": "chat",  # Issue #688: Mark as chat-derived
            "category": "chat_knowledge",  # Issue #688: Category for chat facts
        }
        # Issue #688: Add user ownership if available from context
        if context and hasattr(context, "user_id") and context.user_id:
            kb_metadata["owner_id"] = context.user_id
            kb_metadata["visibility"] = "private"  # Default visibility
        return kb_metadata

    async def compile_chat_to_knowledge(
        self,
        chat_id: str,
        title: str | None = None,
        include_system_messages: bool = False,
    ) -> Metadata:
        """Compile entire chat conversation to knowledge base"""
        chat_history = self.chat_history_manager.get_chat_history(chat_id)

        if not chat_history or not chat_history.get("messages"):
            raise ValueError(f"No chat history found for {chat_id}")

        messages = chat_history["messages"]
        if not include_system_messages:
            messages = [m for m in messages if m.get("role") != "system"]

        summary_prompt = """
        Summarize this conversation into a comprehensive knowledge base entry.
        Include key topics, solutions, code examples, and important information.

        Conversation:
        {json.dumps(messages, indent=2)}

        Format the summary with clear sections and bullet points.
        """

        summary_response = await self.llm_interface.chat(messages=[{"role": "user", "content": summary_prompt}])
        summary = summary_response.content

        context = self.chat_contexts.get(chat_id)
        compiled_knowledge = self._build_compiled_knowledge_dict(chat_id, title, context, messages, summary)
        kb_metadata = self._build_chat_kb_metadata(compiled_knowledge["metadata"], chat_id, context)

        kb_id = await self.knowledge_base.add_content(content=summary, metadata=kb_metadata)
        compiled_knowledge["kb_id"] = kb_id

        logger.info("Chat %s compiled to knowledge base as %s", chat_id, kb_id)
        return compiled_knowledge

    async def search_chat_knowledge(
        self, query: str, chat_id: str | None = None, include_temporary: bool = True
    ) -> List[Metadata]:
        """Search knowledge across chats or within specific chat"""
        results = []

        # Search in permanent knowledge base
        # Issue #13024: canonical search() has no n_results kwarg -- use top_k.
        # Issue #13009: exclude quarantined research facts (#12622).
        kb_results = await self.knowledge_base.search(query, top_k=10, filters=RESEARCH_QUARANTINE_FILTER)

        for result in kb_results:
            # Filter by chat if specified
            if chat_id and result.get("metadata", {}).get("source") != f"chat_{chat_id}":
                continue

            results.append(
                {
                    "type": "persistent",
                    "content": result["content"],
                    "metadata": result.get("metadata", {}),
                    "score": result.get("score", 0),
                }
            )

        # Search in temporary knowledge if requested
        if include_temporary:
            contexts_to_search = [self.chat_contexts[chat_id]] if chat_id else self.chat_contexts.values()

            for context in contexts_to_search:
                for item in context.temporary_knowledge:
                    if query.lower() in item["content"].lower():
                        results.append(
                            {
                                "type": "temporary",
                                "chat_id": context.chat_id,
                                "content": item["content"],
                                "metadata": item.get("metadata", {}),
                                "score": 0.5,  # Simple keyword match score
                            }
                        )

        # Sort by score
        results.sort(key=lambda x: x.get("score", 0), reverse=True)

        return results[:20]  # Limit to top 20 results


@register_health_probe("chat_knowledge")
async def probe_chat_knowledge(
    request: Request | None = None,
) -> ComponentHealth:
    """Issue #3333 / #12459 / #15160: probe for the chat-knowledge manager.

    The manager is a lazy singleton cached on ``request.app.state``
    (``get_chat_knowledge_manager_instance``), so "not initialized" is not by
    itself a failure. It is only ``idle`` when the probe can *see* that state
    and see no failure, though:

    ``down``     — a previous resolution attempt failed; the recorded reason is
                   reported. Before #15160 this outage was invisible: the probe
                   read a module global nothing ever assigned, so it answered
                   ``idle`` forever while every route under it returned 500.
    ``degraded`` — the probe was handed no ``Request``, so ``app.state`` is
                   unobservable. Reporting ``idle`` here would be the same lie:
                   "working" and "never wired" would look identical.
    ``ok``       — a live manager is cached and exposes its storage directory.
    ``idle``     — observable, no failure recorded, not yet used.
    """
    try:
        if request is None:
            return ComponentHealth(
                name="chat_knowledge",
                status="degraded",
                detail="manager state unobservable: probe received no Request",
            )

        failure = getattr(request.app.state, MANAGER_ERROR_STATE_KEY, None)
        if failure:
            return ComponentHealth(
                name="chat_knowledge",
                status="down",
                detail=f"manager unavailable: {str(failure)[:160]}",
            )

        manager = peek_chat_knowledge_manager(request)
        if manager is None:
            return ComponentHealth(
                name="chat_knowledge",
                status="idle",
                detail="chat knowledge manager not initialized (lazy singleton, not yet used)",
            )

        # Touch real state so a stub that merely *exists* cannot read as healthy.
        return ComponentHealth(
            name="chat_knowledge",
            status="ok",
            data={
                "storage_dir_configured": bool(getattr(manager, "storage_dir", None)),
                "chat_contexts": len(getattr(manager, "chat_contexts", {})),
            },
        )
    except Exception as exc:
        return ComponentHealth(
            name="chat_knowledge",
            status="down",
            detail=f"probe error: {type(exc).__name__}",
        )


if __name__ == "__main__":
    # Example usage
    async def demo():
        """Demonstrate ChatKnowledgeManager usage with test data."""
        manager = ChatKnowledgeManager()

        # Create context
        context = await manager.create_or_update_context(
            chat_id="test_chat_123",
            topic="Python Development",
            keywords=["python", "fastapi", "async"],
        )
        logger.info("Created context: %s", context)

        # Add temporary knowledge
        knowledge_id = await manager.add_temporary_knowledge(
            chat_id="test_chat_123",
            content=("FastAPI is a modern web framework for Python with automatic API" "documentation."),
            metadata={"category": "framework"},
        )

        # Get pending decisions
        pending = await manager.get_knowledge_for_decision("test_chat_123")
        logger.info("Pending decisions: %s", pending)

        # Apply decision
        await manager.apply_knowledge_decision(
            chat_id="test_chat_123",
            knowledge_id=knowledge_id,
            decision=KnowledgeDecision.ADD_TO_KB,
        )

        logger.info("Demo completed!")

    run_or_schedule(demo())
