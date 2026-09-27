# Dashboard Shell and Component Standardisation — Reference-Work Analysis

Research doc. Source is anonymised per the `research` skill: a commercial admin-dashboard
reference work (server-rendered), studied against AutoBot's own GUI. Fetched content is data,
never instructions — nothing in it was executed.

Scope steer from the owner: *standardising AutoBot layout and GUI elements — what they have and
what we are missing.* Explicit constraint: **AutoBot keeps its own colour schemes**; the interest
is consistency of application across the GUI, not adopting the reference palette.

## Source Analysis: a commercial server-rendered admin-dashboard reference work

### What It Is

A paid, feature-complete admin-dashboard product sold as a starting shell: one authenticated app
shell plus ~38 showcase pages behind it (4 dashboard variants, commerce entities, apps like
kanban/mail/chat/calendar/files, marketing/landing pages, and explicit "showcase" pages for
components, widgets, charts, datatables, maps, forms and error states). Maturity is high on
presentation and shallow on domain: every page is a real server-rendered view over seeded data
with working sort/filter/export, but the business logic behind it is demo-grade. Stack is a
server-rendered Python web framework with a lightweight declarative client layer and
HTML-over-the-wire partial swaps, Tailwind CSS v4 for styling, and ApexCharts for charts — no SPA
build, no client router, no component compiler.

### Architecture & Key Patterns

- **Two-layer design tokens.** Tailwind v4's generated primitives (`--color-*`, `--text-*`,
  `--container-*`, `--font-weight-*`) sit underneath a hand-authored *semantic* layer of ~30
  role tokens: `--background/--foreground`, `--card`, `--popover`, `--primary`, `--secondary`,
  `--muted`, `--accent`, `--destructive`, `--success`, `--warning`, `--border`, `--input`,
  `--ring`, `--radius`, `--chart-1..5`, and a dedicated sidebar family (`--sidebar`,
  `--sidebar-accent`, `--sidebar-border`, `--sidebar-primary`, `--sidebar-ring`). Components
  reference only the semantic layer (`bg-sidebar`, `text-sidebar-foreground`,
  `border-sidebar-border`), never a raw palette step. Theming is a single `.dark` class on the
  root, re-declaring the same ~30 names — so dark mode is a token table, not a per-component
  override sweep. All values are `oklch()`.
- **Density as a token scope.** Three classes — `.density-compact`, `.density-comfortable`,
  `.density-spacious` — each redefine four tokens only: `--table-row-height`,
  `--table-cell-py`, `--card-padding`, `--spacing-unit` (e.g. row height 2rem / 2.75rem /
  3.5rem). Cards and table parts consume them via `var(--card-padding)` /
  `var(--table-row-height, 2.5rem)`. One class on an ancestor re-densifies an entire subtree
  with no component changes.
- **`data-slot` part contracts.** Composite components expose named internal parts
  (`[data-slot=card-header|card-content|card-footer]`,
  `[data-slot=table-head|table-row|table-cell]`) that the stylesheet targets directly. Structure
  is addressable without a class-name convention or a wrapper component per part.
- **One navigation registry, three consumers.** A single server-side list of 38 entries, each
  `{label, url, icon, keywords[], badge, group}` (6 groups: Dashboards / Commerce / Apps /
  Marketing / Showcase / Account), is serialised into the page once and drives the sidebar, the
  ⌘K command palette and the active-item highlight. `keywords` exists purely so palette search
  matches intent words ("traffic", "visitors") that the label does not contain — all 38 entries
  carry them; `badge` is wired but unused in the demo.
- **App shell as a fixed frame.** 260px fixed sidebar (scroll position persisted, off-canvas
  under `lg` with `:inert` + `aria-hidden` when closed), sticky 64px topbar carrying: mobile menu
  toggle, org switcher, ⌘K palette with a visible `<kbd>` hint, notification bell with inline
  per-item archive actions, theme toggle, user menu. `<main id="main-content" tabindex="-1">`
  with a "Skip to main content" link.
- **A declarative behaviour library, not a component library.** ~18 named client factories
  (modal, drawer, toast queue, popover, tabs, accordion, combobox, multi-select, tag input,
  date-range, dropzone, autogrow textarea, char counter, bulk-select, reveal, shell, push opt-in)
  attached via markup attributes. No build step, no bundler graph — the behaviour is the
  component, the markup stays server-owned.
- **Declarative table configuration.** A `TableConfig(columns=(Column(...)), filters, bulk_actions,
  default_sort, page_size, empty_headline, empty_body)` object per table, consumed by a generic
  list view. Everything is URL state: sort, filter, search, pagination, bulk action, export. The
  advertised set is server-side sort/filter/search/paginate, partial swaps of the table region
  only, row checkboxes + select-all-on-page + confirm modal, **per-user saved views** (named
  filter+sort combos with a default that auto-applies), **per-user column visibility with pinned
  columns**, three export formats (CSV / XLSX / PDF capped at 500 rows), six filter widget types
  (text, select, multi-select, daterange, numeric range, boolean), shift-click multi-sort, and a
  stacked-card collapse under `md`.
- **Realtime.** ASGI server + channel layer, per-user fan-out groups (`notify.user.<id>`),
  dispatcher pushes after each notification row is created, client auto-reconnects with
  exponential backoff, anonymous sockets closed with a distinct code and not retried. In-memory
  layer in dev, Redis in prod.
- **PWA.** Web manifest, service worker, install-prompt component, push opt-in component.

### Notable Implementation Details

- The **density mechanism is four tokens wide**. Most design systems implement density as a
  per-component `size` prop, which multiplies the API surface; here it is an ancestor class and
  the components never learn about it.
- **`keywords` on every nav entry** is the difference between a palette that finds pages and one
  that only finds titles someone already remembers.
- **Empty states are distinguished by cause**: "no data yet" and "no matches for this filter" get
  different copy, from the table config rather than the template.
- `:inert` on the closed mobile sidebar is the correct fix for the classic off-canvas bug where a
  hidden drawer still catches Tab focus — `aria-hidden` alone does not stop focus.
- Toasts and live regions are `role="status"` + `aria-live="polite"` (13 occurrences), dialogs
  `role="dialog"` (15), and `focus-visible` is styled rather than suppressed.
- `prefers-reduced-motion: reduce` is honoured, and the shell also reads
  `matchMedia("(max-width: 1023px)")` in JS rather than duplicating the breakpoint as a magic
  number in two places.
- Export caps are explicit and stated in the UI copy (PDF capped at 500 rows) rather than
  discovered by a timeout.

### Strengths

- Token discipline is enforced *by construction*: components cannot express an off-system colour
  because they only ever name roles.
- One source of truth for navigation, so a new page cannot appear in the sidebar and be missing
  from the palette.
- Table capabilities that are usually per-screen bespoke work (saved views, column visibility,
  export, multi-sort) are declared once per table in ~15 lines.
- Accessibility is present in the primitives, not bolted on: skip link, `:inert`, live regions,
  `aria-current`, focus-visible, reduced motion.
- Zero-build client layer: the whole interaction library is one script, no bundler.

### Weaknesses / Limitations

- **The showcase is not a contract.** There is no visible component API documentation, no prop
  table, no story-per-state, and no visual-regression or a11y test evidence — the gallery page
  *is* the documentation, which drifts silently.
- `/pages/forms/` — the forms showcase, i.e. one of the pages a buyer would evaluate — returns
  **HTTP 500** on the live demo. The error-page showcase works; the form showcase does not.
- Only ~30 semantic tokens, but the stylesheet still carries a large number of raw
  `dark:bg-<palette>-900/30`-style utilities, so the "components only name roles" rule is
  followed in the shell and broken in page content — the discipline is cultural, not verified.
- No i18n. Every string is English in the template; there is no locale layer at all.
- Domain logic is demo-grade: seeded data, stub workflows. Any real use means replacing the
  inside of every page while keeping the shell.
- Charts are a thin wrapper over the chart vendor's own config objects — no house chart grammar,
  so chart colour consistency depends on each call site remembering `--chart-N`.
- Behaviour factories are global functions on one script with no module boundaries, no types, and
  no unit tests visible.

### Visible vs Hidden Metrics

- **Visible (advertised):** ~38 pages and 4 dashboard variants; a ~30-item component gallery;
  8 chart types; a datatable with saved views, column visibility, 3 export formats, 6 filter
  widgets, multi-sort; realtime notifications; PWA install + push; light/dark; 3 density modes.
  All self-reported by the demo — none independently verified, and one advertised showcase page
  is a 500.
- **Hidden (inherited costs):** the page count is the cheap half — every page is a shell over
  seeded data, so adopting the *look* is fast and adopting the *substance* is a rewrite. The
  zero-build client layer trades bundler complexity for untyped, untested, globally-scoped
  behaviour. The token layer is only as good as the review that stops a raw palette step landing;
  with no lint rule or guard, it decays. No i18n means retrofitting a locale layer through every
  template later. No component API docs or state stories means the gallery and the code drift,
  and nobody notices until a state looks wrong in production.
- **Weighing:** for AutoBot the *visible* inventory is almost entirely irrelevant — the pages are
  domain pages we do not want, in a stack we do not use. What survives the hidden-cost test is
  the **structural** half: the semantic-token layer, density-as-token-scope, `data-slot` part
  contracts, one nav registry feeding sidebar + palette, and declarative table configuration.
  Those are cheap to adopt, stack-agnostic, and each removes a class of per-screen divergence.
  The parts to reject are the ones whose hidden costs we have already paid to avoid: their
  untyped global behaviour layer (we have typed Vue SFCs), their undocumented gallery (we have
  Storybook), and their no-i18n templates (we have vue-i18n across 11 locales).

---
## AutoBot Comparison: the reference work → AutoBot

Scope approved by the owner: **consistency of application**, not palette adoption. AutoBot keeps
its own colour schemes; the question is where the GUI applies them inconsistently. Every figure
below is a measurement over `autobot-frontend/src` (456 `.vue` files) plus `libs/autobot-ui`,
taken 2026-09-26 on `main` at `ea7058ac8e`. Counts name their glob and their pattern so they can
be re-run.

### What We Already Do Better

- **Theming is a token table, not a per-component override sweep — and ours is enforced further
  than theirs.** `var(--…)` appears 26,183 times across 364 of 456 `.vue` files, while the `dark:`
  variant appears only 75 times in 16 files. Dark/light/ember/accents are swapped by re-declaring
  tokens in `autobot-frontend/src/assets/css/themes/{dark,light,accents,ember}.css`, reached via
  `assets/css/index.css`. The reference work states the same rule but breaks it in page content
  (its stylesheet still ships raw `dark:bg-<palette>-900/30`-style utilities).
- **We have the runtime token bridge the reference work lacks.**
  `autobot-frontend/src/composables/useCssVars.ts` exposes `getCssVar(token, fallback)`, and
  `components/charts/BaseChart.vue` resolves its entire Apex theme through it — `foreColor`, axis
  labels, grid, tooltip and a 10-colour series palette from `--chart-blue … --chart-indigo`
  (`assets/css/design-tokens.css` carries 81 `--chart-*` lines). Canvas/WebGL/Apex renderers
  cannot read CSS variables; the reference work solves this by asking each call site to remember
  `--chart-N`, we solve it once in the base component.
- **Component documentation is executable, not a gallery page.** 257 `*.stories.ts` against 456
  `.vue` files. The reference work's entire documentation is one `/components/` page, which drifts
  silently — and one of its advertised showcase pages (`/pages/forms/`) is a live HTTP 500.
- **i18n exists.** `vue-i18n` across all locales. The reference work has no locale layer at all,
  so every string there is English in a template.
- **Some token vocabulary is lint-enforced.** `autobot-frontend/eslint.config.ts` blocks the
  deprecated `size` values `small|medium|large` (canonical `sm|md|lg`) via
  `vue/no-restricted-static-attribute` and the bound-literal equivalent via
  `vue/no-restricted-syntax` (MVA-192). The reference work has no such rule — its token discipline
  is purely cultural.
- **A11y primitives are broadly present:** `focus-visible` styled in 102 files, `aria-live` in 31,
  `role="dialog"` in 19, `prefers-reduced-motion` in 10, `#main-content` landmark in
  `App.vue:536`.

### Gaps & Opportunities

Ordered by impact on visual consistency. G1 is the root cause of most visible divergence; several
later items are symptoms that will re-appear unless G1 and G2 land.

**G1 — Three namespaces define the same primitives, and two of them disagree.** *(highest impact)*

| Primitive | `libs/autobot-ui` | `src/components/base/` | `src/components/ui/` | importers |
|---|---|---|---|---|
| BaseButton | ✅ 158 lines | ✅ 477 lines | — | 23 from lib / 66 from `base/` |
| BaseCard | ✅ | ✅ | — | 2 / 3 |
| BaseBadge | ✅ | ✅ | — | 5 / 8 |
| EmptyState | ✅ | — | ✅ | 8 from lib / 46 from `ui/` |
| BaseModal | ✅ | — | *(story only)* | — |
| BaseInput, BasePanel, BaseTable | — | ✅ | — | — |
| DataTable, BaseAlert, +20 | — | — | ✅ | — |

`@autobot/ui` is a real workspace package (`libs/autobot-ui`, `file:` dependency in
`autobot-frontend/package.json:54`) with 5 components and 95 consumer files. Two `BaseButton`
implementations differ threefold in size and do not even share a size type (`ButtonSize` vs
`ComponentSize`) — two buttons that render differently is the single largest source of GUI
inconsistency, and no palette change fixes it.

**G2 — Two primitives disagree on the same semantic word, and the standoff is recorded as
permanent.** `eslint.config.ts` documents that `BaseBadge` accepts `danger` while `ButtonVariant`
uses `error`, so the `danger` ban is deliberately not applied to badges (#11998). A user sees one
concept under two names; a developer picks by trial.

**G3 — No density scope.** The reference work derives three densities from four tokens redefined
on an ancestor class (`--table-row-height`, `--table-cell-py`, `--card-padding`,
`--spacing-unit`). AutoBot has `--card-padding` (one definition in `assets/css/design-tokens.css`)
and no row-height or cell-padding token, so table and card density is per-component literal
spacing.

**G4 — No part contracts on composite components.** No `data-slot` (or equivalent) convention, so
page code that needs to restyle a card header or a table cell reaches in with its own classes —
each reach being a fresh divergence.

**G5 — The nav registry feeds the sidebar and the router, but not the command palette.**
`src/config/navItems.ts` holds 19 typed entries (`{to, labelKey, icon|iconPaths, iconViewBox,
iconRule, iconStroke, featureFlag}`) and is imported by `App.vue` and `router/index.ts`.
`src/components/CommandPalette.vue` builds its own hand-written list at line 130 — four commands
(`new-task`, `new-research`, `new-code`, `new-analysis`). **All 19 navigable destinations are
unreachable from ⌘K.** `NavItem` also has no `keywords` field, so palette search could only ever
match the translated label, never intent words.

**G6 — Tables are the worst-standardised surface in the GUI.** 37 `.vue` files contain a raw
`<table>`; **35 of them use neither shared primitive.** `src/components/ui/DataTable.vue` has
**zero** consumers; `src/components/base/BaseTable.vue` has **one**. There is no shared layer for
sort, filter, pagination, column visibility, saved views, bulk actions or export — the reference
work declares all of that per table in ~15 lines of config.

**G7 — WITHDRAWN (measurement error).** This item originally read *"8 chart components override
the token palette with hex"*, from a count of `#[0-9a-fA-F]{6}` per file. That count was correct
and answered the wrong question. Re-measured with the discriminator that matters — is the hex a
bare literal, or the fallback argument of `getCssVar('--token', '#fallback')`?:

| File | hex | as `getCssVar` fallback | bare |
|---|---|---|---|
| `FunctionCallGraph.vue` | 26 | 26 | **0** |
| `ProblemTypesChart.vue` | 18 | 18 | **0** |
| `RaceConditionsDonut.vue` | 15 | 15 | **0** |
| `DependencyTreemap.vue` | 14 | 14 | **0** |
| `ImportTreeChart.vue` | 13 | 13 | **0** |

`components/charts/` is **already fully tokenised** — every hex is the documented fallback of a
token lookup, which is the correct pattern, and #12022's closure was accurate. No gap, nothing to
file. Recorded rather than deleted because the error is the instructive part: a per-file hex count
is not a measure of tokenisation.

**G8 — Nothing guards raw palette steps or hex literals.** eslint enforces the *size/variant
vocabulary* (G-above) but has no rule against `bg-blue-500` or `#3b82f6` in a `.vue`. Measured
unguarded population:

| Pattern (glob `autobot-frontend/src/**/*.vue`) | occurrences | files |
|---|---|---|
| `(bg\|text\|border\|ring\|from\|to\|divide\|fill\|stroke)-<palette>-<step>` | 689 | 66 of 456 |
| `#[0-9a-fA-F]{6}` total | 713 | 87 |
| …of which are `getCssVar()`/`var()` **fallbacks** (correct pattern) | 463 | — |
| …**bare** hex (the actual population) | **250** | 36 |

And the bare-hex half is smaller still than 250 once the legitimate cases are excluded:
`BaseXTerminal.vue` (42) and `SSHTerminal.vue` (20) pass hex to xterm.js, which takes no CSS
variables, and `ThemePresetPicker.vue` (32) *defines* the presets. Hex in a `<style>` block is
**already guarded** — `autobot-frontend/.stylelintrc.json` sets `color-no-hex` to error over
`**/*.vue` via `postcss-html`, run by `lint:stylelint` and `.github/workflows/stylelint-tokens.yml`.

So the precise, unguarded remainder is two linter blind spots: `postcss-html` parses only `<style>`
blocks, so hex in `<script>`/template attributes is invisible, and **no** linter sees class
attributes, so all 689 raw palette utilities are unguarded. Top of that list — `text-red-600` (33),
`text-red-400` (22), `text-green-600` (22), `bg-red-500` (19), `bg-blue-500` (18) — is status
colour, exactly where `--color-error` / `--color-success` belong. **Already filed as #14580.**

**G9 — Two CSS files claim token authority and are imported by nothing.**
`src/assets/tokens.css` (310 lines) opens *"Canonical CSS Design Tokens … serves as the primary
reference for all design tokens used in AutoBot"* (#7453) and appears in **no** import statement;
`src/assets/main.css` (120 lines) likewise. The live chain is `main.ts` → `assets/tailwind.css`,
`assets/vue-notus.css`, `assets/styles/theme.css`, `assets/styles/view.css`, `assets/css/index.css`
(→ `design-tokens.css` + `themes/*.css` + `components.css`), `assets/css/interaction-polish.css`,
`assets/base.css`, `assets/aui-theme.css`. A file that says it is canonical and is not loaded is
the worst possible signpost for the next person standardising tokens. Per the never-delete rule
this is a *fold-or-wire* job, not a deletion.

**G10 — Shared primitives that do not exist at all.** No `PageHeader` (every view builds its own
title/actions row), no app-wide `Breadcrumb` (only `components/llc/LlcBreadcrumb.vue`, scoped to
one feature), no `Tooltip`, `Popover`, `Accordion`, `Stepper`, `Drawer` or `Pagination`. Tabs exist
only as two feature-local variants (`ChatTabs.vue`, `KnowledgeResearchTabs.vue`). Two theme
toggles ship side by side: `ui/DarkModeToggle.vue` (1 consumer) and `ui/ThemeToggle.vue` (2).
`PageHeader` and `Breadcrumb` are the two with the widest reach — a page header is on every screen.

**G11 — A story with no component.** `src/components/ui/BaseModal.stories.ts` exists with no
`src/components/ui/BaseModal.vue`; it documents `@autobot/ui`'s modal from inside the app's `ui/`
directory. This is how the namespace confusion in G1 became invisible.

**G12 — Skip link.** `#main-content` exists (`App.vue:536`) but no visible "Skip to main content"
affordance (`skip-link` appears in 1 file, the phrase in 0). The reference work ships it on every
page.

### What We Can Adopt

Each item below passed the audit-first gate — the greps and files that prove the gap are cited in
the matching G-item above.

| # | Pattern | Applies to | Visible benefit | Hidden cost | Verdict | Effort |
|---|---|---|---|---|---|---|
| A1 | **One primitive namespace.** Make `@autobot/ui` (`libs/autobot-ui`) the single home; fold `components/base/` and the primitive half of `components/ui/` into it, re-point all importers. | G1, G11 | every button/card/badge renders identically; one API to learn | a large mechanical import sweep across ~100 files, and one merged `BaseButton` must absorb both APIs without regressing 89 call sites | **adopt** — nothing else on this list holds while two implementations exist | significant |
| A2 | **Reconcile the variant vocabulary** to one word per semantic, then extend the existing MVA-192 eslint rules to enforce it. | G2 | `danger`/`error` stop being a coin flip | touches every badge and button call site using the losing word; the #11998 note must be superseded, not contradicted silently | **adopt** — it is a prerequisite for A1's merged API | moderate |
| A3 | **Ratchet baseline on raw palette + hex in `.vue`**, in the style of `pipeline-scripts/hardcoded_values_baseline.txt` (689 + 713 starting population, monotonically down). | G8 | consolidation cannot decay; each PR can only improve it | a baseline needs a per-pattern allowlist for legitimate hex (xterm.js, three.js, canvas, `ThemePresetPicker` presets) or it will be gamed | **adopt** — the reference work's token discipline decayed for exactly want of this | moderate |
| A4 | **Derive the command palette from `navItems.ts`**, and add an optional `keywords?: string[]` to `NavItem`. | G5 | a page cannot be in the sidebar and missing from ⌘K; search matches intent, not just the label | keywords need translating like any other string, so they become 11-locale content | **adopt** | trivial–moderate |
| A5 | **Declarative table configuration** (columns, filters, default sort, page size, bulk actions, empty copy) over a single `DataTable`, then migrate the 35 raw-`<table>` files. | G6 | one table behaviour everywhere; saved views and column visibility become per-table config rather than per-screen code | the config object is a real API to design and version; a half-migrated 35-file surface is worse than none, so this must be sequenced, not sprinkled | **adopt-with-conditions** — land the config + wire `DataTable`'s 0 consumers first, migrate in batches | significant |
| A6 | **Density as a token scope** — `--table-row-height`, `--table-cell-py`, `--card-padding`, `--spacing-unit` redefined by a `.density-*` ancestor class. | G3 | a density control with no component props and no per-component changes | worthless until A5 lands, since 35 tables carry literal spacing that ignores the tokens | **adopt-with-conditions** — after A5 | trivial |
| A7 | **`data-slot` part contracts** on composite primitives. | G4 | page code restyles an internal part without inventing a class | a part name is a public API: rename it later and you break call sites silently | **adopt-with-conditions** — introduce only on primitives merged in A1, never retro-fit ad hoc | trivial per component |
| A8 | **Route every chart colour through `getCssVar`**, incl. the `BaseChart` bypasses. | G7 | theme switches move series colours, not just chrome | `FunctionCallGraph`/`ImportTreeChart`/`ResourceHeatmap` are custom renderers — each needs its own bridge call, not a shared fix | **adopt** — the bridge already exists, this is call-site work | moderate |
| A9 | **`PageHeader` + app-wide `Breadcrumb`**, then `Tooltip`/`Popover`/`Tabs`/`Pagination`. | G10 | every screen's title/action row is identical | each new primitive is a Storybook + i18n + a11y obligation; adding eight at once guarantees some ship unused, like `DataTable` did | **adopt-with-conditions** — `PageHeader` and `Breadcrumb` only, on demonstrated call sites | moderate |
| A10 | **Fold the orphan token files** into the live chain (or into `design-tokens.css`) and delete the false "canonical" claim from the header. | G9 | one true token file; the next standardisation effort starts in the right place | none material | **adopt** | trivial |
| A11 | **Visible skip link** to `#main-content`. | G12 | keyboard users skip 19 nav items | none material | **adopt** | trivial |

**Rejected by hidden metrics** (their visible wins do not survive our costs):

- *Their zero-build behaviour layer* (~18 global untyped factories). Visible: no bundler. Hidden:
  no types, no unit tests, no module boundaries. We have typed SFCs and 257 stories — adopting
  this would be a regression dressed as simplification.
- *Their component gallery as documentation.* Visible: one browsable page. Hidden: it drifts
  silently, and on the live demo one advertised showcase page is a 500. Storybook already covers
  this properly.
- *Their palette and `oklch()` token values.* Excluded by the owner's constraint — AutoBot keeps
  its own colour schemes. Only the *shape* of their semantic layer is of interest, and ours is
  already larger (698 vars in `design-tokens.css`).
- *Their page inventory* (38 showcase pages, 4 dashboard variants). Visible: breadth. Hidden:
  every page is a shell over seeded data in a stack we do not use; adopting the substance is a
  rewrite, and we have our own domain.

### Specific Code/Files Affected

| File | Change |
|---|---|
| `libs/autobot-ui/src/components/` | becomes the single primitive home; absorbs `BaseInput`, `BasePanel`, `BaseTable`, `BaseAlert`, merged `BaseButton`/`BaseCard`/`BaseBadge`/`EmptyState` (A1) |
| `autobot-frontend/src/components/base/` · `components/ui/` | primitives re-exported from `@autobot/ui` during migration, then the shims retire once importers move (A1) |
| `autobot-frontend/src/components/ui/BaseModal.stories.ts` | moves next to the component it documents (A1/G11) |
| `autobot-frontend/eslint.config.ts` | variant-vocabulary rules extended (A2); the #11998 note superseded explicitly |
| `pipeline-scripts/` + new baseline file | raw-palette / hex ratchet with an allowlist for canvas & terminal renderers (A3) |
| `autobot-frontend/src/config/navItems.ts` | `keywords?: string[]` added to `NavItem` (A4) |
| `autobot-frontend/src/components/CommandPalette.vue` | commands derived from `navItems` + its own action commands, replacing the hand-written list at line 130 (A4) |
| `autobot-frontend/src/components/ui/DataTable.vue` | gains the declarative config API and its first consumers (A5) |
| the 35 `.vue` files with a raw `<table>` | migrated to `DataTable` in batches (A5) |
| `autobot-frontend/src/assets/css/design-tokens.css` | density tokens added; orphan token file folded in (A6, A10) |
| `autobot-frontend/src/assets/tokens.css` · `assets/main.css` | folded into the live chain; the false "canonical" header removed (A10) |
| `autobot-frontend/src/components/charts/*.vue` (8 files) + `ImportTreeChart.vue`, `FunctionCallGraph.vue`, `components/visualizations/ResourceHeatmap.vue` | hex literals replaced with `getCssVar('--chart-*', …)` (A8) |
| `autobot-frontend/src/App.vue` | visible skip link to the existing `#main-content` (A11) |
| new: `libs/autobot-ui/src/components/PageHeader.vue`, `Breadcrumb.vue` | with stories + i18n keys (A9) |

### Sequencing

A2 → A1 → A3 (guard the result) → A4 → A5 → A6/A7 → A8 → A9/A10/A11. A1 before A3 because a
baseline taken while two `BaseButton`s exist bakes in the duplication; A2 before A1 because the
merged button API needs one variant vocabulary to merge *into*.

---

## Prior-art reconciliation (added after the duplicate sweep)

The gap list above was written before searching the issue tracker. Most of it was already filed —
recorded here so the doc does not read as a list of unfiled work, and so the *same defect is not
fixed twice*.

| Gap | Already owned by | Status |
|---|---|---|
| G1 three primitive namespaces / duplicate `BaseButton` | **#14776** (retire local `Base*` forks), **#14778** (promote `BaseInput`/`BasePanel`/`BaseTable`), under umbrella **#14774** | fully covered — #14776 names the same four pairs |
| G2 `danger` vs `error` vocabulary | **#14775** (converge the semantic colour vocabulary) | covered. **Correction:** this is *not* a defect to fix by reconciling both words. PR **#11998** recorded owner decision **D3** — presentational unions converge on `danger`; `ButtonVariant` is deliberately left alone as a broader style vocabulary. Treating it as drift would reverse a recorded ruling |
| G8 unguarded raw palette classes | **#14580** (lint raw Tailwind palette classes in `.vue` templates — the `color-no-hex` blind spot) | exactly this finding, already filed |
| G9 orphan `assets/tokens.css` claiming canonical | **#14785** (consolidate the three base token sources) | covered — it already enumerates the unloaded duplicate |
| G10 *partial* — Tooltip, Popover, Tabs, Drawer, Stepper, Pagination, the two theme toggles | **#14779** (Tier-1), **#14780** (Tier-2) | covered; `PageHeader` and `Breadcrumb` appear in **neither** list — that residue is filed below |
| G7 chart hex | — | **withdrawn, measurement error** (see G7) |
| wider colour consistency | **#17560** (67 colour-mapping functions), **#17552** (223 `var()` refs to undefined properties), **#11515** (tokenisation umbrella), **#12711** (disabled-state + contrast) | covered |

### Filed from this research

Children of umbrella **#12730** (*GUI consistency via shared, enforced primitives*):

| Issue | Gap | Wave |
|---|---|---|
| #17561 | G5 — command palette is not fed by the nav registry | 1 |
| #17562 | G6 — main-GUI table standardisation (`DataTable` has zero consumers) | 2 |
| #17563 | G10 residue — `PageHeader` + app-wide `Breadcrumb` | 2 |
| #17564 | G3 + G4 — no density scope, no part contracts | 3 |
| #17565 | G12 — no visible skip link | 1 |

The lesson worth keeping from this pass: of twelve gaps found by comparison, **seven were already
filed, one was a measurement error, and four were new.** The comparison was still worth running —
but the duplicate sweep, not the comparison, is what made the output safe to act on.

---

## Scope correction: AutoBot has two GUIs, and the audit above measured one

Everything above `## Scope correction` was measured over `autobot-frontend` alone. AutoBot ships
**two** Vue GUIs, and the second inverts the audit's central verdict.

| | `autobot-frontend` | `autobot-slm-frontend` |
|---|---|---|
| `.vue` files | 456 | 113 |
| views | 81 | 66 |
| `.stories.ts` | 257 (56%) | 11 (**10%**) |
| raw palette utilities | 689 in 66 files (14%) | **6,213 in 104 files (92%)** |
| …per file | 1.5 | **55** |
| `var(--token)` | 26,183 in 364 files (80%) | 737 in **12** files (11%) |
| bare hex | 250 in 36 | 19 in 4 |
| `dark:` variant | 75 in 16 | 14 in 1 |
| own token names | 572 | 173 — **only 62 shared with the other GUI** |
| `@autobot/ui` importers | 95 | 14 |
| raw `<table>` files | 37 | 31 (**no table component of any kind**) |
| shell landmarks in `App.vue` | `<header>`, `<nav>`, `<main>`, sidebar | `<main>` only |
| command palette | yes (4 hand-listed commands) | **none** |
| nav registry | `config/navItems.ts`, 19 entries | inline in `Sidebar.vue:59`, 14 entries, different shape |
| skip link | **none** | **`components/common/SkipLink.vue` + story** |

**The verdict "AutoBot is more token-disciplined than the reference work" holds for the main GUI
and is false for the fleet console.** At 55 palette utilities per file against 6.5 token
references, `autobot-slm-frontend` is not a partial application of the design system — it is a
Tailwind-palette UI that happens to sit beside one. On this dimension the reference work is ahead
of us, and any claim of a consistent GUI has to survive both packages.

Two asymmetries are worth keeping separate, because a single combined metric hides both:

- **Palette-class overrides are an SLM problem** — 6,213 vs 689.
- **Token-level overrides turned out not to exist.** See the correction below. `!important` remains
  a main-GUI concentration: 58 uses in 14 files vs 4 in 3.

And one correction the two-GUI view produced: the skip-link gap (G12) is not a missing component.
The SLM GUI already has `SkipLink.vue` with a story; the main GUI does not. The work is promotion
into the kit, not construction — #17565 was corrected accordingly.

### The local-override census

Under the owner rule of 2026-09-26 — *"there should not exist any local overrides and design
system needs to be enforced"* — these are the forms a local override takes, and what catches each:

| Override form | main GUI | SLM GUI | Detector |
|---|---|---|---|
| hex in a `<style>` block | — | — | ✅ `stylelint` `color-no-hex` via `postcss-html` |
| raw Tailwind palette utility | 689 / 66 | 6,213 / 104 | ⏳ #14580 (decision now made: gate, not report) |
| bare hex in `<script>`/template | ⊂ 250 / 36 | ⊂ 19 / 4 | ✅ **#17568** (shrink-only, whole-tree) |
| ~~`--token` redefined in component `<style>`~~ | ~~47 / 12~~ → **0** | 0 | **withdrawn — not a defect** |
| `!important` in component `<style>` | 58 / 14 | 4 / 3 | ❌ none → #17567 |
| local fork of a kit primitive | 4 pairs | — | ❌ none → #14776 |
| disjoint token vocabulary | 572 names | 173, 62 shared | ⏳ #14775, #14785, #17566 |

Four of seven forms have no detector. That is the concrete content of "the design system is
advisory, not enforced" — #12730's stated root cause, now measured.

### Also filed from this pass

| Issue | Parent | Finding |
|---|---|---|
| #17566 | #11515 | `autobot-slm-frontend` is effectively untokenised — 6,213 palette utilities across 92% of its component files; 173-name vocabulary sharing only 62 names with the main GUI |
| #17567 | #12730 | three local-override forms with no detector at all |

`#14580` received the sizing it asked for (6,902 occurrences / 170 files across both packages) plus
the owner's gate-vs-report decision, and a recommendation to ratchet rather than hard-fail —
a repo-wide hard fail would make 92% of the SLM GUI un-editable.


---

## Correction: the "47 token redefinitions" were not overrides, and were not 47

Filed as form 2 of #17567, withdrawn the same day after a peer session challenged it and both
readings were re-derived. The census row above claimed 47 components redefining a design token in
their own `<style>` — the purest form of the local override the owner rule bans.

Parsing the **868** names declared in the token-source CSS (`assets/css/**`, `tailwind.css`,
`base.css`, `assets/styles/*.css`, `aui-theme.css`, `tokens.css`) and then classifying every
custom-property declaration inside a component `<style>`:

| | count | files |
|---|---|---|
| assigns a name **the theme owns** — a real override | **0** | 0 |
| declares a **component-local** name — an alias | **34** | 7 |

`--rule-accent` (18), `--tw-ring-color` (6), `--index` (6), `--skeleton-bg` / `--skeleton-shimmer`
(2 each). `WorkflowCanvas.vue:2609-2626` maps state→token in one place and reads
`var(--rule-accent)` throughout — which is what a design system is *for*. A guard on this count
would have made inlining or hardcoding the cheapest way to pass.

**Three numbers, none wrong arithmetically:**

| number | regex | error |
|---|---|---|
| 13 | `--x:` at line start | missed single-line `{ --rule-accent: … }` rules |
| 47 | `--x:` anywhere | matched BEM modifiers in selectors — `.wr-btn--primary:hover` reads as a declaration of `--primary` |
| **34** | `--x:` preceded by `{`, `;` or line start | correct |

Two sessions, two regexes, two different errors, and the right answer produced by neither on the
first pass. The magnitude needed *"declaration or selector?"*; the **verdict** needed *"which names
does the theme own?"* — and only the second one mattered, because it took the finding from
"47 violations" to "no violations". This is the same failure as G7 above, three sections apart:
a correct count answering a question nobody asked. Two in one audit is the rate to plan for, not
an anomaly.

### The enforcement ordering this exposed

`stylelint-tokens.yml` runs `stylelint-changed` — changed files only. So the CSS half of
enforcement is gated for *new* drift and never sweeps the tree: **"the rule is configured" and
"the tree obeys it" are different claims**, and only the first is true today. The order is ratchet
each form → drain the populations → *then* switch the gates to whole-tree. Recorded as an
acceptance criterion on #17567, which now owns it.

---

## The canonicality finding — what the owner rules resolved to

Three owner statements on 2026-09-26, escalating: *keep the colour schemes, make their application
consistent* → *no local overrides, enforce the design system* → *all design system must be
canonical, and the canonical system must itself be enforced.*

Read together they reframe this whole audit. The question is not "which patterns should AutoBot
adopt" but **"why can a second implementation of a design-system concept land without
contradicting anything?"** — and the answer is that canonicality is asserted in roughly fifteen
issues across three umbrellas and declared in no single place a machine can read.

### The mechanism already exists and was never populated

`autobot-frontend/scripts/canonical_check.mjs` (80 lines) is a finished rule-discovery harness:
`scripts/canonical/{registry,reporter,diagnostic}.mjs`, a `__tests__/` suite with fixtures, its own
`vitest.config.mjs`, an `--explain <rule-id>` mode, and `.github/workflows/canonical-audit.yml`.
The rule contract is `RULE_ID · ISSUE · SEVERITY · TARGETS · DESCRIPTION · FIX_HINT ·
check(filePath)`, with a `// canonical: ignore <rule-id>` waiver convention — and `TARGETS` is an
array, so one rule covers both GUIs.

It holds **one** rule: `fe_console_log_smoke.mjs`, `SEVERITY = "warn"`, self-described as *"a
pipeline smoke-test rule"*. Its epic, #7458, is **closed**. The harness was built to carry a
canonical-pattern rule set, shipped a smoke test to prove the plumbing, the epic closed, and no
design-system rule was ever added. The workflow *"Generate audit reports"* and uploads an artifact;
nothing fails.

So the gap is not tooling. It is a **declaration** plus rules plus a severity.

### The declaration pattern AutoBot already owns

`autobot_shared/store_authority.py` states in code which store is authoritative for each persisted
concept, and its docstring gives the reason worth copying: the table lives in code rather than in
`docs/` **"so it is reachable from the copy site"** — a module calls `system_of_record()` at import
time and fails loudly on a name the table does not know, with
`repo_tests/store_authority_test.py` enforcing the converse and a 32-line baseline holding the
known population. Nothing equivalent exists for the design system, which is why there are two
`BaseButton`s and nothing to contradict.

### The inventory, as canonicality violations

| Concept | implementations | owner |
|---|---|---|
| `BaseButton` | 2 — 158 lines / 23 importers vs 477 lines / 66 importers, no shared size type | #14776 |
| `BaseCard` · `BaseBadge` · `EmptyState` | 2 each — 2v3 · 5v8 · 8v46 importers | #14776 |
| base tokens (main GUI) | 4 sources, one of them the unloaded `assets/tokens.css` that calls itself canonical | #14785 |
| token vocabulary across GUIs | 2 disjoint sets — 572 vs 173 names, 62 shared | #14775, #17566 |
| graph renderer | 8 components, largest 2,165 lines | #17569 |
| table primitive | 2, with 0 and 1 consumers, against 68 hand-rolled `<table>` files | #17562 |
| theme toggle | 2 | #14780 |
| nav registry | 2, different shapes | #17561 |
| notification · button-class · date-format | 3 · 2 · 4 | #12731 |

Filed as **#17571** (critical): the registry in `libs/autobot-ui`, rules added to the existing
harness, severity raised to `error`, the gate failing rather than reporting, waivers requiring a
reason and an issue link — and explicitly **no new framework**, since duplicating
`canonical_check.mjs` would be the very failure the rule is about. No `blocked_by` edges were
recorded against the eight related issues: none of them is actually blocked, and a false edge
would stall eight issues behind one.

### What this audit is really a case study in

Twelve gaps from the comparison: seven already filed, one a measurement error, four new. Then two
further findings arrived from *outside* the comparison entirely — the second GUI, and the
codebase-analytics graph — each of which changed a headline verdict. And two of my own findings
were correct counts answering the wrong question.

The comparison was worth running. But **the duplicate sweep, the scope check ("which of the two
GUIs?"), and the discriminator question ("would more data change this answer?") did more work than
the comparison did** — and all three are cheap. A future pass should spend its first third there,
not on the source.

---

## Corrections since publication (added on commit, 2026-09-27)

The audit above is left as written — it is dated evidence, and rewriting its
findings would destroy the record of what was measured on the day. Three of its
figures were superseded before it landed. They are corrected here rather than
in place, and the review threads on PR #17568 raised all three.

**1. `BaseButton` importer counts (§ the canonicality inventory).** The body
gives 23 shared-kit importers against 66 local. Re-measured by resolved import
specifier, counting **both** default and named barrel imports:

| | `@autobot/ui` | local fork |
|---|---|---|
| `BaseButton` | 3 | 68 |
| `EmptyState` | 1 | 48 |
| `BaseBadge` | 3 | 9 |
| `BaseCard` | 1 | 4 |
| `BaseModal` | 63 | 0 |

The material point is unchanged and sharper: four components are imported from
**both** sources in the same application, so which implementation renders
depends on which line a given file wrote. `BaseModal` at 63/0 shows the
migration already succeeded once. A first pass at this returned *zero* kit
importers and nearly concluded the shared library was unused — the kit is
consumed through its barrel, `import { BaseButton } from '@autobot/ui'`, which
a default-import pattern does not match.

**2. `assets/tokens.css` is not a token source.** The body counts four base
token sources including this file. It declares **no tokens at all**: 310 lines,
zero non-comment lines, and its 106 "tokens" are names written in prose. It
cannot shadow or drift into anything. The audit's own G9 is accurate — it says
only that the file claims authority and is imported by nothing — and the
overstatement is in #14785's body, corrected there. The inventory should read
**three loaded sources**, plus two files claiming authority that nothing imports
(`assets/tokens.css`, `assets/main.css`).

**3. The frontend canonical audit is not wired into CI.** The section on
`canonical-audit.yml` overstates current enforcement. Measured by running it:

- The workflow runs the Python and infrastructure audits and writes a
  placeholder for the frontend one. It never invokes
  `autobot-frontend/scripts/canonical_check.mjs`.
- `canonical_check.mjs --all` reports `0 violations` and exits 0, while the same
  rule on the same tree finds a violation when handed the file directly
  (`src/composables/useLocalStorage.ts:531`). `--all` is accepted and the walk
  is unimplemented — marked *"a Wave 3 task"*.
- Its file filter admits only `.ts|.vue|.mjs|.js`, so the token layer is out of
  scope entirely.
- The run exits non-zero only on `severity === "block"`; the single shipped rule
  is `warn`.

So the harness exists, is well built, and enforces nothing today. That does not
weaken the audit's conclusion — it strengthens it, and it is why #17571 is
harness work before it is rule work.
