---
tags:
  - research
---

# Research: deterministic code knowledge graph with edge provenance

Status: Phase 1 and Phase 2 complete; scoped to code intelligence and graph retrieval, read at `origin/main` 5a78dd9a75. Defects filed; see Linked issues. #21316 and #21317 were fixed by #21397 (merged 12.11.2026); #21318 is open.

## Source Analysis: an open-source code-to-knowledge-graph tool for coding assistants

### What It Is
The reference work is a Python CLI and assistant integration. It turns a folder of code, docs, configs and media into a queryable graph with three outputs: a JSON graph, an interactive HTML view and a Markdown report. Code is parsed locally with tree-sitter and no LLM is used. Docs and media get an optional LLM "semantic pass". Queries cover a scoped subgraph for a question, the shortest path between two concepts, and an explanation of a single node. It is very actively released (every 1–3 days) and commercially backed.

### Architecture & Key Patterns
- A pipeline of pure stages, `detect → extract → build → cluster → analyze → report → export`, exchanging plain dicts and NetworkX graphs. A test imports every symbol named in the architecture doc, so the doc cannot drift.
- About 38 per-language tree-sitter extractors share one engine, followed by a symbol-resolution pass.
- A single extraction schema (`nodes[id,label,source_file,source_location]`, `edges[source,target,relation,confidence]`) is validated before graph build.
- Edge provenance is an enum, `EXTRACTED > INFERRED > AMBIGUOUS`, with an optional numeric score. A path's confidence is that of its weakest hop.
- Leiden community detection gives LLM-free subsystem labels, high-degree hub nodes, surprising cross-community links and import-cycle detection.
- Git post-commit/checkout hooks rebuild in a detached process. An assistant pre-tool hook steers file reads toward graph queries.

### Notable Implementation Details
- **Grammar-fingerprinted AST cache**: the cache key is the SHA-256 of the file body plus a hash of the installed grammar versions, so grammar upgrades invalidate stale parses automatically.
- **Evidence folding**: when several extractors assert one edge, the strongest tier wins and every witness is retained as an evidence list, sorted weakest first.
- **External stubs**: unresolved import targets become explicit stub nodes rather than dangling edges.
- **Rationale nodes**: `NOTE:` / `WHY:` comments and ADR/RFC citations become graph nodes linked to the code they explain.
- **Root-relative node ids**, so a graph or cache is portable between checkouts.

### Strengths
- Deterministic, local and free for code. Rebuilds are reproducible.
- Provenance is explicit on every edge and every path answer.
- Broad language coverage and many export formats.

### Weaknesses / Limitations
- Very large single modules (several hundred KB each) are hard to audit.
- The graph is a snapshot. It goes stale between rebuilds and needs one graph per checkout or worktree.
- The pre-tool hooks change, and in strict mode block, how an assistant reads files.
- The semantic pass sends document content to an LLM provider.
- Queries are logged to a user cache file by default.
- High open-issue volume relative to maintainer concentration.

### Visible vs Hidden Metrics
- **Visible:** large token-saving claims; memory-benchmark recall and QA numbers; ~40 languages; zero LLM cost for the code graph. All benchmarks are self-reported on the authors' own harness with a single model. Some samples are tiny (n=50, n=6), and the headline benchmark measures conversational memory, not code navigation.
- **Hidden:** coupling to 25 pinned tree-sitter grammars with ABI constraints; daily release churn; per-worktree rebuild operations; hooks that alter agent behaviour; disclosure risk from the semantic pass; auditability of very large modules.
- **Weighing:** for a large monorepo with many concurrent worktrees, its own hook discipline and a no-egress rule for internal content, the hidden costs outweigh installing the tool. The value is in the techniques: provenance enum, evidence folding, grammar-fingerprinted cache, community anchors and rationale nodes.

## AutoBot Comparison: the reference work → AutoBot

Audit base: `origin/main` @ 5a78dd9a75, fetched 10.11.2026.

### Status of the April 2026 adoption plan
All three planned items exist on main, but item A only in part:
- **Community clustering**: `autobot-backend/services/mesh_brain/community_clusterer.py` (`cluster_graph`, `_pick_centroid`) uses NetworkX's built-in Louvain. The Leiden dependency was removed in #10524 because it pinned numpy<2. `get_anchor_neighbors` exists in `mesh_db.py:202`, `mesh_db_adapter.py:59` and `neural_mesh_retriever.py:51`.
- **Tree-sitter code indexing**: `autobot-backend/services/knowledge/code_indexer.py` (#4820) runs two passes and resolves edges through `autobot_shared/code_graph/resolver.py` (#13470). Every edge carries one of three tiers (`resolver.py:343`, `origin: "extracted" | "inferred" | "ambiguous"`). Consumers: `impact_analysis.py`, `codebase_analytics/endpoints/call_graph.py`, `knowledge_code_indexing.py`.
- **Edge-provenance enum on mesh edges (NOT landed)**: no `EdgeOrigin` type exists. `mesh_edges.origin` holds producer names (`"learner"` in `edge_learner.py:266`, `"discoverer"` in `edge_discoverer.py:144`, `"seeder"`), not tiers. `graph_rag_service.py:613-614` defaults any non-tier value to `"inferred"`. Not traced: whether the relations read there ever come from `mesh_edges` or only from the entity graph.

### What We Can Adopt

| # | Technique | AutoBot target | Already-exists audit | Visible benefit | Hidden cost | Verdict | Effort |
|---|---|---|---|---|---|---|---|
| 1 | Cache key includes the installed grammar versions — **done**: fixed by #21397 (merged 12.11.2026) | `code_indexer.py` cache (`_CACHE_VERSION_KEY`, `EXTRACTOR_VERSION = 1` at line 94) | The key is content SHA-256 plus a hand-bumped `EXTRACTOR_VERSION`. `requirements.txt:97-99` has no upper bound on `tree-sitter*`, so a grammar upgrade serves old parses until someone remembers to bump | No stale call graph after a dependency update | One `importlib.metadata` lookup per run | adopt | trivial |
| 2 | Keep every call site as evidence on an edge — **done**: fixed by #21397 (merged 12.11.2026) | `_record_call_edge` (`code_indexer.py:230`) | Deduplicates on `(scope, target_name)` and keeps only the **first** call line, so other call sites are lost | Impact analysis can list every line that calls X | Bigger edge documents in ChromaDB | adopt-with-conditions (cap the list per edge) | moderate |
| 3 | A path's confidence is its weakest hop | `services/knowledge/impact_analysis.py` | Tracks ambiguous/unresolved edges it skipped (lines 21, 87, 129, 155). No grep hit for a per-path tier (`weakest`, `min(`) | One honest confidence per impact answer | None notable | adopt | trivial |
| 4 | `imports` / `inherits` edges in the code graph | `code_indexer.py` + `autobot_shared/code_graph/` | Indexer emits only `kind: "calls"`. Import resolution and cycle detection exist separately in `codebase_analytics/endpoints/dependencies.py` (`_resolve_import`:155, `_find_cycles_dfs`:167), using stdlib `ast` and Python only | Dependency questions answered from the same graph as calls | Must **reuse** the dependencies resolver, not write a second one (twice-defined rule) | adopt-with-conditions | moderate |
| 5 | Rationale nodes: link `#NNNN` issue refs and `NOTE:`/`WHY:` comments to the code they annotate | `code_indexer.py` structural pass | No `rationale`/`NOTE:` handling. AutoBot code is dense with issue refs (e.g. `#13469`, `#13471` in `code_indexer.py` itself) | "Why is this like this?" answered from the graph, with each issue linked to its code | Parsing comments; issue-ref false positives | adopt | moderate |
| 6 | Vue SFC / real TypeScript grammar | `code_indexer.py` (TS goes through the JS grammar, line 416) | `.vue` is neither parsed nor reported in `_NO_GRAMMAR_EXTENSIONS` (`{.pyx,.pxd}`). Not checked: whether `.vue` reaches the indexer at all | The frontend becomes visible to call-graph and impact queries | Two more grammar deps (one version declared once in `constraints/shared.txt`); SFC script-block extraction | adopt-with-conditions | significant |
| 7 | Finish plan item A: a tier on mesh edges | `mesh_brain/mesh_db.py`, `graph_rag_service.py:613` | See status above | Mesh answers carry real provenance instead of a default | A migration of the `origin` meaning; producer name must move to its own column, not be overwritten | adopt (finishes recorded work) | moderate |

**Rejected by hidden metrics:**
- **Installing the tool, or its pre-tool hooks**: one graph per worktree, hooks that change how agents read, and a query log.
- **The LLM semantic pass over docs**: sends internal content to a provider.
- **~40 language grammars**: maintenance and ABI pinning for languages AutoBot doesn't contain.
- **Leiden**: dropped once already (#10524), and Louvain gives the same contract.
- **The multi-format exporters**: AutoBot serves the graph through its own API and UI.

### What We Already Do Better
- **Staleness is explicit**: `GraphProvenance` (`code_indexer.py:115`) records the run that wrote the graph, and "absence means unknown, never fresh". The reference work leaves freshness to hooks and a daemon.
- **Ambiguity is never guessed**: the resolver returns `(None, count)` for 2+ candidates (`resolver.py:330`), and `impact_analysis.py` reports skipped edges instead of dropping them.
- **Unparseable files are reported**: `_HELD_BACK_EXTENSIONS` and the per-extension no-grammar count (#13510) are surfaced, not silently skipped.
- **The graph is a service**: ChromaDB-backed and feeding RAG, impact analysis and the analytics API. No snapshot file to keep fresh per checkout.
- **Clustering needs no extra dependency** (NetworkX Louvain).

### Gaps & Opportunities (by impact)
1. #1 grammar-versioned cache (correctness, trivial). — **done**: fixed by #21397 (merged 12.11.2026)
2. #7 finish the mesh provenance tier (recorded plan, unfinished).
3. #3 weakest-hop confidence (trivial, user-facing honesty).
4. #4 import/inherit edges reusing `dependencies.py`.
5. #2 all call sites as evidence. — **done**: fixed by #21397 (merged 12.11.2026)
6. #5 rationale nodes from issue refs.
7. #6 Vue/TS coverage (largest effort, largest blind spot).

### Specific Code/Files Affected
- `autobot-backend/services/knowledge/code_indexer.py`: items 1, 2, 4, 5, 6.
- `autobot_shared/code_graph/resolver.py`: item 4, with the import resolver moved here from `api/codebase_analytics/endpoints/dependencies.py`.
- `autobot-backend/services/knowledge/impact_analysis.py`: item 3.
- `autobot-backend/services/mesh_brain/mesh_db.py`, `edge_learner.py`, `edge_discoverer.py` and `autobot-backend/services/graph_rag_service.py`, plus a migration: item 7.
- `autobot-backend/requirements.txt`, `constraints/shared.txt`: item 6.

### Other findings
- The name of a studied source appears in 5 files on main (plan doc, two indexes, two changelogs). Recorded as a sighting on #18984, which already owns this defect class.

## Linked issues

- #21316 bug(code-intelligence): CodeIndexer cache ignores tree-sitter grammar versions — a grammar upgrade serves stale parses
- #21317 bug(code-intelligence): call edges keep only the first call site — every later call line is dropped
- #21318 bug(kb-retrieval): mesh edge origin stores the producer, GraphRAG reads it as a confidence tier — unknown values silently become inferred
