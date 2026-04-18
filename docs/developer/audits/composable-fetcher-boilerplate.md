# Composable Fetcher Boilerplate Audit (Issue #5154)

> Origin: PR #5137 (issue #5112) introduced
> [`autobot-frontend/src/composables/analytics/useAnalyticsEndpoint.ts`](../../../autobot-frontend/src/composables/analytics/useAnalyticsEndpoint.ts)
> — a 144-line generic GET-fetcher that collapsed 14 near-identical fetchers
> in `useAnalyticsDataFetchers.ts` (1147 LOC -> 693 LOC, **-40%**).
>
> This audit walks every non-analytics composable in `autobot-frontend/src/composables/`
> that calls `fetchWithAuth(...)` and decides whether `useAnalyticsEndpoint`
> generalises. Every claim cites a file path and line number.
>
> **Headline finding (validated by POC migration):** `useAnalyticsEndpoint` only
> shrinks a file when the file has a critical mass of homogeneous fetchers
> (analytics had 14, all sharing the same `withSourceId` axis). For
> 6-fetcher files like `useWorkflowTemplates.ts`, the per-endpoint
> configuration ceremony (12 lines x N endpoints + bridge `watch()` + path
> factories for parameterised paths) **outweighs** the per-fetcher boilerplate
> savings. The composable still works correctly outside analytics — but the
> case for migrating files with <8 fetchers on LOC grounds alone is weak.
> See "POC migration measurement" below.

## Pattern under audit

```
loading.value = true
error.value = null
try {
  const url = await getBackendUrl(...) + '/api/...' [+ optional query/source-id]
  const resp = await fetchWithAuth(url, { method: 'GET', headers: {...} })
  if (!resp.ok) throw new Error(...)
  const data = await resp.json()
  state.value = pickField(data)
} catch (e) {
  error.value = String(e)
  logger.error(...)
} finally {
  loading.value = false
}
```

The `useAnalyticsEndpoint` composable generalises this exactly, with the
optional source-id wrap defaulting to `true` (intentionally — see #5111).

## Composable-by-composable findings

### 1. `autobot-frontend/src/composables/useWorkflowTemplates.ts` — 251 LOC

| Fetcher | Lines | Method | Pattern fit | Notes |
|---|---|---|---|---|
| `fetchTemplates(category?, tags?, complexity?)` | L41-66 | GET | EXACT | builds `URLSearchParams` from up to 3 optional filters; assigns `templates.value = data.templates \|\| []` |
| `fetchTemplateDetail(templateId)` | L68-85 | GET | EXACT (path-parameterised) | path `/api/templates/templates/${templateId}`; assigns `selectedTemplate.value = data.template`; also returns `data.template` to caller |
| `searchTemplates(query)` | L87-105 | GET | EXACT | encodes `q=...`; returns `data.results \|\| []` to caller (does NOT mutate state) |
| `fetchCategories()` | L107-117 | GET | EXACT | no error.value assignment (logs only); assigns `categories.value = data.categories \|\| []` |
| `fetchStats()` | L119-129 | GET | EXACT | no error.value assignment (logs only); no `loading` flag (silent) |
| `previewTemplate(templateId, variables?)` | L131-155 | GET | EXACT (path-parameterised) | optional JSON-stringified `variables` query param; assigns `preview.value = data` and returns it |
| `createWorkflowFromTemplate(templateId, variables?)` | L157-186 | POST | OUT OF SCOPE | mutating call |
| `executeTemplate(templateId, variables?, autoApprove)` | L188-218 | POST | OUT OF SCOPE | mutating call |

**Per-fetcher avg LOC (GETs only):** ~17 LOC each (six GETs span L41-155 = 115 LOC, ~19/fetcher counting blank lines).

**Per-call differences forcing opt-outs:**
- **No source scoping concept** — workflow templates are global. Every fetcher must pass `scopeToSource: false`. Requires also passing a no-op `withSourceId: (url) => url` deps shim because `useAnalyticsEndpoint`'s deps contract requires it.
- **`searchTemplates` and `previewTemplate` return values** instead of (or in addition to) populating module state. Migration must wrap `endpoint.load()` and read `endpoint.data.value` to preserve the return shape.
- **`fetchCategories` and `fetchStats` don't surface errors** to `error.value` (logger-only). Use `onError: () => {}` to suppress.
- **`fetchTemplateDetail` and `previewTemplate` paths are parameterised** (`/templates/${id}/...`) so the endpoint instance must be constructed inside the wrapper function rather than at module setup. This adds ~14 LOC per parameterised endpoint.
- **Loading flag is shared across all 6 GETs.** With `useAnalyticsEndpoint` each endpoint has its own `loading` ref, so a `watch([...endpoints.loading], (flags) => loading.value = flags.some(Boolean))` bridge is needed.
- **POSTs (`createWorkflowFromTemplate`, `executeTemplate`) are out of scope** — leave as-is.

**Migration verdict:** **POC** (proven works; LOC neutral-to-negative — see below).

---

### 2. `autobot-frontend/src/composables/usePatternAnalysis.ts` — 952 LOC

| Fetcher | Lines | Method | Pattern fit | Notes |
|---|---|---|---|---|
| `analyzePatterns(...)` | L214-350 | POST + 409 retry + poll | OUT OF SCOPE | full-blown background-task orchestration including stuck-task clearing |
| `pollTaskStatus(taskId)` | L358-485 | GET poll loop | OUT OF SCOPE | partial-result accumulation, not a one-shot fetcher |
| `getCachedSummary()` | L491-529 | GET | NEAR FIT | no `error.value` assignment, swallows errors as `logger.debug`; specifically wants to return `false` on miss without surfacing user-visible error |
| `getSummary(path?)` | L535-585 | GET (cached fast path) + background-task fallback | OUT OF SCOPE | composite |
| `getDuplicates(path?, minSim, limit)` | L590-622 | GET | EXACT | builds `URLSearchParams`; assigns `duplicatePatterns.value = data.duplicates \|\| []`; checks `data.status === 'success'` |
| `getRegexOpportunities(path?, limit)` | L627-655 | GET | EXACT | same shape as `getDuplicates`; assigns `regexOpportunities.value` |
| `getComplexityHotspots(path?, minComp, limit)` | L660-692 | GET | EXACT | same shape; assigns `complexityHotspots.value` |
| `getRefactoringSuggestions(path?, max)` | L697-725 | GET | EXACT | same shape; assigns `refactoringSuggestions.value` |
| `getStorageStats()` | L730-750 | GET | EXACT | no `error.value` assignment (logger-only) |
| `getReport(path?)` | L785-808 | GET | NEAR FIT | returns markdown string from `data.report`; no state mutation |
| `clearStorage()` | L755-780 | DELETE | OUT OF SCOPE | mutating |
| `clearStuckTasks(force)` | L870-889 | POST | OUT OF SCOPE | mutating |
| `listTasks()` | L895-909 | GET | NEAR FIT | returns full payload without state mutation; missing `error.value` |

**Per-fetcher avg LOC (the 4-5 EXACT GETs):** ~29 LOC each (`getDuplicates` is 33 LOC L590-622, `getRegexOpportunities` 29, `getComplexityHotspots` 33, `getRefactoringSuggestions` 29, `getStorageStats` 21).

**Per-call differences:**
- All GETs share a common `${backendUrl}/api/analytics/codebase/patterns/${endpoint}` prefix — cleaner extraction would also factor that.
- `data.status === 'success'` envelope — fits `pickData` exactly.
- No source-id concept — `scopeToSource: false` opt-out everywhere.
- Coexists with `useBackgroundTask` (already used at L157 for the summary task).

**Migration verdict:** **OK** — heavier per-fetcher boilerplate (~29 LOC each vs ~17 in workflowTemplates) means the configuration ceremony breaks even sooner. Still, file is huge (952 LOC) with complex POST+poll orchestration intermixed; risk of confusing the migration scope. Better as a follow-up with its own PR. With ~5 fetchers, expect roughly LOC-neutral after migration (same pattern as POC, slightly better per-fetcher density).

---

### 3. `autobot-frontend/src/composables/useVoiceProfiles.ts` — 171 LOC

| Fetcher | Lines | Method | Pattern fit | Notes |
|---|---|---|---|---|
| `fetchVoices()` | L52-69 | GET | EXACT | unusual: stores error string from `res.status` then `return` (no throw); falls through to `data.voices \|\| []` shape with array|object polymorphism (L62: `Array.isArray(data) ? data : (data.voices \|\| [])`) |
| `createVoice(name, blob, filename)` | L77-106 | POST FormData | OUT OF SCOPE | mutating, multipart |
| `deleteVoice(voiceId)` | L108-131 | DELETE | OUT OF SCOPE | mutating |
| `fetchPersonalityVoice()` | L138-153 | GET | NEAR FIT | doesn't set `loading` or `error`; on `!res.ok` resets `personalityVoiceId.value = ''` (no error surface); writes to TWO refs: `personalityVoiceId` + `personalityVoiceIds` |

**Per-fetcher avg LOC:** `fetchVoices` ~18 LOC, `fetchPersonalityVoice` ~16 LOC.

**Per-call differences forcing opt-outs:**
- Module-level singleton state (L28-37) — `useAnalyticsEndpoint` already returns a fresh instance per call site, so the singleton refs (`voices`, `selectedVoiceId`) would still need to be assigned via `onSuccess`.
- `fetchVoices` polymorphic response shape (`Array \| { voices: [...] }`) → handled inside `pickData`.
- `fetchPersonalityVoice` writes to two refs and quietly clears them on failure — needs `onSuccess` + `onError: () => { personalityVoiceId.value=''; personalityVoiceIds.value={} }`.
- No `scopeToSource`.

**Migration verdict:** **SKIP** — only 2 fetchers, both small (16-18 LOC). The configuration ceremony for `useAnalyticsEndpoint` (~12 LOC per endpoint setup + deps shim) would make the file LARGER, not smaller. Defer until either (a) more voice GETs are added, or (b) the rehomed `useFetchEndpoint` ships with default `scopeToSource: false` (eliminating one config field per call).

---

### 4. `autobot-frontend/src/composables/useKnowledgeCollaboration.ts` — 305 LOC

Uses `ApiClient` (`@/utils/ApiClient`) not `fetchWithAuth` — all 9 fetchers (L69-289) use `apiClient.get/post/put/delete` which already returns parsed JSON. The boilerplate is the loading/error try-catch block, not the fetch sequence.

**Per-fetcher avg LOC:** ~15 LOC each (5 GETs at L69-152, L220-262 + 4 POST/PUT/DELETEs).

**Why `useAnalyticsEndpoint` does NOT fit:**
- L67 instantiates a per-call `new ApiClient()` — completely different transport contract.
- `apiClient.get<T>()` returns `Promise<T>`, not `Response`; there is no `if (!resp.ok) throw` step.
- All callers re-throw the error after surfacing to `error.value` (L94, L121, L148, L172, L194, L216, L233, L257, L286) — `useAnalyticsEndpoint` swallows errors into `error.value` and returns `void`, breaking the throw contract that 100% of consumers rely on.

**Migration verdict:** **SKIP** — wrong abstraction layer. The duplication here is the loading/error try-catch wrapper around an already-typed client. That's a separate primitive (it overlaps with `useApi`/`useApiLoading`/`useUnifiedLoading`; see #5108). Filing this is a job for whoever resolves #5108.

---

### 5. `autobot-frontend/src/composables/useVncControls.ts` — 201 LOC

Uses `ApiClient` not `fetchWithAuth`. 8 actions (L50-186) each follow:
```
loading = true; error = null
try { return await ApiClient.post<VncActionResponse>(path, params) }
catch { error = ...; return { status: 'error', message: ... } }
finally { loading = false }
```

**Why it does NOT fit:**
- 7 of 8 actions are POST (single-shot RPCs); only `captureScreenshot` (L145-163) is GET.
- All actions return a structured `VncActionResponse` envelope on both success AND error (L60-63, L78-81, etc.) — they NEVER throw, NEVER set `data.value`, callers expect a sync return value.
- This is the inverse of `useAnalyticsEndpoint` — error becomes a payload, not a state side-effect.

**Migration verdict:** **SKIP** — wrong shape entirely. Could be normalised against a generic POST helper, but that's not the boilerplate this audit is about.

---

### 6. `autobot-frontend/src/composables/useOperationsApi.ts` — 376 LOC

Uses `useApiWithState()` (from `./useApi`) — already wrapped at L31, L139. Every fetcher delegates to `withErrorHandling(...)` (L38, L67, L83, L98, L113).

**Why it does NOT fit:**
- `withErrorHandling` (an existing abstraction) already handles loading/error/fallback for these calls — adding `useAnalyticsEndpoint` on top would be a fourth loading abstraction stacked on the third (see Recommendations).
- The `useOperationsState` wrapper at L189-209 (`loadOperations`) does have raw `loading.value=true` / `try / catch / finally`, but it calls into `operationsApi.listOperations(...)` which is itself wrapped — adding another wrapper here would deepen the stack.

**Migration verdict:** **SKIP** — already abstracted. Reconcile via #5108 instead.

---

### 7. `autobot-frontend/src/composables/useServiceManagement.ts` — 325 LOC

Does NOT call `fetchWithAuth` at all. All HTTP goes through `redisServiceAPI` (L15-19, an existing service object). Three actions (`startService`/`stopService`/`restartService` at L132-219) each have an identical 28-line wrapper:
```
loading=true; error=null
try { result = await redisServiceAPI.X()
      if (result.success) { await refreshStatus(); return result }
      throw new Error(...)
} catch { logger.error; error = msg; showSubtleErrorNotification; throw }
finally { loading = false }
```

**Why it does NOT fit:**
- The action result `ServiceOperationResult` has its own `.success` envelope handled separately from `!ok`.
- All actions also call `refreshStatus()` on success — a side-effect, not data assignment.
- Actions throw on failure; `useAnalyticsEndpoint` swallows.

**Migration verdict:** **SKIP** — pattern overlap is real (28 LOC x 3 = 84 LOC of repeated wrapper) but the abstraction wanted here is a "withSideEffectAndToast" helper, not a GET-fetcher. File a separate refactor issue if anyone cares.

---

### 8. `autobot-frontend/src/composables/useServiceMessages.ts` — 177 LOC

Uses `useApiWithState()` (L55) + `withErrorHandling()` wrappers (L74-90, L107-114, L122-133). Same shape as `useOperationsApi`.

**Migration verdict:** **SKIP** — already abstracted via `useApi`. See #5108.

---

### 9. `autobot-frontend/src/composables/useEvolution.ts` — 333 LOC

Uses **axios** (L13, L94-100), not `fetchWithAuth`. All 6 fetchers (L125-288) use `api.get`/`api.post` from an axios instance.

**Migration verdict:** **SKIP** — completely different transport. Either migrate axios -> `fetchWithAuth` first (separate refactor, would expose this composable to the audit) or accept the divergence.

---

### 10. `autobot-frontend/src/composables/useAnalyticsFetch.ts` — 127 LOC (the older attempt)

**Reconciliation note** for the open design question in #5154.

`useAnalyticsFetch` (older, narrower) and `useAnalyticsEndpoint` (newer, the #5137 abstraction) are **siblings doing 90% the same job**:

| Aspect | `useAnalyticsFetch` (L58-125) | `useAnalyticsEndpoint` (L89-144) |
|---|---|---|
| Backend URL resolution | `appConfig.getServiceUrl('backend')` with SSOT fallback (L25-32) | `appConfig.getServiceUrl('backend')` only (L106) |
| HTTP method | GET or POST (`opts.method`, L70) | GET only |
| POST body | `JSON.stringify(body)` (L91) | Not supported |
| Source scoping | NONE | `withSourceId` injected via deps (L108-110) — defaults TRUE |
| Query params | `URLSearchParams` (L80-82) | hand-rolled `appendQueryExtras` preserving existing `?` (L70-87) |
| Status branching | `extract` returning `T \| undefined` -> `null` (L101-106) | `pickData` returning `TOut \| null` + `onSuccess`/`onNoData`/`onError` callbacks |
| Return value | `T \| null` from `load()` | `void` from `load()`; consumer reads `endpoint.data.value` |
| Reset | `reset()` exposed (L118-122) | Not exposed (callers reassign refs) |
| Error type | `ComputedRef<string \| null>` (multi-error array) | `Ref<string>` (single error) |
| Logger label | derived from `path` | explicit `opts.label` |

**Active consumers of `useAnalyticsFetch` (5):**
- `autobot-frontend/src/composables/analytics/useCodeIntelScores.ts` (L16, used 5x — security/performance/redis)
- `autobot-frontend/src/composables/analytics/useOwnershipAnalysis.ts`
- `autobot-frontend/src/composables/analytics/useConfigDuplicates.ts`
- `autobot-frontend/src/composables/analytics/useApiEndpointAnalysis.ts`
- `autobot-frontend/src/composables/analytics/useSourceRegistry.ts`

**Status:** Both helpers live under `composables/` (one at root, one nested), both used inside `analytics/`. `useAnalyticsFetch` is NOT dead code; it has 5 consumers. The two abstractions have meaningfully different APIs (return-from-load vs side-effect-into-data, single vs multi-error, POST support vs GET-only) so a mechanical merge would break consumers.

**Recommendation:** see Recommendations section below.

---

## Composables NOT in the candidate list but inspected

The grep `fetchWithAuth(\(` across `composables/` (excluding `analytics/` and tests) found 9 hits. Beyond the ones above, the additional finds are:

- `useBackgroundTask.ts` (290 LOC) — a **complementary** primitive (POST `/analyze` -> poll `/status/{id}`). Not the same boilerplate as `useAnalyticsEndpoint`; this is the *other* recurring pattern (#1304). Keep separate.
- `useCommandApproval.ts` (418 LOC) — POST `/approve` + custom 50s polling loop with `AbortController`. SKIP (custom polling).
- `useToolApproval.ts` (138 LOC) — single POST submit driven by `LiveEventService` subscription. SKIP (event-driven, not GET-fetcher).
- `useVoiceConversation.ts` (895 LOC) — POST FormData transcribe + WebSocket signaling. SKIP.
- `useVoiceOutput.ts` (331 LOC) — POST FormData TTS + WebSocket streaming. SKIP.

None of these fit the GET-fetcher boilerplate.

---

## POC migration measurement (corrects pre-migration estimates)

The POC migration in this PR migrated `useWorkflowTemplates.ts` (6 GETs).
Measured outcome:

| Metric | Before | After | Delta |
|---|---|---|---|
| File LOC | 251 | 337 | **+86 (+34%)** |
| Per-fetcher avg LOC (GETs) | ~17 | ~24 (config + wrapper combined) | **+7/fetcher** |
| New TS errors introduced | n/a | **0** (baseline 2 errors unchanged) | 0 |
| Public API changes | n/a | **0** (all exports preserved) | 0 |
| Behavioural changes | n/a | **1 micro** — `selectedTemplate` reset to `null` (was `undefined`) on missing template | minimal |

**Why the migration grew the file** (this contradicts the audit's first-pass
estimate of -70 LOC):

1. **Module-level endpoint construction adds ~12 LOC per fixed-path endpoint** (4 endpoints x ~12 = 48 LOC). The original try/catch was ~14 LOC; the saved 14-LOC body is replaced by an 8-line wrapper PLUS the 12-line module-level config — net +6/fetcher.
2. **Path-parameterised endpoints** (`fetchTemplateDetail`, `previewTemplate`) cannot be hoisted to module level — they must be constructed inside the wrapper function, costing ~14 LOC each. Original try/catch was ~16 LOC. Net loss is small per-fetcher but eats most of the structural win.
3. **Loading-flag bridge** — composable-level `loading` ref exists but each endpoint owns its own `loading`. A `watch([endpoint.loading, ...], (flags) => loading.value = flags.some(Boolean))` block costs ~12 LOC.
4. **`noScope` deps shim** required by the deps contract even though `scopeToSource: false` skips `withSourceId` — 1 LOC, but signals API friction.

**Why analytics achieved -40% but workflow templates broke even:**
analytics had **14 fetchers** all sharing the same `withSourceId` axis, so the
configuration ceremony amortises across many call sites and the `withSourceId`
wrap (mandatory for analytics, free at config time) is pure savings.
Workflow templates have **6 fetchers** with no source-id, so the ceremony
doesn't amortise and the wrap is dead weight.

**Critical mass threshold (estimated):** `useAnalyticsEndpoint` starts saving
LOC at roughly **>= 8 GET fetchers per file** (where 8 is N such that `12 +
12*N + N*8 < N*16`, i.e. fixed overhead + per-endpoint config + wrapper LOC
beats raw try/catch LOC). Below that threshold, the migration is value-add
ONLY for **bug-prevention** (forced `pickData` typing, structural `withSourceId`
opt-out, single fetcher contract reviewable in one place).

**The POC is still a successful proof point** that the composable generalises
outside analytics: zero new type errors, zero public API breakage, behavioural
parity, opt-outs work. It demonstrates the composable is correct outside its
home domain. **It does NOT validate that migrating sub-critical-mass files is
worth doing on LOC grounds.**

---

## Summary table

| Composable | Total LOC | GET-fetchers fitting pattern | Estimated saved LOC | Verdict |
|---|---|---|---|---|
| `useWorkflowTemplates.ts` | 251 -> **337** (POC migrated) | 6 | **-86** (file grew) | **POC** (works; LOC-negative) |
| `usePatternAnalysis.ts` | 952 | 4-5 | ~0 (LOC-neutral or negative) | **DEFER** until rehomed `useFetchEndpoint` lands |
| `useVoiceProfiles.ts` | 171 | 2 | NEGATIVE | **SKIP** — too few fetchers |
| `useKnowledgeCollaboration.ts` | 305 | 0 (different transport) | 0 | SKIP — see #5108 |
| `useVncControls.ts` | 201 | 0 (POST envelopes) | 0 | SKIP |
| `useOperationsApi.ts` | 376 | 0 (already wrapped) | 0 | SKIP — see #5108 |
| `useServiceManagement.ts` | 325 | 0 (different abstraction) | 0 | SKIP |
| `useServiceMessages.ts` | 177 | 0 (already wrapped) | 0 | SKIP — see #5108 |
| `useEvolution.ts` | 333 | 0 (axios) | 0 | SKIP |
| `useAnalyticsFetch.ts` | 127 | (peer abstraction) | (reconciliation only) | see Recommendations |
| `useBackgroundTask.ts` | 290 | (different pattern: POST+poll) | 0 | SKIP — complementary |
| `useCommandApproval.ts` | 418 | 0 (custom polling) | 0 | SKIP |
| `useToolApproval.ts` | 138 | 0 (event-driven) | 0 | SKIP |
| `useVoiceConversation.ts` | 895 | 0 (WebSocket + FormData) | 0 | SKIP |
| `useVoiceOutput.ts` | 331 | 0 (WebSocket + FormData) | 0 | SKIP |

**Realistic LOC-savings ROI across all candidates: roughly NEGATIVE-to-zero**
unless a target file with 8+ GET fetchers is found. None exists in the current
non-analytics composable set.

The genuine wins from a broader migration are **uniformity** (one
fetcher pattern instead of five — `useAnalyticsEndpoint`, `useAnalyticsFetch`,
`useApi+withErrorHandling`, raw fetchWithAuth, axios), **bug prevention**
(`pickData` enforces typed transformation, `scopeToSource` opt-out is
structural), and **testability** (one composable to mock instead of multiple
inline `fetch` calls). LOC reduction is NOT the right metric for sub-critical-mass
migrations.

---

## Recommendations (answers to the open design questions in #5154)

### 1. Should `useAnalyticsEndpoint` be rehomed to `composables/api/useFetchEndpoint.ts`?

**Yes — but in a follow-up PR, not this one.** Specifically:

1. Move the file to `autobot-frontend/src/composables/api/useFetchEndpoint.ts`.
2. Rename the export to `useFetchEndpoint<TRaw, TOut>` and the option type to `UseFetchEndpointOptions`.
3. **Make the `deps` parameter optional** — when no `deps` is passed, default to `{ withSourceId: (url) => url }`. This eliminates the `noScope` shim that the POC migration had to write.
4. **Default `scopeToSource: false`** for the renamed root-level composable (see #3 below).
5. Re-export from `composables/analytics/useAnalyticsEndpoint.ts` as a deprecated alias for one release cycle to avoid a 16-call-site churn. The alias should set `scopeToSource: true` by default to preserve analytics-domain semantics.
6. Update analytics consumers in a separate batch.

**This PR uses the existing import path** (`@/composables/analytics/useAnalyticsEndpoint`) deliberately — proving the composable generalises does NOT require renaming it. Rehoming is a mechanical rename that should be its own reviewable change.

The POC migration also surfaces a UX gap for the rehome: the **mandatory `deps` parameter** (forcing every non-analytics caller to write `{ withSourceId: (url) => url }`) is friction that should disappear when `scopeToSource: false` is the default. Without that ergonomic fix, the rehomed composable will keep accumulating `noScope`-style shims at every call site.

### 2. What's the relationship between `useAnalyticsEndpoint`, `useAnalyticsFetch`, `useApi`, `useApiLoading`, `useUnifiedLoading`?

This audit only **describes** the overlap — the rationalisation is #5108's job. Current state:

- **`useApi` / `useApiWithState`** — wraps `fetch` with auth headers; provides `withErrorHandling(fn, opts)` for "fallback-on-error" pattern. Used by `useOperationsApi`, `useServiceMessages`, others. Does NOT manage `loading`/`error` state for caller — caller wraps it.
- **`useApiLoading`** — issue #5108 says this is subsumed by `useUnifiedLoading`; both manage loading flags + structured `ApiError`.
- **`useUnifiedLoading`** — newer, broader; includes structured error envelope.
- **`useAnalyticsFetch`** — narrow GET/POST helper that returns a `{ data, loading, error, load, reset }` tuple, errors go into a multi-error array, `extract` callback transforms response.
- **`useAnalyticsEndpoint`** — newer (#5137); GET-only; tuple is `{ data, loading, error, load }`; errors go into single string; `pickData` callback transforms response, plus `onSuccess`/`onNoData`/`onError` lifecycle hooks; first-class source-id scoping.

**The overlap:** `useAnalyticsEndpoint` is a strict subset of `useAnalyticsFetch` for GETs, plus an opinionated `withSourceId` wrap and lifecycle hooks. They do not differ in capability so much as in API shape. A single unified `useFetchEndpoint` could be designed but every existing caller would need to migrate.

**Recommendation for #5108:** treat the four-helper sprawl (`useApi` / `useApiLoading` / `useUnifiedLoading` / `useAnalyticsEndpoint` / `useAnalyticsFetch`) as one decision. Pick ONE to be the canonical "fetch with reactive loading + error state" composable. Until that decision lands, this audit recommends `useAnalyticsEndpoint` as the GET-fetcher choice because it is the most recently designed (knows about #5111), the most opinionated (less misuse surface), and already validated by 14 successful migrations.

### 3. Should `scopeToSource` flip from default-true to default-false when generalised?

**Yes — when (and only when) the rename to `useFetchEndpoint` happens.**

- `useAnalyticsEndpoint` defaults `scopeToSource: true` because the analytics domain has a stable `withSourceId(url)` injection point and the #5111 bug class proved that "forgot to scope" is a recurring footgun. **Inside analytics, default-true is correct.**
- For non-analytics callers (workflow templates, voice profiles, pattern analysis, etc.), there is no `source_id` concept at all. Default-true would force every non-analytics caller to type `scopeToSource: false` AND provide a `noScope` deps shim — both pure noise.
- When rehomed to `composables/api/useFetchEndpoint.ts`, the default should flip to `scopeToSource: false`, AND the `deps.withSourceId` parameter should become optional (defaulting to identity).
- The analytics re-export (deprecated alias) should keep `scopeToSource: true` as its default by passing it explicitly in a thin wrapper, preserving the analytics-domain bug-prevention behaviour.

In this PR, the POC migration (`useWorkflowTemplates`) opts out of source scoping explicitly via `scopeToSource: false` AND constructs a module-level `noScope = { withSourceId: (url) => url }` shim — demonstrating that BOTH friction points need addressing before the composable can be ergonomically used outside analytics.

---

## POC migration scope (this PR)

**Migrated:** `autobot-frontend/src/composables/useWorkflowTemplates.ts`

**Migrated fetchers (all GETs):**
- `fetchTemplates` -> module-level `templatesEndpoint.load(query)`
- `fetchTemplateDetail` -> per-call factory + `data.value` read (path-parameterised)
- `searchTemplates` -> module-level `searchEndpoint.load({ q })` + read `data.value`
- `fetchCategories` -> module-level `categoriesEndpoint.load()`
- `fetchStats` -> module-level `statsEndpoint.load()`
- `previewTemplate` -> per-call factory + `data.value` read (path-parameterised)

**NOT migrated (intentional, out of scope):**
- `createWorkflowFromTemplate` (POST)
- `executeTemplate` (POST)
- `initializeTemplates` (orchestration helper that calls the GET-migrated functions)

**Public API preservation:**
All exported function names, signatures, and return types are unchanged. Verified by grepping `useWorkflowTemplates` across `autobot-frontend/src` — three consumers (`useWorkflowBuilder.ts`, `WorkflowTemplateGallery.vue`, `WorkflowBuilderView.vue`) destructure named methods (`fetchTemplates`, `searchTemplates`, `fetchCategories`, `fetchTemplateDetail`, `createWorkflowFromTemplate`, `executeTemplate`); none need changes.

**Type-check (`npx vue-tsc --noEmit -p tsconfig.app.json`):** zero new errors in the migrated file. Baseline 2 errors (one pre-existing `vue` import resolution issue from #5096, one pre-existing `c => c.display_name` implicit-any on the `categoryNames` computed) remain unchanged.

**LOC delta (`wc -l`):** 251 LOC -> 337 LOC = +86. The migration grew the file because the per-endpoint configuration ceremony for `useAnalyticsEndpoint` (12 lines x N endpoints + bridge `watch()` + path-parameterised factories + `noScope` shim) outweighed the per-fetcher boilerplate savings for a 6-fetcher file. See "POC migration measurement" above for the critical-mass analysis.

**Why ship the POC anyway:** it answers the design questions in #5154 with empirical data. Specifically: (a) it proves the composable WORKS outside analytics, (b) it surfaces the two ergonomic gaps (`scopeToSource` default, `deps` mandatory) that must be fixed when rehoming, (c) it sets a critical-mass expectation for follow-up migrations. Reverting the POC would leave the design questions unanswered and the architectural team would re-derive these findings from first principles next time.
