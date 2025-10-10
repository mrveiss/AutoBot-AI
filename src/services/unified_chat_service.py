"""
Unified Chat Service - Consolidation of Duplicate Chat Implementations
Addresses massive code duplication identified by backend architecture agent:
- 4 chat implementations (chat.py, chat_improved.py, chat_knowledge.py, async_chat.py)
- 3,790 total lines of duplicate code
- Single source of truth for all chat operations
"""

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, List, Optional, Protocol
from datetime import datetime
from dataclasses import dataclass, field
import uuid

# Import optimized components
from utils.optimized_stream_processor import get_optimized_llm_interface
from utils.optimized_redis_manager import get_optimized_redis_manager
from utils.optimized_memory_manager import get_optimized_memory_manager
from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Chat message types for routing"""
    GENERAL = "general"
    TERMINAL = "terminal" 
    RESEARCH = "research"
    KNOWLEDGE = "knowledge"
    SYSTEM = "system"


class ChatResponse(Enum):
    """Chat response status"""
    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"
    STREAMING = "streaming"


@dataclass
class ChatKnowledgeContext:
    """Enhanced knowledge context from chat_knowledge.py"""
    session_id: str
    topic: str
    keywords: List[str] = field(default_factory=list)
    confidence_score: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    temporary_knowledge: List[Dict[str, Any]] = field(default_factory=list)
    persistent_knowledge_ids: List[str] = field(default_factory=list)
    file_associations: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'session_id': self.session_id,
            'topic': self.topic,
            'keywords': self.keywords,
            'confidence_score': self.confidence_score,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'temporary_knowledge': self.temporary_knowledge,
            'persistent_knowledge_ids': self.persistent_knowledge_ids,
            'file_associations': self.file_associations,
            'metadata': self.metadata
        }


@dataclass
class ChatMessage:
    """Standardized chat message"""
    id: str
    session_id: str
    content: str
    role: str  # user, assistant, system
    message_type: MessageType
    timestamp: float
    metadata: Dict[str, Any] = None
    # Enhanced features from other implementations
    options: Dict[str, Any] = field(default_factory=dict)
    knowledge_context: Optional[ChatKnowledgeContext] = None
    workflow_messages: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'session_id': self.session_id,
            'content': self.content,
            'role': self.role,
            'message_type': self.message_type.value,
            'timestamp': self.timestamp,
            'metadata': self.metadata or {}
        }


@dataclass
class ChatResult:
    """Standardized chat response - enhanced with best features"""
    status: ChatResponse
    content: str
    message_id: str
    processing_time: float
    metadata: Dict[str, Any] = None
    error: Optional[str] = None
    # Enhanced features from async_chat.py
    conversation_id: Optional[str] = None
    workflow_messages: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[Dict[str, Any]] = field(default_factory=list)
    # Enhanced features from chat_knowledge.py
    knowledge_context: Optional[ChatKnowledgeContext] = None
    knowledge_decision: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'status': self.status.value,
            'content': self.content,
            'message_id': self.message_id,
            'processing_time': self.processing_time,
            'metadata': self.metadata or {},
            'error': self.error,
            'conversation_id': self.conversation_id,
            'workflow_messages': self.workflow_messages,
            'sources': self.sources,
            'knowledge_context': self.knowledge_context.to_dict() if self.knowledge_context else None,
            'knowledge_decision': self.knowledge_decision
        }


class ChatProcessor(Protocol):
    """Protocol for chat processors"""
    async def process_message(self, message: ChatMessage) -> ChatResult: ...
    async def supports_streaming(self) -> bool: ...


class GeneralChatProcessor:
    """General purpose chat processor using optimized LLM interface"""
    
    def __init__(self):
        self.llm_interface = None
    
    async def _ensure_llm_interface(self):
        """Lazy load LLM interface"""
        if self.llm_interface is None:
            self.llm_interface = await get_optimized_llm_interface()
    
    async def process_message(self, message: ChatMessage) -> ChatResult:
        """Process general chat message with optimized streaming"""
        start_time = time.time()
        
        try:
            await self._ensure_llm_interface()
            
            # Convert to Ollama format
            messages = [{"role": message.role, "content": message.content}]
            
            # Use optimized streaming with environment variables
            import os
            ollama_host = os.getenv('AUTOBOT_OLLAMA_HOST')
            ollama_port = os.getenv('AUTOBOT_OLLAMA_PORT')
            if not ollama_host or not ollama_port:
                raise ValueError('Ollama configuration missing: AUTOBOT_OLLAMA_HOST and AUTOBOT_OLLAMA_PORT environment variables must be set')
            url = f"http://{ollama_host}:{ollama_port}/api/chat"
            data = {
                "model": "llama3.1:8b",
                "messages": messages,
                "stream": True,
                "options": {
                    "temperature": 0.7,
                    "num_ctx": 4096
                }
            }
            
            content, success = await self.llm_interface.stream_ollama_request(url, data)
            processing_time = (time.time() - start_time) * 1000
            
            return ChatResult(
                status=ChatResponse.SUCCESS if success else ChatResponse.ERROR,
                content=content,
                message_id=message.id,
                processing_time=processing_time,
                metadata={
                    'model': 'llama3.1:8b',
                    'optimized_streaming': True,
                    'natural_completion': success
                }
            )
            
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            logger.error(f"General chat processing error: {e}")
            
            return ChatResult(
                status=ChatResponse.ERROR,
                content=f"Error processing message: {str(e)}",
                message_id=message.id,
                processing_time=processing_time,
                error=str(e)
            )
    
    async def supports_streaming(self) -> bool:
        return True


class KnowledgeChatProcessor:
    """Enhanced knowledge-based chat processor with best features consolidated"""
    
    def __init__(self):
        self.knowledge_base = None
        self.general_processor = GeneralChatProcessor()
        self.knowledge_contexts = {}  # session_id -> ChatKnowledgeContext
    
    def _create_or_update_context(self, session_id: str, topic: str, keywords: List[str]) -> ChatKnowledgeContext:
        """Create or update knowledge context for session"""
        if session_id in self.knowledge_contexts:
            context = self.knowledge_contexts[session_id]
            context.topic = topic
            context.keywords.extend(k for k in keywords if k not in context.keywords)
            context.updated_at = datetime.now()
        else:
            context = ChatKnowledgeContext(
                session_id=session_id,
                topic=topic,
                keywords=keywords
            )
            self.knowledge_contexts[session_id] = context
        return context
    
    def _extract_keywords(self, content: str) -> List[str]:
        """Extract keywords from message content"""
        # Simple keyword extraction - could be enhanced with NLP
        words = content.lower().split()
        keywords = [w for w in words if len(w) > 3 and w.isalpha()]
        return keywords[:10]  # Limit to top 10 keywords
    
    async def process_message(self, message: ChatMessage) -> ChatResult:
        """Process knowledge-based chat with search"""
        start_time = time.time()
        
        try:
            # Extract keywords and create/update knowledge context
            keywords = self._extract_keywords(message.content)
            topic = message.content[:100]  # First 100 chars as topic
            context = self._create_or_update_context(message.session_id, topic, keywords)
            
            # Search knowledge base (if available)
            knowledge_results = []
            if self.knowledge_base:
                # TODO: Integrate with knowledge base search
                # knowledge_results = await self.knowledge_base.search(message.content, n_results=5)
                pass
            
            # Determine knowledge decision
            knowledge_decision = "FOUND" if knowledge_results else "SEARCH_NEEDED"
            
            # Enhance message with knowledge context
            enhanced_content = message.content
            if knowledge_results:
                context_text = "\n".join([r.get("content", "") for r in knowledge_results[:3]])
                enhanced_content = f"Context: {context_text}\n\nQuestion: {message.content}"
                context.confidence_score = 0.8  # High confidence with KB results
            else:
                context.confidence_score = 0.3  # Low confidence without KB
            
            # Use general processor with enhanced content
            enhanced_message = ChatMessage(
                id=message.id,
                session_id=message.session_id,
                content=enhanced_content,
                role=message.role,
                message_type=message.message_type,
                timestamp=message.timestamp,
                metadata=message.metadata,
                knowledge_context=context
            )
            
            result = await self.general_processor.process_message(enhanced_message)
            
            # Enhance result with knowledge features
            result.knowledge_context = context
            result.knowledge_decision = knowledge_decision
            result.conversation_id = message.session_id
            
            # Add knowledge metadata
            if result.metadata is None:
                result.metadata = {}
            result.metadata['knowledge_enhanced'] = bool(knowledge_results)
            result.metadata['knowledge_results_count'] = len(knowledge_results)
            result.metadata['knowledge_keywords'] = keywords
            result.metadata['confidence_score'] = context.confidence_score
            
            # Add sources if knowledge was found
            if knowledge_results:
                result.sources = [
                    {
                        "type": "knowledge_base",
                        "content": r.get("content", "")[:200],
                        "metadata": r.get("metadata", {})
                    }
                    for r in knowledge_results
                ]
            
            return result
            
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            logger.error(f"Knowledge chat processing error: {e}")
            
            return ChatResult(
                status=ChatResponse.ERROR,
                content=f"Error processing knowledge query: {str(e)}",
                message_id=message.id,
                processing_time=processing_time,
                error=str(e)
            )
    
    async def supports_streaming(self) -> bool:
        return True


class UnifiedChatService:
    """
    Unified chat service that consolidates all chat functionality
    Single source of truth for chat operations
    """
    
    def __init__(self):
        self.processors = {
            MessageType.GENERAL: GeneralChatProcessor(),
            MessageType.KNOWLEDGE: KnowledgeChatProcessor(),
            MessageType.RESEARCH: KnowledgeChatProcessor(),  # Use knowledge processor for research
            MessageType.TERMINAL: GeneralChatProcessor(),    # TODO: Implement terminal processor
            MessageType.SYSTEM: GeneralChatProcessor()       # TODO: Implement system processor
        }
        
        self.redis_manager = None
        self.memory_manager = None
        self.session_cache = None
        
    async def _ensure_dependencies(self):
        """Lazy load dependencies"""
        if self.redis_manager is None:
            self.redis_manager = get_optimized_redis_manager()
        
        if self.memory_manager is None:
            self.memory_manager = get_optimized_memory_manager()
            self.session_cache = self.memory_manager.create_lru_cache('chat_sessions', 1000)
    
    def _classify_message(self, content: str) -> MessageType:
        """Classify message type based on content"""
        content_lower = content.lower()
        
        if any(word in content_lower for word in ['terminal', 'command', 'bash', 'shell']):
            return MessageType.TERMINAL
        elif any(word in content_lower for word in ['search', 'find', 'research', 'lookup']):
            return MessageType.RESEARCH
        elif any(word in content_lower for word in ['knowledge', 'documentation', 'docs']):
            return MessageType.KNOWLEDGE
        elif any(word in content_lower for word in ['system', 'config', 'settings']):
            return MessageType.SYSTEM
        else:
            return MessageType.GENERAL
    
    async def process_message(
        self,
        session_id: str,
        content: str,
        role: str = "user",
        message_type: Optional[MessageType] = None
    ) -> ChatResult:
        """
        Process chat message using appropriate processor
        Unified entry point for all chat operations
        """
        await self._ensure_dependencies()
        
        # Create message
        message = ChatMessage(
            id=str(uuid.uuid4()),
            session_id=session_id,
            content=content,
            role=role,
            message_type=message_type or self._classify_message(content),
            timestamp=time.time()
        )
        
        # Get appropriate processor
        processor = self.processors.get(message.message_type, self.processors[MessageType.GENERAL])
        
        # Process message
        result = await processor.process_message(message)
        
        # Cache result
        if self.session_cache is not None:
            self.memory_manager.put_in_cache(
                'chat_sessions',
                f"{session_id}:{message.id}",
                {
                    'message': message.to_dict(),
                    'result': result.to_dict()
                }
            )
        
        # Store in Redis for persistence (optional)
        try:
            async with self.redis_manager.get_managed_client('localhost', 6379, 1) as client:
                client.hset(
                    f"chat:{session_id}",
                    message.id,
                    json.dumps({
                        'message': message.to_dict(),
                        'result': result.to_dict()
                    })
                )
                # Set expiration for session (24 hours)
                client.expire(f"chat:{session_id}", 86400)
        except Exception as e:
            logger.warning(f"Failed to persist chat to Redis: {e}")
        
        return result
    
    async def get_session_history(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get chat history for session"""
        await self._ensure_dependencies()
        
        history = []
        
        try:
            # Try Redis first
            async with self.redis_manager.get_managed_client('localhost', 6379, 1) as client:
                chat_data = client.hgetall(f"chat:{session_id}")
                
                for message_id, data_json in chat_data.items():
                    try:
                        data = json.loads(data_json)
                        history.append(data)
                    except json.JSONDecodeError:
                        continue
                
                # Sort by timestamp
                history.sort(key=lambda x: x.get('message', {}).get('timestamp', 0))
                
        except Exception as e:
            logger.warning(f"Failed to get session history from Redis: {e}")
        
        return history[-limit:] if history else []
    
    async def get_service_stats(self) -> Dict[str, Any]:
        """Get unified chat service statistics"""
        await self._ensure_dependencies()
        
        stats = {
            'timestamp': time.time(),
            'processors': {
                processor_type.value: {
                    'available': True,
                    'supports_streaming': await processor.supports_streaming()
                }
                for processor_type, processor in self.processors.items()
            }
        }
        
        # Add memory stats
        if self.memory_manager:
            stats['memory'] = self.memory_manager.get_cache_stats()
        
        # Add Redis stats
        if self.redis_manager:
            stats['redis'] = await self.redis_manager.health_check_all_pools()
        
        return stats


# Global unified chat service instance
_unified_chat_service = None

async def get_unified_chat_service() -> UnifiedChatService:
    """Get global unified chat service instance"""
    global _unified_chat_service
    if _unified_chat_service is None:
        _unified_chat_service = UnifiedChatService()
    return _unified_chat_service