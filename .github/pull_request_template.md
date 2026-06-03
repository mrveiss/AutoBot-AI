## Thinking Path
<!-- Required: Trace the reasoning from problem context to this change. What problem are we solving? Why this approach over alternatives? -->
Two separate `ChartCell.vue` implementations existed in the codebase: one in `artifact-cells/` (feature-rich with i18n, accessibility, stories, and tests) and one in `canvas/` (simpler, missing features, but actively used). This divergence created maintenance overhead and a risk of bug fixes or new features only being applied to one version. To resolve this, we consolidated to a single canonical version by keeping the robust `artifact-cells/ChartCell.vue` implementation and pointing the canvas components to use it. This approach removes technical debt without losing functionality.

## What Changed
<!-- Required: Bullet list of concrete changes made. Be specific — file names, function names, config keys. -->
- Deleted duplicate components and related files: `autobot-frontend/src/components/canvas/ChartCell.vue`, `ChartCell.stories.ts`, and `ChartCell.spec.ts`.
- Updated import in `autobot-frontend/src/components/canvas/CanvasCell.vue` to point to `../artifact-cells/ChartCell.vue`.
- Updated export in `autobot-frontend/src/components/canvas/index.ts` to point to `../artifact-cells/ChartCell.vue`.

## Verification
<!-- Required: How a reviewer can confirm this works. Include commands to run, endpoints to hit, or UI steps to follow. -->
1. Run the local development server (e.g., `npm run dev`) and trigger an AI response that renders a chart on the canvas to ensure it renders correctly without errors.
2. Run unit tests to confirm tests pass and no missing module errors occur (`npm run test`).
3. Run Storybook (`npm run storybook`) and ensure the remaining `ChartCell` stories under `artifact-cells` load as expected.

## Risks
<!-- What could go wrong; edge cases not covered; rollback plan if needed. Write "None identified" if applicable. -->
Minor layout or styling differences might occur if the deleted `canvas/ChartCell.vue` contained canvas-specific hardcoded logic that wasn't present in the `artifact-cells` version. Rollback plan: Revert the PR if unintended UI bugs appear.

## Model Used
<!-- Required: The AI model that produced or assisted with this change. Format: "Provider ModelID". Write "None — human-authored" if no AI was used. -->
None — human-authored

## Issue Link
<!-- Closes #N or related #N -->
Closes <https://github.com/mrveiss/AutoBot-AI/issues/9220>

## Checklist

- [] Code follows AutoBot patterns from `CLAUDE.md`
- [] Tests added or updated (or N/A with reason) (Removed redundant tests, canonical tests remain)
- [ ] Documentation updated if behavior changed
- [] Pre-commit hooks pass (`git commit` runs them automatically)
- [] PR targets `Dev_new_gui` (not `main`)
- [] No secrets or credentials in the diff
