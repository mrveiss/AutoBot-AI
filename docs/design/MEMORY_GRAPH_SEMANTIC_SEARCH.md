# AutoBot Memory Graph Semantic Search Design

**Version**: 1.0
**Date**: 2025-10-03
**Status**: Design Complete - Ready for Implementation

---

## Executive Summary

This document specifies the semantic search capabilities for AutoBot's Memory Graph system. The design enables natural language queries like "What bugs did we fix this week?" through a hybrid search approach combining Redis full-text search with Ollama-powered vector embeddings.

**Key Design Decisions**:
- **Hybrid Search (Option C)**: Combines RedisSearch for structured queries + vector embeddings for semantic similarity
- **Infrastructure Reuse**: Leverages existing Knowledge Base V2 (Ollama, nomic-embed-text, RedisVectorStore)
- **Performance Target**: <100ms for simple queries, <500ms for complex multi-modal queries
- **Entity Embedding**: Weighted combination of name (0.3) + type (0.1) + observations (0.6)

---

## 1. Search Approach Recommendation

### **Selected: Option C - Hybrid Search**

**Rationale**:
1. **Best of Both Worlds**: Combines structured filtering (fast) with semantic understanding (intelligent)
2. **Proven Pattern**: Already implemented successfully in `HybridSearchEngine` for Knowledge Base
3. **Flexibility**: Handles both precise queries ("show me bug_fix entities from today") and fuzzy queries ("what did we work on yesterday?")
4. **Performance**: Redis indexes handle time-based and type filters efficiently, while vectors provide semantic ranking

**Architecture**:
```
User Query: "What bugs did we fix today?"
    ↓
┌─────────────────────────────────┐
│ Query Intent Extraction         │
│ - Entity type: bug_fix          │
│ - Time filter: created_at > today│
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│ Parallel Search Execution       │
├─────────────────────────────────┤
│ Redis Filter (Fast)             │
│ - Type = bug_fix                │
│ - Date >= 2025-10-03            │
│ → 50 candidates                 │
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│ Vector Semantic Ranking         │
│ - Generate query embedding      │
│ - Score each candidate          │
│ - Rank by similarity            │
│ → Top 10 results                │
└─────────────────────────────────┘
    ↓
    Return ranked entities
```

**Why Not Option A (Reuse KB)**:
- Mixing entities with documents would pollute knowledge base semantics
- Entity metadata (relationships, type) requires different indexing strategy
- KB optimized for document retrieval, not graph traversal

**Why Not Option B (Dedicated Index)**:
- Additional infrastructure overhead
- Duplicate embedding generation logic
- Unnecessary when hybrid approach is more flexible

---

## 2. Entity Embedding Strategy

### **Weighted Text Combination Approach**

**Embedding Text Generation**:
```python
def generate_entity_embedding_text(entity: Entity) -> str:
    """
    Create weighted text representation for embedding generation.

    Weights:
    - Name: 0.3 (semantic identity)
    - Type: 0.1 (categorical context)
    - Observations: 0.6 (core semantic content)
    """
    # Repeat components based on weights (simple approximation)
    name_text = f"{entity.name} {entity.name} {entity.name}"  # 3x for 0.3 weight
    type_text = f"{entity.type}"  # 1x for 0.1 weight

    # Observations get highest weight
    obs_text = "\n".join(entity.observations) * 6  # 6x for 0.6 weight

    combined_text = f"""
Entity: {name_text}
Type: {type_text}
Details:
{obs_text}
    """.strip()

    return combined_text
```

**Example**:
```python
Entity: {
  "type": "bug_fix",
  "name": "System Status Bug Fix",
  "observations": [
    "Fixed incorrect endpoint",
    "Updated API calls",
    "Deployed to Frontend VM"
  ]
}

# Generated embedding text (simplified):
"""
Entity: System Status Bug Fix System Status Bug Fix System Status Bug Fix
Type: bug_fix
Details:
Fixed incorrect endpoint
Updated API calls
Deployed to Frontend VM
Fixed incorrect endpoint
Updated API calls
Deployed to Frontend VM
[... repeated 6 times for 0.6 weight]
"""
```

**Rationale**:
- **Observations dominate (60%)**: Core semantic content describing what happened
- **Name provides context (30%)**: Entity identity for similarity matching
- **Type adds category (10%)**: Helps group similar entity types

**Alternative Considered - Multi-Vector**:
- Separate embeddings for name, observations, relations
- More complex, slower to query
- Marginal accuracy improvement not worth complexity

---

## 3. Query Processing Pipeline

### **5-Stage Pipeline**

```python
class MemoryGraphQueryProcessor:
    """Natural language query → Structured search"""

    async def process_query(self, query: str) -> SearchResults:
        """
        Stage 1: Intent Extraction
        Stage 2: Filter Generation
        Stage 3: Query Embedding
        Stage 4: Hybrid Search
        Stage 5: Result Ranking
        """

        # Stage 1: Extract search intent
        intent = await self._extract_intent(query)
        # {
        #   "entity_types": ["bug_fix", "feature"],
        #   "time_range": {"start": "2025-10-03", "end": None},
        #   "semantic_query": "bugs fixed",
        #   "keywords": ["fixed", "bugs"]
        # }

        # Stage 2: Generate Redis filters
        redis_filters = self._build_redis_filters(intent)
        # FT.SEARCH entities "@type:{bug_fix} @created_at:[timestamp_today +inf]"

        # Stage 3: Generate query embedding
        query_embedding = await self._generate_embedding(
            intent["semantic_query"]
        )

        # Stage 4: Execute hybrid search
        # 4a: Redis structured filter (fast candidate retrieval)
        candidates = await self._redis_search(redis_filters)

        # 4b: Vector similarity scoring
        scored_results = await self._vector_rank(
            candidates,
            query_embedding
        )

        # Stage 5: Final ranking with cross-modal boosting
        final_results = self._rank_results(scored_results, intent)

        return final_results
```

### **Intent Extraction Details**

**Pattern-Based Intent Extraction**:
```python
INTENT_PATTERNS = {
    "time_filter": {
        r"today": lambda: {"start": datetime.now().date()},
        r"yesterday": lambda: {"start": datetime.now().date() - timedelta(days=1)},
        r"this week": lambda: {"start": get_week_start()},
        r"last (\d+) days": lambda m: {"start": datetime.now().date() - timedelta(days=int(m.group(1)))}
    },
    "entity_types": {
        r"bug[s]?": ["bug_fix"],
        r"fix(es)?": ["bug_fix"],
        r"feature[s]?": ["feature_implementation"],
        r"architecture": ["architecture_decision"],
        r"decision[s]?": ["architecture_decision", "design_decision"]
    },
    "actions": {
        r"(worked on|completed|finished)": {"status": ["completed"]},
        r"(started|began|working on)": {"status": ["in_progress"]},
        r"(planned|todo)": {"status": ["pending"]}
    }
}

async def _extract_intent(self, query: str) -> Dict[str, Any]:
    """Extract structured intent from natural language query."""
    query_lower = query.lower()

    intent = {
        "entity_types": [],
        "time_range": None,
        "status_filter": None,
        "semantic_query": query,  # fallback to full query
        "keywords": []
    }

    # Extract time filters
    for pattern, handler in INTENT_PATTERNS["time_filter"].items():
        if re.search(pattern, query_lower):
            intent["time_range"] = handler()
            break

    # Extract entity types
    for pattern, types in INTENT_PATTERNS["entity_types"].items():
        if re.search(pattern, query_lower):
            intent["entity_types"].extend(types)

    # Extract status filters
    for pattern, status_filter in INTENT_PATTERNS["actions"].items():
        if re.search(pattern, query_lower):
            intent["status_filter"] = status_filter
            break

    # Extract keywords for hybrid scoring
    intent["keywords"] = self._extract_keywords(query)

    return intent
```

**Example Query Processing**:
```
Query: "What bugs did we fix today?"

Intent Extraction:
{
  "entity_types": ["bug_fix"],
  "time_range": {"start": "2025-10-03"},
  "status_filter": {"status": ["completed"]},
  "semantic_query": "bugs fix",
  "keywords": ["bugs", "fix", "today"]
}

Redis Filter:
FT.SEARCH entities
  "@type:{bug_fix}
   @status:{completed}
   @created_at:[1696291200 +inf]"

Vector Query:
embedding = ollama.embed("bugs fix")
→ [0.123, -0.456, 0.789, ... ] (768-dim)

Hybrid Scoring:
candidate.score = (
  0.6 * vector_similarity(query_embedding, entity_embedding) +
  0.4 * keyword_match(keywords, entity.observations)
)
```

---

## 4. Search API Design

### **Core Search Interface**

```python
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

@dataclass
class Entity:
    """Memory graph entity"""
    name: str
    type: str
    observations: List[str]
    created_at: datetime
    updated_at: datetime
    relations: List[Dict[str, str]]  # [{"to": "entity_name", "type": "relates_to"}]
    metadata: Dict[str, Any]

@dataclass
class SearchResult:
    """Search result with scoring details"""
    entity: Entity
    score: float  # Combined hybrid score [0.0-1.0]
    semantic_score: float  # Vector similarity [0.0-1.0]
    keyword_score: float  # Keyword match [0.0-1.0]
    matched_keywords: List[str]
    explanation: str  # Human-readable scoring explanation

class MemoryGraphSearch:
    """Semantic search interface for Memory Graph entities"""

    def __init__(self,
                 redis_client: aioredis.Redis,
                 knowledge_base: KnowledgeBaseV2):
        """
        Initialize search with existing infrastructure.

        Args:
            redis_client: Redis connection for entity storage
            knowledge_base: Knowledge Base V2 for embedding generation
        """
        self.redis = redis_client
        self.kb = knowledge_base
        self.cache = LRUCache(maxsize=1000)

    async def search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 10
    ) -> List[SearchResult]:
        """
        Semantic search with optional structured filters.

        Args:
            query: Natural language search query
                   Examples:
                   - "What bugs did we fix today?"
                   - "Show me architecture decisions from this week"
                   - "Find entities related to TLS implementation"

            filters: Optional structured filters
                {
                    "entity_types": ["bug_fix", "feature"],
                    "time_range": {
                        "start": datetime(2025, 10, 1),
                        "end": datetime(2025, 10, 3)
                    },
                    "status": ["completed"],
                    "tags": ["security", "backend"]
                }

            limit: Maximum number of results (default: 10)

        Returns:
            List of SearchResult objects ranked by relevance

        Performance:
            - Simple queries: <100ms
            - Complex filtered queries: <500ms
            - Cached queries: <10ms
        """
        # Check cache first
        cache_key = self._generate_cache_key(query, filters, limit)
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Process query through pipeline
        processor = MemoryGraphQueryProcessor(self.redis, self.kb)
        results = await processor.process_query(query, filters, limit)

        # Cache results
        self.cache[cache_key] = results

        return results

    async def get_similar_entities(
        self,
        entity_name: str,
        limit: int = 5
    ) -> List[SearchResult]:
        """
        Find entities similar to the given entity.

        Uses the entity's embedding to find semantically related entities.
        Useful for:
        - "Show me related bug fixes"
        - Finding similar architecture decisions
        - Discovering connected work items

        Args:
            entity_name: Name of reference entity
            limit: Number of similar entities to return

        Returns:
            List of similar entities ranked by similarity
        """
        # Get entity embedding
        entity = await self._get_entity(entity_name)
        if not entity:
            return []

        entity_embedding_text = self._generate_embedding_text(entity)
        entity_embedding = await self.kb.generate_embedding(
            entity_embedding_text
        )

        # Vector similarity search
        all_entities = await self._get_all_entities()
        scored_entities = []

        for candidate in all_entities:
            if candidate.name == entity_name:
                continue  # Skip self

            candidate_embedding = await self._get_entity_embedding(candidate)
            similarity = self._cosine_similarity(
                entity_embedding,
                candidate_embedding
            )

            scored_entities.append(
                SearchResult(
                    entity=candidate,
                    score=similarity,
                    semantic_score=similarity,
                    keyword_score=0.0,
                    matched_keywords=[],
                    explanation=f"Similar to {entity_name}"
                )
            )

        # Sort by similarity and return top results
        scored_entities.sort(key=lambda x: x.score, reverse=True)
        return scored_entities[:limit]

    async def get_conversation_context(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Get full conversation context including related entities.

        Retrieves:
        - All entities mentioned in conversation
        - Related entities (via graph traversal)
        - Recent entity updates relevant to conversation
        - Conversation metadata

        Args:
            session_id: Chat session identifier

        Returns:
            {
                "session_id": "uuid",
                "entities": [Entity, ...],
                "related_entities": [Entity, ...],
                "recent_updates": [Entity, ...],
                "conversation_summary": str,
                "entity_graph": {
                    "nodes": [...],
                    "edges": [...]
                }
            }
        """
        context = {
            "session_id": session_id,
            "entities": [],
            "related_entities": [],
            "recent_updates": [],
            "conversation_summary": "",
            "entity_graph": {"nodes": [], "edges": []}
        }

        # Get conversation messages
        messages = await self._get_conversation_messages(session_id)

        # Extract entity mentions from messages
        mentioned_entities = await self._extract_entity_mentions(messages)
        context["entities"] = mentioned_entities

        # Get related entities via graph traversal
        for entity in mentioned_entities:
            related = await self._get_related_entities(entity.name)
            context["related_entities"].extend(related)

        # Deduplicate
        context["related_entities"] = self._deduplicate_entities(
            context["related_entities"]
        )

        # Get recent updates (last 24 hours)
        recent_cutoff = datetime.now() - timedelta(days=1)
        context["recent_updates"] = [
            e for e in (context["entities"] + context["related_entities"])
            if e.updated_at >= recent_cutoff
        ]

        # Build entity graph
        context["entity_graph"] = await self._build_entity_graph(
            context["entities"] + context["related_entities"]
        )

        # Generate conversation summary
        context["conversation_summary"] = await self._summarize_conversation(
            messages, context["entities"]
        )

        return context

    async def advanced_search(
        self,
        semantic_query: str,
        structured_filters: Dict[str, Any],
        time_range: Optional[Dict[str, datetime]] = None,
        include_relations: bool = True,
        min_score: float = 0.5
    ) -> Dict[str, Any]:
        """
        Advanced search with detailed filtering and graph traversal.

        Args:
            semantic_query: Natural language query for semantic matching
            structured_filters: Precise filters (type, status, tags, etc.)
            time_range: Optional time window for results
            include_relations: Include related entities in results
            min_score: Minimum relevance score threshold

        Returns:
            {
                "results": [SearchResult, ...],
                "total_count": int,
                "query_analysis": {
                    "intent": {...},
                    "filters_applied": {...},
                    "performance_ms": float
                },
                "related_entities": [Entity, ...] if include_relations,
                "suggestions": [str, ...]  # Query suggestions
            }
        """
        start_time = datetime.now()

        # Combine semantic query with structured filters
        combined_filters = {**structured_filters}
        if time_range:
            combined_filters["time_range"] = time_range

        # Execute search
        results = await self.search(
            semantic_query,
            filters=combined_filters,
            limit=50  # Get more candidates for filtering
        )

        # Apply score threshold
        filtered_results = [r for r in results if r.score >= min_score]

        # Build response
        response = {
            "results": filtered_results[:20],  # Return top 20
            "total_count": len(filtered_results),
            "query_analysis": {
                "intent": await self._analyze_query_intent(semantic_query),
                "filters_applied": combined_filters,
                "performance_ms": (datetime.now() - start_time).total_seconds() * 1000
            },
            "suggestions": []
        }

        # Include related entities if requested
        if include_relations:
            related = []
            for result in filtered_results[:10]:  # Top 10 only
                related.extend(
                    await self._get_related_entities(result.entity.name)
                )
            response["related_entities"] = self._deduplicate_entities(related)

        # Generate search suggestions
        response["suggestions"] = await self._generate_search_suggestions(
            semantic_query,
            filtered_results
        )

        return response

    async def invalidate_cache(self, entity_name: Optional[str] = None):
        """
        Invalidate search cache.

        Args:
            entity_name: If provided, invalidate only queries related to this entity
                        If None, invalidate entire cache
        """
        if entity_name:
            # Selective invalidation
            keys_to_remove = [
                k for k in self.cache.keys()
                if entity_name in str(k)
            ]
            for key in keys_to_remove:
                del self.cache[key]
        else:
            # Full cache clear
            self.cache.clear()
```

---

## 5. Integration with Chat Workflow

### **Natural Language Query Interface**

**User Interaction Pattern**:
```python
# In chat workflow
async def handle_memory_query(message: str, session_id: str) -> str:
    """
    Detect and handle memory-related queries in chat.

    Triggers:
    - "What did we work on..."
    - "Show me..."
    - "Find entities..."
    - "What's the status of..."
    """
    # Detect memory query
    if is_memory_query(message):
        memory_search = get_memory_search()

        # Execute search
        results = await memory_search.search(message, limit=10)

        # Format response
        if not results:
            return "I couldn't find any relevant entities for that query."

        response = f"Found {len(results)} relevant entities:\n\n"

        for i, result in enumerate(results[:5], 1):
            entity = result.entity
            response += f"{i}. **{entity.name}** ({entity.type})\n"
            response += f"   - {entity.observations[0]}\n"
            if result.matched_keywords:
                response += f"   - Matched: {', '.join(result.matched_keywords)}\n"
            response += f"   - Relevance: {result.score:.2f}\n\n"

        # Get conversation context
        context = await memory_search.get_conversation_context(session_id)
        if context["recent_updates"]:
            response += f"\n**Recent related updates:**\n"
            for update in context["recent_updates"][:3]:
                response += f"- {update.name}: {update.observations[-1]}\n"

        return response

    # Not a memory query, handle normally
    return await normal_chat_handler(message)
```

**Example Conversations**:

```
User: "What bugs did we fix today?"
AutoBot: Found 3 relevant entities:

1. System Status Bug Fix (bug_fix)
   - Fixed incorrect endpoint /api/system/status
   - Matched: bugs, fix
   - Relevance: 0.92

2. Conversation Handling Bug Fix (bug_fix)
   - Resolved session ID validation error
   - Matched: fix
   - Relevance: 0.87

3. Documentation Access Bug Fix (bug_fix)
   - Fixed CORS headers for API docs
   - Matched: fix
   - Relevance: 0.83

Recent related updates:
- System Status Bug Fix: Deployed to Frontend VM
- API Documentation: Updated with new endpoints
```

```
User: "Tell me more about the system status fix"
AutoBot: [Executes get_similar_entities("System Status Bug Fix")]

The System Status Bug Fix addressed an incorrect API endpoint. Here's what I found:

**Details:**
- Fixed endpoint from /api/status to /api/system/status
- Updated API calls in frontend components
- Deployed to Frontend VM (172.16.168.21)

**Related entities:**
- API Documentation Update (documentation)
- Frontend Component Refactor (feature_implementation)
- Health Check Endpoint Enhancement (feature_implementation)

**Context:**
This was part of a larger effort to standardize API endpoints across the system.
Would you like me to show you the related architecture decisions?
```

### **Context-Aware Search**

```python
async def context_aware_search(
    query: str,
    session_id: str,
    conversation_history: List[Dict]
) -> List[SearchResult]:
    """
    Use conversation context to enhance search relevance.
    """
    # Extract entities mentioned in recent conversation
    recent_entities = extract_mentioned_entities(
        conversation_history[-10:]  # Last 10 messages
    )

    # Build context-enhanced query
    if recent_entities:
        # Boost results related to conversation topics
        entity_names = [e.name for e in recent_entities]
        entity_types = list(set(e.type for e in recent_entities))

        filters = {
            "boost_entities": entity_names,  # Boost these in ranking
            "suggested_types": entity_types   # Suggest these types
        }
    else:
        filters = {}

    # Execute search with context
    results = await memory_search.search(query, filters=filters)

    return results
```

---

## 6. Performance Optimization Plan

### **6.1 Caching Strategy**

```python
from functools import lru_cache
import hashlib

class SearchCache:
    """Multi-level cache for search results"""

    def __init__(self):
        # L1: LRU cache for frequent queries (in-memory)
        self.query_cache = LRUCache(maxsize=1000)

        # L2: Redis cache for embedding results (distributed)
        self.embedding_cache = RedisCache(ttl=3600)  # 1 hour

        # L3: Batch embedding cache (for efficiency)
        self.batch_cache = {}

    def get_query_results(self, query: str, filters: Dict) -> Optional[List[SearchResult]]:
        """L1 cache lookup"""
        cache_key = self._hash_query(query, filters)
        return self.query_cache.get(cache_key)

    def cache_query_results(self, query: str, filters: Dict, results: List[SearchResult]):
        """L1 cache storage"""
        cache_key = self._hash_query(query, filters)
        self.query_cache[cache_key] = results

    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """L2 distributed cache lookup"""
        cache_key = f"embed:{hashlib.sha256(text.encode()).hexdigest()}"
        cached = await self.embedding_cache.get(cache_key)
        if cached:
            return json.loads(cached)
        return None

    async def cache_embedding(self, text: str, embedding: List[float]):
        """L2 distributed cache storage"""
        cache_key = f"embed:{hashlib.sha256(text.encode()).hexdigest()}"
        await self.embedding_cache.set(
            cache_key,
            json.dumps(embedding),
            ex=3600  # 1 hour TTL
        )

    def _hash_query(self, query: str, filters: Dict) -> str:
        """Generate cache key from query + filters"""
        content = f"{query}:{json.dumps(filters, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()
```

**Cache Invalidation Rules**:
```python
async def on_entity_update(entity_name: str):
    """Invalidate caches when entity is modified"""
    # Invalidate L1 query cache entries mentioning this entity
    await search_cache.invalidate_query_cache(entity_name)

    # Invalidate L2 embedding cache for this entity
    await search_cache.invalidate_embedding(entity_name)

    # Trigger async re-indexing
    await background_tasks.add_task(reindex_entity, entity_name)
```

### **6.2 Index Optimization**

```python
class EntityIndexManager:
    """Manage entity indexing for optimal search performance"""

    async def create_indexes(self):
        """Create optimized Redis indexes for entity search"""

        # Full-text search index on observations
        await self.redis.execute_command(
            "FT.CREATE", "idx:entities",
            "ON", "HASH",
            "PREFIX", "1", "entity:",
            "SCHEMA",
            "name", "TEXT", "WEIGHT", "3.0",  # Higher weight for names
            "type", "TAG", "SORTABLE",
            "observations", "TEXT", "WEIGHT", "6.0",  # Highest weight
            "created_at", "NUMERIC", "SORTABLE",
            "updated_at", "NUMERIC", "SORTABLE",
            "status", "TAG",
            "tags", "TAG", "SEPARATOR", ",",
            "embedding", "VECTOR", "FLAT", "6",
                "TYPE", "FLOAT32",
                "DIM", "768",
                "DISTANCE_METRIC", "COSINE"
        )

    async def batch_index_entities(self, entities: List[Entity]):
        """Batch index multiple entities efficiently"""
        pipe = self.redis.pipeline()

        for entity in entities:
            # Generate embedding (batched)
            embedding_text = self._generate_embedding_text(entity)

            # Store entity with embedding
            entity_key = f"entity:{entity.name}"
            pipe.hset(entity_key, mapping={
                "name": entity.name,
                "type": entity.type,
                "observations": "\n".join(entity.observations),
                "created_at": entity.created_at.timestamp(),
                "updated_at": entity.updated_at.timestamp(),
                "tags": ",".join(entity.metadata.get("tags", [])),
            })

        # Execute batch
        await pipe.execute()

        # Generate embeddings in batch (more efficient)
        embedding_texts = [
            self._generate_embedding_text(e) for e in entities
        ]
        embeddings = await self.kb.batch_generate_embeddings(embedding_texts)

        # Update entities with embeddings
        pipe = self.redis.pipeline()
        for entity, embedding in zip(entities, embeddings):
            entity_key = f"entity:{entity.name}"
            # Convert embedding to bytes for Redis
            embedding_bytes = np.array(embedding, dtype=np.float32).tobytes()
            pipe.hset(entity_key, "embedding", embedding_bytes)

        await pipe.execute()
```

### **6.3 Query Optimization**

```python
class QueryOptimizer:
    """Optimize search queries for performance"""

    async def optimize_query(self, query: str, filters: Dict) -> Dict:
        """
        Optimize query execution plan based on filters and query complexity.
        """
        plan = {
            "strategy": "hybrid",
            "redis_first": True,
            "estimated_ms": 0
        }

        # If filters are very selective, use Redis-only search
        if self._is_highly_selective(filters):
            plan["strategy"] = "redis_only"
            plan["estimated_ms"] = 50
            return plan

        # If query is purely semantic with no filters, use vector-only
        if not filters and len(query.split()) > 5:
            plan["strategy"] = "vector_only"
            plan["estimated_ms"] = 200
            return plan

        # Default hybrid approach
        candidate_count = await self._estimate_candidate_count(filters)

        if candidate_count < 100:
            # Few candidates, vector score all of them
            plan["estimated_ms"] = 100
        elif candidate_count < 1000:
            # Moderate candidates, use hybrid
            plan["estimated_ms"] = 300
        else:
            # Many candidates, filter heavily first
            plan["redis_first"] = True
            plan["estimated_ms"] = 500

        return plan

    def _is_highly_selective(self, filters: Dict) -> bool:
        """Determine if filters are selective enough for Redis-only search"""
        selectivity_score = 0

        if "entity_types" in filters and len(filters["entity_types"]) == 1:
            selectivity_score += 2

        if "time_range" in filters:
            time_window = filters["time_range"].get("end", datetime.now()) - \
                         filters["time_range"]["start"]
            if time_window < timedelta(days=7):
                selectivity_score += 3

        if "status" in filters:
            selectivity_score += 1

        # Highly selective if score >= 4
        return selectivity_score >= 4
```

### **6.4 Performance Benchmarks**

```python
import time
from dataclasses import dataclass

@dataclass
class PerformanceBenchmark:
    """Search performance metrics"""
    query_type: str
    avg_latency_ms: float
    p95_latency_ms: float
    cache_hit_rate: float
    candidate_count: int

async def run_performance_tests():
    """Benchmark search performance"""

    benchmarks = []

    # Test 1: Simple type filter
    start = time.time()
    results = await memory_search.search(
        "bug fixes",
        filters={"entity_types": ["bug_fix"]}
    )
    latency = (time.time() - start) * 1000

    benchmarks.append(PerformanceBenchmark(
        query_type="simple_type_filter",
        avg_latency_ms=latency,
        p95_latency_ms=latency * 1.2,
        cache_hit_rate=0.0,  # First run
        candidate_count=len(results)
    ))

    # Test 2: Complex hybrid query
    start = time.time()
    results = await memory_search.search(
        "What architecture decisions did we make about security?"
    )
    latency = (time.time() - start) * 1000

    benchmarks.append(PerformanceBenchmark(
        query_type="complex_hybrid",
        avg_latency_ms=latency,
        p95_latency_ms=latency * 1.3,
        cache_hit_rate=0.0,
        candidate_count=len(results)
    ))

    # Test 3: Cached query (should be <10ms)
    start = time.time()
    results = await memory_search.search(
        "What architecture decisions did we make about security?"
    )
    cached_latency = (time.time() - start) * 1000

    benchmarks.append(PerformanceBenchmark(
        query_type="cached_query",
        avg_latency_ms=cached_latency,
        p95_latency_ms=cached_latency * 1.1,
        cache_hit_rate=1.0,
        candidate_count=len(results)
    ))

    return benchmarks

# Expected Performance Targets:
# - Simple filtered queries: <100ms
# - Complex hybrid queries: <500ms
# - Cached queries: <10ms
# - Batch operations (10 entities): <200ms
# - Similar entity search: <150ms
```

---

## 7. Example Queries and Expected Results

### **Query 1: Time-Based Bug Search**

**Input**:
```python
await memory_search.search("What bugs did we fix today?")
```

**Expected Processing**:
```
Intent Extraction:
{
  "entity_types": ["bug_fix"],
  "time_range": {"start": datetime(2025, 10, 3)},
  "semantic_query": "bugs fix",
  "keywords": ["bugs", "fix", "today"]
}

Redis Filter:
FT.SEARCH idx:entities
  "@type:{bug_fix} @created_at:[1696291200 +inf]"
→ 5 candidates

Vector Ranking:
Query embedding: embed("bugs fix") → [0.12, -0.45, ...]
Rank by cosine similarity
```

**Expected Results**:
```python
[
    SearchResult(
        entity=Entity(
            name="System Status Bug Fix",
            type="bug_fix",
            observations=[
                "Fixed incorrect endpoint /api/system/status",
                "Updated API calls in frontend",
                "Deployed to Frontend VM"
            ],
            created_at=datetime(2025, 10, 3, 9, 15)
        ),
        score=0.92,
        semantic_score=0.89,
        keyword_score=0.95,
        matched_keywords=["bugs", "fix"],
        explanation="High relevance: Recent bug fix matching 'bugs fix'"
    ),
    SearchResult(
        entity=Entity(
            name="Conversation Handling Bug Fix",
            type="bug_fix",
            observations=[
                "Resolved session ID validation error",
                "Added UUID format validation"
            ],
            created_at=datetime(2025, 10, 3, 11, 30)
        ),
        score=0.87,
        semantic_score=0.85,
        keyword_score=0.89,
        matched_keywords=["fix"],
        explanation="High relevance: Recent bug fix matching 'fix'"
    ),
    # ... more results
]
```

### **Query 2: Architecture Decision Search**

**Input**:
```python
await memory_search.search(
    "Show me architecture decisions about TLS",
    filters={"entity_types": ["architecture_decision"]}
)
```

**Expected Results**:
```python
[
    SearchResult(
        entity=Entity(
            name="TLS Certificate Management Architecture",
            type="architecture_decision",
            observations=[
                "Decided to use Let's Encrypt for auto-renewal",
                "Implemented certificate rotation strategy",
                "Configured nginx reverse proxy for TLS termination"
            ]
        ),
        score=0.94,
        semantic_score=0.96,
        keyword_score=0.92,
        matched_keywords=["TLS", "architecture"],
        explanation="Exact match for TLS architecture decision"
    ),
    # ... related decisions
]
```

### **Query 3: Contextual Search**

**Input**:
```python
context = await memory_search.get_conversation_context(
    session_id="abc-123-def"
)
```

**Expected Response**:
```python
{
    "session_id": "abc-123-def",
    "entities": [
        Entity(name="System Status Bug Fix", ...),
        Entity(name="API Documentation Update", ...)
    ],
    "related_entities": [
        Entity(name="Frontend Component Refactor", ...),
        Entity(name="Health Check Endpoint Enhancement", ...)
    ],
    "recent_updates": [
        Entity(
            name="System Status Bug Fix",
            observations=["Deployed to Frontend VM"],
            updated_at=datetime(2025, 10, 3, 14, 20)
        )
    ],
    "conversation_summary": "Discussion about system status bug fix and related API improvements",
    "entity_graph": {
        "nodes": [
            {"id": "System Status Bug Fix", "type": "bug_fix"},
            {"id": "API Documentation Update", "type": "documentation"}
        ],
        "edges": [
            {"from": "System Status Bug Fix", "to": "API Documentation Update", "type": "relates_to"}
        ]
    }
}
```

---

## 8. Implementation Roadmap

### **Phase 1: Core Infrastructure (Week 1)**
- [ ] Implement `MemoryGraphQueryProcessor` with intent extraction
- [ ] Implement `MemoryGraphSearch` base class
- [ ] Set up Redis indexes for entity search
- [ ] Integrate with existing Knowledge Base V2 for embeddings

### **Phase 2: Search Methods (Week 2)**
- [ ] Implement `search()` method with hybrid scoring
- [ ] Implement `get_similar_entities()` method
- [ ] Add caching layer (L1 + L2)
- [ ] Add query optimization

### **Phase 3: Context & Integration (Week 3)**
- [ ] Implement `get_conversation_context()` method
- [ ] Integrate with chat workflow
- [ ] Add natural language query detection
- [ ] Implement context-aware search

### **Phase 4: Performance & Testing (Week 4)**
- [ ] Performance benchmarking and optimization
- [ ] Batch indexing implementation
- [ ] Cache invalidation strategy
- [ ] Comprehensive test suite

### **Phase 5: Advanced Features (Week 5)**
- [ ] Implement `advanced_search()` method
- [ ] Add query suggestions
- [ ] Add search analytics
- [ ] Documentation and examples

---

## 9. Success Metrics

### **Performance Metrics**
- ✅ Simple queries: <100ms (Target: 50-80ms avg)
- ✅ Complex hybrid queries: <500ms (Target: 200-400ms avg)
- ✅ Cached queries: <10ms (Target: 2-5ms avg)
- ✅ Cache hit rate: >60% (Target: 70-80%)

### **Quality Metrics**
- ✅ Relevance score (MRR): >0.8
- ✅ Query understanding accuracy: >90%
- ✅ False positive rate: <5%
- ✅ User satisfaction (feedback): >4.5/5

### **Scale Metrics**
- ✅ Handle 10,000+ entities efficiently
- ✅ Support 100+ concurrent search requests
- ✅ Embedding generation: <50ms per entity
- ✅ Batch indexing: >50 entities/second

---

## 10. Technical Dependencies

### **Required Components**
- Redis 7+ with RediSearch module
- Ollama (127.0.0.1:11434) with nomic-embed-text model
- Knowledge Base V2 (existing)
- aioredis for async Redis operations

### **Python Dependencies**
```python
# requirements.txt additions
numpy>=1.24.0  # Vector operations
scikit-learn>=1.3.0  # Cosine similarity
cachetools>=5.3.0  # LRU cache
```

### **Redis Modules**
```bash
# Verify RediSearch is loaded
redis-cli MODULE LIST
# Should show: redisearch
```

---

## Appendices

### **A. Embedding Model Comparison**

| Model | Dimensions | Performance | Use Case |
|-------|-----------|-------------|----------|
| nomic-embed-text | 768 | Best quality | **Selected** - Existing infrastructure |
| all-MiniLM-L6-v2 | 384 | Faster | Alternative for speed |
| text-embedding-ada-002 | 1536 | Highest quality | Future consideration (requires API) |

### **B. Alternative Approaches Considered**

**Graph Database (Neo4j)**:
- Pros: Native graph traversal, powerful query language
- Cons: Additional infrastructure, learning curve, overkill for current scale
- Decision: Not selected - Redis graph capabilities sufficient

**Elasticsearch**:
- Pros: Mature full-text search, good hybrid capabilities
- Cons: Heavy infrastructure, overlaps with Redis, additional complexity
- Decision: Not selected - Redis + vectors sufficient

**Dedicated Vector DB (Pinecone/Weaviate)**:
- Pros: Optimized for vectors, cloud-managed options
- Cons: Additional cost, data duplication, network latency
- Decision: Not selected - Redis vector capabilities meet needs

### **C. Query Pattern Examples**

```python
# Time-based queries
"What did we work on yesterday?"
"Show me last week's architecture decisions"
"Find bugs fixed in the last 3 days"

# Type-based queries
"Show me all feature implementations"
"List security-related entities"
"Find documentation updates"

# Status-based queries
"What tasks are in progress?"
"Show me completed features"
"Find pending decisions"

# Semantic queries
"Find entities related to authentication"
"Show me similar bug fixes"
"What's the status of TLS implementation?"

# Combined queries
"What security bugs did we fix this week?"
"Show me in-progress features related to AI"
"Find completed architecture decisions from last month"
```

---

**End of Design Document**

**Next Steps**: Proceed to implementation following the roadmap in Section 8.

**Design Approval**: Ready for technical review and implementation planning.
