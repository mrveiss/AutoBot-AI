# Research: does RAG / the knowledge base use graph results?

Date: 2026-10-09 · Base: `origin/main` @ `5c56e3a353` · Status: findings filed — #18139–#18144, comments on #16665, #17526, #18094

## Source

An auto-generated architecture diagram of this repository. It draws
`RAG Retrieval → Vector Search` and `Knowledge Base API → Knowledge Graph`, but no edge from
RAG to any graph. Question raised: vectors give similarity, a graph gives linkage and context —
does retrieval actually consult the graph?

## Answer

**Graph retrieval is built three times and none of it is on the default chat path.** The diagram
is accurate about the default behaviour: chat retrieval is vector(+hybrid) only.

| # | Graph store | Retrieval code | Reached from chat by default? | Gate (file:line) |
|---|---|---|---|---|
| 1 | Neural mesh (Postgres, PPR) — `services/mesh_brain/` | `NeuralMeshRetriever` (`services/neural_mesh_retriever.py`, "mesh_expand: follow graph edges") | **No** | `mesh_retriever_enabled: bool = False` — `services/rag_config.py:70` |
| 2 | Memory graph (entities/relations) — `autobot_memory_graph/` | `GraphRAGService.graph_aware_search` (hybrid RAG + graph proximity, weight 0.3) | **No** | only via `retrieval_dispatcher` `kag` strategy; `enable_kag: bool = False` — `services/rag_config.py:127`; dispatcher's only caller is `api/knowledge_rag.py:563`, not chat |
| 3 | KB fact relations — `knowledge/relations` | `_expand_fact_relations` in `api/knowledge_search_aggregator.py:77` | **No** | only behind `POST .../context` (`api/knowledge_search_aggregator.py:463`), not the chat path |

Chat path, verified: `chat_workflow/manager.py:348-380` builds a plain `RAGService(kb)` →
`ChatKnowledgeService` (`services/knowledge/service.py:268`) calls `rag_service.advanced_search`.
In `advanced_search`, the mesh branch (`services/rag_service.py:636`) runs only when the flag is
on. No YAML/frontend sets `mesh_retriever_enabled` or `enable_kag` (grep of `*.yaml`, `*.yml`,
`*.vue`, `*.ts`: 0 hits), so the dataclass defaults hold.

Graph search is user-reachable only as a separate KB tool: `api/graph_rag.py` (`/search`, `/path`)
via `components/knowledge/GraphRAGQuery.vue`.

## Secondary findings

- **Population — corrected after cross-check.** `services/knowledge/doc_indexer.py` writes no graph
  (0 matches for `graph|mesh|entity|relation`), but the ECL knowledge pipeline does:
  `knowledge/pipeline/config.py:118-167` runs `mesh_seeder` and the Redis graph loader, and
  `knowledge/pipeline/loaders/redis_graph_loader.py:93` writes entities (attribution defect: #17588).
  So the graph is fed by one of the indexers and not the other — the indexer fork is #18129.
  `api/agent_config.py:229`'s "invoked by kb_librarian during ingestion" still has no caller found.
  **Not verified:** live node/edge counts — did not query the host DB.
- **Recorded decision vs reality.** #4761 closed with "Phase 3 is now active" for the mesh
  retriever. The wiring is active (`initialization/neural_mesh_wiring.py`); the retrieval is not
  because the flag defaults off.
- **Three graphs, one concept.** Mesh, memory graph and fact relations each have their own
  storage and expansion logic — a consolidation question before wiring any of them into chat.
- Related open work: #17625 (chat retrieval queries neither doc nor code chunks), #17215
  (multi-view retrieval umbrella), #17211 (corpus bridge-term graph), #13251 (retrieval quality
  is unmeasurable — needed to prove a graph step helps).

## Visible vs hidden metrics

- **Visible:** graph expansion adds linked context similarity misses (multi-hop, entity
  neighbours); all code exists and is tested.
- **Hidden:** extra latency on every chat turn (a graph hop + rerank inside a 10s RAG timeout,
  `initialization/lifespan.py:1163`); access control — a relation is not an access grant
  (#16665 handling exists only in path 3); empty or noisy graph adds noise; three stores to keep
  consistent; no benchmark (#13251) to show the gain.
- **Weighing:** enabling a flag is cheap; enabling it *blind* is not. Order should be:
  pick one graph → confirm it is populated from ingestion → measure → default on.

## Open decisions (owner)

1. Which graph is canonical for retrieval: mesh (PPR), memory graph (KAG), or KB fact relations?
2. Default-on in chat, or per-collection `auto` mode (`retrieval_dispatcher.select_strategy`)?

## Forks in this topic (sweep 2026-10-09)

A fork = one concept defined in 2+ places that can drift (#17312). Verified = re-checked by
reading the cited lines; reported = from a read-only sweep, not re-read.

### Defects found on the way (not forks — crashes)

| # | Defect | Evidence | Status | Existing issue |
|---|---|---|---|---|
| D1 | PPR receives the mesh **adapter**, whose `get_neighbors(node_id)` has no `min_weight`; PPR calls `get_neighbors(node_id, min_weight=…)` → `TypeError` the first time the mesh path runs | `initialization/neural_mesh_wiring.py:33,38`; `services/mesh_brain/ppr.py:167`; `services/mesh_brain/mesh_db_adapter.py:91` | verified | none found |
| D2 | `security_memory_integration` calls `memory_graph.traverse_relations(entity_name=, depth=)`; the only definition is the KB's (`start_fact_id`, `max_depth`), no `__getattr__` delegation in `autobot_memory_graph/` | `services/security_memory_integration.py:831`; `knowledge/relations.py:261` | verified | none found |
| D3 | `/graph-rag` search authenticates but never filters results by caller access | `api/graph_rag.py:172` (`current_user` unused in handler) | verified | #16665 lists `api/graph_rag.py:163` |

D1 means flipping `mesh_retriever_enabled` today would fail, not merely add noise.

### Forks

| # | Concept | Homes | Disagreement | Status | Existing issue |
|---|---|---|---|---|---|
| F1 | Graph store + traversal | KB relations `knowledge/relations.py:261` (depth 2) · memory graph `autobot_memory_graph/relations.py:423` (depth 1) · PropertyGraph `autobot_memory_graph/property_graph.py:483` (2; shortest-path 6) · mesh `services/mesh_brain/mesh_db.py:423` · `api/knowledge_graph_routes.py:355` reads a 4th key space | 4–5 stores, 5 depth defaults; PropertyGraph mirror skips `create_relation_by_id`/deletes, so path-finding can drift from what GraphRAG traverses | reported | #17526 covers memory graph vs LLC relations only — mesh, PropertyGraph and the routes' key space are not in it |
| F2 | Vector + graph score blend | `services/graph_rag_service.py:647` (w=0.3 multiplicative) · `services/neural_mesh_retriever.py:461` (additive `ppr_boost`) · `knowledge/search_components/reranking.py:46` (`edge=0.0`, `edge_weight` never passed) | 3 formulas; 0.3 restated at `lifespan.py:1175`, response schema default 0.0 | reported | none found |
| F3 | Entity extractors | `agents/graph_entity_extractor.py:190` · `knowledge/pipeline/cognifiers/entity_extractor.py:44` · GraphRAGService name lookup | extractor emits lowercase types `create_entity` rejects; error swallowed | reported | #13805, #13553 |
| F4 | Entity-type vocabularies | `autobot_memory_graph/core.py:40` (14) · `knowledge/pipeline/models/entity.py:19` (8) · `models/entity_mapping.py:19` (9) · `services/security_memory_integration.py:87` | overlap is 2 types; relations ARE unified via `CORE_RELATION_TYPES` | reported | #13840 |
| F5 | Chunk ↔ graph node identity | `neural_mesh_retriever.py:444` vs `:465` (same file disagrees) · `rag_service.py:653` · `doc_indexer.py:863` (md5[:12], not stored in metadata) · `mesh_db.py` uuid ids | vector hits fall back to path; join to mesh nodes uncertain (mesh_nodes has a `chunk_id` column — not checked what fills it) | partly verified | #2050 (closed, MeshSeeder ids) |
| F6 | RAGService config | `lifespan.py:1163` timeout 10s vs `get_rag_config()` 120s elsewhere | GraphRAG alone runs on 10s | reported | none found |
| F7 | Cross-encoder blend | `reranking.py:370-400` vs `advanced_rag_optimizer.py:688-708` (no staleness/provenance) | mesh path's `ResultReranker()` ignores `RAGConfig.rerank_weights` | reported | none found |
| F8 | Stale-chunk filter | `rag_service.py:796`, `:1172` | mesh path returns at `:737` before the filter | reported | none found |
| F9 | Embedding model key | `knowledge/search.py:331` caches on `config.llm.embedding_model`, generates with npu_client default | cache key can diverge from model used | reported, unverified | none found |
| F10 | Hybrid weights / top_k | `ssot_constants.py:213-216,769` vs literals in `advanced_rag_optimizer.py:183-186` | same values today, duplicated | reported | fits #18094 |

Single definition (checked): PPR (`ppr.py:57`), community clustering (`community_clusterer.py:35`),
`relations_by_direction` (`knowledge/relations.py:49`).

## Duplicate cross-check (2026-10-09)

Searched open **and** closed issues, 3–6 queries per finding.

| Finding | Verdict | Home |
|---|---|---|
| Graph view absent from chat retrieval | **new child** — #17215 names graph as one view but no task wires it; #17537 Phase 5 points at #17215 | **#18144** (child of #17215, blocked by #18139, #18142) |
| D1 PPR adapter TypeError | **new** (#2057/#2058/#4761 closed, none mention it) | **#18139** (under #17312) |
| D2 `traverse_relations` AttributeError | **new** | **#18140** (under #17312) |
| D3 `/graph-rag` no access filter | **duplicate** — #16665 lists `api/graph_rag.py` | sighting posted on #16665 |
| F1 graph stores | **extends** #17526 (mesh edges, PropertyGraph mirror, routes key space are second originals under its rule) | comment posted on #17526 |
| F2 + F6 + F7 + F8 mesh/graph scoring path bypasses shared config, reranker weights and stale filter | **new**; recurrences of closed #2103 (bypassed reranker weights) and #4721 (stale filter skipped on a path) | **#18141** (under #17312) |
| F3 entity extractors | **duplicate** #13805, #13553 | none |
| F4 entity vocabularies | **duplicate** #13840 | none |
| F5 chunk ↔ node identity | **new** (#2050 closed, earlier MeshSeeder variant) | **#18142** (under #17312) |
| F9 embedding-model cache key | **new** (#17967 is a different embedding bug) | **#18143** (under #17312) |
| F10 hybrid weight literals | **fits** #18094 | comment posted on #18094 |
| Population | **covered** — #17588, #18129, #17537 Phase 2 | none |
