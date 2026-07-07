# Task 8 Report — Frontend System Health Panel (#10932)

## Status: DONE

**Commit:** `2e4379e65` — `feat(content-reach): frontend System Health panel for CONTENT_REACH probe (#10932)`

## Gate Results

| Gate | Result |
|---|---|
| `npm run type-check` | PASS — 0 errors |
| `npm run lint:oxlint` | PASS — 0 warnings/errors |
| `npm run lint:eslint` | PASS — 0 warnings/errors (auto-fixed 2 pre-existing missing i18n keys in chat.citations.*) |
| `npm run test:unit -- SystemHealthView` | PASS — 2/2 tests green |
| `npm run check:i18n` | PASS — All translation keys found in en.json |

## Files Changed

- `autobot-frontend/src/types/probe-names.ts` — Added `CONTENT_REACH: 'content_reach'`
- `autobot-frontend/src/views/SystemHealthView.vue` — New admin view (script-setup, fully typed, no `any`)
- `autobot-frontend/src/views/__tests__/SystemHealthView.spec.ts` — New spec: 2 tests (sources/live/dead + unavailable path)
- `autobot-frontend/src/router/index.ts` — Route `/admin/system-health` (name `admin-system-health`, meta: requiresAuth, admin, hideInNav)
- `autobot-frontend/src/config/navItems.ts` — `{ to: '/admin/system-health', labelKey: 'nav.systemHealth', iconStroke: true }` added to adminMenuItems
- `autobot-frontend/src/i18n/locales/en.json` — Added `nav.systemHealth` + `admin.systemHealth` block (14 keys)
- `autobot-frontend/src/i18n/locales/{ar,de,es,fa,fr,he,lv,pl,pt,ur}.json` — Same keys added to all 11 locales

---

## Review Fixes — Commit `d05a779ec`

**Commit:** `d05a779ec` — `fix(content-reach): render degraded/down probe status in System Health panel + runtime-narrow probe data (#10932)`

### Fix 1 — Fidelity: degraded/down probes now reach buildHealthy
- Added `renderNonOkFromProbe?: boolean` (default: undefined/false) to `ProbeBackedHealthOptions<R>`.
- When true: `buildHealthy` is called for any found probe regardless of status; `buildUnavailable` reserved for missing probe or fetch error.
- When false/absent: exact pre-existing behavior (`ok`→buildHealthy, else buildUnavailable). All other consumers unaffected.
- `SystemHealthView.vue` passes `renderNonOkFromProbe: true` so degraded/down status + sources/live render correctly.

### Fix 2 — Type safety: runtime-narrowing for data.sources / data.live
- Added `toSourceMap(v: unknown): Record<string, string[]>` helper in `SystemHealthView.vue`.
- Replaces `data.sources as Record<string,string[]>` / `data.live as ...` unchecked casts. No `any`.

### Fix 3 — Tests
- `useProbeBackedHealth.test.ts`: 3 new tests under `renderNonOkFromProbe option` describe block — degraded→buildHealthy (flag true), missing probe→buildUnavailable (flag true), degraded→buildUnavailable (flag absent/legacy).
- `SystemHealthView.spec.ts`: 2 new tests — Degraded badge, Down badge with real status strings.
- Total: 13 tests green (9 composable + 4 view).

### Gate Results (review fixes)

| Gate | Result |
|---|---|
| `npm run type-check` | PASS — 0 errors |
| `npm run lint:oxlint` | PASS — 0 |
| `npm run lint:eslint` | PASS — 0 |
| `npm run test:unit -- useProbeBackedHealth SystemHealthView` | PASS — 13/13 green |
| `npm run check:i18n` | PASS — All keys found |
| Pre-existing consumer failures (baseline) | 2 pre-existing failures unrelated to these changes (RedisServiceControl.spec.js, useModal.test.ts) — confirmed present before changes via git stash baseline run |

---

## Concerns / Notes

- Pre-existing `chat.citations.modelOnly` and `chat.citations.modelOnlyTooltip` keys were missing from en.json and were fixed as a side effect (Rule 6: fix pre-existing issues discovered along the way).
- The view uses Tailwind utility classes matching the existing SystemHealthView.vue template style (already present in the file when the worktree was created).
- Backend Tasks 1–7 are already live; this is a read-only UI surface only.
