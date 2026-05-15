# TypeScript Error Baseline — Dev_new_gui

**Date:** 2026-04-25
**Branch:** Dev_new_gui
**Command:** `npx vue-tsc --noEmit -p tsconfig.app.json`
**Total: 188**

> **Correction (2026-04-25):** The original baseline of 2005 (recorded 2026-04-24) was inflated.
> Re-running `npx vue-tsc --noEmit -p tsconfig.app.json` on 2026-04-25 produces **188 errors**.
> The 686 TS2307 "cannot find module" errors in the original are absent — they were artefacts of
> a different tsconfig or invocation. Zero missing-module errors exist on this branch.

---

## Breakdown by Error Code

| Error Code | Count | Description |
|-----------|-------|-------------|
| TS18046 | 74 | Variable is of type `unknown` |
| TS2322 | 27 | Type X is not assignable to type Y |
| TS2353 | 23 | Object literal may only specify known properties |
| TS2339 | 22 | Property does not exist on type |
| TS2304 | 18 | Cannot find name |
| TS2561 | 6 | Object literal may only specify known properties (did you mean?) |
| TS2769 | 4 | No overload matches this call |
| TS2352 | 3 | Type conversion may be a mistake |
| TS2440 | 2 | Import declaration conflicts with local declaration |
| TS2559 | 2 | Type has no properties in common |
| TS2345 | 2 | Argument of type X not assignable to Y |
| TS7053 | 1 | Element implicitly has `any` type (index expression) |
| TS7006 | 1 | Parameter implicitly has an `any` type |
| TS2554 | 1 | Expected N arguments but got M |
| TS2551 | 1 | Property does not exist (did you mean?) |
| TS2351 | 1 | This expression is not callable |

---

## Breakdown by File (top 15)

| File | Error Count |
|------|-------------|
| `src/composables/useApi.ts` | 15 |
| `src/composables/useBatchProcessing.ts` | 14 |
| `src/components/visualizations/ResourceHeatmap.vue` | 14 |
| `src/composables/useAutoResearch.ts` | 7 |
| `src/composables/useAuditApi.ts` | 7 |
| `src/composables/useAIDocument.ts` | 7 |
| `src/components/ui/BaseAlert.stories.ts` | 7 |
| `src/composables/useKnowledgeGraph.ts` | 6 |
| `src/components/ui/EmptyState.stories.ts` | 6 |
| `src/components/chat/TranslationShortcutPanel.vue` | 6 |
| `src/components/base/BaseCard.stories.ts` | 6 |
| `src/components/auth/LoginForm.vue` | 6 |
| `src/composables/usePreferences.ts` | 5 |
| `src/composables/useOperationsApi.ts` | 5 |
| `src/components/ui/CommandPermissionDialog.vue` | 5 |

---

## How to Update This Baseline

1. Run: `cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep -c "error TS"`
2. Update `**Total:**` line above with the new count
3. Update the breakdown tables
4. Commit: `docs(frontend): update TypeScript error baseline to N errors`

The `check-ts-delta.sh` script reads the `**Total:**` line automatically — keep that format exact.

---

## High-Value Fix Opportunities

- **TS18046 (74)** — `unknown` type errors in catch blocks and API responses: add `instanceof Error` guards or type assertions
- **TS2353 (23)** — extra properties in stories files: Storybook ArgTypes need updating for component API changes
- **TS2339 (22)** — property doesn't exist: composable return types need explicit interface definitions
