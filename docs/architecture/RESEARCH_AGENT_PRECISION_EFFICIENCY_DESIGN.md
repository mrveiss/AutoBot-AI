# Research Agent: Precision & Efficiency Architecture

> **Issue:** [#12621](https://github.com/mrveiss/AutoBot-AI/issues/12621) (umbrella) · children #12622–#12625
> **Status:** Research & Design
> **Author:** mrveiss
> **Last Updated:** 2026-07-26
> **Related:** Knowledge Base (`knowledge/` — Facts/Relations/Collections/Versioning) · `services/claim_verifier.py` · autoresearch M2/M3 · `deep-research` skill

---

## Executive Summary

AutoBot can already **fetch** and **summarize** web content, but each research run starts cold, the synthesized answer is an un-cited template string, and findings land only as flat KB documents — never as verified, reusable, cited **facts**. This document specifies an architecture that makes information gathering **more efficient** (reuse accumulated knowledge, prune low-value search branches, stop at saturation) and **more precise** (every claim traced to sources, contradictions surfaced, staleness tracked) — for **any topic**.

**Key insight:** the required infrastructure already exists but is _disconnected_. Critically, the **Knowledge Base already provides a fact store with provenance chains, verification fields, dedup, versioning, temporal validity, relations, and collections** (`knowledge/facts.py`, `relations.py`, `collections.py`). Research findings must integrate **into the KB as facts** — not into a parallel graph. The leapfrog is to connect the fetcher, source registry, verifier, and KB into one bounded loop, and add the missing LLM reasoning layer.

This is **not** an OSINT/recon capability. It borrows structural patterns from investigation frameworks (Maltego, SpiderFoot, Recon-ng, Sherlock) but targets general-purpose research on arbitrary topics.

**Owner decisions incorporated:** first consumer = **dedicated `/research` API endpoint**; knowledge **integrates with the existing KB** (its collections/scoping govern persistence); first PR **bundles Phase 0 + grounded synthesis**; web-research facts are **quarantined in a dedicated `research` collection until corroborated**, then promoted into the general KB; the response exposes **both inline caveats and a structured `contradictions[]`/confidence block**.

---

## Table of Contents

1. [Goals & Non-Goals](#1-goals--non-goals)
2. [Current State & Gap](#2-current-state--gap)
3. [Architecture Overview](#3-architecture-overview)
4. [Component Design](#4-component-design)
5. [Data Model — KB-Native](#5-data-model--kb-native)
6. [Reuse Map (Canonical Sources)](#6-reuse-map-canonical-sources)
7. [How Each Goal Is Met](#7-how-each-goal-is-met)
8. [Design Decisions & Alternatives](#8-design-decisions--alternatives)
9. [Phasing](#9-phasing)
10. [Testing](#10-testing)
11. [Risks & Mitigations](#11-risks--mitigations)
12. [Open Questions for Owner](#12-open-questions-for-owner)

---

## 1. Goals & Non-Goals

### Goals

- **Precision:** every synthesized statement is grounded in ≥1 cited source; conflicting sources are surfaced with confidence, not silently resolved; facts carry temporal validity.
- **Efficiency:** overlapping research reuses prior KB facts; the agent pursues only high-value sub-questions; a run stops when new searches stop yielding new facts.
- **Topic-agnostic:** science, engineering, market, historical, general-knowledge — no domain hardcoding.
- **KB-integrated:** findings become first-class KB facts, retrievable by chat/RAG like any other knowledge; scoping follows the KB's existing model.
- **Canonical:** extend existing modules; introduce one new coordinator + one API surface; no `_v2`/`Enhanced` variants.

### Non-Goals

- OSINT / recon / offensive-security workflows.
- A parallel knowledge store — the KB is the system of record; the Redis memory graph stays dev/session memory.
- A visual graph UI (later, separate).
- Replacing the `deep-research` skill or `AutoResearchAgent` (ML-experiment scope).

---

## 2. Current State & Gap

Audited during design (file:line evidence):

| Capability | Where it lives today | State |
|---|---|---|
| Web fetch (browser, anti-detection, CAPTCHA) | `agents/web_researcher.py:366-753` | ✅ Ahead of donor tools |
| Plain-HTTP crawl + markdown extract | `knowledge/connectors/web_crawler.py` | ✅ Exists (no JS render) |
| Credential-gated source registry + fallback | `agent_loop/search/registry.py:63` | ✅ Clean; code-class providers |
| **KB fact store w/ provenance + verification** | `knowledge/facts.py:831 store_fact`, `:383-405` provenance defaults (Issue #1252) | ✅ **Exists — the claim store** |
| **KB relations / collections / versioning / temporal** | `knowledge/relations.py`, `collections.py`, `versioning.py`, `temporal_search.py` | ✅ Exists |
| KB semantic search (reuse check) | `knowledge/search.py:194` | ✅ Exists |
| Correlation primitive | `services/autoresearch/osint_engine.py:425` | ⚠️ Keyword-only, single sweep |
| Claim verification | `services/claim_verifier.py:365` | ⚠️ 2-source arbitration, not multi-source |
| Iterative research loop | `services/autoresearch/auto_research_agent.py:587` | ⚠️ Fixed query, rule-based, ML-scoped |
| Synthesis | `agents/web_researcher.py:1175` | ❌ Template string, no citations |
| Research findings → **KB facts** | web research calls `add_document` only | ❌ Lands as flat docs, **not verified facts** |
| LLM-driven next-step selection | — | ❌ Absent |

**The gap in one sentence:** research fetches into flat KB _documents_ and summarizes with a template; it never lands **verified, cited facts** (though the KB supports them), and it never decides what to ask next.

---

## 3. Architecture Overview

A single coordinator drives a bounded loop; **the KB is the shared, persistent state**.

```text
   POST /research ──►  ┌────────────────────────────────────────────┐
   {question}         │            ResearchOrchestrator              │
                      │  (services/research/orchestrator.py — NEW)   │
                      └───────────────┬─────────────────────────────┘
                                      │
        ┌───────────────┬─────────────┼───────────────┬────────────────────┐
        ▼               ▼             ▼                ▼                    ▼
  ┌───────────┐  ┌────────────┐ ┌────────────┐ ┌──────────────┐   ┌─────────────┐
  │ Planner   │  │  Source    │ │  Fetch /   │ │ Corroborator │   │ Synthesizer │
  │ (LLM      │  │  Router    │ │  Extract   │ │ (multi-src   │   │ (grounded,  │
  │ sub-Qs +  │  │ (topic→    │ │ claims)    │ │ confidence + │   │  cited from │
  │ skip-known│  │  providers)│ │            │ │ contradiction│   │  KB facts)  │
  │ + prune)  │  │            │ │            │ │              │   │             │
  └─────┬─────┘  └─────┬──────┘ └─────┬──────┘ └──────┬───────┘   └──────┬──────┘
        │              │              │               │                  │
        │  KB.search   │              │ add_document  │ store_fact +      │ reads KB
        │  (reuse)     │              │ (source)      │ relations         │ facts
        └──────────────┴──────┬───────┴───────────────┴──────────────────┘
                              ▼
              ┌───────────────────────────────────────────────┐
              │              KNOWLEDGE BASE (existing)          │
              │  Facts (provenance chain, confidence, verify)  │
              │  Documents (sources) · Relations · Collections │
              │  Versioning · Temporal validity · Categories   │
              └───────────────────────────────────────────────┘
```

**Control flow (one `/research` request):**

1. **Plan** — Planner decomposes the question into sub-questions; **`KB.search` first** and drops sub-questions already answered by facts above a confidence threshold (E1); LLM prunes low-value branches (E2).
2. **Route** — Source Router picks providers per sub-question topic (E4).
3. **Fetch + Extract** — reuse `web_researcher`/`web_crawler`; store each retrieved page as a KB **document** (source of record); LLM extracts atomic **claims** from it.
4. **Land** — each claim → `store_fact(content, metadata=…)` with provenance chain pointing at its source document; dedup via `unique_key`; link fact→source and fact→concept via Relations (P1, E1).
5. **Corroborate** — for each material claim, gather independent sources; raise confidence on agreement; on disagreement, add a `contradicts` relation + set the fact's verification/`requires_human_review` field (P2).
6. **Decide** — Planner inspects new facts; loop to (1) if high-value follow-ups remain and budget allows; else stop on **saturation** (E3).
7. **Synthesize** — LLM answer where **every statement cites the KB fact(s) + source document(s)** backing it; contradictions reported, not resolved silently (P1, P2).

---

## 4. Component Design

### 4.1 ResearchOrchestrator (NEW — `services/research/orchestrator.py`)

The one new top-level module. Composes existing services; owns the loop, the budget (max depth, max sources, token ceiling), and saturation detection (reuse `AutoResearchAgent._should_continue` plateau logic — extract to a shared helper, do not duplicate).

> **Canonical note:** neither `WebResearcher` (fetch-focused, 1.4k lines) nor `AutoResearchAgent` (ML-experiment-scoped) is the right home — verified by reading both. A new coordinator that _composes_ them is justified and is **not** a variant of either.

### 4.2 API surface (NEW — `services/research/routes.py`, mounted like `autoresearch/routes.py`)

`POST /research` → `{question, options}`; returns `{answer, citations[], facts[], contradictions[], confidence}`. Streaming variant later. This is the **first consumer** (owner decision); chat agent and `deep-research` skill wire in afterward against the same orchestrator.

### 4.3 Planner

LLM decomposes question → sub-question DAG; scores branches by expected value; prunes before spending searches. Before emitting a sub-question, calls `KB.search` and skips ones already answered above threshold. Input: question + retrieved KB context. Output: ordered sub-questions for this round.

### 4.4 Source Router

Maps a sub-question's inferred topic to providers via the existing `SearchProviderRegistry` + config-declared sources (§4.6). Default general web when no specialization matches. Registry credential-gating and graceful fallback unchanged.

### 4.5 Fetch + Claim Extractor

Reuse `web_researcher` (browser path for JS/Cloudflare) and `web_crawler` (fast HTTP) — router chooses per source. Store each page via `KB.add_document` (the source record). An LLM step then extracts atomic claims `{statement, source_doc_id, confidence_prior}`. **No claim invented that isn't supported by the fetched text** (post-check).

### 4.6 Corroborator (extends `services/claim_verifier.py`)

Upgrades 2-source arbitration to **N-independent-source** verification:

- Gather ≥K independent sources for a **material** claim (Planner tags materiality — cost control).
- Agreement → raise fact confidence (function of source count + independence).
- Disagreement → `contradicts` relation + set the fact's verification field / `requires_human_review` (reuse existing flag).
- Add a refutation prompt ("what evidence would contradict this?") — port the pattern the `deep-research` skill already uses.

### 4.7 Source Definitions (data-driven, extends registry)

Simple `URL-template + response-parse` sources declared in config/JSON so non-code contributors add authoritative sources (docs, encyclopedic, news, domain APIs). Complex-auth sources stay Python classes. Router prefers specialized sources per topic.

### 4.8 Synthesizer (replaces the template summary)

LLM synthesis constrained to KB facts retrieved for the question: every output sentence references the fact ID(s) + source doc(s); statements with no supporting fact are omitted or flagged unknown; contradictions presented with both sides + confidence. Post-check that every cited fact ID exists (anti-hallucinated-citation).

---

## 5. Data Model — KB-Native

**No new store, no new memory-graph types.** Research knowledge maps onto existing KB primitives:

| Concept | KB primitive | Notes |
|---|---|---|
| **Claim** | **Fact** (`store_fact`) | provenance chain + verification fields already built in (Issue #1252); `confidence` in metadata; `unique_key` for dedup-by-merge |
| **Source** | **Document** (`add_document`) | already how web results land; fact.provenance → source doc id; `source_type="web_research"`, `source_connector_id` |
| **Topic/Concept** | **Category / Tag / Collection** | groups facts by subject; enables topic-scoped reuse |
| `supports` / `cites` | **Relation** (fact→document) | RelationsMixin |
| `contradicts` | **Relation** (fact↔fact) + fact verification flag | drives P2 surfacing |
| Freshness / staleness | **Versioning + temporal_search** | re-verify stale facts; supersede, don't delete (no-data-loss) |
| Per-user vs shared scope | **Collections** | scoping follows KB's existing collection model (resolves owner Q on persistence) |

Dedup-by-merge: a repeated claim with the same `unique_key` updates the existing fact (append provenance, bump version) rather than creating a duplicate — the KB becomes the deduplicated accumulator.

---

## 6. Reuse Map (Canonical Sources)

| Need | Reuse (do not recreate) |
|---|---|
| Store & dedup findings as verified facts | KB `knowledge/facts.py` (`store_fact`, provenance, `unique_key`) |
| Sources of record | KB `knowledge/documents.py` (`add_document`) |
| Fact/source/topic relationships | KB `knowledge/relations.py`, `collections.py`, `categories.py` |
| Freshness / supersede | KB `knowledge/versioning.py`, `temporal_search.py` |
| Reuse-before-search | KB `knowledge/search.py` (`search`) |
| Fetch hard / fast pages | `agents/web_researcher.py` / `knowledge/connectors/web_crawler.py` |
| Pick/fallback providers | `agent_loop/search/registry.py` |
| Verify claims | `services/claim_verifier.py` (extend to N-source) |
| Loop stop / plateau | `services/autoresearch/auto_research_agent.py` (extract helper) |

**New code, minimized:** `services/research/orchestrator.py` + `routes.py` + Planner/Router/Synthesizer helpers under `services/research/`. Everything else is composition.

---

## 7. How Each Goal Is Met

| Goal | Mechanism | Component |
|---|---|---|
| **Precision** — grounded answers | every sentence cites Fact→Source | §4.8 Synthesizer |
| **Precision** — no hidden disagreement | `contradicts` relation + confidence surfaced | §4.6 Corroborator |
| **Precision** — freshness | KB versioning + temporal; re-verify stale | §5 |
| **Efficiency** — no re-research | `KB.search` before searching the web | §4.3 Planner + §5 |
| **Efficiency** — no wasted branches | LLM prunes low-value sub-questions | §4.3 Planner |
| **Efficiency** — right source first | topic→provider routing | §4.4 / §4.7 |
| **Efficiency** — stop at saturation | reused plateau detection | §4.1 Orchestrator |

---

## 8. Design Decisions & Alternatives

**D1 — Store: KB facts vs new Redis memory-graph types.**
Chosen: **KB**. Owner requirement ("must integrate with our knowledge base") + audit showing the KB already has facts with provenance, verification, dedup, versioning, temporal, relations, collections. A parallel memory-graph namespace would fork knowledge and duplicate all of that. The Redis memory graph stays dev/session memory. **Verdict: KB is the system of record.**

**D2 — One coordinator vs extend WebResearcher.**
Chosen: new coordinator composing existing parts. `WebResearcher` is fetch-scoped; overloading it bloats a 1.4k-line class. A composition root, not a variant.

**D3 — LLM synthesis vs keep template summary.**
Chosen: LLM synthesis constrained to KB facts. The template is the precision bottleneck. _Hidden cost:_ token spend + hallucination risk — mitigated by citing only existing fact IDs + post-check.

**D4 — Verify everything vs material claims only.**
Verifying every fragment against N sources is costly. Verify only **material** claims (those the synthesis will assert). Planner tags materiality.

**D5 — Cascade cost control (SpiderFoot's inherited weakness).**
Hard budget: max depth, max sources/run, token ceiling, plateau stop. `log()` what a bound truncates so coverage limits are visible, never silent.

---

## 9. Phasing

- **Phase 0 (first PR) — Findings→KB facts + grounded synthesis** _(bundled, per owner)_:
  wire fetch/extract → `store_fact` (into the quarantined `research` collection) with provenance + `add_document` sources; replace the template summary with cited LLM synthesis over those facts; expose `POST /research` returning inline caveats **and** a structured `contradictions[]`/confidence block. First merge is a **visibly better, cited answer** that also accumulates reusable facts. Facts stay in `research` (not general RAG) until Phase 1 promotes them.

- **Phase 1 — Corroboration + promotion gate:** extend `claim_verifier` to N-source; add `contradicts` relations + confidence; **promote facts from `research` → general KB collection once corroborated / above threshold** (the quarantine release valve).
- **Phase 2 — Planner loop:** LLM sub-question decomposition, `KB.search` skip-when-known, branch pruning, saturation stop.
- **Phase 3 — Source routing + data-driven sources:** topic routing + config-declared sources.

Each phase is independently mergeable and valuable.

> **Ordering note:** quarantine-until-verified means Phase 0 facts are visible only to `/research` synthesis, not general chat/RAG. Broad KB visibility begins at Phase 1's promotion gate — keeping the main KB's precision intact while still shipping value in the first PR.

---

## 10. Testing

- Unit: claim extraction (prose→fact, no unsupported claims), `unique_key` dedup-merge, contradiction-relation creation, plateau stop, planner skip-when-known.
- Integration: `/research` question → KB facts populated w/ provenance → cited synthesis; a second overlapping question reuses KB facts (assert fewer web fetches).
- Precision assertions: every synthesized sentence maps to ≥1 fact + source; injected contradictory sources surface a conflict, not a silent pick; every cited fact ID exists.
- Reuse the `autoresearch` eval harness/scorers where applicable.

---

## 11. Risks & Mitigations

- **Extraction noise / bad facts** → constrain extraction to fetched text; quality-gate before `store_fact`; provenance always attached.
- **KB pollution / dedup errors** → `unique_key` normalization; `source_type="web_research"` for filterable provenance; versioning + temporal invalidation over deletion.
- **Token cost** → materiality-gated verification; hard budgets; saturation stop.
- **Hallucinated citations** → synthesis references only existing fact IDs; post-check.
- **Confidence miscalibration** → confidence = f(independent-source count); never assert single-source claims as verified.

---

## 12. Resolved Decisions

All owner decisions closed — the design is ready to decompose into an umbrella + child issues.

1. ~~Answer surface~~ → **dedicated `/research` API endpoint first.**
2. ~~Persistence scope~~ → **integrate with the KB; Collections model governs scoping.**
3. ~~Confidence display~~ → **both** — inline caveats in the answer **and** a structured `contradictions[]`/confidence block.
4. ~~First-PR scope~~ → **bundle Phase 0 + grounded synthesis.**
5. ~~Fact promotion~~ → **quarantine in a dedicated `research` collection until corroborated**, then promote to general KB (gate lands in Phase 1).
