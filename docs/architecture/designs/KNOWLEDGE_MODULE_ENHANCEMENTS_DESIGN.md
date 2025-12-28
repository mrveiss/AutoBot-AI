# Knowledge Module Enhancements Design

**Issue**: #645 - Implement Industry-Standard Agent Architecture Patterns
**Author**: mrveiss
**Date**: 2025-12-28
**Status**: Draft

---

## 1. Overview

This document defines enhancements to AutoBot's Knowledge Module inspired by industry-leading agent architectures (Manus, Cursor). The enhancements provide:

- Scoped knowledge with adoption conditions
- Priority-based knowledge retrieval (Data API > Web > Internal)
- Event stream integration for knowledge visibility
- Memory rating system for quality control

---

## 2. Industry Pattern Analysis

### 2.1 Manus Knowledge Module

From the Manus architecture:

1. **Scoped Knowledge**: Each knowledge item has a scope (python, frontend, etc.)
2. **Adoption Conditions**: Conditions that must be met to apply the knowledge
3. **Priority Order**: Data API > Web Search > Internal Knowledge
4. **Event Integration**: Knowledge provided as events in the event stream

### 2.2 Cursor Memory System

From the Cursor architecture:

1. **Rating System**: 1-5 score for knowledge quality
2. **Specific & Actionable**: High-rated items are specific and generalizable
3. **Project Context**: Lower-rated items are tied to specific files/code

---

## 3. Data Structures

### 3.1 Scoped Knowledge Item

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
import uuid

class KnowledgeScope(Enum):
    """Scope/domain of knowledge applicability"""
    GENERAL = "general"
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    VUE = "vue"
    FRONTEND = "frontend"
    BACKEND = "backend"
    DATABASE = "database"
    REDIS = "redis"
    DOCKER = "docker"
    SECURITY = "security"
    TESTING = "testing"
    API = "api"
    GIT = "git"

class KnowledgeSource(Enum):
    """Source of the knowledge"""
    CHROMADB = "chromadb"          # Vector database
    MEMORY_MCP = "memory_mcp"      # Memory MCP server
    FILE_SYSTEM = "file_system"    # Codebase files
    WEB_SEARCH = "web_search"      # Web search results
    DATA_API = "data_api"          # External data APIs
    USER_PROVIDED = "user_provided" # Explicit user input
    INFERRED = "inferred"          # Agent-inferred

class KnowledgePriority(Enum):
    """Priority for knowledge application"""
    CRITICAL = 5    # Must always apply
    HIGH = 4        # Strongly preferred
    MEDIUM = 3      # Apply when relevant
    LOW = 2         # Optional enhancement
    BACKGROUND = 1  # Nice to have

@dataclass
class AdoptionCondition:
    """Condition that must be met to apply knowledge"""
    condition_type: str  # "file_type", "task_type", "context_contains", "always"
    value: Any
    operator: str = "equals"  # "equals", "contains", "matches", "exists"

    def evaluate(self, context: dict) -> bool:
        """Evaluate if condition is met in current context"""
        if self.condition_type == "always":
            return True

        context_value = context.get(self.condition_type)
        if context_value is None:
            return False

        if self.operator == "equals":
            return context_value == self.value
        elif self.operator == "contains":
            return self.value in str(context_value)
        elif self.operator == "matches":
            import re
            return bool(re.match(self.value, str(context_value)))
        elif self.operator == "exists":
            return context_value is not None

        return False

@dataclass
class ScopedKnowledge:
    """Knowledge item with scope and adoption conditions"""

    # Identity
    knowledge_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Content
    content: str = ""
    summary: str = ""  # Brief description
    source_type: KnowledgeSource = KnowledgeSource.CHROMADB

    # Scoping
    scope: KnowledgeScope = KnowledgeScope.GENERAL
    scopes: list[KnowledgeScope] = field(default_factory=list)  # Multiple scopes

    # Adoption
    conditions: list[AdoptionCondition] = field(default_factory=list)
    priority: KnowledgePriority = KnowledgePriority.MEDIUM

    # Quality (Cursor-style rating)
    quality_score: int = 3  # 1-5 scale
    is_actionable: bool = True
    is_generalizable: bool = True

    # Tracking
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_used_at: Optional[datetime] = None
    use_count: int = 0

    # Metadata
    document_ids: list[str] = field(default_factory=list)
    source_url: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def is_applicable(self, context: dict) -> bool:
        """Check if knowledge applies to current context"""
        if not self.conditions:
            return True  # No conditions = always applicable

        # Check scope match
        current_scope = context.get("scope")
        if current_scope:
            scope_enum = KnowledgeScope(current_scope) if isinstance(current_scope, str) else current_scope
            if self.scopes and scope_enum not in self.scopes:
                return False
            if self.scope != KnowledgeScope.GENERAL and self.scope != scope_enum:
                return False

        # All conditions must be met
        return all(cond.evaluate(context) for cond in self.conditions)

    def to_dict(self) -> dict:
        return {
            "knowledge_id": self.knowledge_id,
            "content": self.content,
            "summary": self.summary,
            "source_type": self.source_type.value,
            "scope": self.scope.value,
            "scopes": [s.value for s in self.scopes],
            "conditions": [
                {"type": c.condition_type, "value": c.value, "operator": c.operator}
                for c in self.conditions
            ],
            "priority": self.priority.value,
            "quality_score": self.quality_score,
            "is_actionable": self.is_actionable,
            "is_generalizable": self.is_generalizable,
            "created_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "use_count": self.use_count,
            "document_ids": self.document_ids,
            "source_url": self.source_url,
            "metadata": self.metadata,
        }
```

### 3.2 Knowledge Query

```python
@dataclass
class KnowledgeQuery:
    """Query for knowledge retrieval"""

    # Query content
    query_text: str
    query_embedding: Optional[list[float]] = None

    # Filters
    scopes: list[KnowledgeScope] = field(default_factory=list)
    sources: list[KnowledgeSource] = field(default_factory=list)
    min_quality_score: int = 1
    min_priority: KnowledgePriority = KnowledgePriority.BACKGROUND

    # Context for condition evaluation
    context: dict = field(default_factory=dict)

    # Retrieval settings
    max_results: int = 10
    min_relevance_score: float = 0.5

    # Priority order (Manus pattern)
    source_priority: list[KnowledgeSource] = field(default_factory=lambda: [
        KnowledgeSource.DATA_API,
        KnowledgeSource.WEB_SEARCH,
        KnowledgeSource.CHROMADB,
        KnowledgeSource.MEMORY_MCP,
        KnowledgeSource.FILE_SYSTEM,
    ])
```

---

## 4. Enhanced Knowledge Module

### 4.1 Core Interface

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator

class KnowledgeModule(ABC):
    """Abstract knowledge module interface"""

    @abstractmethod
    async def retrieve(
        self,
        query: KnowledgeQuery,
    ) -> list[ScopedKnowledge]:
        """Retrieve relevant knowledge for a query"""
        pass

    @abstractmethod
    async def add(
        self,
        knowledge: ScopedKnowledge,
    ) -> str:
        """Add new knowledge item"""
        pass

    @abstractmethod
    async def update(
        self,
        knowledge_id: str,
        updates: dict,
    ) -> ScopedKnowledge:
        """Update existing knowledge"""
        pass

    @abstractmethod
    async def rate(
        self,
        knowledge_id: str,
        score: int,
        feedback: str | None = None,
    ) -> None:
        """Rate knowledge quality (1-5)"""
        pass

    @abstractmethod
    async def get_applicable(
        self,
        context: dict,
    ) -> list[ScopedKnowledge]:
        """Get all knowledge applicable to current context"""
        pass
```

### 4.2 Enhanced Implementation

```python
import logging
from typing import Any

from src.events.stream_manager import EventStreamManager
from src.events.types import AgentEvent, EventType
from src.npu_semantic_search import NPUSemanticSearch

logger = logging.getLogger(__name__)

class EnhancedKnowledgeModule(KnowledgeModule):
    """
    Enhanced knowledge module with:
    - Scoped knowledge retrieval
    - Priority-based source ordering
    - Quality rating system
    - Event stream integration
    """

    def __init__(
        self,
        chromadb_client: Any,
        memory_mcp: Any,
        npu_search: NPUSemanticSearch,
        event_stream: EventStreamManager,
        redis_client: Any,
    ):
        self.chromadb = chromadb_client
        self.memory_mcp = memory_mcp
        self.npu_search = npu_search
        self.event_stream = event_stream
        self.redis = redis_client

        # In-memory cache for hot knowledge
        self._cache: dict[str, ScopedKnowledge] = {}

    async def retrieve(
        self,
        query: KnowledgeQuery,
    ) -> list[ScopedKnowledge]:
        """
        Retrieve knowledge with priority ordering.

        Order: Data API > Web Search > ChromaDB > Memory MCP > File System
        """
        all_results: list[tuple[ScopedKnowledge, float]] = []

        # Query each source in priority order
        for source in query.source_priority:
            if query.sources and source not in query.sources:
                continue

            try:
                results = await self._query_source(source, query)
                all_results.extend(results)

                # Stop early if we have enough high-quality results
                high_quality = [
                    r for r, score in all_results
                    if r.quality_score >= 4 and score >= 0.8
                ]
                if len(high_quality) >= query.max_results:
                    break

            except Exception as e:
                logger.warning("Failed to query %s: %s", source.value, e)

        # Sort by relevance and quality
        all_results.sort(
            key=lambda x: (x[0].quality_score * 0.3 + x[1] * 0.7),
            reverse=True,
        )

        # Filter by conditions and take top results
        applicable = []
        for knowledge, score in all_results:
            if len(applicable) >= query.max_results:
                break

            if knowledge.is_applicable(query.context):
                # Update usage tracking
                knowledge.last_used_at = datetime.utcnow()
                knowledge.use_count += 1
                applicable.append(knowledge)

        # Publish KNOWLEDGE event
        if applicable:
            await self.event_stream.publish(AgentEvent(
                event_type=EventType.KNOWLEDGE,
                content={
                    "knowledge_items": [k.to_dict() for k in applicable],
                    "query": query.query_text,
                    "scope": query.scopes[0].value if query.scopes else "general",
                    "relevance_score": sum(k.quality_score for k in applicable) / len(applicable),
                    "source_type": applicable[0].source_type.value if applicable else "none",
                    "document_ids": [
                        doc_id
                        for k in applicable
                        for doc_id in k.document_ids
                    ],
                },
                source="knowledge_module",
                task_id=query.context.get("task_id"),
            ))

        return applicable

    async def _query_source(
        self,
        source: KnowledgeSource,
        query: KnowledgeQuery,
    ) -> list[tuple[ScopedKnowledge, float]]:
        """Query a specific knowledge source"""

        if source == KnowledgeSource.CHROMADB:
            return await self._query_chromadb(query)

        elif source == KnowledgeSource.MEMORY_MCP:
            return await self._query_memory_mcp(query)

        elif source == KnowledgeSource.FILE_SYSTEM:
            return await self._query_file_system(query)

        elif source == KnowledgeSource.WEB_SEARCH:
            return await self._query_web_search(query)

        elif source == KnowledgeSource.DATA_API:
            return await self._query_data_api(query)

        return []

    async def _query_chromadb(
        self,
        query: KnowledgeQuery,
    ) -> list[tuple[ScopedKnowledge, float]]:
        """Query ChromaDB vector database"""
        # Generate embedding if not provided
        if query.query_embedding is None:
            embedding = await self.npu_search.generate_embedding(query.query_text)
        else:
            embedding = query.query_embedding

        # Query ChromaDB
        results = self.chromadb.query(
            query_embeddings=[embedding],
            n_results=query.max_results * 2,  # Get more to filter
            where={
                "$and": [
                    {"scope": {"$in": [s.value for s in query.scopes]}} if query.scopes else {},
                ]
            } if query.scopes else None,
        )

        knowledge_items = []
        for i, (doc_id, document, metadata, distance) in enumerate(
            zip(
                results["ids"][0],
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ):
            # Convert distance to relevance score (assuming cosine distance)
            relevance = 1 - (distance / 2)  # Normalize to 0-1

            if relevance < query.min_relevance_score:
                continue

            knowledge = ScopedKnowledge(
                knowledge_id=doc_id,
                content=document,
                summary=document[:200] + "..." if len(document) > 200 else document,
                source_type=KnowledgeSource.CHROMADB,
                scope=KnowledgeScope(metadata.get("scope", "general")),
                quality_score=metadata.get("quality_score", 3),
                document_ids=[doc_id],
                metadata=metadata,
            )

            knowledge_items.append((knowledge, relevance))

        return knowledge_items

    async def _query_memory_mcp(
        self,
        query: KnowledgeQuery,
    ) -> list[tuple[ScopedKnowledge, float]]:
        """Query Memory MCP server"""
        try:
            # Use Memory MCP search
            results = await self.memory_mcp.search_nodes(query=query.query_text)

            knowledge_items = []
            for entity in results.get("entities", []):
                knowledge = ScopedKnowledge(
                    knowledge_id=entity.get("name", str(uuid.uuid4())),
                    content="\n".join(entity.get("observations", [])),
                    summary=entity.get("name", ""),
                    source_type=KnowledgeSource.MEMORY_MCP,
                    scope=self._infer_scope(entity.get("entityType", "")),
                    quality_score=4,  # Memory MCP items are generally high quality
                    metadata=entity,
                )

                # Estimate relevance (could use embedding similarity)
                relevance = 0.7  # Default moderate relevance
                knowledge_items.append((knowledge, relevance))

            return knowledge_items

        except Exception as e:
            logger.warning("Memory MCP query failed: %s", e)
            return []

    async def _query_file_system(
        self,
        query: KnowledgeQuery,
    ) -> list[tuple[ScopedKnowledge, float]]:
        """Query codebase files via semantic search"""
        results = await self.npu_search.search(
            query=query.query_text,
            top_k=query.max_results,
        )

        knowledge_items = []
        for result in results:
            knowledge = ScopedKnowledge(
                knowledge_id=result.doc_id,
                content=result.content,
                summary=result.content[:200] + "...",
                source_type=KnowledgeSource.FILE_SYSTEM,
                scope=self._infer_scope_from_path(result.metadata.get("file_path", "")),
                quality_score=3,
                document_ids=[result.doc_id],
                metadata=result.metadata,
            )

            knowledge_items.append((knowledge, result.score))

        return knowledge_items

    async def _query_web_search(
        self,
        query: KnowledgeQuery,
    ) -> list[tuple[ScopedKnowledge, float]]:
        """Query web search (placeholder - needs web search integration)"""
        # TODO: Integrate with web search API
        return []

    async def _query_data_api(
        self,
        query: KnowledgeQuery,
    ) -> list[tuple[ScopedKnowledge, float]]:
        """Query external data APIs (placeholder - needs API registry)"""
        # TODO: Integrate with data API registry
        return []

    def _infer_scope(self, entity_type: str) -> KnowledgeScope:
        """Infer scope from entity type"""
        scope_map = {
            "python": KnowledgeScope.PYTHON,
            "typescript": KnowledgeScope.TYPESCRIPT,
            "vue": KnowledgeScope.VUE,
            "database": KnowledgeScope.DATABASE,
            "redis": KnowledgeScope.REDIS,
            "security": KnowledgeScope.SECURITY,
            "api": KnowledgeScope.API,
        }
        return scope_map.get(entity_type.lower(), KnowledgeScope.GENERAL)

    def _infer_scope_from_path(self, file_path: str) -> KnowledgeScope:
        """Infer scope from file path"""
        if file_path.endswith(".py"):
            return KnowledgeScope.PYTHON
        elif file_path.endswith((".ts", ".tsx")):
            return KnowledgeScope.TYPESCRIPT
        elif file_path.endswith(".vue"):
            return KnowledgeScope.VUE
        elif "test" in file_path.lower():
            return KnowledgeScope.TESTING
        elif "api" in file_path.lower():
            return KnowledgeScope.API
        return KnowledgeScope.GENERAL

    async def add(
        self,
        knowledge: ScopedKnowledge,
    ) -> str:
        """Add new knowledge item to ChromaDB"""
        # Generate embedding
        embedding = await self.npu_search.generate_embedding(knowledge.content)

        # Add to ChromaDB
        self.chromadb.add(
            ids=[knowledge.knowledge_id],
            documents=[knowledge.content],
            embeddings=[embedding],
            metadatas=[{
                "scope": knowledge.scope.value,
                "quality_score": knowledge.quality_score,
                "source_type": knowledge.source_type.value,
                "created_at": knowledge.created_at.isoformat(),
                **knowledge.metadata,
            }],
        )

        # Cache
        self._cache[knowledge.knowledge_id] = knowledge

        logger.info("Added knowledge: %s (scope=%s)", knowledge.knowledge_id, knowledge.scope.value)
        return knowledge.knowledge_id

    async def rate(
        self,
        knowledge_id: str,
        score: int,
        feedback: str | None = None,
    ) -> None:
        """
        Rate knowledge quality (Cursor-style 1-5 rating).

        Rating criteria:
        5 - Specific, actionable, generalizable preference
        4 - Clear configuration/workflow preference
        3 - Project-specific but helpful
        1-2 - Vague, obvious, or tied to specific code
        """
        if score < 1 or score > 5:
            raise ValueError("Score must be between 1 and 5")

        # Update in ChromaDB
        existing = self.chromadb.get(ids=[knowledge_id])
        if existing and existing["ids"]:
            metadata = existing["metadatas"][0]
            metadata["quality_score"] = score
            if feedback:
                metadata["rating_feedback"] = feedback
            metadata["rated_at"] = datetime.utcnow().isoformat()

            self.chromadb.update(
                ids=[knowledge_id],
                metadatas=[metadata],
            )

        # Update cache
        if knowledge_id in self._cache:
            self._cache[knowledge_id].quality_score = score

        logger.info("Rated knowledge %s: score=%d", knowledge_id, score)

    async def get_applicable(
        self,
        context: dict,
    ) -> list[ScopedKnowledge]:
        """Get all knowledge applicable to current context without query"""
        # Build query from context
        query = KnowledgeQuery(
            query_text=context.get("task_description", ""),
            context=context,
            scopes=[KnowledgeScope(context["scope"])] if context.get("scope") else [],
            max_results=20,
        )

        return await self.retrieve(query)

    async def update(
        self,
        knowledge_id: str,
        updates: dict,
    ) -> ScopedKnowledge:
        """Update existing knowledge"""
        existing = self.chromadb.get(ids=[knowledge_id])
        if not existing or not existing["ids"]:
            raise ValueError(f"Knowledge not found: {knowledge_id}")

        metadata = existing["metadatas"][0]
        metadata.update(updates)
        metadata["updated_at"] = datetime.utcnow().isoformat()

        self.chromadb.update(
            ids=[knowledge_id],
            metadatas=[metadata],
        )

        # Update cache
        if knowledge_id in self._cache:
            for key, value in updates.items():
                if hasattr(self._cache[knowledge_id], key):
                    setattr(self._cache[knowledge_id], key, value)
            return self._cache[knowledge_id]

        # Return updated knowledge
        return ScopedKnowledge(
            knowledge_id=knowledge_id,
            content=existing["documents"][0],
            **metadata,
        )
```

---

## 5. Quality Rating Criteria

### 5.1 Cursor-Style Rating System

| Score | Criteria | Examples |
|-------|----------|----------|
| 5 | Specific, actionable, generalizable | "Prefer Svelte over React", "Use TypeScript strict mode" |
| 4 | Clear configuration/workflow | "strictNullChecks: true always", "Run tests before commit" |
| 3 | Project-specific but helpful | "Frontend code in 'components' dir", "Use Redis for caching" |
| 2 | Somewhat helpful, limited scope | "This function handles auth", "Config file at path X" |
| 1 | Vague or obvious | "Code should be clean", "Add comments" |

### 5.2 Auto-Rating Logic

```python
def auto_rate_knowledge(knowledge: ScopedKnowledge) -> int:
    """Automatically rate knowledge based on characteristics"""
    score = 3  # Start at medium

    # Actionable (has verbs like "use", "prefer", "always")
    actionable_words = ["use", "prefer", "always", "never", "must", "should"]
    if any(word in knowledge.content.lower() for word in actionable_words):
        score += 1

    # Generalizable (not tied to specific files/lines)
    specific_patterns = [r"line \d+", r"file [\w/]+\.\w+", r"function \w+\(\)"]
    if not any(re.search(p, knowledge.content) for p in specific_patterns):
        score += 1

    # Too vague (very short or generic)
    if len(knowledge.content) < 50:
        score -= 1
    if any(vague in knowledge.content.lower() for vague in ["good", "clean", "better"]):
        score -= 1

    return max(1, min(5, score))
```

---

## 6. Configuration

```python
@dataclass
class KnowledgeModuleConfig:
    """Knowledge module configuration"""

    # Retrieval settings
    max_results_per_source: int = 10
    min_relevance_score: float = 0.5
    min_quality_score: int = 2

    # Cache settings
    cache_ttl_seconds: int = 3600
    max_cache_size: int = 1000

    # Source priority (Manus pattern)
    source_priority: list[str] = field(default_factory=lambda: [
        "data_api",
        "web_search",
        "chromadb",
        "memory_mcp",
        "file_system",
    ])

    # Quality thresholds
    high_quality_threshold: int = 4
    auto_rate_new_knowledge: bool = True
```

---

## 7. File Structure

```
src/knowledge/
├── __init__.py
├── types.py              # KnowledgeScope, ScopedKnowledge, etc.
├── module.py             # KnowledgeModule interface
├── enhanced_module.py    # EnhancedKnowledgeModule implementation
├── rating.py             # Quality rating system
├── conditions.py         # AdoptionCondition evaluation
└── sources/
    ├── __init__.py
    ├── chromadb.py       # ChromaDB integration
    ├── memory_mcp.py     # Memory MCP integration
    ├── file_system.py    # File system search
    └── web_search.py     # Web search integration
```

---

## 8. Integration with Event Stream

```python
# Example KNOWLEDGE event content
{
    "knowledge_items": [
        {
            "knowledge_id": "abc123",
            "content": "Use TypeScript strict mode for better type safety",
            "summary": "TypeScript strict mode recommendation",
            "scope": "typescript",
            "quality_score": 5,
            "source_type": "memory_mcp",
        }
    ],
    "query": "How to configure TypeScript",
    "scope": "typescript",
    "relevance_score": 4.5,
    "source_type": "memory_mcp",
    "document_ids": ["doc1", "doc2"],
}
```

---

## 9. References

- Manus Knowledge Module: `docs/external_apps/.../Manus Agent Tools & Prompt/Modules.txt`
- Cursor Memory System: `docs/external_apps/.../Cursor Prompts/Memory Prompt.txt`
- Current ChromaDB integration: `src/knowledge/`
- Current Memory MCP: `src/utils/memory_mcp.py`
