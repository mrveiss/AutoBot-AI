# Content Reach — Task 8 (Frontend doctor/status panel) Plan

**Goal:** Surface the backend `CONTENT_REACH` health probe in the UI — a standalone admin System Health view showing per-source/per-backend live status. Umbrella #10932. Makes the layer 100% end-to-end (backend capability → visible in app).

**Constraints:** reuse `useProbeBackedHealth` (no new fetch plumbing); all user-facing strings via `$t()` with keys in ALL 11 locales; clear the frontend gate — `type-check` (vue-tsc), `lint` (oxlint `-D correctness` + eslint, 0 warnings), `test:unit` (vitest), `check:i18n`. No commit trailers (mrveiss). Commit `feat(content-reach): <desc> (#10932)`.

## Given (from scout)
- `useProbeBackedHealth<R>({ probeName, buildHealthy, buildUnavailable, errorMessage })` → returns `() => Promise<R>`. `ProbeResponse = { name, status?, data?, detail? }`. Example consumer: `useBatchProcessing.ts`.
- `PROBE_NAMES` in `src/types/probe-names.ts` (add `CONTENT_REACH: 'content_reach'`).
- content_reach probe `data`: `{ sources: {source: [backend...]}, live: {source: [live backend...]} }`, `status` ∈ ok/degraded/down.
- No existing system-health view → create standalone admin view.
- Router admin pattern: `src/router/index.ts` (~line 856); nav: `src/config/navItems.ts` `adminMenuItems` (~line 108).
- Locales: 11 files in `src/i18n/locales/` (ar,de,en,es,fa,fr,he,lv,pl,pt,ur).
- Test pattern: `src/composables/__tests__/useProbeBackedHealth.test.ts`, `@vue/test-utils` `mount`.
- Node/npm present; node_modules symlinked into the worktree.

## Files
1. **`src/types/probe-names.ts`** — add `CONTENT_REACH: 'content_reach',` to `PROBE_NAMES`.
2. **`src/views/SystemHealthView.vue`** (new) — admin view:
   - Use `useProbeBackedHealth<ContentReachHealth>({ probeName: PROBE_NAMES.CONTENT_REACH, buildHealthy: (probe, data) => ({ status: probe.status ?? 'unavailable', detail: probe.detail, sources: data.sources ?? {}, live: data.live ?? {} }), buildUnavailable: (message) => ({ status: 'unavailable', detail: message, sources: {}, live: {} }), errorMessage: t('admin.systemHealth.error') })`.
   - On mount + a refresh button: call the getter, store reactive state (loading/error/data).
   - Render: overall status badge (ok/degraded/down/unavailable, color-coded), `detail`; then a grid/list of sources — for each source in `data.sources`, show the source name and each backend as live (present in `data.live[source]`) or dead (in sources but not live), with a per-source health indicator. Reuse `components/admin/HealthBar.vue` if it fits, else a simple badge grid.
   - Loading + error + empty states. ALL strings via `$t('admin.systemHealth.*')`. `<script setup lang="ts">`.
3. **`src/router/index.ts`** — add route: `{ path: '/admin/system-health', name: 'admin-system-health', component: () => import('@/views/SystemHealthView.vue'), meta: { title: 'System Health', hideInNav: true, requiresAuth: true, admin: true } }`.
4. **`src/config/navItems.ts`** — add to `adminMenuItems`: `{ to: '/admin/system-health', labelKey: 'nav.systemHealth', icon: <existing icon convention> }`.
5. **i18n** — add to ALL 11 locale files (translate reasonably; en canonical):
   - `nav.systemHealth`, and an `admin.systemHealth` block: `title`, `subtitle`, `status`, `sources`, `live`, `backends`, `healthy`, `degraded`, `down`, `unavailable`, `loading`, `error`, `refresh`, `noSources`.
6. **`src/views/__tests__/SystemHealthView.spec.ts`** (new) — mount the view with `useProbeBackedHealth` mocked to resolve a fake content_reach health (2 sources, one with a dead backend); assert the sources + live/dead backends render and the status badge shows. Also a test for the unavailable/error path. Mock i18n (`$t` → key or global mock) per existing view-test convention.

## Verification gate (run ALL from `autobot-frontend/`)
- `npm run type-check` → 0 errors.
- `npm run lint:oxlint` and `npm run lint:eslint` → 0 warnings/errors (fix any). (`--max-warnings 0` posture per #9924.)
- `npm run test:unit -- SystemHealthView` (and the full run if fast) → green.
- `npm run check:i18n` → passes (all keys present in all locales, no orphans).

## Out of scope
Backend already live (Tasks 1–7). This is purely the read-only UI surface.
