# Research: Quotio — multi-account AI quota monitoring and failover

**Source:** https://github.com/nguyenphutrong/quotio (MIT, Swift 6 / SwiftUI, macOS 14+)
**Steering context:** AutoBot has a secrets manager; monitoring + swapping provider accounts
before they hit rate limits is the feature of interest.
**Date:** 2026-08-25 · **Phase:** 1 + 2 complete
**Filed:** umbrella #15021 — children #15022, #15026, #15027, #15028, #15029, #15030; unrelated discovery #15031

---

## Source Analysis: Quotio

### What It Is

Quotio is a native macOS menu-bar GUI that fronts **CLIProxyAPI**
(`router-for-me/CLIProxyAPI`, confirmed at `Quotio/Services/Proxy/CLIProxyManager.swift:13`) —
a third-party Go proxy that multiplexes many AI provider accounts behind one local
OpenAI/Anthropic-compatible endpoint. Quotio itself does **not** route traffic. It does four
things: OAuth-onboards accounts, polls each provider's *private* usage endpoint to show
remaining quota, writes config for CLI agents (Claude Code, Codex, OpenCode, Droid, Amp) so they
point at the local proxy, and manages the proxy binary's lifecycle.

Maturity: ~8 months old (created 2025-12-24), 4.7k stars, 310 forks, 126 open issues, active
(last push 2026-08-23). Single-maintainer, no automated test suite (`AGENTS.md` states this
outright; `QuotioTests/` holds 17 files but the doc says none is a real suite). ~217 source
files, several of them enormous — `QuotaViewModel.swift` is 118 KB, `SettingsScreen.swift`
101 KB, `StatusBarMenuBuilder.swift` 96 KB, `CLIProxyManager.swift` 76 KB.

### Architecture & Key Patterns

- **Wrapper-over-daemon.** GUI (Swift) + downloaded Go binary (CLIProxyAPI). Quotio talks to it
  over a local management API (`Services/ManagementAPIClient.swift`) and edits its YAML config.
- **Two operating modes** (`Models/OperatingMode.swift`): `monitor` (quota polling only, no
  proxy) and `localProxy` (full routing). The mode gates which nav pages exist — monitor mode is
  the default and works with zero infrastructure.
- **Per-provider quota fetcher actors.** 16 fetchers under `Services/QuotaFetchers/` (Claude
  Code, Codex CLI, Copilot, Cursor, Kiro, Trae, Warp, Grok, Devin, Amp, OpenRouter, OpenAI,
  ClinePass, Factory Droid…) plus Antigravity and GLM elsewhere. Each is a Swift `actor` with its
  own credential discovery, token refresh, response parsing, and TTL cache.
- **Normalised quota DTO.** All fetchers emit `ProviderQuotaData` / `ModelQuota`, keyed by
  `QuotaAccountID { provider, accountKey }` (`Models/Models.swift:281`). Heterogeneous provider
  semantics are normalised through `QuotaMetricUnit` (usd / credits / requests / searches),
  `QuotaAmountSemantics` (balance vs spent) and `QuotaMetricPresentation`
  (progress / amount / status) — `Models/Models.swift:290-320`.
- **Concurrency discipline:** UI state `@MainActor`, services are `actor`s, DTOs `Sendable`,
  models marked `nonisolated`. Enforced as a written rule in `AGENTS.md`.

### Notable Implementation Details

1. **Quota is read from undocumented first-party endpoints, not billing APIs.** The Claude
   fetcher hits `https://api.anthropic.com/api/oauth/usage` with the *Claude Code OAuth token*
   and a hardcoded public client id, refreshing via `https://platform.claude.com/v1/oauth/token`
   (`ClaudeCodeQuotaFetcher.swift:55-75`). It parses the real subscription windows —
   `fiveHour`, `sevenDay`, `sevenDaySonnet`, `sevenDayOpus`, plus `extraUsage` credit balance —
   each as `{utilization %, resetsAt ISO8601}` with a `remaining` computed property
   (`ClaudeCodeQuotaFetcher.swift:19-52`). This is the substantive insight: subscription-plan
   headroom is knowable per rolling window *before* you get a 429.
2. **Credential discovery is multi-source.** The same fetcher reads proxy auth files
   (`~/.cli-proxy-api`), the macOS Keychain, and Claude Desktop's own credential store
   (`fetchClaudeDesktopQuota`, `fetchNativeKeychainQuotas`, `ClaudeDesktopCredentialReader.swift`)
   — so it can monitor accounts it does not own or route.
3. **Refresh is written back.** On a 401 the fetcher refreshes the OAuth token and rewrites the
   on-disk auth file / Keychain entry (`updateAuthFile`, `persistClaudeKeychainRefresh`), keeping
   the proxy's credentials live rather than just its own session.
4. **Three-state result enum instead of throwing:** `ClaudeAPIResult { success, authenticationError,
   otherError }` — an auth failure means "re-onboard this account", a transient failure means
   "keep the cached value". Distinguishing the two is what stops a network blip from evicting an
   account from the pool.
5. **Account health surfaced as a lifecycle, not a boolean.** `AuthFile.status` is
   `ready | cooling | error` with `disabled`, `unavailable`, `runtimeOnly` flags and a
   `statusMessage` that gets JSON-unwrapped into human text (`Models.swift:356-472`).
   `cooling` = rate-limited and resting.
6. **Warmup / keep-alive scheduler** (`Models/WarmupSettings.swift`, `Services/WarmupService.swift`):
   per-account, per-model scheduled cheap requests on an interval (15 min – 4 h) or a daily clock
   time, to keep sessions warm and windows ticking. Settings are per `(provider, accountKey)`.
7. **Threshold notifications with de-dup** (`Services/NotificationManager.swift:105-215`):
   `notifyQuotaLow` fires once per account below a configurable `quotaAlertThreshold`,
   `notifyAccountCooling` once on entering cooling, both cleared when the account recovers —
   a `sentNotifications` set prevents alert storms.
8. **Active-first ordering** (`Models/AccountSorting.swift`): a stable partition that floats
   in-use accounts to the top without disturbing tie-break order. Small, but it's the pattern a
   pool dashboard needs.
9. **Hardware-backed secret vault** (`Services/YubiKeySecretVault.swift`, 24 KB): optional
   YubiKey PIV provisioning that wraps stored secrets with a key that never leaves the token, with
   legacy-migration detection (`shouldMigrateLegacy`) and a preflight check before provisioning.
10. **Non-owned quota sources.** Cursor and Trae are monitor-only — detected on disk when the IDE
    is installed and logged in. Antigravity goes further: `AntigravityDatabaseService`,
    `AntigravityProtobufHandler` and `AntigravityAccountSwitcher` read the IDE's local DB and
    swap its active account, restarting the IDE process to apply.

### Strengths

- **The right primitive.** Per-window `(utilization, resetsAt)` per account is a genuinely
  better signal than 429-counting, and it is normalised across 18 wildly different providers.
- Failure-mode taxonomy (`ready/cooling/error`, auth-vs-transient) is more thought-through than
  most retry code.
- Clean concurrency model, documented invariants, and an `AGENTS.md` that is short and specific.
- Preventive posture: warmup, thresholds, active-first ordering, cooling notifications — all aim
  at *avoiding* exhaustion rather than reacting to it.
- Honest scoping: monitor mode works standalone; the proxy is optional.

### Weaknesses / Limitations

- **The advertised failover isn't in this repo.** "Smart auto-failover (Round Robin / Fill First)"
  is CLIProxyAPI's; Quotio writes `RoutingConfig.strategy` and `QuotaExceededConfig
  {switch-project, switch-preview-model}` into its YAML (`Models.swift:569-582`) and nothing more.
  Adopting the failover means adopting a second, unexamined Go project.
- **Built entirely on undocumented endpoints and hardcoded OAuth client ids.** Every fetcher is a
  provider ToS question and a one-sided-change-away-from-breaking dependency. 16 of them.
- **macOS-only and unportable** — SwiftUI, Keychain, PIV, `NSWorkspace` process control, Sparkle.
  Zero of the UI and most of the service layer transfers to a Linux/Python/Vue stack.
- **No test suite**, by the maintainer's own statement. 100 KB+ single files. `QuotaViewModel` at
  118 KB is a god object.
- **Account swapping is IDE-process surgery** — writing another app's SQLite DB and killing its
  process. Fragile and version-coupled (`AntigravityVersionDetector` exists precisely because of
  this).
- 126 open issues against a single maintainer; provider-endpoint churn is a treadmill.

### Visible vs Hidden Metrics

**Visible (advertised):** 4.7k stars in 8 months, Trendshift-trending, 18 provider integrations,
OAuth for 8, real-time quota dashboard, "smart auto-failover", one-click agent config, notarised
signed builds, Sparkle auto-update, 4 languages, MIT. All self-reported; none independently
benchmarked. Star count measures desirability of *the problem*, not quality of *the solution*.

**Hidden (what an adopter inherits):**

| Cost | Detail |
|---|---|
| Endpoint-churn treadmill | 16 fetchers against undocumented APIs; each provider change is an outage. Ongoing, unbounded maintenance. |
| ToS / account risk | Scraping first-party usage endpoints with CLI OAuth tokens, plus warmup traffic that exists only to hold a window open. Worst case is account suspension, i.e. the failure the feature exists to prevent. |
| Second-project coupling | Real routing lives in CLIProxyAPI. Adopting failover = adopting a Go daemon this analysis has not reviewed. |
| Zero portability | Swift/SwiftUI/Keychain/PIV/Sparkle. Only the *concepts* cross to AutoBot; no code does. |
| Credential blast radius | Reads and rewrites Keychain, Claude Desktop credentials, and proxy auth files. Any port must route through AutoBot's secrets manager, not a parallel path. |
| No tests | Nothing to inherit as a safety net; every ported behaviour needs tests written from scratch. |
| Operational load | A long-lived poller per account per provider, plus warmup jobs — scheduler, backoff, and cache invalidation that must not itself burn quota. |

**Weighing.** The visible wins are almost entirely *product* wins on a macOS desktop, and those
do not transfer. What survives the hidden-cost filter is the **data model and the state machine**:
`(provider, account) → [window: {utilization, resetsAt}]`, the `ready/cooling/error` lifecycle,
the auth-vs-transient result split, threshold de-dup, and pre-emptive selection of the account
with the most headroom. Those are cheap, testable, and provider-agnostic. The **fetchers
themselves** are where the hidden cost concentrates — per-provider scraping of undocumented
endpoints is a permanent liability, and the case for it collapses for any provider whose usage
data arrives in ordinary response headers. **Warmup** is the one feature whose hidden cost
(deliberate traffic to game a quota window, ToS-adjacent) plausibly vetoes it outright.

---

## AutoBot Comparison: Quotio → AutoBot

**Audit scope.** Read (not guessed): `autobot-backend/llm_shared/` — `provider_auth.py`,
`provider_registry.py`, `provider_degradation.py`, `rate_limit_backoff.py`,
`cross_worker_rate_limiter.py`, `fallback_chain.py`, `model_fallback_coordinator.py`,
`token_budget.py`; `autobot-backend/api/provider_auth.py`, `api/usage.py`;
`autobot-backend/llc/api/costs.py`; `autobot-backend/models/secret.py`;
`autobot_shared/secrets_vault.py`; `autobot-frontend/src/components/settings/ProviderOAuthConnect.vue`.
Negative greps recorded inline below.

### Headline

AutoBot's provider resilience is **reactive and provider-scoped**: detect a 429, back off,
mark the provider degraded, fall to the next model. Quotio's contribution is **proactive and
account-scoped**: know each account's remaining headroom per subscription window *before*
sending, and pick the account with room. AutoBot has no account dimension at all — one
credential per provider per org — and no headroom signal. Notably, AutoBot has already
*declared* the missing piece and left it unbuilt.

### What We Can Adopt

#### 1. Provider quota headroom as a first-class signal — **adopt**

*Source pattern:* `(utilization %, resetsAt)` per rolling window per account, normalised across
providers (`ClaudeCodeQuotaFetcher.swift:19-52`).

*Already-exists audit:*
- [`llm_shared/cross_worker_rate_limiter.py`](autobot-backend/llm_shared/cross_worker_rate_limiter.py) — proactive Redis token bucket, but the limits are **operator guesses** from
  `AUTOBOT_LLM_RL_{PROVIDER}_RPM` env vars (`:118-126`), model *request rate* only, and are keyed
  by provider with no account dimension. It cannot know a subscription's 5-hour window is 90 % spent.
- [`llm_shared/rate_limit_backoff.py`](autobot-backend/llm_shared/rate_limit_backoff.py) — parses
  `retry-after` / `x-ratelimit-reset` **out of the error string after a 429** (`:64-100`). Reactive by construction.
- [`llm_shared/provider_degradation.py`](autobot-backend/llm_shared/provider_degradation.py) — Redis
  `mark_degraded` / `is_degraded` with env-backed TTL. Binary, post-failure, no headroom.
- [`api/usage.py`](autobot-backend/api/usage.py) — *our own* recorded spend by user, not provider-side headroom.
- **The hook already exists and is unbuilt:** [`llc/api/costs.py:209-244`](autobot-backend/llc/api/costs.py#L209-L244)
  exposes `GET /costs/quota-windows`, whose `_PROVIDER_QUOTA_STRUCTURE` (`:73-94`) already names
  `["5h_output_tokens", "7d_output_tokens"]` for Anthropic — the exact windows Quotio reads. It
  returns **structure with no values**; the docstring says they "are populated by the quota monitor
  (phase 3)". `grep -rniE "quota.monitor|QuotaMonitor"` across backend, shared and frontend returns
  **two hits: that comment and its generated OpenAPI copy**. The quota monitor does not exist.
- Precedent for the mechanism exists elsewhere in the tree:
  [`integrations/rate_limiter.py:97-98`](autobot-backend/integrations/rate_limiter.py#L97-L98) already
  reads `X-RateLimit-Remaining` / `X-RateLimit-Reset` response headers — for GitHub-style
  integrations, never for LLM providers.

*Visible benefit:* pre-emptive routing away from a nearly-exhausted account; no user-visible 429s;
`/costs/quota-windows` stops being a hollow endpoint.
*Hidden cost:* a poller per credential per window, its own cache invalidation, and the risk that
the monitor itself burns quota. Bounded if headroom is harvested from response headers on traffic
we already send, rather than polled.
*Verdict:* **adopt — header-derived first, poller only where headers do not carry it.** The
undocumented-endpoint scraping that makes Quotio work is the single largest hidden cost in the
source and must not be ported wholesale; the *data model* is what transfers.
*Effort:* moderate (headroom store + wiring into `BaseProvider` response handling + populating the
existing endpoint). Significant if per-provider polling fetchers are added.

#### 2. Multiple accounts per provider, pooled — **adopt-with-conditions**

*Source pattern:* `QuotaAccountID { provider, accountKey }` (`Models.swift:281`) — every quota,
setting, and notification is keyed by account, not provider.

*Already-exists audit — AutoBot has no account dimension anywhere:*
- [`llm_shared/provider_auth.py:146`](autobot-backend/llm_shared/provider_auth.py#L146) —
  `_vault_secret_name(provider_name, subject="global") -> f"provider_auth:{provider_name}:{subject}"`.
  `subject` is the **org/tenant** (`org_vault_subject`, `:66`), not an account. One credential per
  provider per tenant, by construction.
- [`api/provider_auth.py:588,620`](autobot-backend/api/provider_auth.py#L588) —
  `GET /api/llm-auth/status/{provider_name}` and `DELETE /api/llm-auth/{provider_name}`. Singular;
  no list, no account id.
- [`ProviderOAuthConnect.vue:125,136`](autobot-frontend/src/components/settings/ProviderOAuthConnect.vue#L125)
  — connect / disconnect one provider; there is no account list UI.
- [`llm_shared/provider_registry.py`](autobot-backend/llm_shared/provider_registry.py) — registers
  providers by `name`; `set_fallback_chain` is a list of provider names. No account selection.
- `grep -rniE "account_pool|credential_rotation|rotate_account|switch_account|multi[- _]account"`
  over `autobot-backend`, `autobot_shared`, `autobot-frontend/src` → **zero hits**.
- The storage layer does *not* block it: [`models/secret.py`](autobot-backend/models/secret.py) keys
  on `(owner_id, name)` with `String(256)` names plus JSONB metadata, `expires_at` and `is_active` —
  `provider_auth:anthropic:{subject}:{account_id}` fits today without a migration to the secrets table.

*Visible benefit:* the actual requested feature — swap accounts before one runs out.
*Hidden cost:* a real blast-radius increase. Account selection has to thread through
`provider_registry` → `base_provider` → auth strategy, and the *audit trail* must record which
account served which request or cost attribution and the access graph both break. Multi-tenancy
makes it worse: an account pool is a shared resource that RBAC currently has no vocabulary for.
*Verdict:* **adopt-with-conditions** — only alongside (1), only with per-account audit attribution,
and only if pool membership is expressed through the existing `VaultRef` / principal namespace
rather than a parallel registry. Without those conditions the hidden cost wins.
*Effort:* significant.

#### 3. Account lifecycle state, with auth-vs-transient split — **adopt**

*Source pattern:* `ready | cooling | error` + `disabled`/`unavailable` (`Models.swift:356-472`), and
`ClaudeAPIResult { success, authenticationError, otherError }` (`ClaudeCodeQuotaFetcher.swift:12-17`) —
a dead credential is a different event from a flaky network.

*Already-exists audit:* `provider_degradation.py` gives one boolean per `(provider, model)` with a
single TTL — an expired refresh token and a transient socket error produce the identical state and
the identical 300 s recovery. `TokenExpiredError` exists
([`provider_auth.py:85`](autobot-backend/llm_shared/provider_auth.py#L85)) but nothing feeds it into
the degradation store, so a permanently dead credential is silently retried every TTL forever.
*Missing delta only:* classify the degradation cause and give `needs_reauth` a distinct, non-expiring
state that raises an operator alert instead of a retry.
*Visible benefit:* dead credentials surface as an action item instead of a recurring latency tax.
*Hidden cost:* low — an extra field on an existing Redis value plus one alert path.
*Verdict:* **adopt.** Best effort-to-value ratio in this report.
*Effort:* trivial-to-moderate.

#### 4. Normalised quota metric presentation — **adopt-with-conditions**

*Source pattern:* `QuotaMetricUnit` (usd/credits/requests/searches) × `QuotaAmountSemantics`
(balance vs spent) × `QuotaMetricPresentation` (progress/amount/status) — `Models.swift:290-320`.
Lets one dashboard render 18 providers that count entirely different things.

*Already-exists audit:* nothing equivalent. `QuotaWindow` (`llc/api/costs.py:146-152`) carries
`windows: List[str]` and a `description` string — names of windows, no typed values. Cost analytics
(`api/analytics_cost.py`, `services/llm_cost_tracker.py`) are USD/token-only.
*Visible benefit:* one UI for heterogeneous providers; avoids a per-provider rendering branch.
*Hidden cost:* premature until (1) produces values to render — a type system with no data behind it
is the debris this repo's rules warn about.
*Verdict:* **adopt-with-conditions** — as part of (1)'s response schema, never standalone.
*Effort:* trivial.

#### 5. Warmup / keep-alive scheduler — **rejected by hidden metrics**

`WarmupSettings.swift` / `WarmupService.swift`: scheduled cheap requests (15 min – 4 h, or a daily
clock time) per account per model, purely to hold a quota window open.
*Visible benefit:* smoother window boundaries.
*Hidden cost:* deliberate traffic whose only purpose is to game a provider's quota accounting, on
a multi-tenant server that would generate it continuously and unattended. ToS-adjacent, spends
budget to save budget, and the worst case — account suspension — is the exact failure the feature
claims to prevent.
*Verdict:* **rejected.** Note this is a *softer* call for a single developer's laptop than for a
server platform; the hidden cost scales with AutoBot's deployment model, not Quotio's.

#### 6. Hardware-backed vault root — **not adoptable in this shape**

`YubiKeySecretVault.swift` wraps secrets with a YubiKey PIV key that never leaves the token.
*Already-exists audit:* [`autobot_shared/secrets_vault.py`](autobot_shared/secrets_vault.py) +
`secrets_envelope.py` implement envelope encryption over a `VaultRef` principal namespace (umbrella
#10088) — a real DEK/vault-key hierarchy, but software-rooted. `grep -rniE "hsm|yubikey|pkcs11"` over
`autobot_shared` and `autobot-backend` → no hits.
*Verdict (not filed — belongs under #10088):* a genuine gap, but a USB token is the wrong shape for a headless multi-tenant server; the
equivalent is an HSM/KMS-backed root key. Out of scope for this research, worth its own issue.

### What We Already Do Better

| Area | AutoBot | Quotio |
|---|---|---|
| Cross-process correctness | `cross_worker_rate_limiter.py` — Redis token bucket with an atomic Lua check-and-decrement, correct under `uvicorn --workers N` (#8170) | Single-process app; no such problem to solve |
| Degradation propagation | `provider_degradation.py` — Redis-backed, env-configured TTL, shared by all workers, graceful in-process fallback (#11519) | In-memory app state |
| Fallback routing | `fallback_chain.py` + `model_fallback_coordinator.py` — model-level chains, audit trail into `LLMResponse.provider_metadata`, emitted events, plus `ProviderFallbackView.vue` / `ProviderFallbackChip.vue` surfacing it in the UI (#8998, #9421) | Delegated entirely to a third-party Go binary; Quotio only writes `routing.strategy` into its YAML |
| Alert de-duplication | `autobot_shared/alert_cooldown.py` — multi-tier progressive cooldown with recurrence tracking (#1948) | A `Set<String>` of sent notification ids (`NotificationManager.swift:209-219`) |
| Secret architecture | Envelope encryption, `VaultRef` principal namespace, RBAC grants, access graph, org/team/workflow scoping | Keychain entries + optional PIV wrap |
| Budget control | `token_budget.py`, `llc/services/budget.py`, `budget_watchdog.py`, per-agent budgets | None — quota display only |
| Testing | Every module above has a `_test.py` sibling | "No dedicated automated test suite currently exists" (`AGENTS.md`) |

The honest summary: AutoBot's *plumbing* is better everywhere. What Quotio has is a **signal**
AutoBot's plumbing has never been given.

### Gaps & Opportunities

Priority ordered by impact per unit of hidden cost.

| # | Gap | Impact | Effort | Note |
|---|---|---|---|---|
| 1 | No provider-side headroom signal; `/costs/quota-windows` returns structure with no values and its "quota monitor" does not exist | High | Moderate | Unfinished work already declared in-tree ([`llc/api/costs.py:220`](autobot-backend/llc/api/costs.py#L220)) — completing it is mandated, not optional |
| 2 | Degradation cannot distinguish a dead credential from a transient failure | High | Trivial | Dead tokens are retried every TTL forever today |
| 3 | One credential per provider per tenant — no account pool, no swap | High | Significant | The user's actual ask; gated on #1 and on per-account audit attribution |
| 4 | Response headers carrying rate-limit remaining are read for GitHub-style integrations but never for LLM providers | Medium | Trivial | Cheapest possible source for #1 |
| 5 | No typed quota-metric presentation for heterogeneous providers | Medium | Trivial | Only meaningful once #1 has values |
| 6 | Rate-limit buckets are operator-guessed env RPM, never reconciled against observed provider limits | Medium | Moderate | #1 makes them self-correcting |
| 7 | No hardware/KMS-rooted vault key | Low-Medium | Significant | Different shape than Quotio's; own issue |

### Specific Code/Files Affected

| File | Change |
|---|---|
| `autobot-backend/llm_shared/` **(new)** `quota_headroom.py` | Redis-backed store: `(provider, account_id, window) → {utilization, resets_at, observed_at}`, env-backed TTL per project convention. The "quota monitor" `llc/api/costs.py` already names |
| [`autobot-backend/llm_shared/base_provider.py`](autobot-backend/llm_shared/base_provider.py) | On every response, harvest rate-limit headers into the headroom store — the free path, no extra traffic |
| [`autobot-backend/llm_shared/provider_degradation.py`](autobot-backend/llm_shared/provider_degradation.py) | Add a cause field; `needs_reauth` becomes non-expiring and alerts instead of retrying |
| [`autobot-backend/llm_shared/rate_limit_backoff.py`](autobot-backend/llm_shared/rate_limit_backoff.py) | Feed parsed reset info into the headroom store instead of discarding it after the retry |
| [`autobot-backend/llm_shared/cross_worker_rate_limiter.py`](autobot-backend/llm_shared/cross_worker_rate_limiter.py) | Let observed headroom override the env-guessed RPM defaults |
| [`autobot-backend/llm_shared/model_fallback_coordinator.py`](autobot-backend/llm_shared/model_fallback_coordinator.py) | Consult headroom *before* dispatch, not only after a `RateLimitError` |
| [`autobot-backend/llc/api/costs.py`](autobot-backend/llc/api/costs.py) | `/costs/quota-windows` returns real values; drop the "requires configuration to populate" note |
| [`autobot-backend/llm_shared/provider_auth.py`](autobot-backend/llm_shared/provider_auth.py) | `_vault_secret_name` gains an optional account segment; keep the current name as the default account for backward compatibility |
| [`autobot-backend/api/provider_auth.py`](autobot-backend/api/provider_auth.py) | Add `GET /api/llm-auth/accounts/{provider_name}`; make status/delete account-aware |
| [`autobot-backend/llm_shared/provider_registry.py`](autobot-backend/llm_shared/provider_registry.py) | Account selection at dispatch: healthiest account by headroom, skipping `cooling` / `needs_reauth` |
| [`autobot-frontend/src/views/ProviderFallbackView.vue`](autobot-frontend/src/views/ProviderFallbackView.vue) | Per-account headroom bars and lifecycle badges; all strings i18n'd across 11 locales |

### Discovered problem (unrelated to this research)

[`ProviderOAuthConnect.vue`](autobot-frontend/src/components/settings/ProviderOAuthConnect.vue) has
hardcoded user-facing strings — `"Sign in with {{ providerLabel }}"` (`:14,67`),
`"Authenticate with your existing ... subscription."` (`:63`), `"Redirecting..."` (`:67`),
`"Device auth is not configured for this provider"` (`:161`). The file contains no `$t(` and no
`useI18n` import, violating the no-hardcoded-UI-strings rule (11 locales). Not in this research's
scope — filed separately as #15031.
