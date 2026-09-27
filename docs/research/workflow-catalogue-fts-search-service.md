# Source Analysis: a community catalogue of low-code automation workflow definitions with a search service

*Reference work studied 2026-09-27. Source identity is deliberately omitted — see the research
skill's anonymization rule. Everything below is an analysis of fetched content treated as data.*

## What It Is

A very widely starred (tens of thousands of stars, thousands of forks) community collection of
~4,300 workflow definition files for a third-party low-code automation engine, wrapped in a small
Python search service. The engineering content is not the workflows — it is the **catalogue layer**:
a FastAPI + SQLite/FTS5 indexer that turns a directory of ~29,000-node JSON documents into a
sub-100 ms searchable corpus, plus a build step that flattens the same index into static JSON so the
whole thing can be served from a static-pages host with no backend at all. The project's own headline
claim is that this replaced a previous approach of pre-generating one HTML page per workflow
(~71 MB of output) with a ~2 MB index and a dynamic query path.

Maturity: **popular but decelerating**. Last substantive code change ~7 months before the study
date; only a README touch since; 41 open issues. MIT licensed. Multi-arch Docker images, five CI
workflows, a non-root container with a healthcheck — the delivery packaging is more mature than the
code it packages.

## Architecture & Key Patterns

- **Two-tier read model.** One SQLite file is the query engine; the JSON files on disk stay the
  system of record. Nothing is ever written back to the source documents.
- **Derived-metadata indexing.** A single `analyze_workflow_file` pass parses each JSON document and
  derives what the document does not state: trigger type, an integration set, a complexity bucket,
  and a generated natural-language description when the document carries none.
- **FTS5 external-content table.** `workflows_fts` is declared `content=workflows,
  content_rowid=id`, so the index stores no duplicate text; three `AFTER INSERT/DELETE/UPDATE`
  triggers keep it in sync. Filter columns (trigger type, complexity, active, node count) get
  ordinary B-tree indexes and are applied as a `WHERE` conjunction on top of the `MATCH`.
- **Content-hash change detection.** Re-indexing hashes each file and skips unchanged ones, so a
  re-run over 4,300 files touches only what moved.
- **Static-export escape hatch.** A build script reads the same SQLite database and emits
  `search-index.json` plus small `stats`/`categories`/`integrations` sidecars; a vanilla-JS client
  does the searching in the browser. Same data, two delivery modes, one generator.
- **Stack:** Python 3.11, FastAPI, SQLite FTS5 (WAL, `synchronous=NORMAL`, memory temp store),
  vanilla JS front end, Docker, static pages hosting.

## Notable Implementation Details

- **The derived description.** Rather than leaving 4,000 records with empty descriptions, it
  synthesises one from the trigger type and the integration set. Cheap, deterministic, no model
  call — and it materially improves full-text recall because the synthesised sentence contains the
  words a searcher actually types.
- **A service-name normalisation table.** Raw node type identifiers are mapped through an explicit
  dictionary to human service names, which is what makes "365 integrations" a countable facet rather
  than a pile of vendor-specific type strings.
- **On-the-fly diagram generation.** A `/diagram` endpoint walks the node graph and emits Mermaid
  source at request time instead of storing rendered images — no asset pipeline, no staleness.
- **External-content FTS to avoid double storage.** The right call for a corpus where the text is
  already in a table, and the pattern most projects get wrong by copying text into the index.
- **Three-pass URL decoding in the filename validator**, to defeat nested percent-encoded traversal
  before pattern matching.

## Strengths

- The **indexer/serve/export split** is clean: one analysis pass feeds both a live API and a static
  build, so the static site can never drift from the API's view of the data.
- **Honest performance engineering for the size.** FTS5 + WAL + narrow indexed facets is the correct
  answer for a few thousand documents; no vector database was reached for where lexical search wins.
- **Idempotent, hash-gated re-indexing** makes the catalogue cheap to keep current.
- **Delivery maturity** — multi-arch images, non-root user, healthcheck, vulnerability scanning
  config, and a static fallback that costs nothing to host.

## Weaknesses / Limitations

Ordered by how much they would matter to an adopter, not by how visible they are.

| # | Finding | Evidence | Severity |
|---|---|---|---|
| 1 | **Raw user input is passed straight into an FTS5 `MATCH` expression.** Not injectable (it is a bound parameter), but FTS5 `MATCH` takes a *query language*, so an ordinary search containing `"`, `:`, `*` or a bare `AND`/`NEAR` raises `OperationalError`. | search endpoint → `search_workflows(query=q)` → `WHERE workflows_fts MATCH ?` | High — ordinary input returns 500 |
| 2 | **Internal exception text is returned to the client.** The search, detail and download handlers all end in `except Exception as e: raise HTTPException(500, detail=f"...{str(e)}")`, so finding #1 leaks SQLite internals to any caller. | three handlers + a global exception handler | High |
| 3 | **`INSERT OR REPLACE` silently bypasses the FTS delete trigger.** SQLite fires delete triggers on a REPLACE conflict *only* when `recursive_triggers` is on; the code never enables it. The surrogate key is `AUTOINCREMENT`, so each re-index of a changed file allocates a **new** rowid, the `AFTER INSERT` trigger adds a fresh index row, and the old one is never removed. | schema + `index_all_workflows` | Medium — orphans accumulate; the inner join hides them from result sets, but the index grows unbounded and BM25 corpus statistics are computed over stale documents, so ranking degrades over time. Mechanism: high confidence. Practical magnitude: unmeasured (only changed files are re-indexed). |
| 4 | **Detail lookup is an O(directories) filesystem scan per request** — it iterates all 188 category directories probing for the file, because the indexer stores the basename but never the relative path it found it at. | `get_workflow_detail` | Medium |
| 5 | **~200 KB of unwired code.** Eleven modules under `src/` (an assistant, an analytics engine, user management, an integration hub, a performance monitor, community features, an "enhanced" API) plus a **parallel Node.js re-implementation** of the same server. Neither entrypoint imports any of it — the running app imports exactly one module. | `api_server.py` imports only the database module; `run.py` imports stdlib only; Dockerfile runs `run.py` | Medium — a maintenance tax disguised as features |
| 6 | **Unrelated product committed into the repo.** A complete, separate Next.js/Supabase product (its own strategy docs, config, `src/`, prompts) lives in a top-level directory of a workflow-catalogue repo. | top-level directory listing | Medium — repo hygiene |
| 7 | **Defence-in-depth written as dead code.** The filename validator ends with an allow-list regex (`^[a-zA-Z0-9_\-]+\.json$`) that already rejects every one of the ~17 deny-list patterns checked above it. The deny list is unreachable, and the allow-list simultaneously rejects legitimate filenames containing dots or spaces. | `validate_filename` | Low — correct outcome, misleading code |
| 8 | **Rate limiting is a per-process in-memory dict keyed by client IP**, with no key eviction and no effect across workers; it is also applied to the detail/download endpoints but **not** to the search endpoint, which is the expensive one. | `check_rate_limit` and its call sites | Low–Medium |
| 9 | **The 2.2 MB static index is serialised with `indent=2`**, shipping pretty-printing whitespace to every browser. | index generator | Low |
| 10 | Deprecated `@app.on_event("startup")`, a bare `except:`, `LIMIT/OFFSET` built by f-string (values are integer-validated upstream, so not exploitable today), and two near-duplicate ~55 KB front-end HTML files. | assorted | Low |

## Visible vs Hidden Metrics

**Visible (all self-reported; none independently verified in this study):**
~4,300 workflows · 365 integrations · 29,445 nodes · "<100 ms search" · "<50 MB memory" ·
"700× smaller than v1" · "100× faster search with FTS5" · "100% import success rate" ·
tens of thousands of stars.

The believable ones are the *architectural* claims: 700× smaller and 100× faster are what you get
moving from pre-rendered HTML-per-record to an FTS5 index, and that ratio does not need trusting —
it follows from the change. The operational numbers (<100 ms, <50 MB) are plausible for a 4,300-row
SQLite corpus and unverified here.

**Hidden (the costs an adopter inherits):**

- **A search path that 500s on ordinary punctuation** (#1+#2) — the advertised "<100 ms search" is
  measured on queries that parse. Nothing in the advertised numbers covers the ones that do not.
- **An index that rots quietly** (#3). No error, no alert; ranking quality decays with churn. This is
  the worst kind of hidden cost: invisible until someone asks why results got worse.
- **A 6:1 dead-to-live code ratio** (#5). Every reader must first determine which of twelve modules
  is real. Every fork inherits all of it.
- **Star count is a popularity metric for the *data*, not a quality signal for the *code*.** The
  workflows are what 56k people starred; the service is incidental to that number. Reading stars as
  evidence about the search service is a category error.
- **Deceleration** — no substantive code change in ~7 months, 41 open issues. An adopter of the code
  is adopting a fork, not a dependency.

**Weighing:** the *pattern* is sound and the hidden costs attach almost entirely to the
*implementation*. Copying the architecture — derive metadata once, index it in FTS5 with external
content, export the same index statically — is cheap and the visible wins are real and mechanically
explained. Copying the code would import ten defects and 200 KB of dead weight for a service that is
~800 lines when written correctly. Verdict: **learn the shape, write the code**.

## Two lessons that transfer regardless of adoption

1. **External-content FTS5 + `INSERT OR REPLACE` is a trap** (#3). Any AutoBot table pairing an FTS5
   external-content index with upsert-by-natural-key has the same silent-orphan bug unless it either
   enables `recursive_triggers`, uses `ON CONFLICT ... DO UPDATE` (which fires the update trigger),
   or makes the natural key the rowid.
2. **Security controls must be reachable to be controls** (#7). An unreachable deny-list reads as
   hardening in review and enforces nothing; the audit question is "which line actually rejects
   this input?", not "is there a check?".

---

---

# AutoBot Comparison — scoped to: workflow builder, workflows-as-templates, workflow marketplace

*User-steered focus, 2026-09-27. Every claim below cites a file read during the audit.*

## Headline

A workflow marketplace is **mostly already built** — export, import, validation, sharing and clone
all exist and are versioned. What is missing is a *public discovery surface* for workflows, because
the only catalogue we have is typed to plugins. Conversely, **the reference work's ~4,300 workflow
documents are not adoptable as templates** — three independent blockers, one of them legal. The
part of that corpus worth having is its *statistics*, not its contents.

## What AutoBot Already Has (audited, not assumed)

| Capability | Where | State |
|---|---|---|
| Visual builder + canvas | `autobot-frontend/src/views/WorkflowBuilderView.vue`, `components/workflow/WorkflowCanvas.vue`, `composables/useWorkflowBuilder.ts` | Built |
| DAG execution | `autobot-backend/orchestration/workflow_executor.py`, `dag_executor.py` (`NodeType` enum at `dag_executor.py:54`) | Built |
| Native template library | `autobot-backend/workflow_templates/` — 18 templates across 6 category modules (analysis, community, development, research, security, sysadmin) | Built |
| Template model | `workflow_templates/types.py:87` — `id, name, description, category, complexity, steps, estimated_duration_minutes, agents_involved, tags, variables, required_secrets` | Built |
| Template gallery UI | `components/workflow/WorkflowTemplateGallery.vue` — search box + category filter chips | Built |
| Template API | `/api/templates/templates`, `/search`, `/categories`, `/stats` via `composables/useWorkflowTemplates.ts` | Built |
| **Export / import / validate** | `api/workflow_export.py:59,96,123` + `services/workflow_serializer.py` — `SCHEMA_VERSION = "1.0"`, forward-compatible (unknown keys preserved), explicit `validate_import` with per-step issue list | Built |
| **Share / list / clone** | `api/workflow_export.py:162,222,244` — share-id based private sharing with clone | Built |
| Plugin marketplace | `api/marketplace.py` — Redis-cached catalog, categories, downloads/rating sort, install/uninstall | Built |
| **Remote catalogue sources** | `api/marketplace_sources.py:130` — add a third-party catalogue by URL, fetch + validate the document, scheme validation (`_validate_url_scheme`) | Built |

That last row matters: the federation model the reference work does not have, we already do.

## The three blockers on adopting the ~4,300 workflows as templates

**1. Schema incompatibility — structural, not cosmetic.**
Those documents are `{nodes, connections}` graphs typed to a third-party engine's node vocabulary
(the reference work's own indexer normalises ~365 vendor-specific node type strings through a
hand-written mapping table). AutoBot's interchange format is `{schema_version: "1.0", steps: [...]}`
with `agents_involved` and an automation mode (`services/workflow_serializer.py:38,295`), executed
against our own `NodeType` enum. There is no shared vocabulary. Only generic control flow —
trigger, HTTP request, conditional, loop, code, wait — has any AutoBot counterpart; the other ~350
node types are connectors to services we have no node for. A translator would therefore convert a
small fraction of workflows and silently mangle the rest.
**Effort to do properly: significant. Value: low** — we would be building an importer for an engine
we do not run.

**2. Licensing/provenance — blocking, and a decision for the owner, not for me.**
The repository is MIT, but MIT grants only what the grantor holds. By that repository's own
description the workflows were *collected from the upstream vendor's own site* — i.e. a community
template gallery where each submission carries the submitter's and the platform's terms. Restating
them inside an AutoBot marketplace is redistribution of third-party content under a licence the
collector may not have had standing to grant. This is not mitigated by attribution or by the files
being public.
**I am not able to resolve this from the repository — it needs a human decision.** Recommendation:
do not ingest the documents.

**3. Unverified executability.**
4,343 untested documents are 4,343 unverified claims, each needing credentials for services we do
not integrate. Our templates carry `required_secrets` (`types.py:108`) precisely so a template
declares its needs — a bulk import would populate that field with guesses.

## What *is* adoptable — and the licensing-clean part is the most valuable

### A. Connector demand ranking from corpus statistics — **adopt**
Count node-type frequency across the corpus and you get an evidence-ranked list of which
integrations people actually automate. That answers "which connector do we build next?" with data
instead of intuition.
- *Already-exists audit:* no frequency/demand analysis exists — `workflow_templates/` is 18
  hand-authored templates; nothing derives priorities from external usage.
- *Licensing:* clean. Statistics about a corpus are not a derivative of it; nothing is redistributed.
- *Visible benefit:* a ranked connector roadmap. *Hidden cost:* near zero — a one-off script, no
  runtime surface, no dependency, nothing to maintain.
- *Effort:* trivial. **Verdict: adopt.** This is the single highest value-per-cost item in this study.

### B. Two missing facets on the template model — **adopt**
The reference work facets on `trigger_type` and a derived `integrations` set. Our `WorkflowTemplate`
has `category`, `complexity` and `tags` but **neither** (`workflow_templates/types.py:98-108`).
- *Already-exists audit:* read the full field list at `types.py:98-108` — confirmed absent.
- *Visible benefit:* "show me everything webhook-triggered that touches Slack" becomes answerable.
- *Hidden cost:* a schema addition to a model already persisted and exported — needs a
  `SCHEMA_VERSION` story. The serializer preserves unknown keys forward-compatibly
  (`workflow_serializer.py:9`), so additive fields are cheap; removing one later is not.
- *Effort:* moderate. **Verdict: adopt-with-conditions** — add as optional/derived, do not bump
  `SCHEMA_VERSION` for an additive field.

### C. Derived description when the author supplies none — **adopt, but only with the marketplace**
The reference work synthesises a description from trigger type + integration set when the document
has none. Deterministic, no model call, and it materially raises full-text recall because the
synthesised sentence contains the words people search for.
- *Already-exists audit:* our 18 templates are hand-written and all carry descriptions, so the
  problem does not exist *today*. It appears the moment users publish their own workflows.
- *Visible benefit:* user-published workflows stay findable without nagging authors.
- *Hidden cost:* a synthesised description can read as authoritative; it must be visibly marked
  as generated or it will be mistaken for the author's intent.
- *Effort:* trivial. **Verdict: adopt when the publish path lands, not before.**

### D. FTS5 for the catalogue — **adopt-with-conditions, and the timing is the whole point**
- *Already-exists audit:* `grep -rniE "fts5|VIRTUAL TABLE"` across all `.py`/`.sql`/`.ts` returns
  **one comment** (`api/database_mcp.py:335`, about `dbstat`). AutoBot uses no FTS5 anywhere.
- Current catalogue search is an in-Python substring scan in three places:
  `api/marketplace.py:339-348`, `workflow_templates/manager.py:72-85`, and the gallery's client-side
  filter. All three are `q.lower() in field.lower()` — no ranking, no stemming, no prefix match.
- *But:* the built-in plugin catalogue is **5 entries** and the template library is **18**. At that
  size FTS5 is unambiguously over-engineering, and saying otherwise would be cargo-culting the
  reference work's numbers onto our data.
- *Visible benefit:* ranked, sub-100 ms search that stays flat as the catalogue grows.
- *Hidden cost:* a second storage engine in the catalogue path (we are Redis-cached JSON today), an
  index to keep in sync, and the upsert trap in the next section. Also: FTS5 `MATCH` takes a query
  *language* — adopting it without an input sanitiser reproduces the reference work's #1 defect.
- **Verdict: adopt-with-conditions — the condition is a public workflow marketplace existing.** The
  schema decision is expensive to retrofit, so it should be made *when the marketplace is designed*,
  not bolted on after the data grows.

### E. Static catalogue export — **adopt-with-conditions**
One generator feeding both a live API and a static JSON index is how the reference work serves a
backend-free deployment.
- *Already-exists audit:* no static catalogue export exists; `grep` for `search.index|search_index`
  hits vector/FAISS builders (`utils/faiss_ivfpq_builder.py`, `knowledge/index.py`), not a catalogue.
- *Visible benefit:* an air-gapped or offline AutoBot install could still browse the marketplace.
- *Hidden cost:* a published static index is a disclosure surface — it must be generated from the
  *public* catalogue only, never from a tenant's private or shared workflows. Given
  `api/workflow_export.py` share-ids are private-by-link, this is a real leak risk if wired naively.
- *Effort:* moderate. **Verdict: adopt-with-conditions** — only if offline install is a goal;
  gate strictly on published-public state.

### F. On-the-fly Mermaid rendering — **rejected, already have it**
Generating diagram source per request rather than storing images. We already do this:
`code_intelligence/doc_generation/markdown_generator.py`, `api/analytics_architecture.py`,
`api/schemas_analytics.py`. Moves to "already do better" — ours is wired into doc generation.

## What We Already Do Better

| Area | Reference work | AutoBot | Why ours wins |
|---|---|---|---|
| Path containment | Deny-list of ~17 patterns rendered unreachable by an allow-list regex below it | `autobot_shared/security/path_validator.py:33,138,145` — allow-listed roots + `resolve().relative_to(root)` | Structural containment beats pattern-matching; ours cannot be bypassed by an encoding we failed to imagine |
| Rate limiting | Per-process dict keyed by IP, no eviction, absent on the expensive endpoint | `llm_shared/cross_worker_rate_limiter.py` — Redis Lua token bucket shared across workers, graceful all-allow on Redis outage | Correct across workers; theirs is decorative behind >1 worker |
| Error responses | `detail=f"...{str(e)}"` in every handler | `utils/error_catalog.py` + `utils/catalog_http_exceptions.py` — structured `{message, code, category, retry, retry_after}` | Machine-readable, no internals by default |
| Change detection | MD5, boolean skip | `models/knowledge_import_tracking.py:61,151` — SHA256, `needs_reimport()`, failure recording, per-file status and statistics | Stronger hash, richer state, observable |
| Lexical ranking | FTS5/BM25 (better *mechanism* than ours) | `knowledge/search_components/bm25.py` + `advanced_rag_optimizer.py:475` — BM25 Okapi, landed in #10600 | We have the *algorithm*; see the gap below on the *index* |
| Catalogue federation | Single hard-coded catalogue | `api/marketplace_sources.py:130` — add remote catalogues by URL with fetch + schema + scheme validation | They have no federation at all |
| Interchange format | None — files are the format | `services/workflow_serializer.py:38` — explicit `SCHEMA_VERSION`, `validate_import` with per-step diagnostics, forward-compatible unknown-key preservation | A real versioned contract |
| Repo hygiene | ~200 KB unwired `src/`, a parallel Node server, an unrelated product committed at top level | — | Stated for contrast only |

## Gaps & Opportunities, prioritised

1. **No public discovery surface for workflows.** Sharing is private-link-only
   (`api/workflow_export.py:162`); the only catalogue is plugin-typed (`CatalogCategory` at
   `api/marketplace.py:35-47` = example/analytics/observability/integration/agent/tool, entries keyed
   by `plugin_name`). **This is the actual marketplace gap** — and it is a smaller job than it looks,
   because install/uninstall, remote sources, Redis caching, categories and rating/download sort all
   already exist and would be reused rather than rebuilt.
2. **BM25 rebuilds its index on every query.** `advanced_rag_optimizer.py:455-472` — `_build_bm25_scorer`
   tokenises the entire fact corpus and recomputes document frequencies *per query* (its own docstring
   says "computed once per query"). Fine now, O(corpus) per query as facts grow. This is the precise
   delta where a persistent inverted index wins, and it is a real finding independent of any adoption.
3. **Two hybrid-search implementations.** `utils/hybrid_search.py:133 HybridSearchEngine` is reachable
   only from `utils/system_validator.py:894` — a validator, not the production path — while the live
   RAG path uses the `advanced_rag_optimizer` BM25 route. Per *consolidate, never fork*, one of these
   is unwired machinery. Belongs under the open umbrella **#10603** ("wire built-but-disconnected
   machinery"), not a new issue.
4. **Marketplace OpenAPI contract overstates its search.** `api/marketplace.py:314` documents the
   parameter as "Full-text search across name, description, tags"; the implementation at lines 339-348
   is a substring `in` test. The generated TypeScript client inherits that description. Low severity,
   trivially fixable, but it is a contract saying something the code does not do.
5. **11 raw-exception-detail sites remain.** `detail=f"...{str(e)}"` at `api/knowledge_chroma.py:177,228,306,393`,
   `api/chat.py:2762`, `api/analytics.py:1237`, `api/diagnostics.py:98`, `api/memory.py:408`,
   `api/mcp_registry.py:1047`, `llc/api/agent_api.py:525`, `llc/api/companies.py:1678` — despite
   **#5692** ("py/stack-trace-exposure in 14 remaining locations") being **closed**. Either a
   regression or these were never in that issue's scope; I did not determine which, and it should be
   re-checked rather than assumed. Per *one defect, one fix*, these are witnesses to #5692's scope,
   not eleven new issues.

## Specific Files That Would Change

| File | Change |
|---|---|
| `autobot-backend/api/marketplace.py` | Generalise from plugin-only: an `entry_kind` (plugin \| workflow) or a sibling `/api/marketplace/workflows` reusing `_resolve_catalog`, `_get_catalog`, install and source resolution |
| `autobot-backend/api/workflow_export.py` | Add a publish-to-public transition beside `share` — the share-id path stays private; publishing is a distinct, explicit state |
| `autobot-backend/workflow_templates/types.py` | Optional `trigger_type` and derived `integrations` on `WorkflowTemplate` |
| `autobot-backend/workflow_templates/manager.py` | `search_templates` (lines 72-85) gains ranking; substring scan stays correct but stops being the only option |
| `autobot-backend/services/workflow_serializer.py` | No change — additive fields are already forward-compatible (line 9); resist bumping `SCHEMA_VERSION` |
| `autobot-frontend/src/components/workflow/WorkflowTemplateGallery.vue` | Trigger/integration filter chips beside the existing category chips |
| `autobot-frontend/src/composables/useWorkflowTemplates.ts` | New marketplace-backed source alongside `/api/templates/templates` |
| *(new, one-off)* connector-demand analysis script | Reads a corpus, emits node-type frequencies; never ships the corpus |

## If we adopt FTS5 later — the trap to write down now

AutoBot has **9** `INSERT OR REPLACE` sites and **0** uses of `recursive_triggers`
(`grep -rn "recursive_triggers" --include=*.py` → 0). Today that is harmless: with no FTS5 external-content
index anywhere, there is no trigger to skip. The moment a catalogue pairs an FTS5 external-content
index with `INSERT OR REPLACE` on a natural key, SQLite will drop the old row **without firing the
delete trigger**, and orphaned index entries accumulate silently. Use `ON CONFLICT ... DO UPDATE`,
or make the natural key the rowid, or enable `recursive_triggers` — and decide which *before* the
schema ships.

## Recommended order

1. **Connector demand ranking** (trivial, licensing-clean, immediately decision-useful).
2. **Workflow marketplace on the existing plumbing** — the gap is discovery, not machinery.
3. **Template facets** (trigger type, integrations) — cheap, additive, unblocks better filtering.
4. **FTS5 + derived descriptions** — at marketplace design time, not before.
5. **Do not ingest the third-party corpus** pending an owner decision on provenance.

---

## Owner decision, 2026-09-27

**Do not copy the pipelines.** We build our own templates, and only the ones valuable to our users.
This resolves blocker 2 (provenance) by removing it: nothing from the reference corpus is ingested
or redistributed. The corpus is used **only** as a demand signal — node-type frequency tells us
which connectors and which template subjects are worth authoring natively. Adoptable **A** is
therefore not just the cheapest item, it is the *only* sanctioned use of the corpus, and its output
feeds a native authoring backlog rather than an importer.

Consequences:
- The schema translator (blocker 1) is **not** to be built — there is nothing to translate.
- `workflow_templates/` grows by hand-authored, executable, credential-declaring templates.
- The marketplace hosts **our** templates plus user-published workflows, never mirrored content.

## Issue & milestone coverage of this study's findings (audited 2026-09-27)

Repo state: 1,557 open issues; 9 milestones (v0.9.0–v0.16.0 + Backlog); 315 open issues (20%) carry
no milestone.

| # | Finding | Existing issue | Milestone |
|---|---|---|---|
| G1 | No public discovery surface for workflows (the marketplace gap) | **#17590** umbrella (+#17591, #17592) | v0.13.0 |
| G2 | BM25 scorer rebuilt over the full corpus per query | #11064 (open) — re-scope comment posted | v0.12.0 |
| G3 | `HybridSearchEngine` reachable only from a validator | **#17599** (child of #10603) | v0.12.0 |
| G4 | Marketplace OpenAPI documents "full-text search", implements substring | **#17600** | v0.12.0 |
| G5 | 11 raw `detail=f"...{str(e)}"` sites | **#17601** (refs closed #5692) | v0.12.0 |
| A | Connector demand ranking from corpus statistics | **#17597** | v0.13.0 |
| B | `trigger_type` / `integrations` facets on `WorkflowTemplate` | **#17593** | v0.13.0 |
| C | Derived description for authorless published workflows | **#17594** | v0.13.0 |
| D | FTS5 for the catalogue | **#17595** | v0.13.0 |
| E | Static/offline catalogue export | **#17596** | v0.13.0 |

**All 10 findings are now filed and milestoned** (2026-09-27). Native sub-issue links: #17590 owns
#17591-#17598; #17599 is a child of #10603. Dependency edges: #17594←#17592, #17595←#17591,
#17596←#17591, #17598←#17597. Task 8 (#17598) is the native re-authoring track — owner decision:
rewrite valuable pipelines for our platform, never port them.

### Correction to this study's G2, and a question about #11064

#11064 states that BM25 IDF/avgdl "are computed over the ~20-doc query-local candidate set instead
of corpus statistics". Against current `main` that premise does not hold:
`advanced_rag_optimizer.py:862-868` binds `all_facts = await self.kb.get_all_facts()` — the whole
corpus from Redis — and passes it unchanged into `_perform_keyword_search` → `_build_bm25_scorer`
(line 479). IDF is therefore corpus-wide already.

The real cost at that call site is the opposite of what the issue describes: **a full-corpus Redis
fetch plus full-corpus tokenisation on every query**. Whether #11064 was accurate when filed and
has since been overtaken (e.g. by #10600 landing), or was mistaken from the start, **I did not
determine** — it needs a read of the code as it stood at filing, not an assumption. Either way
#11064 should be re-scoped or closed with evidence rather than implemented as written.

---

## Second owner decision, 2026-09-27 — a converter, scoped apart from the library

The first decision ("do not copy the pipelines, rewrite them for our platform") governs **what we
ship**. A second requirement followed: a tool that converts workflows from any other platform into
our format. These are not in conflict once the input is distinguished:

| | Curated template library (#17598) | Import tool (#17602) |
|---|---|---|
| Input | our own authoring | the **user's own** workflows |
| Volume | selected subjects | one at a time, user-initiated |
| Provenance | ours | the user's |
| Review | authored and tested by us | human review of every conversion |

Bulk-importing a third-party corpus stays out of scope. Letting a user bring their own work across
is migration, and it lowers our switching cost. #17598 was amended so the tree does not contradict
itself.

**The governing constraint on the converter**, recorded in #17604: *a conversion that silently
drops or approximates what it could not map is worse than one that fails loudly.* A half-converted
workflow that looks complete will be trusted, run, and produce wrong results. Every node gets one
of three outcomes — mapped, approximated, unmapped — and unmapped is a normal result, not an error
path.

Two security constraints fell out of the design and are filed as `priority: high`:
- **#17606** — source documents carry credential references and sometimes values; neither may
  enter AutoBot. Converted workflows declare `required_secrets` and hold nothing.
- **#17607** — most source platforms have a code node carrying arbitrary JS/Python. Converting one
  into an executable step turns "import a file" into "execute code from an untrusted document".
  Code nodes are quarantined; promotion out of quarantine is a separate audited action.

### Issue tree filed for this decision

| Issue | Title | Milestone |
|---|---|---|
| **#17602** | Umbrella: import workflows from other platforms | v0.13.0 |
| #17603 | Converter framework — adapter registry + canonical IR | v0.13.0 |
| #17604 | Node-mapping registry, unmapped as first-class (← #17603) | v0.13.0 |
| #17605 | Fidelity report + pre-import preview (← #17604) | v0.13.0 |
| #17606 | Credentials never carried across (← #17603) | v0.13.0 |
| #17607 | Quarantine foreign code nodes (← #17603) | v0.13.0 |
