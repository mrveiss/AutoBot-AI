---
tags: [type/reference, status/current, component/frontend]
date: 2026-06-04
issue: 7453
---

# CSS Theming Pattern

The AutoBot frontend uses a three-tier CSS architecture for all theming and styling.

---

## Three-Tier Architecture

### Tier 1 — Design Tokens (Source of Truth)
**File:** `src/assets/css/design-tokens.css`

All semantic design decisions live as CSS custom properties at `:root`. Tokens are the single source of truth for colors, spacing, typography, shadows, z-index, and component-specific values.

Rules:
1. Use CSS design tokens for all styling
2. Never use hardcoded color values (`#ffffff`, `rgb()`, etc.)
3. Never use magic numbers for spacing or sizing

### Tier 2 — Tailwind CSS (Layout & Common Properties)
**File:** `src/assets/tailwind.css` + TailwindCSS runtime

Use Tailwind for: grid/flex layouts, responsive breakpoints, standard padding/borders, alignment.

Do **not** use Tailwind for: hardcoded colors, component-specific theming, dark-mode variants needing token integration.

### Tier 3 — Scoped Styles (Component-Local)

Use `<style scoped>` only for:
- Complex selectors (pseudo-elements, pseudo-classes)
- Animations and transitions
- Component-specific layouts Tailwind can't express cleanly

All values in scoped styles must reference design tokens:

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
</style>

<!-- ❌ WRONG -->
<style scoped>
.my-component {
  padding: 1rem;        /* use var(--spacing-md) */
  background: #1e293b;  /* use var(--bg-card) */
  border-radius: 8px;   /* use var(--radius-lg) */
}
</style>
```

---

## Design Token Reference

### Colors

**Semantic (brand & status):**
- `--color-primary` — Electric Blue #3b82f6 — primary actions, links
- `--color-secondary` — Slate #64748b — secondary actions
- `--color-success` — Emerald #10b981
- `--color-warning` — Amber #f59e0b
- `--color-error` — Red #ef4444
- `--color-info` — Blue #3b82f6
- `--color-danger` — Red #dc2626 — critical/destructive actions

Each semantic color has variants: `-hover`, `-light`, `-dark`, `-bg`, `-bg-hover`, `-border`, `-alpha-10`.

**Background (theme-aware):**
- `--bg-primary` — main page background
- `--bg-secondary`, `--bg-tertiary`, `--bg-elevated`, `--bg-card`
- `--bg-input` — input fields
- `--bg-hover`, `--bg-active` — interaction states
- `--bg-overlay` — modal/drawer backdrops

**Text (theme-aware):**
- `--text-primary`, `--text-secondary`, `--text-tertiary`, `--text-muted`
- `--text-inverse` — text on dark backgrounds
- `--text-link`

**Borders:**
- `--border-default`, `--border-subtle`, `--border-strong`, `--border-focus`

### Spacing

```
--spacing-xs   = 0.25rem (4px)
--spacing-sm   = 0.5rem  (8px)
--spacing-md   = 1rem    (16px)
--spacing-lg   = 1.5rem  (24px)
--spacing-xl   = 2rem    (32px)
--spacing-2xl  = 3rem    (48px)
```

Numeric scale `--spacing-1` through `--spacing-32` (0.25 rem increments). Micro scale `--spacing-micro-3` through `--spacing-micro-5` for dense UI (badges, chips).

### Border Radius

```
--radius-xs through --radius-3xl
--radius-full = 9999px  (circles, pills)
```

### Typography

**Families:**
- `--font-sans` — IBM Plex Sans (body, UI)
- `--font-mono` — JetBrains Mono (code blocks)
- `--font-numeric` — IBM Plex Mono (tabular data)

**Sizes:** `--text-xs` (12px) through `--text-3xl` (30px)

**Weights:** `--font-normal` (400), `--font-medium` (500), `--font-semibold` (600), `--font-bold` (700)

---

## Theme Structure

```
design-tokens.css      ← canonical values, default dark theme
├── light.css          ← light theme overrides
└── dark.css           ← dark theme overrides
```

Theme switching is CSS-only — set `data-theme="light"` or `data-theme="dark"` on the root element.

---

## Component Examples

### Button

```vue
<style scoped>
.btn {
  display: inline-flex;
  align-items: center;
  height: var(--btn-height-md);
  padding: 0 var(--btn-padding-x-md);
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: 1px solid var(--color-primary);
  border-radius: var(--btn-radius);
  font-size: var(--btn-font-size-md);
  font-weight: var(--font-medium);
  transition: var(--transition-colors);
  cursor: pointer;
}
.btn:hover { background: var(--color-primary-hover); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
```

### Card

```vue
<style scoped>
.card {
  padding: var(--card-padding);
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: var(--card-radius);
  box-shadow: var(--card-shadow);
}
</style>
```

---

## Adding New Tokens

1. Define in `design-tokens.css` at `:root`
2. Override in `light.css` / `dark.css` if theme-aware
3. Reference in components via `var(--token-name)`

Naming convention: `--{category}-{property}[-{variant}]`
- Semantic: `--color-primary`, `--color-success`
- Component: `--btn-height-md`, `--card-padding`
- System: `--spacing-md`, `--radius-lg`

---

## Legacy Aliases

Old variable names are aliased in `design-tokens.css` for gradual migration:

```css
--primary-color   → --color-primary
--secondary-color → --color-secondary
--danger-color    → --color-error
```

---

## Checklist for New Components

- [ ] Tailwind for layout (`flex`, `grid`, responsive breakpoints)
- [ ] CSS tokens for all colors, spacing, typography
- [ ] No hardcoded hex values or magic numbers
- [ ] Light and dark theme both tested
- [ ] Color contrast ≥ 4.5:1 (WCAG AA)
- [ ] Hover/focus/active states use token variants
