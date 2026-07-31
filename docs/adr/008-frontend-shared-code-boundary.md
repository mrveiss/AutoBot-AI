# ADR-008: Frontend Shared-Code Boundary Between the Two SPAs

## Status

**Status**: Accepted

## Date

**Date**: 2026-07-31

## Context

AutoBot ships two Vue 3 SPAs against two different backends:

| SPA | Audience | Primary backend |
|---|---|---|
| `autobot-frontend/` | end users (chat, knowledge, desktop, workflows) | autobot backend |
| `autobot-slm-frontend/` | fleet/control-plane operators | SLM backend (plus the autobot backend for admin tools) |

Issue #12653 (under umbrella #12645) asked whether the plumbing these two apps
each carry — HTTP client, config resolver, WebSocket singleton — is an internal
fork that should be collapsed into a shared package, and required this ADR
before any convergence work.

The question is not hypothetical: shared frontend packages already exist and are
already consumed by both apps via `file:` dependencies.

```
libs/autobot-ui           -> @autobot/ui        theme-agnostic components + a11y/form composables
autobot-plugins/vnc       -> @autobot/vnc       VNC viewer, toolbar, useVncControls
autobot-plugins/terminal  -> @autobot/terminal  xterm-based terminal surface
```

So the real decision is **where the boundary sits**, not whether sharing is
possible.

### Measured state (2026-07-31, `origin/Dev_new_gui`)

The three "copy-adapted plumbing" items named in #12653, measured on both sides:

| Concept | `autobot-frontend` | `autobot-slm-frontend` | Overlap |
|---|---|---|---|
| HTTP client | `src/utils/ApiClient.ts` (842 lines) | `src/utils/ApiClient.ts` (419 lines) | method *names* only |
| Config resolver | `src/config/ssot-config.ts` (787 lines) | `src/config/ssot-config.ts` (217 lines) | `getConfig`, `getBackendUrl` |
| WS singleton | `src/services/GlobalWebSocketService.ts` (839 lines) | `src/composables/useSlmWebSocket.ts` (415 lines) | reconnect/handler-registry shape |

The bodies have diverged along the axis that matters — **which system they talk
to and how they authenticate to it**:

- `autobot-frontend/src/utils/ApiClient.ts:191-232` resolves its base URL
  through service discovery, reads the token from the user auth store *with an
  expiry check* (`isRealAuthToken`, line 222), attaches an org-context header
  (`X-Organization-Id`, lines 330-331), and offers XHR upload progress
  (`UploadProgressEvent`, line 24).
- `autobot-slm-frontend/src/utils/ApiClient.ts:36-40,149` resolves
  `getSlmApiBase()`, reads `sessionStorage['slm_access_token']` with a
  `localStorage` fallback, and on 401 clears the SLM session keys and redirects
  to `/login`.
- `autobot-slm-frontend/src/config/ssot-config.ts:13-47` defines `SLMConfig`
  (Grafana/Prometheus URLs, VM roles, known hosts). `autobot-frontend`'s
  `AutoBotConfig` (`src/config/ssot-config.ts:228-257`) defines permission
  modes, approval records, VNC config and service discovery. The two schemas are
  near-disjoint.
- `autobot-slm-frontend/src/composables/useSlmWebSocket.ts:16,26` connects to the
  **SLM** backend's `/api/ws/events` and carries `SLMWebSocketMessage`;
  `GlobalWebSocketService.ts` connects to the **autobot** backend with a
  different message vocabulary.

These are not one capability implemented twice. They are per-app adapters whose
only genuine commonality is a shape (`get`/`post`/`rawRequest`, "singleton
socket with backoff"). Merging them would require a strategy object per app for
base URL, token source, 401 policy and message schema — i.e. re-introducing the
divergence as configuration, with a shared package that no longer has a single
coherent behaviour to test.

By contrast, the two items that *were* the same capability twice converged
cleanly:

- `useVncControls` existed in three places; #12931 gave the shared copy an
  injected transport and #12978 reduced the two app copies to re-export shims
  (`autobot-frontend/src/composables/useVncControls.ts:13-21`,
  `autobot-slm-frontend/src/composables/useVncControls.ts:13-21`).
- The `@autobot/ui` components carry no backend knowledge at all, so both apps
  consume them unchanged and supply their own design tokens.

The distinguishing property is visible in both successes: **the shared code
contains no knowledge of which backend it talks to or how that backend
authenticates.** Where it needs I/O, the consumer injects it.

## Decision

The shared-frontend boundary is drawn at **backend knowledge**.

1. **Shared** (in `libs/` or `autobot-plugins/`, consumed via `@autobot/*`):
   presentation, interaction, accessibility, and any behaviour expressible
   without naming a backend, a base URL, or a token store. Where such code needs
   I/O it takes an **injected transport** — the `@autobot/vnc` `useVncControls`
   pattern — never a client of its own.

2. **Per-app** (deliberately duplicated shape, not a fork): the HTTP client, the
   config/SSOT resolver, and the WebSocket singleton. Each app owns exactly one
   of each, and each encodes that app's origin resolution, token storage,
   401 policy and message schema. These files are permitted to look alike; they
   are not permitted to multiply within an app.

3. **One client per (app, backend) pair.** This is the rule that has teeth. An
   SPA that talks to two backends gets exactly two clients, and *no component
   may open its own transport*:

   | App | Backend | Canonical client |
   |---|---|---|
   | `autobot-frontend` | autobot | `src/utils/ApiClient.ts` |
   | `autobot-slm-frontend` | SLM | `src/utils/ApiClient.ts` (`slmApiClient`) |
   | `autobot-slm-frontend` | autobot | `src/composables/useAutobotApi.ts` |

   Endpoint paths and payload types for a backend live with that backend's
   client, not inline in the component that happens to call them first.

4. **Cross-app feature duplication is a product decision, not a refactor.** When
   the same capability is built in both SPAs and both copies are reachable by
   real users, converging them changes what someone sees. Such cases are
   escalated to the owner with both consumer sets identified; they are not
   resolved by picking the larger implementation.

### Alternatives Considered

1. **A shared `@autobot/core` package holding ApiClient + ssot-config + WS.**
   - Pros: one place to fix a transport bug; smaller total line count.
   - Cons: the measured divergence is entirely in backend identity, auth storage
     and 401 policy, so the package would be a strategy-injection shell with no
     behaviour of its own; a change for one app's auth model would need
     regression testing of the other app; it would fight #12420, which is
     actively standing up the SLM contract *inside* the SLM app.
   - Rejected: it converges the shape and leaves the semantics forked, which is
     the worse of the two outcomes.

2. **Full per-app copies with no shared packages at all.**
   - Pros: zero coupling.
   - Cons: contradicted by three shared packages already in production use, and
     by the `useVncControls` triplication that shipped a fix to one app only.
   - Rejected.

3. **Move the Advanced Control API contract into a new shared package.**
   - Pros: endpoint paths and enums would exist once across both SPAs.
   - Cons: requires a fourth `file:` dependency and lockfile edits in both apps;
     the two consumers still differ in transport and auth, so only ~150 lines of
     type declarations are actually shared; and it would settle by implication
     the open question in §"Deferred" below.
   - Deferred, not rejected — revisit if a third consumer appears.

## Consequences

### Positive

- A component that needs the network has exactly one place to go, per backend.
  The rule is checkable by grep (`fetch(` / `axios.create` outside a client).
- Shared packages stay testable in isolation, because none of them can reach a
  backend on their own.
- A transport bug in an app is fixed once for that app; a presentation bug in a
  shared component is fixed once for both.

### Negative

- The two `ApiClient.ts` files keep looking like duplicates to a reader (and to
  clone detectors), so each carries a header explaining that the similarity is
  intentional.
- Retry/timeout improvements must be ported by hand between the two clients.

### Neutral

- `libs/autobot-sdk-ts` (`@autobot/sdk`) remains an *external-consumer* SDK with
  its own build and test toolchain. It is not a dependency of either SPA and is
  not the home for in-app plumbing.

## Deferred — open owner decision

**Advanced Control is built twice and both copies are live.** This ADR
deliberately does not pick a survivor:

- `autobot-frontend/src/views/AdvancedControlView.vue` (1103 lines) +
  `src/composables/useAdvancedControl.ts` + `src/utils/AdvancedControlApiClient.ts`
  (458 lines, all 17 backend routes incl. emergency-stop, system status/health
  and the monitoring/desktop WebSocket helpers). Routed at
  `src/router/index.ts:843-853` — but `hideInNav: true`, and no other file in
  the app links to it, so it is reachable only by typing the URL.
- `autobot-slm-frontend/src/views/tools/admin/AdvancedControlTool.vue`
  (504 lines, 12 of the 17 routes — no `takeover/.../action`, no
  `system/status`, `system/health` or `system/emergency-stop`, no info
  route). Routed at `src/router/index.ts:476-482`
  **and** listed in the operator tool nav at `src/views/tools/ToolsLayout.vue:26`
  — this is the copy an operator actually reaches.

So the fuller implementation is the less reachable one. Converging them either
removes a feature set from the surface that has users, or promotes a nav-hidden
admin view into the product. Both are product calls.

## Implementation Notes

### Key files

- `libs/autobot-ui/index.ts` — shared component/composable kit, no backend knowledge.
- `autobot-plugins/vnc/src/composables/useVncControls.ts` — injected-transport reference implementation.
- `autobot-slm-frontend/src/composables/useAutobotApi.ts` — the SLM app's single client for the autobot backend.
- `autobot-frontend/src/utils/ApiClient.ts`, `autobot-slm-frontend/src/utils/ApiClient.ts` — per-app clients, intentionally similar.

### Applying rule 3

`AdvancedControlTool.vue` previously carried a private `fetch` helper that sent
only `authStore.token` — no `autobot_access_token` fallback, no 401 cleanup, no
timeout — while every other SLM admin tool went through `useAutobotApi`. Under
rule 3 the endpoints and payload types moved onto `useAutobotApi` and the tool
calls it, which also removed that auth divergence.

## Related ADRs

- [ADR-005](005-single-frontend-mandate.md) - Single frontend server mandate (deployment topology; this ADR covers source-code sharing).

---

**Author**: mrveiss
**Copyright**: © 2025-2026 mrveiss
