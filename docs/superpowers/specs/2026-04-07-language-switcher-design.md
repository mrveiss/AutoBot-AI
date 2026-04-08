# Language Switcher Design

**Date:** 2026-04-07
**Author:** mrveiss
**Issue:** #3850 (web research settings UI) — language switcher is a parallel gap

---

## Overview

AutoBot has a full vue-i18n setup (11 locale files, RTL support, `usePreferences` persistence) but no UI control for switching languages. The `LanguageSettingsPanel` in Settings fetches from the backend `/personality/languages` endpoint which returns 16 languages — 5 of which have no frontend locale files — so the dropdown never populates past the fallback `{ en: 'English' }`.

This design adds a globe icon to the nav bar (desktop) and mobile menu (mobile) that lets users switch languages. It fixes the data-source mismatch, adds dynamic native-name rendering via `Intl.DisplayNames`, and wires in cross-device sync via the existing personality profile backend.

---

## Section 1 — Component Placement

### `LanguageSwitcher.vue`

New component at `autobot-frontend/src/components/layout/LanguageSwitcher.vue`.

**Desktop nav** (`App.vue` right-side controls, between `DarkModeToggle` and the profile button):
- Globe icon (`fa-globe`) only — no text label
- Click opens a dropdown listing all available languages
- Active language has a checkmark
- Selecting a language calls `setLanguage(code)` from `usePreferences`

**Mobile nav** (inside the hamburger menu):
- Full-row variant: globe icon + current language name + inline dropdown
- Activated via a `mobile` boolean prop on `LanguageSwitcher.vue`

```
Desktop:  [...] 🌐 ☀️ 👤 ☰
Mobile:   ☀️ 👤 ☰  →  hamburger: 🌐 English ▾  / other items
```

No changes to the existing desktop nav layout or spacing.

---

## Section 2 — Language Data Source

### `useAvailableLanguages.ts`

New composable at `autobot-frontend/src/composables/useAvailableLanguages.ts`.

Reads `SUPPORTED_LOCALES` from `i18n/index.ts` (auto-derived from locale files that actually exist) and generates display names via the browser's `Intl.DisplayNames` API:

```typescript
import { computed } from 'vue'
import { SUPPORTED_LOCALES } from '@/i18n'

export function useAvailableLanguages() {
  const languages = computed(() =>
    SUPPORTED_LOCALES.map(code => ({
      code,
      name: new Intl.DisplayNames([code], { type: 'language' }).of(code) ?? code
    }))
  )
  return { languages }
}
```

`Intl.DisplayNames([code], { type: 'language' }).of(code)` asks each language to name itself in its own script:
- `'de'` → `'Deutsch'`
- `'ar'` → `'العربية'`
- `'he'` → `'עברית'`

The `?? code` fallback covers any browser that doesn't support an obscure code.

**Why this fixes the dropdown:** `LanguageSettingsPanel` currently fetches from `/personality/languages` (16 entries, 5 with no locale files). Switch it to use `useAvailableLanguages()` instead — the list is always exactly the locales that exist, no backend call needed.

Adding a new locale file automatically adds it to the switcher with no further changes.

---

## Section 3 — Cross-Device Sync

Language preference already:
- Persists locally via `localStorage` (`usePreferences`)
- Syncs to backend on change via PUT `/personality/profiles/{id}` with `language_code`

The missing piece is **loading it back on login**.

In `usePreferences.ts`, `loadPreferences()` already fetches the active personality profile and is already called in `App.vue` on authentication. Add language application there:

```typescript
// usePreferences.ts — inside loadPreferences(), after profile data arrives
if (profile.language_code && profile.language_code !== locale.value) {
  await setLanguage(profile.language_code)
}
```

If the backend has `fr` saved and local is `en`, it silently switches to `fr` on first load. No conflict prompt — backend wins on login.

No new API calls or call sites needed.

---

## Section 4 — RTL Handling

RTL is already fully handled by the existing `setLocale()` → `getLocaleDir()` → `document.documentElement.dir` pipeline. No new work needed.

Arabic (`ar`), Farsi (`fa`), Hebrew (`he`), and Urdu (`ur`) are the RTL locales covered by `getLocaleDir()` in `i18n/index.ts`.

---

## Files Affected

| File | Change |
|------|--------|
| `autobot-frontend/src/components/layout/LanguageSwitcher.vue` | New component |
| `autobot-frontend/src/composables/useAvailableLanguages.ts` | New composable |
| `autobot-frontend/src/App.vue` | Add `<LanguageSwitcher>` to desktop nav + mobile menu |
| `autobot-frontend/src/composables/usePreferences.ts` | Apply `language_code` in `loadPreferences()` |
| `autobot-frontend/src/components/settings/LanguageSettingsPanel.vue` | Replace `/personality/languages` fetch with `useAvailableLanguages()` |

---

## Out of Scope

- Adding missing locale files for zh, ja, ko, ru, it, nl, hi (separate task)
- Completing partial translations for fa, he, ur (separate task)
- Backend SUPPORTED_LANGUAGES cleanup (can remain as-is; frontend no longer depends on it for the switcher)
