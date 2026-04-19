# Visual regression tests

Pixel-diff every Storybook story against committed baseline PNGs. Catches
the kind of drift that type-check + unit tests miss — design-token rounds,
icon path typos, layout shifts, color regressions.

This was the safety gap closed by #5077, originally surfaced because
PRs #5036 / #5043 / #4805 each touched 30+ UI files with no way to verify
the visual result.

## Quick reference

| Task | Command |
|---|---|
| Run all visual tests (diff against baselines) | `npm run test:visual` |
| Generate / regenerate baselines | `npm run test:visual -- --update-snapshots` |
| Run with Storybook already started elsewhere | `SKIP_STORYBOOK_START=1 npm run test:visual` |
| View HTML report after a failure | `npx playwright show-report` |

## How it works

1. `playwright.visual.config.ts` auto-starts Storybook on port 6006 (unless
   `SKIP_STORYBOOK_START=1` is set — useful for fast iteration when you
   already have `npm run storybook` running)
2. `tests/visual/storybook-stories.spec.ts` fetches Storybook's
   `/index.json` to enumerate every story
3. For each story, navigate to its iframe URL, wait for the root element,
   screenshot the component, diff against the baseline in
   `__screenshots__/`
4. Diffs above the threshold (`maxDiffPixels: 100`, `threshold: 0.2`) fail
   the test. The HTML report shows the actual / expected / diff images
   side-by-side.

Baselines are stored per-OS (`-linux.png`, `-darwin.png`, `-win32.png`)
because subpixel font rendering varies across platforms. CI runs Linux
baselines.

## Workflow

### When adding a new component

1. Write the component as usual
2. Add a `*.stories.ts` file demonstrating the variants you care about
3. Run `npm run test:visual -- --update-snapshots`
4. Commit the new `__screenshots__/*.png` baselines alongside the component

### When intentionally changing visuals

1. Make the design change
2. Run `npm run test:visual` — it'll fail with a diff
3. Inspect the diff (HTML report) to confirm the change is what you wanted
4. Run `npm run test:visual -- --update-snapshots` to accept
5. Commit the updated baselines with the design change in the same PR

### When unintentionally breaking visuals

1. PR review fails CI on visual regression
2. Inspect the HTML report to see exactly what shifted
3. Either fix the regression (most common) or update baselines if the
   change was intentional but missed step 2 above

## Coverage today

Coverage = whatever has a `*.stories.ts`. Currently:

- `auth/LoginForm`
- `base/{BaseAlert, BaseBadge, BaseButton, BaseCard, BaseInput, BaseTable}`
- `ui/{EmptyState, LoadingSpinner}`

**Gaps worth filling** (touched recently, no story → no visual coverage):

- `ui/Icon.vue` (added in #4805 — the icon registry)
- `ui/ThemeToggle.vue`, `ui/DarkModeToggle.vue`
- `ui/BaseModal.vue`, `ui/CommandPermissionDialog.vue`, `ui/PreferencesPanel.vue`
- `ui/HostSelector.vue`, `ui/HostSelectionDialog.vue`
- `ui/ToastContainer.vue`

Adding a story is mechanical (~10-15 lines per variant set). New stories
get visual coverage automatically.

## Why Playwright + Storybook (not Chromatic / Percy)

- **No external service**: tests run anywhere, no SaaS dependency, no
  per-month seat cost
- **Tests live with code**: baselines are in the repo, reviewable in PRs
- **Existing infra**: both Storybook and Playwright were already installed;
  this PR just wired them together
- **Trade-off**: no fancy UI for browsing diffs across PRs (Chromatic's
  strength). Use the local HTML report instead.

If we ever outgrow this and want PR-level diff browsing, swap to Chromatic
later — the stories themselves don't need to change.
