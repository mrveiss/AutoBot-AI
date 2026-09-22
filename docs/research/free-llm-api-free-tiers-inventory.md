# Source Analysis: a community-curated inventory of permanently-free LLM API tiers

Research date: 2026-09-22 · Phases 1-2 (source analysis + AutoBot comparison, approved 2026-09-22)

Driving question from the requester: *"we run out of token usage — is this real, is it safe to
use, can we use it in our development process to not run out of tokens?"*

## What It Is

A curated, machine-generated catalogue of LLM inference endpoints that advertise a **permanent**
free tier (explicitly excluding trial credits and time-limited promos). 16 providers, split into
"provider APIs" (companies that train the models) and "inference providers" (gateways reselling
other people's weights). Each entry carries a base URL, an API-key signup link, a per-model table
(context, max output, modality, rate limit) and, for most, a footnote documenting the catch.
Maturity: high adoption (~8k stars, ~770 forks), CC0-licensed, README generated from a single
`data.json` via CI. The repository is published as a developer-marketing asset by a commercial
agent-platform vendor, whose product is advertised at the top of the page as the way to consume
the same list — that is the business model behind the curation, not a neutral standards body.

## Architecture & Key Patterns

- **Data/render split.** `data.json` is the single source of truth; a GitHub Action regenerates
  `README.md` on every push that touches it. Contributors edit data, never the rendered table.
- **Live-probe verification harness.** `scripts/verify-providers.js` issues a real completion
  request per provider/model, with per-provider request shapes (OpenAI-compatible, Gemini,
  Cohere, Cloudflare, Ollama), retry with backoff (2s/8s/30s), status-to-error-class mapping,
  and key redaction before anything is written to a report.
- **Failure-streak state machine.** `.verify/state.json` records consecutive failures per
  `provider/model` with a first-fail date and error class, so a row is retired on sustained
  failure rather than on one bad night.
- **Footnote layer for the fine print.** The decay, licensing and data-use conditions that
  break a naive "it's free" reading live in numbered footnotes rather than the table.

## Notable Implementation Details

- The catalogue **documents its own rot**: rows are annotated with announced shutdown dates that
  have already passed while the model is still served, gateways whose model catalogue "can lag
  what is actually served", and providers that stopped publishing numeric rate limits (the
  column then carries the last-published value, flagged as such).
- **Keyless tiers are called out explicitly** — two gateways answer with no API key at all
  (one at 2 requests/minute/IP, one at 10 RPM / 500K tokens per 24h anonymously).
- Verification is **evidence-dated**: individual rows state the date a live request confirmed
  them, instead of asserting a permanent fact.

## Strengths

- Honest about conditions most such lists omit: training-on-your-prompts, non-commercial-only
  licences, real-name/identity verification, region restrictions, shared-quota arithmetic.
- Structured data (`data.json`) makes it directly consumable as a provider registry seed.
- The verification harness is a genuinely reusable pattern, independent of the list content.

## Weaknesses / Limitations

- **The refresh has lapsed.** Every "nightly refresh" commit is human-driven, not scheduled: the
  only CI workflow regenerates the README from `data.json`, it does not run the prober. Last
  data refresh `2026-08-21`; the newest verification report on disk is `2026-07-30`. As of
  2026-09-22 the catalogue is ~1 month past its own stated cadence, and the probe evidence is
  ~2 months old.
- **"Permanent" is the publisher's reading, not a contractual guarantee.** Nothing in these free
  tiers is contractual; the list itself records providers shutting models down mid-cycle.
- Rate-limit columns are a mix of live-probed, documented, and last-known-published values, with
  the provenance only in footnotes.
- No aggregate quality signal — a row says a model answers, never how well.

## Visible vs Hidden Metrics

**Visible (what the list advertises)**
- 16 providers, 100s of models, "permanent" free tiers, mostly no credit card.
- OpenAI-SDK-compatible endpoints throughout → near-zero integration cost.
- Headline allowances up to ~1M tokens/24h (one gateway, free token) and 2,000 requests/day.
- Self-reported verification: live probes, dated rows, failure streaks. Independently
  re-verified here only as far as *the harness exists and the reports are stale* — the model
  rows themselves were not re-probed in this analysis.

**Hidden (what an adopter inherits)**
- **The prompt is the price.** Documented, per the source's own footnotes: one major provider's
  free tier may use prompts to improve its products (except EEA/UK/CH); another trains on
  free-mode inputs and outputs unless you opt out; a gateway warns it "may route your requests
  to providers that log prompts and outputs"; one vendor's free endpoints carry an explicit
  "do not submit personal or confidential data — your use is logged" condition.
- **Licence traps.** At least one free tier is non-commercial-use-only, which a product
  integration silently violates.
- **Identity/jurisdiction cost.** Several require real-name or national-ID verification, or
  binding to a specific cloud account; some are region-locked.
- **Operational load.** N providers × N auth shapes × N rate-limit regimes × a catalogue that
  rotates weekly = a routing/fallback/quota layer to build, monitor and keep current. The
  source's own harness exists precisely because this decays.
- **Failure modes are quota-shaped.** Over-quota is a *failed request*, not a bill — so the
  degradation is availability loss, at an unpredictable time, under an unpublished limit.
- **Egress surface.** Each added provider is another outbound destination carrying prompt
  content, several of them anonymous/keyless gateways with no accountable counterparty.

**Weighing.** For throwaway experiments, hobby scripts and non-sensitive evaluation, the visible
wins stand and the hidden costs are cheap. For anything carrying proprietary source, customer
data, or credentials in the prompt, the data-use terms alone are disqualifying on most of these
tiers, and no rate-limit improvement offsets that. For sustained agentic workloads the decisive
hidden metric is arithmetic, not policy — see below.

## Direct Answer to the Driving Question

1. **Is it real?** Yes — the providers and free tiers are real, the verification harness is real
   code that makes live calls. But the catalogue is currently ~1 month stale against its own
   cadence, so individual rows must be re-probed before being trusted, not read as current fact.
2. **Is it safe?** Not uniformly, and the unsafe part is contractual rather than technical. The
   dominant risk is **prompt disclosure and training use**, documented by the source itself for
   several of the largest entries, plus one non-commercial-only licence and several
   keyless/anonymous gateways with no accountable counterparty. Any use touching proprietary
   code, customer data or secrets fails on terms before it fails on security.
3. **Can it stop us running out of tokens in development?** **No — category mismatch.** The
   development-session budget that runs out is scoped to the Anthropic account serving the
   coding agent; none of the listed providers serve that API, so none of their quota can offset
   it. And the arithmetic is not close: a single development session here is provisioned at
   ~15M tokens, while the *largest* daily allowance in the entire catalogue is ~1M tokens/24h
   (most are 20K–500K/day). The list is off by one to three orders of magnitude for agentic
   coding, per provider, per day.
   What it *could* offset is a **different budget**: the product's own runtime inference — the
   LLM calls the platform makes on behalf of users — where per-call volumes are small, latency
   tolerance is higher, and a non-sensitive subset of traffic (classification, routing,
   summarising public content) might be servable from a free tier. That is a separate question
   from developer-session budget, and it is the only version of this idea with a viable shape.

## Follow-up Questions for Phase 2 (if approved)

- Does the platform already have a provider registry / fallback router that a new free-tier
  backend would slot into, or would one have to be built?
- Which runtime call sites, if any, are non-sensitive enough to be legal on a train-on-input
  free tier — and is there an existing classification of prompt sensitivity to base that on?
- Does the failure-streak + live-probe verification pattern have an analogue in the existing
  provider-health checks, or is that the actually-adoptable idea here (independent of the list)?

---

# Phase 2 — AutoBot Comparison

Approved 2026-09-22, full scope (no focus area given). Every claim below cites a file read or a
grep run; "0 hits" means the grep ran and returned nothing, not that it was not attempted.

## What We Can Adopt

### 1. Per-provider data-use / licence policy metadata on the provider record

**Already-exists audit.** `grep -rn 'data_retention|trains_on|training_use|data_residency|no_train|zero_retention' --include='*.py' autobot-backend/llm_shared/ autobot_shared/` → **0 hits**.
`ProviderRuntimeFact` and `list_providers()` (`autobot-backend/llm_shared/provider_registry.py:522-535`)
expose runtime facts (availability, models, health) only — nothing about what the provider is
permitted to do with the prompt. `grep -rn 'free_tier|is_free' llm_shared/` → 0 hits outside a
comment in `pricing/deepseek_source.py:32`. Issue search (`gh issue list --state all --search
"provider data retention training prompts"`) returned no matching issue.

**Visible benefit.** Routing and fallback can refuse a provider for a sensitive prompt; the
"which call sites may use a free tier" question becomes answerable per provider instead of by
argument.
**Hidden cost.** Policy metadata rots faster than the code around it — the reference work's own
footnotes are a live demonstration (announced retirement dates passed, published rate limits
withdrawn). A stale `trains_on=False` is *worse* than an absent field, because it is
evidence-shaped and will be trusted.
**Verdict: adopt-with-conditions.** Only if the field carries a `verified_on` date and a source
URL, and the unknown value is the *unsafe* one (absent ⇒ treat as trains-on, non-commercial,
unverified). Absence must never read as safe. Effort: **moderate**.

### 2. Cross-run failure-streak retirement (delta only — partially exists)

**Already-exists audit.** `grep -rn 'consecutive|streak|fail_count|failure_count'` over
`autobot-backend/llm_shared/` and `autobot-backend/services/provider_health/` (excluding tests) →
**1 hit**: `llm_shared/streaming.py:94` `get_failure_count(model)`, which is per-stream, not
cross-run. `ProviderHealthResult` (`services/provider_health/base.py:25`) is a point-in-time
snapshot with no history; `ProviderHealthManager` (`autobot-backend/services/provider_health/manager.py:28`) caches results, it does not
accumulate them. `ProviderDegradationStore` (`llm_shared/provider_degradation.py:98`) is the
closest existing thing — Redis-backed, keyed `autobot:llm:deg`, with a `DegradationCause` enum.

**Missing delta.** A persisted per-`(provider, model)` *consecutive*-failure counter carrying a
first-fail date and an error class, surviving restarts, that **retires a model from the fallback
chain** after N consecutive failures rather than only flagging it degraded for the current
window. That is exactly the state machine in the reference work's `.verify/state.json`.
**Visible benefit.** A model that has been dead for days stops being retried and stops polluting
latency/fallback decisions.
**Hidden cost.** A retirement mechanism that retires on a transient (a provider-side outage, a
credential expiry) removes capacity during exactly the incident where it is needed; it needs a
revival path and an operator-visible reason, which is most of the work.
**Verdict: adopt-with-conditions** — extend `ProviderDegradationStore`, do not build a second
store (rule 2, reuse from shared). Effort: **moderate**.

### 3. The catalogue itself (the 16 providers)

**Verdict: rejected-by-hidden-metrics**, and separately redundant — see the next section.

## What We Already Do Better

| Capability | AutoBot | The reference work |
|---|---|---|
| Provider adapters | 13 in `llm_shared/providers/` — incl. `groq.py`, `huggingface.py`, `mistral.py`, `openrouter.py`, `ollama_provider.py` (5 of its 16), plus `openai_compatible.py` and `custom_openai.py` which cover the rest, since the whole list is OpenAI-SDK-compatible | A markdown table |
| Credential gating | `CredentialGatedRegistry` (`autobot_shared/credential_gated_registry.py`) — never-raise lookups, replace-with-warning; every cloud provider gated on `resolve_provider_key(...)` at `provider_registry.py:582-668` | n/a |
| Cost model | `llm_shared/pricing/` — live sources per vendor + `crosscheck.py:78 cross_check()` reconciling two sources with a tolerance | None; everything is $0, so there is nothing to reconcile |
| Quota / rate limiting | `quota_headroom.py` (Redis, `autobot:llm:headroom`, utilization), `cross_worker_rate_limiter.py`, `rate_limit_backoff.py` | Rate limits are a documentation column |
| Fallback | `fallback_chain.py`, `model_fallback_coordinator.py`, `fallback_events.py`, plus a completion circuit breaker (`provider_registry.py:196`) | One gateway's auto-router, externally operated |
| Secret hygiene | `credential_redaction.py:48-155` (`redact_api_key`, `redact_dict`, logging filter) | `redactKeys()` in the prober only |

**The integration value of the list to us is ≈ 0**: we already have the adapters, and every
remaining provider is config (`base_url` + key on `custom_openai`), not code.

## Gaps & Opportunities

**1. No prompt-sensitivity classification exists — and it is the prerequisite.** (highest impact)
There is nothing in the codebase that lets a call site declare "this prompt may go to a
train-on-input provider". Adoption item 1 has nothing to *enforce against* without it. Any
free-tier routing plan must start here, not with providers.

**2. The egress guard is address-class, not a destination allowlist.**
`_assert_egress_allowed` (`autobot_shared/http_egress_guard.py:30`) delegates to
`is_public_url_async` and refuses loopback / link-local / cloud-metadata / reserved addresses —
it **passes every public host**. Rule 8 therefore protects against SSRF, not against prompt
egress to an arbitrary public gateway. Nothing in the current egress layer would stop a prompt
being sent to any of these free endpoints. This is a gap in what the rule is assumed to cover,
independent of whether we ever adopt a free tier.

**3. Keyless providers cannot register, by design.** `_populate_default_providers`
(`provider_registry.py:565-668`) registers every cloud provider only when `resolve_provider_key`
returns a value. Two of the listed free tiers need no key at all, so they would require an
explicit keyless opt-in path — which is simultaneously the feature and the reason not to build
it: a keyless gateway has no accountable counterparty for a prompt.

## Specific Code/Files Affected (if items 1–2 were implemented)

| File | Change |
|---|---|
| `autobot-backend/llm_shared/models.py` | Add a `ProviderDataPolicy` value object: `trains_on_input`, `commercial_use_allowed`, `jurisdiction`, `source_url`, `verified_on`; unknown defaults to the unsafe value |
| `autobot-backend/llm_shared/provider_registry.py:522-535` | Surface the policy through `get_provider_facts()` / `list_providers()` |
| `autobot-backend/llm_shared/provider_degradation.py:98` | Extend `ProviderDegradationStore` with a consecutive-failure counter (count, first-fail date, error class) and a retirement threshold |
| `autobot-backend/llm_shared/fallback_chain.py:195` | Skip retired models when selecting the next fallback |
| `autobot_shared/http_egress_guard.py` | (gap 2) an optional destination allowlist mode for prompt-bearing requests, distinct from the address-class check |

## Bottom Line

For the question that started this — *offset the development token budget* — the answer is
**rejected-by-hidden-metrics and by arithmetic**: wrong API, wrong account, and one to three
orders of magnitude of quota short. The two things actually worth taking are internal patterns
(policy metadata with an expiry date; cross-run failure-streak retirement), and they are worth
taking whether or not a single free tier is ever wired in. Gap 2 (egress guard scope) is a
finding that stands on its own and does not depend on any of this being adopted.

## Filed

The governance gaps above are tracked; the inventory itself is not adopted.

| Issue | Scope | Wave |
|---|---|---|
| **#17248** | Umbrella — the LLM path cannot answer *"may this prompt go to this provider?"* | — |
| #17249 | LLM provider calls bypass the egress mechanism entirely | 1, no blockers |
| #17250 | No prompt-sensitivity classification at any call site | 1, blocks #17251 |
| #17251 | Provider records carry no data-use or licence policy | 2, blocked by #17250 |
| #17252 | Provider degradation has no cross-run failure streak (reliability, not governance) | standalone |

#17233 already records that the egress guard is an address deny-list rather than a destination
allow-list. It is **not** a duplicate of #17249: its measured population is shared-client callers
plus direct `requests`/`httpx`/`aiohttp` callers, and LLM providers are a third bucket that
reaches the network through vendor SDKs, so that issue's ruling would not reach them. #13623
(connector/credential/egress umbrella) is adjacent and deliberately untouched.
