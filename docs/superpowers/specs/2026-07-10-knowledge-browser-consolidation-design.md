# Knowledge Document Browser Consolidation — Design

**Date:** 2026-07-10
**Status:** Approved by owner (design phase)
**Scope:** Frontend UI/navigation only — no backend or API changes.

## Problem

Three Knowledge sidebar pages contain related, overlapping functionality:

| Route | Component | Purpose |
|---|---|---|
| `/knowledge/categories` | `src/components/knowledge/KnowledgeBrowser.vue` (~1600 lines) | Hierarchical fact/file tree, vectorization management |
| `/knowledge/documents` | `src/views/DocumentsView.vue` (~580 lines) | AI document list + editor, transcriber mini-grid |
| `/knowledge/search` | `src/components/knowledge/KnowledgeSearch.vue` (~800 lines) | Traditional + RAG search with filters |

All three already share the singleton `KnowledgeRepository` and the
`src/composables/knowledge/` layer, so consolidation is purely a UI and
navigation merge.

## Decisions (owner-approved)

1. **Layout:** unified explorer — search bar on top, category tree left,
   list + preview/editor right. Search and browsing share the list pane;
   no tabs, no mode switcher.
2. **Navigation:** one sidebar entry; the three old routes are **removed
   outright** (no redirects). Every in-code reference to the old paths is
   updated to the new route.
3. **AI Documents:** a top-level tree branch; selecting a document swaps
   the right pane to the full AI Document Editor (edit + delete retained).

## Design

### 1. Route & navigation

- New single route **`/knowledge/browser`** rendering `KnowledgeBrowser.vue`.
- Remove `/knowledge/categories`, `/knowledge/documents`, `/knowledge/search`
  from `src/router/index.ts` and from the Knowledge sidebar
  (`KnowledgeView.vue`).
- Add one sidebar entry "Browser" (new i18n key, all 11 locales).
- Repo-wide sweep: update every `router.push`, `<router-link>`, legacy
  redirect (e.g. top-level `/documents` → `/knowledge/documents`), test,
  and doc reference from the three old paths to `/knowledge/browser`.
  Completion gate: grep returns zero matches for the old paths.
- Deep-link query params on the new route:
  - `?q=<query>` — opens with search active.
  - `?doc=<id>` — opens the AI document in the editor pane.

### 2. Component architecture

`KnowledgeBrowser.vue` remains the **canonical component** (no new
"Unified"/"Consolidated" variant names) and absorbs the other two views.
It is decomposed into a thin container plus focused children:

- **KnowledgeBrowserSearchBar** (new, extracted from `KnowledgeSearch.vue`):
  query input, RAG toggle; access-level chips, rerank options, and result
  limit behind a "Filters" dropdown. The standalone category dropdown is
  dropped — the selected tree node scopes the search.
- **Tree pane** (existing tree, left): category/folder hierarchy plus a new
  top-level **AI Documents** branch (50-per-page pagination via
  `useAIDocument`), and a collapsed **Transcriber projects** group under it
  whose items link to the existing Transcriber page.
- **List + preview pane** (existing split, right), three states:
  - *Browsing* (no query): current behavior — folder contents,
    `KnowledgeContentViewer` preview, batch-vectorize toolbar.
  - *Searching* (query active): list pane renders `KBSearchResultPanel`;
    RAG synthesis panel above it. Clearing the query restores the
    previously selected tree node's browsing state.
  - *Document selected*: right pane renders the AI Document Editor
    (edit, delete with confirmation modal, focus trap — unchanged).
- **Deleted after absorption:** `KnowledgeSearch.vue`, `DocumentsView.vue`.
  Their composables (`useAIDocument`, `useKnowledgeCategories`,
  `useTranscriberApi`, etc.) are reused as-is.

### 3. Feature parity checklist

Nothing is lost in the merge:

- **Search:** traditional + RAG, reranking, result limit, access-level
  filter, AI synthesis + confidence badges, query reformulation display,
  keyboard navigation in results.
- **Browse:** tree navigation, breadcrumbs, lazy folder loading,
  cursor-based pagination, vectorization status refresh, batch selection
  and vectorize, vectorization progress modal, search-within-tree filter
  with auto-expand.
- **Documents:** paginated list, full editor, delete confirmation modal
  (focus trap, focus restore, body scroll lock), empty states, refresh,
  transcriber projects (relocated under the AI Documents branch).

### 4. i18n

- Reuse existing `knowledge.search.*`, `knowledge.browser.*`, and
  `documents.*` keys wherever the UI element survives.
- Add only genuinely new keys (sidebar label, filter-dropdown affordances)
  to **all 11 locales**. No hardcoded UI strings.

### 5. Error handling

- Search errors, document load/delete errors, and vectorization errors keep
  their existing per-composable handling and toast surfaces; no new error
  paths are introduced.
- Unknown `?doc=` id: fall back to browsing state with the existing error
  toast.

### 6. Testing & verification

- `vue-tsc --noEmit -p tsconfig.app.json` clean.
- Component tests: browse ↔ search ↔ edit state transitions; deep-link
  params; delete flow still guarded by confirmation modal.
- Grep gate: zero references to `/knowledge/categories`,
  `/knowledge/documents`, `/knowledge/search` outside git history.
- Existing lint gate (`--max-warnings 0`) stays green.

## Out of scope

- Backend/API changes of any kind.
- Other Knowledge sidebar pages (Transcriber, Research, Vector Store,
  Graph, MCP Resources, …).
- Redesign of the AI Document Editor internals.
