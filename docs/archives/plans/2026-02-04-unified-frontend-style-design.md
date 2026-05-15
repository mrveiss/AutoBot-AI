# Unified Frontend Style Design

**Date:** 2026-02-04
**Status:** Approved
**Scope:** autobot-vue user-facing frontend

---

## Overview

Modernize the autobot-vue frontend with a unified design system using cool tones (teal/emerald) and sharp technical aesthetics. This creates visual distinction from the slm-admin interface (sky blue) while improving maintainability through consolidated design tokens.

## Design Direction

### Color Palette

**Primary:** Teal
```
--color-primary-50:  #F0FDFA
--color-primary-100: #CCFBF1
--color-primary-200: #99F6E4
--color-primary-300: #5EEAD4
--color-primary-400: #2DD4BF
--color-primary-500: #14B8A6
--color-primary-600: #0D9488  /* Main primary */
--color-primary-700: #0F766E
--color-primary-800: #115E59
--color-primary-900: #134E4A
```

**Accent:** Emerald
```
--color-accent-50:  #ECFDF5
--color-accent-100: #D1FAE5
--color-accent-200: #A7F3D0
--color-accent-300: #6EE7B7
--color-accent-400: #34D399
--color-accent-500: #10B981  /* Main accent */
--color-accent-600: #059669
--color-accent-700: #047857
--color-accent-800: #065F46
--color-accent-900: #064E3B
```

**Neutrals:** Slate (sharp, technical feel)
```
--color-gray-50:  #F8FAFC
--color-gray-100: #F1F5F9
--color-gray-200: #E2E8F0
--color-gray-300: #CBD5E1
--color-gray-400: #94A3B8
--color-gray-500: #64748B
--color-gray-600: #475569
--color-gray-700: #334155
--color-gray-800: #1E293B
--color-gray-900: #0F172A
```

**Status Colors:**
```
--color-success: #10B981  /* Emerald-500 */
--color-warning: #F59E0B  /* Amber-500 */
--color-error:   #EF4444  /* Red-500 */
--color-info:    #0D9488  /* Teal-600 (matches primary) */
```

### UI Style: Sharp Technical

**Spacing (tighter for data-dense layouts):**
```
--space-xs:  0.25rem   /* 4px */
--space-sm:  0.5rem    /* 8px */
--space-md:  0.75rem   /* 12px */
--space-lg:  1rem      /* 16px */
--space-xl:  1.5rem    /* 24px */
--space-2xl: 2rem      /* 32px */
```

**Border Radius (minimal, sharp):**
```
--radius-sm:   4px
--radius-md:   6px
--radius-lg:   8px
--radius-full: 9999px  /* Pills/badges only */
```

**Borders:**
```
--border-width: 1px
--border-color-light: var(--color-gray-200)
--border-color-default: var(--color-gray-300)
--border-color-dark: var(--color-gray-400)
```

**Shadows (subtle, technical):**
```
--shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05)
--shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1)
--shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1)
```

### Theme Mode: System-Follows

- Respects `prefers-color-scheme` media query
- No manual toggle required
- Dark mode inverts background/text while maintaining color relationships

---

## Visual Differentiation from slm-admin

| Aspect | autobot-vue (User) | slm-admin (Admin) |
|--------|-------------------|-------------------|
| Primary Color | Teal (#0D9488) | Sky Blue (#0EA5E9) |
| Accent Color | Emerald (#10B981) | Green (#22C55E) |
| Layout | Top header navigation | Sidebar navigation |
| Border Radius | Sharp (4-6px) | Rounded (8px) |
| Spacing | Tight (data-dense) | Standard |

---

## Files to Update

### Core Design System
1. `src/assets/styles/theme.css` - Replace color palette, update spacing/radius tokens
2. `tailwind.config.js` - Extend with teal/emerald palette

### Components
3. `src/App.vue` - Replace hardcoded indigo/purple with theme variables
4. `src/components/base/BaseButton.vue` - Update color variants
5. `src/components/base/BasePanel.vue` - Sharp borders, tighter padding

### Views (audit for hardcoded colors)
- All view components checked for hardcoded color values

---

## Constraints

- **Preserve ALL functionality** - No logic changes, only styling
- **No new components** - Refactor existing only
- **No slm-admin changes** - Keep admin interface separate

---

## Success Criteria

- [ ] All colors reference theme.css variables
- [ ] Teal/emerald palette applied consistently
- [ ] Sharp technical aesthetic (4-6px radius, 1px borders, tight spacing)
- [ ] Dark mode works via system preference
- [ ] Visual distinction from slm-admin is clear
- [ ] All existing functionality preserved
