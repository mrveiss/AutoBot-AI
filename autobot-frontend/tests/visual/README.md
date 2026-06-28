# Visual regression tests

Pixel-diff every Storybook story against baseline PNGs. Catches the kind of
drift that type-check + unit tests miss — design-token rounds, icon path
typos, layout shifts, color regressions.

This was the safety gap closed by #5077, originally surfaced because
PRs #5036 / #5043 / #4805 each touched 30+ UI files with no way to verify
the visual result.

> **Baselines are NOT committed (#9825 cleanup).** `__screenshots__/` is
> gitignored. Developer-machine PNGs (incl. WSL2) never matched ubuntu-latest
> CI font rendering, so committed baselines caused constant false failures on
> every PR (#10316/#10320) for a non-required gate, plus ~23 MB of binary churn.
>
> Visual regression now runs **on demand**, not per-PR:
> - **Authoritative CI baseline set:** dispatch the *Visual Regression* workflow
>   with `regenerate_baselines=true` — it builds the baseline artifact on
>   ubuntu-latest.
> - **Locally:** `npm run test:visual` (generates baselines on first run; they
>   stay local/untracked).
>
> To restore a per-PR committed-baseline gate later: generate the set via the
> workflow, commit it, and re-add the `pull_request` trigger.

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

## ⚠️ Baseline generation policy — read before running `--update-snapshots`

**Linux baselines must be generated on the CI runner (ubuntu-latest), not
on a developer machine — even if that machine runs Linux.**

Font rendering on WSL2, macOS Docker containers, or other Linux variants
differs from the GitHub Actions `ubuntu-latest` runner in ways that exceed
the 100-pixel diff tolerance. Committing locally-generated `-linux.png`
baselines will cause CI failures for other contributors.

This policy was established after [MVA-270] to fix renderer-mismatch
failures on 6-7 stories (CommandPermissionDialog, EmptyState,
HostSelectionDialog, Icon, StableLoadingState, ThemeToggle, NavOverflowMenu).

### Correct way to regenerate baselines

**Option A — GitHub Actions workflow_dispatch (recommended):**

1. Go to **Actions → Visual Regression → Run workflow** on GitHub
2. Select your branch, set **Regenerate baselines** to `true`, and run
3. When the run finishes, download the `visual-regression-updated-baselines-*`
   artifact
4. Extract it and copy the contents into
   `autobot-frontend/tests/visual/__screenshots__/`
5. Commit and push — the baselines came from the exact CI environment and
   are guaranteed to match future CI runs

**Option B — Docker (for local iteration):**

```bash
# Run inside a container that matches ubuntu-latest
docker run --rm \
  -v "$(pwd)":/workspace \
  -w /workspace/autobot-frontend \
  mcr.microsoft.com/playwright:v1.52.0-jammy \
  bash -c "npm ci && SKIP_STORYBOOK_START=1 npm run test:visual -- --update-snapshots"
```

The Playwright Docker image ships with the same Chromium version and system
fonts used in CI, eliminating rendering drift.

**Option C — native ubuntu-22.04/24.04 only:**

If you have an actual Ubuntu 22.04/24.04 install (not WSL2, not Docker),
you can run `npm run test:visual -- --update-snapshots` directly. Verify
the CI passes before opening the PR.

### Never do this

- `--update-snapshots` on macOS → committing the `-linux.png` files
- `--update-snapshots` on WSL2 → committing as CI baselines
- Accepting a "first run" artifact from a non-CI source

## Workflow

### When adding a new component

1. Write the component as usual
2. Add a `*.stories.ts` file demonstrating the variants you care about
3. Use Option A or B above to generate CI-matched baselines
4. Commit the new `__screenshots__/*.png` baselines alongside the component

### When intentionally changing visuals

1. Make the design change
2. Run `npm run test:visual` locally — it will fail with a diff showing old
   vs. new rendering
3. Inspect the diff (HTML report) to confirm the change is what you wanted
4. Use Option A or B above to regenerate CI-matched baselines
5. Commit the updated baselines with the design change in the same PR

### When unintentionally breaking visuals

1. PR review fails CI on visual regression
2. Inspect the HTML report artifact from CI to see exactly what shifted
3. Either fix the regression (most common) or update baselines if the
   change was intentional but missed step 2 above

### When CI fails with renderer mismatch

Symptom: CI fails on stories that pass locally; diff looks like font
kerning, antialiasing, or sub-pixel shift.

Root cause: baselines were generated in a different environment than the CI
runner.

Fix: use Option A (workflow_dispatch) to regenerate baselines directly on CI.

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
