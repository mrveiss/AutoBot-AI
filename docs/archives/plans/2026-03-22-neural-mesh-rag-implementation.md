# Neural Mesh RAG Implementation Plan (#1994)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform AutoBot's retrieval into a self-evolving knowledge mesh — seed it once, AutoBot grows it through usage patterns.

**Architecture:** 5-phase dependency chain. Phase 1 hardens retrieval foundations. Phase 2 completes ECL pipeline with RAPTOR + MeshSeeder. Phase 3 adds PostgreSQL mesh graph + EdgeLearner + PPR + NeuralMeshRetriever. Phase 4 makes the mesh autonomous (Discoverer, Pruner, Promoter). Phase 5 adds agentic query decomposition + agent topology evolution.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy async (PostgreSQL), Redis Stack, ChromaDB, spaCy (NLP-light), pytest-asyncio, Alembic migrations.

**Tracking Issue:** #1994
**Design Document:** `docs/plans/2026-03-22-neural-mesh-rag-design.md`

**Test patterns:** Colocated `*_test.py` next to source. `@pytest.mark.asyncio` for async. `AsyncMock` for Redis/ChromaDB/LLM. Fixtures in `conftest.py`. `AUTOBOT_TEST_MODE=true` auto-set.

---

## Dependency Graph

```
Task 0.1 (#1516 wire events)
    |
    v
Task 1.1 (BM25) --> Task 1.2 (Classifier) --> Task 1.3 (Reranker blend)
                                                      |
Task 1.4 (Feedback hook) <----------------------------+
    |
Task 1.5 (Context tracker)
    |
    v
Task 2.1 (Entity ext) --> Task 2.2 (Rel ext) --> Task 2.3 (RAPTOR)
                                                       |
Task 2.4 (MeshSeeder) <-------------------------------+
    |
Task 2.5 (Edge sync)
    |
    v
Task 3.1 (PG migration) --> Task 3.2 (EdgeLearner) --> Task 3.3 (PPR)
                                                              |
Task 3.4 (NeuralMeshRetriever) <------------------------------+
    |
Task 3.5 (RAGService integration)
    |
    v
Task 4.1 (EdgeDiscoverer) --> Task 4.2 (MeshPruner) --> Task 4.3 (NodePromoter)
                                                               |
Task 4.4 (Scheduler) <----------------------------------------+
    |
Task 4.5 (Feature flags + API)
    |
    v
Task 5.1 (#1572 LangChain) --> Task 5.2 (Decomposer) --> Task 5.3 (Evidence ext)
                                                                 |
Task 5.4 (Agentic strategy) <-----------------------------------+
    |
Task 5.5 (Agent topology) --> Task 5.6 (Topology routing) --> Task 5.7 (Agent evolution)
```

---

## Phase 0: Prerequisites

### Task 0.1: Wire publish_live_event() Producers (#1516)

**Files:**
- Modify: `autobot-backend/services/rag_service.py`
- Test: `autobot-backend/services/rag_service_events_test.py`
- Reference: `autobot-backend/live_event_manager.py`

**Step 1: Write failing test**

```python
# autobot-backend/services/rag_service_events_test.py
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_rag_emits_retrieval_event():
    with patch("services.rag_service.publish_live_event", new_callable=AsyncMock) as mock_pub:
        from services.rag_service import RAGService
        service = RAGService.__new__(RAGService)
        service._initialized = True
        await service._emit_retrieval_feedback(
            query="test", retrieved_ids=["c1"], ranked_ids=["c1"],
        )
        mock_pub.assert_called_once()
        payload = mock_pub.call_args[0][2]
        assert payload["query_text"] == "test"
```

**Step 2:** Run: `pytest autobot-backend/services/rag_service_events_test.py -v` — Expected: FAIL

**Step 3: Implement** — Add `_emit_retrieval_feedback()` and `_store_feedback_in_stream()` to RAGService. Wire into search methods after reranking.

**Step 4:** Run test — Expected: PASS

**Step 5: Commit**

```bash
git add autobot-backend/services/rag_service.py autobot-backend/services/rag_service_events_test.py
git commit -m "feat(rag): emit retrieval feedback events (#1516, #1994)"
```

---

## Phase 1: Harden Foundations

### Task 1.1: BM25 Keyword Search (#1720)

**Files:**
- Create: `autobot-backend/knowledge/search_components/bm25.py`
- Test: `autobot-backend/knowledge/search_components/bm25_test.py`
- Modify: `autobot-backend/knowledge/search_components/keyword_search.py`

**Step 1: Write failing tests**

```python
# autobot-backend/knowledge/search_components/bm25_test.py
import pytest
from knowledge.search_components.bm25 import BM25Scorer

class TestBM25:
    def test_rare_terms_score_higher(self):
        s = BM25Scorer(total_docs=100, avg_doc_length=50.0,
                       doc_frequencies={"python": 10, "banana": 1})
        assert s.score(["banana"], "banana fruit", 2) > s.score(["python"], "python lang", 2)

    def test_shorter_docs_score_higher(self):
        s = BM25Scorer(total_docs=100, avg_doc_length=50.0, doc_frequencies={"x": 10})
        assert s.score(["x"], "x y", 2) > s.score(["x"], "x " + "w " * 100, 101)

    def test_unknown_terms_smoothed(self):
        s = BM25Scorer(total_docs=100, avg_doc_length=50.0, doc_frequencies={})
        assert s.score(["unknown"], "unknown term", 2) > 0

    @pytest.mark.parametrize("k1,b", [(1.2, 0.75), (0.5, 0.3)])
    def test_configurable(self, k1, b):
        s = BM25Scorer(total_docs=10, avg_doc_length=20.0, doc_frequencies={"t": 5}, k1=k1, b=b)
        assert s.score(["t"], "t doc", 2) > 0
```

**Step 2:** Run — FAIL (module missing)

**Step 3: Implement BM25Scorer** — IDF with smoothing, k1/b params, length normalization

**Step 4:** Run — PASS

**Step 5:** Integrate into KeywordSearcher, replacing `score_fact_by_terms()`

**Step 6: Commit**

```bash
git add autobot-backend/knowledge/search_components/bm25.py \
       autobot-backend/knowledge/search_components/bm25_test.py \
       autobot-backend/knowledge/search_components/keyword_search.py
git commit -m "feat(search): upgrade keyword search to BM25 (#1720, #1994)"
```

---

### Task 1.2: Query Complexity Classifier

**Files:**
- Create: `autobot-backend/knowledge/search_components/query_classifier.py`
- Test: `autobot-backend/knowledge/search_components/query_classifier_test.py`

**Step 1: Write failing tests**

```python
import pytest
from knowledge.search_components.query_classifier import QueryClassifier, QueryComplexity

class TestClassifier:
    @pytest.mark.parametrize("query,expected", [
        ("What is Redis?", QueryComplexity.SIMPLE),
        ("How does Redis relate to ChromaDB?", QueryComplexity.MODERATE),
        ("Compare BM25 and TF-IDF across corpus sizes", QueryComplexity.COMPLEX),
        ("What caused the auth failure that led to rollback?", QueryComplexity.MULTI_HOP),
    ])
    def test_classification(self, query, expected):
        assert QueryClassifier().classify(query) == expected

    def test_empty_defaults_simple(self):
        assert QueryClassifier().classify("") == QueryComplexity.SIMPLE
```

**Step 2-4:** Implement rule-based classifier (regex patterns + heuristics), verify pass

**Step 5: Commit**

```bash
git commit -m "feat(search): add query complexity classifier (#1719, #1994)"
```

---

### Task 1.3: Configurable Reranker Blend

**Files:**
- Modify: `autobot-backend/knowledge/search_components/reranking.py`
- Modify: `autobot-backend/services/rag_config.py`
- Test: `autobot-backend/knowledge/search_components/reranking_blend_test.py`

**Step 1: Write failing tests** — RerankWeights dataclass, compute_blended_score, recency_score

**Step 2:** Implement + add weights to RAGConfig

**Step 3: Commit**

```bash
git commit -m "feat(search): configurable reranker blend weights (#1994)"
```

---

### Task 1.4: Feedback Hook Integration

Wire `_emit_retrieval_feedback()` (from 0.1) with classifier complexity + Redis stream storage.

```bash
git commit -m "feat(rag): integrate feedback hook with complexity classifier (#1994)"
```

---

### Task 1.5: Context Tracker

**Files:**
- Create: `autobot-backend/knowledge/search_components/context_tracker.py`
- Test: `autobot-backend/knowledge/search_components/context_tracker_test.py`

**Step 1: Write failing tests** — filter_unseen, record, token_budget, summary

**Step 2:** Implement (set-based tracking, token budget)

**Step 3: Commit**

```bash
git commit -m "feat(search): add context tracker (#1994)"
```

---

## Phase 2: ECL + Dual Indexing

### Task 2.1: Dual-Mode Entity Extraction

**Files:**
- Modify: `autobot-backend/knowledge/pipeline/cognifiers/entity_extractor.py`
- Test: `autobot-backend/knowledge/pipeline/cognifiers/entity_extractor_test.py`

**Prereq:** `pip install spacy && python3 -m spacy download en_core_web_sm`

**Step 1: Write tests** — NLP mode extracts entities, auto mode selects by chunk count

**Step 2:** Add `_nlp_extract()` (spaCy NER + noun phrases) and `_select_mode()` to EntityExtractor

**Step 3: Commit**

```bash
git commit -m "feat(pipeline): add NLP-light entity extraction mode (#1994)"
```

---

### Task 2.2: Dual-Mode Relationship Extraction

Same pattern. NLP mode: co-occurrence + keyword patterns.

```bash
git commit -m "feat(pipeline): add NLP-light relationship extraction (#1994)"
```

---

### Task 2.3: RAPTOR Recursive Summarizer

**Files:**
- Modify: `autobot-backend/knowledge/pipeline/cognifiers/summarizer.py`
- Test: `autobot-backend/knowledge/pipeline/cognifiers/summarizer_raptor_test.py`

**Step 1: Write tests** — k-means clustering, multi-level output

**Step 2:** Add recursive clustering + per-level ChromaDB collections

**Step 3: Commit**

```bash
git commit -m "feat(pipeline): add RAPTOR recursive summarizer (#1994)"
```

---

### Task 2.4: MeshSeeder Loader

**Files:**
- Create: `autobot-backend/knowledge/pipeline/loaders/mesh_seeder.py`
- Test: `autobot-backend/knowledge/pipeline/loaders/mesh_seeder_test.py`

**Step 1: Write tests** — PART_OF edges, NEXT edges, entity edges

**Step 2:** Implement structural + semantic + entity edge creation

**Step 3: Commit**

```bash
git commit -m "feat(pipeline): add MeshSeeder loader (#1994)"
```

---

### Task 2.5: Edge Sync Service

**Files:**
- Create: `autobot-backend/services/mesh_brain/__init__.py`
- Create: `autobot-backend/services/mesh_brain/edge_sync.py`
- Test: `autobot-backend/services/mesh_brain/edge_sync_test.py`

**Step 1: Write tests** — syncs only above min_weight threshold

**Step 2:** Implement PostgreSQL -> Redis sorted set sync

**Step 3: Commit**

```bash
git commit -m "feat(mesh): add edge sync service (#1994)"
```

---

## Phase 3: Mesh Brain + NeuralMeshRetriever

### Task 3.1: PostgreSQL Mesh Schema

**Files:**
- Create: `autobot-backend/services/mesh_brain/models.py`
- Create: Alembic migration

**Step 1:** Define MeshNode, MeshEdge, MeshEvolutionLog SQLAlchemy models

**Step 2:** `alembic revision --autogenerate -m "add mesh tables (#1994)"` then verify up/down

**Step 3: Commit**

```bash
git commit -m "feat(mesh): add PostgreSQL mesh schema (#1994)"
```

---

### Task 3.2: EdgeLearner

**Files:**
- Create: `autobot-backend/services/mesh_brain/edge_learner.py`
- Test: `autobot-backend/services/mesh_brain/edge_learner_test.py`

**Step 1: Write tests** — reinforce existing (EMA), create after threshold, skip below threshold

**Step 2:** Implement Hebbian reinforcement + Redis stream consumer

**Step 3: Commit**

```bash
git commit -m "feat(mesh): add EdgeLearner (#1994)"
```

---

### Task 3.3: PersonalizedPageRank

**Files:**
- Create: `autobot-backend/services/mesh_brain/ppr.py`
- Test: `autobot-backend/services/mesh_brain/ppr_test.py`

**Step 1: Write tests** — seed nodes rank highest, high-weight edges propagate, scores sum to 1

**Step 2:** Implement power iteration PPR (alpha=0.15, subgraph loading, convergence)

**Step 3: Commit**

```bash
git commit -m "feat(mesh): add PersonalizedPageRank (#1994)"
```

---

### Task 3.4: NeuralMeshRetriever

**Files:**
- Create: `autobot-backend/services/neural_mesh_retriever.py`
- Test: `autobot-backend/services/neural_mesh_retriever_test.py`

**Step 1: Write tests** — simple skips expansion, moderate uses PPR, edge learner fires

**Step 2:** Implement full retrieval flow (classify->seed->anchor->PPR->track->RAPTOR->rerank->learn)

**Step 3: Commit**

```bash
git commit -m "feat(mesh): add NeuralMeshRetriever (#1994)"
```

---

### Task 3.5: RAGService Integration

**Files:**
- Modify: `autobot-backend/services/rag_service.py`
- Modify: `autobot-backend/services/rag_config.py`
- Test: `autobot-backend/services/rag_service_mesh_test.py`

**Step 1: Write tests** — mesh flag routes to mesh retriever, disabled uses legacy

**Step 2:** Add feature flag + conditional routing

**Step 3: Commit**

```bash
git commit -m "feat(rag): integrate NeuralMeshRetriever behind feature flag (#1994)"
```

---

## Phase 4: Autonomous Evolution

### Task 4.1: EdgeDiscoverer

Create `autobot-backend/services/mesh_brain/edge_discoverer.py` + test. LLM labels CO_RETRIEVED edges.

```bash
git commit -m "feat(mesh): add EdgeDiscoverer (#1994)"
```

### Task 4.2: MeshPruner

Create `autobot-backend/services/mesh_brain/mesh_pruner.py` + test. 5 pruning rules, safety guards.

```bash
git commit -m "feat(mesh): add MeshPruner (#1994)"
```

### Task 4.3: NodePromoter

Create `autobot-backend/services/mesh_brain/node_promoter.py` + test. Anchor promotion + demotion.

```bash
git commit -m "feat(mesh): add NodePromoter (#1994)"
```

### Task 4.4: Mesh Brain Scheduler

Create `autobot-backend/services/mesh_brain/scheduler.py` + test. 5 job registrations.

```bash
git commit -m "feat(mesh): add Mesh Brain scheduler (#1994)"
```

### Task 4.5: Feature Flags + Mesh API

Add 6 flags to RAGConfig. Create `autobot-backend/api/mesh.py` endpoints. Register router.

```bash
git commit -m "feat(mesh): add feature flags + mesh API (#1994)"
```

---

## Phase 5: Agentic RAG + Mesh Agent Topology

### Task 5.1: LangChain 1.x Migration (#1572)

Update langchain-core, verify chat_workflow/graph.py works.

```bash
git commit -m "fix(security): migrate langchain-core to 1.x (#1572, #1994)"
```

### Task 5.2: Query Decomposer

Create `autobot-backend/services/neural_mesh/query_decomposer.py` + test. MA-RAG decomposition.

```bash
git commit -m "feat(mesh): add query decomposer (#1994)"
```

### Task 5.3: Evidence Extractor

Create `autobot-backend/services/neural_mesh/evidence_extractor.py` + test. Sentence-level precision.

```bash
git commit -m "feat(mesh): add evidence extractor (#1994)"
```

### Task 5.4: Autonomous Strategy Selection

Modify `neural_mesh_retriever.py`. ReAct loop with tool registry.

```bash
git commit -m "feat(mesh): add autonomous strategy selection (#1718, #1994)"
```

### Task 5.5: Agent Topology + Migration

Create `autobot-backend/agents/agent_orchestration/topology.py` + Alembic migration + test.

```bash
git commit -m "feat(mesh): add agent topology (#1994)"
```

### Task 5.6: Topology-Aware Routing

Modify `autobot-backend/agents/agent_orchestration/routing.py`. Complex tasks query topology.

```bash
git commit -m "feat(mesh): add topology-aware routing (#1994)"
```

### Task 5.7: Agent Specialization Emergence

Create `autobot-backend/services/mesh_brain/agent_evolution.py` + test.

```bash
git commit -m "feat(mesh): add agent specialization emergence (#1994)"
```

---

## Verification Checklist

- [ ] `pytest autobot-backend/ -v --tb=short` — all pass
- [ ] `flake8 autobot-backend/` — clean
- [ ] Feature flags default safe (mesh disabled)
- [ ] Legacy RAG works when mesh disabled
- [ ] `alembic upgrade head` / `downgrade -1` clean
- [ ] `GET /api/mesh/brain/status` returns healthy
- [ ] `GET /api/mesh/stats` shows correct counts
