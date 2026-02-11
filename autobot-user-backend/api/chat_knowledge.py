#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat Knowledge Management API
Handles chat-specific file associations, knowledge context, and compilation
"""

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

import aiofiles
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from backend.type_defs.common import Metadata
from chat_history import ChatHistoryManager
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

# Import existing components
from knowledge_base import KnowledgeBase
from llm_interface import LLMInterface
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat_knowledge"])

# O(1) lookup optimization constants (Issue #326)
TROUBLESHOOTING_KEYWORDS = {"error", "bug", "issue", "problem"}
DOCUMENTATION_KEYWORDS = {"config", "setup", "install", "guide"}


async def get_chat_knowledge_manager_instance(request: Request = None):
    """Get chat knowledge manager (preferring pre-initialized app.state)."""
    # Try to use pre-initialized manager from app state first
    if request is not None:
        app_manager = getattr(request.app.state, "chat_knowledge_manager", None)
        if app_manager is not None:
            logger.debug("Using pre-initialized chat knowledge manager from app.state")
            return app_manager

    # Try to use global instance
    if chat_knowledge_manager is not None:
        logger.debug("Using global chat knowledge manager instance")
        return chat_knowledge_manager

    # Create new instance as last resort
    logger.info("Creating new ChatKnowledgeManager instance (expensive operation)")
    new_manager = ChatKnowledgeManager()

    # Cache in app state if request available
    if request is not None:
        request.app.state.chat_knowledge_manager = new_manager
        logger.info(
            "Cached new chat knowledge manager in app.state for future requests"
        )

    return new_manager


class KnowledgeDecision(str, Enum):
    """Decision for knowledge persistence"""

    ADD_TO_KB = "add_to_kb"
    KEEP_TEMPORARY = "keep_temporary"
    DELETE = "delete"


class FileAssociationType(str, Enum):
    """Type of file association"""

    REFERENCE = "reference"  # File referenced in chat
    UPLOAD = "upload"  # File uploaded to chat
    GENERATED = "generated"  # File generated during chat
    MODIFIED = "modified"  # File modified during chat


@dataclass
class ChatKnowledgeContext:
    """Knowledge context for a specific chat session (Issue #688: added user_id)."""

    chat_id: str
    topic: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    summary: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    temporary_knowledge: List[Metadata] = field(default_factory=list)
    persistent_knowledge_ids: List[str] = field(default_factory=list)
    file_associations: List[Metadata] = field(default_factory=list)
    metadata: Metadata = field(default_factory=dict)
    # Issue #688: Track user ownership for chat-derived facts
    user_id: Optional[str] = None


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
    content_hash: Optional[str] = None
    size_bytes: Optional[int] = None


class ChatKnowledgeManager:
    """Manager for chat-specific knowledge and file associations"""

    def __init__(self):
        """Initialize manager with knowledge base and storage paths."""
        self.knowledge_base = KnowledgeBase()
        self.chat_history_manager = ChatHistoryManager()
        self.llm_interface = LLMInterface()

        # In-memory storage (should be persisted to database in production)
        self.chat_contexts: Dict[str, ChatKnowledgeContext] = {}
        self.file_associations: Dict[str, List[ChatFileAssociation]] = {}
        self.pending_decisions: Dict[str, List[Metadata]] = {}

        # Initialize storage directory using centralized path management
        from backend.utils.paths_manager import ensure_data_directory, get_data_path

        ensure_data_directory()
        self.storage_dir = str(get_data_path("chat_knowledge"))
        os.makedirs(self.storage_dir, exist_ok=True)

        logger.info("ChatKnowledgeManager initialized")

    async def create_or_update_context(
        self,
        chat_id: str,
        topic: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        user_id: Optional[str] = None,
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
            context.updated_at = datetime.now()
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
        metadata: Optional[Metadata] = None,
    ) -> ChatFileAssociation:
        """Associate a file with a chat session"""
        file_id = str(uuid.uuid4())

        # Get file info
        file_name = os.path.basename(file_path)
        # Issue #358 - avoid blocking
        file_exists = await asyncio.to_thread(os.path.exists, file_path)
        size_bytes = (
            await asyncio.to_thread(os.path.getsize, file_path) if file_exists else None
        )

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

        logger.info(
            f"File associated with chat {chat_id}: {file_name} ({association_type.value})"
        )
        return association

    async def add_temporary_knowledge(
        self, chat_id: str, content: str, metadata: Optional[Metadata] = None
    ) -> str:
        """Add temporary knowledge to chat context"""
        knowledge_id = str(uuid.uuid4())

        knowledge_item = {
            "id": knowledge_id,
            "content": content,
            "metadata": metadata or {},
            "created_at": datetime.now().isoformat(),
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
                        "suggested_action": self._suggest_knowledge_action(
                            item["content"]
                        ),
                    }
                )

        return pending_items

    def _suggest_knowledge_action(self, content: str) -> str:
        """Suggest action for knowledge based on content analysis"""
        # Simple heuristics for suggestions
        content_lower = content.lower()

        if any(
            keyword in content_lower
            for keyword in TROUBLESHOOTING_KEYWORDS  # O(1) lookup (Issue #326)
        ):
            return KnowledgeDecision.ADD_TO_KB  # Useful for troubleshooting
        elif any(
            keyword in content_lower
            for keyword in DOCUMENTATION_KEYWORDS  # O(1) lookup (Issue #326)
        ):
            return KnowledgeDecision.ADD_TO_KB  # Useful for documentation
        elif len(content) < 50:
            return KnowledgeDecision.DELETE  # Too short to be useful
        else:
            return KnowledgeDecision.KEEP_TEMPORARY  # Keep for this session

    async def apply_knowledge_decision(
        self, chat_id: str, knowledge_id: str, decision: KnowledgeDecision
    ) -> bool:
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

    async def compile_chat_to_knowledge(
        self,
        chat_id: str,
        title: Optional[str] = None,
        include_system_messages: bool = False,
    ) -> Metadata:
        """Compile entire chat conversation to knowledge base"""
        # Get chat history
        chat_history = self.chat_history_manager.get_chat_history(chat_id)

        if not chat_history or not chat_history.get("messages"):
            raise ValueError(f"No chat history found for {chat_id}")

        messages = chat_history["messages"]

        # Filter messages
        if not include_system_messages:
            messages = [m for m in messages if m.get("role") != "system"]

        # Generate summary using LLM
        summary_prompt = """
        Summarize this conversation into a comprehensive knowledge base entry.
        Include key topics, solutions, code examples, and important information.

        Conversation:
        {json.dumps(messages, indent=2)}

        Format the summary with clear sections and bullet points.
        """

        summary_response = await self.llm_interface.chat_completion(
            model="default", messages=[{"role": "user", "content": summary_prompt}]
        )

        summary = summary_response.get("content", "")

        # Extract key information
        context = self.chat_contexts.get(chat_id)

        compiled_knowledge = {
            "chat_id": chat_id,
            "title": title or context.topic if context else f"Chat Session {chat_id}",
            "summary": summary,
            "message_count": len(messages),
            "keywords": context.keywords if context else [],
            "file_associations": self.file_associations.get(chat_id, []),
            "created_at": datetime.now().isoformat(),
            "metadata": {
                "original_chat_id": chat_id,
                "compilation_date": datetime.now().isoformat(),
                "message_stats": {
                    "total": len(messages),
                    "user": len([m for m in messages if m.get("role") == "user"]),
                    "assistant": len(
                        [m for m in messages if m.get("role") == "assistant"]
                    ),
                },
            },
        }

        # Add to knowledge base
        # Issue #547: Include source_session_id for orphan cleanup
        # Issue #688: Include ownership metadata for chat-compiled knowledge
        kb_metadata = {
            **compiled_knowledge["metadata"],
            "source_session_id": chat_id,  # Issue #547: Track source session
            "source_type": "chat",  # Issue #688: Mark as chat-derived
            "category": "chat_knowledge",  # Issue #688: Category for chat facts
        }

        # Issue #688: Add user ownership if available from context
        context = self.chat_contexts.get(chat_id)
        if context and hasattr(context, "user_id") and context.user_id:
            kb_metadata["owner_id"] = context.user_id
            kb_metadata["visibility"] = "private"  # Default visibility

        kb_id = await self.knowledge_base.add_content(
            content=summary, metadata=kb_metadata
        )

        compiled_knowledge["kb_id"] = kb_id

        logger.info("Chat %s compiled to knowledge base as %s", chat_id, kb_id)
        return compiled_knowledge

    async def search_chat_knowledge(
        self, query: str, chat_id: Optional[str] = None, include_temporary: bool = True
    ) -> List[Metadata]:
        """Search knowledge across chats or within specific chat"""
        results = []

        # Search in permanent knowledge base
        kb_results = await self.knowledge_base.search(query, n_results=10)

        for result in kb_results:
            # Filter by chat if specified
            if (
                chat_id
                and result.get("metadata", {}).get("source") != f"chat_{chat_id}"
            ):
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
            contexts_to_search = (
                [self.chat_contexts[chat_id]]
                if chat_id
                else self.chat_contexts.values()
            )

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


# Global manager instance - initialized lazily to avoid expensive startup
chat_knowledge_manager = None


# API Endpoints


class CreateContextRequest(BaseModel):
    """Create chat context request (Issue #688: added user_id)."""

    chat_id: str
    topic: Optional[str] = None
    keywords: Optional[List[str]] = None
    user_id: Optional[str] = None  # Issue #688: Track user ownership


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_chat_context",
    error_code_prefix="CHAT_KNOWLEDGE",
)
@router.post("/context/create")
async def create_chat_context(request_data: CreateContextRequest, request: Request):
    """Create or update knowledge context for a chat (Issue #688: added user_id)."""
    try:
        manager = await get_chat_knowledge_manager_instance(request)
        context = await manager.create_or_update_context(
            chat_id=request_data.chat_id,
            topic=request_data.topic,
            keywords=request_data.keywords,
            user_id=request_data.user_id,
        )

        return {
            "success": True,
            "context": {
                "chat_id": context.chat_id,
                "topic": context.topic,
                "keywords": context.keywords,
                "user_id": context.user_id,
                "created_at": context.created_at.isoformat(),
                "updated_at": context.updated_at.isoformat(),
            },
        }

    except Exception as e:
        logger.error("Failed to create context: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class AssociateFileRequest(BaseModel):
    chat_id: str
    file_path: str
    association_type: FileAssociationType
    metadata: Optional[Metadata] = None


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="associate_file_with_chat",
    error_code_prefix="CHAT_KNOWLEDGE",
)
@router.post("/files/associate")
async def associate_file_with_chat(
    request_data: AssociateFileRequest, request: Request
):
    """Associate a file with a chat session"""
    try:
        manager = await get_chat_knowledge_manager_instance(request)
        association = await manager.associate_file(
            chat_id=request_data.chat_id,
            file_path=request_data.file_path,
            association_type=request_data.association_type,
            metadata=request_data.metadata,
        )

        return {
            "success": True,
            "association": {
                "file_id": association.file_id,
                "file_name": association.file_name,
                "association_type": association.association_type.value,
                "created_at": association.created_at.isoformat(),
            },
        }

    except Exception as e:
        logger.error("Failed to associate file: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="upload_file_to_chat",
    error_code_prefix="CHAT_KNOWLEDGE",
)
@router.post("/files/upload/{chat_id}")
async def upload_file_to_chat(
    chat_id: str,
    file: UploadFile = File(...),
    association_type: str = Form(default="upload"),
):
    """Upload a file and associate it with a chat"""
    try:
        # Save uploaded file
        file_path = os.path.join(
            chat_knowledge_manager.storage_dir, f"{chat_id}_{file.filename}"
        )

        content = await file.read()
        try:
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(content)
        except OSError as e:
            logger.error("Failed to write uploaded file %s: %s", file_path, e)
            raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

        # Associate with chat
        association = await chat_knowledge_manager.associate_file(
            chat_id=chat_id,
            file_path=file_path,
            association_type=FileAssociationType(association_type),
            metadata={"original_filename": file.filename},
        )

        return {"success": True, "file_id": association.file_id, "file_path": file_path}

    except Exception as e:
        logger.error("Failed to upload file: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class AddKnowledgeRequest(BaseModel):
    chat_id: str
    content: str
    metadata: Optional[Metadata] = None


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_temporary_knowledge",
    error_code_prefix="CHAT_KNOWLEDGE",
)
@router.post("/knowledge/add_temporary")
async def add_temporary_knowledge(request: AddKnowledgeRequest):
    """Add temporary knowledge to chat context"""
    try:
        knowledge_id = await chat_knowledge_manager.add_temporary_knowledge(
            chat_id=request.chat_id, content=request.content, metadata=request.metadata
        )

        return {"success": True, "knowledge_id": knowledge_id}

    except Exception as e:
        logger.error("Failed to add temporary knowledge: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pending_knowledge_decisions",
    error_code_prefix="CHAT_KNOWLEDGE",
)
@router.get("/knowledge/pending/{chat_id}")
async def get_pending_knowledge_decisions(chat_id: str):
    """Get knowledge items pending user decision"""
    try:
        pending_items = await chat_knowledge_manager.get_knowledge_for_decision(chat_id)

        return {
            "success": True,
            "pending_items": pending_items,
            "count": len(pending_items),
        }

    except Exception as e:
        logger.error("Failed to get pending knowledge: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class KnowledgeDecisionRequest(BaseModel):
    chat_id: str
    knowledge_id: str
    decision: KnowledgeDecision


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="apply_knowledge_decision",
    error_code_prefix="CHAT_KNOWLEDGE",
)
@router.post("/knowledge/decide")
async def apply_knowledge_decision(request: KnowledgeDecisionRequest):
    """Apply user decision for temporary knowledge"""
    try:
        success = await chat_knowledge_manager.apply_knowledge_decision(
            chat_id=request.chat_id,
            knowledge_id=request.knowledge_id,
            decision=request.decision,
        )

        return {
            "success": success,
            "message": f"Knowledge {request.decision.value} applied",
        }

    except Exception as e:
        logger.error("Failed to apply knowledge decision: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class CompileChatRequest(BaseModel):
    chat_id: str
    title: Optional[str] = None
    include_system_messages: bool = False


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="compile_chat_to_knowledge",
    error_code_prefix="CHAT_KNOWLEDGE",
)
@router.post("/compile")
async def compile_chat_to_knowledge(request_data: CompileChatRequest, request: Request):
    """Compile entire chat conversation to knowledge base"""
    try:
        manager = await get_chat_knowledge_manager_instance(request)
        compiled = await manager.compile_chat_to_knowledge(
            chat_id=request_data.chat_id,
            title=request_data.title,
            include_system_messages=request_data.include_system_messages,
        )

        return {"success": True, "compiled": compiled}

    except Exception as e:
        logger.error("Failed to compile chat: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class SearchRequest(BaseModel):
    query: str
    chat_id: Optional[str] = None
    include_temporary: bool = True


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_chat_knowledge",
    error_code_prefix="CHAT_KNOWLEDGE",
)
@router.post("/search")
async def search_chat_knowledge(request: SearchRequest):
    """Search knowledge across chats or within specific chat"""
    try:
        results = await chat_knowledge_manager.search_chat_knowledge(
            query=request.query,
            chat_id=request.chat_id,
            include_temporary=request.include_temporary,
        )

        return {"success": True, "results": results, "count": len(results)}

    except Exception as e:
        logger.error("Failed to search knowledge: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_chat_context",
    error_code_prefix="CHAT_KNOWLEDGE",
)
@router.get("/context/{chat_id}")
async def get_chat_context(chat_id: str):
    """Get complete knowledge context for a chat"""
    try:
        context = chat_knowledge_manager.chat_contexts.get(chat_id)

        if not context:
            return {"success": False, "message": "No context found for chat"}

        file_associations = chat_knowledge_manager.file_associations.get(chat_id, [])

        return {
            "success": True,
            "context": {
                "chat_id": context.chat_id,
                "topic": context.topic,
                "keywords": context.keywords,
                "created_at": context.created_at.isoformat(),
                "updated_at": context.updated_at.isoformat(),
                "temporary_knowledge_count": len(context.temporary_knowledge),
                "persistent_knowledge_count": len(context.persistent_knowledge_ids),
                "file_count": len(file_associations),
                "files": [
                    {
                        "file_id": f.file_id,
                        "file_name": f.file_name,
                        "type": f.association_type.value,
                        "size": f.size_bytes,
                    }
                    for f in file_associations
                ],
            },
        }

    except Exception as e:
        logger.error("Failed to get chat context: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="health_check",
    error_code_prefix="CHAT_KNOWLEDGE",
)
@router.get("/health")
async def health_check():
    """Health check endpoint for chat knowledge system"""
    try:
        return {
            "status": "healthy",
            "service": "chat_knowledge",
            "manager_initialized": chat_knowledge_manager is not None,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Chat knowledge health check failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Session Facts Endpoints (Issue #547)
# ============================================================================


class MarkFactsPreservedRequest(BaseModel):
    """Request model for marking facts as preserved/important."""

    fact_ids: List[str]
    preserve: bool = True


@router.get("/chat/sessions/{session_id}/facts")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_session_facts",
    error_code_prefix="CHAT_KB",
)
async def get_session_facts(session_id: str, request: Request):
    """
    Get all knowledge base facts created during a specific session.

    Issue #547: This endpoint allows the frontend to preview facts
    that will be deleted when a conversation is deleted.

    Args:
        session_id: Chat session ID to get facts for

    Returns:
        List of facts with their metadata
    """
    # Get knowledge base from app state
    knowledge_base = getattr(request.app.state, "knowledge_base", None)
    if not knowledge_base:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        # Get facts for this session
        facts = await knowledge_base.get_facts_by_session(session_id)

        # Format response with relevant fields for frontend
        formatted_facts = []
        for fact in facts:
            formatted_facts.append(
                {
                    "id": fact.get("id"),
                    "content": fact.get("content", "")[:200]
                    + ("..." if len(fact.get("content", "")) > 200 else ""),
                    "full_content": fact.get("content", ""),
                    "category": fact.get("category", "general"),
                    "tags": fact.get("tags", []),
                    "important": fact.get("important", False),
                    "preserve": fact.get("preserve", False),
                    "created_at": fact.get("created_at"),
                }
            )

        return {
            "status": "success",
            "session_id": session_id,
            "fact_count": len(formatted_facts),
            "facts": formatted_facts,
        }

    except Exception as e:
        logger.error(f"Failed to get facts for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _preserve_single_fact(
    knowledge_base,
    fact_id: str,
    session_id: str,
    preserve: bool,
    preserve_time: str,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Preserve a single fact with bounded concurrency."""
    async with semaphore:
        try:
            fact = await knowledge_base.get_fact(fact_id)
            if not fact:
                return {"status": "error", "fact_id": fact_id, "error": "not_found"}

            fact_session = await knowledge_base.get_session_for_fact(fact_id)
            if fact_session != session_id:
                return {"status": "error", "fact_id": fact_id, "error": "wrong_session"}

            metadata = fact.get("metadata", {})
            metadata["important"] = preserve
            metadata["preserve"] = preserve
            metadata["preserved_at"] = preserve_time
            metadata["preserved_from_deletion"] = True

            success = await knowledge_base.update_fact(
                fact_id=fact_id, metadata=metadata
            )
            if success:
                return {"status": "success", "fact_id": fact_id}
            else:
                return {"status": "error", "fact_id": fact_id, "error": "update_failed"}

        except Exception as e:
            logger.error(f"Error preserving fact {fact_id}: {e}")
            return {"status": "error", "fact_id": fact_id, "error": str(e)}


def _count_preserve_results(results: list, session_id: str) -> tuple[int, int, list]:
    """Count results and collect error messages."""
    errors = []
    updated_count = 0
    failed_count = 0

    for result in results:
        if isinstance(result, Exception):
            errors.append(f"Unexpected error: {str(result)}")
            failed_count += 1
        elif result.get("status") == "success":
            updated_count += 1
        else:
            error_msg = result.get("error", "unknown")
            fact_id = result.get("fact_id", "unknown")
            if error_msg == "not_found":
                errors.append(f"Fact {fact_id} not found")
            elif error_msg == "wrong_session":
                errors.append(f"Fact {fact_id} does not belong to session {session_id}")
            else:
                errors.append(f"Error with fact {fact_id}: {error_msg}")
            failed_count += 1

    return updated_count, failed_count, errors


@router.post("/chat/sessions/{session_id}/facts/preserve")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="preserve_session_facts",
    error_code_prefix="CHAT_KB",
)
async def preserve_session_facts(
    session_id: str, request: Request, body: MarkFactsPreservedRequest
):
    """
    Mark specific facts as preserved/important before session deletion.

    Issue #547: This allows users to select which facts to keep
    when deleting a conversation.

    Uses parallel processing with semaphore for optimal performance.

    Args:
        session_id: Chat session ID
        body: Request body with fact_ids and preserve flag

    Returns:
        Update result with counts
    """
    if len(body.fact_ids) > 100:
        raise HTTPException(
            status_code=400, detail="Maximum 100 facts can be preserved at once"
        )

    knowledge_base = getattr(request.app.state, "knowledge_base", None)
    if not knowledge_base:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        preserve_time = datetime.now().isoformat()
        semaphore = asyncio.Semaphore(20)

        results = await asyncio.gather(
            *[
                _preserve_single_fact(
                    knowledge_base,
                    fid,
                    session_id,
                    body.preserve,
                    preserve_time,
                    semaphore,
                )
                for fid in body.fact_ids
            ],
            return_exceptions=True,
        )

        updated_count, failed_count, errors = _count_preserve_results(
            results, session_id
        )

        return {
            "status": "success" if failed_count == 0 else "partial",
            "session_id": session_id,
            "updated_count": updated_count,
            "failed_count": failed_count,
            "errors": errors if errors else None,
        }

    except Exception as e:
        logger.error(f"Failed to preserve facts for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
            content=(
                "FastAPI is a modern web framework for Python with automatic API"
                "documentation."
            ),
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

    asyncio.run(demo())
