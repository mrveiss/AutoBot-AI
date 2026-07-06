# Content Reach Capability — Design Spec

- **Issue:** [#10932](https://github.com/mrveiss/AutoBot-AI/issues/10932)
- **Date:** 2026-07-05
- **Author:** mrveiss
- **Status:** Approved (brainstorming)
- **Source:** Research of [Agent Reach](https://github.com/Panniantong/Agent-Reach)

## 1. Problem

AutoBot agents cannot reach external web/social content. Researching Agent Reach
confirmed the gap: AutoBot has **no** web-wide search, YouTube caption extraction,
Reddit/social reading, or readable web-page fetch. It only has (a) local vector/NPU
search over its own KB and (b) raw Playwright automation.

AutoBot already owns *superior infrastructure* for exactly this shape of problem —
`FallbackChainManager` (primary→fallback model chains), `CircuitBreaker`
(CLOSED/OPEN/HALF_OPEN per service), the unified `system_health` probe registry, and
`source_attribution`. This design adds the **missing capability** by reusing that
infrastructure one layer down: for *content sources* instead of *models*.

## 2. Constraints (decided in brainstorming)

| Decision | Choice |
|---|---|
| Implementation | Native async Python (no CLI subprocessing; sync libs via `asyncio.to_thread`) |
| Cost | Zero-cost / local-first only (no paid APIs) |
| Social access | AutoBot's existing Playwright `research_browser_manager` as a rendering backend |
| Agent surface | Core Python service exposed as **agent tools**, consumed by `agent_loop`/research |

## 3. Architecture

Mirror of the LLM provider/fallback stack, for content:

```
autobot-backend/content_reach/
├── base.py            # ContentBackend ABC; ContentRequest / ContentResult dataclasses
├── chain.py           # ContentSourceChain (mirrors FallbackChain) + env-driven reorder
├── registry.py        # ContentSourceRegistry: source→chain map + chain execution
├── health.py          # register_health_probe(KnownProbes.CONTENT_REACH) — the `doctor` analog
├── sources/
│   ├── web_search.py  # ddgs (DuckDuckGo) ▸ s.jina.ai ▸ BrowserBackend
│   ├── web_page.py    # httpx + trafilatura ▸ r.jina.ai ▸ BrowserBackend
│   ├── youtube.py     # yt-dlp caption extract (asyncio.to_thread — sync lib)
│   ├── reddit.py      # old.reddit .json ▸ HN Algolia ▸ BrowserBackend
│   └── social.py      # BrowserBackend only (Twitter/IG via research_browser_manager)
└── backends/
    └── browser.py     # universal last-resort: delegates to get_research_browser_manager()
```

### 3.1 Reuse (canonical-source discipline)

| Existing module | How it's reused |
|---|---|
| `llm_shared/fallback_chain.py` | `ContentSourceChain` is a direct structural analog (ordered primary+fallbacks, env override). |
| `circuit_breaker.py` | `CircuitBreakerManager` guards every backend call. |
| `source_attribution.py` | Every `ContentResult` passes through `track_source(...)`; new `SourceType` values added. |
| `research_browser_manager.py` | `BrowserBackend` delegates to `get_research_browser_manager().research_url()`. |
| `api/system_health.py` | Health probe registered under `KnownProbes.CONTENT_REACH`; surfaced at `/api/system/health`. |
| `provider_registry.py` (pattern) | 30s-TTL cached liveness probe before dispatch. |

## 4. Components

Each is single-purpose and independently unit-testable.

### 4.1 `ContentBackend` (ABC) — `base.py`
```
name: str
source_type: SourceType
async def probe() -> bool          # REAL liveness (Agent Reach's core idea), not "installed"
async def fetch(req: ContentRequest) -> ContentResult
```
`ContentRequest`: `query`/`url`, `source`, `limit`, `options`.
`ContentResult`: `success`, `text`, `structured`, `url`, `backend_used`, `reliability`,
`source_type`, `metadata`. A failed backend raises `BackendError`; empty-but-ok returns
`success=True, text=""`.

### 4.2 `ContentSourceChain` — `chain.py`
Ordered `[primary, *fallbacks]` of `ContentBackend`. Env override
`AUTOBOT_CONTENT_CHAIN_<SOURCE>=backend1,backend2` reorders without code change — the
property that makes the system resilient to backend rot (yt-dlp blockades, etc.).
Direct analog of `FallbackChain._load_env_chains`.

### 4.3 `ContentSourceRegistry` — `registry.py`
`async def fetch(source_key, request) -> ContentResult`:
1. Resolve chain for `source_key`.
2. For each backend: check cached probe (30s TTL) → skip if dead.
3. Guard with `CircuitBreakerManager.get_breaker(backend.name)`.
4. `await backend.fetch(req)`; on **any** failure (timeout/5xx/parse/empty-error/CB-open)
   advance to next backend.
5. First success → `track_source(...)` → return. All failed → structured
   "no backend succeeded" result (not an exception).

### 4.4 `BrowserBackend` — `backends/browser.py`
Thin adapter over `get_research_browser_manager().research_url(conversation_id, url)`.
The universal fallback that makes social/JS-heavy sources work locally at zero API cost.
Reuses the manager's existing MHTML fallback and CAPTCHA detection.

### 4.5 Health probe — `health.py`
Registers `KnownProbes.CONTENT_REACH`; reports per-source/per-backend live status by
running cached probes. This is AutoBot's `agent-reach doctor` equivalent, surfaced via
`/api/system/health` and consumable by frontend `useProbeBackedHealth`.

### 4.6 Agent tools
`content_search`, `content_fetch_url`, `content_fetch_youtube`, `content_fetch_reddit`
registered in the agent tool registry; call the registry and return `ContentResult`.

## 5. Data flow

```
agent tool call
  → ContentSourceRegistry.fetch(source, req)
  → chain: probe → circuit-breaker → backend.fetch → (fail? next backend)
  → ContentResult(text, structured, url, backend_used, reliability)
  → track_source()
  → returned to agent (with provenance)
```

## 6. Error handling & attribution

- Fallback triggers on **any** backend failure — not just quota (fixes the narrowness of
  the LLM `model_fallback_coordinator`, which only catches `RateLimitError`).
- Circuit breaker prevents hammering a dead backend across requests.
- New `SourceType` values: `YOUTUBE`, `REDDIT`, `WEB_PAGE`, `SOCIAL`.
- Degraded/empty ≠ exception: registry returns a structured result the agent can reason
  about and cite.

## 7. Dependencies to add

- `ddgs` (DuckDuckGo search, no key)
- `trafilatura` (readable article extraction)
- `yt-dlp` (caption extraction; sync → `asyncio.to_thread`)

All free/local. Jina (`s.jina.ai`/`r.jina.ai`) and Reddit/HN are keyless HTTP via existing
`httpx`. Pinned in the appropriate `requirements-*.txt` per
[[ci_backend_image_cpu_only_vllm_optional]] conventions.

## 8. Testing

- Per-backend unit tests with mocked `httpx`/`yt-dlp` transport.
- Registry tests: chain traversal, CB tripping, probe-cache TTL, all-fail path.
- One network-marked integration test per source.
- `doctor`-style smoke listing source→backend health.

## 9. Decomposition (umbrella #10932)

1. **Core foundation** (this spec + `base`/`chain`/`registry`/`health` + `SourceType`) — everything depends on it.
2. Web search · 3. Web page · 4. YouTube · 5. Reddit/HN · 6. Browser-backed social.
7. Agent tools + wire into agent_loop/research.
8. *(optional)* Frontend doctor/status panel.

Tasks 2–6 parallelize after Task 1.

## 10. Non-goals

- Paid search APIs (Exa/Tavily) — excluded by zero-cost constraint.
- Cookie/credentialed social scraping — deferred; browser rendering covers best-effort.
- Content writing/posting — read-only capability only.
