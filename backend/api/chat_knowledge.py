#!/usr/bin/env python3
"""
Chat Knowledge Management API
Handles chat-specific file associations, knowledge context, and compilation
"""

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

# Import existing components
from src.knowledge_base import KnowledgeBase
from src.chat_history_manager import ChatHistoryManager
from src.llm_interface import LLMInterface

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat_knowledge"])


class KnowledgeDecision(str, Enum):
    """Decision for knowledge persistence"""
    ADD_TO_KB = "add_to_kb"
    KEEP_TEMPORARY = "keep_temporary"
    DELETE = "delete"


class FileAssociationType(str, Enum):
    """Type of file association"""
    REFERENCE = "reference"  # File referenced in chat
    UPLOAD = "upload"       # File uploaded to chat
    GENERATED = "generated" # File generated during chat
    MODIFIED = "modified"   # File modified during chat


@dataclass
class ChatKnowledgeContext:
    """Knowledge context for a specific chat session"""
    chat_id: str
    topic: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    summary: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    temporary_knowledge: List[Dict[str, Any]] = field(default_factory=list)
    persistent_knowledge_ids: List[str] = field(default_factory=list)
    file_associations: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatFileAssociation:
    """File associated with a chat session"""
    file_id: str
    chat_id: str
    file_path: str
    file_name: str
    association_type: FileAssociationType
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    content_hash: Optional[str] = None
    size_bytes: Optional[int] = None


class ChatKnowledgeManager:
    """Manager for chat-specific knowledge and file associations"""
    
    def __init__(self):
        self.knowledge_base = KnowledgeBase()
        self.chat_history_manager = ChatHistoryManager()
        self.llm_interface = LLMInterface()
        
        # In-memory storage (should be persisted to database in production)
        self.chat_contexts: Dict[str, ChatKnowledgeContext] = {}
        self.file_associations: Dict[str, List[ChatFileAssociation]] = {}
        self.pending_decisions: Dict[str, List[Dict[str, Any]]] = {}
        
        # Initialize storage directory
        self.storage_dir = "data/chat_knowledge"
        os.makedirs(self.storage_dir, exist_ok=True)
        
        logger.info("ChatKnowledgeManager initialized")
    
    async def create_or_update_context(
        self,
        chat_id: str,
        topic: Optional[str] = None,
        keywords: Optional[List[str]] = None
    ) -> ChatKnowledgeContext:
        """Create or update knowledge context for a chat"""
        if chat_id in self.chat_contexts:
            context = self.chat_contexts[chat_id]
            if topic:
                context.topic = topic
            if keywords:
                context.keywords.extend(keywords)
                context.keywords = list(set(context.keywords))  # Remove duplicates
            context.updated_at = datetime.now()
        else:
            context = ChatKnowledgeContext(
                chat_id=chat_id,
                topic=topic,
                keywords=keywords or []
            )
            self.chat_contexts[chat_id] = context
        
        logger.info(f"Context updated for chat {chat_id}: topic='{topic}', keywords={keywords}")
        return context
    
    async def associate_file(
        self,
        chat_id: str,
        file_path: str,
        association_type: FileAssociationType,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ChatFileAssociation:
        """Associate a file with a chat session"""
        file_id = str(uuid.uuid4())
        
        # Get file info
        file_name = os.path.basename(file_path)
        size_bytes = os.path.getsize(file_path) if os.path.exists(file_path) else None
        
        association = ChatFileAssociation(
            file_id=file_id,
            chat_id=chat_id,
            file_path=file_path,
            file_name=file_name,
            association_type=association_type,
            size_bytes=size_bytes,
            metadata=metadata or {}
        )
        
        # Store association
        if chat_id not in self.file_associations:
            self.file_associations[chat_id] = []
        self.file_associations[chat_id].append(association)
        
        # Update context
        if chat_id in self.chat_contexts:
            self.chat_contexts[chat_id].file_associations.append({
                "file_id": file_id,
                "file_name": file_name,
                "type": association_type.value,
                "path": file_path
            })
        
        logger.info(f"File associated with chat {chat_id}: {file_name} ({association_type.value})")
        return association
    
    async def add_temporary_knowledge(
        self,
        chat_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Add temporary knowledge to chat context"""
        knowledge_id = str(uuid.uuid4())
        
        knowledge_item = {
            "id": knowledge_id,
            "content": content,
            "metadata": metadata or {},
            "created_at": datetime.now().isoformat(),
            "status": "temporary"
        }
        
        if chat_id not in self.chat_contexts:
            await self.create_or_update_context(chat_id)
        
        self.chat_contexts[chat_id].temporary_knowledge.append(knowledge_item)
        
        logger.info(f"Temporary knowledge added to chat {chat_id}: {knowledge_id}")
        return knowledge_id
    
    async def get_knowledge_for_decision(self, chat_id: str) -> List[Dict[str, Any]]:
        """Get temporary knowledge items pending decision"""
        if chat_id not in self.chat_contexts:
            return []
        
        context = self.chat_contexts[chat_id]
        pending_items = []
        
        for item in context.temporary_knowledge:
            if item.get("status") == "temporary":
                pending_items.append({
                    "id": item["id"],
                    "content": item["content"],
                    "metadata": item.get("metadata", {}),
                    "created_at": item["created_at"],
                    "suggested_action": self._suggest_knowledge_action(item["content"])
                })
        
        return pending_items
    
    def _suggest_knowledge_action(self, content: str) -> str:
        """Suggest action for knowledge based on content analysis"""
        # Simple heuristics for suggestions
        content_lower = content.lower()
        
        if any(keyword in content_lower for keyword in ["error", "bug", "issue", "problem"]):
            return KnowledgeDecision.ADD_TO_KB  # Useful for troubleshooting
        elif any(keyword in content_lower for keyword in ["config", "setup", "install", "guide"]):
            return KnowledgeDecision.ADD_TO_KB  # Useful for documentation
        elif len(content) < 50:
            return KnowledgeDecision.DELETE  # Too short to be useful
        else:
            return KnowledgeDecision.KEEP_TEMPORARY  # Keep for this session
    
    async def apply_knowledge_decision(
        self,
        chat_id: str,
        knowledge_id: str,
        decision: KnowledgeDecision
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
                kb_id = await self.knowledge_base.add_content(
                    content=item["content"],
                    metadata={
                        **item.get("metadata", {}),
                        "source": f"chat_{chat_id}",
                        "original_id": knowledge_id
                    }
                )
                
                # Track in context
                context.persistent_knowledge_ids.append(kb_id)
                item["status"] = "persistent"
                item["kb_id"] = kb_id
                
                logger.info(f"Knowledge {knowledge_id} added to KB as {kb_id}")
                
            except Exception as e:
                logger.error(f"Failed to add knowledge to KB: {e}")
                return False
                
        elif decision == KnowledgeDecision.KEEP_TEMPORARY:
            item["status"] = "session_only"
            logger.info(f"Knowledge {knowledge_id} kept as session-only")
            
        elif decision == KnowledgeDecision.DELETE:
            context.temporary_knowledge.remove(item)
            logger.info(f"Knowledge {knowledge_id} deleted")
        
        return True
    
    async def compile_chat_to_knowledge(
        self,
        chat_id: str,
        title: Optional[str] = None,
        include_system_messages: bool = False
    ) -> Dict[str, Any]:
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
        summary_prompt = f"""
        Summarize this conversation into a comprehensive knowledge base entry.
        Include key topics, solutions, code examples, and important information.
        
        Conversation:
        {json.dumps(messages, indent=2)}
        
        Format the summary with clear sections and bullet points.
        """
        
        summary_response = await self.llm_interface.chat_completion(
            model="default",
            messages=[{"role": "user", "content": summary_prompt}]
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
                    "assistant": len([m for m in messages if m.get("role") == "assistant"])
                }
            }
        }
        
        # Add to knowledge base
        kb_id = await self.knowledge_base.add_content(
            content=summary,
            metadata=compiled_knowledge["metadata"]
        )
        
        compiled_knowledge["kb_id"] = kb_id
        
        logger.info(f"Chat {chat_id} compiled to knowledge base as {kb_id}")
        return compiled_knowledge
    
    async def search_chat_knowledge(
        self,
        query: str,
        chat_id: Optional[str] = None,
        include_temporary: bool = True
    ) -> List[Dict[str, Any]]:
        """Search knowledge across chats or within specific chat"""
        results = []
        
        # Search in permanent knowledge base
        kb_results = await self.knowledge_base.search(query, n_results=10)
        
        for result in kb_results:
            # Filter by chat if specified
            if chat_id and result.get("metadata", {}).get("source") != f"chat_{chat_id}":
                continue
            
            results.append({
                "type": "persistent",
                "content": result["content"],
                "metadata": result.get("metadata", {}),
                "score": result.get("score", 0)
            })
        
        # Search in temporary knowledge if requested
        if include_temporary:
            contexts_to_search = [self.chat_contexts[chat_id]] if chat_id else self.chat_contexts.values()
            
            for context in contexts_to_search:
                for item in context.temporary_knowledge:
                    if query.lower() in item["content"].lower():
                        results.append({
                            "type": "temporary",
                            "chat_id": context.chat_id,
                            "content": item["content"],
                            "metadata": item.get("metadata", {}),
                            "score": 0.5  # Simple keyword match score
                        })
        
        # Sort by score
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        return results[:20]  # Limit to top 20 results


# Global manager instance
chat_knowledge_manager = ChatKnowledgeManager()


# API Endpoints

class CreateContextRequest(BaseModel):
    chat_id: str
    topic: Optional[str] = None
    keywords: Optional[List[str]] = None


@router.post("/context/create")
async def create_chat_context(request: CreateContextRequest):
    """Create or update knowledge context for a chat"""
    try:
        context = await chat_knowledge_manager.create_or_update_context(
            chat_id=request.chat_id,
            topic=request.topic,
            keywords=request.keywords
        )
        
        return {
            "success": True,
            "context": {
                "chat_id": context.chat_id,
                "topic": context.topic,
                "keywords": context.keywords,
                "created_at": context.created_at.isoformat(),
                "updated_at": context.updated_at.isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to create context: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class AssociateFileRequest(BaseModel):
    chat_id: str
    file_path: str
    association_type: FileAssociationType
    metadata: Optional[Dict[str, Any]] = None


@router.post("/files/associate")
async def associate_file_with_chat(request: AssociateFileRequest):
    """Associate a file with a chat session"""
    try:
        association = await chat_knowledge_manager.associate_file(
            chat_id=request.chat_id,
            file_path=request.file_path,
            association_type=request.association_type,
            metadata=request.metadata
        )
        
        return {
            "success": True,
            "association": {
                "file_id": association.file_id,
                "file_name": association.file_name,
                "association_type": association.association_type.value,
                "created_at": association.created_at.isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to associate file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/files/upload/{chat_id}")
async def upload_file_to_chat(
    chat_id: str,
    file: UploadFile = File(...),
    association_type: str = Form(default="upload")
):
    """Upload a file and associate it with a chat"""
    try:
        # Save uploaded file
        file_path = os.path.join(
            chat_knowledge_manager.storage_dir,
            f"{chat_id}_{file.filename}"
        )
        
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Associate with chat
        association = await chat_knowledge_manager.associate_file(
            chat_id=chat_id,
            file_path=file_path,
            association_type=FileAssociationType(association_type),
            metadata={"original_filename": file.filename}
        )
        
        return {
            "success": True,
            "file_id": association.file_id,
            "file_path": file_path
        }
        
    except Exception as e:
        logger.error(f"Failed to upload file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class AddKnowledgeRequest(BaseModel):
    chat_id: str
    content: str
    metadata: Optional[Dict[str, Any]] = None


@router.post("/knowledge/add_temporary")
async def add_temporary_knowledge(request: AddKnowledgeRequest):
    """Add temporary knowledge to chat context"""
    try:
        knowledge_id = await chat_knowledge_manager.add_temporary_knowledge(
            chat_id=request.chat_id,
            content=request.content,
            metadata=request.metadata
        )
        
        return {
            "success": True,
            "knowledge_id": knowledge_id
        }
        
    except Exception as e:
        logger.error(f"Failed to add temporary knowledge: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge/pending/{chat_id}")
async def get_pending_knowledge_decisions(chat_id: str):
    """Get knowledge items pending user decision"""
    try:
        pending_items = await chat_knowledge_manager.get_knowledge_for_decision(chat_id)
        
        return {
            "success": True,
            "pending_items": pending_items,
            "count": len(pending_items)
        }
        
    except Exception as e:
        logger.error(f"Failed to get pending knowledge: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class KnowledgeDecisionRequest(BaseModel):
    chat_id: str
    knowledge_id: str
    decision: KnowledgeDecision


@router.post("/knowledge/decide")
async def apply_knowledge_decision(request: KnowledgeDecisionRequest):
    """Apply user decision for temporary knowledge"""
    try:
        success = await chat_knowledge_manager.apply_knowledge_decision(
            chat_id=request.chat_id,
            knowledge_id=request.knowledge_id,
            decision=request.decision
        )
        
        return {
            "success": success,
            "message": f"Knowledge {request.decision.value} applied"
        }
        
    except Exception as e:
        logger.error(f"Failed to apply knowledge decision: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class CompileChatRequest(BaseModel):
    chat_id: str
    title: Optional[str] = None
    include_system_messages: bool = False


@router.post("/compile")
async def compile_chat_to_knowledge(request: CompileChatRequest):
    """Compile entire chat conversation to knowledge base"""
    try:
        compiled = await chat_knowledge_manager.compile_chat_to_knowledge(
            chat_id=request.chat_id,
            title=request.title,
            include_system_messages=request.include_system_messages
        )
        
        return {
            "success": True,
            "compiled": compiled
        }
        
    except Exception as e:
        logger.error(f"Failed to compile chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SearchRequest(BaseModel):
    query: str
    chat_id: Optional[str] = None
    include_temporary: bool = True


@router.post("/search")
async def search_chat_knowledge(request: SearchRequest):
    """Search knowledge across chats or within specific chat"""
    try:
        results = await chat_knowledge_manager.search_chat_knowledge(
            query=request.query,
            chat_id=request.chat_id,
            include_temporary=request.include_temporary
        )
        
        return {
            "success": True,
            "results": results,
            "count": len(results)
        }
        
    except Exception as e:
        logger.error(f"Failed to search knowledge: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/context/{chat_id}")
async def get_chat_context(chat_id: str):
    """Get complete knowledge context for a chat"""
    try:
        context = chat_knowledge_manager.chat_contexts.get(chat_id)
        
        if not context:
            return {
                "success": False,
                "message": "No context found for chat"
            }
        
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
                        "size": f.size_bytes
                    }
                    for f in file_associations
                ]
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get chat context: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check endpoint for chat knowledge system"""
    try:
        return {
            "status": "healthy",
            "service": "chat_knowledge",
            "manager_initialized": chat_knowledge_manager is not None,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Chat knowledge health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    # Example usage
    async def demo():
        manager = ChatKnowledgeManager()
        
        # Create context
        context = await manager.create_or_update_context(
            chat_id="test_chat_123",
            topic="Python Development",
            keywords=["python", "fastapi", "async"]
        )
        
        # Add temporary knowledge
        knowledge_id = await manager.add_temporary_knowledge(
            chat_id="test_chat_123",
            content="FastAPI is a modern web framework for Python with automatic API documentation.",
            metadata={"category": "framework"}
        )
        
        # Get pending decisions
        pending = await manager.get_knowledge_for_decision("test_chat_123")
        print(f"Pending decisions: {pending}")
        
        # Apply decision
        await manager.apply_knowledge_decision(
            chat_id="test_chat_123",
            knowledge_id=knowledge_id,
            decision=KnowledgeDecision.ADD_TO_KB
        )
        
        print("Demo completed!")
    
    import asyncio
    asyncio.run(demo())