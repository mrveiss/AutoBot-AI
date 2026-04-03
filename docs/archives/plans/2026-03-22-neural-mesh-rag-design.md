# Neural Mesh RAG — Self-Evolving Knowledge Architecture

> **Date**: 2026-03-22
> **Author**: mrveiss
> **Status**: Approved — Ready for Implementation Planning
> **Tracking Issue**: #1994
> **Absorbs**: #1718 (Agentic RAG), #1719 (Dynamic Weights), #1720 (BM25)
> **Prerequisites**: #1516 (publish_live_event), #1572 (LangChain 1.x), #1836 (Dependency Upgrade)

---

## Executive Summary

Neural Mesh RAG transforms AutoBot's retrieval system from a fixed pipeline into a self-evolving knowledge mesh. The core philosophy: **seed it, AutoBot grows it**. A minimal bootstrap creates structural edges between knowledge chunks. Usage patterns — which chunks get retrieved together, which agents collaborate successfully — drive autonomous graph evolution through Hebbian reinforcement ("nodes that fire together, wire together").

The system builds incrementally across 5 phases, each independently deployable. Phase 1 hardens the existing retrieval foundations. Phase 2 completes the ECL pipeline with dual-mode indexing. Phase 3 brings the mesh to life with PostgreSQL-backed graph evolution and PersonalizedPageRank retrieval. Phase 4 makes the mesh fully autonomous. Phase 5 extends the mesh principle to agent orchestration.

### Key Research Sources

| System | Origin | Pattern Adopted |
|--------|--------|----------------|
| AgentNet | NeurIPS 2025 | Decentralized DAG with per-agent memory + evolution |
| G-Designer | 2024 | GNN-based adaptive communication topology |
| MA-RAG | 2025 | 4-agent query decomposition pipeline |
| A-RAG | 2026 | Hierarchical retrieval interfaces + autonomous strategy |
| GraphRAG | Microsoft 2024 | Knowledge graph + community detection |
| HippoRAG | NeurIPS 2024 | PersonalizedPageRank over knowledge graphs |
| RAPTOR | ICLR 2024 | Recursive clustering + tree-organized retrieval |
| LightRAG | 2024 | Dual-level graph retrieval + incremental updates |
| LazyGraphRAG | Microsoft 2025 | Deferred LLM processing, 700x cheaper queries |
| Modular RAG | 2024 | LEGO-like reconfigurable flow patterns |

---

## Architecture Overview

### Three Storage Layers

```
+------------------------------------------------------------------+
|                        QUERY PATH (hot)                          |
|                                                                  |
|   ChromaDB              Redis Cache           Cross-Encoder      |
|   +---------+          +----------+          +----------+        |
|   | Vectors |--seed--> | Hot Edges |--expand->| Reranker |       |
|   | (embed) |  nodes   | (weight>  |  + rank  | (MiniLM) |       |
|   +---------+          |  0.5)     |          +----------+        |
|                        +----------+                              |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
|                     MESH BRAIN (analytical)                       |
|                                                                  |
|   PostgreSQL                           Background Jobs           |
|   +----------------------+            +------------------+       |
|   | mesh_nodes           |            | EdgeLearner      |       |
|   | mesh_edges           |<---------->| EdgeDiscoverer   |       |
|   | mesh_anchors         |  read/     | MeshPruner       |       |
|   | mesh_evolution_log   |  write     | NodePromoter     |       |
|   +----------------------+            +------------------+       |
|         |                                                        |
|         | sync hot edges (weight > 0.5)                          |
|         v                                                        |
|   Redis Cache (read replica of high-weight edges)                |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
|                     ECL PIPELINE (indexing)                       |
|                                                                  |
|   Document -> Extract -> Cognify -> Load                         |
|                          |                                       |
|              +-----------+--------------+                        |
|              v           v              v                        |
|         Entity Ext.  RAPTOR Trees   LazyGraph NLP                |
|         (LLM-heavy)  (clustering)   (noun phrases)               |
|              |           |              |                         |
|              +-----------+--------------+                        |
|                          v                                       |
|                    MeshSeeder                                    |
|              (structural + semantic edges)                        |
+------------------------------------------------------------------+
```

### Data Flow Summary

| Path | Store | Latency | Who Manages |
|------|-------|---------|-------------|
| Vector similarity | ChromaDB | ~50ms | Indexing pipeline |
| Graph expansion (retrieval) | Redis | ~5ms | Synced from PostgreSQL |
| Edge learning/evolution | PostgreSQL | N/A (async) | Mesh Brain agents |
| Anchor summaries | ChromaDB + PostgreSQL | ~50ms | NodePromoter |
| Full graph analytics | PostgreSQL | ~200ms | Pruner, Discoverer |

### Integration with Existing AutoBot

| Existing Component | Action |
|---|---|
| `autobot_memory_graph/` | Stays as-is (conversation memory, different concern) |
| `services/rag_service.py` | Gets new strategy: `NeuralMeshRetriever` behind feature flag |
| `knowledge/pipeline/` | ECL cognifiers completed, MeshSeeder added as new loader |
| `services/graph_rag_service.py` | Replaced by `NeuralMeshRetriever` (superset) |
| `agents/agent_orchestration/` | Phase 5 adds topology evolution on top |
| `protocols/agent_communication.py` | Extended for mesh topology communication |

---

## Existing Code Assessment

### Fix Before Building On Top

| Component | Problem | Fix |
|---|---|---|
| `keyword_search.py` | TF-only scoring, no IDF/length normalization (#1720) | Upgrade to BM25 |
| `hybrid_search.py` | Hardcoded 70/30 semantic/keyword | Query complexity classifier selects weights |
| `reranking.py` | Hardcoded 80/20 reranker/original blend | Configurable multi-factor blend |
| `rag_service.py` | RAGMetrics computed but never fed back | Add retrieval feedback hook (EdgeLearner input) |
| `pipeline/cognifiers/` | Entity/relationship extraction stubbed | Complete with dual-mode (LLM + NLP) |

### Replaced by Neural Mesh RAG

| Component | Why |
|---|---|
| `graph_rag_service.py` | BFS with static weights -> PPR + weighted mesh expansion |
| `autobot_memory_graph/relations.py` BFS (for knowledge) | PPR for knowledge retrieval; BFS stays for conversation memory |
| Fixed retrieval pipeline in `rag_service.py` | Agentic strategy selection per query complexity |

### Preserve and Extend

| Component | Extension |
|---|---|
| 4-tier caching | Add Tier 5: mesh expansion cache |
| Cross-encoder reranker (MiniLM singleton) | Called after mesh expansion in reranking step |
| ECL pipeline structure (`pipeline/base.py`, `registry.py`, `runner.py`) | Add cognifiers + MeshSeeder loader |
| ChromaDB client (`chromadb_client.py`) | Add `mesh_anchors` collection |
| NPU embedding fallback chain | Unchanged, mesh doesn't affect embedding generation |
| Agent communication protocol | Extended for Phase 5 mesh topology |

---

## Phase 1: Harden Foundations

**Goal:** Make the existing retrieval pipeline mesh-ready. Each item independently deployable, immediately improves search quality.

**Prerequisites:** #1516 (wire `publish_live_event()`)

### 1.1 BM25 Keyword Search

**File:** `autobot-backend/knowledge/search_components/keyword_search.py`

Replace TF-only scoring with BM25:
- Precompute corpus statistics at startup: document count, average length, term frequencies
- Store in Redis: `bm25:corpus_stats` (refreshed on KB changes)
- Parameters: `k1=1.2`, `b=0.75` (configurable via RAG config)
- Existing Redis SCAN iteration stays, only the scoring function changes

### 1.2 Query Complexity Classifier

**New file:** `autobot-backend/knowledge/search_components/query_classifier.py`

```python
class QueryComplexity(Enum):
    SIMPLE = "simple"           # "What is X?" -> semantic-heavy, skip graph
    MODERATE = "moderate"       # "How does X relate to Y?" -> hybrid, light graph
    COMPLEX = "complex"         # "Compare X and Y across Z" -> full pipeline
    MULTI_HOP = "multi_hop"     # "What caused X which led to Y?" -> decomposition
```

Routing table:

| Complexity | Strategies | Graph Expansion | Decomposition |
|---|---|---|---|
| SIMPLE | Semantic only | None | No |
| MODERATE | Hybrid (dynamic weights) | 1-hop | No |
| COMPLEX | Hybrid + reranker | 2-hop | No |
| MULTI_HOP | Full agentic pipeline | PPR | Yes |

### 1.3 Configurable Reranker Blend

**File:** `autobot-backend/knowledge/search_components/reranking.py`

```
Current: final = reranker * 0.8 + original * 0.2
After:   final = w.reranker * reranker + w.vector * vector + w.edge * edge + w.recency * recency
```

- Weights configurable via `rag_config.py`, defaults to current behavior
- Edge weight component starts at 0.0, activated in Phase 3
- Recency score: `1.0 / (1.0 + days_since_access)`

### 1.4 RAG Retrieval Feedback Hook

**File:** `autobot-backend/services/rag_service.py`

```python
@dataclass
class RetrievalFeedbackEvent:
    query_id: str
    query_text: str
    complexity: QueryComplexity
    retrieved_chunk_ids: list[str]
    final_ranked_ids: list[str]
    user_used_ids: list[str]
    response_quality: float | None
    timestamp: datetime
```

- Emitted via `publish_live_event()` after every retrieval
- Stored in Redis stream: `rag:feedback:{date}` with 7-day retention
- Phase 3's EdgeLearner consumes this stream
- Events accumulate and replay when the learner activates

### 1.5 Context Tracker

**New file:** `autobot-backend/knowledge/search_components/context_tracker.py`

Per-query-session tracker preventing redundant chunk reads across multi-step retrieval. Returns zero-token notification when a chunk was already read (A-RAG pattern).

---

## Phase 2: ECL + Dual Indexing

**Goal:** Complete stubbed ECL cognifiers with Neural Mesh RAG patterns. Two indexing modes: LLM-heavy (accuracy) and NLP-light (speed). MeshSeeder creates structural edges.

### 2.1 Dual-Mode Entity Extraction

**File:** `autobot-backend/knowledge/pipeline/cognifiers/entity_extractor.py` (existing stub)

| Mode | When | Method | Cost |
|---|---|---|---|
| LLM-heavy | Small/medium corpora, high-value docs | Existing LLM prompt, 7 entity types | ~2s/doc |
| NLP-light | Large corpora, bulk ingestion | spaCy noun-phrase extraction + regex | ~0.01s/doc |

Auto-mode: NLP for >500 chunks, LLM otherwise (configurable threshold).

### 2.2 Relationship Extraction

**File:** `autobot-backend/knowledge/pipeline/cognifiers/relationship_extractor.py` (existing stub)

Same dual-mode:
- LLM: 22 relationship types (existing model)
- NLP: Co-occurrence + keyword pattern matching (`imports` -> IMPORTS, `extends` -> EXTENDS)

### 2.3 RAPTOR Recursive Summarizer

**File:** `autobot-backend/knowledge/pipeline/cognifiers/summarizer.py` (existing stub -> RAPTOR)

```
Level 0: Raw chunks (existing knowledge_vectors)
Level 1: Cluster 5-10 similar chunks -> summarize each
Level 2: Cluster Level 1 summaries -> summarize again
Level 3: Top-level themes (large corpora only)
```

- Clustering: k-means on chunk embeddings (reuse NPU/Ollama embeddings)
- Each level in separate ChromaDB collection: `knowledge_L0`, `knowledge_L1`, `knowledge_L2`
- Retrieval queries all levels simultaneously

### 2.4 MeshSeeder

**New file:** `autobot-backend/knowledge/pipeline/loaders/mesh_seeder.py`

Runs after all cognifiers complete:
1. Create `mesh_nodes` in PostgreSQL (one per chunk)
2. Structural edges: `PART_OF` (same file), `NEXT` (adjacent chunks)
3. Entity-based edges: shared entity -> edge
4. Semantic edges: cosine > 0.82 -> `SIMILAR_TO`
5. Relationship edges from ECL extraction
6. Sync high-weight edges to Redis

### 2.5 PostgreSQL -> Redis Edge Sync

Background process syncing edges with `weight > 0.5` from PostgreSQL to Redis sorted sets. Interval: 5 minutes (configurable).

---

## Phase 3: Mesh Brain + NeuralMeshRetriever

**Goal:** The graph comes alive. EdgeLearner consumes feedback, PPR replaces BFS, unified retriever ties it together.

**Prerequisites:** PostgreSQL mesh migration

### 3.1 PostgreSQL Mesh Schema

```sql
CREATE TABLE mesh_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id TEXT NOT NULL UNIQUE,
    source_file TEXT,
    node_type TEXT NOT NULL,          -- 'code', 'doc', 'config', 'entity', 'summary_L1', 'summary_L2'
    raptor_level INT DEFAULT 0,
    access_count INT DEFAULT 0,
    is_anchor BOOLEAN DEFAULT FALSE,
    last_accessed TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE mesh_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_node UUID REFERENCES mesh_nodes(id) ON DELETE CASCADE,
    to_node UUID REFERENCES mesh_nodes(id) ON DELETE CASCADE,
    edge_type TEXT NOT NULL,
    weight FLOAT DEFAULT 1.0,
    origin TEXT NOT NULL,              -- 'seeder', 'learner', 'discoverer'
    co_access_count INT DEFAULT 0,
    last_reinforced TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(from_node, to_node, edge_type)
);

CREATE TABLE mesh_evolution_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type TEXT NOT NULL,
    entity_id UUID,
    old_value JSONB,
    new_value JSONB,
    actor TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.2 EdgeLearner — Hebbian Reinforcement

**New file:** `autobot-backend/services/mesh_brain/edge_learner.py`

Consumes `RetrievalFeedbackEvent` stream:
- Top-5 co-retrieved pairs get edges reinforced (EMA: `weight * 0.95 + 1.0 * 0.05`)
- New `CO_RETRIEVED` edges created after 3 co-occurrences, starting weight 0.3
- Async background task, non-blocking
- Bumps `access_count` on all retrieved nodes

### 3.3 PersonalizedPageRank

**New file:** `autobot-backend/services/mesh_brain/ppr.py`

Power iteration PPR over the mesh graph:
- Loads 3-hop subgraph from PostgreSQL (not full graph)
- Edge weights influence propagation directly
- `alpha=0.15` teleport probability (biased toward seed nodes)
- Converges in ~10-15 iterations for typical subgraphs

### 3.4 NeuralMeshRetriever

**New file:** `autobot-backend/services/neural_mesh_retriever.py`

Unified retriever replacing `graph_rag_service.py`:

```
1. Classify query complexity
2. Hybrid seed retrieval (BM25 + semantic, dynamic weights)
3. Anchor check (nearby pre-computed entry points)
4. PPR mesh expansion
5. Fetch expanded chunk content
6. Context tracker filter (skip seen chunks)
7. RAPTOR multi-level retrieval (for COMPLEX/MULTI_HOP)
8. Configurable rerank (vector x edge x reranker x recency)
9. Fire EdgeLearner (async, non-blocking)
```

Feature flag: `mesh_retriever_enabled` in RAG config. Legacy pipeline stays as fallback.

---

## Phase 4: Autonomous Evolution

**Goal:** Mesh Brain becomes self-managing. No human intervention needed after activation.

### 4.1 EdgeDiscoverer — Semantic Pattern Mining

**New file:** `autobot-backend/services/mesh_brain/edge_discoverer.py`

Scheduled nightly:
- Finds high-weight `CO_RETRIEVED` edges (weight > 0.7, co_access > 5)
- Clusters similar edge pairs to reduce LLM calls
- LLM classifies relationship type from predefined vocabulary + can suggest new types
- Upgrades `CO_RETRIEVED` -> named typed edge (CALLS, CONFIGURES, VALIDATES, etc.)
- Batch size capped at 50 per run

### 4.2 MeshPruner — Entropy Control

**New file:** `autobot-backend/services/mesh_brain/mesh_pruner.py`

Scheduled weekly:
1. Decay unreinforced learner edges (30+ days stale, factor 0.8)
2. Delete edges below weight 0.1
3. Archive orphaned nodes (no edges, 60+ days no access)
4. Merge near-duplicate edges
5. Graph density check (if avg edges/node > 20, raise creation threshold)

Safety: seeder edges never decayed. Archive, not delete for nodes. Full evolution log.

### 4.3 NodePromoter — Anchor Emergence

**New file:** `autobot-backend/services/mesh_brain/node_promoter.py`

Scheduled daily:
- Promote nodes with access_count > 50 and 5+ edges to anchor status
- Generate neighborhood summary (2-hop), store in `mesh_anchors` ChromaDB collection
- Demote stale anchors (access dropped below 10, 30+ days inactive)
- Anchors serve as fast retrieval entry points

### 4.4 Mesh Brain Scheduler

**New file:** `autobot-backend/services/mesh_brain/scheduler.py`

| Job | Schedule |
|-----|----------|
| EdgeLearner | Realtime (Redis stream consumer) |
| Edge Sync | Every 5 minutes |
| NodePromoter | Daily 3 AM |
| EdgeDiscoverer | Daily 2 AM |
| MeshPruner | Weekly Sunday 4 AM |

### 4.5 Feature Flag Progression

```python
MESH_FEATURE_FLAGS = {
    "mesh_seed_edges":      True,     # Phase 2
    "mesh_retriever":       True,     # Phase 3
    "mesh_edge_learner":    False,    # Phase 4 - flip after retriever stable
    "mesh_edge_discoverer": False,    # Phase 4 - flip after learner producing
    "mesh_pruner":          False,    # Phase 4 - flip after discoverer running
    "mesh_node_promoter":   False,    # Phase 4 - last, full autonomy
}
```

Runtime toggleable via `PUT /api/knowledge/rag/config`.

### 4.6 Evolution Timeline

```
Week 1:   Seed edges only (SIMILAR_TO, PART_OF, NEXT, entity-based)
Week 2:   CO_RETRIEVED edges appear from actual usage
Week 3:   EdgeDiscoverer names them (CALLS, CONFIGURES, VALIDATES...)
Month 2:  Anchor nodes emerge around most-used knowledge
Month 2:  Pruner clears first stale edges, graph stays lean
Month 3:  Graph reflects how AutoBot is actually used
Month 6:  Mesh is a learned map of knowledge topology
```

---

## Phase 5: Agentic RAG + Mesh Agent Topology

**Goal:** Complex queries get decomposed and solved iteratively. Agent orchestration evolves its own topology using the same Hebbian principle.

**Prerequisites:** #1572 (LangChain 1.x migration)

### 5.1 Query Decomposer (MA-RAG Pattern)

**New file:** `autobot-backend/services/neural_mesh/query_decomposer.py`

Activated for MULTI_HOP queries only:
- LLM breaks query into 2-4 sequential retrieval steps
- Each step uses NeuralMeshRetriever
- Evidence extraction at sentence level between steps
- Results aggregated across all steps

### 5.2 Evidence Extractor

**New file:** `autobot-backend/services/neural_mesh/evidence_extractor.py`

Sentence-level precision instead of whole-chunk inclusion:
- Split chunks into sentences
- Cross-encoder scores each sentence against the query (reuses MiniLM singleton)
- Top-k sentences with source attribution
- Reduces context: ~500 tokens instead of ~2000 tokens

### 5.3 Autonomous Strategy Selection (A-RAG Pattern)

**Modified file:** `autobot-backend/services/neural_mesh_retriever.py`

For COMPLEX/MULTI_HOP queries, ReAct loop:
- Available tools: semantic_search, keyword_search, mesh_expand, raptor_retrieve, anchor_lookup, decompose_query
- LLM decides which tool to use next based on what's been retrieved
- Max steps: 5-10 (configurable), prevents runaway loops
- SIMPLE/MODERATE queries stay on Phase 3 fixed path (no LLM overhead)

### 5.4 Agent Mesh Topology — Dynamic DAG

**New files:**
- `autobot-backend/agents/agent_orchestration/topology.py`
- `autobot-backend/agents/agent_orchestration/topology_evolution.py`

Hebbian principle applied to agents:
- Track which agent pairs produce good results together
- `agent_connections` table: from_agent, to_agent, task_type, weight
- After workflow completion: reinforce (success) or weaken (failure) connection weights
- EMA: `weight * 0.9 + outcome * 0.1`

### 5.5 Topology-Aware Routing

**Modified file:** `autobot-backend/agents/agent_orchestration/routing.py`

For complex/multi-step tasks:
- Select primary agent (existing logic)
- Query topology for high-weight collaborators
- Route as parallel or pipeline pattern based on connection topology

### 5.6 Agent Specialization Emergence

**New file:** `autobot-backend/services/mesh_brain/agent_evolution.py`

Analyzes 30-day task history per agent:
- Identifies task types with highest success rates
- Updates agent profile with discovered specializations
- Router preferentially assigns agents to their emergent specialties

### 5.7 Phase 5 Schema

```sql
CREATE TABLE agent_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_agent TEXT NOT NULL,
    to_agent TEXT NOT NULL,
    task_type TEXT,
    weight FLOAT DEFAULT 0.5,
    co_success_count INT DEFAULT 0,
    co_failure_count INT DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(from_agent, to_agent, task_type)
);

CREATE TABLE agent_task_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    workflow_id TEXT,
    success BOOLEAN NOT NULL,
    execution_time_ms INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 5.8 Full System Query Flow

```
Query -> QueryClassifier

SIMPLE:     Semantic search -> return (~50ms)
MODERATE:   Hybrid search -> 1-hop mesh expand -> rerank
COMPLEX:    Agentic strategy selection (ReAct loop, 2-5s)
MULTI_HOP:  Query decomposition -> sequential sub-queries -> evidence aggregation

All paths:  EdgeLearner fires (async) -> mesh evolves
            AgentTopology records outcome -> agent DAG evolves
```

---

## API Endpoints

### Mesh Brain Status

```
GET  /api/mesh/brain/status           -- Mesh Brain health + job status
GET  /api/mesh/brain/evolution-log    -- Recent evolution events
GET  /api/mesh/stats                  -- Graph statistics (nodes, edges, anchors)
GET  /api/mesh/topology               -- Agent DAG visualization data
PUT  /api/knowledge/rag/config        -- Toggle feature flags at runtime
```

### Mesh Retrieval

```
POST /api/knowledge/rag/advanced_search  -- Existing endpoint, mesh-aware when enabled
GET  /api/mesh/anchors                   -- List anchor nodes + summaries
```

---

## File Structure (New + Modified)

```
autobot-backend/
+-- knowledge/
|   +-- search_components/
|   |   +-- keyword_search.py          # MODIFY: BM25 upgrade
|   |   +-- query_classifier.py        # NEW: complexity classifier
|   |   +-- context_tracker.py         # NEW: prevent redundant reads
|   |   +-- hybrid_search.py           # MODIFY: dynamic weights
|   |   +-- reranking.py               # MODIFY: configurable blend
|   +-- pipeline/
|   |   +-- cognifiers/
|   |   |   +-- entity_extractor.py    # MODIFY: complete with dual-mode
|   |   |   +-- relationship_extractor.py  # MODIFY: complete with dual-mode
|   |   |   +-- summarizer.py         # MODIFY: RAPTOR recursive
|   |   +-- loaders/
|   |       +-- mesh_seeder.py         # NEW: structural edge creation
+-- services/
|   +-- rag_service.py                 # MODIFY: mesh retriever integration
|   +-- neural_mesh_retriever.py       # NEW: unified mesh-aware retriever
|   +-- mesh_brain/
|   |   +-- __init__.py                # NEW
|   |   +-- edge_learner.py            # NEW: Hebbian reinforcement
|   |   +-- edge_discoverer.py         # NEW: semantic pattern mining
|   |   +-- mesh_pruner.py             # NEW: entropy control
|   |   +-- node_promoter.py           # NEW: anchor emergence
|   |   +-- ppr.py                     # NEW: PersonalizedPageRank
|   |   +-- edge_sync.py              # NEW: PostgreSQL -> Redis sync
|   |   +-- scheduler.py              # NEW: background job orchestration
+-- services/neural_mesh/
|   +-- __init__.py                    # NEW
|   +-- query_decomposer.py           # NEW: MA-RAG decomposition
|   +-- evidence_extractor.py         # NEW: sentence-level extraction
+-- agents/agent_orchestration/
|   +-- routing.py                     # MODIFY: topology-aware routing
|   +-- topology.py                    # NEW: dynamic agent DAG
|   +-- topology_evolution.py          # NEW: agent connection evolution
+-- services/mesh_brain/
|   +-- agent_evolution.py             # NEW: specialization tracking
+-- alembic/versions/
    +-- xxx_add_mesh_tables.py         # NEW: mesh schema migration
    +-- xxx_add_agent_topology.py      # NEW: agent topology migration
```

---

## Dependency Sequence

```
Phase 0: Prerequisites
  #1516 -> publish_live_event (feedback hook needs this)

Phase 1: Harden Foundations
  BM25 -> query classifier -> configurable reranker -> feedback hook -> context tracker

Phase 2: ECL + Dual Indexing
  Entity extractor -> relationship extractor -> RAPTOR summarizer -> MeshSeeder -> edge sync

Phase 3: Mesh Brain + Retriever
  PostgreSQL migration -> EdgeLearner -> PPR -> NeuralMeshRetriever -> integration

Phase 4: Autonomous Evolution
  EdgeDiscoverer -> MeshPruner -> NodePromoter -> scheduler -> feature flags

Phase 5: Agentic RAG + Mesh Topology
  #1572 LangChain migration -> query decomposer -> evidence extractor ->
  autonomous strategy -> agent topology -> topology routing -> agent evolution
```

Each phase is independently deployable and provides value on its own.
