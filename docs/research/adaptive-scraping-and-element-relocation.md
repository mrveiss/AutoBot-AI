---
tags:
  - research
aliases:
  - Adaptive Scraping and Element Relocation
---

# Source Analysis: An Adaptive Web-Scraping Framework

Home: #17258 — this analysis produced no umbrella of its own. The one new gap it found
(resume inside a seed) is unfiled; everything else folds into #12497 or was rejected.

## What It Is

A single-author Python scraping framework, permissively licensed and actively pushed,
that spans three layers normally shipped as separate tools: a selector/parser
layer, a set of fetchers (plain HTTP, headless browser, anti-bot "stealth" browser), and a
spider/crawl engine with pause-resume, proxy rotation and adaptive throttling. Its headline
differentiator is **element relocation**: you mark a selection as saved, and when the site's
markup changes later, it re-finds the same element by structural similarity rather than
failing. Unusually mature distribution for a single maintainer — published package, Docker
image, a multi-language README, an MCP server, and a vendor-authored agent skill. Very high
adoption by stars, with a fork:star ratio around 0.10 that reads as "library people depend
on" rather than "template people copy".

## Architecture & Key Patterns

- **Three layers, one import surface.** `parser` (selection + relocation), `fetchers`
  (three interchangeable fetch strategies behind one call signature), `spiders` (crawl
  engine). Each is usable alone; the fetchers return the parser's own type, so the same
  selection API works whatever fetched the page.
- **Pluggable storage behind an ABC.** an abstract storage base declares `save`/`retrieve`;
  the shipped implementation is SQLite with `journal_mode=WAL`, `check_same_thread=False`
  and an `RLock`, explicitly so the library survives being used inside threaded frameworks.
- **Spider engine decomposed into one file per concern** — `scheduler`, `throttle`,
  `checkpoint`, `cache`, `robotstxt`, `links`, `session`, `result`. Crawl *templates*
  (sitemap, feed, site-to-markdown, a per-platform one) sit on top as ready-made spiders.
- **Browser layer split by role**, not by vendor: a base, a controller, a page wrapper,
  a stealth module, config tools, and a validators module — so anti-detection logic is
  isolated from session plumbing.
- **Typed throughout**, `py.typed` shipped, with `@overload` used to vary return type on a
  boolean argument rather than returning a union the caller must narrow.

## Notable Implementation Details

- **Element relocation by weighted similarity.** An element is persisted as a dict (tag,
  text, attributes, structural path, parent name/attribs/text). To relocate, it walks
  *every* element in the new tree and scores each candidate: tag equality, then
  `difflib.SequenceMatcher` ratios on text, on the whole attribute dict, on `class`/`id`/
  `href`/`src` individually, on the structural path, and on the parent's name and attributes.
  Score is the mean over however many checks applied, so the denominator varies by how much
  the original element had. Default accept threshold is **40%**.
- **It deliberately does not early-exit on a perfect match.** The loop scores all candidates
  and returns *every* element tied at the top score, with a comment explaining that a 100%
  match does not preclude another identical element. Honest about ambiguity, at the cost of
  returning a set where the caller may expect one.
- **The below-threshold path reports the number it measured.** On failure it logs the top
  score achieved and tells the caller to lower the threshold if that was the right element —
  so a miss is diagnosable instead of silent. Good instrument design.
- **Adaptive per-domain throttle.** Delay converges on `latency / target_concurrency` via
  `new = max((current + target) / 2, target)`, doubles on a block, and honours `Retry-After`
  in both numeric and HTTP-date forms, treating an unparseable value as absent with a debug
  log rather than guessing.
- **A memoised class.** The SQLite storage class is decorated with `lru_cache(1, typed=True)`
  *on the class itself*, making construction return a shared instance per argument tuple —
  a singleton with no singleton boilerplate, and a subtle one to debug.
- **Identifier hashing appends the input length** to the digest to cut collision chance.
- **An agent-facing output mode.** A CLI flag advertised for agent use sets ad-blocking and
  switches the converter to main-content-only, whose docstring states the purpose plainly:
  *strip hidden content that could be used for prompt injection*. The strip targets inline
  `display:none` / `visibility:hidden` style attributes, `aria-hidden="true"`, and
  `<template>` tags.

## Strengths

- **The relocation feature is a genuine differentiator**, not a repackaging — it addresses
  the actual failure mode of scrapers (markup drift) rather than the one people benchmark
  (speed).
- **Failure messages carry the measurement.** The threshold miss reports the achieved score;
  the throttle logs the header it refused to parse. Both let an operator act without a
  debugger.
- **Boundaries are drawn where they help a consumer**: storage is an ABC so you can swap it,
  fetchers are interchangeable at the call site, crawl templates are a layer not a fork.
- **Distribution is taken as seriously as the code** — typed, packaged, containerised,
  documented in ten languages, with an MCP server and a maintained agent skill.
- **A written AI-contribution policy** requiring disclosure of AI assistance in PRs and
  issues, with the reason stated: it determines *how much scrutiny to apply*. That is a
  governance artifact most projects this size do not have.

## Weaknesses / Limitations

- **Relocation is O(elements) per saved element, with string-similarity at each step.**
  `SequenceMatcher.ratio()` is quadratic in string length, and it is called up to eight times
  per candidate. On a large page with several saved selectors this is expensive, and nothing
  in the code bounds it — no candidate pre-filter by tag, no early rejection, no cap on the
  node count scanned.
- **A 40% default threshold is low for a similarity mean.** Combined with scoring that
  returns *all* top-tied candidates, the plausible failure is silent: a wrong-but-similar
  element returned confidently, or several elements where one was expected. The caller gets
  no confidence value back — only the elements.
- **The prompt-injection claim is stronger than the mechanism.** The agent skill states the
  flag is advertised as prompt-injection protection; what it does is remove main-page
  chrome and strip elements hidden via **inline style attributes** or `aria-hidden`. Content
  hidden by a stylesheet rule or a class — which is how hidden text is usually hidden — is
  not matched, and *visible* injected text is not addressed at all. A real partial mitigation
  described as protection.
- **The variable denominator makes scores incomparable across elements.** An element with no
  text, no class and no parent is scored on fewer checks than one with all of them, so "62%"
  means different things for different targets, and a single global threshold governs both.
- **Anti-bot bypass is the load-bearing feature and the most perishable one.** It is a
  stated capability against named commercial protections, which puts the project in a
  permanent race it does not control.
- **Single-maintainer bus factor** against a very large dependent population.

## Visible vs Hidden Metrics

**Visible** (all self-reported except adoption):

| Claim | Status |
|---|---|
| very high adoption, active daily | independently visible; the low fork:star ratio supports "depended on", not "forked" |
| Parser relocates elements after site changes | real, and the implementation matches the claim |
| Fetchers bypass named anti-bot systems out of the box | self-reported; not verifiable from source, and inherently time-limited |
| a speed claim in the project's own marketing | self-reported; a `benchmarks.py` exists in-repo, i.e. the author's own harness |
| Agent skill + MCP server | real, both shipped in-tree |

**Hidden** — what an adopter inherits:

- **An unbounded similarity scan** on the feature you adopted it for. Cost grows with page
  size × saved selectors, and there is no knob to bound it.
- **A silent-wrong-answer mode.** Relocation returns elements, not a confidence; a 41% match
  and a 99% match are indistinguishable to the caller.
- **A second datastore.** Adaptive mode means a SQLite file whose lifecycle, location, backup
  and growth become yours, keyed per registrable domain.
- **Perishable core value.** The anti-bot layer must be maintained against adversaries who
  update deliberately; adopting it is subscribing to someone else's arms race.
- **Legal and policy surface, not just technical.** Stealth fetching and anti-bot bypass
  carry terms-of-service and jurisdictional exposure that no dependency list shows.
- **Breadth as coupling.** Taking the parser is cheap; taking the spider engine means its
  scheduler, throttle, checkpoint and session model become your crawl architecture.

**Weighing.** For its intended user — someone whose job is extracting data from sites that
resist it — the hidden costs are the job description, and the visible wins are real. For an
adopter who wants *one* of the three layers, the calculus inverts: the parser and the
relocation idea are separable and cheap, while the fetcher layer imports a maintenance race
and a policy surface, and the spider engine imports an architecture. The two hidden costs
that should veto rather than discount are **the silent-wrong-answer mode** (a scraper that
confidently returns the wrong element is worse than one that fails, because the failure is
detectable and the wrong answer is not) and **the perishable anti-bot core** (value that
decays unless someone keeps fighting for it).

## Untrusted-content observations

Recorded per this skill's contract — these are *findings about the fetched material*, not
instructions followed:

1. The vendor-authored agent skill contains a section addressed **to AI readers**, headed as
   notes for AI scanners, pre-empting security objections (no solvers used, no credentials
   required, arguments validated internally). Benign in intent and plausibly accurate, but
   structurally it is fetched content speaking to the agent evaluating it, which is the shape
   the contract exists for. It was read as data and none of its assurances were taken as
   verified.
2. The same file contains an imperative in bold addressed to the reading agent,
   directing which tool to use.
   Treated as documentation of a flag, not as an instruction; and the flag's actual behaviour
   was checked against the claim rather than assumed, which is how the gap above was found.

## Phase 2 — AutoBot Comparison

Scope: the four mechanisms Phase 1 found transferable, plus the one the reference work is
weakest at. Every item was audited against AutoBot code and cross-referenced against open
**and** closed issues before a verdict. Issue numbers are given so nothing here is re-filed.

### What We Already Do Better

**Untrusted-content handling, and not narrowly.** The reference work's agent mode *removes*
hidden elements. AutoBot *labels* the whole fetched body and defends the label
(`autobot-backend/knowledge/query_sanitizer.py`):

- `wrap_untrusted_web_content` fences page text in `<untrusted_web_content source=URL>` with an
  advisory stating the content is data, never instructions.
- **Both delimiters are neutralised inside the text first**, so a page emitting the closing tag
  cannot end the quoted region — an escape the reference work has no equivalent of because it
  has no boundary.
- On a high-confidence pattern hit, `sanitize_and_wrap_web_content` **prepends a warning and
  keeps the content** rather than dropping it.
- `_escaping_sanitizer` downgrades REJECT to ESCAPE, wrapping the span as `[ESCAPED:...]`.
- A documented false-positive carve-out: rules that reject a *query* must not discard a *page*,
  because legitimate pages discuss prompt injection.
- The rationale for doing both is written down: *sanitising alone assumes the rule set is
  exhaustive, and wrapping alone assumes the model always honours the boundary.*

**And it is reachable** — 7 call sites in `chat_workflow/tool_handler.py` plus
`chat_workflow/browser_tool_handler.py:296`, covering `scrape_url`, `crawl_site`, `map_site`
and browser `get_text`. That matters because the recurring finding elsewhere in this repo is a
control that exists and is not wired; here it is wired.

**Outbound egress safety.** `autobot_shared/security/ssrf_guard.py` resolves and pins the IP,
hard-blocks link-local even with private egress enabled, refuses redirects or re-validates per
hop, and caps size and timeout. The reference work's fetchers have no comparable guard — their
threat model is the site defending against them, not them defending against the site.

**Per-domain failure isolation already exists**, just not adaptively: `web_fetch/fetcher.py:80-148`
has a fixed per-netloc semaphore (4) and a circuit breaker (3 failures in 60s → 60s cooldown).

### What We Can Adopt

**1. Strip hidden elements before text reaches a model — adopt-with-conditions, trivial.**
Already-exists audit: **ABSENT on every model-feeding path.** A repo-wide grep over `.py/.js/.ts`
for `display:none|visibility:hidden|aria-hidden|template|offscreen|opacity:0|checkVisibility|
getComputedStyle` found only two hits, both action-indexers rather than content sanitisers
(`autobot-browser-worker/element-index.js:50`, `api/playwright.py:686`). Every text path reads
raw DOM text: `markdownify` (`web_fetch/extractors.py:51`), BS4 `get_text` (`:62`,
`media/link/pipeline.py:379`), `textContent` (`playwright-server.js:1055`, which *includes*
hidden text), and `outerHTML` snapshots (`tool_handler.py:388`). `innerText` paths
(`research_browser_manager.py:57`) skip CSS-hidden text only as a side effect of rendering.
Visible benefit: closes the classic hidden-div injection vector that our regex sanitiser cannot
see. Hidden cost: near zero technically — but a blind strip conflicts with our own
label-don't-delete philosophy and would destroy a page that legitimately uses hidden markup.
**Condition:** strip into a labelled note ("N hidden elements removed") rather than silently, so
the sanitiser's existing warning channel reports it. Not covered by #12757 (closed — it added
the fence, not hidden-text removal) or #16488 (closed — Claude Code skills, not product code).

**2. `Retry-After` parsed in both forms, with an unparseable value treated as absent — adopt, trivial.**
Already-exists audit: **PARTIAL, and one path crashes.** `integrations/github_integration.py:341-342`
does `wait = float(retry_after)` with no guard, and the `except` clauses cover only
`asyncio.TimeoutError`, `aiohttp.ClientConnectionError` and `aiohttp.ClientError` — **not
`ValueError`**. RFC 9110 permits an HTTP-date, so a compliant response raises out of the 429
handler. The `"60"` default protects only against the header being *absent*, not unparseable.
`integrations/rate_limiter.py:171-176` has the mirror defect — `except ValueError: pass`, so a
date-form header is ignored without a trace. Nothing in the tree parses the HTTP-date form:
a grep for `parsedate|parse_http_date|email.utils` finds only a Last-Modified parse. The
reference work's parser is ~10 lines, tries numeric then HTTP-date, and logs an unreadable value
at debug while returning None. **#12497 (open, under epic #12492) already asks for Retry-After
generally — the unfiled delta is the HTTP-date form and the crash.**

**3. Per-domain adaptive delay — adopt-with-conditions, fold into #12497.**
Already-exists audit: **ABSENT.** Nothing is keyed by remote domain *and* adapts to latency;
`autobot_shared/rate_limiter.py` is per caller/key, `integrations/rate_limiter.py` per token, and
`llm_shared/cross_worker_rate_limiter.py` per provider — a different plane. Greps for
`crawl_delay|request_delay|politeness|ewma|adaptive|latency` across `web_fetch`,
`knowledge/connectors` and `media/link` found nothing relevant, and `web_fetch/robots.py` uses
`urllib.robotparser` for `can_fetch` only, never reading Crawl-delay. The reference work converges
on `latency / target_concurrency` via `new = max((current + target) / 2, target)` and doubles on a
block. Visible benefit: politeness without a hand-tuned constant. Hidden cost: a second piece of
per-domain state, and a latency-driven delay misreads a slow-but-willing host as hostile.
**#12497 asks for a fixed politeness delay; the delta is making it adaptive.**

**4. Resume inside a seed — adopt, moderate.**
Already-exists audit: **PARTIAL.** Seed- and source-level checkpoints exist in Redis
(`knowledge/connectors/base.py:222-260`, 24h TTL; `web_crawler.py:297-358` per seed, skipping
recorded seeds). But the BFS frontier inside a seed is in-memory only
(`web_fetch/frontier.py:76-140`, a `_visited` set plus a queue, reconstructed per seed at
`web_crawler.py:463`), so an interruption restarts the whole seed. The seed-level work landed under
#8146, #8284, #8296, #8297, #12744, #12843 (all closed); **the within-seed gap is unfiled.**

**5. Report the score you measured on a failed match — adopt, trivial, and it is the half of
relocation worth taking.** The reference work's miss path logs the top similarity achieved and
tells the caller to lower the threshold if that was the right element. Our equivalent failure is
silent (see Gaps). Visible benefit: a drift failure becomes diagnosable. Hidden cost: none.

### Rejected by hidden metrics

**Element relocation by similarity — rejected as shaped; take the diagnostics, not the mechanism.**
Already-exists audit: **ABSENT entirely.** Greps for `SequenceMatcher|difflib|rapidfuzz|fuzz|
levenshtein|simhash|minhash|relocate|fallback_selector|self.?heal` across backend, worker and
shared found no DOM comparison — every hit is text or code similarity (`utils/entity_resolver.py:300`,
`api/codebase_analytics/duplicate_detector.py:424` MinHash, `code_intelligence/code_fingerprinting.py`).
The only structural artefact is the positional xpath generated by `api/playwright.py:701-710` and
`element-index.js:51-58`, used for exact lookup only. **Why rejected:** the mechanism is an
unbounded O(elements) scan with quadratic string similarity at each candidate, no pre-filter and
no node cap — and it returns elements **without a confidence**, at a 40% default threshold, with
all top-tied candidates returned. For a knowledge base that *ingests* what it extracts, a
confidently-wrong element is strictly worse than an empty one, because the empty one is
detectable. Adopting the scoring without a returned confidence would convert our silent-null
failure into a silent-wrong-value failure.

**Proxy rotation / egress IP pooling — rejected by hidden metrics.**
Already-exists audit: **ABSENT** (greps for `proxy_pool|proxy_rotat|egress_ip|socks|HTTPS?_PROXY`
over backend, shared, worker and config found only a fixed trusted reader endpoint at
`web_fetch/fetcher.py:28` and inbound reverse proxies). Rotation imports a terms-of-service and
jurisdictional surface that no dependency list shows, plus a maintenance race against adversaries
who update deliberately. **#12497 already asks for a single optional proxy for egress-restricted
networks, which is the defensible subset** — that is worth doing and rotation is not.

**Mandatory AI-contribution disclosure — not adoptable; it contradicts a standing owner rule.**
The reference work requires disclosing AI assistance in PRs and issues, with a stated reason worth
recording: it determines *how much scrutiny to apply*. AutoBot's standing rule is the opposite —
no commit trailers, `mrveiss` sole author. Noted as a contrast, not a proposal.

### Gaps & Opportunities — defects found while auditing

Ordered by severity. Each was verified first-hand, not relayed.

| # | Finding | Evidence | Existing issue |
|---|---|---|---|
| G1 | **`web_search` puts third-party page text into the model context unfenced.** The trust boundary covers `scrape_url`, `crawl_site`, `map_site` and browser `get_text` — not the search path. `_format_full_search_results` inserts `markdown[:4000]` directly, and the browser-VM fallback truncates `raw_text` the same way | `chat_workflow/tool_handler.py:1238`; `:3135-3150`; 7 `sanitize_and_wrap_web_content` calls in that file, none on the search path | **unfiled.** #12757 (closed) built the fence and covers only the three wrapped tools |
| G2 | **No hidden-element stripping anywhere on a model-feeding path** | see adopt item 1 | unfiled |
| G3 | **`content_reach` output is unsanitised, and mislabelled when it is inspected.** No sanitiser or firewall inside `content_reach/`; when the call goes through `ParallelToolExecutor` the output is inspected as `ContentSource.STDOUT`, not `WEB` | `tools/tool_registry.py:243`; `tools/parallel/executor.py:476` | unfiled |
| G4 | **A changed page silently writes nulls into the knowledge base.** A scrape-template region whose selector stops matching stores `extracted[label] = None`, `run_template` returns HTTP 200 with the nulls, and the crawl path ingests them without comment. The UI renders null as a "no value" string — display, not alert | `api/scrape_templates.py:173-232`, `:305-317`; `api/knowledge_crawl.py:140-146`; `ScrapeTemplatePanel.vue:149` | unfiled (#5136 closed is the origin feature) |
| G5 | **`ELEMENT_REFS` is advertised and unimplemented.** The capability is declared and `params["ref"]` is sent, but the worker has no handler for it — a grep excluding `unref`/`href` returns nothing | `browser_backends/worker.py:50`, `:108-111`; `autobot-browser-worker/playwright-server.js` | unfiled |
| G6 | **An HTTP-date `Retry-After` crashes one path and is silently ignored on another** | see adopt item 2 | unfiled (#12497 covers Retry-After generally) |
| G7 | **Stored selectors are weak by construction.** Template selectors are built from id, else the *first class*, else the tag name, plus a positional xpath — the three most drift-prone choices | `api/playwright.py:676`, `:701-710` | unfiled |
| G8 | **The index staleness guard is count-only and optional.** `expected_element_count` catches a changed count; a same-count reshuffle is undetected, and the caller may omit the check | `playwright-server.js:967-990`; `element-index.js:105-111` | #11537 closed (delivered the feature); the reshuffle case is not in its criteria |
| G9 | Within-seed crawl resume | see adopt item 4 | unfiled |

### Specific Code/Files Affected

- `autobot-backend/chat_workflow/tool_handler.py` — wrap `_format_full_search_results` and the
  browser-VM fallback in `sanitize_and_wrap_web_content` (G1); route `content_reach` through the
  firewall with `ContentSource.WEB` (G3).
- `autobot-backend/web_fetch/extractors.py` — add a hidden-element pass before `markdownify`,
  reporting what it removed rather than removing silently (G2, adopt 1).
- `autobot-backend/integrations/github_integration.py` + `integrations/rate_limiter.py` — a shared
  `Retry-After` parser handling both forms, unparseable → None with a debug log (G6, adopt 2).
- `autobot-backend/api/scrape_templates.py` — a region miss must be distinguishable from a region
  whose true value is empty, and must not reach the KB unlabelled (G4); add the measured-score
  diagnostic (adopt 5).
- `autobot-backend/web_fetch/frontier.py` + `knowledge/connectors/web_crawler.py` — persist the
  frontier so an interrupted seed resumes (G9, adopt 4).
- `autobot-backend/browser_backends/worker.py` or the worker — implement `ref` or stop advertising
  `ELEMENT_REFS` (G5).

### Method and limits

Three parallel read-only audits plus first-hand verification of every finding that became a
numbered gap. Each audit was required to distinguish *searched and found nothing* from *did not
search*, and to record any path or file-type filter, because a filtered empty result is not an
absence. Stated limits: `.vue`/`.html` files were not searched for the hidden-element patterns;
`autobot-slm-*` and `autobot-frontend/` fetch code were not audited; whether chat tool calls route
through `ParallelToolExecutor` is NOT-DETERMINED, which affects G3's severity; and the consumer of
`research_browser_manager.extract_content` was not identified.

One untrusted-content note: the harness neutralised instruction-shaped control tags in one
subagent's report before it reached this session. Nothing in it was acted on as an instruction.
