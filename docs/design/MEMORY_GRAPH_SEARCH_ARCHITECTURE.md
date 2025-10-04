# Memory Graph Search - System Architecture

**Visual representation of the semantic search architecture for AutoBot Memory Graph**

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        User Interface Layer                          │
│                                                                       │
│  Chat Interface          API Endpoints           CLI Tools           │
│  ┌──────────┐           ┌──────────┐            ┌──────────┐        │
│  │ "What    │           │ /search  │            │ memory-  │        │
│  │ bugs...?"│           │ /similar │            │ search   │        │
│  └─────┬────┘           └─────┬────┘            └─────┬────┘        │
└────────┼──────────────────────┼───────────────────────┼─────────────┘
         │                      │                       │
         └──────────────────────┼───────────────────────┘
                                ↓
         ┌──────────────────────────────────────────────────────┐
         │         MemoryGraphSearch (Main Interface)            │
         │                                                        │
         │  - search(query, filters)                             │
         │  - get_similar_entities(entity_name)                  │
         │  - get_conversation_context(session_id)               │
         │  - advanced_search(semantic, structured, time)        │
         └────────────┬─────────────────────────────────────────┘
                      ↓
         ┌──────────────────────────────────────────────────────┐
         │      MemoryGraphQueryProcessor (Query Pipeline)       │
         │                                                        │
         │  Stage 1: Intent Extraction                           │
         │  ├─ Pattern matching (time, type, status)             │
         │  └─ Keyword extraction                                │
         │                                                        │
         │  Stage 2: Filter Generation                           │
         │  ├─ Build Redis queries                               │
         │  └─ Apply structured filters                          │
         │                                                        │
         │  Stage 3: Query Embedding                             │
         │  ├─ Generate semantic embedding                       │
         │  └─ Check embedding cache (L2)                        │
         │                                                        │
         │  Stage 4: Hybrid Search Execution                     │
         │  ├─ Redis candidate retrieval                         │
         │  └─ Vector similarity ranking                         │
         │                                                        │
         │  Stage 5: Result Ranking & Scoring                    │
         │  ├─ Combine semantic + keyword scores                 │
         │  └─ Apply cross-modal boosting                        │
         └────────────┬─────────────────────────────────────────┘
                      ↓
         ┌──────────────────────────────────────────────────────┐
         │           Storage & Indexing Layer                    │
         │                                                        │
         │  ┌────────────────┐         ┌────────────────┐       │
         │  │ Redis Storage  │         │ Knowledge Base │       │
         │  │                │         │ V2 (Embeddings)│       │
         │  │ • Entities     │◄────────┤                │       │
         │  │ • Metadata     │         │ • Ollama       │       │
         │  │ • Relations    │         │ • nomic-embed  │       │
         │  │ • Indexes      │         │ • 768-dim      │       │
         │  └────────────────┘         └────────────────┘       │
         └──────────────────────────────────────────────────────┘
```

---

## Hybrid Search Flow Diagram

```
User Query: "What bugs did we fix today?"
│
├─► [L1 Cache Check] ─────────────────────► Cache Hit? ──► Return Cached Results
│        ↓ Miss                                              (< 10ms)
│
├─► [Intent Extraction]
│        │
│        ├─ Pattern Matching: "bugs" → entity_type = bug_fix
│        ├─ Time Extraction: "today" → date >= 2025-10-03
│        └─ Keywords: ["bugs", "fix", "today"]
│        │
│        ↓
│   {
│     "entity_types": ["bug_fix"],
│     "time_range": {"start": "2025-10-03"},
│     "keywords": ["bugs", "fix", "today"],
│     "semantic_query": "bugs fix"
│   }
│        │
│        ↓
├─► [Parallel Execution]
│        │
│        ├─────────────────┬─────────────────┐
│        ↓                 ↓                 ↓
│   [Redis Filter]   [Query Embed]    [Candidate Prep]
│        │                 │                 │
│   FT.SEARCH         [L2 Cache?]      Get entity
│   @type:{bug_fix}        │            embeddings
│   @date:[today +∞]       ↓
│        │           embed("bugs fix")
│        │           → [0.12, -0.45, ...]
│        │                 │
│        └────────┬────────┘
│                 ↓
│        [Vector Similarity Ranking]
│                 │
│        For each candidate:
│          similarity = cosine(query_embed, entity_embed)
│                 │
│                 ↓
│        [Hybrid Scoring]
│                 │
│        score = 0.6 * semantic_score +
│                0.4 * keyword_score
│                 │
│                 ↓
│        [Sort by score DESC]
│                 │
│                 ↓
│        [Top K Results]
│                 │
│                 ↓
│        [L1 Cache Store]
│                 │
│                 ↓
│        Return Results
```

---

## Entity Embedding Strategy

```
┌─────────────────────────────────────────────────────────────┐
│                    Entity Structure                          │
├─────────────────────────────────────────────────────────────┤
│ Entity: System Status Bug Fix                               │
│ Type: bug_fix                                                │
│ Observations:                                                │
│   - Fixed incorrect endpoint /api/system/status             │
│   - Updated API calls in frontend components                │
│   - Deployed to Frontend VM (172.16.168.21)                 │
│ Created: 2025-10-03 09:15                                    │
│ Relations: [relates_to: API Documentation Update]           │
└─────────────────────────────────────────────────────────────┘
                         ↓
         ┌───────────────────────────────────┐
         │   Weighted Text Generation        │
         ├───────────────────────────────────┤
         │                                   │
         │ Name (30% weight):                │
         │   "System Status Bug Fix" × 3     │
         │                                   │
         │ Type (10% weight):                │
         │   "bug_fix" × 1                   │
         │                                   │
         │ Observations (60% weight):        │
         │   [All observations] × 6          │
         │                                   │
         └───────────────────────────────────┘
                         ↓
         ┌───────────────────────────────────┐
         │     Combined Embedding Text       │
         ├───────────────────────────────────┤
         │                                   │
         │ Entity: System Status Bug Fix     │
         │ System Status Bug Fix             │
         │ System Status Bug Fix             │
         │ Type: bug_fix                     │
         │ Details:                          │
         │ Fixed incorrect endpoint...       │
         │ Updated API calls...              │
         │ Deployed to Frontend VM...        │
         │ [... repeated 6 times]            │
         │                                   │
         └───────────────────────────────────┘
                         ↓
         ┌───────────────────────────────────┐
         │    Ollama Embedding Generation    │
         ├───────────────────────────────────┤
         │                                   │
         │ Model: nomic-embed-text           │
         │ Endpoint: localhost:11434         │
         │ Dimensions: 768                   │
         │                                   │
         └───────────────────────────────────┘
                         ↓
         ┌───────────────────────────────────┐
         │         Vector Output             │
         ├───────────────────────────────────┤
         │                                   │
         │ [0.123, -0.456, 0.789, ..., 0.321]│
         │        (768 dimensions)           │
         │                                   │
         └───────────────────────────────────┘
                         ↓
         ┌───────────────────────────────────┐
         │       Store in Redis              │
         ├───────────────────────────────────┤
         │                                   │
         │ Key: entity:System Status Bug Fix │
         │ Fields:                           │
         │   - name                          │
         │   - type                          │
         │   - observations                  │
         │   - embedding (binary)            │
         │   - created_at                    │
         │                                   │
         └───────────────────────────────────┘
```

---

## Multi-Level Caching Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                         Cache Hierarchy                             │
└────────────────────────────────────────────────────────────────────┘

Query: "What bugs did we fix today?"
    ↓
┌─────────────────────────────────────────┐
│   L1: In-Memory LRU Cache               │  < 10ms
│   ┌───────────────────────────────┐     │
│   │ Max: 1000 queries             │     │
│   │ TTL: No expiry (LRU eviction) │     │
│   │ Storage: Process memory       │     │
│   │                               │     │
│   │ Cache Key: SHA256(query +     │     │
│   │             filters)          │     │
│   │                               │     │
│   │ Value: List[SearchResult]     │     │
│   └───────────────────────────────┘     │
└──────────────┬──────────────────────────┘
               ↓ Miss
┌─────────────────────────────────────────┐
│   L2: Redis Distributed Cache           │  < 50ms
│   ┌───────────────────────────────┐     │
│   │ TTL: 1 hour                   │     │
│   │ Storage: Redis (shared)       │     │
│   │                               │     │
│   │ Embedding Cache:              │     │
│   │   Key: embed:<text_hash>      │     │
│   │   Value: [0.12, -0.45, ...]   │     │
│   │                               │     │
│   │ Query Result Cache:           │     │
│   │   Key: search:<query_hash>    │     │
│   │   Value: Serialized results   │     │
│   └───────────────────────────────┘     │
└──────────────┬──────────────────────────┘
               ↓ Miss
┌─────────────────────────────────────────┐
│   L3: Batch Processing Cache            │  Variable
│   ┌───────────────────────────────┐     │
│   │ Purpose: Batch embedding gen  │     │
│   │ Optimization: Group requests  │     │
│   │                               │     │
│   │ Batches:                      │     │
│   │   - 10 entities → 1 API call  │     │
│   │   - ~50ms per batch           │     │
│   │   - 5ms per entity (amortized)│     │
│   └───────────────────────────────┘     │
└──────────────┬──────────────────────────┘
               ↓ Miss
         Full Search Execution
         (100-500ms)

Cache Invalidation Strategy:
┌────────────────────────────────────────┐
│ On Entity Update:                      │
│  ├─ Clear L1 entries mentioning entity │
│  ├─ Delete L2 embedding for entity     │
│  └─ Mark entity for re-indexing        │
│                                        │
│ Periodic Cleanup:                      │
│  ├─ L1: LRU eviction (automatic)       │
│  ├─ L2: TTL expiry (automatic)         │
│  └─ L3: Clear on batch completion      │
└────────────────────────────────────────┘
```

---

## Search Performance Comparison

```
┌──────────────────────────────────────────────────────────────┐
│              Search Strategy Performance                      │
└──────────────────────────────────────────────────────────────┘

Strategy 1: Redis-Only (Keyword Search)
┌─────────────────┐
│ User Query      │
└────────┬────────┘
         ↓
┌─────────────────┐
│ FT.SEARCH       │  ← Fast (10-30ms)
│ Keyword match   │
└────────┬────────┘
         ↓
    Results (Less accurate for semantic queries)

────────────────────────────────────────────────────────────

Strategy 2: Vector-Only (Pure Semantic)
┌─────────────────┐
│ User Query      │
└────────┬────────┘
         ↓
┌─────────────────┐
│ Generate embed  │  ← Slow (50ms)
└────────┬────────┘
         ↓
┌─────────────────┐
│ Compute cosine  │  ← Expensive (200-400ms for 10K entities)
│ for ALL entities│
└────────┬────────┘
         ↓
    Results (Accurate but slow)

────────────────────────────────────────────────────────────

Strategy 3: Hybrid (SELECTED) ✅
┌─────────────────┐
│ User Query      │
└────────┬────────┘
         ↓
┌─────────────────────────────┐
│ Parallel Execution:         │
│  ├─ Redis filter (10ms)     │  ← Fast candidate retrieval
│  └─ Generate embed (50ms)   │  ← Parallel with filtering
└────────┬────────────────────┘
         ↓
┌─────────────────┐
│ Vector rank     │  ← Only 50 candidates (fast: 20ms)
│ 50 candidates   │
└────────┬────────┘
         ↓
┌─────────────────┐
│ Hybrid scoring  │  ← Combine scores (5ms)
│ semantic + kw   │
└────────┬────────┘
         ↓
    Results (Accurate AND fast: ~100ms total)

Performance Breakdown:
├─ Intent extraction: 5ms
├─ Redis filtering: 10ms
├─ Embedding generation: 50ms (parallel)
├─ Vector ranking: 20ms
└─ Scoring & sorting: 15ms
   ───────────────────
   Total: ~100ms
```

---

## Integration Points

```
┌────────────────────────────────────────────────────────────────┐
│                   System Integration Map                        │
└────────────────────────────────────────────────────────────────┘

                    ┌──────────────────┐
                    │  Chat Interface  │
                    │  (Frontend UI)   │
                    └────────┬─────────┘
                             │
                             ↓
                    ┌──────────────────┐
                    │ Chat Workflow    │
                    │ Manager          │
                    └────────┬─────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ↓                  ↓                  ↓
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ Memory Graph    │ │ Knowledge Base  │ │ Chat History    │
│ Search          │ │ V2              │ │ Manager         │
│                 │ │                 │ │                 │
│ • Entity search │ │ • Embeddings    │ │ • Conversation  │
│ • Similarity    │ │ • Vector store  │ │   context       │
│ • Context       │ │ • Ollama client │ │ • Session data  │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             ↓
                    ┌──────────────────┐
                    │  Redis Database  │
                    │                  │
                    │  DB 0: Entities  │
                    │  DB 1: KB Docs   │
                    │  DB 2: Chat      │
                    │                  │
                    │  Indexes:        │
                    │  • FT.SEARCH     │
                    │  • Vector index  │
                    └──────────────────┘

Data Flow:
1. User asks question in chat
2. Chat Workflow detects memory query
3. Calls Memory Graph Search
4. MG Search uses KB V2 for embeddings
5. MG Search queries Redis entities
6. Returns results to Chat Workflow
7. Chat enriches with conversation context
8. Response formatted and sent to user
```

---

## Query Processing State Machine

```
┌─────────────────────────────────────────────────────────────────┐
│             Query Processing State Diagram                       │
└─────────────────────────────────────────────────────────────────┘

        START
          │
          ↓
    ┌──────────┐
    │ VALIDATE │─── Invalid ──► ERROR: "Invalid query"
    │  QUERY   │
    └─────┬────┘
          │ Valid
          ↓
    ┌──────────┐
    │  CACHE   │─── Hit ──────► RETURN cached results (< 10ms)
    │  LOOKUP  │
    └─────┬────┘
          │ Miss
          ↓
    ┌──────────┐
    │ EXTRACT  │
    │  INTENT  │
    └─────┬────┘
          │
          ↓
    ┌──────────┐
    │ GENERATE │
    │ FILTERS  │
    └─────┬────┘
          │
          ├─────────────────┬─────────────────┐
          ↓                 ↓                 ↓
    ┌──────────┐      ┌──────────┐    ┌──────────┐
    │  REDIS   │      │  EMBED   │    │ PREPARE  │
    │  FILTER  │      │  QUERY   │    │ ENTITIES │
    └─────┬────┘      └─────┬────┘    └─────┬────┘
          │                 │               │
          └────────┬────────┴───────────────┘
                   ↓
             ┌──────────┐
             │  VECTOR  │
             │   RANK   │
             └─────┬────┘
                   │
                   ↓
             ┌──────────┐
             │  HYBRID  │
             │  SCORE   │
             └─────┬────┘
                   │
                   ↓
             ┌──────────┐
             │   SORT   │
             │  & LIMIT │
             └─────┬────┘
                   │
                   ↓
             ┌──────────┐
             │  CACHE   │
             │  STORE   │
             └─────┬────┘
                   │
                   ↓
             ┌──────────┐
             │  RETURN  │
             │ RESULTS  │
             └──────────┘
                   │
                   ↓
                 END

Error Handling:
├─ Intent extraction fails → Fallback to full semantic search
├─ Redis timeout → Use cached or partial results
├─ Embedding fails → Use keyword-only search
└─ Empty results → Return suggestions
```

---

## Component Dependencies

```
┌──────────────────────────────────────────────────────────────┐
│                    Dependency Graph                           │
└──────────────────────────────────────────────────────────────┘

MemoryGraphSearch
    │
    ├─► MemoryGraphQueryProcessor
    │       │
    │       ├─► IntentExtractor
    │       ├─► FilterBuilder
    │       └─► QueryOptimizer
    │
    ├─► SearchCache
    │       │
    │       ├─► LRUCache (cachetools)
    │       └─► RedisCache (aioredis)
    │
    ├─► KnowledgeBaseV2
    │       │
    │       ├─► OllamaEmbedding (llama-index)
    │       │       └─► Ollama Server (localhost:11434)
    │       │
    │       └─► RedisVectorStore (llama-index)
    │               └─► Redis Server (172.16.168.23:6379)
    │
    ├─► EntityIndexManager
    │       │
    │       ├─► Redis Client (aioredis)
    │       └─► Batch Processor
    │
    └─► ResultRanker
            │
            ├─► CosineSimilarity (sklearn)
            └─► KeywordMatcher

External Dependencies:
├─ Ollama: nomic-embed-text model (768-dim)
├─ Redis: RediSearch module + Vector support
├─ Python: aioredis, numpy, scikit-learn, cachetools
└─ AutoBot: KnowledgeBaseV2, ChatHistoryManager
```

---

## Scalability Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                   Horizontal Scaling                          │
└──────────────────────────────────────────────────────────────┘

Current (Single Instance):
┌───────────────────────┐
│ AutoBot Instance      │
│  └─ Memory Search     │
│     └─ Cache (local)  │
└──────────┬────────────┘
           │
           ↓
    ┌──────────┐
    │  Redis   │
    │ (Shared) │
    └──────────┘

Future (Multi-Instance):
┌───────────────────────┐   ┌───────────────────────┐
│ AutoBot Instance 1    │   │ AutoBot Instance 2    │
│  └─ Memory Search     │   │  └─ Memory Search     │
│     └─ L1 Cache       │   │     └─ L1 Cache       │
└──────────┬────────────┘   └──────────┬────────────┘
           │                           │
           └────────────┬──────────────┘
                        ↓
              ┌──────────────────┐
              │  Redis Cluster   │
              │                  │
              │ • L2 Cache (TTL) │
              │ • Entities       │
              │ • Indexes        │
              └──────────────────┘

Benefits:
✅ L1 cache per instance (no sharing needed)
✅ L2 cache shared via Redis (consistency)
✅ Load balancing across instances
✅ Horizontal scaling as needed
```

---

## Error Handling & Fallbacks

```
┌──────────────────────────────────────────────────────────────┐
│                  Graceful Degradation                         │
└──────────────────────────────────────────────────────────────┘

Failure Scenario 1: Ollama Service Down
    Query → [Detect Ollama failure]
              └─► Fallback: Redis keyword-only search
                    └─► Return results with warning

Failure Scenario 2: Redis Timeout
    Query → [Redis timeout (>2s)]
              └─► Fallback: Cached results or empty with error

Failure Scenario 3: Intent Extraction Fails
    Query → [Pattern matching fails]
              └─► Fallback: Full semantic search (slower but accurate)

Failure Scenario 4: No Results Found
    Query → [Empty result set]
              └─► Generate suggestions
                    ├─ Similar queries
                    ├─ Available entity types
                    └─- Recent entities

Circuit Breaker Pattern:
┌─────────────────────────────────────┐
│ Monitor failure rate:               │
│  └─ >50% failures in 1 min          │
│     └─► OPEN circuit                │
│         └─► Direct to fallback      │
│                                     │
│ Half-open after 30s:                │
│  └─ Test with single request        │
│     └─► Success? CLOSE circuit      │
│     └─► Fail? Remain OPEN           │
└─────────────────────────────────────┘
```

---

**End of Architecture Document**

For implementation details, see: [`MEMORY_GRAPH_SEMANTIC_SEARCH.md`](./MEMORY_GRAPH_SEMANTIC_SEARCH.md)
