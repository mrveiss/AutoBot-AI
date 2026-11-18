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

All base tokens are defined once, in `src/assets/css/design-tokens.css`; per-theme overrides live in `src/assets/css/themes/`. Precedence is written down in `src/assets/css/index.css`.

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

A **local override** is a component giving itself a value the design system owns. There are
five forms, each caught by exactly one check, so a sixth found later has an obvious home:

| Form | Owner check | Mode |
|---|---|---|
| hex in a `<style>` block | stylelint `color-no-hex` (`.stylelintrc.json` in each app and in `libs/autobot-ui`; `stylelint-tokens.yml`) | changed files, report-only |
| hex in `<script>` / a template attribute | `repo_tests/hardcoded_colour_ratchet_17560_test.py` (#17560) | whole tree, shrink-only |
| raw Tailwind palette class in a template (`bg-red-50`) | `repo_tests/raw_palette_class_ratchet_14580_test.py` (#14580) | whole tree, both apps, shrink-only |
| `!important` in a component `<style>` | the same file as hex-in-script, `TestTheImportantPopulationOnlyShrinks` (#17567) | whole tree, both apps, shrink-only |
| a token declared as a base value in two files, or a stylesheet nothing imports | `autobot-frontend/scripts/canonical/rules/ds_duplicate_base_declaration.mjs`, `ds_unloaded_stylesheet.mjs` (#14785, #17613) | whole tree, blocking |

A token redefined inside a component's `<style>` is not on this list on purpose: #17567 measured
it and found zero (the component-local custom properties are aliases assigned *from* tokens, the
pattern the system is for).

Each ratchet freezes the measured population in a baseline module and fails only on growth, with
a message that names the token to use. Baselines move one way: when a count falls, lower its
entry. The stylelint step is not yet whole-tree: that switch waits until the `<style>` hex
population reaches zero (#17567).

## Palette-step to token mapping for the SLM frontend (#17566)

`autobot-slm-frontend` styles itself from the Tailwind palette; the main frontend uses the `autobot-*` colour
utilities. Both apps declare the same `--color-autobot-*` names (`autobot-frontend/src/assets/tailwind.css`,
`autobot-slm-frontend/src/assets/styles/slm-scheme.css`; `ds_theme_contract.mjs` fails when they drift), so the
utility named below means the same thing in both and only the value differs per theme. Every utility in the
table exists in both files; none is invented. Token meanings: [REFINED_TOKEN_MAPPING.md](../design/REFINED_TOKEN_MAPPING.md).

**Measured** on `origin/main` @ `250ddc4554`, with the detector that enforces the ratchet
(`repo_tests/_raw_palette_detect.py`, `<style>` blocks excluded, opacity suffix `/NN` folded into its step):

```python
from pathlib import Path
from repo_tests._raw_palette_detect import scan_tree
c = scan_tree(Path("autobot-slm-frontend/src"))   # run with the python-suite venv's interpreter: python -I
sum(c.values())  # 5300 occurrences, 195 distinct classes, 103 of 113 .vue files, 105 family-step pairs
```

Control: `RAW_PALETTE_CLASS.search("bg-gray-800")` matches, and `raw_palette_class_ratchet_14580_test.py`
plants a class in a temporary SLM tree and sees it under the `slm:` key. The ratchet in
`_raw_palette_baseline.py` was measured when it landed (6214 occurrences); the sweep has drained it since, so
re-measure rather than reuse this figure. The figures are a snapshot at `250ddc4554`, not a contract; re-measure them with the same command.

How to read it: pick the row for the step, then the utility for the role (`bg`, `text`, `border`, `ring`, `divide`,
`placeholder`). An opacity suffix stays (`bg-red-500/10` becomes `bg-autobot-error/10`). The count is how often
each role occurs. Where the role cannot be read from the class, the row gives two answers: **informational**
(status, a notice) or **interactive** (a button, a link, a selected state); choose by what the element does.
Judgement calls, stated once:

- Neutrals follow the tonal ladder: 900/800 text is primary, 700/600 secondary, 500 muted, 400/300 tertiary.
  Backgrounds go 50 secondary, 100 tertiary, 200 hover, 300 active; 800 and up is `ink`. Borders go 100/200 subtle,
  300 default, 400 and up strong.
- Status hues fold onto the four semantic variants: `red` is error, `green` and `emerald` success, `amber`,
  `yellow` and `orange` warning, `blue` and `cyan` info. `orange` has no variant of its own; folding it into
  warning is a decision the sweep PR should confirm.
- Contrast is not verified by this table. A step 700/800 text becomes the one `text-autobot-<status>` colour, so each
  sweep batch carries the screenshot pair #17566 asks for.
- **no token yet** means no existing `--color-autobot-*` fits the role. It is a gap to decide, never a licence to keep the
  class; tokens are added deliberately in `slm-scheme.css` and `tailwind.css` together, or the use is redesigned.

| Palette step | Uses | Role (count) -> utility | No token yet because |
|---|---|---|---|
| `amber-50` | 3 | bg (3) -> `bg-autobot-warning-bg` |  |
| `amber-100` | 19 | bg (19) -> `bg-autobot-warning-bg` |  |
| `amber-200` | 6 | bg (4) -> `bg-autobot-warning-bg`; border (1) -> `border-autobot-warning-light`; text (1) -> `text-autobot-warning-light` |  |
| `amber-300` | 7 | text (4) -> `text-autobot-warning-light`; border (2) -> `border-autobot-warning-light`; bg (1) -> `bg-autobot-warning-light` |  |
| `amber-400` | 3 | text (3) -> `text-autobot-warning-light` |  |
| `amber-500` | 18 | bg (13) -> `bg-autobot-warning`; border (5) -> `border-autobot-warning` |  |
| `amber-600` | 21 | text (18) -> `text-autobot-warning`; bg (3) -> `bg-autobot-warning-hover` |  |
| `amber-700` | 20 | text (19) -> `text-autobot-warning`; bg (1) -> `bg-autobot-warning-hover` |  |
| `amber-800` | 6 | text (6) -> `text-autobot-warning` |  |
| `amber-900` | 1 | bg (1): **no token yet** | a dark status fill has no token (the -solid/-hover pair covers 500-700) |
| `blue-50` | 17 | bg (17) -> `bg-autobot-info-bg` |  |
| `blue-100` | 53 | bg (52) -> `bg-autobot-info-bg`; border (1) -> `border-autobot-info-light` |  |
| `blue-200` | 11 | border (7) -> `border-autobot-info-light`; bg (4) -> `bg-autobot-info-bg` |  |
| `blue-300` | 3 | border (2) -> `border-autobot-info-light`; text (1) -> `text-autobot-info-light` |  |
| `blue-400` | 5 | text (4) -> `text-autobot-info-light`; border (1) -> `border-autobot-info` informational / `border-autobot-primary` interactive |  |
| `blue-500` | 94 | ring (44) -> `ring-autobot-focus`; border (33) -> `border-autobot-info` informational / `border-autobot-primary` interactive; bg (11) -> `bg-autobot-info-solid` informational / `bg-autobot-primary` interactive; text (5) -> `text-autobot-info` informational / `text-autobot-text-link` interactive; border-l (1) -> `border-l-autobot-info` informational / `border-l-autobot-primary` interactive |  |
| `blue-600` | 84 | text (44) -> `text-autobot-info` informational / `text-autobot-text-link` interactive; bg (36) -> `bg-autobot-info-hover` informational / `bg-autobot-primary` interactive; border (4) -> `border-autobot-info` informational / `border-autobot-primary` interactive |  |
| `blue-700` | 62 | text (37) -> `text-autobot-info` informational / `text-autobot-text-link` interactive; bg (25) -> `bg-autobot-info-hover` informational / `bg-autobot-primary-hover` interactive |  |
| `blue-800` | 23 | text (23) -> `text-autobot-info` informational / `text-autobot-text-link` interactive |  |
| `blue-900` | 2 | text (1) -> `text-autobot-info` informational / `text-autobot-text-link` interactive; bg (1): **no token yet** | a dark status fill has no token (the -solid/-hover pair covers 500-700) |
| `cyan-50` | 1 | bg (1) -> `bg-autobot-info-bg` |  |
| `cyan-100` | 1 | bg (1) -> `bg-autobot-info-bg` |  |
| `cyan-300` | 1 | text (1) -> `text-autobot-info-light` |  |
| `cyan-400` | 4 | text (4) -> `text-autobot-info-light` |  |
| `cyan-500` | 4 | bg (3) -> `bg-autobot-info-solid`; border (1) -> `border-autobot-info` |  |
| `cyan-600` | 1 | text (1) -> `text-autobot-info` |  |
| `cyan-800` | 2 | text (2) -> `text-autobot-info` |  |
| `cyan-900` | 1 | text (1) -> `text-autobot-info` |  |
| `emerald-300` | 2 | text (2) -> `text-autobot-success-light` |  |
| `emerald-400` | 3 | text (2) -> `text-autobot-success-light`; bg (1) -> `bg-autobot-success-light` |  |
| `emerald-500` | 4 | bg (2) -> `bg-autobot-success`; border (2) -> `border-autobot-success` |  |
| `emerald-600` | 3 | bg (3) -> `bg-autobot-success-hover` |  |
| `emerald-700` | 1 | bg (1) -> `bg-autobot-success-hover` |  |
| `gray-50` | 239 | bg (235) -> `bg-autobot-bg-secondary`; border (4) -> `border-autobot-border-subtle` |  |
| `gray-100` | 275 | bg (197) -> `bg-autobot-bg-tertiary`; border (54) -> `border-autobot-border-subtle`; text (on dark fills) (12) -> `text-autobot-text-inverse`; divide (12) -> `divide-autobot-border-subtle` |  |
| `gray-200` | 444 | border (305) -> `border-autobot-border-subtle`; bg (92) -> `bg-autobot-bg-hover`; divide (42) -> `divide-autobot-border-subtle`; text (on dark fills) (5) -> `text-autobot-text-inverse` |  |
| `gray-300` | 377 | border (322) -> `border-autobot-border`; text (46) -> `text-autobot-text-tertiary`; bg (9) -> `bg-autobot-bg-active` |  |
| `gray-400` | 249 | text (208) -> `text-autobot-text-tertiary`; bg (41): **no token yet** | a solid mid-grey fill has no surface token (the bg-* tokens are page and panel surfaces) |
| `gray-500` | 877 | text (866) -> `text-autobot-text-muted`; bg (6): **no token yet**; border (4) -> `border-autobot-border-strong`; placeholder (1) -> `placeholder-autobot-text-tertiary` | a solid mid-grey fill has no surface token (the bg-* tokens are page and panel surfaces) |
| `gray-600` | 286 | text (264) -> `text-autobot-text-secondary`; border (14) -> `border-autobot-border-strong`; bg (8): **no token yet** | a solid mid-grey fill has no surface token (the bg-* tokens are page and panel surfaces) |
| `gray-700` | 462 | text (428) -> `text-autobot-text-secondary`; border (24) -> `border-autobot-border-strong`; bg (10): **no token yet** | a solid mid-grey fill has no surface token (the bg-* tokens are page and panel surfaces) |
| `gray-800` | 65 | text (40) -> `text-autobot-text-primary`; bg (22) -> `bg-autobot-ink`; border (3) -> `border-autobot-border-strong` |  |
| `gray-900` | 467 | text (437) -> `text-autobot-text-primary`; bg (30) -> `bg-autobot-ink` |  |
| `gray-950` | 1 | bg (1) -> `bg-autobot-ink` |  |
| `green-50` | 17 | bg (17) -> `bg-autobot-success-bg` |  |
| `green-100` | 62 | bg (62) -> `bg-autobot-success-bg` |  |
| `green-200` | 7 | bg (4) -> `bg-autobot-success-bg`; border (3) -> `border-autobot-success-light` |  |
| `green-300` | 10 | border (6) -> `border-autobot-success-light`; text (4) -> `text-autobot-success-light` |  |
| `green-400` | 4 | text (4) -> `text-autobot-success-light` |  |
| `green-500` | 60 | bg (55) -> `bg-autobot-success`; text (2) -> `text-autobot-success`; border (2) -> `border-autobot-success`; border-l (1) -> `border-l-autobot-success` |  |
| `green-600` | 83 | text (66) -> `text-autobot-success`; bg (17) -> `bg-autobot-success-hover` |  |
| `green-700` | 54 | text (47) -> `text-autobot-success`; bg (7) -> `bg-autobot-success-hover` |  |
| `green-800` | 26 | text (26) -> `text-autobot-success` |  |
| `green-900` | 1 | text (1) -> `text-autobot-success` |  |
| `indigo-50` | 4 | bg (4) -> `bg-autobot-primary-bg` |  |
| `indigo-100` | 4 | bg (4) -> `bg-autobot-primary-bg` |  |
| `indigo-200` | 2 | border (1) -> `border-autobot-primary-light`; bg (1) -> `bg-autobot-primary-light` |  |
| `indigo-300` | 1 | border (1) -> `border-autobot-primary-light` |  |
| `indigo-400` | 9 | ring (8) -> `ring-autobot-focus`; border (1) -> `border-autobot-primary` |  |
| `indigo-600` | 7 | bg (6) -> `bg-autobot-primary`; border (1) -> `border-autobot-primary` |  |
| `indigo-700` | 12 | text (8) -> `text-autobot-primary`; bg (4) -> `bg-autobot-primary-hover` |  |
| `orange-50` | 1 | bg (1) -> `bg-autobot-warning-bg` |  |
| `orange-100` | 15 | bg (15) -> `bg-autobot-warning-bg` |  |
| `orange-200` | 6 | border (4) -> `border-autobot-warning-light`; bg (2) -> `bg-autobot-warning-bg` |  |
| `orange-500` | 3 | bg (3) -> `bg-autobot-warning` |  |
| `orange-600` | 22 | text (17) -> `text-autobot-warning`; bg (5) -> `bg-autobot-warning-hover` |  |
| `orange-700` | 12 | text (8) -> `text-autobot-warning`; bg (4) -> `bg-autobot-warning-hover` |  |
| `orange-800` | 6 | text (6) -> `text-autobot-warning` |  |
| `pink-100` | 1 | bg (1): **no token yet** | categorical hue; chart-N tokens are data-series only, a decorative hue needs a decision |
| `pink-700` | 1 | text (1): **no token yet** | categorical hue; chart-N tokens are data-series only, a decorative hue needs a decision |
| `purple-50` | 3 | bg (3): **no token yet** | categorical hue; chart-N tokens are data-series only, a decorative hue needs a decision |
| `purple-100` | 11 | bg (11): **no token yet** | categorical hue; chart-N tokens are data-series only, a decorative hue needs a decision |
| `purple-200` | 5 | bg (3): **no token yet**; border (2): **no token yet** | categorical hue; chart-N tokens are data-series only, a decorative hue needs a decision |
| `purple-300` | 1 | text (1): **no token yet** | categorical hue; chart-N tokens are data-series only, a decorative hue needs a decision |
| `purple-400` | 2 | text (2): **no token yet** | categorical hue; chart-N tokens are data-series only, a decorative hue needs a decision |
| `purple-500` | 7 | bg (4): **no token yet**; border (1): **no token yet**; border-l (1): **no token yet**; text (1): **no token yet** | categorical hue; chart-N tokens are data-series only, a decorative hue needs a decision |
| `purple-600` | 12 | text (7): **no token yet**; bg (5): **no token yet** | categorical hue; chart-N tokens are data-series only, a decorative hue needs a decision |
| `purple-700` | 12 | text (8): **no token yet**; bg (4): **no token yet** | categorical hue; chart-N tokens are data-series only, a decorative hue needs a decision |
| `purple-800` | 4 | text (4): **no token yet** | categorical hue; chart-N tokens are data-series only, a decorative hue needs a decision |
| `purple-900` | 2 | text (1): **no token yet**; bg (1): **no token yet** | categorical hue; chart-N tokens are data-series only, a decorative hue needs a decision |
| `red-50` | 29 | bg (29) -> `bg-autobot-error-bg` |  |
| `red-100` | 69 | bg (69) -> `bg-autobot-error-bg` |  |
| `red-200` | 17 | bg (10) -> `bg-autobot-error-bg`; border (6) -> `border-autobot-error-light`; ring (1) -> `ring-autobot-error` |  |
| `red-300` | 14 | border (10) -> `border-autobot-error-light`; text (4) -> `text-autobot-error-light` |  |
| `red-400` | 5 | text (4) -> `text-autobot-error-light`; bg (1) -> `bg-autobot-error-light` |  |
| `red-500` | 65 | bg (48) -> `bg-autobot-error-solid`; text (12) -> `text-autobot-error`; border (5) -> `border-autobot-error` |  |
| `red-600` | 103 | text (85) -> `text-autobot-error`; bg (18) -> `bg-autobot-error-hover` |  |
| `red-700` | 83 | text (71) -> `text-autobot-error`; bg (12) -> `bg-autobot-error-hover` |  |
| `red-800` | 32 | text (31) -> `text-autobot-error`; bg (1): **no token yet** | a dark status fill has no token (the -solid/-hover pair covers 500-700) |
| `red-900` | 1 | bg (1): **no token yet** | a dark status fill has no token (the -solid/-hover pair covers 500-700) |
| `slate-400` | 1 | text (1) -> `text-autobot-text-tertiary` |  |
| `slate-900` | 2 | bg (2) -> `bg-autobot-ink` |  |
| `teal-100` | 1 | bg (1) -> `bg-autobot-primary-bg` |  |
| `teal-500` | 1 | bg (1) -> `bg-autobot-primary` |  |
| `teal-600` | 1 | bg (1) -> `bg-autobot-primary` |  |
| `teal-700` | 1 | text (1) -> `text-autobot-primary` |  |
| `yellow-50` | 7 | bg (7) -> `bg-autobot-warning-bg` |  |
| `yellow-100` | 38 | bg (38) -> `bg-autobot-warning-bg` |  |
| `yellow-200` | 5 | border (4) -> `border-autobot-warning-light`; bg (1) -> `bg-autobot-warning-bg` |  |
| `yellow-300` | 4 | border (3) -> `border-autobot-warning-light`; text (1) -> `text-autobot-warning-light` |  |
| `yellow-400` | 3 | text (2) -> `text-autobot-warning-light`; bg (1) -> `bg-autobot-warning-light` |  |
| `yellow-500` | 26 | bg (20) -> `bg-autobot-warning`; text (4) -> `text-autobot-warning`; border (2) -> `border-autobot-warning` |  |
| `yellow-600` | 32 | text (32) -> `text-autobot-warning` |  |
| `yellow-700` | 24 | text (24) -> `text-autobot-warning` |  |
| `yellow-800` | 19 | text (19) -> `text-autobot-warning` |  |

Totals: 105 rows; 14 rows have no token for any of their roles (every `pink` and `purple` step, plus the
dark status fills `amber-900` and `red-900`); 6 more have no token for one role (the solid mid-grey fills
`gray-400` to `gray-700`, and the dark fills of `blue-900` and `red-800`). Rebuild the table with the snippet above when the baseline moves.

## Canonical homes (#17571)

Which module owns each design-system concept is declared in code, not here:
`libs/autobot-ui/src/authority/designSystemAuthority.mjs` (`AUTHORITY`, `designSystemOwner()`).
It is the source of truth; where this document or any issue disagrees with it, the registry wins.
`designSystemOwner()` throws for a concept the registry does not list, but only when a caller
invokes it; no check calls it yet, and the canonical-check harness does not read `AUTHORITY`. An
entry that is not yet decided says so in a `note` with an issue link, and a deliberate exception
carries a stated `reason`.

The canonical-check harness (`node autobot-frontend/scripts/canonical_check.mjs --all`, also the
pre-commit hook and the weekly `canonical-audit.yml`, which fails on a `block`) runs two rules, each
derived from the kit's component listing rather than from the registry:

| Violation | Rule | Population frozen in |
|---|---|---|
| an app component file named like a kit component | `ds-second-kit-component` | `scripts/canonical/baselines/ds_second_kit_component.txt` |
| a kit-named component imported from a path other than `@autobot/ui` | `ds-noncanonical-primitive-import` | `scripts/canonical/baselines/ds_noncanonical_primitive_import.txt` |

Both baselines only shrink: delete a line in the PR that fixes it (the test fails if an entry no
longer matches). Their stated boundaries are in each baseline's header.

---

*Last updated: 2026-05-22 (Issue #7880)*
