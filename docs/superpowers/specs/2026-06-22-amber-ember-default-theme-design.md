# Amber/Ember default theme for the user GUI — design (#10461)

**Date:** 2026-06-22
**Issue:** #10461 (follow-up to #8988 theme system, #9929 umbrella; design source #9274 "Ember")
**Status:** Phase 1 design — approved decisions captured below

## Goal

Make the warm amber **Ember** palette the **default theme for the AutoBot user GUI**, while the
`/slm` (Service Lifecycle Manager) control plane keeps its current look. Users can switch themes
from user settings.

## Decisions (from brainstorming)

- **Design source = Ember (#9274) as-is.** Reuse the already-built `ember` variant
  (marigold `#C4651A`, apricot-linen `#F5EEDE` light surfaces, mulberry-plum `#1E1418` dark,
  gold `#ECA22A`). No new palette work. Its light mode is the warm cream/amber "pastel" look.
- **Phased.** This spec is **Phase 1** (Ember default + user switching). The pluggable
  "upload theme folder/zip via /slm, install, runtime-deliver" subsystem is **Phase 2** with its
  own spec → plan → PR.
- **`/slm` is a separate frontend deployment.** This `autobot-frontend` app contains only one
  embedded `/slm/tools/novnc` tool and a single Vite entry; the SLM control plane is served
  separately (`VITE_SLM_HOST`). So defaulting this app to Ember = defaulting the **user GUI**;
  the SLM GUI is unaffected automatically.

## Approach (chosen: A)

Flip the default variant in the **existing** `data-theme-variant` system, made env-overridable.
Ember is already a registered variant with CSS, persistence, and a working switcher — so this is a
small, reversible change, not a new subsystem.

Rejected: (B) route/area-scoped default — unnecessary, `/slm` is already separate (YAGNI);
(C) hardcode `data-theme-variant="ember"` in `index.html` — breaks the default-vs-chosen logic and
no-flash init.

## Architecture (reused, unchanged subsystems)

- `src/assets/css/themes/ember.css` — palette tokens, gated on `[data-theme-variant="ember"]`.
- `src/composables/useThemeVariant.ts` — reactive variant state, localStorage persistence, applies
  `data-theme-variant` to `<html>`.
- `src/theme-variant-init.ts` — pre-mount no-flash bootstrap (module script in `index.html`).
- `src/components/theme/EmberThemeToggle.vue` — generic switcher (iterates `availableVariants`),
  already mounted in `src/components/ui/PreferencesPanel.vue`.

## Changes

1. **`useThemeVariant.ts`** — `DEFAULT_VARIANT = (import.meta.env.VITE_DEFAULT_THEME_VARIANT as ThemeVariant) || 'ember'`.
   `loadThemeVariant()` already returns `DEFAULT_VARIANT` when nothing is stored; ensure an unknown
   stored value or invalid env value falls back to `'ember'`.
2. **`theme-variant-init.ts`** — when no stored variant, apply the env default (`'ember'`) to
   `<html data-theme-variant>` before mount, so first paint is Ember with no flash. Vite inlines
   `import.meta.env.VITE_DEFAULT_THEME_VARIANT` at build.
3. **User settings** — the switcher (`EmberThemeToggle`, iterates `availableVariants`) is already
   reachable: `SettingsView` → `PreferencesPanel` renders it under a "Theme Variant" fieldset,
   alongside the separate light/dark "Theme" control. Kept the existing "Theme Variant" label
   (a rename to "Theme" would collide with the light/dark control). The switcher is generic, so
   Phase 2 themes appear automatically once registered in `availableVariants`.
4. **`/slm` safety valve** — env override documented: an SLM/operator-console build can set
   `VITE_DEFAULT_THEME_VARIANT=default` to pin the current look even if it ever shares this build.

## Data flow

init script (pre-mount) reads `localStorage` → else env-default (`ember`) → sets
`data-theme-variant` → `useThemeVariant` on mount reconciles, `watch` persists user choice and
re-applies the attribute → `EmberThemeToggle` calls `setThemeVariant`.

## Migration / behavior

- Users with **no** saved choice now see Ember (intended new default).
- Users who explicitly chose "Default" have it in `localStorage` → unaffected.

## Error handling

`localStorage` unavailable → fall back to `ember`; unknown stored value → `ember`; invalid env
value → `ember`.

## Testing

Unit tests for `useThemeVariant`: empty store → `ember`; env override respected; stored choice
wins; unknown stored value → `ember`. Init-script no-flash behavior. Existing `EmberThemeToggle`
still switches and persists. `vue-tsc` clean.

## Out of scope (Phase 2 — separate spec)

Theme package format (folder/zip manifest + CSS + fonts/icons); `/slm` upload + install flow;
storage of installed themes; runtime dynamic-CSS delivery to the running frontend; validation and
sandboxing/sanitization of uploaded CSS (security-sensitive).
