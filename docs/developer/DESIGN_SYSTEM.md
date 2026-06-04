# AutoBot Frontend Design System

> **Canonical token reference** for all frontend styling decisions.
> Issue #7453 (audit) → Issue #7880 (migration)

---

## Priority Order

Use this order when choosing how to style a component:

1. **Tailwind utility classes** — for layout, spacing, flex, grid, sizing
2. **CSS custom properties** (`var(--)`) — for semantic color, shadow, typography
3. **Component-local values** — only when truly component-specific (e.g. SVG geometry)

Never hard-code hex color values or numeric pixels for spacing in scoped styles.

---

## CSS Token Vocabulary

All tokens are defined in `src/assets/styles/theme.css` and `src/assets/tokens.css`.

### Color — Status / Semantic

| Token | Value | Use for |
|---|---|---|
| `var(--color-primary)` | `#0d9488` | Primary brand actions, active states |
| `var(--color-primary-hover)` | `#0f766e` | Hover on primary elements |
| `var(--color-primary-light)` | `#5eead4` | Subtle primary tint |
| `var(--color-primary-dark)` | `#115e59` | Active/pressed primary |
| `var(--color-secondary)` | `#64748b` | Secondary buttons, muted text |
| `var(--color-secondary-hover)` | `#475569` | Hover on secondary |
| `var(--color-secondary-light)` | `#94a3b8` | Subtle secondary |
| `var(--color-success)` | `#10b981` | Success states, positive indicators |
| `var(--color-success-light)` | `#34d399` | Success tint |
| `var(--color-success-dark)` | `#059669` | Success pressed |
| `var(--color-warning)` | `#f59e0b` | Warning states, caution indicators |
| `var(--color-warning-light)` | `#fbbf24` | Warning tint |
| `var(--color-warning-dark)` | `#d97706` | Warning pressed |
| `var(--color-error)` | `#ef4444` | Error states, destructive actions |
| `var(--color-error-light)` | `#f87171` | Error tint |
| `var(--color-error-dark)` | `#dc2626` | Error pressed |
| `var(--color-info)` | `#3b82f6` | Informational states, neutral indicators |
| `var(--color-info-light)` | `#60a5fa` | Info tint |
| `var(--color-info-dark)` | `#2563eb` | Info pressed |

### Color — Background

| Token | Use for |
|---|---|
| `var(--bg-primary)` | Main page background |
| `var(--bg-secondary)` | Secondary panels, sidebars |
| `var(--bg-tertiary)` | Nested surfaces, hover states |
| `var(--bg-elevated)` | Modals, dropdowns, elevated cards |
| `var(--bg-card)` | Card / panel backgrounds |
| `var(--bg-input)` | Input field backgrounds |

### Color — Text

| Token | Use for |
|---|---|
| `var(--text-primary)` | Main readable text |
| `var(--text-secondary)` | Subdued / supporting text |
| `var(--text-tertiary)` | Placeholder, disabled |
| `var(--text-muted)` | Very subdued labels |
| `var(--text-inverse)` | Text on dark / colored backgrounds |

### Color — Border

| Token | Use for |
|---|---|
| `var(--border-default)` | Standard borders |
| `var(--border-muted)` | Subtle dividers |
| `var(--border-focus)` | Focus rings |

### Border Radius

| Token | Tailwind equivalent |
|---|---|
| `var(--radius-sm)` | `rounded` |
| `var(--radius-md)` | `rounded-md` |
| `var(--radius-lg)` | `rounded-lg` |
| `var(--radius-xl)` | `rounded-xl` |
| `var(--radius-full)` | `rounded-full` |

### Shadow

| Token | Use for |
|---|---|
| `var(--shadow-sm)` | Subtle lift |
| `var(--shadow-md)` | Cards |
| `var(--shadow-lg)` | Modals, dropdowns |
| `var(--shadow-xl)` | Full-screen overlays |

### Spacing

Prefer Tailwind spacing (`p-4`, `gap-2`, `mt-3`) over CSS variables. Use CSS spacing tokens only inside scoped styles where Tailwind doesn't apply:

| Token | Value |
|---|---|
| `var(--spacing-1)` | `0.25rem` |
| `var(--spacing-2)` | `0.5rem` |
| `var(--spacing-4)` | `1rem` |
| `var(--spacing-6)` | `1.5rem` |
| `var(--spacing-8)` | `2rem` |

---

## Migration Rules

### When to Replace Hardcoded Values

Replace a hardcoded hex value with a token when the value is a **semantic color** with a clear mapping:

```css
/* Before */
color: #ef4444;
background-color: #10b981;
border-color: #3b82f6;

/* After */
color: var(--color-error);
background-color: var(--color-success);
border-color: var(--color-info);
```

### When NOT to Replace

- **RGBA variants** (`rgba(239, 68, 68, 0.1)`) — keep as-is unless the token set includes the specific alpha variant.
- **Canvas / chart colors** — D3, Chart.js, and SVG paths use direct hex for rendering; do not tokenize.
- **Third-party library overrides** — colors in `.vendor-class {}` blocks may be intentional overrides.
- **`#fff` / `#ffffff`** — depends on context; use `var(--bg-elevated)` for backgrounds, `var(--text-inverse)` for text on dark surfaces.

---

## Scoped Style Audit Summary

As of the audit run on 2026-05-22:

- **307** `<style scoped>` blocks across `src/`
- **288** already use `var(--…)` CSS variables
- **37** use Tailwind `@apply` inside scoped styles
- **228** contain at least one hardcoded color value (many overlap with var users)
- **21** contain clear-cut semantic color substitutions (`#ef4444`, `#10b981`, `#f59e0b`, `#0d9488`)

### Remaining Gaps

The following patterns need tokens or a documented decision:
- `rgba(239, 68, 68, N)` — error with alpha (no token yet; could add `--color-error-rgb`)
- `rgba(59, 130, 246, N)` — info with alpha
- `rgba(34, 197, 94, N)` — success with alpha
- `rgba(30, 41, 59, 0.5)` — slate-900 overlay (backdrop)
- `rgba(0, 0, 0, 0.5)` — generic black overlay

---

## Enforcement

1. **Code review**: flag any new `#hex` value in a `<style scoped>` block
2. **Lint rule**: (future) add `stylelint-no-unsupported-browser-features` + custom rule for hardcoded colors
3. **CI gate**: (future) add a grep-based CI step that fails if new scoped styles introduce un-mapped hex values

---

*Last updated: 2026-05-22 (Issue #7880)*
