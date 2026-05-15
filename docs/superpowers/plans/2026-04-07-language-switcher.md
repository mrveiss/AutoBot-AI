# Language Switcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a globe icon to the nav bar that lets users switch UI language, fixing the broken language dropdown and enabling cross-device language sync via the personality profile.

**Architecture:** A new `useAvailableLanguages` composable derives the language list from frontend locale files using `Intl.DisplayNames` for native names. A `LanguageSwitcher.vue` component renders as an icon-button with dropdown (desktop) or inline row (mobile). Cross-device sync is added to `usePreferences` — on login, the personality profile's `language_code` is fetched and applied if it differs from the current locale.

**Tech Stack:** Vue 3 Composition API, vue-i18n, Pinia (userStore), Intl.DisplayNames (browser built-in), Vitest + @vue/test-utils

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `src/composables/useAvailableLanguages.ts` | Language list from locale files + Intl.DisplayNames |
| Create | `src/composables/__tests__/useAvailableLanguages.test.ts` | Unit tests for composable |
| Create | `src/components/layout/LanguageSwitcher.vue` | Globe icon button + dropdown |
| Modify | `src/i18n/locales/en.json` | Add `nav.switchLanguage` key |
| Modify | `src/App.vue` | Add LanguageSwitcher to desktop nav + mobile menu; call loadLanguageFromBackend after login |
| Modify | `src/composables/usePreferences.ts` | Add + export `loadLanguageFromBackend()` |
| Modify | `src/components/settings/LanguageSettingsPanel.vue` | Replace `/personality/languages` fetch with `useAvailableLanguages()` |

All paths relative to `autobot-frontend/`.

---

## Task 1: Add i18n translation key

**Files:**
- Modify: `autobot-frontend/src/i18n/locales/en.json`

- [ ] **Step 1: Add the key**

Open `src/i18n/locales/en.json`. Find the `"nav"` object. Add one key at the end of the object (before the closing `}`):

```json
"switchLanguage": "Switch language"
```

The `nav` object should now end with:
```json
    "profileSettings": "Profile Settings",
    "switchLanguage": "Switch language"
```

- [ ] **Step 2: Verify JSON is valid**

```bash
cd autobot-frontend
python3 -c "import json; json.load(open('src/i18n/locales/en.json')); print('valid')"
```

Expected: `valid`

- [ ] **Step 3: Commit**

```bash
cd autobot-frontend
git add src/i18n/locales/en.json
git commit -m "feat(i18n): add nav.switchLanguage translation key"
```

---

## Task 2: Create useAvailableLanguages composable + tests

**Files:**
- Create: `autobot-frontend/src/composables/useAvailableLanguages.ts`
- Create: `autobot-frontend/src/composables/__tests__/useAvailableLanguages.test.ts`

- [ ] **Step 1: Write the failing test**

Create `autobot-frontend/src/composables/__tests__/useAvailableLanguages.test.ts`:

```typescript
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useAvailableLanguages } from '../useAvailableLanguages'

// Mock SUPPORTED_LOCALES so tests don't depend on disk files
vi.mock('@/i18n', () => ({
  SUPPORTED_LOCALES: ['ar', 'de', 'en', 'fr']
}))

describe('useAvailableLanguages', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns one entry per supported locale', () => {
    const { languages } = useAvailableLanguages()
    expect(languages.value).toHaveLength(4)
    expect(languages.value.map(l => l.code)).toEqual(['ar', 'de', 'en', 'fr'])
  })

  it('each entry has a non-empty name string', () => {
    const { languages } = useAvailableLanguages()
    for (const lang of languages.value) {
      expect(typeof lang.name).toBe('string')
      expect(lang.name.length).toBeGreaterThan(0)
    }
  })

  it('falls back to locale code when Intl.DisplayNames returns undefined', () => {
    // Simulate a browser that returns undefined for an unknown code
    const spy = vi.spyOn(Intl, 'DisplayNames').mockImplementation(() => ({
      of: () => undefined,
      resolvedOptions: () => ({} as any)
    }))

    const { languages } = useAvailableLanguages()
    expect(languages.value[0].name).toBe('ar')

    spy.mockRestore()
  })

  it('en locale produces an English name', () => {
    const { languages } = useAvailableLanguages()
    const en = languages.value.find(l => l.code === 'en')
    expect(en).toBeDefined()
    // Intl.DisplayNames(['en'], { type: 'language' }).of('en') → 'English'
    expect(en!.name).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd autobot-frontend
npm run test:unit -- --run src/composables/__tests__/useAvailableLanguages.test.ts
```

Expected: FAIL — `Cannot find module '../useAvailableLanguages'`

- [ ] **Step 3: Create the composable**

Create `autobot-frontend/src/composables/useAvailableLanguages.ts`:

```typescript
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { computed } from 'vue'
import { SUPPORTED_LOCALES } from '@/i18n'

export interface AvailableLanguage {
  code: string
  name: string
}

export function useAvailableLanguages() {
  const languages = computed<AvailableLanguage[]>(() =>
    SUPPORTED_LOCALES.map(code => ({
      code,
      name: new Intl.DisplayNames([code], { type: 'language' }).of(code) ?? code
    }))
  )

  return { languages }
}
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
cd autobot-frontend
npm run test:unit -- --run src/composables/__tests__/useAvailableLanguages.test.ts
```

Expected: 4 tests pass

- [ ] **Step 5: Commit**

```bash
cd autobot-frontend
git add src/composables/useAvailableLanguages.ts src/composables/__tests__/useAvailableLanguages.test.ts
git commit -m "feat(i18n): add useAvailableLanguages composable with Intl.DisplayNames"
```

---

## Task 3: Create LanguageSwitcher component

**Files:**
- Create: `autobot-frontend/src/components/layout/LanguageSwitcher.vue`

- [ ] **Step 1: Create the component**

Create `autobot-frontend/src/components/layout/LanguageSwitcher.vue`:

```vue
<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss

LanguageSwitcher.vue - Globe icon language switcher for nav bar
-->

<template>
  <div class="language-switcher" :class="{ 'language-switcher--mobile': mobile }">
    <!-- Desktop: icon button that opens dropdown -->
    <template v-if="!mobile">
      <button
        ref="triggerRef"
        @click="toggleDropdown"
        class="lang-trigger"
        :aria-label="t('nav.switchLanguage')"
        :aria-expanded="open"
        aria-haspopup="listbox"
      >
        <i class="fas fa-globe" aria-hidden="true"></i>
      </button>

      <Transition name="lang-dropdown">
        <ul
          v-if="open"
          ref="dropdownRef"
          role="listbox"
          class="lang-dropdown"
          :aria-label="t('nav.switchLanguage')"
        >
          <li
            v-for="lang in languages"
            :key="lang.code"
            role="option"
            :aria-selected="lang.code === currentLanguage"
            class="lang-option"
            :class="{ 'lang-option--active': lang.code === currentLanguage }"
            @click="select(lang.code)"
          >
            <i
              v-if="lang.code === currentLanguage"
              class="fas fa-check lang-option__check"
              aria-hidden="true"
            ></i>
            <span class="lang-option__name">{{ lang.name }}</span>
          </li>
        </ul>
      </Transition>
    </template>

    <!-- Mobile: inline row with select -->
    <template v-else>
      <div class="lang-mobile-row">
        <i class="fas fa-globe lang-mobile-icon" aria-hidden="true"></i>
        <select
          :value="currentLanguage"
          @change="select(($event.target as HTMLSelectElement).value)"
          class="lang-mobile-select"
          :aria-label="t('nav.switchLanguage')"
        >
          <option
            v-for="lang in languages"
            :key="lang.code"
            :value="lang.code"
          >
            {{ lang.name }}
          </option>
        </select>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePreferences } from '@/composables/usePreferences'
import { useAvailableLanguages } from '@/composables/useAvailableLanguages'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('LanguageSwitcher')

defineProps<{ mobile?: boolean }>()

const { t } = useI18n()
const { language, setLanguage } = usePreferences()
const { languages } = useAvailableLanguages()

const open = ref(false)
const triggerRef = ref<HTMLElement | null>(null)
const dropdownRef = ref<HTMLElement | null>(null)

const currentLanguage = computed(() => language.value)

function toggleDropdown() {
  open.value = !open.value
}

async function select(code: string) {
  open.value = false
  if (code === currentLanguage.value) return
  try {
    await setLanguage(code)
  } catch (err) {
    logger.error('Failed to switch language', err)
  }
}

function handleOutsideClick(event: MouseEvent) {
  const target = event.target as Node
  if (
    triggerRef.value && !triggerRef.value.contains(target) &&
    dropdownRef.value && !dropdownRef.value.contains(target)
  ) {
    open.value = false
  }
}

onMounted(() => document.addEventListener('click', handleOutsideClick))
onUnmounted(() => document.removeEventListener('click', handleOutsideClick))
</script>

<style scoped>
.language-switcher {
  position: relative;
}

.lang-trigger {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  background-color: rgba(255, 255, 255, 0.1);
  color: white;
  font-size: 18px;
  transition: all 0.2s ease;
  cursor: pointer;
}

.lang-trigger:hover {
  background-color: rgba(255, 255, 255, 0.2);
  transform: scale(1.05);
}

.lang-trigger:focus-visible {
  outline: 2px solid white;
  outline-offset: 2px;
}

.lang-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 160px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  z-index: 100;
  padding: var(--spacing-xs) 0;
  list-style: none;
  margin: 0;
}

.lang-option {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  cursor: pointer;
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  transition: background 0.15s;
}

.lang-option:hover {
  background: var(--bg-tertiary);
}

.lang-option--active {
  color: var(--color-primary);
  font-weight: 600;
}

.lang-option__check {
  font-size: var(--font-size-xs);
  color: var(--color-primary);
  width: 12px;
}

.lang-option__name {
  flex: 1;
}

/* Mobile row */
.lang-mobile-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  color: var(--text-primary);
}

.lang-mobile-icon {
  width: 16px;
  text-align: center;
}

.lang-mobile-select {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  appearance: none;
}

.lang-mobile-select:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
  border-radius: var(--radius-sm);
}

/* Dropdown transition */
.lang-dropdown-enter-active,
.lang-dropdown-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.lang-dropdown-enter-from,
.lang-dropdown-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
```

- [ ] **Step 2: Verify no TypeScript errors**

```bash
cd autobot-frontend
npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep -i "LanguageSwitcher\|language-switcher" || echo "no errors for this file"
```

Expected: `no errors for this file` (or silence)

- [ ] **Step 3: Commit**

```bash
cd autobot-frontend
git add src/components/layout/LanguageSwitcher.vue
git commit -m "feat(i18n): add LanguageSwitcher component with desktop/mobile modes"
```

---

## Task 4: Wire LanguageSwitcher into App.vue

**Files:**
- Modify: `autobot-frontend/src/App.vue`

- [ ] **Step 1: Register the component**

In `src/App.vue`, in the `components:` object (around line 420), add `LanguageSwitcher` alongside `DarkModeToggle`:

Find:
```typescript
    DarkModeToggle: defineAsyncComponent(() => import('@/components/ui/DarkModeToggle.vue')),
```

Replace with:
```typescript
    DarkModeToggle: defineAsyncComponent(() => import('@/components/ui/DarkModeToggle.vue')),
    LanguageSwitcher: defineAsyncComponent(() => import('@/components/layout/LanguageSwitcher.vue')),
```

- [ ] **Step 2: Add to desktop nav**

In `src/App.vue`, find the desktop nav right-side controls (around line 102). The current structure is:

```html
            <!-- Dark Mode Toggle -->
            <DarkModeToggle />

            <!-- Mobile menu button -->
```

Insert `LanguageSwitcher` between `DarkModeToggle` and the mobile menu button:

```html
            <!-- Dark Mode Toggle -->
            <DarkModeToggle />

            <!-- Language Switcher -->
            <LanguageSwitcher />

            <!-- Mobile menu button -->
```

- [ ] **Step 3: Add to mobile menu**

In `src/App.vue`, find the mobile nav panel (around line 177). The Profile Settings button is the last item before `</div>`. Add the language switcher row just before it:

Find:
```html
            <!-- Profile Settings (Issue #950) -->
            <button
              v-if="userStore.isAuthenticated"
              @click="showProfileModal = true; closeMobileNav()"
```

Insert before it:
```html
            <!-- Language Switcher -->
            <LanguageSwitcher :mobile="true" />

            <!-- Profile Settings (Issue #950) -->
            <button
              v-if="userStore.isAuthenticated"
              @click="showProfileModal = true; closeMobileNav()"
```

- [ ] **Step 4: Verify the build compiles**

```bash
cd autobot-frontend
npm run build-only 2>&1 | tail -10
```

Expected: No errors. May show warnings about bundle size — acceptable.

- [ ] **Step 5: Commit**

```bash
cd autobot-frontend
git add src/App.vue
git commit -m "feat(i18n): wire LanguageSwitcher into desktop nav and mobile menu"
```

---

## Task 5: Add cross-device language sync on login

**Files:**
- Modify: `autobot-frontend/src/composables/usePreferences.ts`
- Modify: `autobot-frontend/src/App.vue`

- [ ] **Step 1: Add loadLanguageFromBackend to usePreferences**

In `src/composables/usePreferences.ts`, add this function after `syncLanguageToBackend` (after line 141):

```typescript
/**
 * Fetch language preference from backend personality profile and apply it.
 * Called after login to enable cross-device language sync.
 */
async function loadLanguageFromBackend(): Promise<void> {
  try {
    const res = await apiClient.get(`${getApiBase()}/personality/active`)
    const code: string | undefined = res.data?.language_code
    if (code && code !== language.value) {
      await setLanguage(code)
      logger.debug(`Language loaded from backend: ${code}`)
    }
  } catch (error) {
    logger.warn('Could not load language from backend', error)
  }
}
```

Then export it from the `usePreferences()` return object. Find the `return {` block (around line 226) and add `loadLanguageFromBackend` to the Actions section:

```typescript
  return {
    // State
    fontSize,
    accentColor,
    layoutDensity,
    voiceDisplayMode,
    language,

    // Actions
    setFontSize,
    setAccentColor,
    setLayoutDensity,
    setVoiceDisplayMode,
    setLanguage,
    loadLanguageFromBackend,
    resetPreferences
  }
```

- [ ] **Step 2: Call it in App.vue after login**

In `src/App.vue`, the preferences are lazy-loaded at setup. Replace the existing preferences initialization block (around line 434):

Find:
```typescript
    // Initialize user preferences system (Issue #753)
    import('@/composables/usePreferences').then(({ usePreferences }) => {
      usePreferences();
      logger.debug('User preferences system initialized');
    });
```

Replace with:
```typescript
    // Initialize user preferences system (Issue #753)
    import('@/composables/usePreferences').then(({ usePreferences }) => {
      const prefs = usePreferences();
      logger.debug('User preferences system initialized');

      // Cross-device language sync: load stored language from backend after login (#1675)
      watch(
        () => userStore.isAuthenticated,
        async (authenticated) => {
          if (authenticated) {
            await prefs.loadLanguageFromBackend();
          }
        },
        { immediate: true }
      );
    });
```

`watch` is already imported at line 384 (`import { ref, computed, onMounted, onUnmounted, defineAsyncComponent } from 'vue'`). Add `watch` to the existing import:

Find:
```typescript
import { ref, computed, onMounted, onUnmounted, defineAsyncComponent } from 'vue';
```

Replace with:
```typescript
import { ref, computed, watch, onMounted, onUnmounted, defineAsyncComponent } from 'vue';
```

- [ ] **Step 3: Verify TypeScript**

```bash
cd autobot-frontend
npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep -i "usePreferences\|App.vue" | head -10 || echo "no errors"
```

Expected: no errors

- [ ] **Step 4: Commit**

```bash
cd autobot-frontend
git add src/composables/usePreferences.ts src/App.vue
git commit -m "feat(i18n): cross-device language sync via personality profile on login"
```

---

## Task 6: Fix LanguageSettingsPanel to use useAvailableLanguages

**Files:**
- Modify: `autobot-frontend/src/components/settings/LanguageSettingsPanel.vue`

The current panel fetches from `/personality/languages` (16 languages, 5 without locale files), causing the dropdown to fall back to `{ en: 'English' }`. Replace this with `useAvailableLanguages()`.

- [ ] **Step 1: Update the script section**

In `src/components/settings/LanguageSettingsPanel.vue`, replace the entire `<script setup lang="ts">` block:

Find:
```typescript
<script setup lang="ts">
// Issue #1331: Use usePreferences for language persistence
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePreferences } from '@/composables/usePreferences'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('LanguageSettingsPanel')
const { t } = useI18n()
const { language, setLanguage } = usePreferences()

const selectedLanguage = ref(language.value)
const languages = ref<Record<string, string>>({ en: 'English' })
const announcement = ref('')
const statusMessage = ref('')
const statusType = ref<'success' | 'error'>('success')

onMounted(async () => {
  try {
    const response = await apiClient.get(`${getApiBase()}/personality/languages`)
    if (response.data && typeof response.data === 'object') {
      languages.value = response.data
    }
  } catch (error) {
    logger.error('Failed to load supported languages', error)
  }
})
```

Replace with:
```typescript
<script setup lang="ts">
// Issue #1331: Use usePreferences for language persistence
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePreferences } from '@/composables/usePreferences'
import { useAvailableLanguages } from '@/composables/useAvailableLanguages'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('LanguageSettingsPanel')
const { t } = useI18n()
const { language, setLanguage } = usePreferences()
const { languages: availableLanguages } = useAvailableLanguages()

const selectedLanguage = ref(language.value)
// Convert to Record<string,string> for the existing template's v-for="(name, code) in languages"
const languages = computed<Record<string, string>>(() =>
  Object.fromEntries(availableLanguages.value.map(l => [l.code, l.name]))
)
const announcement = ref('')
const statusMessage = ref('')
const statusType = ref<'success' | 'error'>('success')
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd autobot-frontend
npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep -i "LanguageSettings" | head -10 || echo "no errors"
```

Expected: no errors

- [ ] **Step 3: Run all unit tests to confirm nothing broken**

```bash
cd autobot-frontend
npm run test:unit 2>&1 | tail -15
```

Expected: All existing tests pass (new test from Task 2 included).

- [ ] **Step 4: Commit**

```bash
cd autobot-frontend
git add src/components/settings/LanguageSettingsPanel.vue
git commit -m "fix(i18n): use useAvailableLanguages in LanguageSettingsPanel — fixes empty dropdown (#1675)"
```

---

## Self-Review

**Spec coverage:**
- Section 1 (LanguageSwitcher placement): Tasks 3 + 4 ✓
- Section 2 (useAvailableLanguages + Intl.DisplayNames): Task 2 ✓
- Section 3 (cross-device sync on login): Task 5 ✓
- Section 4 (RTL): handled by existing `setLocale()` called inside `setLanguage()` — no new code needed ✓
- LanguageSettingsPanel fix: Task 6 ✓

**No placeholders found.**

**Type consistency:**
- `useAvailableLanguages()` returns `{ languages: ComputedRef<AvailableLanguage[]> }` — used consistently in Task 3 and Task 6
- `loadLanguageFromBackend()` is added to usePreferences return and called in App.vue — consistent
- `setLanguage` signature is `(code: string) => Promise<void>` — awaited correctly in LanguageSwitcher and loadLanguageFromBackend
