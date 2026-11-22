---
tags:
  - research
---

# Research: agent web-data API — fetch waterfall, browser egress and local-only mode

Status: Phase 1 and Phase 2 complete. The scope is the web-research and browser-worker fetch path and web → KB ingest, read at `origin/main` 210d58354c. It covers only what is new compared with [[adaptive-scraping-and-element-relocation]], which already covers the SSRF guard, untrusted-content fencing and the per-domain circuit breaker. Defects and gaps filed; see Linked issues.

## Source Analysis: an open-core web-data API for LLM agents

### What It Is
The reference work is a web-data service for agents. It offers search (web search plus full page content), scrape (URL → markdown, HTML, JSON or screenshot), interact (scrape, then drive the page), crawl, map (URL discovery ranked by relevance to a query), batch scrape, document parsing, an autonomous gathering agent, and change monitoring. It ships SDKs in many languages, an MCP server and a CLI. It is open-core: the hosted service adds a proprietary stealth/proxy fetcher, a search index and paid data providers. The server is AGPL-3.0. It is very mature and changes daily.

### Architecture & Key Patterns
- **A monorepo of services:** a TypeScript API and workers, a Playwright microservice, a Go HTML→markdown service, a Postgres-backed job queue, Redis, RabbitMQ and an optional FoundationDB. A Rust single-binary "local" edition serves the same API with no database or queue.
- **Engine waterfall.** A scrape builds a fallback list of engines: plain fetch, Playwright, the hosted stealth fetcher, plus PDF, document, image and cached-page engines. It tries each in turn until the markdown passes a success check, and otherwise fails with a no-engines-left error.
- **Deterministic experiment buckets.** `sha256(scrapeId:experiment)` maps each request to a fixed fraction, which gates alternative retry strategies in the waterfall.
- **Async jobs** for crawl and batch: the caller gets a job id and polls it.

### Notable Implementation Details
- **Local edition's egress model.** The server binds loopback and refuses private and localhost targets unless explicitly allowed. A non-loopback bind requires a token plus an allowed-Host list. Link-local and cloud-metadata addresses are refused in every mode, after redirects and DNS resolution. The headless browser runs behind a loopback proxy that applies the same rule to every connection it opens: redirects, subresources, scripts and WebSockets. A public-only mode is recommended for agents that read untrusted pages, because hidden instructions in a page can steer an agent at an internal URL.
- **A labelled cloud hand-off.** The local edition hands search and blocked pages to the hosted service by default, but a single switch turns that off. Results the cloud fetched are labelled as such, and a page nobody could fetch is returned as `blocked` with a reason.
- **Relevance-ranked site map** for agent-driven discovery.

### Strengths
- The broadest feature surface in its category, reachable from agents through MCP, SDKs and a CLI.
- The local edition's per-connection browser egress check is the most complete SSRF treatment seen in this class of tool.
- An honest self-hosting guide: it states that the default deployment is unauthenticated, has no persistent volumes, and is not a production architecture.

### Weaknesses / Limitations
- **The reliability headline is a cloud feature.** Coverage and latency claims come from the hosted stealth fetcher. A self-hosted copy gets Playwright plus plain fetch.
- **A heavy self-host:** 6–7 stateful services, no volumes, unauthenticated by default.
- **AGPL** on the server.
- **The local edition phones home by default:** search and blocked pages go to the hosted service with an install id unless switched off.
- **Tagged releases lag a fast-moving main** (the last tag was months before the read).

### Visible vs Hidden Metrics
- **Visible (self-reported):** very high web coverage, low P95 latency, a huge star count, hundreds of data providers. All of these describe the hosted service, not self-host.
- **Hidden:** operating four stateful stores; the AGPL obligation; capabilities that keep moving into the paid cloud; outbound traffic by default; drift between tags and main.
- **Weighing:** for a self-hosted platform that already has a fetch waterfall, an SSRF guard and a browser worker, the *patterns* are worth more than the software.

## AutoBot Comparison

### What We Can Adopt

| # | Candidate | AutoBot target | Already-exists audit | Visible benefit | Hidden cost | Verdict | Effort |
|---|---|---|---|---|---|---|---|
| 1 | Check every browser connection (subresources, redirects, WebSockets), not just the first URL | `autobot-browser-worker/playwright-server.js`, `autobot-backend/services/browser_url_guard.py` | Only the top-level URL is admitted (`browser_url_guard.py`). `/navigate` calls `page.goto` directly (`playwright-server.js:236`). There is no `.route(` or request interception anywhere in the browser worker or backend. Already filed as #16562 (redirect/DNS); the subresource and WebSocket scope was added there as a witness comment. | Closes SSRF from any public page the agent opens | Per-request resolve + guard latency; the admin browser's fleet exceptions must keep working | **adopt**, within #16562 | moderate |
| 2 | Site map ranked by relevance to a query | `autobot-backend/web_fetch/site_mapper.py:250`, `map_site` schema in `chat_workflow/tool_handler.py` | The parameters are `domain`, `max_urls` and `respect_robots`. There is no query and no ranking. | The agent reads a handful of URLs instead of up to 500 | Must reuse the existing KB scorer, not add one | **adopt** → #21851 | trivial–moderate |
| 3 | Labelled third-party hand-off with a local-only switch | `web_fetch/fetcher.py:94`, `media/link/pipeline.py:86`, `content_reach/sources/web_page.py:32`, `content_reach/sources/web_search.py:32` | AutoBot's **default** fetch path (AUTO step 1) sends every URL to the Jina reader, and the content-reach search backend sends every query to Jina search. The endpoints are hardcoded, three of them duplicated. There is no SSOT key and no off switch. | URLs and queries stay on the host unless the user chooses otherwise | A config key and a settings toggle | **defect** → #21850 (owner to decide the default) | trivial |
| 4 | Hash-bucketed rollout of retry strategies | `web_fetch/fetcher.py` | There is no experiment layer in the fetch path | Safe A/B testing of fetch tactics | An experiment framework with no traffic volume to justify it | **rejected-by-hidden-metrics** | — |
| 5 | Run the reference work as a fetch backend | — | — | Breadth of features and SDKs | AGPL; 6–7 stateful services; the reliability features are cloud-only | **rejected-by-hidden-metrics** | significant |

### What We Already Do Better
- **A fetch waterfall with provenance and failure codes:** `web_fetch/fetcher.py` `_run_auto` (Jina → BS4 → Playwright) returns `FetchResult.source`, `error_code`, `retryable` and `status_code` (`web_fetch/types.py`). This is the equivalent of the reference work's engine list and its source and blocked flags.
- **SSRF on the HTTP path:** `autobot_shared/security/ssrf_guard.py` pins every hop, redirects included. The reference work's API server is weaker by default; its strong model exists only in the local edition.
- **Untrusted content is fenced and sanitised** (`knowledge/query_sanitizer.py`). The reference work relies on a public-only recommendation.
- **The fetch cache key includes render mode, profile and extractor version** (`web_fetch/cache.py`), so an extractor change invalidates old entries.
- **robots.txt** is honoured (`web_fetch/robots.py`). Its own fetch-guard gap is already filed (#16378).

### Gaps & Opportunities (by impact)
1. #21850: third-party egress on by default with no opt-out; the endpoint is hardcoded in four places.
2. #16562: browser requests beyond the top-level URL go unchecked. The reference work's proxy-every-connection pattern is the shape of the fix.
3. #21851: a relevance-ranked `map_site`.
4. Not audited in this pass: change monitoring for web sources. `knowledge/versioning.py` exists for documents; whether web sources are re-checked was not examined.

## Linked issues

- #21850 security(egress): every fetched URL and search query goes to a hardcoded third-party reader by default, with no opt-out — and the endpoint is defined three times
- #21851 feat(web): map_site takes a query and ranks discovered URLs by relevance, so an agent stops reading 500 URLs to find one
- #16562 security(browser): the Playwright container follows redirects and re-resolves DNS after the one-time SSRF check
