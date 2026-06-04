# AutoBot CSS Theming Pattern Guide

**Issue:** #7453 — Tech-debt(frontend/css) — Canonical theming pattern audit

## Canonical Theming Pattern

The AutoBot frontend uses a **three-tier CSS architecture** for theming and styling:

### Tier 1: CSS Design Tokens (Source of Truth)
**File:** `src/assets/css/design-tokens.css`

All semantic design decisions are expressed as CSS custom properties (variables) at the `:root` scope. These are the single source of truth for:
- **Colors** (semantic: `--color-primary`, `--color-success`, `--color-error`, `--color-warning`, `--color-info`)
- **Spacing** (`--spacing-xs` through `--spacing-2xl`, micro units for dense UI)
- **Border-radius** (`--radius-sm` through `--radius-full`)
- **Typography** (font families, sizes, weights, line heights)
- **Shadows** (elevation system)
- **Transitions** (animation timings and easing)
- **Z-index** (semantic layering for modals, dropdowns, tooltips)
- **Component-specific tokens** (button heights, input styling, card styling)

**Preference Order:**
1. **Use CSS design tokens for all styling** — this is the canonical approach
2. **Never use hardcoded color values** (`#ffffff`, `rgb()`, etc.)
3. **Never use magic numbers** for spacing or sizing

### Tier 2: Tailwind CSS Utilities (Layout & Common Properties)
**File:** `src/assets/tailwind.css` + TailwindCSS runtime

Tailwind provides:
- **Layout classes** (`flex`, `grid`, `absolute`, `relative`, etc.)
- **Responsive breakpoints** (`md:`, `lg:`, etc.)
- **Common spacing** (`p-4`, `m-6`, `gap-3`, etc. — mapped to `--spacing-*` tokens)
- **Semantic utilities** (`.btn`, `.card`, `.input-field`, etc.)

**When to use Tailwind:**
- Grid/flex layouts
- Responsive sizing and margins
- Standard padding/borders (mapped to tokens)
- Alignment and positioning

**When NOT to use Tailwind:**
- ❌ Hardcoded colors or hex values
- ❌ Component-specific theming
- ❌ Dark-mode variants that need token integration
- ❌ Custom shadows, gradients, or complex styling

### Tier 3: Scoped Styles (Component-Local Behavior)
**Pattern:** `<style scoped>` blocks in Vue components

Use scoped styles **only** for:
- Component-specific layouts that Tailwind can't express cleanly
- Complex selectors (pseudo-elements, pseudo-classes beyond hover)
- Media queries for component-specific responsiveness
- Animations and transitions

**Required:** All values in scoped styles MUST reference design tokens:

```vue
<!-- ✅ CORRECT -->
<style scoped>
.my-component {
  padding: var(--spacing-md);
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  color: var(--text-primary);
  transition: all var(--duration-150) var(--ease-in-out);
}

.my-component:hover {
  background: var(--bg-hover);
}
</style>

<!-- ❌ WRONG -->
<style scoped>
.my-component {
  padding: 1rem;           /* Use var(--spacing-md) */
  background: #1e293b;     /* Use var(--bg-card) */
  border-radius: 8px;      /* Use var(--radius-lg) */
  color: #e2e8f0;          /* Use var(--text-primary) */
  transition: all 150ms;   /* Use var(--duration-150) var(--ease-in-out) */
}
</style>
```

## Design Token Categories

### Color Tokens

**Semantic Colors (Brand & Status):**
- `--color-primary` (Electric Blue #3b82f6) — primary actions, links
- `--color-secondary` (Slate #64748b) — secondary actions
- `--color-success` (Emerald #10b981) — positive feedback, success states
- `--color-warning` (Amber #f59e0b) — alerts, caution, warnings
- `--color-error` (Red #ef4444) — errors, destructive actions
- `--color-info` (Blue #3b82f6) — information, neutral feedback
- `--color-danger` (Red #dc2626) — critical, dangerous actions
- `--color-purple` (Violet #9333ea) — special UI elements

**Variants:** Each semantic color includes:
- Base: `--color-error`
- Hover: `--color-error-hover`
- Light: `--color-error-light`
- Dark: `--color-error-dark`
- Background: `--color-error-bg`, `--color-error-bg-hover`
- Border: `--color-error-border`
- Alpha: `--color-error-alpha-10`

**Background Colors (Theme-Aware):**
- `--bg-primary` — main page background (dark mode: #0f172a)
- `--bg-secondary` — secondary surfaces (dark mode: #1e293b)
- `--bg-tertiary` — tertiary surfaces (dark mode: #334155)
- `--bg-elevated` — lifted surfaces (dark mode: #1e293b)
- `--bg-card` — card backgrounds (dark mode: #1e293b)
- `--bg-surface` — surface backgrounds (dark mode: #1a1a2e)
- `--bg-input` — input field backgrounds (dark mode: #1e293b)
- `--bg-hover` — hover state backgrounds (dark mode: rgba(255, 255, 255, 0.05))
- `--bg-active` — active state backgrounds (dark mode: rgba(255, 255, 255, 0.1))
- `--bg-overlay` — overlay/modal backgrounds (dark mode: rgba(0, 0, 0, 0.5))

**Text Colors (Theme-Aware):**
- `--text-primary` — main text (dark mode: #e2e8f0)
- `--text-secondary` — secondary text (dark mode: #94a3b8)
- `--text-tertiary` — tertiary text (dark mode: #64748b)
- `--text-muted` — muted/disabled text (dark mode: #475569)
- `--text-inverse` — text on dark backgrounds (dark mode: #0f172a)
- `--text-link` — link color (dark mode: #3b82f6)

**Border Colors:**
- `--border-default` — standard borders
- `--border-subtle` — subtle/secondary borders
- `--border-strong` — emphasized borders
- `--border-focus` — focus ring borders (linked to primary color)

### Spacing Tokens

**Semantic Scale:**
```
--spacing-xs   = 0.25rem (4px)
--spacing-sm   = 0.5rem  (8px)
--spacing-md   = 1rem    (16px)
--spacing-lg   = 1.5rem  (24px)
--spacing-xl   = 2rem    (32px)
--spacing-2xl  = 3rem    (48px)
```

**Numeric Scale:**
```
--spacing-1 to --spacing-32 (by half-rems, 0.25rem increments)
--spacing-micro-3 to --spacing-micro-5 (for dense UI: badges, chips)
```

**Use:** Padding, margins, gaps in flexbox/grid
- ✅ `padding: var(--spacing-md);`
- ✅ `gap: var(--spacing-lg);`
- ❌ `padding: 1rem;`
- ❌ `margin: 20px;`

### Border Radius Tokens

```
--radius-none   = 0
--radius-xs    = 2px
--radius-sm    = 0.125rem
--radius-md    = 0.375rem
--radius-lg    = 0.5rem
--radius-xl    = 0.75rem
--radius-2xl   = 1rem
--radius-3xl   = 1.5rem
--radius-full  = 9999px (for circles, pills)
```

**Use:**
- `border-radius: var(--radius-md);` for buttons, inputs
- `border-radius: var(--radius-lg);` for cards
- `border-radius: var(--radius-full);` for badges, avatars

### Typography Tokens

**Font Families:**
- `--font-sans` — IBM Plex Sans (body text, UI)
- `--font-mono` — JetBrains Mono (code blocks, data display)
- `--font-numeric` — IBM Plex Mono (numbers, tabular data)

**Font Sizes:**
```
--text-xs   = 0.75rem   (12px)
--text-sm   = 0.875rem  (14px)
--text-base = 1rem      (16px)
--text-lg   = 1.125rem  (18px)
--text-xl   = 1.25rem   (20px)
--text-2xl  = 1.5rem    (24px)
--text-3xl  = 1.875rem  (30px)
```

**Font Weights:**
```
--font-normal   = 400
--font-medium   = 500
--font-semibold = 600
--font-bold     = 700
```

**Line Heights:**
```
--leading-tight   = 1.25
--leading-normal  = 1.5
--leading-relaxed = 1.625
--leading-loose   = 2
```

## Theming Architecture

### Single Source of Truth
All color decisions flow through `design-tokens.css`. Theme files (`light.css`, `dark.css`) override the `:root` values.

**Structure:**
```
design-tokens.css      (canonical values, default dark theme)
├── light.css          (light theme overrides)
└── dark.css           (dark theme overrides)
```

**Theme Switching:**
```html
<!-- Light theme: data-theme="light" on root element -->
<html data-theme="light">

<!-- Dark theme: data-theme="dark" -->
<html data-theme="dark">
```

### Token Inheritance Flow
1. **Design tokens** define all color/spacing/typography values
2. **Tailwind config** maps tokens to utility classes
3. **Scoped styles** reference tokens directly
4. **Theme files** override `:root` values for light/dark modes

## Implementation Checklist

When creating new components:

- [ ] Use Tailwind utilities for layout (`flex`, `grid`, `p-4`, etc.)
- [ ] Use CSS design tokens for all colors, spacing, typography
- [ ] If using `<style scoped>`, reference tokens with `var(--token-name)`
- [ ] Never hardcode color values or pixel measurements
- [ ] Test in both light and dark themes
- [ ] Verify responsive behavior with Tailwind breakpoints
- [ ] Use semantic token names, not raw values

## Examples

### Button Component
```vue
<template>
  <button class="btn">
    Action
  </button>
</template>

<style scoped>
.btn {
  /* Layout from Tailwind or Flex */
  display: inline-flex;
  align-items: center;
  justify-content: center;
  
  /* Sizing from tokens */
  height: var(--btn-height-md);
  padding: 0 var(--btn-padding-x-md);
  
  /* Colors from tokens */
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: 1px solid var(--color-primary);
  border-radius: var(--btn-radius);
  
  /* Typography from tokens */
  font-size: var(--btn-font-size-md);
  font-weight: var(--font-medium);
  
  /* Transitions from tokens */
  transition: var(--transition-colors);
  cursor: pointer;
}

.btn:hover {
  background: var(--color-primary-hover);
  border-color: var(--color-primary-hover);
}

.btn:active {
  background: var(--color-primary-active);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
```

### Card Component
```vue
<template>
  <div class="card">
    <header class="card-header">Title</header>
    <div class="card-body">Content</div>
  </div>
</template>

<style scoped>
.card {
  /* Spacing from tokens */
  padding: var(--card-padding);
  
  /* Colors from tokens */
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: var(--card-radius);
  
  /* Elevation from tokens */
  box-shadow: var(--card-shadow);
}

.card-header {
  /* Tailwind layout + token styling */
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--border-subtle);
  margin-bottom: var(--spacing-md);
}

.card-body {
  padding: var(--spacing-md);
  color: var(--text-primary);
}
</style>
```

## Theme Switching (Dark Mode)

Components automatically support theme switching via CSS custom properties. No JavaScript required:

```vue
<!-- Theme context automatically applies data-theme attribute -->
<template>
  <div class="themed-component">Dark mode friendly!</div>
</template>

<style scoped>
.themed-component {
  /* Automatically adapts to light/dark theme */
  background: var(--bg-primary);
  color: var(--text-primary);
}
</style>
```

All token values are overridden by theme files when `data-theme` changes on the root element.

## Backward Compatibility

Legacy component variable names are aliased to modern tokens:

```css
/* Old name → Modern token */
--primary-color → --color-primary
--secondary-color → --color-secondary
--success-color → --color-success
--danger-color → --color-error (or --color-danger)
```

These aliases exist in `design-tokens.css` for gradual migration of older components.

## Migration Guide

### From Hardcoded Values
**Before:**
```vue
<style scoped>
.component { color: #e2e8f0; }
</style>
```

**After:**
```vue
<style scoped>
.component { color: var(--text-primary); }
</style>
```

### From Inline Styles
**Before:**
```vue
<div style="background: #1e293b; padding: 1rem">Content</div>
```

**After:**
```vue
<div style="background: var(--bg-card); padding: var(--spacing-md)">Content</div>
<!-- Or better: use class-based styling -->
<div class="card"><div class="p-4">Content</div></div>
```

### From Magic Numbers
**Before:**
```vue
<style scoped>
.container { max-width: 1280px; }
.sidebar { width: 240px; }
.gap { gap: 16px; }
</style>
```

**After:**
```vue
<style scoped>
.container { max-width: var(--content-max-width); }
.sidebar { width: var(--sidebar-width); }
.gap { gap: var(--spacing-lg); }
</style>
```

## Maintenance

**Adding New Tokens:**
1. Define in `design-tokens.css` at `:root`
2. Document in this file under the appropriate category
3. Override in `light.css` and `dark.css` if theme-aware
4. Reference in components via `var(--token-name)`

**Removing Tokens:**
1. Search codebase for all usages: `grep -r "var(--token-name)"`
2. Replace with appropriate alternative token
3. Remove from `design-tokens.css` and theme files
4. File discovery issue if token is referenced but no longer defined

**Token Naming Convention:**
- **Semantic:** `--color-primary`, `--color-success` (what it's for)
- **Component:** `--btn-height-md`, `--card-padding` (component + property)
- **System:** `--spacing-md`, `--radius-lg` (category + scale)
- **Theme-aware:** override in light/dark theme files
- **Variant:** `-hover`, `-active`, `-light`, `-dark`, `-bg`, `-border`

## Related Issues & References

- Issue #704 — CSS Design System (established design tokens)
- Issue #901 — Technical Precision Theme (dark mode refinement)
- Issue #548 — Unified design system with CSS variables
- Issue #7453 — Tech-debt(frontend/css) — Canonical theming pattern audit

## Testing Checklist

When implementing or migrating components:

- [ ] Light theme: inspect element, verify token values resolve
- [ ] Dark theme: inspect element, verify dark overrides apply
- [ ] No hardcoded colors in component styles
- [ ] No magic numbers for spacing or sizing
- [ ] Responsive breakpoints work without `!important` overrides
- [ ] Hover/focus/active states use token variants
- [ ] No inline styles with hardcoded values
- [ ] Accessibility: color contrast meets WCAG AA (4.5:1 for text)

---

**Last Updated:** 2026-05-16  
**Maintainer:** AutoBot Frontend Team  
**Status:** Active — canonical theming pattern enforced
