# TypeScript Error Baseline — Dev_new_gui

**Date:** 2026-04-24
**Branch:** Dev_new_gui
**Command:** `npx vue-tsc --noEmit -p tsconfig.app.json`
**Total: 2005**

> Note: Issue #5096 originally reported 169 errors. The actual count at audit time is 2005.
> The delta-check gate uses this file as the authoritative baseline.

---

## Breakdown by Error Code (top 20)

| Error Code | Count | Description |
|-----------|-------|-------------|
| TS7006 | 772 | Parameter implicitly has an `any` type |
| TS2307 | 686 | Cannot find module or its type declarations |
| TS2339 | 331 | Property does not exist on type |
| TS18046 | 100 | Variable is of type `unknown` |
| TS2365 | 26 | Operator not applicable to types |
| TS2304 | 18 | Cannot find name |
| TS2882 | 15 | Cannot access ambient const before init |
| TS7031 | 13 | Binding element implicitly has `any` type |
| TS7053 | 12 | Element implicitly has `any` (index expression) |
| TS2345 | 9 | Argument of type X not assignable to parameter of type Y |
| TS2362 | 5 | Left-hand side of arithmetic not of type `any`/`number`/`bigint` |
| TS5097 | 3 | `rootDir` is not below `rootDirs` |
| TS2352 | 3 | Type conversion may be a mistake |
| TS2769 | 2 | No overload matches this call |
| TS2559 | 2 | Type has no properties in common |
| TS2322 | 2 | Type X is not assignable to type Y |
| TS5083 | 1 | Cannot read file `tsconfig.node.json` |
| TS2664 | 1 | Invalid module name in augmentation |
| TS2554 | 1 | Expected N arguments but got M |
| TS2363 | 1 | Right-hand side of arithmetic not of type `any`/`number`/`bigint` |

---

## Breakdown by File (top 15 files)

| File | Error Count |
|------|-------------|
| `src/components/desktop/PopoutChromiumBrowser.vue` | 170 |
| `src/App.vue` | 105 |
| `src/components/browser/BrowserSessionManager.vue` | 59 |
| `src/stores/useChatStore.ts` | 43 |
| `src/components/charts/FunctionCallGraph.vue` | 27 |
| `src/components/visualizations/ResourceHeatmap.vue` | 23 |
| `src/stores/useKnowledgeStore.ts` | 22 |
| `src/main.ts` | 20 |
| `src/composables/useBatchProcessing.ts` | 20 |
| `src/views/WorkflowBuilderView.vue` | 18 |
| `src/components/knowledge/KnowledgeStats.vue` | 17 |
| `src/stores/useAppStore.ts` | 16 |
| `src/composables/useApi.ts` | 16 |
| `src/components/knowledge/KnowledgeGraph.vue` | 16 |
| `src/composables/useAuditApi.ts` | 15 |

---

## How to Update This Baseline

Run the following from `autobot-frontend/`:

```bash
cd autobot-frontend

# Get full error list
npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 > /tmp/ts-errors.txt

# Total count
grep -c "error TS" /tmp/ts-errors.txt

# Breakdown by error code
grep "error TS" /tmp/ts-errors.txt \
  | sed 's/.*error \(TS[0-9]*\).*/\1/' \
  | sort | uniq -c | sort -rn | head -20

# Breakdown by file
grep "error TS" /tmp/ts-errors.txt \
  | cut -d'(' -f1 \
  | sort | uniq -c | sort -rn | head -15
```

Update the `Total:` line and the tables in this file, then commit with message:
`docs(frontend): update TypeScript baseline to <N> errors (#<issue>)`

The delta-check script (`autobot-frontend/scripts/check-ts-delta.sh`) reads the `Total:` line
from this file automatically — no changes to the script are needed after updating this doc.

---

## CI Delta-Check

The script `autobot-frontend/scripts/check-ts-delta.sh` enforces this baseline:
- Runs `npx vue-tsc --noEmit -p tsconfig.app.json` and counts errors
- Reads the `Total:` value from this file
- Exits 1 (fail) if `current_errors > baseline`
- Exits 0 (pass) if `current_errors <= baseline`

Add to CI:
```yaml
- name: TypeScript delta check
  run: bash autobot-frontend/scripts/check-ts-delta.sh
  working-directory: .
```
