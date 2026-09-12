---
tags:
  - research
  - llm-routing
  - semantic-cache
---

# Source Analysis: Signal-Driven LLM Gateway/Router

Gaps and adoption candidates identified here are tracked under umbrella #16524.

## What It Is

An open-source routing and control-plane layer that sits between AI client
applications and a pool of heterogeneous LLM backends. It runs as an Envoy
External-Processing (`ext_proc`) service: Envoy carries the traffic, the
router inspects/extracts request signals and decides which model (or bounded
multi-model plan) handles each request, then Envoy forwards the provider-
shaped request upstream. Clients can speak OpenAI Chat Completions, OpenAI
Responses, or Anthropic Messages; the router translates between client and
backend wire formats. Associated with a large, well-funded open-source LLM
inference-serving project (not named here — see chat reply). ~5.7k GitHub
stars, 936 forks, first commit 2025-08-26, three tagged releases (latest
v0.3, 2026-06-05) despite continuous `main` churn — still pre-1.0 in
practice. Top contributor holds ~479 of all commits vs. ~204 for #2:
concentrated-but-backed ownership typical of a young, sponsor-funded
project.

## Architecture & Key Patterns

- **Polyglot, layered:** Go (router core, ~80% of LOC), Rust via CGo
  (`candle-binding` — embeddings, classifiers, multimodal encoders,
  hallucination checks, MLP-based model selection, run natively instead of
  through a Python inference server), Python (CLI + install tooling),
  TypeScript (operator dashboard).
- **Pipeline separation — signals → projections → decisions → algorithms →
  plugins → model pool.** Each layer answers one question: *what do we know*
  (signals: keyword/metadata/embedding/classifier facts) → *how does
  evidence combine* (projections: partitions, weighted scores, score→band
  mappings) → *which route is eligible* (decisions: boolean rules over
  signals/projections, priority-ordered) → *which candidate or plan*
  (algorithms: fixed-order/semantic-fit/latency/feedback selection, or
  "looper" cascades/panels/multi-round workflows) → *what else should
  happen* (plugins: retrieval, memory, compression, caching, response
  controls, at configurable request/execution/response hooks).
  Deliberately keeps classification reusable across policies and policy
  changeable without touching model selection.
  Docs: `website/docs/overview/signal-driven-decisions.md`.
- **Recipe = policy isolation boundary.** An "entrypoint" maps one or more
  public virtual model names to a "recipe," which owns its own signals,
  decisions, plugins, cache namespace, and routing state. Explicit physical
  model names bypass the whole pipeline (pass-through) — an intentional
  escape hatch for direct selection.
- **Config-as-code:** one canonical YAML (`config/config.yaml`) with schema
  validation (`pkg/configschema`), a model catalog, versioned evaluation
  records tied to specific model+benchmark pairs, and per-model
  pricing/reliability (LB policy, retry, ejection, health checks) declared
  alongside routing — cost and reliability are first-class config, not
  bolted on.
- **Online learning with guardrails:** `router_learning_*` adapts routing
  weights from observed outcomes (cost/latency/quality feedback), gated by
  an explicit "protection policy" against runaway adaptation — plus replay
  and trajectory capture (`router_replay_*`) so a policy change can be
  evaluated against recorded traffic before it ships.
- Admission control, rate limiting, and in-flight concurrency caps live at
  the gateway layer as router-owned protections in front of the backend
  pool (`pkg/admission`, `pkg/ratelimit`, `pkg/inflight`), not left to each
  backend.

## Notable Implementation Details

- **Category-aware semantic cache**, not a single global policy: an exact-
  match L1 (pluggable across in-memory/Redis/Valkey/Qdrant/Milvus) plus a
  hybrid semantic cache that runs a local in-process HNSW index as a fast
  pre-filter before touching the external vector store. Their own published
  benchmark claims this cuts a cache-miss's added latency from ~30ms to
  ~2ms, which lowers the hit-rate break-even for cache profitability from
  15-20% down to 3-5% — letting low-repetition categories be cached
  profitably instead of only high-repetition ones.
- **One unified classifier surface, many swappable backends.** ~15 signal
  families (jailbreak, PII, hallucination [NLI-based + endpoint + windowed
  variants], complexity, domain/category [KB-grounded + embedding-based],
  language, input modality, feedback, fact-check, "reask," preference,
  structure, tool-choice, authz) each resolve through a common dispatch
  layer to a local model (LoRA/ModernBERT via the Rust binding), ONNX,
  OpenVINO, an HTTP/vLLM remote classifier, or an MCP-based classifier —
  operators swap the inference backend per signal without touching policy.
- **Decisions are a rule tree, not an LLM judge.** `pkg/decision/engine.go`
  evaluates boolean/confidence-scored rules over signal+projection outputs
  with explicit handling for an "unknown" (no-match) case — deterministic
  and auditable rather than a second model deciding routing.
- **Compression is a first-class pipeline stage in two flavors:** prompt
  compression (TextRank + TF-IDF + novelty/position scoring to shrink a
  single prompt) and context compression (structural/semantic compression
  of multi-turn history with Redis-backed recovery so a compressed turn can
  be reconstituted) — both configurable plugins, not ad hoc truncation.
- **Shadow dispatch** lets a candidate route or model receive a mirrored
  copy of live traffic for comparison without affecting the served
  response — a built-in canary mechanism for routing changes.

## Strengths

- Clean separation of workload/policy/pool concerns makes the routing
  policy itself reviewable and testable independent of model inventory
  changes.
- Protocol-agnostic at the client boundary (OpenAI Chat/Responses,
  Anthropic Messages) with an explicit backend translation matrix.
- Hot-path inference (embeddings, classification) runs in Rust via a native
  binding rather than shelling out to a Python process — keeps per-request
  classification overhead low.
- Every capability (cache backend, vector store, rate-limit provider) is an
  interface with multiple pluggable implementations, so operators aren't
  locked into one infra choice.
- Built-in replay/trajectory/shadow-dispatch tooling makes "test this
  policy change against real traffic before shipping" a supported workflow
  rather than a bespoke one.

## Weaknesses / Limitations

- Surface area is very large relative to what "a router" implies — the
  classification package alone is ~150 files; onboarding and review cost is
  substantial, and a single contributor holds the large majority of commit
  history.
- Three tagged releases since inception; operators building on `main` are
  tracking a moving target, and the YAML config shape has changed across
  the documented `v0.1`→`v0.3` announcements.
- 539 open issues against ~5.7k stars is a high ratio — could mean healthy
  engagement or could mean triage lag; not disambiguated from the outside.
- Hard dependency on Envoy as the data-plane proxy — any adopter not
  already running Envoy inherits a new infra component purely to get the
  router in the request path.
- All headline benchmark numbers (cache latency/hit-rate economics,
  MMLU-Pro accuracy/latency/token deltas for reasoning routing) are
  self-published by the project's own team; no independent reproduction
  found during this pass.

## Visible vs Hidden Metrics

- **Visible:** self-reported cache-miss latency cut (~30ms → ~2ms via local
  HNSW pre-filter); self-reported cache break-even drop (15-20% → 3-5% hit
  rate) enabling caching on previously-uncacheable low-repetition
  categories; self-reported MMLU-Pro reasoning-routing gains (+10.2pp
  accuracy, -47.1% latency, -48.5% tokens vs. always-direct inference).
  None of these are independently verified; all come from the project's own
  papers/blog.
- **Hidden:** an Envoy dependency for any non-Envoy shop; a very large
  multi-language codebase to audit/patch if self-hosted rather than
  consumed as a managed service; concentrated bus-factor risk on the
  dominant contributor; a pre-1.0 config surface that has already changed
  shape twice; operational load of running and tuning a *second* stateful
  system (the semantic cache's vector index) alongside whatever vector
  store the adopter already runs for RAG.
- **Weighing:** for a team already running Envoy at the edge and already
  operating a vector store, the hidden costs shrink substantially — the
  pattern (not the whole system) is the reusable asset. For a team with
  neither, adopting the *whole* gateway to get category-aware caching or
  signal-driven routing would mean inheriting Envoy, a second vector
  index, and a pre-1.0 dependency just to reach one or two techniques;
  the hidden costs there outweigh adopting the project wholesale, though
  individual patterns (category-aware cache policy, signal/decision
  separation, rule-tree routing) remain worth evaluating standalone.

## AutoBot Comparison: Reference System → AutoBot

Audited via four parallel read-only passes over `autobot-backend/`,
`autobot_shared/`, and `autobot-infrastructure/shared/config/`. Every item
below cites the files/greps actually checked.

### What We Can Adopt

1. **Finish wiring the already-built extractive prompt compressor.**
   `autobot-backend/llm_shared/optimization/prompt_compressor.py:47`
   (`PromptCompressor`) and `integration.py:44`
   (`OptimizedLLMMiddleware`) exist, are tested, and have **zero callers**
   outside their own package/tests (confirmed by repo-wide grep for
   `OptimizedLLMMiddleware`/`TokenOptimizer(`). The reference's prompt-
   compression stage (TextRank + TF-IDF + novelty/position scoring) is a
   more principled version of the same idea.
   **Visible benefit:** lower prompt token cost/latency without truncation.
   **Hidden cost:** low — this is finishing written code, not new design;
   the existing filler-phrase/word-overlap heuristic could mis-trim
   dense technical text, so it needs eval against a few real transcripts
   before going live.
   **Verdict:** adopt (wire the existing compressor first; upgrading its
   scoring toward TextRank/TF-IDF is a reasonable but separate follow-on).
   **Effort:** trivial (wiring) → moderate (better scoring).

2. **Enforce the per-provider concurrency cap that already has a field and
   a half-built pool.** `ProviderConfig.max_concurrent_requests`
   (`autobot-backend/llm_multi_provider.py:67`,
   `autobot-backend/llm_shared/models.py:81`) is read by nothing — no
   semaphore consumes it. `autobot-backend/utils/ollama_connection_pool.py:35`
   (`OllamaConnectionPool`, `asyncio.Semaphore` + bounded queue) implements
   exactly this for one backend and is also unused outside its own test.
   The reference's `pkg/admission` is the same idea as a first-class
   pipeline stage.
   **Visible benefit:** stops one backend being overwhelmed by bursty
   concurrent in-flight requests — a distinct failure mode from the
   requests-per-minute limiting AutoBot already enforces elsewhere.
   **Hidden cost:** low — wiring existing code; the real cost is picking
   defensible concurrency limits without production traffic data to
   calibrate against.
   **Verdict:** adopt.
   **Effort:** trivial → moderate.

3. **Category-aware tuning for the semantic cache.** AutoBot's semantic
   cache config is a global singleton — one similarity threshold (0.95)
   and one TTL (3600s) for every query
   (`autobot_shared/ssot_config.py:858-942`,
   `autobot-backend/services/semantic_query_cache.py:45-60`). A working
   per-type precedent already exists elsewhere in the codebase —
   `autobot-backend/utils/advanced_cache_manager.py:171-230`
   (`CacheStrategy` enum, distinct TTL/size per data type) — but isn't
   applied to the LLM/semantic cache. The reference's category-aware
   policy (tighter threshold/shorter TTL for volatile categories, looser
   for high-repetition ones) is the same shape of idea already proven
   inside this codebase, just not extended here.
   **Visible benefit:** reference's own (self-reported, unverified) numbers
   claim this drops the cache-profitability break-even from 15-20% to
   3-5% hit rate, covering currently-uncacheable volatile-but-frequent
   categories.
   **Hidden cost:** needs a category signal *before* the cache lookup;
   reusing the existing `WorkflowClassifier`
   (`autobot-backend/workflow_classifier.py:205`) avoids building a new
   classifier but couples cache behavior to a classifier built for a
   different purpose. More config surface on `cache_management.py`'s
   admin API.
   **Verdict:** adopt-with-conditions — only if `WorkflowClassifier`'s
   existing categories are reused rather than adding a cache-only
   classifier.
   **Effort:** moderate.

4. **A common classifier-dispatch registry for safety signals.** PII
   (`autobot-backend/a2a/pii_pipeline.py:393` `get_pii_pipeline()`),
   prompt injection (`get_prompt_injection_detector()`), the content
   firewall (`content_firewall.py:340` `get_content_firewall()`), and the
   security-risk judge (`judges/security_risk_judge.py`) are each an
   independent singleton with its own calling convention — confirmed no
   shared registry exists (repo "registry" hits are the LLM provider/tool/
   skills registries, unrelated). The reference dispatches ~15 signal
   families through one registry with a swappable backend per signal.
   **Visible benefit:** one place to add a new safety signal or swap a
   detector's backend, instead of a new bespoke module each time.
   **Hidden cost:** high coordination cost — touches every existing call
   site in `security/`, `a2a/`, `judges/` for a maintainability win, not a
   runtime one (the underlying checks already work).
   **Verdict:** adopt-with-conditions — only worth the refactor cost if
   done *while* closing gaps #1-#2 below (PII-in-chat-path, blanket
   injection guard), so the registry earns its cost by fixing real gaps
   rather than refactoring for its own sake.
   **Effort:** significant.

5. **NLI/entailment-style grounding check for RAG answers.** Grepped
   `entailment|NLI|cross-encoder|grounded|faithfulness` repo-wide: only
   RAG-reranking cross-encoders and prompt-level "grounded context"
   phrasing exist. `autobot-backend/rlm/evaluator.py:23-55` does LLM-
   self-eval (no source-grounding check) and `rlm/rag_refiner.py:27-42`
   checks retrieval *sufficiency* pre-generation, not the generated
   answer's factual grounding after the fact. The reference's hallucination
   detector checks the response against source context post-hoc.
   **Visible benefit:** catches fabricated claims independent of the
   generating model's own (unreliable) self-assessment — specifically
   valuable where a source context exists to check against.
   **Hidden cost:** a new small model in the serving path (needs an
   OpenVINO/NPU-compatible cross-encoder to fit AutoBot's hardware
   constraints) and a policy decision on what to do with a flagged
   answer (block/warn/reroute) — detection alone doesn't close the loop.
   **Verdict:** adopt-with-conditions — scope to RAG answers specifically
   (`autobot-backend/knowledge/`, `services/rag_service.py`), where a
   source context actually exists to check against; not a general-chat
   feature.
   **Effort:** significant.

### What We Already Do Better

- **Conversation-history compression via LLM summarization**
  (`autobot-backend/chat_history/context_overflow.py:608`
  `ContextOverflowProtection`, wired into the live chat path at
  `api/chat.py:836`) preserves meaning by summarizing at 90% of context
  budget rather than extractively trimming sentences. For multi-turn chat
  continuity — where losing exact wording can break a later reference —
  this is a defensible fidelity-over-cost tradeoff against the reference's
  TextRank/TF-IDF extractive approach, at the cost of one extra LLM call
  per summarization.
- **Per-provider circuit breaking is already wired and tested**
  (`autobot-backend/llm_shared/base_provider.py:206-266`, checked
  fail-fast before every call). The reference expresses the equivalent
  capability declaratively per-model in Envoy outlier-detection config
  (`consecutive_5xx`, `base_ejection_time`, `max_ejection_percent` in
  `config/config.yaml`) rather than as a Python state machine — different
  style, not a capability gap either direction.

### Gaps & Opportunities

Prioritized by risk/impact, each traceable to an adopt item above where
one exists:

1. **PII scanning never runs on the main chat path.** The only wired PII
   detector (`a2a/pii_pipeline.py`) scrubs Agent-to-Agent task payloads;
   `autobot-backend/api/chat.py` has no PII/injection call at all (checked
   directly). This is the highest-priority gap — it's a security posture
   hole, not a missing nice-to-have.
2. **No blanket prompt-injection guard on raw user chat input.** The
   detector (`security/prompt_injection_detector.py`) is wired to specific
   features (screen analysis, KB transcript, advanced-workflow intent) and
   to *tool-fetched* content via `ContentFirewall`, but not to the raw
   user message on every chat turn.
3. **No unified safety-signal registry** → adopt item #4.
4. **No post-hoc hallucination/grounding check for RAG answers** → adopt
   item #5.
5. **No per-category semantic-cache policy** → adopt item #3.
6. **No enforced per-backend concurrency admission control** → adopt item
   #2.
7. **Extractive prompt compression is written but unwired** → adopt item
   #1.
8. **Duplicate semantic-cache implementations, one dead.**
   `autobot-backend/llm_shared/semantic_cache.py` (numpy-cosine,
   threshold 0.95) has no caller outside `llm_shared/__init__.py` and its
   own test; the live path uses a second, unrelated implementation
   (`services/semantic_query_cache.py`, ChromaDB-backed). This wasn't a
   reference-system gap — it surfaced during the audit as a consolidation
   defect (dead code shadowing the real implementation) and is flagged
   here rather than dropped.

### Specific Code/Files Affected

| File | Change |
| --- | --- |
| `llm_shared/optimization/integration.py`, `services/llm_service.py` | Wire `OptimizedLLMMiddleware` into the live completion path |
| `llm_shared/models.py:81`, `llm_shared/base_provider.py` | Add a semaphore that actually reads `max_concurrent_requests` |
| `utils/ollama_connection_pool.py`, `llm_shared/adapters/ollama_adapter.py` | Wire the existing pool into the Ollama adapter |
| `autobot_shared/ssot_config.py` (`CacheL2Config`), `services/semantic_query_cache.py` | Add per-category threshold/TTL, keyed by `WorkflowClassifier` category |
| `api/chat.py` | Add a PII/injection check on the raw user message before the LLM call |
| `security/` (new registry module) | Route `pii_pipeline`, `content_firewall`, `prompt_injection_detector`, `security_risk_judge` through one dispatcher |
| `knowledge/`, `services/rag_service.py` | Add a post-generation grounding check against retrieved source context |
| `llm_shared/semantic_cache.py` vs `services/semantic_query_cache.py` | Consolidate — delete the dead one once confirmed unused, or merge its cosine fallback into the live path |
