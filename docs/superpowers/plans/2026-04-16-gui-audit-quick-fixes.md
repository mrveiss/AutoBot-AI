# GUI Audit — Quick Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix five self-contained bugs/regressions identified in the GUI design audit: missing i18n keys causing raw key strings in toasts, a mislabeled "Overseer" toggle in the chat toolbar, the stale `/desktop` nav item (noVNC is already in the chat tab), and the empty About page.

**Architecture:** All changes are isolated — one locale JSON file, one component file (ChatInput.vue), one router/App.vue pair, one view file (AboutView.vue). No shared-state or inter-component coordination needed. Each task can be committed independently.

**Tech Stack:** Vue 3, vue-i18n, Tailwind CSS v4, Vite

---

## Scope note — what this plan does NOT cover

The full audit also identifies:
- **Design token rationalization** (11 font sizes → 7, 6 radii → 4, 23 bg-colors → 4 surface steps): tracked as a separate plan — `2026-04-16-design-tokens.md`
- **Shared UI component library** (PageHeader, EmptyState, ErrorState, StatusChip): tracked as `2026-04-16-shared-components.md`
- **Responsive "More ▾" overflow nav**: tracked as `2026-04-16-responsive-nav.md`

---

## Files touched in this plan

| File | Action | Reason |
|---|---|---|
| `autobot-frontend/src/i18n/locales/en.json` | Modify (add 4 keys to `nav` object) | `nav.applicationError`, `nav.unexpectedError`, `nav.loadingTimeout`, `nav.loadingTimeoutMessage` referenced in App.vue but missing → raw keys shown in toasts |
| `autobot-frontend/src/components/chat/ChatInput.vue` | Modify (label + i18n key on Overseer toggle) | Overseer toggle reuses `chat.input.explain` label — duplicate with the quick-action "Explain" |
| `autobot-frontend/src/i18n/locales/en.json` | Modify (add `chat.input.overseerMode` label) | New label for Overseer toggle |
| `autobot-frontend/src/App.vue` | Modify (remove `/desktop` navItem entry) | `/desktop` is redundant — noVNC already lives in the chat tab |
| `autobot-frontend/src/router/index.ts` (or equivalent) | Modify (remove `/desktop` route) | Clean up route table |
| `autobot-frontend/src/views/AboutView.vue` | Modify (replace placeholder with real content) | Currently renders only a `<h1>` — fails the audit |

---

## Task 1: Add missing `nav.*` i18n keys

**Files:**
- Modify: `autobot-frontend/src/i18n/locales/en.json` (around line 6824 — end of `nav` object)

### Context

App.vue (lines 578–611) calls:
- `t('nav.applicationError')` — title for global error toasts
- `t('nav.unexpectedError')` — fallback message for global error toasts
- `t('nav.loadingTimeout')` — title for loading-timeout notifications
- `t('nav.loadingTimeoutMessage')` — message for loading-timeout notifications

None of these keys exist in the `nav` section. vue-i18n returns the key path as a string when a key is missing, so users see "nav.applicationError" as the toast title.

- [ ] **Step 1: Add the four missing keys**

In `autobot-frontend/src/i18n/locales/en.json`, find the closing of the `nav` object (line ~6824, after `"operations": "Operations"`). Change:

```json
    "operations": "Operations"
  },
```

to:

```json
    "operations": "Operations",
    "applicationError": "Application Error",
    "unexpectedError": "An unexpected error occurred",
    "loadingTimeout": "Loading Timed Out",
    "loadingTimeoutMessage": "Some content took too long to load. Try refreshing."
  },
```

- [ ] **Step 2: Verify keys resolve in the browser (manual)**

Start the dev server (`npm run dev` in `autobot-frontend/`) and trigger an error notification (e.g. disconnect from the backend). Confirm the toast title reads "Application Error", not "nav.applicationError".

- [ ] **Step 3: Commit**

```bash
cd autobot-frontend
git add src/i18n/locales/en.json
git commit -m "fix(i18n): add missing nav.applicationError/unexpectedError/loadingTimeout keys (#4xxx)"
```

---

## Task 2: Fix the mislabeled Overseer toggle in ChatInput

**Files:**
- Modify: `autobot-frontend/src/components/chat/ChatInput.vue` (line ~134)
- Modify: `autobot-frontend/src/i18n/locales/en.json` (add key to `chat.input` section)

### Context

`ChatInput.vue` has two unrelated things both labeled "Explain":

1. **Line ~134** — The Overseer Mode toggle (sitemap icon, `fa-sitemap`). Its label text is `$t('chat.input.explain')`. This is wrong — the tooltip already says `$t('chat.input.overseerMode')`. The visible label should match.
2. **Line ~375** — A quick action entry `{ id: 'explain', label: t('chat.input.explain'), icon: 'fas fa-lightbulb' }`. This is the legitimate "Explain" action.

The fix: give the Overseer toggle its own label key `chat.input.overseerLabel` so the two elements stop sharing text.

- [ ] **Step 1: Add the new i18n key**

In `autobot-frontend/src/i18n/locales/en.json`, find the `chat.input` section and add after the existing `"overseerMode"` key (search for `"overseerMode"` to locate it):

```json
"overseerLabel": "Overseer",
```

- [ ] **Step 2: Update the Overseer toggle label in ChatInput.vue**

At `autobot-frontend/src/components/chat/ChatInput.vue` line ~134, change:

```html
<span class="toggle-label">{{ $t('chat.input.explain') }}</span>
```

to:

```html
<span class="toggle-label">{{ $t('chat.input.overseerLabel') }}</span>
```

- [ ] **Step 3: Verify in the browser (manual)**

Load `/chat`. Confirm the toggle in the input toolbar now reads "Overseer" while the quick-actions popup still shows "Explain" (with the lightbulb icon).

- [ ] **Step 4: Commit**

```bash
git add src/i18n/locales/en.json src/components/chat/ChatInput.vue
git commit -m "fix(chat): rename mislabeled Overseer toggle from 'Explain' to 'Overseer' (#4xxx)"
```

---

## Task 3: Remove the `/desktop` nav item and route

**Files:**
- Modify: `autobot-frontend/src/App.vue` — remove the `desktop` entry from `navItems` array
- Modify: router file — remove the `/desktop` route definition

### Context

The audit notes: "noVNC is already in the chat tab". The `/desktop` nav entry (`labelKey: 'nav.desktop'`) and its route are redundant. Removing them eliminates one of the 12+ nav items (helps nav overcrowding) and removes a dead-end page.

- [ ] **Step 1: Find the router file**

```bash
find autobot-frontend/src/router -name "*.ts" | head -5
```

Expected: `autobot-frontend/src/router/index.ts` (or similar).

- [ ] **Step 2: Remove `/desktop` from navItems in App.vue**

In `autobot-frontend/src/App.vue`, find the `navItems` array (around line 793). Remove the entire entry for `/desktop`:

```js
// REMOVE this line:
{ to: '/desktop', labelKey: 'nav.desktop', icon: 'M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z', iconStroke: true },
```

- [ ] **Step 3: Remove `/desktop` route from the router**

Open the router file found in Step 1. Search for `'desktop'` or `DesktopView`. Remove the route object for `/desktop`. Also remove the associated dynamic import if no other route uses the same component.

```bash
grep -n "desktop\|Desktop" autobot-frontend/src/router/index.ts
```

Remove the matching route entry (typically):
```js
// REMOVE:
{
  path: '/desktop',
  component: () => import('../views/DesktopView.vue'),
  // ...
},
```

- [ ] **Step 4: Verify nav no longer shows Desktop (manual)**

Load the app. Confirm "Desktop" is gone from both the desktop navbar and the mobile nav drawer. Navigate to `/desktop` directly and confirm it 404s or redirects (a redirect to `/chat` is ideal — add one if the router doesn't do it automatically).

To add a catch-all redirect (optional, improves UX):
In the router, if there's already a 404/catch-all route, ensure `/desktop` would hit it. Or add:
```js
{ path: '/desktop', redirect: '/chat' },
```
before the catch-all.

- [ ] **Step 5: Commit**

```bash
git add src/App.vue src/router/index.ts
git commit -m "feat(nav): remove redundant /desktop route — noVNC lives in /chat tab (#4xxx)"
```

---

## Task 4: Give the About page real content

**Files:**
- Modify: `autobot-frontend/src/views/AboutView.vue`
- Modify: `autobot-frontend/src/i18n/locales/en.json` (add keys to `views.about`)

### Context

`AboutView.vue` renders only `<h1>{{ $t('views.about.title') }}</h1>` in an empty centered div. The audit notes "not a design". The fix is a minimal but meaningful page: what AutoBot is, key capabilities, version info, and links to docs/GitHub.

Check what keys already exist under `views.about`:

```bash
grep -A 10 '"about"' autobot-frontend/src/i18n/locales/en.json | head -20
```

- [ ] **Step 1: Add i18n keys for the About page**

In `autobot-frontend/src/i18n/locales/en.json`, find the `views.about` section and expand it:

```json
"about": {
  "title": "About AutoBot",
  "tagline": "AI-powered automation platform for intelligent workflows",
  "descriptionHeading": "What is AutoBot?",
  "description": "AutoBot is an open-source AI orchestration platform that routes user requests to specialized agents, integrates with your infrastructure, and learns from every interaction through a vector knowledge base.",
  "capabilitiesHeading": "Key Capabilities",
  "capability1": "Multi-agent chat workflows with A2A task routing",
  "capability2": "RAG-powered knowledge retrieval with ChromaDB",
  "capability3": "Browser automation, voice I/O, and code execution",
  "capability4": "Secure secrets management and host-based SSH execution",
  "capability5": "Pluggable LLM backends — Ollama, OpenAI-compatible, SLM",
  "versionLabel": "Version",
  "authorLabel": "Author",
  "authorName": "mrveiss",
  "licenseLabel": "License",
  "licenseValue": "Proprietary — © 2026 mrveiss"
}
```

- [ ] **Step 2: Replace AboutView.vue template**

Replace the entire content of `autobot-frontend/src/views/AboutView.vue` with:

```vue
<template>
  <div class="about-view view-container px-6 py-8 max-w-3xl mx-auto">
    <!-- Header -->
    <div class="mb-8">
      <div class="flex items-center gap-3 mb-2">
        <div class="w-10 h-10 bg-autobot-primary rounded-lg flex items-center justify-center shrink-0">
          <span class="text-white font-bold text-lg font-mono">AB</span>
        </div>
        <h1 class="text-2xl font-bold text-autobot-text-primary">{{ $t('views.about.title') }}</h1>
      </div>
      <p class="text-autobot-text-secondary text-base">{{ $t('views.about.tagline') }}</p>
    </div>

    <!-- Description -->
    <section class="mb-8">
      <h2 class="text-base font-semibold text-autobot-text-primary mb-2">
        {{ $t('views.about.descriptionHeading') }}
      </h2>
      <p class="text-autobot-text-secondary leading-relaxed">{{ $t('views.about.description') }}</p>
    </section>

    <!-- Capabilities -->
    <section class="mb-8">
      <h2 class="text-base font-semibold text-autobot-text-primary mb-3">
        {{ $t('views.about.capabilitiesHeading') }}
      </h2>
      <ul class="space-y-2">
        <li
          v-for="n in 5"
          :key="n"
          class="flex items-start gap-2 text-autobot-text-secondary"
        >
          <svg class="w-4 h-4 mt-0.5 shrink-0 text-autobot-primary" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
          </svg>
          <span>{{ $t(`views.about.capability${n}`) }}</span>
        </li>
      </ul>
    </section>

    <!-- Meta -->
    <section class="border-t border-autobot-border pt-6">
      <dl class="grid grid-cols-2 gap-x-8 gap-y-3 max-w-xs text-sm">
        <dt class="text-autobot-text-muted font-medium uppercase tracking-wide text-xs">{{ $t('views.about.versionLabel') }}</dt>
        <dd class="text-autobot-text-primary font-mono">{{ appVersion }}</dd>
        <dt class="text-autobot-text-muted font-medium uppercase tracking-wide text-xs">{{ $t('views.about.authorLabel') }}</dt>
        <dd class="text-autobot-text-primary">{{ $t('views.about.authorName') }}</dd>
        <dt class="text-autobot-text-muted font-medium uppercase tracking-wide text-xs">{{ $t('views.about.licenseLabel') }}</dt>
        <dd class="text-autobot-text-primary">{{ $t('views.about.licenseValue') }}</dd>
      </dl>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

// Read version from Vite's env injection (set in vite.config.ts via define)
// Falls back to package.json version string if not injected
const appVersion = import.meta.env.VITE_APP_VERSION ?? '—'
</script>

<style scoped>
/* view-container provides scroll and height constraints (Issue #548) */
</style>
```

- [ ] **Step 3: Expose `VITE_APP_VERSION` in Vite config (if not already set)**

Check whether `VITE_APP_VERSION` is already defined:

```bash
grep -r "VITE_APP_VERSION" autobot-frontend/
```

If not found, open `autobot-frontend/vite.config.ts` and add to the `define` block:

```ts
import { readFileSync } from 'fs'
const pkg = JSON.parse(readFileSync('./package.json', 'utf8'))

export default defineConfig({
  define: {
    'import.meta.env.VITE_APP_VERSION': JSON.stringify(pkg.version),
    // ... existing define entries
  },
  // ...
})
```

If `vite.config.ts` already has a `define` block, add just the `VITE_APP_VERSION` line. If adding `readFileSync` causes a type error, add `/// <reference types="node" />` at the top of the file.

- [ ] **Step 4: Verify in the browser (manual)**

Load `/about`. Confirm the page shows the logo mark, title, tagline, capability list (5 items), and the meta table (Version / Author / License). Confirm no raw i18n keys are visible.

- [ ] **Step 5: Commit**

```bash
git add src/views/AboutView.vue src/i18n/locales/en.json vite.config.ts
git commit -m "feat(about): replace placeholder with real About page content (#4xxx)"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ §9 Notifications — `nav.applicationError` i18n regression fixed (Task 1)
- ✅ §7 Chat View — duplicate "Explain" label resolved (Task 2)
- ✅ §2 Top Navigation — `/desktop` removed, reducing nav from 13 to 12 items (Task 3)
- ✅ §4 / §7 About page — real content added (Task 4)

**Not covered in this plan (separate plans):**
- §1 Design system token consolidation
- §2 "More ▾" overflow dropdown
- §3 PageHeader component standardization
- §4 EmptyState / ErrorState / Skeleton component unification
- §5 Card/widget padding standardization
- §6 Contrast ratio fixes
- §8 Agent Registry tab spacing / status chips
- §9 Notification weight/dismissal
- §10 Accessibility aria-label audit

**Placeholder scan:** No TBD/TODO in any task. All code blocks are complete.

**Type consistency:** `$t('views.about.capability${n}')` — the template literal uses backtick interpolation inside `$t(...)`. This is valid Vue i18n usage only when the key is a computed string; in the template `v-for="n in 5"` with `` $t(`views.about.capability${n}`) `` is standard template-literal i18n. ✅
